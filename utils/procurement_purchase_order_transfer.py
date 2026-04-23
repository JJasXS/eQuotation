"""Transfer approved purchase request lines into purchase order tables."""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from utils.db_utils import get_db_connection
from utils.procurement_purchase_request import (
    _as_date,
    _as_decimal,
    _clean_text,
    _column_is_numeric,
    _encode_status,
    _get_table_columns,
    _insert_dynamic,
    _money,
    _next_key,
    _pick_existing,
)


class PurchaseOrderTransferValidationError(ValueError):
    """Raised when a purchase request cannot be transferred to purchase order."""


def _connect_db():
    return get_db_connection()


def _coerce_bool(value: Any) -> bool:
    if value is True or value == 1:
        return True
    text = str(value or "").strip().lower()
    return text in {"true", "1", "t", "y", "yes"}


def _normalize_transfer_date(value: Any) -> str:
    parsed = _as_date(value)
    if parsed:
        return parsed.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return datetime.utcnow().date().isoformat()


def _next_purchase_order_number(cur: Any, header_columns: set[str]) -> str:
    docno_col = _pick_existing(header_columns, "DOCNO")
    prefix = f"PO-{datetime.utcnow().strftime('%Y%m%d')}-"
    if not docno_col:
        return f"{prefix}0001"

    cur.execute(
        f"""
        SELECT FIRST 1 {docno_col}
        FROM PH_PO
        WHERE {docno_col} LIKE ?
        ORDER BY {docno_col} DESC
        """,
        (f"{prefix}%",),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return f"{prefix}0001"

    last_value = _clean_text(row[0])
    try:
        sequence = int(last_value.split("-")[-1]) + 1
    except Exception:
        sequence = 1
    return f"{prefix}{sequence:04d}"


def _purchase_order_number_exists(cur: Any, header_columns: set[str], docno: str) -> bool:
    docno_col = _pick_existing(header_columns, "DOCNO")
    if not docno_col or not docno:
        return False
    cur.execute(f"SELECT FIRST 1 {docno_col} FROM PH_PO WHERE {docno_col} = ?", (docno,))
    return cur.fetchone() is not None


def _fetch_existing_transfer_qty_map(
    cur: Any,
    request_dockey: int,
    detail_ids: list[int],
    xtrans_columns: set[str],
) -> dict[int, Decimal]:
    fromdoctype_col = _pick_existing(xtrans_columns, "FROMDOCTYPE")
    fromdockey_col = _pick_existing(xtrans_columns, "FROMDOCKEY")
    fromdtlkey_col = _pick_existing(xtrans_columns, "FROMDTLKEY")
    qty_col = _pick_existing(xtrans_columns, "QTY")
    sqty_col = _pick_existing(xtrans_columns, "SQTY")

    if not detail_ids or not (fromdoctype_col and fromdockey_col and fromdtlkey_col and (qty_col or sqty_col)):
        return {}

    quantity_expr = f"COALESCE({sqty_col}, {qty_col}, 0)" if sqty_col and qty_col else (sqty_col or qty_col)
    placeholders = ", ".join(["?"] * len(detail_ids))
    cur.execute(
        f"""
        SELECT {fromdtlkey_col}, SUM(CAST({quantity_expr} AS DOUBLE PRECISION))
        FROM ST_XTRANS
        WHERE {fromdoctype_col} = ?
          AND {fromdockey_col} = ?
          AND {fromdtlkey_col} IN ({placeholders})
        GROUP BY {fromdtlkey_col}
        """,
        tuple(["PQ", request_dockey, *detail_ids]),
    )
    rows = cur.fetchall() or []
    result: dict[int, Decimal] = {}
    for row in rows:
        try:
            result[int(row[0])] = _as_decimal(row[1], "0")
        except Exception:
            continue
    return result


def _get_string_column_lengths(cur: Any, table_name: str) -> dict[str, int]:
    """Return max character length for text/varchar columns in a table."""
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME) AS COL_NAME,
               COALESCE(F.RDB$CHARACTER_LENGTH, F.RDB$FIELD_LENGTH) AS MAX_LEN
        FROM RDB$RELATION_FIELDS RF
        JOIN RDB$FIELDS F ON RF.RDB$FIELD_SOURCE = F.RDB$FIELD_NAME
        WHERE RF.RDB$RELATION_NAME = ?
          AND F.RDB$FIELD_TYPE IN (14, 37)
        """,
        (table_name.upper(),),
    )
    rows = cur.fetchall() or []
    result: dict[str, int] = {}
    for row in rows:
        if not row or row[0] is None or row[1] is None:
            continue
        try:
            result[str(row[0]).strip().upper()] = int(row[1])
        except Exception:
            continue
    return result


def _fit_string_values(row: dict[str, Any], string_lengths: dict[str, int]) -> dict[str, Any]:
    """Trim strings to table-defined length to avoid SQLCODE -303 truncation errors."""
    fitted: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str):
            max_len = string_lengths.get(str(key).upper())
            if isinstance(max_len, int) and max_len > 0 and len(value) > max_len:
                fitted[key] = value[:max_len]
            else:
                fitted[key] = value
        else:
            fitted[key] = value
    return fitted


def transfer_purchase_request_to_po(
    purchase_request: dict[str, Any],
    transfer_lines: list[dict[str, Any]],
    supplier: dict[str, Any] | None = None,
    created_by: str = "system",
    transfer_date: Any = None,
) -> dict[str, Any]:
    """Create PH_PO, PH_PODTL, and ST_XTRANS rows from approved PR detail lines."""
    if not isinstance(purchase_request, dict):
        raise PurchaseOrderTransferValidationError("purchase_request must be an object")
    if not isinstance(transfer_lines, list) or not transfer_lines:
        raise PurchaseOrderTransferValidationError("transfer_lines[] is required")
    if supplier is None:
        supplier = {}
    if not isinstance(supplier, dict):
        raise PurchaseOrderTransferValidationError("supplier must be an object")

    request_dockey = purchase_request.get("dockey")
    try:
        request_dockey = int(request_dockey)
    except Exception as exc:
        raise PurchaseOrderTransferValidationError("purchase_request.dockey is required") from exc

    request_docno = _clean_text(purchase_request.get("docno")) or f"PQ-{request_dockey}"
    if not _coerce_bool(purchase_request.get("transferable", True)):
        raise PurchaseOrderTransferValidationError("purchase request is not transferable")

    supplier_code = _clean_text(
        supplier.get("code")
        or supplier.get("supplierId")
        or purchase_request.get("code")
        or purchase_request.get("supplierid")
        or purchase_request.get("agent")
    )
    supplier_name = _clean_text(
        supplier.get("companyname")
        or supplier.get("companyName")
        or purchase_request.get("companyname")
    )
    supplier_currency_code = _clean_text(
        supplier.get("currencycode")
        or supplier.get("currencyCode")
        or supplier.get("currency")
    )
    supplier_currency_rate_raw = supplier.get("currencyrate")
    if supplier_currency_rate_raw is None:
        supplier_currency_rate_raw = supplier.get("currencyRate")

    if not supplier_code:
        raise PurchaseOrderTransferValidationError(
            "supplier code is missing on purchase request (PH_PQ.CODE)"
        )
    if not supplier_name:
        raise PurchaseOrderTransferValidationError(
            "supplier name is missing on purchase request (PH_PQ.COMPANYNAME)"
        )

    source_details = purchase_request.get("sdsdocdetail")
    if not isinstance(source_details, list) or not source_details:
        raise PurchaseOrderTransferValidationError("purchase_request.sdsdocdetail is required")

    detail_map: dict[int, dict[str, Any]] = {}
    for row in source_details:
        if not isinstance(row, dict):
            continue
        try:
            detail_id = int(row.get("dtlkey"))
        except Exception:
            continue
        detail_map[detail_id] = row

    normalized_transfers: list[dict[str, Any]] = []
    requested_detail_ids: list[int] = []
    for line in transfer_lines:
        if not isinstance(line, dict):
            continue
        raw_detail_id = line.get("fromdtlkey", line.get("dtlkey", line.get("detailId")))
        raw_quantity = line.get("qty", line.get("quantity", line.get("transferQty")))
        try:
            detail_id = int(raw_detail_id)
        except Exception as exc:
            raise PurchaseOrderTransferValidationError("each transfer line requires a valid detail id") from exc

        quantity = _money(_as_decimal(raw_quantity, "0"))
        if quantity <= 0:
            raise PurchaseOrderTransferValidationError(f"transfer quantity must be > 0 for detail {detail_id}")
        if detail_id not in detail_map:
            raise PurchaseOrderTransferValidationError(f"purchase request detail {detail_id} was not found")

        normalized_transfers.append({"detailId": detail_id, "quantity": quantity})
        requested_detail_ids.append(detail_id)

    con = _connect_db()
    try:
        cur = con.cursor()
        po_header_cols = _get_table_columns(cur, "PH_PO")
        po_detail_cols = _get_table_columns(cur, "PH_PODTL")
        xtrans_cols = _get_table_columns(cur, "ST_XTRANS")
        po_header_str_len = _get_string_column_lengths(cur, "PH_PO")
        po_detail_str_len = _get_string_column_lengths(cur, "PH_PODTL")
        xtrans_str_len = _get_string_column_lengths(cur, "ST_XTRANS")

        po_header_key_col = _pick_existing(po_header_cols, "DOCKEY", "ID")
        po_detail_key_col = _pick_existing(po_detail_cols, "DTLKEY", "ID")
        po_detail_fk_col = _pick_existing(po_detail_cols, "DOCKEY")
        po_status_col = _pick_existing(po_header_cols, "STATUS")
        xtrans_key_col = _pick_existing(xtrans_cols, "DOCKEY", "ID")

        if not po_header_key_col or not po_detail_key_col or not po_detail_fk_col or not xtrans_key_col:
            raise PurchaseOrderTransferValidationError("purchase order table schema is missing required key columns")

        existing_qty_map = _fetch_existing_transfer_qty_map(cur, request_dockey, requested_detail_ids, xtrans_cols)
        docno = _clean_text(supplier.get("docno") or supplier.get("poNumber")) or _next_purchase_order_number(cur, po_header_cols)
        if _purchase_order_number_exists(cur, po_header_cols, docno):
            raise PurchaseOrderTransferValidationError(f"purchase order number already exists: {docno}")

        po_dockey = _next_key(
            cur,
            "PH_PO",
            po_header_key_col,
            ["GEN_PH_PO_ID", "GEN_PH_PO_DOCKEY", "GEN_PH_PO", "SEQ_PH_PO_DOCKEY"],
        )

        status_is_numeric = bool(po_status_col and _column_is_numeric(cur, "PH_PO", po_status_col))
        po_status_value = _encode_status("DRAFT", status_is_numeric)
        effective_date = _normalize_transfer_date(transfer_date or purchase_request.get("docdate"))
        total_doc_amount = Decimal("0")
        inserted_detail_keys: list[int] = []
        xtrans_rows: list[dict[str, Any]] = []

        detail_inserts: list[dict[str, Any]] = []
        for line_index, line in enumerate(normalized_transfers, start=1):
            source = detail_map[line["detailId"]]
            if not _coerce_bool(source.get("udf_pqapproved")):
                raise PurchaseOrderTransferValidationError(
                    f"purchase request detail {line['detailId']} is not approved"
                )
            if not _coerce_bool(source.get("transferable", True)):
                raise PurchaseOrderTransferValidationError(
                    f"purchase request detail {line['detailId']} is not transferable"
                )

            source_qty = _money(_as_decimal(source.get("qty"), "0"))
            if source_qty <= 0:
                raise PurchaseOrderTransferValidationError(
                    f"purchase request detail {line['detailId']} has invalid qty"
                )

            already_transferred = _money(_as_decimal(existing_qty_map.get(line["detailId"], Decimal("0")), "0"))
            remaining_qty = _money(source_qty - already_transferred)
            if line["quantity"] > remaining_qty:
                raise PurchaseOrderTransferValidationError(
                    f"transfer quantity exceeds remaining qty for detail {line['detailId']}"
                )

            unit_price = _money(_as_decimal(source.get("unitprice"), "0"))
            line_tax = Decimal("0")
            source_tax = _money(_as_decimal(source.get("taxamt"), "0"))
            if source_qty > 0 and source_tax != 0:
                line_tax = _money((source_tax / source_qty) * line["quantity"])
            amount = _money((unit_price * line["quantity"]) + line_tax)
            total_doc_amount += amount

            po_detail_key = _next_key(
                cur,
                "PH_PODTL",
                po_detail_key_col,
                ["GEN_PH_PODTL_ID", "GEN_PH_PODTL_DTLKEY", "GEN_PH_PODTL", "SEQ_PH_PODTL_DTLKEY"],
            )
            inserted_detail_keys.append(po_detail_key)

            detail_values = {
                po_detail_key_col: po_detail_key,
                po_detail_fk_col: po_dockey,
                "SEQ": source.get("seq") if source.get("seq") is not None else line_index * 1000,
                "ITEMCODE": _clean_text(source.get("itemcode")),
                "LOCATION": _clean_text(source.get("location")),
                "BATCH": _clean_text(source.get("batch")),
                "PROJECT": _clean_text(source.get("project")) or _clean_text(purchase_request.get("project")) or "----",
                "DESCRIPTION": _clean_text(source.get("description")),
                "DESCRIPTION2": _clean_text(source.get("description2")),
                "DESCRIPTION3": source.get("description3"),
                "PERMITNO": _clean_text(source.get("permitno")),
                "QTY": float(line["quantity"]),
                "UOM": _clean_text(source.get("uom")) or "UNIT",
                "RATE": float(_as_decimal(source.get("rate"), "1")),
                "SQTY": float(line["quantity"]),
                "SUOMQTY": float(_as_decimal(source.get("suomqty"), "0")),
                "OFFSETQTY": float(_as_decimal(source.get("offsetqty"), "0")),
                "UNITPRICE": float(unit_price),
                "DELIVERYDATE": _normalize_transfer_date(source.get("deliverydate") or effective_date),
                "DISC": _clean_text(source.get("disc")),
                "TAX": _clean_text(source.get("tax")),
                "TARIFF": _clean_text(source.get("tariff")),
                "TAXEXEMPTIONREASON": _clean_text(source.get("taxexemptionreason")),
                "IRBM_CLASSIFICATION": _clean_text(source.get("irbm_classification")),
                "TAXRATE": _clean_text(source.get("taxrate")),
                "TAXAMT": float(line_tax),
                "LOCALTAXAMT": float(line_tax),
                "EXEMPTED_TAXRATE": _clean_text(source.get("exempted_taxrate")),
                "EXEMPTED_TAXAMT": float(_as_decimal(source.get("exempted_taxamt"), "0")),
                "TAXINCLUSIVE": bool(source.get("taxinclusive") or False),
                "AMOUNT": float(amount),
                "LOCALAMOUNT": float(amount),
                "PRINTABLE": bool(source.get("printable") if source.get("printable") is not None else True),
                "FROMDOCTYPE": "PQ",
                "FROMDOCKEY": request_dockey,
                "FROMDTLKEY": line["detailId"],
                "TRANSFERABLE": True,
                "REMARK1": _clean_text(source.get("remark1")),
                "REMARK2": _clean_text(source.get("remark2")),
            }
            detail_inserts.append(detail_values)

            xtrans_rows.append(
                {
                    xtrans_key_col: _next_key(
                        cur,
                        "ST_XTRANS",
                        xtrans_key_col,
                        ["GEN_ST_XTRANS_ID", "GEN_ST_XTRANS_DOCKEY", "GEN_ST_XTRANS", "SEQ_ST_XTRANS_DOCKEY"],
                    ),
                    "CODE": supplier_code,
                    "FROMDOCTYPE": "PQ",
                    "TODOCTYPE": "PO",
                    "FROMDOCKEY": request_dockey,
                    "TODOCKEY": po_dockey,
                    "FROMDTLKEY": line["detailId"],
                    "TODTLKEY": po_detail_key,
                    "QTY": float(line["quantity"]),
                    "SQTY": float(line["quantity"]),
                    "TOSTATUS": po_status_value,
                }
            )

        header_values = {
            po_header_key_col: po_dockey,
            "DOCNO": docno,
            "DOCNOEX": docno,
            "DOCDATE": effective_date,
            "POSTDATE": effective_date,
            "TAXDATE": effective_date,
            "CODE": supplier_code,
            "COMPANYNAME": supplier_name,
            "ADDRESS1": _clean_text(supplier.get("address1")),
            "ADDRESS2": _clean_text(supplier.get("address2")),
            "ADDRESS3": _clean_text(supplier.get("address3")),
            "ADDRESS4": _clean_text(supplier.get("address4")),
            "POSTCODE": _clean_text(supplier.get("postcode")),
            "CITY": _clean_text(supplier.get("city")),
            "STATE": _clean_text(supplier.get("state")),
            "COUNTRY": _clean_text(supplier.get("country")),
            "PHONE1": _clean_text(supplier.get("phone1")),
            "MOBILE": _clean_text(supplier.get("mobile")),
            "FAX1": _clean_text(supplier.get("fax1")),
            "ATTENTION": _clean_text(supplier.get("attention")),
            "AREA": _clean_text(purchase_request.get("area")) or "----",
            "AGENT": supplier_code,
            "PROJECT": _clean_text(purchase_request.get("project")) or "----",
            "TERMS": _clean_text(supplier.get("terms")),
            "CURRENCYCODE": supplier_currency_code or _clean_text(purchase_request.get("currencycode")) or "MYR",
            "CURRENCYRATE": float(
                _as_decimal(
                    supplier_currency_rate_raw
                    if supplier_currency_rate_raw is not None
                    else purchase_request.get("currencyrate"),
                    "1",
                )
            ),
            "SHIPPER": _clean_text(purchase_request.get("shipper")) or "----",
            "DESCRIPTION": _clean_text(supplier.get("description")) or f"Purchase Order - {request_docno}",
            "CANCELLED": False,
            "STATUS": po_status_value,
            "DOCAMT": float(_money(total_doc_amount)),
            "LOCALDOCAMT": float(_money(total_doc_amount)),
            "BRANCHNAME": _clean_text(supplier.get("branchname")),
            "DADDRESS1": _clean_text(purchase_request.get("daddress1")),
            "DADDRESS2": _clean_text(purchase_request.get("daddress2")),
            "DADDRESS3": _clean_text(purchase_request.get("daddress3")),
            "DADDRESS4": _clean_text(purchase_request.get("daddress4")),
            "DPOSTCODE": _clean_text(purchase_request.get("dpostcode")),
            "DCITY": _clean_text(purchase_request.get("dcity")),
            "DSTATE": _clean_text(purchase_request.get("dstate")),
            "DCOUNTRY": _clean_text(purchase_request.get("dcountry")),
            "DATTENTION": _clean_text(purchase_request.get("dattention")),
            "DPHONE1": _clean_text(purchase_request.get("dphone1")),
            "DMOBILE": _clean_text(purchase_request.get("dmobile")),
            "DFAX1": _clean_text(purchase_request.get("dfax1")),
            "TAXEXEMPTNO": _clean_text(supplier.get("taxexemptno")),
            "SALESTAXNO": _clean_text(supplier.get("salestaxno")),
            "SERVICETAXNO": _clean_text(supplier.get("servicetaxno")),
            "TIN": _clean_text(supplier.get("tin")),
            "IDTYPE": int(_as_decimal(supplier.get("idtype"), "0")),
            "IDNO": _clean_text(supplier.get("idno")),
            "TOURISMNO": _clean_text(supplier.get("tourismno")),
            "SIC": _clean_text(supplier.get("sic")),
            "INCOTERMS": _clean_text(supplier.get("incoterms")),
            "SUBMISSIONTYPE": int(_as_decimal(supplier.get("submissiontype"), "0")),
            "BUSINESSUNIT": _clean_text(purchase_request.get("businessunit")),
            "TRANSFERABLE": True,
            "UPDATECOUNT": 0,
            "PRINTCOUNT": 0,
            "LASTMODIFIED": int(time.time()),
        }

        _insert_dynamic(cur, "PH_PO", _fit_string_values(header_values, po_header_str_len), po_header_cols)
        for row in detail_inserts:
            _insert_dynamic(cur, "PH_PODTL", _fit_string_values(row, po_detail_str_len), po_detail_cols)
        for row in xtrans_rows:
            _insert_dynamic(cur, "ST_XTRANS", _fit_string_values(row, xtrans_str_len), xtrans_cols)

        con.commit()
        return {
            "poDockey": po_dockey,
            "poNumber": docno,
            "sourceRequestDockey": request_dockey,
            "sourceRequestNumber": request_docno,
            "lineCount": len(detail_inserts),
            "transferredQty": float(sum((line["quantity"] for line in normalized_transfers), Decimal("0"))),
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()