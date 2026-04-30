"""Procurement bidding service: supplier bid submission + admin approval workflow."""
from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from utils.db_utils import get_db_connection
from utils.procurement_purchase_request import _as_decimal, _clean_text, _get_table_columns, _money, _pick_existing


class BiddingValidationError(ValueError):
    """Raised when bidding workflow validation fails."""


def _connect_db():
    return get_db_connection()


def _utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _table_exists(cur: Any, table_name: str) -> bool:   
    cur.execute(
        "SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?",
        (table_name.upper(),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _generator_exists(cur: Any, generator_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM RDB$GENERATORS WHERE RDB$GENERATOR_NAME = ?",
        (generator_name.upper(),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _index_exists(cur: Any, index_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM RDB$INDICES WHERE RDB$INDEX_NAME = ?",
        (index_name.upper(),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _pr_bid_hdr_columns(cur: Any) -> set[str]:
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = 'PR_BID_HDR'
        """,
    )
    return {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}


def _ensure_pr_bid_hdr_udf_reason(con: Any) -> None:
    """Add PR_BID_HDR.UDF_REASON when missing (admin accept/reject explanation)."""
    cur = con.cursor()
    try:
        cols = _pr_bid_hdr_columns(cur)
        if "UDF_REASON" in cols:
            return
        cur.execute("ALTER TABLE PR_BID_HDR ADD UDF_REASON VARCHAR(500)")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()


def _next_key(cur: Any, table_name: str, key_column: str, generator_name: str) -> int:
    if _generator_exists(cur, generator_name):
        cur.execute(f"SELECT GEN_ID({generator_name}, 1) FROM RDB$DATABASE")
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    cur.execute(f"SELECT COALESCE(MAX({key_column}), 0) + 1 FROM {table_name}")
    row = cur.fetchone()
    return int(row[0] if row and row[0] is not None else 1)


def ensure_bidding_schema() -> None:
    """Create bidding tables/generators if they do not exist."""
    con = _connect_db()
    try:
        cur = con.cursor()

        if not _table_exists(cur, "PR_BID_INVITE"):
            cur.execute(
                """
                CREATE TABLE PR_BID_INVITE (
                    INVITE_ID INTEGER NOT NULL,
                    REQUEST_DOCKEY INTEGER NOT NULL,
                    REQUEST_NO VARCHAR(60),
                    SUPPLIER_CODE VARCHAR(30) NOT NULL,
                    SUPPLIER_NAME VARCHAR(160),
                    STATUS VARCHAR(20),
                    CREATED_BY VARCHAR(120),
                    CREATED_AT TIMESTAMP,
                    UPDATED_AT TIMESTAMP,
                    PRIMARY KEY (INVITE_ID)
                )
                """
            )
        if not _generator_exists(cur, "GEN_PR_BID_INVITE_ID"):
            cur.execute("CREATE GENERATOR GEN_PR_BID_INVITE_ID")

        if not _table_exists(cur, "PR_BID_HDR"):
            cur.execute(
                """
                CREATE TABLE PR_BID_HDR (
                    BID_ID INTEGER NOT NULL,
                    REQUEST_DOCKEY INTEGER NOT NULL,
                    REQUEST_NO VARCHAR(60),
                    SUPPLIER_CODE VARCHAR(30) NOT NULL,
                    SUPPLIER_NAME VARCHAR(160),
                    STATUS VARCHAR(20),
                    REMARKS VARCHAR(500),
                    UDF_REASON VARCHAR(500),
                    CREATED_BY VARCHAR(120),
                    CREATED_AT TIMESTAMP,
                    APPROVED_BY VARCHAR(120),
                    APPROVED_AT TIMESTAMP,
                    PRIMARY KEY (BID_ID)
                )
                """
            )
        if not _generator_exists(cur, "GEN_PR_BID_HDR_ID"):
            cur.execute("CREATE GENERATOR GEN_PR_BID_HDR_ID")

        if not _table_exists(cur, "PR_BID_DTL"):
            cur.execute(
                """
                CREATE TABLE PR_BID_DTL (
                    BID_DTL_ID INTEGER NOT NULL,
                    BID_ID INTEGER NOT NULL,
                    SOURCE_DTLKEY INTEGER NOT NULL,
                    ITEMCODE VARCHAR(60),
                    DESCRIPTION VARCHAR(255),
                    BID_QTY NUMERIC(18, 2),
                    BID_UNITPRICE NUMERIC(18, 2),
                    BID_TAXAMT NUMERIC(18, 2),
                    BID_AMOUNT NUMERIC(18, 2),
                    LEAD_DAYS INTEGER,
                    REMARKS VARCHAR(255),
                    PRIMARY KEY (BID_DTL_ID)
                )
                """
            )
        if not _generator_exists(cur, "GEN_PR_BID_DTL_ID"):
            cur.execute("CREATE GENERATOR GEN_PR_BID_DTL_ID")

        if not _table_exists(cur, "PR_BID_LINE_AWARD"):
            cur.execute(
                """
                CREATE TABLE PR_BID_LINE_AWARD (
                    AWARD_ID INTEGER NOT NULL,
                    REQUEST_DOCKEY INTEGER NOT NULL,
                    DETAIL_ID INTEGER NOT NULL,
                    BID_ID INTEGER NOT NULL,
                    SUPPLIER_CODE VARCHAR(30),
                    SUPPLIER_NAME VARCHAR(160),
                    UDF_REASON VARCHAR(500),
                    APPROVED_BY VARCHAR(120),
                    APPROVED_AT TIMESTAMP,
                    PRIMARY KEY (AWARD_ID)
                )
                """
            )
        if not _generator_exists(cur, "GEN_PR_BID_LINE_AWARD_ID"):
            cur.execute("CREATE GENERATOR GEN_PR_BID_LINE_AWARD_ID")

        if not _index_exists(cur, "IX_PR_BID_INVITE_REQ_SUP"):
            cur.execute("CREATE INDEX IX_PR_BID_INVITE_REQ_SUP ON PR_BID_INVITE (REQUEST_DOCKEY, SUPPLIER_CODE)")
        if not _index_exists(cur, "IX_PR_BID_HDR_REQ"):
            cur.execute("CREATE INDEX IX_PR_BID_HDR_REQ ON PR_BID_HDR (REQUEST_DOCKEY)")
        if not _index_exists(cur, "IX_PR_BID_DTL_BID"):
            cur.execute("CREATE INDEX IX_PR_BID_DTL_BID ON PR_BID_DTL (BID_ID)")
        if not _index_exists(cur, "IX_PR_BID_AWARD_REQ_DTL"):
            cur.execute("CREATE UNIQUE INDEX IX_PR_BID_AWARD_REQ_DTL ON PR_BID_LINE_AWARD (REQUEST_DOCKEY, DETAIL_ID)")
        if not _index_exists(cur, "IX_PR_BID_AWARD_REQ"):
            cur.execute("CREATE INDEX IX_PR_BID_AWARD_REQ ON PR_BID_LINE_AWARD (REQUEST_DOCKEY)")

        if _table_exists(cur, "PR_BID_HDR"):
            cols = _pr_bid_hdr_columns(cur)
            if "UDF_REASON" not in cols:
                cur.execute("ALTER TABLE PR_BID_HDR ADD UDF_REASON VARCHAR(500)")

        con.commit()
    finally:
        con.close()


def _normalize_supplier_rows(suppliers: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in suppliers:
        if not isinstance(row, dict):
            continue
        code = _clean_text(row.get("code") or row.get("supplierCode") or row.get("supplierId"))
        name = _clean_text(row.get("companyname") or row.get("companyName") or row.get("name"))
        if not code:
            continue
        if code in seen:
            continue
        seen.add(code)
        normalized.append({"code": code, "name": name})
    if not normalized:
        raise BiddingValidationError("at least one supplier with a valid code is required")
    return normalized


def create_bid_invitations(  # noqa: too-many-locals
    request_dockey: int,
    request_no: str,
    suppliers: list[dict[str, Any]],
    created_by: str,
) -> dict[str, Any]:
    normalized = _normalize_supplier_rows(suppliers)
    now = _utc_now()

    con = _connect_db()
    inserted = 0
    updated = 0
    try:
        cur = con.cursor()
        for supplier in normalized:
            cur.execute(
                """
                SELECT FIRST 1 INVITE_ID
                FROM PR_BID_INVITE
                WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE = ?
                """,
                (request_dockey, supplier["code"]),
            )
            hit = cur.fetchone()
            if hit:
                cur.execute(
                    """
                    UPDATE PR_BID_INVITE
                    SET SUPPLIER_NAME = ?, STATUS = ?, UPDATED_AT = ?
                    WHERE INVITE_ID = ?
                    """,
                    (supplier["name"], "OPEN", now, int(hit[0])),
                )
                updated += 1
                continue

            invite_id = _next_key(cur, "PR_BID_INVITE", "INVITE_ID", "GEN_PR_BID_INVITE_ID")
            cur.execute(
                """
                INSERT INTO PR_BID_INVITE (
                    INVITE_ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME,
                    STATUS, CREATED_BY, CREATED_AT, UPDATED_AT
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invite_id,
                    request_dockey,
                    request_no,
                    supplier["code"],
                    supplier["name"],
                    "OPEN",
                    _clean_text(created_by) or "admin",
                    now,
                    now,
                ),
            )
            inserted += 1

        con.commit()
        return {
            "requestDockey": request_dockey,
            "requestNumber": request_no,
            "invitedCount": len(normalized),
            "inserted": inserted,
            "updated": updated,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _fetch_pr_delivery_dates_by_dockey(dockeys: list[int]) -> dict[int, str | None]:
    uniq = sorted({int(d) for d in dockeys if d})
    if not uniq:
        return {}

    con = _connect_db()
    try:
        cur = con.cursor()
        if not _table_exists(cur, "PH_PQ"):
            return {}
        cols = _get_table_columns(cur, "PH_PQ")
        key_col = _pick_existing(cols, "DOCKEY", "PQKEY", "ID")
        date_col = _pick_existing(cols, "REQUIREDDATE", "DELIVERYDATE", "POSTDATE", "DOCDATE")
        if not key_col or not date_col:
            return {}
        placeholders = ", ".join(["?"] * len(uniq))
        cur.execute(
            f"SELECT {key_col}, {date_col} FROM PH_PQ WHERE {key_col} IN ({placeholders})",
            uniq,
        )
        out: dict[int, str | None] = {}
        for row in cur.fetchall() or []:
            if not row:
                continue
            try:
                key = int(row[0])
            except Exception:
                continue
            val = row[1]
            if val is None:
                out[key] = None
            elif hasattr(val, "isoformat"):
                out[key] = val.isoformat()
            else:
                out[key] = str(val).strip() or None
        return out
    finally:
        con.close()


def list_supplier_invitations(supplier_code: str) -> list[dict[str, Any]]:
    code = _clean_text(supplier_code)
    if not code:
        raise BiddingValidationError("supplier code is required")

    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT
                i.INVITE_ID,
                i.REQUEST_DOCKEY,
                i.REQUEST_NO,
                i.SUPPLIER_CODE,
                i.SUPPLIER_NAME,
                i.STATUS,
                i.CREATED_AT,
                h.BID_ID,
                h.STATUS
            FROM PR_BID_INVITE i
            LEFT JOIN PR_BID_HDR h
              ON h.REQUEST_DOCKEY = i.REQUEST_DOCKEY
             AND h.SUPPLIER_CODE = i.SUPPLIER_CODE
            WHERE i.SUPPLIER_CODE = ?
            ORDER BY i.UPDATED_AT DESC, i.INVITE_ID DESC
            """,
            (code,),
        )
        rows = cur.fetchall() or []
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "inviteId": int(row[0]),
                    "requestDockey": int(row[1]),
                    "requestNumber": _clean_text(row[2]),
                    "supplierCode": _clean_text(row[3]),
                    "supplierName": _clean_text(row[4]),
                    "inviteStatus": _clean_text(row[5]) or "OPEN",
                    "inviteAt": row[6].isoformat() if row[6] else None,
                    "bidId": int(row[7]) if row[7] is not None else None,
                    "bidStatus": _clean_text(row[8]),
                }
            )
        delivery_map = _fetch_pr_delivery_dates_by_dockey([int(r["requestDockey"]) for r in result])
        for r in result:
            dk = int(r.get("requestDockey") or 0)
            r["requestDeliveryDate"] = delivery_map.get(dk)
        return result
    finally:
        con.close()


def _normalize_bid_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        raw_dtl = row.get("detailId")
        if raw_dtl is None:
            raw_dtl = row.get("dtlkey")
        if raw_dtl is None:
            raw_dtl = row.get("fromdtlkey")

        try:
            source_dtl = int(raw_dtl)
        except Exception as exc:
            raise BiddingValidationError("each bid line requires a valid detailId") from exc

        bid_qty = _money(_as_decimal(row.get("quantity", row.get("qty", "0")), "0"))
        bid_price = _money(_as_decimal(row.get("unitPrice", row.get("unitprice", "0")), "0"))
        bid_tax = _money(_as_decimal(row.get("tax", row.get("taxamt", "0")), "0"))
        if bid_qty <= 0:
            raise BiddingValidationError(f"bid quantity must be > 0 for detail {source_dtl}")
        if bid_price < 0:
            raise BiddingValidationError(f"bid unitPrice must be >= 0 for detail {source_dtl}")

        normalized.append(
            {
                "sourceDtlKey": source_dtl,
                "itemCode": _clean_text(row.get("itemCode") or row.get("itemcode")),
                "description": _clean_text(row.get("description") or row.get("description2") or row.get("itemName")),
                "quantity": bid_qty,
                "unitPrice": bid_price,
                "taxAmt": bid_tax,
                "amount": _money((bid_qty * bid_price) + bid_tax),
                "leadDays": int(_as_decimal(row.get("leadDays"), "0")),
                "remarks": _clean_text(row.get("remarks")),
            }
        )

    if not normalized:
        raise BiddingValidationError("bidLines[] is required")
    return normalized


def submit_supplier_bid(
    request_dockey: int,
    request_no: str,
    supplier_code: str,
    supplier_name: str,
    bid_lines: list[dict[str, Any]],
    remarks: str,
    created_by: str,
) -> dict[str, Any]:
    code = _clean_text(supplier_code)
    if not code:
        raise BiddingValidationError("supplierCode is required")

    lines = _normalize_bid_lines(bid_lines)
    now = _utc_now()

    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT FIRST 1 INVITE_ID, STATUS
            FROM PR_BID_INVITE
            WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE = ?
            """,
            (request_dockey, code),
        )
        invite_row = cur.fetchone()
        if not invite_row:
            raise BiddingValidationError("supplier is not invited for this purchase request")

        invite_status = _clean_text(invite_row[1]).upper() or "OPEN"
        if invite_status == "CLOSED":
            raise BiddingValidationError("bidding invitation is already closed")

        cur.execute(
            """
            SELECT FIRST 1 BID_ID, STATUS
            FROM PR_BID_HDR
            WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE = ?
            ORDER BY BID_ID DESC
            """,
            (request_dockey, code),
        )
        bid_row = cur.fetchone()

        if bid_row:
            bid_id = int(bid_row[0])
            if _clean_text(bid_row[1]).upper() == "APPROVED":
                raise BiddingValidationError("approved bid cannot be edited")
            cur.execute(
                """
                UPDATE PR_BID_HDR
                SET REQUEST_NO = ?, SUPPLIER_NAME = ?, STATUS = ?, REMARKS = ?, CREATED_BY = ?, CREATED_AT = ?
                WHERE BID_ID = ?
                """,
                (
                    request_no,
                    _clean_text(supplier_name),
                    "SUBMITTED",
                    _clean_text(remarks),
                    _clean_text(created_by) or code,
                    now,
                    bid_id,
                ),
            )
            cur.execute("DELETE FROM PR_BID_DTL WHERE BID_ID = ?", (bid_id,))
        else:
            bid_id = _next_key(cur, "PR_BID_HDR", "BID_ID", "GEN_PR_BID_HDR_ID")
            cur.execute(
                """
                INSERT INTO PR_BID_HDR (
                    BID_ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME,
                    STATUS, REMARKS, CREATED_BY, CREATED_AT
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bid_id,
                    request_dockey,
                    request_no,
                    code,
                    _clean_text(supplier_name),
                    "SUBMITTED",
                    _clean_text(remarks),
                    _clean_text(created_by) or code,
                    now,
                ),
            )

        for line in lines:
            bid_dtl_id = _next_key(cur, "PR_BID_DTL", "BID_DTL_ID", "GEN_PR_BID_DTL_ID")
            cur.execute(
                """
                INSERT INTO PR_BID_DTL (
                    BID_DTL_ID, BID_ID, SOURCE_DTLKEY, ITEMCODE, DESCRIPTION,
                    BID_QTY, BID_UNITPRICE, BID_TAXAMT, BID_AMOUNT, LEAD_DAYS, REMARKS
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bid_dtl_id,
                    bid_id,
                    line["sourceDtlKey"],
                    line["itemCode"],
                    line["description"],
                    float(line["quantity"]),
                    float(line["unitPrice"]),
                    float(line["taxAmt"]),
                    float(line["amount"]),
                    line["leadDays"],
                    line["remarks"],
                ),
            )

        cur.execute(
            "UPDATE PR_BID_INVITE SET STATUS = ?, UPDATED_AT = ? WHERE INVITE_ID = ?",
            ("RESPONDED", now, int(invite_row[0])),
        )

        con.commit()
        total_amount = float(_money(sum((line["amount"] for line in lines), Decimal("0"))))
        return {
            "bidId": bid_id,
            "requestDockey": request_dockey,
            "requestNumber": request_no,
            "supplierCode": code,
            "status": "SUBMITTED",
            "lineCount": len(lines),
            "totalAmount": total_amount,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _bid_hdr_row_to_lines(cur: Any, bid_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT SOURCE_DTLKEY, ITEMCODE, DESCRIPTION, BID_QTY, BID_UNITPRICE, BID_TAXAMT,
               BID_AMOUNT, LEAD_DAYS, REMARKS
        FROM PR_BID_DTL
        WHERE BID_ID = ?
        ORDER BY BID_DTL_ID ASC
        """,
        (bid_id,),
    )
    lines = cur.fetchall() or []
    return [
        {
            "detailId": int(row[0]),
            "itemCode": _clean_text(row[1]),
            "description": _clean_text(row[2]),
            "quantity": float(_as_decimal(row[3], "0")),
            "unitPrice": float(_as_decimal(row[4], "0")),
            "tax": float(_as_decimal(row[5], "0")),
            "amount": float(_as_decimal(row[6], "0")),
            "leadDays": int(_as_decimal(row[7], "0")),
            "remarks": _clean_text(row[8]),
        }
        for row in lines
    ]


def _bid_hdr_row_to_dict(bid: tuple, lines: list[dict[str, Any]]) -> dict[str, Any]:
    udf_reason = _clean_text(bid[11]) if len(bid) > 11 else ""
    return {
        "bidId": int(bid[0]),
        "requestDockey": int(bid[1]),
        "requestNumber": _clean_text(bid[2]),
        "supplierCode": _clean_text(bid[3]),
        "supplierName": _clean_text(bid[4]),
        "status": _clean_text(bid[5]),
        "remarks": _clean_text(bid[6]),
        "createdBy": _clean_text(bid[7]),
        "createdAt": bid[8].isoformat() if bid[8] else None,
        "approvedBy": _clean_text(bid[9]),
        "approvedAt": bid[10].isoformat() if bid[10] else None,
        "udfReason": udf_reason,
        "lines": lines,
    }


def list_bids_for_request(request_dockey: int) -> list[dict[str, Any]]:
    con = _connect_db()
    try:
        cur = con.cursor()
        _ensure_pr_bid_hdr_udf_reason(con)
        cur = con.cursor()
        cur.execute(
            """
            SELECT BID_ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME,
                   STATUS, REMARKS, CREATED_BY, CREATED_AT, APPROVED_BY, APPROVED_AT,
                   UDF_REASON
            FROM PR_BID_HDR
            WHERE REQUEST_DOCKEY = ?
            ORDER BY CASE STATUS WHEN 'APPROVED' THEN 0 WHEN 'SUBMITTED' THEN 1 ELSE 9 END, BID_ID DESC
            """,
            (request_dockey,),
        )
        bid_rows = cur.fetchall() or []

        result: list[dict[str, Any]] = []
        for bid in bid_rows:
            bid_id = int(bid[0])
            lines = _bid_hdr_row_to_lines(cur, bid_id)
            result.append(_bid_hdr_row_to_dict(bid, lines))
        return result
    finally:
        con.close()


def get_supplier_bid_snapshot(request_dockey: int, supplier_code: str) -> dict[str, Any] | None:
    """Return this supplier's bid for a PR (for read-only review of pricing and admin decision)."""
    code = _clean_text(supplier_code)
    if not code:
        return None

    con = _connect_db()
    try:
        cur = con.cursor()
        _ensure_pr_bid_hdr_udf_reason(con)
        cur = con.cursor()
        cur.execute(
            """
            SELECT FIRST 1 BID_ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME,
                   STATUS, REMARKS, CREATED_BY, CREATED_AT, APPROVED_BY, APPROVED_AT,
                   UDF_REASON
            FROM PR_BID_HDR
            WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE = ?
            ORDER BY BID_ID DESC
            """,
            (request_dockey, code),
        )
        bid = cur.fetchone()
        if not bid:
            return None
        bid_id = int(bid[0])
        lines = _bid_hdr_row_to_lines(cur, bid_id)
        return _bid_hdr_row_to_dict(bid, lines)
    finally:
        con.close()


def get_approved_bid_for_request(request_dockey: int) -> dict[str, Any] | None:
    bids = list_bids_for_request(request_dockey)
    for bid in bids:
        if _clean_text(bid.get("status")).upper() == "APPROVED":
            return bid
    return None


def map_approved_bid_suppliers_by_request_ids(request_ids: list[int]) -> dict[int, dict[str, str]]:
    """Batch-load APPROVED bid supplier code/name per purchase request dockey."""
    cleaned = sorted({int(x) for x in request_ids if x and int(x) > 0})
    if not cleaned:
        return {}

    con = _connect_db()
    try:
        cur = con.cursor()
        if not _table_exists(cur, "PR_BID_HDR"):
            return {}
        placeholders = ", ".join(["?"] * len(cleaned))
        cur.execute(
            f"""
            SELECT REQUEST_DOCKEY, SUPPLIER_CODE, SUPPLIER_NAME
            FROM PR_BID_HDR
            WHERE STATUS = 'APPROVED'
              AND REQUEST_DOCKEY IN ({placeholders})
            """,
            cleaned,
        )
        rows = cur.fetchall() or []
        grouped: dict[int, list[tuple[str, str]]] = {}
        for row in rows:
            if not row:
                continue
            try:
                dk = int(row[0])
            except Exception:
                continue
            code = _clean_text(row[1])
            name = _clean_text(row[2]) or code
            if not code and not name:
                continue
            bucket = grouped.setdefault(dk, [])
            if (code, name) not in bucket:
                bucket.append((code, name))

        out: dict[int, dict[str, str]] = {}
        for dk, pairs in grouped.items():
            codes = [c for c, _ in pairs if c]
            names = [n for _, n in pairs if n]
            out[dk] = {
                "supplierCode": ", ".join(codes),
                "supplierName": ", ".join(names),
            }
        return out
    finally:
        con.close()


_AWARDED_SUPPLIERS_CACHE: dict[tuple[int, ...], tuple[float, dict[int, dict[str, str]]]] = {}
_AWARDED_SUPPLIERS_TTL_SEC = 45.0
_AWARDED_SUPPLIERS_CACHE_MAX = 48


def map_awarded_suppliers_by_request_ids(request_ids: list[int]) -> dict[int, dict[str, str]]:
    """Batch-load awarded suppliers (supports mixed item awards) per request dockey."""
    cleaned = sorted({int(x) for x in request_ids if x and int(x) > 0})
    if not cleaned:
        return {}

    key = tuple(cleaned)
    now = time.monotonic()
    stale_keys = [k for k, (t, _) in _AWARDED_SUPPLIERS_CACHE.items() if now - t > _AWARDED_SUPPLIERS_TTL_SEC]
    for k in stale_keys:
        _AWARDED_SUPPLIERS_CACHE.pop(k, None)
    hit = _AWARDED_SUPPLIERS_CACHE.get(key)
    if hit and now - hit[0] < _AWARDED_SUPPLIERS_TTL_SEC:
        return hit[1]

    con = _connect_db()
    try:
        cur = con.cursor()
        out: dict[int, dict[str, str]] = {}

        # Prefer line-award table (new mixed-supplier flow).
        if _table_exists(cur, "PR_BID_LINE_AWARD"):
            placeholders = ", ".join(["?"] * len(cleaned))
            cur.execute(
                f"""
                SELECT REQUEST_DOCKEY, SUPPLIER_CODE, SUPPLIER_NAME
                FROM PR_BID_LINE_AWARD
                WHERE REQUEST_DOCKEY IN ({placeholders})
                ORDER BY REQUEST_DOCKEY, SUPPLIER_CODE
                """,
                cleaned,
            )
            rows = cur.fetchall() or []
            if rows:
                by_req: dict[int, list[tuple[str, str]]] = {}
                for row in rows:
                    if not row:
                        continue
                    try:
                        req_id = int(row[0])
                    except Exception:
                        continue
                    code = _clean_text(row[1])
                    name = _clean_text(row[2]) or code
                    if not code and not name:
                        continue
                    bucket = by_req.setdefault(req_id, [])
                    if (code, name) not in bucket:
                        bucket.append((code, name))
                for req_id, pairs in by_req.items():
                    codes = [c for c, _ in pairs if c]
                    names = [n for _, n in pairs if n]
                    out[req_id] = {
                        "supplierCode": ", ".join(codes),
                        "supplierName": ", ".join(names),
                    }
                if len(_AWARDED_SUPPLIERS_CACHE) >= _AWARDED_SUPPLIERS_CACHE_MAX:
                    oldest = min(_AWARDED_SUPPLIERS_CACHE, key=lambda k: _AWARDED_SUPPLIERS_CACHE[k][0])
                    _AWARDED_SUPPLIERS_CACHE.pop(oldest, None)
                _AWARDED_SUPPLIERS_CACHE[key] = (now, out)
                return out

        # Fallback: old single-bid flow.
        out = map_approved_bid_suppliers_by_request_ids(cleaned)
        if len(_AWARDED_SUPPLIERS_CACHE) >= _AWARDED_SUPPLIERS_CACHE_MAX:
            oldest = min(_AWARDED_SUPPLIERS_CACHE, key=lambda k: _AWARDED_SUPPLIERS_CACHE[k][0])
            _AWARDED_SUPPLIERS_CACHE.pop(oldest, None)
        _AWARDED_SUPPLIERS_CACHE[key] = (now, out)
        return out
    finally:
        con.close()


def approve_bid(request_dockey: int, bid_id: int, actor: str, udf_reason: str = "") -> dict[str, Any]:
    now = _utc_now()
    reason = _clean_text(udf_reason)
    con = _connect_db()
    try:
        cur = con.cursor()
        _ensure_pr_bid_hdr_udf_reason(con)
        cur = con.cursor()
        cur.execute(
            "SELECT FIRST 1 BID_ID, SUPPLIER_CODE, REQUEST_NO FROM PR_BID_HDR WHERE BID_ID = ? AND REQUEST_DOCKEY = ?",
            (bid_id, request_dockey),
        )
        row = cur.fetchone()
        if not row:
            raise BiddingValidationError("bid not found for this request")

        supplier_code = _clean_text(row[1])
        request_no = _clean_text(row[2])

        cur.execute(
            "UPDATE PR_BID_HDR SET STATUS = ?, APPROVED_BY = ?, APPROVED_AT = ? WHERE REQUEST_DOCKEY = ? AND BID_ID <> ?",
            ("REJECTED", _clean_text(actor) or "admin", now, request_dockey, bid_id),
        )
        cur.execute(
            """
            UPDATE PR_BID_HDR
            SET STATUS = ?, APPROVED_BY = ?, APPROVED_AT = ?, UDF_REASON = ?
            WHERE BID_ID = ?
            """,
            ("APPROVED", _clean_text(actor) or "admin", now, reason, bid_id),
        )
        cur.execute(
            "UPDATE PR_BID_INVITE SET STATUS = ?, UPDATED_AT = ? WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE = ?",
            ("AWARDED", now, request_dockey, supplier_code),
        )
        cur.execute(
            "UPDATE PR_BID_INVITE SET STATUS = ?, UPDATED_AT = ? WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE <> ?",
            ("CLOSED", now, request_dockey, supplier_code),
        )

        con.commit()
        return {
            "requestDockey": request_dockey,
            "requestNumber": request_no,
            "approvedBidId": bid_id,
            "supplierCode": supplier_code,
            "status": "APPROVED",
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def reject_bid(request_dockey: int, bid_id: int, actor: str, udf_reason: str = "") -> dict[str, Any]:
    """Reject a bid; admin explanation is stored in PR_BID_HDR.UDF_REASON (supplier header REMARKS unchanged)."""
    now = _utc_now()
    reason = _clean_text(udf_reason)
    con = _connect_db()
    try:
        cur = con.cursor()
        _ensure_pr_bid_hdr_udf_reason(con)
        cur = con.cursor()
        cur.execute(
            "SELECT FIRST 1 BID_ID FROM PR_BID_HDR WHERE BID_ID = ? AND REQUEST_DOCKEY = ?",
            (bid_id, request_dockey),
        )
        row = cur.fetchone()
        if not row:
            raise BiddingValidationError("bid not found for this request")

        cur.execute(
            """
            UPDATE PR_BID_HDR
            SET STATUS = ?, APPROVED_BY = ?, APPROVED_AT = ?, UDF_REASON = ?
            WHERE BID_ID = ?
            """,
            ("REJECTED", _clean_text(actor) or "admin", now, reason, bid_id),
        )
        con.commit()
        return {
            "requestDockey": request_dockey,
            "bidId": bid_id,
            "status": "REJECTED",
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def save_line_awards(
    request_dockey: int,
    awards: list[dict[str, Any]],
    actor: str,
    udf_reason: str = "",
) -> dict[str, Any]:
    """Save per-detail awarded supplier bid lines for one request."""
    if not isinstance(awards, list) or not awards:
        raise BiddingValidationError("awards[] is required")

    normalized: list[tuple[int, int]] = []
    seen_details: set[int] = set()
    for row in awards:
        if not isinstance(row, dict):
            raise BiddingValidationError("each award row must be an object")
        try:
            detail_id = int(row.get("detailId"))
            bid_id = int(row.get("bidId"))
        except Exception as exc:
            raise BiddingValidationError("each award row requires valid detailId and bidId") from exc
        if detail_id <= 0 or bid_id <= 0:
            raise BiddingValidationError("each award row requires valid detailId and bidId")
        if detail_id in seen_details:
            raise BiddingValidationError(f"duplicate award detailId {detail_id}")
        seen_details.add(detail_id)
        normalized.append((detail_id, bid_id))

    now = _utc_now()
    reason = _clean_text(udf_reason)
    who = _clean_text(actor) or "admin"
    con = _connect_db()
    try:
        cur = con.cursor()
        if not _table_exists(cur, "PR_BID_LINE_AWARD"):
            raise BiddingValidationError("line award table is not available")

        bid_ids = sorted({bid_id for _, bid_id in normalized})
        bid_placeholders = ", ".join(["?"] * len(bid_ids))
        cur.execute(
            f"""
            SELECT BID_ID, REQUEST_DOCKEY, SUPPLIER_CODE, SUPPLIER_NAME
            FROM PR_BID_HDR
            WHERE BID_ID IN ({bid_placeholders})
            """,
            tuple(bid_ids),
        )
        bid_rows = cur.fetchall() or []
        bid_map: dict[int, dict[str, Any]] = {}
        for row in bid_rows:
            if not row:
                continue
            try:
                bid_id = int(row[0])
                req = int(row[1])
            except Exception:
                continue
            bid_map[bid_id] = {
                "requestDockey": req,
                "supplierCode": _clean_text(row[2]),
                "supplierName": _clean_text(row[3]),
            }

        detail_bid_pairs = set(normalized)
        dtl_placeholders = ", ".join(["?"] * len(bid_ids))
        cur.execute(
            f"""
            SELECT BID_ID, SOURCE_DTLKEY
            FROM PR_BID_DTL
            WHERE BID_ID IN ({dtl_placeholders})
            """,
            tuple(bid_ids),
        )
        valid_pairs = {
            (int(row[1]), int(row[0]))
            for row in (cur.fetchall() or [])
            if row and row[0] is not None and row[1] is not None
        }

        for detail_id, bid_id in normalized:
            bid = bid_map.get(bid_id)
            if not bid:
                raise BiddingValidationError(f"bid {bid_id} not found")
            if int(bid.get("requestDockey") or 0) != int(request_dockey):
                raise BiddingValidationError(f"bid {bid_id} does not belong to request {request_dockey}")
            if (detail_id, bid_id) not in valid_pairs:
                raise BiddingValidationError(f"detail {detail_id} is not present in bid {bid_id}")

        cur.execute("DELETE FROM PR_BID_LINE_AWARD WHERE REQUEST_DOCKEY = ?", (request_dockey,))
        saved = 0
        supplier_codes: set[str] = set()
        for detail_id, bid_id in normalized:
            bid = bid_map[bid_id]
            award_id = _next_key(cur, "PR_BID_LINE_AWARD", "AWARD_ID", "GEN_PR_BID_LINE_AWARD_ID")
            supplier_code = _clean_text(bid.get("supplierCode"))
            supplier_name = _clean_text(bid.get("supplierName"))
            cur.execute(
                """
                INSERT INTO PR_BID_LINE_AWARD (
                    AWARD_ID, REQUEST_DOCKEY, DETAIL_ID, BID_ID, SUPPLIER_CODE, SUPPLIER_NAME,
                    UDF_REASON, APPROVED_BY, APPROVED_AT
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(award_id),
                    int(request_dockey),
                    int(detail_id),
                    int(bid_id),
                    supplier_code,
                    supplier_name,
                    reason,
                    who,
                    now,
                ),
            )
            if supplier_code:
                supplier_codes.add(supplier_code)
            saved += 1

        # Requested behavior: any bid not selected in awards is treated as rejected.
        cur.execute(
            "UPDATE PR_BID_HDR SET STATUS = ?, APPROVED_BY = ?, APPROVED_AT = ?, UDF_REASON = ? WHERE REQUEST_DOCKEY = ?",
            ("REJECTED", who, now, reason, request_dockey),
        )
        if bid_ids:
            yes_placeholders = ", ".join(["?"] * len(bid_ids))
            cur.execute(
                f"UPDATE PR_BID_HDR SET STATUS = ?, APPROVED_BY = ?, APPROVED_AT = ?, UDF_REASON = ? WHERE REQUEST_DOCKEY = ? AND BID_ID IN ({yes_placeholders})",
                tuple(["APPROVED", who, now, reason, request_dockey, *bid_ids]),
            )

        cur.execute("UPDATE PR_BID_INVITE SET STATUS = ?, UPDATED_AT = ? WHERE REQUEST_DOCKEY = ?", ("CLOSED", now, request_dockey))
        if supplier_codes:
            code_placeholders = ", ".join(["?"] * len(supplier_codes))
            cur.execute(
                f"UPDATE PR_BID_INVITE SET STATUS = ?, UPDATED_AT = ? WHERE REQUEST_DOCKEY = ? AND SUPPLIER_CODE IN ({code_placeholders})",
                tuple(["AWARDED", now, request_dockey, *sorted(supplier_codes)]),
            )

        con.commit()
        return {
            "requestDockey": int(request_dockey),
            "savedCount": saved,
            "supplierCount": len(supplier_codes),
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_line_awards_for_request(request_dockey: int) -> list[dict[str, Any]]:
    """Return awarded bid lines (per detail) for one request."""
    con = _connect_db()
    try:
        cur = con.cursor()
        if not _table_exists(cur, "PR_BID_LINE_AWARD"):
            return []
        cur.execute(
            """
            SELECT A.DETAIL_ID, A.BID_ID, A.SUPPLIER_CODE, A.SUPPLIER_NAME, A.UDF_REASON, A.APPROVED_BY, A.APPROVED_AT,
                   D.ITEMCODE, D.DESCRIPTION, D.BID_QTY, D.BID_UNITPRICE, D.BID_TAXAMT, D.BID_AMOUNT, D.LEAD_DAYS
            FROM PR_BID_LINE_AWARD A
            LEFT JOIN PR_BID_DTL D
              ON D.BID_ID = A.BID_ID AND D.SOURCE_DTLKEY = A.DETAIL_ID
            WHERE A.REQUEST_DOCKEY = ?
            ORDER BY A.DETAIL_ID
            """,
            (request_dockey,),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall() or []:
            if not row:
                continue
            out.append({
                "detailId": int(row[0]) if row[0] is not None else 0,
                "bidId": int(row[1]) if row[1] is not None else 0,
                "supplierCode": _clean_text(row[2]),
                "supplierName": _clean_text(row[3]),
                "udfReason": _clean_text(row[4]),
                "approvedBy": _clean_text(row[5]),
                "approvedAt": row[6].isoformat() if row[6] else None,
                "itemCode": _clean_text(row[7]),
                "description": _clean_text(row[8]),
                "quantity": float(_money(_as_decimal(row[9], "0"))),
                "unitPrice": float(_money(_as_decimal(row[10], "0"))),
                "tax": float(_money(_as_decimal(row[11], "0"))),
                "amount": float(_money(_as_decimal(row[12], "0"))),
                "leadDays": int(row[13]) if row[13] is not None else 0,
            })
        return out
    finally:
        con.close()


def get_transfer_gate_state(request_dockey: int) -> dict[str, Any]:
    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM PR_BID_INVITE WHERE REQUEST_DOCKEY = ?", (request_dockey,))
        invite_count_row = cur.fetchone()
        invite_count = int(invite_count_row[0] or 0) if invite_count_row else 0

        cur.execute("SELECT COUNT(*) FROM PR_BID_HDR WHERE REQUEST_DOCKEY = ?", (request_dockey,))
        bid_count_row = cur.fetchone()
        bid_count = int(bid_count_row[0] or 0) if bid_count_row else 0

        approved = get_approved_bid_for_request(request_dockey)
        line_awards = get_line_awards_for_request(request_dockey)
        return {
            "requestDockey": request_dockey,
            "hasInvitations": invite_count > 0,
            "invitationCount": invite_count,
            "bidCount": bid_count,
            "approvedBid": approved,
            "lineAwards": line_awards,
            "hasLineAwards": bool(line_awards),
        }
    finally:
        con.close()


def apply_approved_bid_to_request(
    request_header: dict[str, Any],
    approved_bid: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Backward-compatible wrapper for old single-bid flow."""
    if not approved_bid:
        return request_header, {}
    lines = approved_bid.get("lines") if isinstance(approved_bid, dict) else []
    if not isinstance(lines, list):
        lines = []
    awarded_lines = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        awarded_lines.append({
            "detailId": line.get("detailId"),
            "supplierCode": approved_bid.get("supplierCode"),
            "supplierName": approved_bid.get("supplierName"),
            "unitPrice": line.get("unitPrice"),
            "tax": line.get("tax"),
            "amount": line.get("amount"),
            "quantity": line.get("quantity"),
        })
    return apply_awarded_lines_to_request(request_header, awarded_lines), {
        "code": _clean_text(approved_bid.get("supplierCode")),
        "companyname": _clean_text(approved_bid.get("supplierName")),
    }


def apply_awarded_lines_to_request(
    request_header: dict[str, Any],
    awarded_lines: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Overlay awarded line prices onto request detail rows."""
    if not awarded_lines:
        return request_header

    line_map: dict[int, dict[str, Any]] = {}
    for line in awarded_lines:
        if not isinstance(line, dict):
            continue
        try:
            detail_id = int(line.get("detailId"))
        except Exception:
            continue
        line_map[detail_id] = line

    updated_header = dict(request_header)
    source_details = updated_header.get("sdsdocdetail")
    if isinstance(source_details, list):
        patched_details: list[dict[str, Any]] = []
        for row in source_details:
            if not isinstance(row, dict):
                patched_details.append(row)
                continue
            cloned = dict(row)
            try:
                detail_id = int(cloned.get("dtlkey"))
            except Exception:
                patched_details.append(cloned)
                continue
            hit = line_map.get(detail_id)
            if hit:
                qty = _money(_as_decimal(cloned.get("qty"), "0"))
                price = _money(_as_decimal(hit.get("unitPrice"), "0"))
                tax = _money(_as_decimal(hit.get("tax"), "0"))
                amount = _money(_as_decimal(hit.get("amount"), "0"))
                if amount <= 0:
                    amount = _money((qty * price) + tax)
                cloned["unitprice"] = float(price)
                cloned["taxamt"] = float(tax)
                cloned["amount"] = float(amount)
            patched_details.append(cloned)
        updated_header["sdsdocdetail"] = patched_details
    return updated_header


def validate_transfer_against_approved_bid(
    request_dockey: int,
    supplier_code: str,
    transfer_lines: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Backward-compatible wrapper: return single approved bid if no line awards are used."""
    gate = get_transfer_gate_state(request_dockey)
    if gate.get("hasLineAwards"):
        # Keep legacy caller safe; mixed awards are handled by validate_transfer_against_line_awards.
        return None
    if not gate.get("hasInvitations"):
        return None
    approved_bid = gate.get("approvedBid")
    if not isinstance(approved_bid, dict):
        raise BiddingValidationError("PR has supplier bidding invitations but no approved bid yet")
    return approved_bid


def validate_transfer_against_line_awards(
    request_dockey: int,
    transfer_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enforce per-detail awarded bid selections for PR->PO transfer."""
    gate = get_transfer_gate_state(request_dockey)
    if not gate.get("hasInvitations"):
        return []

    line_awards = gate.get("lineAwards") if isinstance(gate, dict) else []
    if not isinstance(line_awards, list) or not line_awards:
        raise BiddingValidationError("PR has supplier bidding invitations but no awarded item selections yet")

    award_map: dict[int, dict[str, Any]] = {}
    for row in line_awards:
        if not isinstance(row, dict):
            continue
        try:
            detail_id = int(row.get("detailId"))
        except Exception:
            continue
        award_map[detail_id] = row

    selected_detail_ids: list[int] = []
    qty_by_detail: dict[int, Decimal] = {}
    for row in transfer_lines:
        if not isinstance(row, dict):
            continue
        raw_detail_id = row.get("fromdtlkey", row.get("dtlkey", row.get("detailId")))
        raw_qty = row.get("qty", row.get("quantity", row.get("transferQty")))
        try:
            detail_id = int(raw_detail_id)
        except Exception as exc:
            raise BiddingValidationError("transfer line detail id is invalid") from exc
        qty = _money(_as_decimal(raw_qty, "0"))
        if qty <= 0:
            continue
        selected_detail_ids.append(detail_id)
        qty_by_detail[detail_id] = qty

    awarded_lines: list[dict[str, Any]] = []
    for detail_id in selected_detail_ids:
        award = award_map.get(detail_id)
        if not award:
            raise BiddingValidationError(f"detail {detail_id} has no awarded supplier selection")
        approved_qty = _money(_as_decimal(award.get("quantity"), "0"))
        if approved_qty <= 0:
            raise BiddingValidationError(f"detail {detail_id} has invalid awarded quantity")
        transfer_qty = qty_by_detail.get(detail_id, Decimal("0"))
        if transfer_qty > approved_qty:
            raise BiddingValidationError(
                f"transfer qty for detail {detail_id} exceeds awarded qty ({float(approved_qty):.2f})"
            )
        awarded_lines.append(award)

    return awarded_lines
