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
    _is_firebird_key_violation,
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


def _detail_is_transferable(
    source: dict[str, Any],
    *,
    override: bool | None = None,
    header_udf_status: str | None = None,
) -> bool:
    """Line may transfer when TRANSFERABLE is true (UI approval checkbox syncs this column)."""
    if override is True:
        return True
    if override is False:
        return False
    if _coerce_bool(source.get("transferable")) or _coerce_bool(source.get("TRANSFERABLE")):
        return True
    if _normalize_udf_status(header_udf_status) == "APPROVED":
        for key in ("udf_pqapproved", "udfPqApproved", "UDF_PQAPPROVED"):
            if key in source and source.get(key) is not None and not _coerce_bool(source.get(key)):
                return False
        return True
    return False


def _transferable_override_map(transfer_lines: list[dict[str, Any]]) -> dict[int, bool]:
    """Optional per-line transferable flags from the View PR transfer payload."""
    out: dict[int, bool] = {}
    for line in transfer_lines:
        if not isinstance(line, dict) or "transferable" not in line:
            continue
        raw_detail_id = line.get("fromdtlkey", line.get("dtlkey", line.get("detailId")))
        try:
            detail_id = int(raw_detail_id)
        except Exception:
            continue
        out[detail_id] = _coerce_bool(line.get("transferable"))
    return out


def _normalize_udf_status(value: Any) -> str:
    text = _clean_text(value).upper()
    if text == "ACTIVE":
        return "APPROVED"
    if text == "INACTIVE":
        return "CANCELLED"
    if text in {"AWAITING", "AWAITING_APPROVAL", "AWAITING APPROVAL"}:
        return "AWAITING"
    if text in {"APPROVED", "CANCELLED", "PENDING", "AWAITING"}:
        return text
    if not text:
        return ""
    return "PENDING"


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


def _allocate_unique_purchase_order_number(
    cur: Any,
    header_columns: set[str],
    *,
    preferred: str = "",
    max_attempts: int = 200,
) -> str:
    """Return an unused PH_PO document number, bumping until free."""
    seed = _clean_text(preferred)
    if seed and not _purchase_order_number_exists(cur, header_columns, seed):
        return seed

    candidate = seed or _next_purchase_order_number(cur, header_columns)
    for _ in range(max_attempts):
        if not _purchase_order_number_exists(cur, header_columns, candidate):
            return candidate
        candidate = _next_purchase_order_number(cur, header_columns)
    raise PurchaseOrderTransferValidationError(
        "could not allocate a unique purchase order document number"
    )


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
    suom_col = _pick_existing(xtrans_columns, "SUOMQTY")

    if not detail_ids or not (fromdoctype_col and fromdockey_col and fromdtlkey_col and (qty_col or sqty_col or suom_col)):
        return {}

    if suom_col and sqty_col and qty_col:
        quantity_expr = (
            f"COALESCE(NULLIF({suom_col}, 0), NULLIF({sqty_col}, 0), COALESCE({qty_col}, 0), 0)"
        )
    elif sqty_col and qty_col:
        quantity_expr = f"COALESCE(NULLIF({sqty_col}, 0), COALESCE({qty_col}, 0), 0)"
    else:
        quantity_expr = suom_col or sqty_col or qty_col
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


def _detail_map_from_request(purchase_request: dict[str, Any]) -> dict[int, dict[str, Any]]:
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
    return detail_map


def _normalize_transfer_line_rows(
    transfer_lines: list[dict[str, Any]],
    detail_map: dict[int, dict[str, Any]],
    *,
    request_dockey: int | None = None,
) -> list[dict[str, Any]]:
    """Normalize transfer payload rows to {detailId, quantity} (+ requestDockey when provided)."""
    normalized: list[dict[str, Any]] = []
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

        row: dict[str, Any] = {"detailId": detail_id, "quantity": quantity}
        if request_dockey is not None:
            row["requestDockey"] = int(request_dockey)
        normalized.append(row)
    return normalized


def _udf_value_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not _clean_text(value):
        return True
    return False


