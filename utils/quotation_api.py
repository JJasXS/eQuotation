"""Quotation API orchestration helpers."""

import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import random

import requests

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings


_QT_DOCNO_RE = re.compile(r"^QT-(\d{5})$")


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _quotation_fallback_item_code() -> str:
    """Stock code used when a line has no code (custom text / unresolved catalog). Must exist in ST_ITEM on the SQL API DB."""
    return (os.getenv("SQL_API_QUOTATION_FALLBACK_ITEM_CODE") or "").strip()


def _quotation_custom_item_code() -> str:
    """Placeholder ST_ITEM.CODE for custom-order quotation lines (description carries the real product text)."""
    raw = (os.getenv("SQL_API_QUOTATION_CUSTOM_ITEM_CODE") or "CUSTOM").strip()
    return raw or "CUSTOM"


def _auto_create_placeholder_items_enabled() -> bool:
    raw = (os.getenv("SQL_API_QUOTATION_AUTO_CREATE_PLACEHOLDER_ITEM") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _normalize_item_code(value: str) -> str:
    """Collapse whitespace; ST_ITEM.CODE may contain spaces (e.g. ``SEMI BOM``)."""
    s = (value or "").strip()
    return re.sub(r"\s+", " ", s) if s else ""


def _default_quotation_line_location() -> str:
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_LOCATION") or "----").strip() or "----"


def _default_quotation_line_uom() -> str:
    """Explicit env override only; otherwise resolve from ST_ITEM per line or tenant default."""
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_UOM") or "").strip()


def _resolve_tenant_default_uom(cur=None) -> str:
    """Best UOM for placeholder/custom lines: env override, else most common ST_ITEM_UOM in this book."""
    configured = _default_quotation_line_uom()
    if configured:
        return configured
    con = None
    try:
        if cur is None:
            db_path = (os.getenv("DB_PATH") or "").strip()
            if not db_path:
                return ""
            import fdb

            db_host = (os.getenv("DB_HOST") or "").strip()
            db_user = (os.getenv("DB_USER") or "sysdba").strip()
            db_password = (os.getenv("DB_PASSWORD") or "masterkey").strip()
            dsn = db_path if not db_host else f"{db_host}:{db_path}"
            con = fdb.connect(dsn=dsn, user=db_user, password=db_password, charset="UTF8")
            cur = con.cursor()
        cur.execute(
            """
            SELECT TRIM(UOM), COUNT(*) FROM ST_ITEM_UOM
            WHERE TRIM(COALESCE(UOM, '')) <> ''
              AND TRIM(UPPER(CODE)) NOT IN ('CUSTOM', 'MISC')
            GROUP BY UOM
            ORDER BY 2 DESC
            """
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
    return ""


def _read_st_item_suom(cur, code: str) -> str:
    try:
        cur.execute(
            "SELECT TRIM(COALESCE(SUOM, '')) FROM ST_ITEM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
            (code,),
        )
        row = cur.fetchone()
        return str(row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _read_item_sales_uom(cur, code: str) -> str:
    """
    UOM accepted by SQL Accounting for sales lines: ST_ITEM_UOM (base row first), then ST_ITEM.SUOM.
    The API validates against ST_ITEM_UOM, not SUOM alone.
    """
    code = _normalize_item_code(code)
    if not code:
        return ""
    try:
        cur.execute(
            """
            SELECT FIRST 1 TRIM(UOM) FROM ST_ITEM_UOM
            WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))
              AND TRIM(COALESCE(UOM, '')) <> ''
            ORDER BY
                CASE WHEN COALESCE(ISBASE, FALSE) = TRUE THEN 0 ELSE 1 END,
                UOM
            """,
            (code,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    return _read_st_item_suom(cur, code)


def _sync_placeholder_item_uom(cur, code: str) -> None:
    """Align placeholder stock with a valid book UOM in ST_ITEM + ST_ITEM_UOM."""
    want = _resolve_tenant_default_uom(cur)
    if not want:
        return
    try:
        cur.execute(
            "UPDATE ST_ITEM SET SUOM = ? WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
            (want, code),
        )
    except Exception:
        pass
    _ensure_st_item_uom_row(cur, code, want)
    try:
        cur.execute(
            """
            DELETE FROM ST_ITEM_UOM
            WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))
              AND TRIM(UPPER(UOM)) <> TRIM(UPPER(?))
            """,
            (code, want),
        )
    except Exception:
        pass


def _default_quotation_line_project() -> str:
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_PROJECT") or "----").strip() or "----"


def _default_quotation_line_irbm() -> str:
    """Optional IRBM classification for all lines when ST_ITEM has none (Malaysia e-invoicing)."""
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_IRBM") or "").strip()


def _placeholder_item_codes() -> set[str]:
    codes = {_normalize_item_code(_quotation_custom_item_code()).upper()}
    fallback = _normalize_item_code(_quotation_fallback_item_code()).upper()
    if fallback:
        codes.add(fallback)
    return codes


def _st_item_exists(cur, code: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM ST_ITEM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
        (code,),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) >= 1)


def _ensure_st_item_uom_row(cur, code: str, uom: str) -> None:
    uom = (uom or "").strip()
    if not uom:
        return
    cur.execute(
        """
        SELECT COUNT(*) FROM ST_ITEM_UOM
        WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))
          AND TRIM(UPPER(UOM)) = TRIM(UPPER(?))
        """,
        (code, uom),
    )
    row = cur.fetchone()
    if row and int(row[0] or 0) >= 1:
        return
    try:
        cur.execute(
            """
            INSERT INTO ST_ITEM_UOM (CODE, UOM, RATE, REFCOST, REFPRICE, ISBASE)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, uom, Decimal("1"), Decimal("0"), Decimal("0"), True),
        )
    except Exception:
        pass


def _ensure_st_item_placeholder(cur, code: str) -> bool:
    """
    Ensure a placeholder stock master exists for custom quotation lines.
    Returns True when ST_ITEM.CODE exists (already or after insert).
    """
    code = _normalize_item_code(code)
    if not code:
        return False
    if _st_item_exists(cur, code):
        _sync_placeholder_item_uom(cur, code)
        return True
    try:
        cur.execute("SELECT GEN_ID(ST_ITEM, 1) FROM RDB$DATABASE")
        dockey = int(cur.fetchone()[0])
        uom = _resolve_tenant_default_uom(cur)
        if not uom:
            return False
        irbm = _default_quotation_line_irbm() or "022"
        cur.execute(
            """
            INSERT INTO ST_ITEM (
                DOCKEY, CODE, DESCRIPTION, STOCKGROUP, STOCKCONTROL, COSTINGMETHOD,
                SERIALNUMBER, MINQTY, MAXQTY, REORDERLEVEL, REORDERQTY, SUOM, ITEMTYPE,
                LEADTIME, BOM_LEADTIME, BOM_ASMCOST, IRBM_CLASSIFICATION, ISACTIVE,
                BALSQTY, BALSUOMQTY, CREATIONDATE, LASTMODIFIED
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dockey,
                code,
                "Custom quotation line (auto)",
                "----",
                True,
                1,
                False,
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                Decimal("1"),
                uom,
                "-",
                0,
                0,
                Decimal("0"),
                irbm,
                True,
                Decimal("0"),
                Decimal("0"),
                date.today(),
                0,
            ),
        )
        _ensure_st_item_uom_row(cur, code, uom)
        return True
    except Exception:
        return False


def _lookup_st_item_uom_irbm(item_code: str, memo: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """Read line UOM (ST_ITEM_UOM) and IRBM from local DB when DB_PATH is set."""
    key = _normalize_item_code(item_code).upper()
    if not key:
        return "", ""
    if key in memo:
        return memo[key]
    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        memo[key] = ("", "")
        return memo[key]
    db_host = (os.getenv("DB_HOST") or "").strip()
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_password = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    uom, irbm = "", ""
    try:
        import fdb

        dsn = db_path if not db_host else f"{db_host}:{db_path}"
        con = fdb.connect(dsn=dsn, user=db_user, password=db_password, charset="UTF8")
        cur = con.cursor()
        try:
            uom = _read_item_sales_uom(cur, item_code.strip())
            try:
                cur.execute(
                    "SELECT TRIM(COALESCE(IRBM_CLASSIFICATION, '')) FROM ST_ITEM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
                    (item_code.strip(),),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    irbm = str(row[0]).strip()
            except Exception:
                pass
        finally:
            cur.close()
            con.close()
    except Exception:
        pass
    memo[key] = (uom, irbm)
    return memo[key]


def _local_itemcode_lookup_enabled() -> bool:
    raw = (os.getenv("SQL_API_QUOTATION_LOCAL_ITEMCODE_LOOKUP") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _resolve_item_code_from_local_db(description_or_code: str) -> str:
    """Match ST_ITEM.CODE when the UI sent a description (or code) but JS did not resolve a code."""
    if not _local_itemcode_lookup_enabled():
        return ""
    needle = (description_or_code or "").strip()
    if not needle:
        return ""
    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        return ""
    db_host = (os.getenv("DB_HOST") or "").strip()
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_password = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    try:
        import fdb

        dsn = db_path if not db_host else f"{db_host}:{db_path}"
        con = fdb.connect(dsn=dsn, user=db_user, password=db_password, charset="UTF8")
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT FIRST 1 TRIM(CODE) FROM ST_ITEM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
                (needle,),
            )
            row = cur.fetchone()
            if row and row[0] and str(row[0]).strip():
                return str(row[0]).strip()
            cur.execute(
                "SELECT FIRST 1 TRIM(CODE) FROM ST_ITEM WHERE TRIM(UPPER(DESCRIPTION)) = TRIM(UPPER(?))",
                (needle,),
            )
            row = cur.fetchone()
            if row and row[0] and str(row[0]).strip():
                return str(row[0]).strip()
            # Optional: substring match when description in UI differs slightly from ST_ITEM.
            fuzz = (os.getenv("SQL_API_QUOTATION_LOCAL_ITEMCODE_CONTAINING") or "").strip().lower()
            if fuzz in ("1", "true", "yes", "on") and len(needle) >= 6:
                cur.execute(
                    """
                    SELECT FIRST 1 TRIM(CODE)
                    FROM ST_ITEM
                    WHERE TRIM(UPPER(DESCRIPTION)) CONTAINING TRIM(UPPER(?))
                    ORDER BY CHAR_LENGTH(TRIM(DESCRIPTION))
                    """,
                    (needle,),
                )
                row = cur.fetchone()
                if row and row[0] and str(row[0]).strip():
                    return str(row[0]).strip()
        finally:
            cur.close()
            con.close()
        return ""
    except Exception:
        return ""


def _local_precheck_quotation(customer_code: str, payload: dict) -> str | None:
    """
    When DB_PATH is set, verify customer and line stock codes exist in local Firebird.
    Catches many 'Operation aborted' cases before calling the SQL API (same company file only).
    Set SQL_API_QUOTATION_LOCAL_PRECHECK=false to skip.
    """
    raw = (os.getenv("SQL_API_QUOTATION_LOCAL_PRECHECK") or "true").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return None
    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        return None
    cc = (customer_code or "").strip()
    if not cc:
        return None
    db_host = (os.getenv("DB_HOST") or "").strip()
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_password = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    try:
        import fdb

        dsn = db_path if not db_host else f"{db_host}:{db_path}"
        con = fdb.connect(dsn=dsn, user=db_user, password=db_password, charset="UTF8")
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM AR_CUSTOMER WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
                (cc,),
            )
            row = cur.fetchone()
            if not row or int(row[0] or 0) < 1:
                return (
                    f'Local DB ({db_path}): customer CODE {cc!r} not found in AR_CUSTOMER. '
                    "Fix the customer in SQL Accounting or align session customer_code with this database."
                )

            if _auto_create_placeholder_items_enabled():
                placeholders = _placeholder_item_codes()
                to_ensure: set[str] = set()
                for d in payload.get("sdsdocdetail") or []:
                    if not isinstance(d, dict):
                        continue
                    ic = _normalize_item_code(str(d.get("itemcode") or ""))
                    if ic and ic.upper() in placeholders:
                        to_ensure.add(ic)
                for ic in sorted(to_ensure):
                    _ensure_st_item_placeholder(cur, ic)
                if to_ensure:
                    con.commit()

            missing_items: list[str] = []
            for d in payload.get("sdsdocdetail") or []:
                if not isinstance(d, dict):
                    continue
                ic = str(d.get("itemcode") or "").strip()
                if not ic:
                    missing_items.append("(blank itemcode)")
                    continue
                cur.execute(
                    "SELECT COUNT(*) FROM ST_ITEM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
                    (ic,),
                )
                r2 = cur.fetchone()
                if not r2 or int(r2[0] or 0) < 1:
                    missing_items.append(ic)

            if missing_items:
                uniq = sorted(set(missing_items))
                return (
                    f"Local DB ({db_path}): no ST_ITEM.CODE for: {', '.join(uniq)}. "
                    "Create these stock items in SQL Accounting, set SQL_API_QUOTATION_FALLBACK_ITEM_CODE, "
                    "or enable SQL_API_QUOTATION_AUTO_CREATE_PLACEHOLDER_ITEM (default on) for placeholder codes like CUSTOM."
                )

            invalid_uom: list[str] = []
            for d in payload.get("sdsdocdetail") or []:
                if not isinstance(d, dict):
                    continue
                ic = str(d.get("itemcode") or "").strip()
                iu = str(d.get("uom") or "").strip()
                if not ic or not iu:
                    continue
                cur.execute(
                    """
                    SELECT COUNT(*) FROM ST_ITEM_UOM
                    WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))
                      AND TRIM(UPPER(UOM)) = TRIM(UPPER(?))
                    """,
                    (ic, iu),
                )
                r3 = cur.fetchone()
                if not r3 or int(r3[0] or 0) < 1:
                    invalid_uom.append(f"{ic}→{iu}")

            if invalid_uom:
                uniq_uom = sorted(set(invalid_uom))
                return (
                    f"Local DB ({db_path}): invalid line UOM (not in ST_ITEM_UOM for item): {', '.join(uniq_uom)}. "
                    "UOM is read from ST_ITEM_UOM (base row), not hard-coded. "
                    "Set SQL_API_QUOTATION_DEFAULT_UOM only if that code exists in ST_ITEM_UOM for the line item."
                )
        finally:
            cur.close()
            con.close()
    except Exception:
        # Do not block quotation if local DB is unreachable; API may still work.
        return None

    return None


def _app_docno_range() -> tuple[int, int]:
    """Return inclusive app reservation range for QT-%.5d numbers."""
    min_seq = _int_env("SQL_API_QUOTATION_DOCNO_MIN", 80000)
    max_seq = _int_env("SQL_API_QUOTATION_DOCNO_MAX", 99999)
    if min_seq < 1:
        min_seq = 1
    if max_seq > 99999:
        max_seq = 99999
    if min_seq > max_seq:
        min_seq, max_seq = 80000, 99999
    return min_seq, max_seq


def _decode_php_json_response(response, endpoint_path):
    """Parse JSON from PHP; return a failed dict if empty/non-JSON."""
    text = (response.text or "").strip()
    if not text:
        return {
            "success": False,
            "error": (
                f"Empty response from {endpoint_path} (HTTP {response.status_code}). "
                "Check that Apache/PHP is running and BASE_API_URL points at your web root."
            ),
        }
    try:
        return response.json()
    except json.JSONDecodeError:
        snippet = text[:400].replace("\n", " ")
        return {
            "success": False,
            "error": (
                f"Non-JSON response from {endpoint_path} (HTTP {response.status_code}): {snippet}"
            ),
        }


def _as_decimal(value, default="0.00"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _fmt_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def _format_qt_docno(sequence: int) -> str:
    if sequence < 1:
        sequence = 1
    return f"QT-{sequence:05d}"


def _read_sl_qt_header_for_sales_api(dockey: int) -> dict:
    """Load CODE, DOCNO and UPDATECOUNT from SL_QT for SQL Accounting salesquotation updates."""
    out: dict = {"code": "", "docno": "", "updatecount": None}
    if dockey <= 0:
        return out
    try:
        from utils import get_db_connection
    except ImportError:
        return out
    con = cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            "SELECT TRIM(CODE), TRIM(DOCNO), UPDATECOUNT FROM SL_QT WHERE DOCKEY = ?",
            (int(dockey),),
        )
        row = cur.fetchone()
        if not row:
            return out
        if row[0] is not None:
            out["code"] = str(row[0]).strip()
        if row[1] is not None:
            out["docno"] = str(row[1]).strip()
        if row[2] is not None:
            try:
                out["updatecount"] = int(row[2])
            except (TypeError, ValueError):
                pass
    except Exception:
        return out
    finally:
        if cur:
            cur.close()
        if con:
            con.close()
    return out


def _safe_float_quotation_email(value, default: float = 0.0) -> float:
    """Convert a value to float for quotation email payloads (comma-safe)."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def fetch_quotation_details_for_email(dockey: int) -> dict:
    """Return the same shape as legacy ``getQuotationDetails.php`` (Firebird only, no PHP/SQL API HTTP).

    Used for customer notification emails (activate quotation, admin update email).
    """
    try:
        dockey_int = int(dockey)
    except (TypeError, ValueError):
        return {"success": False, "error": "Invalid dockey"}
    if dockey_int <= 0:
        return {"success": False, "error": "Invalid dockey"}

    try:
        from utils import get_db_connection
    except ImportError:
        return {"success": False, "error": "Database module unavailable"}

    con = cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT FIRST 1
                q.DOCKEY, q.DOCNO, q.DOCDATE, q.CODE, q.DESCRIPTION, q.DOCAMT,
                q.CURRENCYCODE, q.VALIDITY, q.STATUS, q.TERMS,
                q.COMPANYNAME, q.ADDRESS1, q.ADDRESS2, q.ADDRESS3, q.ADDRESS4, q.PHONE1,
                c.COMPANYNAME, c.CREDITTERM, c.UDF_EMAIL,
                cb.ADDRESS1, cb.ADDRESS2, cb.PHONE1
            FROM SL_QT q
            LEFT JOIN AR_CUSTOMER c ON q.CODE = c.CODE
            LEFT JOIN AR_CUSTOMERBRANCH cb ON q.CODE = cb.CODE
            WHERE q.DOCKEY = ?
            """,
            (dockey_int,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Quotation not found"}

        (
            q_dockey,
            q_docno,
            q_docdate,
            q_code,
            q_description,
            q_docamt,
            q_currency,
            q_validity,
            q_status,
            _q_terms,
            qt_companyname,
            qt_a1,
            qt_a2,
            qt_a3,
            qt_a4,
            qt_phone1,
            c_companyname,
            c_creditterm,
            c_udf_email,
            cb_a1,
            cb_a2,
            cb_phone1,
        ) = row

        def _st(x) -> str:
            if x is None:
                return ""
            return str(x).strip()

        company = _st(qt_companyname) or _st(c_companyname) or "N/A"
        addr1 = _st(qt_a1) or _st(cb_a1) or "N/A"
        addr2 = _st(qt_a2) or _st(cb_a2) or "N/A"
        addr3 = _st(qt_a3)
        addr4 = _st(qt_a4)
        phone1 = _st(qt_phone1) or _st(cb_phone1) or "N/A"
        creditterm = _st(c_creditterm) or "N/A"
        udf_email = _st(c_udf_email)

        cur.execute(
            """
            SELECT TRIM(RF.RDB$FIELD_NAME)
            FROM RDB$RELATION_FIELDS RF
            WHERE TRIM(RF.RDB$RELATION_NAME) = 'SL_QTDTL'
            """
        )
        dtl_columns = {str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]}
        item_fields = [
            "DTLKEY",
            "DOCKEY",
            "SEQ",
            "ITEMCODE",
            "DESCRIPTION",
            "QTY",
            "UNITPRICE",
            "DISC",
            "AMOUNT",
        ]
        for opt in ("UDF_STDPRICE", "DELIVERYDATE"):
            if opt in dtl_columns:
                item_fields.append(opt)

        cur.execute(
            f"SELECT {', '.join(item_fields)} FROM SL_QTDTL WHERE DOCKEY = ? ORDER BY SEQ ASC",
            (dockey_int,),
        )
        item_rows = cur.fetchall() or []
        formatted_items = []
        for ir in item_rows:
            row_map = {item_fields[i]: ir[i] for i in range(len(item_fields))}
            dtl_raw = row_map.get("DTLKEY")
            try:
                dtlkey = int(dtl_raw) if dtl_raw is not None else 0
            except (TypeError, ValueError):
                dtlkey = 0
            seq_raw = row_map.get("SEQ")
            try:
                seq = int(seq_raw) if seq_raw is not None else 0
            except (TypeError, ValueError):
                seq = 0
            item = {
                "DTLKEY": dtlkey,
                "SEQ": seq,
                "ITEMCODE": row_map.get("ITEMCODE"),
                "DESCRIPTION": row_map.get("DESCRIPTION"),
                "QTY": _safe_float_quotation_email(row_map.get("QTY")),
                "UNITPRICE": _safe_float_quotation_email(row_map.get("UNITPRICE")),
                "DISC": _safe_float_quotation_email(row_map.get("DISC")),
                "AMOUNT": _safe_float_quotation_email(row_map.get("AMOUNT")),
            }
            if "UDF_STDPRICE" in item_fields:
                item["UDF_STDPRICE"] = _safe_float_quotation_email(row_map.get("UDF_STDPRICE"))
            if "DELIVERYDATE" in item_fields and row_map.get("DELIVERYDATE") is not None:
                item["DELIVERYDATE"] = str(row_map.get("DELIVERYDATE"))
            else:
                item["DELIVERYDATE"] = None
            formatted_items.append(item)

        quotation_data = {
            "DOCKEY": int(q_dockey) if q_dockey is not None else dockey_int,
            "DOCNO": q_docno,
            "DOCDATE": str(q_docdate) if q_docdate is not None else None,
            "CODE": q_code,
            "DESCRIPTION": q_description,
            "DOCAMT": _safe_float_quotation_email(q_docamt),
            "CURRENCYCODE": q_currency,
            "VALIDITY": q_validity,
            "STATUS": str(q_status) if q_status is not None else "",
            "CREDITTERM": creditterm,
            "COMPANYNAME": company,
            "UDF_EMAIL": udf_email,
            "ADDRESS1": addr1,
            "ADDRESS2": addr2,
            "ADDRESS3": addr3,
            "ADDRESS4": addr4,
            "PHONE1": phone1,
            "items": formatted_items,
        }
        return {"success": True, "data": quotation_data}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def _read_qt_sequences_from_db(limit: int = 2000) -> tuple[int, set[int], str | None]:
    """Return (max_seq, existing_seq_set, error_message) for DOCNO values matching QT-%.5d.

    Uses ``get_db_connection()`` so tenant bootstrap / ``set_db_config`` (same as the rest of
    eQuotation) is respected — not a separate ``os.getenv`` + raw DSN build.
    """
    try:
        from utils import get_db_connection
    except ImportError as exc:
        return 0, set(), str(exc)

    con = cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(f"SELECT FIRST {int(limit)} DOCNO FROM SL_QT ORDER BY DOCKEY DESC")
        rows = cur.fetchall() or []

        max_seq = 0
        existing: set[int] = set()
        for row in rows:
            raw = str(row[0] or "").strip()
            m = _QT_DOCNO_RE.match(raw)
            if not m:
                continue
            seq = int(m.group(1))
            existing.add(seq)
            if seq > max_seq:
                max_seq = seq
        return max_seq, existing, None
    except Exception as exc:
        return 0, set(), str(exc)
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def _fallback_qt_docno() -> str:
    # Last-resort formatter that still follows QT-%.5d.
    return _format_qt_docno(int(datetime.now().strftime("%H%M%S")) % 100000 or 1)


def peek_next_qt_docno(*, for_dockey: int = 0) -> dict:
    """Return the next QT docno eQuotation would use on create (read-only, no API call).

    When ``for_dockey`` is set and the row exists in SL_QT, returns that document's DOCNO
    (update flow — number is not re-allocated).
    """
    if for_dockey > 0:
        hb = _read_sl_qt_header_for_sales_api(for_dockey)
        docno = str(hb.get("docno") or "").strip()
        if docno:
            min_seq, max_seq_allowed = _app_docno_range()
            return {
                "success": True,
                "nextDocno": docno,
                "isUpdate": True,
                "reservedMin": min_seq,
                "reservedMax": max_seq_allowed,
                "note": "Existing quotation — number will not change on save.",
            }

    min_seq, max_seq_allowed = _app_docno_range()
    max_seq, existing, db_err = _read_qt_sequences_from_db(limit=2000)
    db_connected = db_err is None

    if db_err:
        doc_no = _format_qt_docno(min_seq)
        note = (
            f"Could not read SL_QT from Firebird ({db_err}). "
            f"Showing reserved first number {doc_no}; restart the app after tenant DB changes."
        )
    elif max_seq == 0 and not existing:
        doc_no = _format_qt_docno(min_seq)
        note = (
            f"No QT-{min_seq:05d}..QT-{max_seq_allowed:05d} rows found in local SL_QT yet; "
            f"first create will use {doc_no} (or retry with another slot if the API reports duplicate)."
        )
    else:
        doc_no = _next_qt_docno_candidate(max_seq, existing, 0)
        note = ""

    if not doc_no:
        return {
            "success": False,
            "error": (
                f"No available quotation number in reserved range "
                f"QT-{min_seq:05d}..QT-{max_seq_allowed:05d}."
            ),
            "reservedMin": min_seq,
            "reservedMax": max_seq_allowed,
            "dbConnected": db_connected,
            "dbError": db_err,
        }

    return {
        "success": True,
        "nextDocno": doc_no,
        "isUpdate": False,
        "reservedMin": min_seq,
        "reservedMax": max_seq_allowed,
        "maxSeqInDb": max_seq,
        "dbConnected": db_connected,
        "dbError": db_err,
        "note": note,
    }


def _next_qt_docno_candidate(max_seq: int, existing: set[int], attempt: int) -> str:
    """Pick a docno candidate in QT-%.5d format with low collision probability."""
    min_seq, max_seq_allowed = _app_docno_range()

    if attempt == 0:
        baseline = max(max_seq, min_seq - 1)
        candidate = baseline + 1
        if candidate <= max_seq_allowed and candidate not in existing:
            return _format_qt_docno(candidate)

    # On retries, pick random available 5-digit slot to avoid racing with other systems using max+1.
    for _ in range(30):
        seq = random.randint(min_seq, max_seq_allowed)
        if seq not in existing:
            return _format_qt_docno(seq)

    # Fallback to linear probe if random space is saturated.
    start = max(min_seq, max_seq + 1)
    if start > max_seq_allowed:
        start = min_seq
    span = (max_seq_allowed - min_seq) + 1
    for i in range(span):
        seq = min_seq + ((start - min_seq + i) % span)
        if seq not in existing:
            return _format_qt_docno(seq)

    # Range exhausted.
    return ""


def _is_unique_docno_error(status: int, parsed, raw: str) -> bool:
    if status < 400:
        return False
    detail = raw or ""
    if isinstance(parsed, dict):
        detail = str(parsed.get("message") or parsed.get("error") or parsed)
    text = detail.lower()
    return (
        ("unique" in text or "duplicate value" in text)
        and ("document no" in text or "docno" in text or "doc no" in text)
    )


def _strip_client_currency_fields(data: dict) -> dict:
    """Remove browser / Firebird currency fields so save uses SQL API GET /customer only."""
    out = dict(data)
    for key in (
        "currencyCode",
        "currencycode",
        "CURRENCYCODE",
        "customerDetailCurrency",
        "customer_detail_currency",
        "sqlApiCurrencyCode",
    ):
        out.pop(key, None)
    scalars = out.get("customerScalars")
    if isinstance(scalars, dict):
        cleaned = dict(scalars)
        for key in ("currencycode", "currencyCode", "CURRENCYCODE", "customerDetailCurrency"):
            cleaned.pop(key, None)
        out["customerScalars"] = cleaned
    return out


def _resolve_quotation_currency_code(data: dict, customer_code: str) -> str:
    """
    Currency for ``/salesquotation`` — **only** SQL API GET ``/customer?code=…`` (same as create screen).

    Ignores request body, Firebird AR_CUSTOMER, and any MYR/default fallbacks.
    """
    _ = data
    code = str(customer_code or "").strip()
    if not code:
        raise ValueError("Customer code is required to load currency from SQL API.")
    from utils.sql_api_customer import sql_api_currency_and_code

    fields = sql_api_currency_and_code(code)
    cc = str(fields.get("currencycode") or "").strip()
    http_status = str(fields.get("httpStatus") or "").strip()
    if not cc or cc in ("-", "—"):
        hint = f" (SQL API HTTP {http_status})" if http_status else ""
        raise ValueError(
            f"Currency not returned from SQL API GET /customer for customer {code!r}{hint}. "
            "Fix SQL API keys for this tenant and restart eQuotation, then reload Create Quotation."
        )
    return cc


def _build_salesquotation_payload(customer_code, data, *, doc_no: str):
    header_dockey = int(data.get("dockey") or data.get("docKey") or 0)
    uc_raw = data.get("updatecount") if data.get("updatecount") is not None else data.get("updateCount")
    try:
        updatecount_val = int(uc_raw) if uc_raw is not None and str(uc_raw).strip() != "" else 0
    except (TypeError, ValueError):
        updatecount_val = 0

    today = date.today().isoformat()
    valid_until = str(data.get("validUntil") or data.get("validity") or "").strip()
    if not valid_until:
        valid_until = (date.today() + timedelta(days=30)).isoformat()
    doc_date = today
    post_date = today
    tax_date = today
    currency_code = _resolve_quotation_currency_code(data, customer_code)
    currency_rate = _as_decimal(data.get("currencyRate") or "1.00", "1.00")

    company_name = str(data.get("companyName") or "").strip()
    address1 = str(data.get("address1") or "").strip()
    address2 = str(data.get("address2") or "").strip()
    address3 = str(data.get("address3") or "").strip()
    address4 = str(data.get("address4") or "").strip()
    phone1 = str(data.get("phone1") or "").strip()
    mobile = str(data.get("mobile") or "").strip()
    agent = str(data.get("agent") or data.get("AGENT") or "").strip()
    area = str(data.get("area") or data.get("AREA") or "").strip()
    if not agent:
        agent = str((data.get("customerScalars") or {}).get("agent") or "").strip()
    if not area:
        area = str((data.get("customerScalars") or {}).get("area") or "").strip()
    country = str(data.get("country") or data.get("COUNTRY") or "").strip()
    tin = str(data.get("tin") or data.get("TIN") or "").strip()
    terms = str(data.get("terms") or data.get("creditTerm") or "30 Days").strip() or "30 Days"
    description = str(data.get("description") or "Quotation").strip() or "Quotation"
    shipper = str(data.get("shipper") or "----").strip() or "----"

    login_email = str(data.get("loginEmail") or data.get("login_email") or "").strip()
    matched_udf = str(
        data.get("loginMatchedUdfEmailColumn") or data.get("login_matched_udf_email_column") or ""
    ).strip()
    login_suffix = str(data.get("loginUdfEmailSuffix") or data.get("login_udf_email_suffix") or "").strip()
    login_dept = str(data.get("loginDepartment") or data.get("login_department") or "").strip()

    note_base = str(data.get("note") or "").strip()
    meta_bits = []
    if login_email:
        meta_bits.append(f"eQuotation login: {login_email}")
    if matched_udf:
        meta_bits.append(f"matched column: {matched_udf}")
    if login_suffix != "":
        meta_bits.append(f"udf suffix: {login_suffix}")
    if login_dept:
        meta_bits.append(f"department: {login_dept}")
    meta_line = " | ".join(meta_bits)
    if meta_line:
        note_full = f"{note_base}\n{meta_line}" if note_base else meta_line
    else:
        note_full = note_base
    if len(note_full) > 1900:
        note_full = note_full[:1899] + "…"

    cc_value = str(data.get("cc") or "").strip() or login_email

    attention_val = str(data.get("attention") or "").strip()
    if not attention_val and login_dept:
        attention_val = login_dept[:200]

    detail_rows = []
    total_doc_amt = Decimal("0.00")
    fallback_code = _quotation_fallback_item_code()
    line_uom_irbm_memo: dict[str, tuple[str, str]] = {}
    def_loc = _default_quotation_line_location()
    def_uom = _default_quotation_line_uom()
    def_proj = _default_quotation_line_project()
    def_irbm = _default_quotation_line_irbm()
    tenant_default_uom = ""
    for idx, item in enumerate(data.get("items") or [], start=1):
        qty = _as_decimal(item.get("qty") or 0)
        unit_price = _as_decimal(item.get("price") or 0)
        discount = _as_decimal(item.get("discount") or 0)
        gross = qty * unit_price
        line_amount = gross - discount
        if line_amount < Decimal("0.00"):
            line_amount = Decimal("0.00")
        total_doc_amt += line_amount

        delivery_date = str(item.get("deliveryDate") or "").strip() or doc_date
        product_desc = str(item.get("product") or "").strip()
        if not product_desc:
            continue

        item_code = str(
            item.get("itemCode") or item.get("itemcode") or item.get("code") or ""
        ).strip()
        source_line = str(item.get("source") or "").strip().lower()
        if source_line == "custom" and not item_code:
            item_code = _quotation_custom_item_code()
        if not item_code:
            item_code = _resolve_item_code_from_local_db(product_desc)
        if not item_code and fallback_code:
            item_code = fallback_code
        item_code = _normalize_item_code(item_code)

        try:
            dtlkey_val = int(item.get("dtlkey") or item.get("DTLKEY") or 0)
        except (TypeError, ValueError):
            dtlkey_val = 0

        is_custom_line = source_line == "custom" or item_code.upper() in _placeholder_item_codes()
        db_uom, db_irbm = _lookup_st_item_uom_irbm(item_code, line_uom_irbm_memo)
        # UOM precedence: explicit request UOM, then configured default (deliberate alignment to the
        # SQL API book), then local-DB UOM (only when DB_PATH matches the API book), then tenant default.
        # Custom/placeholder lines never use the local-DB UOM (the placeholder lives only in the local book).
        line_uom = str(item.get("uom") or item.get("UOM") or "").strip() or def_uom
        if not line_uom and not is_custom_line:
            line_uom = db_uom
        if not line_uom:
            if not tenant_default_uom:
                tenant_default_uom = _resolve_tenant_default_uom()
            line_uom = tenant_default_uom
        line_irbm = (
            str(item.get("irbmClassification") or item.get("irbm_classification") or "").strip()
            or db_irbm
            or def_irbm
        )
        line_location = str(item.get("location") or item.get("LOCATION") or "").strip() or def_loc
        line_project = str(item.get("project") or item.get("PROJECT") or "").strip() or def_proj
        disc_display = None if discount <= 0 else _fmt_money(discount)

        row = {
                "dtlkey": dtlkey_val,
                "dockey": header_dockey,
                # SQL Accounting expects detail SEQ in 1000-steps (1000, 2000, …). seq=1,2 leaves ITEMCODE unset in SL_QTDTL.
                "seq": idx * 1000,
                "styleid": "",
                "number": "",
                "itemcode": item_code,
                "location": line_location,
                "batch": "",
                "project": line_project,
                "description": product_desc,
                "description2": "",
                "description3": "",
                "permitno": "",
                "qty": _fmt_money(qty),
                "uom": line_uom,
                "rate": "1",
                "sqty": _fmt_money(qty),
                "suomqty": _fmt_money(qty),
                "unitprice": _fmt_money(unit_price),
                "deliverydate": delivery_date,
                "disc": disc_display,
                "tax": "",
                "tariff": "",
                "taxexemptionreason": "",
                "irbm_classification": line_irbm,
                "taxrate": "",
                "taxamt": "0",
                "localtaxamt": "0",
                "exempted_taxrate": "",
                "exempted_taxamt": "0",
                "taxinclusive": False,
                "amount": _fmt_money(line_amount),
                "localamount": _fmt_money(line_amount * currency_rate),
                "amountwithtax": _fmt_money(line_amount),
                "printable": True,
                "transferable": True,
                "remark1": "",
                "remark2": "",
                "companyitemcode": None,
                "initialpurchasecost": "0",
                "udf_status": str(item.get("udfStatus") or item.get("udf_status") or "").strip(),
                "udf_stdprice": _fmt_money(_as_decimal(item.get("udfStdprice") or item.get("udf_stdprice") or "0")),
                "udf_eprice": _fmt_money(_as_decimal(item.get("udfEprice") or item.get("udf_eprice") or "0")),
                "changed": True,
        }
        for api_key, item_keys in (
            ("udf_thickness", ("udfThickness", "udf_thickness")),
            ("udf_width", ("udfWidth", "udf_width")),
            ("udf_length", ("udfLength", "udf_length")),
        ):
            dim_val = ""
            for ik in item_keys:
                dim_val = str(item.get(ik) or "").strip()
                if dim_val:
                    break
            if dim_val:
                row[api_key] = dim_val
        detail_rows.append(row)

    # SQL Accounting /salesquotation usually requires a valid ST_ITEM.CODE per line; empty codes often yield HTTP 500 "Operation aborted".
    for i, row in enumerate(detail_rows, start=1):
        if not str(row.get("itemcode") or "").strip():
            hint = (
                "Add SQL_API_QUOTATION_FALLBACK_ITEM_CODE to .env with a real miscellaneous stock code from ST_ITEM "
                "(used for custom lines and when catalog item code cannot be resolved), or pick catalog products that load codes. "
                "If DB_PATH points at the same company file as the SQL API, leave SQL_API_QUOTATION_LOCAL_ITEMCODE_LOOKUP=true (default) "
                "so the server can resolve CODE from ST_ITEM by description."
            )
            raise ValueError(f"Quotation line {i} has no itemcode ({row.get('description')!r}). {hint}")

    header_payload = {
        "dockey": header_dockey,
        "docno": doc_no,
        "docnoex": "",
        "docdate": doc_date,
        "postdate": post_date,
        "taxdate": tax_date,
        "code": str(customer_code or "").strip(),
        "companyname": company_name,
        "address1": address1,
        "address2": address2,
        "address3": address3,
        "address4": address4,
        "postcode": "",
        "city": "",
        "state": "",
        "country": country,
        "phone1": phone1,
        "mobile": mobile,
        "fax1": "",
        "attention": attention_val or "",
        "area": area,
        "agent": agent,
        "project": "",
        "terms": terms,
        "currencycode": currency_code,
        "currencyrate": _fmt_money(currency_rate),
        "shipper": shipper,
        "description": description,
        "cancelled": False,
        "status": 0,
        "docamt": _fmt_money(total_doc_amt),
        "localdocamt": _fmt_money(total_doc_amt * currency_rate),
        "validity": valid_until,
        "deliveryterm": "",
        "cc": cc_value or "",
        "docref1": "",
        "docref2": "",
        "docref3": "",
        "docref4": "",
        "branchname": "",
        "daddress1": address1,
        "daddress2": address2,
        "daddress3": address3,
        "daddress4": address4,
        "dpostcode": "",
        "dcity": "",
        "dstate": "",
        "dcountry": "",
        "dattention": attention_val or "",
        "dphone1": phone1,
        "dmobile": "",
        "dfax1": "",
        "taxexemptno": "",
        "salestaxno": "",
        "servicetaxno": "",
        "tin": tin,
        "idtype": 0,
        "idno": "",
        "tourismno": "",
        "sic": "",
        "incoterms": "",
        "businessunit": "",
        "attachments": "",
        "submissiontype": 0,
        "note": note_full,
        "approvestate": "",
        "updatecount": updatecount_val,
        "transferable": True,
        "printcount": 0,
        "lastmodified": 0,
        "sdsdocdetail": detail_rows,
        "changed": True,
        "docnosetkey": 0,
        "nextdocno": "",
        "im_scan_autokey": 0,
        "udf_status": str(data.get("udfStatus") or data.get("udf_status") or "PENDING").strip() or "PENDING",
    }
    _merge_customer_scalars_into_salesquotation_header(header_payload, data)
    header_payload["currencycode"] = _resolve_quotation_currency_code(data, customer_code)
    # Explicit create-quotation fields win over merge (agent / area must match Maintain Customer).
    for field, keys in (
        ("agent", ("agent", "AGENT")),
        ("area", ("area", "AREA")),
        ("companyname", ("companyName", "companyname")),
        ("address1", ("address1",)),
        ("address2", ("address2",)),
        ("address3", ("address3",)),
        ("address4", ("address4",)),
        ("phone1", ("phone1",)),
        ("mobile", ("mobile",)),
        ("attention", ("attention",)),
        ("terms", ("terms", "creditTerm", "creditterm")),
        ("tin", ("tin", "TIN")),
        ("country", ("country", "COUNTRY")),
    ):
        for k in keys:
            v = str(data.get(k) or "").strip()
            if v and v not in ("N/A", "—", "----"):
                header_payload[field] = v
                break
    return header_payload


def _merge_customer_scalars_into_salesquotation_header(payload: dict, data: dict) -> None:
    """Apply SQL API customerScalars from create-quotation (fills empty header fields)."""
    scalars = data.get("customerScalars")
    if not isinstance(scalars, dict):
        return
    alias = {"creditterm": "terms", "companyname": "companyname"}
    skip = frozenset(
        {
            "dockey",
            "docno",
            "docdate",
            "postdate",
            "taxdate",
            "docamt",
            "localdocamt",
            "status",
            "cancelled",
            "updatecount",
            "lastmodified",
            "changed",
            "sdsdocdetail",
        }
    )
    branch_to_header = {
        "postcode": "postcode",
        "city": "city",
        "state": "state",
        "country": "country",
        "fax1": "fax1",
        "fax2": "fax2",
        "branchname": "branchname",
        "email": "cc",
    }
    for raw_key, raw_val in scalars.items():
        key = str(raw_key or "").strip().lower()
        if not key or key in skip or key == "currencycode":
            continue
        if key.startswith("branch."):
            bk = key.split(".", 1)[-1]
            target = branch_to_header.get(bk, bk)
            if target in payload and not str(payload.get(target) or "").strip():
                val = str(raw_val or "").strip()
                if val and val not in ("—", "----", "N/A"):
                    payload[target] = val
            continue
        val = str(raw_val or "").strip()
        if not val or val in ("—", "----", "N/A", "null", "None"):
            continue
        target = alias.get(key, key)
        if target not in payload:
            continue
        existing = payload.get(target)
        if existing is not None and str(existing).strip() not in ("", "0", "0.00", "----"):
            continue
        if target in ("idtype", "submissiontype"):
            try:
                payload[target] = int(float(val))
            except (TypeError, ValueError):
                continue
        else:
            payload[target] = val


def create_or_update_quotation(base_api_url, customer_code, data):
    """Create or update a quotation via SQL Accounting API /salesquotation.

    When ``dockey`` / ``docKey`` is set, DOCNO and UPDATECOUNT are read from ``SL_QT``
    so the upstream document is updated in place.

    Returns a dict compatible with Flask caller expectations.
    """
    if not customer_code:
        return {"success": False, "error": "Customer code not found in session"}

    data = _strip_client_currency_fields(dict(data or {}))
    upd_dockey = int(data.get("dockey") or data.get("docKey") or 0)
    if upd_dockey:
        hb = _read_sl_qt_header_for_sales_api(upd_dockey)
        db_docno = str(hb.get("docno") or "").strip()
        if not db_docno:
            return {
                "success": False,
                "error": f"Quotation DOCKEY {upd_dockey} not found in SL_QT (or DOCNO missing).",
            }
        db_code = str(hb.get("code") or "").strip()
        sess_code = str(customer_code or "").strip()
        skip_code_check = bool(
            data.get("adminUpdate")
            or data.get("skipCustomerCodeCheck")
        )
        if (
            not skip_code_check
            and db_code
            and sess_code
            and db_code != sess_code
        ):
            return {
                "success": False,
                "error": "Quotation does not belong to the signed-in customer (CODE mismatch).",
            }
        data["docno"] = db_docno
        if (
            data.get("updatecount") is None
            and data.get("updateCount") is None
            and hb.get("updatecount") is not None
        ):
            data["updatecount"] = hb["updatecount"]

    items = data.get("items") or []
    if not items:
        return {"success": False, "error": "At least one item is required"}

    settings = load_sql_accounting_api_settings()
    quote_path = (os.getenv("SQL_API_SALES_QUOTATION_PATH") or settings.quotation_create_path or "").strip()
    if not quote_path:
        return {"success": False, "error": "SQL_API_SALES_QUOTATION_PATH is not configured in .env"}
    if not settings.access_key or not settings.secret_key:
        return {"success": False, "error": "SQL API keys are not configured"}

    provided_docno = str(data.get("docno") or data.get("docNo") or "").strip()
    is_update = upd_dockey > 0 and bool(provided_docno)

    client = SqlAccountingApiClient(settings)
    # Quotation create is heavier than simple GETs; allow a separate read timeout (defaults to global).
    quote_read_timeout = _float_env(
        "SQL_API_QUOTATION_TIMEOUT_SECONDS",
        float(settings.timeout_seconds),
    )
    last_error = ""
    local_precheck_done = False
    max_attempts = 1 if is_update else 20
    for attempt in range(max_attempts):
        if provided_docno:
            doc_no = provided_docno
        else:
            max_seq, existing, _db_scan_err = _read_qt_sequences_from_db(limit=2000)
            if max_seq == 0 and not existing and attempt == 0:
                doc_no = _fallback_qt_docno()
            else:
                doc_no = _next_qt_docno_candidate(max_seq, existing, attempt)

        if not doc_no:
            min_seq, max_seq_allowed = _app_docno_range()
            return {
                "success": False,
                "error": (
                    f"No available quotation number in reserved range QT-{min_seq:05d}..QT-{max_seq_allowed:05d}."
                ),
            }

        try:
            payload = _build_salesquotation_payload(customer_code, data, doc_no=doc_no)
        except ValueError as ve:
            return {"success": False, "error": str(ve)}

        if not payload.get("sdsdocdetail"):
            return {"success": False, "error": "No valid quotation item rows to submit"}

        if (os.getenv("SQL_API_QUOTATION_LOG_UPSTREAM") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            print(
                f"[quotation_api] salesquotation header currencycode={payload.get('currencycode')!r} "
                f"customer_code={customer_code!r} docno={doc_no!r}",
                flush=True,
            )

        if not local_precheck_done:
            pre_err = _local_precheck_quotation(customer_code, payload)
            local_precheck_done = True
            if pre_err:
                return {
                    "success": False,
                    "error": pre_err,
                    "detail": "Local Firebird pre-check failed; SQL Accounting API was not called.",
                }

        try:
            if is_update:
                update_url = settings.resolved_quotation_update_url(upd_dockey)
                status, parsed, raw = client.put_json(
                    update_url,
                    payload,
                    timeout_seconds=quote_read_timeout,
                )
            else:
                status, parsed, raw = client.post_json(
                    settings.resolved_quotation_create_url(),
                    payload,
                    timeout_seconds=quote_read_timeout,
                )
        except SqlAccountingApiError as exc:
            err_text = str(exc)
            low = err_text.lower()
            if "timed out" in low or "timeout" in low or "read time" in low:
                return {
                    "success": False,
                    "errorCode": "SQL_API_TIMEOUT",
                    "error": (
                        "SQL Accounting API did not respond in time. Wait a minute, then check "
                        "whether the quotation already exists in SQL Accounting before submitting again."
                    ),
                    "detail": err_text,
                }
            return {"success": False, "errorCode": "SQL_API_ERROR", "error": err_text}

        if status < 400:
            response_dict = parsed if isinstance(parsed, dict) else {}
            data_obj = response_dict.get("data") if isinstance(response_dict.get("data"), dict) else {}
            return {
                "success": True,
                "dockey": response_dict.get("dockey") or data_obj.get("dockey") or data_obj.get("docKey") or 0,
                "docno": response_dict.get("docno") or data_obj.get("docno") or data_obj.get("docNo") or doc_no,
                "message": response_dict.get("message") or "Quotation created successfully",
                "upstream": response_dict or {"raw": raw},
            }

        if status >= 400 and (os.getenv("SQL_API_QUOTATION_LOG_UPSTREAM") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            snippet = (raw or "")[:800].replace("\n", " ")
            verb = "PUT" if is_update else "POST"
            print(
                f"[quotation_api] salesquotation {verb} HTTP {status} dockey={upd_dockey} docno={doc_no!r} upstream: {snippet}",
                flush=True,
            )

        detail = raw
        if isinstance(parsed, dict):
            detail = str(parsed.get("message") or parsed.get("error") or parsed)
            err_obj = parsed.get("error")
            if isinstance(err_obj, dict) and err_obj.get("message"):
                detail = str(err_obj.get("message"))
        if status == 401:
            return {
                "success": False,
                "errorCode": "SQL_API_UNAUTHORIZED",
                "error": (
                    "SQL Accounting API returned HTTP 401 (Unauthorized). "
                    "The cloud API keys do not match this tenant/book, or SigV4 service name is wrong "
                    "(api.sql.my requires SQL_API_SERVICE=sqlaccount, not execute-api). "
                    "Check SQL_API_ACCESS_KEY and SQL_API_SECRET_KEY from tenant sqlApi / Secrets Manager "
                    "(same keys as SQL Account portal Test Connection). Re-login does not fix this; "
                    "restart the server after updating credentials."
                ),
                "detail": detail,
            }

        last_error = f"SQL Accounting API returned HTTP {status}: {detail}"
        line_uoms = [
            (str(d.get("itemcode") or ""), str(d.get("uom") or ""))
            for d in (payload.get("sdsdocdetail") or [])
            if isinstance(d, dict)
        ]
        if line_uoms:
            print(f"[quotation_api] salesquotation line itemcode->uom: {line_uoms}", flush=True)
        if "operation aborted" in last_error.lower():
            last_error += (
                " — Common causes: invalid or blank ST_ITEM.CODE on a line, missing line UOM/location/IRBM, "
                "or customer CODE not on the company DB used by the API. "
                "Ensure DB_PATH matches the API book so UOM/IRBM are read from ST_ITEM; set "
                "SQL_API_QUOTATION_DEFAULT_UOM, SQL_API_QUOTATION_DEFAULT_LOCATION, SQL_API_QUOTATION_DEFAULT_IRBM "
                "if needed; set SQL_API_QUOTATION_FALLBACK_ITEM_CODE for custom lines. "
                "Check SQL Accounting / Firebird logs for the underlying exception."
            )

        if provided_docno or not _is_unique_docno_error(status, parsed, raw):
            return {"success": False, "error": last_error}

    return {"success": False, "error": last_error or "Failed to create quotation"}


def save_draft_quotation(base_api_url, customer_code, data):
    """Save a quotation draft directly to Firebird DB (no PHP)."""
    from utils import get_db_connection
    import traceback
    data = _strip_client_currency_fields(dict(data or {}))
    dockey = data.get('dockey')
    description = (data.get('description', '') or '').strip() or 'Draft Quotation'
    valid_until = data.get('validUntil', '')
    currency_code = _resolve_quotation_currency_code(data, customer_code)
    docno_input = str(data.get('docno') or data.get('docNo') or '').strip()
    shipper = str(data.get('shipper') or '----').strip() or '----'
    company_name = data.get('companyName', '')
    address1 = data.get('address1', '')
    address2 = data.get('address2', '')
    phone1 = data.get('phone1', '')
    items = data.get('items', [])
    docdate = datetime.now().date()
    terms = str(data.get('terms') or data.get('creditTerm') or '30 Days').strip() or '30 Days'
    total_doc_amt = sum(float(item.get('qty', 0)) * float(item.get('price', 0)) for item in items)

    try:
        con = get_db_connection()
        cur = con.cursor()
        # Insert or update draft header
        if dockey:
            # Update existing draft
            cur.execute("""
                UPDATE SL_QTDRAFT SET DESCRIPTION=?, VALIDITY=?, TERMS=?, DOCAMT=?, COMPANYNAME=?, ADDRESS1=?, ADDRESS2=?, PHONE1=?, CURRENCYCODE=?, DOCDATE=?
                WHERE DOCKEY=? AND CODE=?
            """, (description, valid_until, terms, total_doc_amt, company_name, address1, address2, phone1, currency_code, docdate, dockey, customer_code))
        else:
            # Get next DOCKEY from generator/sequence (fallback to MAX+1 if generator is unavailable)
            try:
                cur.execute("SELECT GEN_ID(GEN_SL_QTDRAFT_ID, 1) FROM RDB$DATABASE")
                dockey = cur.fetchone()[0]
            except Exception:
                cur.execute("SELECT COALESCE(MAX(DOCKEY), 0) + 1 FROM SL_QTDRAFT")
                dockey = cur.fetchone()[0]

            docno = docno_input or f"DRAFT-{int(dockey):05d}"
            cur.execute("""
                INSERT INTO SL_QTDRAFT (DOCKEY, DOCNO, CODE, DESCRIPTION, VALIDITY, TERMS, DOCAMT, SHIPPER, COMPANYNAME, ADDRESS1, ADDRESS2, PHONE1, CURRENCYCODE, DOCDATE)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (dockey, docno, customer_code, description, valid_until, terms, total_doc_amt, shipper, company_name, address1, address2, phone1, currency_code, docdate))

        # Remove old draft items
        cur.execute("DELETE FROM SL_QTDTLDRAFT WHERE DOCKEY=?", (dockey,))
        # Insert draft items (ITEMCODE must match SL_QTDTLDRAFT schema — used when reloading drafts / SQL API)
        for idx, item in enumerate(items, start=1):
            qty = float(item.get('qty', 0))
            price = float(item.get('price', 0))
            discount = float(item.get('discount', 0))
            product_desc = str(item.get('product', '')).strip()
            if not product_desc:
                continue
            item_code = str(
                item.get('itemCode') or item.get('itemcode') or item.get('code') or ''
            ).strip()
            source_line = str(item.get('source') or '').strip().lower()
            if source_line == 'custom' and not item_code:
                # Match the submit flow: custom lines carry the CUSTOM placeholder so the draft
                # reloads deterministically as a custom line (rather than relying on description).
                item_code = _quotation_custom_item_code()
            if not item_code and source_line != 'custom':
                item_code = _resolve_item_code_from_local_db(product_desc)
            if not item_code:
                item_code = _quotation_fallback_item_code()
            item_code = _normalize_item_code(item_code)
            try:
                cur.execute("SELECT GEN_ID(GEN_SL_QTDTLDRAFT_ID, 1) FROM RDB$DATABASE")
                dtlkey = cur.fetchone()[0]
            except Exception:
                cur.execute("SELECT COALESCE(MAX(DTLKEY), 0) + 1 FROM SL_QTDTLDRAFT")
                dtlkey = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO SL_QTDTLDRAFT (DTLKEY, DOCKEY, SEQ, ITEMCODE, DESCRIPTION, QTY, UNITPRICE, DISC)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (dtlkey, dockey, idx, item_code or None, product_desc, qty, price, str(discount)),
            )

        con.commit()
        cur.close()
        con.close()
        return {"success": True, "dockey": dockey, "docno": None, "message": "Draft saved"}
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}
