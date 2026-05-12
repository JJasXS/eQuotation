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


def _normalize_item_code(value: str) -> str:
    """Collapse whitespace; ST_ITEM.CODE may contain spaces (e.g. ``SEMI BOM``)."""
    s = (value or "").strip()
    return re.sub(r"\s+", " ", s) if s else ""


def _default_quotation_line_location() -> str:
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_LOCATION") or "----").strip() or "----"


def _default_quotation_line_uom() -> str:
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_UOM") or "UNIT").strip() or "UNIT"


def _default_quotation_line_project() -> str:
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_PROJECT") or "----").strip() or "----"


def _default_quotation_line_irbm() -> str:
    """Optional IRBM classification for all lines when ST_ITEM has none (Malaysia e-invoicing)."""
    return (os.getenv("SQL_API_QUOTATION_DEFAULT_IRBM") or "").strip()


def _lookup_st_item_uom_irbm(item_code: str, memo: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """Read ST_ITEM.UOM and IRBM_CLASSIFICATION from local DB when DB_PATH is set."""
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
            try:
                cur.execute(
                    "SELECT TRIM(COALESCE(UOM, '')) FROM ST_ITEM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
                    (item_code.strip(),),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    uom = str(row[0]).strip()
            except Exception:
                pass
            if not uom:
                try:
                    cur.execute(
                        "SELECT FIRST 1 TRIM(UOM) FROM ST_ITEM_UOM WHERE TRIM(UPPER(CODE)) = TRIM(UPPER(?))",
                        (item_code.strip(),),
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        uom = str(row[0]).strip()
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
                    "Create these stock items in SQL Accounting or set SQL_API_QUOTATION_FALLBACK_ITEM_CODE to an existing code."
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


def _read_qt_sequences_from_db(limit: int = 2000) -> tuple[int, set[int]]:
    """Return (max_seq, existing_seq_set) for DOCNO values matching QT-%.5d."""
    db_path = (os.getenv("DB_PATH") or "").strip()
    db_host = (os.getenv("DB_HOST") or "").strip()
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_password = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    if not db_path:
        return 0, set()

    try:
        import fdb

        dsn = db_path if not db_host else f"{db_host}:{db_path}"
        con = fdb.connect(dsn=dsn, user=db_user, password=db_password, charset="UTF8")
        cur = con.cursor()
        cur.execute(f"SELECT FIRST {int(limit)} DOCNO FROM SL_QT ORDER BY DOCKEY DESC")
        rows = cur.fetchall() or []
        cur.close()
        con.close()

        max_seq = 0
        existing = set()
        for row in rows:
            raw = str(row[0] or "").strip()
            m = _QT_DOCNO_RE.match(raw)
            if not m:
                continue
            seq = int(m.group(1))
            existing.add(seq)
            if seq > max_seq:
                max_seq = seq
        return max_seq, existing
    except Exception:
        return 0, set()


def _fallback_qt_docno() -> str:
    # Last-resort formatter that still follows QT-%.5d.
    return _format_qt_docno(int(datetime.now().strftime("%H%M%S")) % 100000 or 1)


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
    currency_code = str(data.get("currencyCode") or "MYR").strip() or "MYR"
    currency_rate = _as_decimal(data.get("currencyRate") or "1.00", "1.00")

    company_name = str(data.get("companyName") or "").strip()
    address1 = str(data.get("address1") or "").strip()
    address2 = str(data.get("address2") or "").strip()
    address3 = str(data.get("address3") or "").strip()
    address4 = str(data.get("address4") or "").strip()
    phone1 = str(data.get("phone1") or "").strip()
    terms = str(data.get("terms") or data.get("creditTerm") or "30 Days").strip() or "30 Days"
    description = str(data.get("description") or "Quotation").strip() or "Quotation"
    shipper = str(data.get("shipper") or "----").strip() or "----"

    detail_rows = []
    total_doc_amt = Decimal("0.00")
    fallback_code = _quotation_fallback_item_code()
    line_uom_irbm_memo: dict[str, tuple[str, str]] = {}
    def_loc = _default_quotation_line_location()
    def_uom = _default_quotation_line_uom()
    def_proj = _default_quotation_line_project()
    def_irbm = _default_quotation_line_irbm()
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
        if not item_code:
            item_code = _resolve_item_code_from_local_db(product_desc)
        if not item_code and fallback_code:
            item_code = fallback_code
        item_code = _normalize_item_code(item_code)

        db_uom, db_irbm = _lookup_st_item_uom_irbm(item_code, line_uom_irbm_memo)
        line_uom = str(item.get("uom") or item.get("UOM") or "").strip() or db_uom or def_uom
        line_irbm = (
            str(item.get("irbmClassification") or item.get("irbm_classification") or "").strip()
            or db_irbm
            or def_irbm
        )
        line_location = str(item.get("location") or item.get("LOCATION") or "").strip() or def_loc
        line_project = str(item.get("project") or item.get("PROJECT") or "").strip() or def_proj
        disc_display = None if discount <= 0 else _fmt_money(discount)

        row = {
                "dtlkey": 0,
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

    return {
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
        "country": "",
        "phone1": phone1,
        "mobile": "",
        "fax1": "",
        "attention": "",
        "area": "",
        "agent": "",
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
        "cc": "",
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
        "dattention": "",
        "dphone1": phone1,
        "dmobile": "",
        "dfax1": "",
        "taxexemptno": "",
        "salestaxno": "",
        "servicetaxno": "",
        "tin": "",
        "idtype": 0,
        "idno": "",
        "tourismno": "",
        "sic": "",
        "incoterms": "",
        "businessunit": "",
        "attachments": "",
        "submissiontype": 0,
        "note": "",
        "approvestate": "",
        "updatecount": updatecount_val,
        "transferable": False,
        "printcount": 0,
        "lastmodified": 0,
        "sdsdocdetail": detail_rows,
        "changed": True,
        "docnosetkey": 0,
        "nextdocno": "",
        "im_scan_autokey": 0,
        "udf_status": str(data.get("udfStatus") or data.get("udf_status") or "PENDING").strip() or "PENDING",
    }


def create_or_update_quotation(base_api_url, customer_code, data):
    """Create or update a quotation via SQL Accounting API /salesquotation.

    When ``dockey`` / ``docKey`` is set, DOCNO and UPDATECOUNT are read from ``SL_QT``
    so the upstream document is updated in place.

    Returns a dict compatible with Flask caller expectations.
    """
    if not customer_code:
        return {"success": False, "error": "Customer code not found in session"}

    data = dict(data or {})
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
        if db_code and sess_code and db_code != sess_code:
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

    client = SqlAccountingApiClient(settings)
    # Quotation create is heavier than simple GETs; allow a separate read timeout (defaults to global).
    quote_read_timeout = _float_env(
        "SQL_API_QUOTATION_TIMEOUT_SECONDS",
        float(settings.timeout_seconds),
    )
    last_error = ""
    local_precheck_done = False
    for attempt in range(20):
        if provided_docno:
            doc_no = provided_docno
        else:
            max_seq, existing = _read_qt_sequences_from_db(limit=2000)
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
            print(f"[quotation_api] salesquotation HTTP {status} docno={doc_no!r} upstream: {snippet}", flush=True)

        detail = raw
        if isinstance(parsed, dict):
            detail = str(parsed.get("message") or parsed.get("error") or parsed)
            err_obj = parsed.get("error")
            if isinstance(err_obj, dict) and err_obj.get("message"):
                detail = str(err_obj.get("message"))
        last_error = f"SQL Accounting API returned HTTP {status}: {detail}"
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
    dockey = data.get('dockey')
    description = (data.get('description', '') or '').strip() or 'Draft Quotation'
    valid_until = data.get('validUntil', '')
    currency_code = data.get('currencyCode', 'MYR')
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
            if not item_code:
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