def _apply_podtl_source_udfs(
    detail_values: dict[str, Any],
    detail_cols: set[str],
    source: dict[str, Any],
) -> None:
    """Copy PQ line ``udf_*`` onto PH_PODTL; fill missing T/W/L from BATCH when possible."""
    from utils.sql_api_batch import parse_batch_code_dimensions
    from utils.stock_items_catalog import stock_item_udf_fields_from_row

    for udf_key, val in stock_item_udf_fields_from_row(source).items():
        col = str(udf_key).upper()
        if col not in detail_cols:
            continue
        if col in detail_values and not _udf_value_missing(detail_values.get(col)):
            continue
        detail_values[col] = val

    thickness_col = _pick_existing(detail_cols, "UDF_THICKNESS")
    width_col = _pick_existing(detail_cols, "UDF_WIDTH")
    length_col = _pick_existing(detail_cols, "UDF_LENGTH")
    need_dims = any(
        col and _udf_value_missing(detail_values.get(col))
        for col in (thickness_col, width_col, length_col)
    )
    if not need_dims:
        return

    batch = source.get("batch") if source.get("batch") is not None else source.get("BATCH")
    if batch is None:
        batch = detail_values.get("BATCH")
    t, w, length_s = parse_batch_code_dimensions(batch)
    if not t or not w or not length_s:
        return
    if thickness_col and _udf_value_missing(detail_values.get(thickness_col)):
        detail_values[thickness_col] = t
    if width_col and _udf_value_missing(detail_values.get(width_col)):
        detail_values[width_col] = w
    if length_col and _udf_value_missing(detail_values.get(length_col)):
        detail_values[length_col] = length_s


def _enrich_detail_map_udfs_from_db(
    cur: Any,
    request_dockey: int,
    detail_map: dict[int, dict[str, Any]],
) -> None:
    """Overlay Firebird PH_PQDTL UDF_* onto transfer source rows when missing."""
    if not detail_map:
        return
    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
    udf_cols = sorted(c for c in detail_cols if str(c).upper().startswith("UDF_"))
    if not fk_col or not dtl_col or not udf_cols:
        return

    keys = sorted(detail_map.keys())
    placeholders = ", ".join(["?"] * len(keys))
    select_cols = ", ".join([dtl_col, *udf_cols])
    cur.execute(
        f"""
        SELECT {select_cols}
        FROM PH_PQDTL
        WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
        """,
        tuple([int(request_dockey), *keys]),
    )
    for row in cur.fetchall() or []:
        if not row:
            continue
        try:
            dtlkey = int(row[0])
        except Exception:
            continue
        target = detail_map.get(dtlkey)
        if not isinstance(target, dict):
            continue
        for idx, col in enumerate(udf_cols, start=1):
            val = row[idx]
            if _udf_value_missing(val):
                continue
            key_l = str(col).lower()
            existing = target.get(key_l)
            if existing is None:
                existing = target.get(str(col).upper())
            if not _udf_value_missing(existing):
                continue
            target[key_l] = val


def _build_po_detail_and_xtrans(
    *,
    source: dict[str, Any],
    purchase_request: dict[str, Any],
    request_dockey: int,
    detail_id: int,
    quantity: Decimal,
    already_transferred: Decimal,
    transferable_override: bool | None,
    line_index: int,
    effective_date: str,
    po_dockey: int,
    po_detail_key: int,
    po_detail_key_col: str,
    po_detail_fk_col: str,
    xtrans_key: int,
    xtrans_key_col: str,
    xtrans_cols: set[str],
    supplier_code: str,
    po_status_value: Any,
    po_detail_cols: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Decimal]:
    """Validate one PR line and build PH_PODTL + ST_XTRANS rows. Returns (detail, xtrans, amount)."""
    if not _detail_is_transferable(
        source,
        override=transferable_override,
        header_udf_status=_normalize_udf_status(purchase_request.get("udf_status")),
    ):
        raise PurchaseOrderTransferValidationError(
            f"purchase request detail {detail_id} is not transferable"
        )

    source_qty = _money(_as_decimal(source.get("qty"), "0"))
    if source_qty <= 0:
        raise PurchaseOrderTransferValidationError(
            f"purchase request detail {detail_id} has invalid qty"
        )

    remaining_qty = _money(source_qty - already_transferred)
    if quantity > remaining_qty:
        raise PurchaseOrderTransferValidationError(
            f"transfer quantity exceeds remaining qty for detail {detail_id}"
        )

    unit_price = _money(_as_decimal(source.get("unitprice"), "0"))
    line_tax = Decimal("0")
    source_tax = _money(_as_decimal(source.get("taxamt"), "0"))
    if source_qty > 0 and source_tax != 0:
        line_tax = _money((source_tax / source_qty) * quantity)
    amount = _money((unit_price * quantity) + line_tax)

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
        "QTY": float(quantity),
        "UOM": _clean_text(source.get("uom")) or "UNIT",
        "RATE": float(_as_decimal(source.get("rate"), "1")),
        "SQTY": float(quantity),
        "SUOMQTY": float(
            _money(_as_decimal(source.get("suomqty"), "0"))
            or float(quantity)
        ),
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
        "FROMDTLKEY": detail_id,
        "TRANSFERABLE": True,
        "REMARK1": _clean_text(source.get("remark1")),
        "REMARK2": _clean_text(source.get("remark2")),
    }

    cols = po_detail_cols if isinstance(po_detail_cols, set) else set()
    if cols:
        _apply_podtl_source_udfs(detail_values, cols, source)

    x_row: dict[str, Any] = {
        xtrans_key_col: xtrans_key,
        "CODE": supplier_code,
        "FROMDOCTYPE": "PQ",
        "TODOCTYPE": "PO",
        "FROMDOCKEY": request_dockey,
        "TODOCKEY": po_dockey,
        "FROMDTLKEY": detail_id,
        "TODTLKEY": po_detail_key,
        "QTY": float(quantity),
        "SQTY": float(quantity),
        "TOSTATUS": po_status_value,
    }
    if "SUOMQTY" in xtrans_cols:
        x_row["SUOMQTY"] = float(quantity)
    return detail_values, x_row, amount


def transfer_purchase_request_to_po(
    purchase_request: dict[str, Any],
    transfer_lines: list[dict[str, Any]],
    supplier: dict[str, Any] | None = None,
    created_by: str = "system",
    transfer_date: Any = None,
) -> dict[str, Any]:
    """Create PH_PO, PH_PODTL, and ST_XTRANS rows from approved PR detail lines."""
    return transfer_purchase_requests_to_single_po(
        [{"purchase_request": purchase_request, "transfer_lines": transfer_lines}],
        supplier=supplier,
        created_by=created_by,
        transfer_date=transfer_date,
    )


def transfer_purchase_requests_to_single_po(
    request_groups: list[dict[str, Any]],
    supplier: dict[str, Any] | None = None,
    created_by: str = "system",
    transfer_date: Any = None,
) -> dict[str, Any]:
    """Create one PH_PO whose lines may originate from multiple purchase requests.

    Each entry in request_groups must be:
      { "purchase_request": {...}, "transfer_lines": [...] }
    Lines keep per-PR FROMDOCKEY / FROMDTLKEY on PH_PODTL and ST_XTRANS.
    """
    del created_by  # reserved for audit / future use
    if not isinstance(request_groups, list) or not request_groups:
        raise PurchaseOrderTransferValidationError("request_groups[] is required")
    if supplier is None:
        supplier = {}
    if not isinstance(supplier, dict):
        raise PurchaseOrderTransferValidationError("supplier must be an object")

    prepared_groups: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for group in request_groups:
        if not isinstance(group, dict):
            raise PurchaseOrderTransferValidationError("each request group must be an object")
        purchase_request = group.get("purchase_request")
        transfer_lines = group.get("transfer_lines")
        if not isinstance(purchase_request, dict):
            raise PurchaseOrderTransferValidationError("purchase_request must be an object")
        if not isinstance(transfer_lines, list) or not transfer_lines:
            raise PurchaseOrderTransferValidationError("transfer_lines[] is required")

        try:
            request_dockey = int(purchase_request.get("dockey"))
        except Exception as exc:
            raise PurchaseOrderTransferValidationError("purchase_request.dockey is required") from exc

        request_docno = _clean_text(purchase_request.get("docno")) or f"PQ-{request_dockey}"
        if not _coerce_bool(purchase_request.get("transferable", True)):
            raise PurchaseOrderTransferValidationError(
                f"purchase request {request_docno} is not transferable"
            )
        if _normalize_udf_status(purchase_request.get("udf_status")) != "APPROVED":
            raise PurchaseOrderTransferValidationError(
                f"purchase request {request_docno} UDF status must be APPROVED before transfer"
            )

        detail_map = _detail_map_from_request(purchase_request)
        normalized = _normalize_transfer_line_rows(
            transfer_lines, detail_map, request_dockey=request_dockey
        )
        if not normalized:
            raise PurchaseOrderTransferValidationError(
                f"transfer_lines[] is required for purchase request {request_docno}"
            )
        for line in normalized:
            pair = (request_dockey, int(line["detailId"]))
            if pair in seen_pairs:
                raise PurchaseOrderTransferValidationError(
                    f"duplicate transfer line for request {request_dockey} detail {line['detailId']}"
                )
            seen_pairs.add(pair)

        prepared_groups.append(
            {
                "purchase_request": purchase_request,
                "request_dockey": request_dockey,
                "request_docno": request_docno,
                "detail_map": detail_map,
                "normalized_transfers": normalized,
                "transferable_overrides": _transferable_override_map(transfer_lines),
            }
        )

    # Primary PR (lowest dockey) supplies header-only fields like PROJECT/AREA.
    prepared_groups.sort(key=lambda g: int(g["request_dockey"]))
    primary = prepared_groups[0]
    primary_request = primary["purchase_request"]
    source_request_dockeys = [int(g["request_dockey"]) for g in prepared_groups]
    source_request_numbers = [str(g["request_docno"]) for g in prepared_groups]

    supplier_code = _clean_text(
        supplier.get("code")
        or supplier.get("supplierId")
        or primary_request.get("code")
        or primary_request.get("supplierid")
        or primary_request.get("agent")
    )
    supplier_name = _clean_text(
        supplier.get("companyname")
        or supplier.get("companyName")
        or primary_request.get("companyname")
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

        existing_qty_by_request: dict[int, dict[int, Decimal]] = {}
        for group in prepared_groups:
            dockey = int(group["request_dockey"])
            detail_ids = [int(line["detailId"]) for line in group["normalized_transfers"]]
            existing_qty_by_request[dockey] = _fetch_existing_transfer_qty_map(
                cur, dockey, detail_ids, xtrans_cols
            )

        po_header_gens = ["PH_PO", "GEN_PH_PO_ID", "GEN_PH_PO_DOCKEY", "GEN_PH_PO", "SEQ_PH_PO_DOCKEY"]
        po_detail_gens = ["PH_PODTL", "GEN_PH_PODTL_ID", "GEN_PH_PODTL_DTLKEY", "GEN_PH_PODTL", "SEQ_PH_PODTL_DTLKEY"]
        xtrans_gens = ["ST_XTRANS", "GEN_ST_XTRANS_ID", "GEN_ST_XTRANS_DOCKEY", "GEN_ST_XTRANS", "SEQ_ST_XTRANS_DOCKEY"]
        docno = _allocate_unique_purchase_order_number(
            cur,
            po_header_cols,
            preferred=_clean_text(supplier.get("docno") or supplier.get("poNumber") or ""),
        )

        po_dockey = _next_key(cur, "PH_PO", po_header_key_col, po_header_gens)

        status_is_numeric = bool(po_status_col and _column_is_numeric(cur, "PH_PO", po_status_col))
        po_status_value = _encode_status("DRAFT", status_is_numeric)
        effective_date = _normalize_transfer_date(transfer_date or primary_request.get("docdate"))
        total_doc_amount = Decimal("0")
        transferred_qty_total = Decimal("0")
        detail_inserts: list[dict[str, Any]] = []
        xtrans_rows: list[dict[str, Any]] = []

        line_index = 0
        for group in prepared_groups:
            purchase_request = group["purchase_request"]
            request_dockey = int(group["request_dockey"])
            detail_map = group["detail_map"]
            transferable_overrides = group["transferable_overrides"]
            existing_qty_map = existing_qty_by_request.get(request_dockey) or {}
            try:
                _enrich_detail_map_udfs_from_db(cur, request_dockey, detail_map)
            except Exception as enrich_exc:
                print(
                    f"[PROCUREMENT PO TRANSFER] UDF enrich skipped for PQ {request_dockey}: {enrich_exc}",
                    flush=True,
                )

            for line in group["normalized_transfers"]:
                line_index += 1
                detail_id = int(line["detailId"])
                quantity = line["quantity"]
                transferred_qty_total += quantity

                po_detail_key = _next_key(cur, "PH_PODTL", po_detail_key_col, po_detail_gens)
                xtrans_key = _next_key(cur, "ST_XTRANS", xtrans_key_col, xtrans_gens)
                detail_values, x_row, amount = _build_po_detail_and_xtrans(
                    source=detail_map[detail_id],
                    purchase_request=purchase_request,
                    request_dockey=request_dockey,
                    detail_id=detail_id,
                    quantity=quantity,
                    already_transferred=_money(
                        _as_decimal(existing_qty_map.get(detail_id, Decimal("0")), "0")
                    ),
                    transferable_override=transferable_overrides.get(detail_id),
                    line_index=line_index,
                    effective_date=effective_date,
                    po_dockey=po_dockey,
                    po_detail_key=po_detail_key,
                    po_detail_key_col=po_detail_key_col,
                    po_detail_fk_col=po_detail_fk_col,
                    xtrans_key=xtrans_key,
                    xtrans_key_col=xtrans_key_col,
                    xtrans_cols=xtrans_cols,
                    supplier_code=supplier_code,
                    po_status_value=po_status_value,
                    po_detail_cols=po_detail_cols,
                )
                total_doc_amount += amount
                detail_inserts.append(detail_values)
                xtrans_rows.append(x_row)

        if not detail_inserts:
            raise PurchaseOrderTransferValidationError("No transferable lines found")

        description = _clean_text(supplier.get("description"))
        if not description:
            if len(source_request_numbers) == 1:
                description = f"Purchase Order - {source_request_numbers[0]}"
            else:
                joined = ", ".join(source_request_numbers)
                description = f"Purchase Order - {joined}"

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
            "AREA": _clean_text(primary_request.get("area")) or "----",
            "AGENT": supplier_code,
            "PROJECT": _clean_text(primary_request.get("project")) or "----",
            "TERMS": _clean_text(supplier.get("terms")),
            "CURRENCYCODE": supplier_currency_code or _clean_text(primary_request.get("currencycode")) or "MYR",
            "CURRENCYRATE": float(
                _as_decimal(
                    supplier_currency_rate_raw
                    if supplier_currency_rate_raw is not None
                    else primary_request.get("currencyrate"),
                    "1",
                )
            ),
            "SHIPPER": _clean_text(primary_request.get("shipper")) or "----",
            "DESCRIPTION": description,
            "CANCELLED": False,
            "STATUS": po_status_value,
            "DOCAMT": float(_money(total_doc_amount)),
            "LOCALDOCAMT": float(_money(total_doc_amount)),
            "BRANCHNAME": _clean_text(supplier.get("branchname")),
            "DADDRESS1": _clean_text(supplier.get("daddress1") or supplier.get("address1")),
            "DADDRESS2": _clean_text(supplier.get("daddress2") or supplier.get("address2")),
            "DADDRESS3": _clean_text(supplier.get("daddress3") or supplier.get("address3")),
            "DADDRESS4": _clean_text(supplier.get("daddress4") or supplier.get("address4")),
            "DPOSTCODE": _clean_text(supplier.get("dpostcode") or supplier.get("postcode")),
            "DCITY": _clean_text(supplier.get("dcity") or supplier.get("city")),
            "DSTATE": _clean_text(supplier.get("dstate") or supplier.get("state")),
            "DCOUNTRY": _clean_text(supplier.get("dcountry") or supplier.get("country")),
            "DATTENTION": _clean_text(supplier.get("dattention") or supplier.get("attention")),
            "DPHONE1": _clean_text(supplier.get("dphone1") or supplier.get("phone1")),
            "DMOBILE": _clean_text(supplier.get("dmobile") or supplier.get("mobile")),
            "DFAX1": _clean_text(supplier.get("dfax1") or supplier.get("fax1")),
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
            "BUSINESSUNIT": _clean_text(primary_request.get("businessunit")),
            "TRANSFERABLE": True,
            "UPDATECOUNT": 0,
            "PRINTCOUNT": 0,
            "LASTMODIFIED": int(time.time()),
        }

        last_insert_exc: BaseException | None = None
        for insert_attempt in range(12):
            if insert_attempt > 0:
                # Concurrent SQL Accounting insert collided — refresh all keys + DOCNO.
                po_dockey = _next_key(cur, "PH_PO", po_header_key_col, po_header_gens)
                docno = _allocate_unique_purchase_order_number(cur, po_header_cols, preferred=docno)
                header_values[po_header_key_col] = po_dockey
                header_values["DOCNO"] = docno
                header_values["DOCNOEX"] = docno
                for detail_row, x_row in zip(detail_inserts, xtrans_rows):
                    po_detail_key = _next_key(cur, "PH_PODTL", po_detail_key_col, po_detail_gens)
                    detail_row[po_detail_key_col] = po_detail_key
                    detail_row[po_detail_fk_col] = po_dockey
                    x_row[xtrans_key_col] = _next_key(cur, "ST_XTRANS", xtrans_key_col, xtrans_gens)
                    x_row["TODOCKEY"] = po_dockey
                    x_row["TODTLKEY"] = po_detail_key
            try:
                _insert_dynamic(
                    cur, "PH_PO", _fit_string_values(header_values, po_header_str_len), po_header_cols
                )
                for row in detail_inserts:
                    _insert_dynamic(
                        cur, "PH_PODTL", _fit_string_values(row, po_detail_str_len), po_detail_cols
                    )
                for row in xtrans_rows:
                    _insert_dynamic(
                        cur, "ST_XTRANS", _fit_string_values(row, xtrans_str_len), xtrans_cols
                    )
                break
            except Exception as exc:
                if not _is_firebird_key_violation(exc):
                    raise
                last_insert_exc = exc
                print(
                    f"[PROCUREMENT PO TRANSFER] KEY VIOLATION on PO insert "
                    f"(attempt {insert_attempt + 1}/12): {exc}",
                    flush=True,
                )
                try:
                    con.rollback()
                except Exception:
                    pass
        else:
            raise RuntimeError(
                "KEY VIOLATION inserting purchase order after 12 attempts"
            ) from last_insert_exc

        con.commit()

        sql_po_sync: dict[str, Any] = {"skipped": True}
        try:
            from utils.procurement_sql_api_sync import sync_purchase_order_supplier_sql_api

            sql_po_sync = sync_purchase_order_supplier_sql_api(
                int(po_dockey),
                supplier_code,
                po_number=docno,
            )
        except Exception as sync_exc:
            print(f"[PROCUREMENT PO TRANSFER] SQL API purchaseorder PUT warning: {sync_exc}", flush=True)
            sql_po_sync = {"synced": False, "error": str(sync_exc)}

        return {
            "poDockey": po_dockey,
            "poNumber": docno,
            "sourceRequestDockey": source_request_dockeys[0],
            "sourceRequestNumber": source_request_numbers[0],
            "sourceRequestDockeys": source_request_dockeys,
            "sourceRequestNumbers": source_request_numbers,
            "lineCount": len(detail_inserts),
            "transferredQty": float(transferred_qty_total),
            "sqlPurchaseOrderSync": sql_po_sync,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()