"""Purchase request service for eProcurement create flow."""
from __future__ import annotations

import time
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import requests

from utils.db_utils import get_db_connection


class PurchaseRequestValidationError(ValueError):
    """Raised when purchase request payload fails validation."""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _as_date(value: Any) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _connect_db():
    return get_db_connection()


def _get_table_columns(cur: Any, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE RF.RDB$RELATION_NAME = ?
        """,
        (table_name.upper(),),
    )
    return {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}


def _column_is_numeric(cur: Any, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT F.RDB$FIELD_TYPE
        FROM RDB$RELATION_FIELDS RF
        JOIN RDB$FIELDS F ON RF.RDB$FIELD_SOURCE = F.RDB$FIELD_NAME
        WHERE RF.RDB$RELATION_NAME = ? AND RF.RDB$FIELD_NAME = ?
        """,
        (table_name.upper(), column_name.upper()),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return False

    # Firebird numeric family: SMALLINT(7), INTEGER/LONG(8), BIGINT(16), NUMERIC/DECIMAL(27)
    return int(row[0]) in {7, 8, 16, 27}


def _encode_status(status: str, numeric_target: bool) -> Any:
    if not numeric_target:
        return status
    mapping = {
        "DRAFT": 0,
        "SUBMITTED": 1,
        "APPROVED": 2,
        "REJECTED": 3,
        "CANCELLED": 4,
    }
    return mapping.get(status, 0)


def _decode_status(raw_status: Any) -> str:
    text = _clean_text(raw_status).upper()
    if text in {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "CANCELLED"}:
        return text
    try:
        numeric = int(raw_status)
    except Exception:
        return text or ""
    reverse = {
        0: "DRAFT",
        1: "SUBMITTED",
        2: "APPROVED",
        3: "REJECTED",
        4: "CANCELLED",
    }
    return reverse.get(numeric, str(numeric))


def _pick_existing(columns: set[str], *candidates: str) -> str:
    for name in candidates:
        if name.upper() in columns:
            return name.upper()
    return ""


def _normalize_stock_qty_uom(value: Any) -> str:
    u = _clean_text(value).upper()
    if u in ("SQTY", "SUOMQTY"):
        return u
    return "SUOMQTY"


def _apply_pqdtl_sqty_suom_columns(
    detail_values: dict[str, Any],
    detail_cols: set[str],
    quantity: float,
    stock_qty_uom: str,
) -> None:
    """Align PH_PQDTL SQTY/SUOMQTY with the stock-card basis used for the line (SQ vs SUOM)."""
    uom = _normalize_stock_qty_uom(stock_qty_uom)
    sqty_c = _pick_existing(detail_cols, "SQTY")
    suom_c = _pick_existing(detail_cols, "SUOMQTY")
    if not sqty_c and not suom_c:
        return
    q = float(quantity)
    if uom == "SUOMQTY":
        if suom_c:
            detail_values[suom_c] = q
        if sqty_c:
            detail_values[sqty_c] = 0.0
    else:
        if sqty_c:
            detail_values[sqty_c] = q
        if suom_c:
            detail_values[suom_c] = 0.0


def _append_pqdtl_sqty_suom_update(
    line_updates: list[str],
    line_values: list[Any],
    detail_cols: set[str],
    quantity: float,
    stock_qty_uom: str,
) -> None:
    uom = _normalize_stock_qty_uom(stock_qty_uom)
    sqty_c = _pick_existing(detail_cols, "SQTY")
    suom_c = _pick_existing(detail_cols, "SUOMQTY")
    if not sqty_c and not suom_c:
        return
    q = float(quantity)
    if uom == "SUOMQTY":
        if suom_c:
            line_updates.append(f"{suom_c} = ?")
            line_values.append(q)
        if sqty_c:
            line_updates.append(f"{sqty_c} = ?")
            line_values.append(0.0)
    else:
        if sqty_c:
            line_updates.append(f"{sqty_c} = ?")
            line_values.append(q)
        if suom_c:
            line_updates.append(f"{suom_c} = ?")
            line_values.append(0.0)


def _next_key(cur: Any, table_name: str, key_column: str, generator_candidates: list[str]) -> int:
    for generator_name in generator_candidates:
        try:
            cur.execute(f"SELECT GEN_ID({generator_name}, 1) FROM RDB$DATABASE")
            row = cur.fetchone()
            if row and row[0] is not None:
                return int(row[0])
        except Exception:
            continue

    cur.execute(f"SELECT COALESCE(MAX({key_column}), 0) + 1 FROM {table_name}")
    row = cur.fetchone()
    return int(row[0] if row and row[0] is not None else 1)


def _insert_dynamic(cur: Any, table_name: str, data: dict[str, Any], existing_columns: set[str]) -> None:
    filtered: list[tuple[str, Any]] = []
    for col, value in data.items():
        col_name = col.upper()
        if col_name in existing_columns:
            filtered.append((col_name, value))

    if not filtered:
        raise RuntimeError(f"No matching columns found for insert into {table_name}")

    columns = ", ".join(col for col, _ in filtered)
    placeholders = ", ".join(["?"] * len(filtered))
    values = tuple(value for _, value in filtered)
    cur.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})", values)


def ensure_purchase_request_schema() -> None:
    """Verify existing PR tables are present. This function does not create tables."""
    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        if not header_cols:
            raise RuntimeError("PH_PQ table not found")
        if not detail_cols:
            raise RuntimeError("PH_PQDTL table not found")
    finally:
        con.close()


def _next_request_number(cur: Any, header_columns: set[str]) -> str:
    request_no_col = _pick_existing(
        header_columns,
        "DOCNO",
        "REQUESTNO",
        "PRNO",
        "PURCHASEREQUESTNO",
    )

    prefix = f"PR-{datetime.utcnow().strftime('%y%m')}"
    if not request_no_col:
        return f"{prefix}0001"

    cur.execute(
        f"""
        SELECT FIRST 1 {request_no_col}
        FROM PH_PQ
        WHERE {request_no_col} LIKE ?
        ORDER BY {request_no_col} DESC
        """,
        (f"{prefix}%",),
    )
    row = cur.fetchone()
    if not row:
        return f"{prefix}0001"

    last = _clean_text(row[0])
    try:
        seq = int(last[-4:]) + 1
    except Exception:
        seq = 1
    return f"{prefix}{seq:04d}"


def _request_number_exists(cur: Any, header_columns: set[str], request_number: str) -> bool:
    request_no_col = _pick_existing(
        header_columns,
        "DOCNO",
        "REQUESTNO",
        "PRNO",
        "PURCHASEREQUESTNO",
    )
    if not request_no_col or not request_number:
        return False

    cur.execute(
        f"SELECT FIRST 1 {request_no_col} FROM PH_PQ WHERE {request_no_col} = ?",
        (request_number,),
    )
    return cur.fetchone() is not None


def _next_request_number_from_seed(cur: Any, header_columns: set[str], seed: str) -> str:
    request_no_col = _pick_existing(
        header_columns,
        "DOCNO",
        "REQUESTNO",
        "PRNO",
        "PURCHASEREQUESTNO",
    )
    seed_text = _clean_text(seed)
    if not request_no_col or not seed_text:
        return _next_request_number(cur, header_columns)

    match = re.match(r"^(.*?)(\d+)$", seed_text)
    if not match:
        return _next_request_number(cur, header_columns)

    prefix = match.group(1)
    width = len(match.group(2))
    cur.execute(
        f"""
        SELECT FIRST 1 {request_no_col}
        FROM PH_PQ
        WHERE {request_no_col} LIKE ?
        ORDER BY {request_no_col} DESC
        """,
        (f"{prefix}%",),
    )
    row = cur.fetchone()
    if row and row[0]:
        text = _clean_text(row[0])
        hit = re.match(rf"^{re.escape(prefix)}(\d+)$", text)
        if hit:
            next_num = int(hit.group(1)) + 1
            return f"{prefix}{next_num:0{width}d}"

    return f"{prefix}{1:0{width}d}"


def _normalize_sql_api_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    header_project = _clean_text(payload.get("project")) or "----"

    request_number = _clean_text(payload.get("docno") or payload.get("requestNumber"))
    request_date_raw = _clean_text(payload.get("docdate") or payload.get("requestDate"))
    required_date_raw = _clean_text(payload.get("postdate") or payload.get("requiredDate"))

    request_date = _as_date(request_date_raw)
    required_date = _as_date(required_date_raw)
    if not request_date:
        request_date = datetime.utcnow().date()
    if not required_date:
        required_date = request_date

    details = payload.get("sdsdocdetail")
    if not isinstance(details, list):
        details = payload.get("lineItems")
    if not isinstance(details, list) or not details:
        errors.append("At least one detail row is required in sdsdocdetail")
        details = []

    normalized_items: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    total_tax = Decimal("0")

    for idx, item in enumerate(details, start=1):
        if not isinstance(item, dict):
            errors.append(f"sdsdocdetail[{idx}] must be an object")
            continue

        item_code = _clean_text(item.get("itemcode") or item.get("itemCode")) or f"LINE-{idx:03d}"
        location_code = _clean_text(item.get("location") or item.get("locationCode") or item.get("loc"))
        item_name = (
            _clean_text(item.get("description") or item.get("itemName") or item.get("description2"))
            or f"Line {idx}"
        )
        description = _clean_text(item.get("description3") or item.get("description") or item_name)
        line_project = _clean_text(item.get("project")) or header_project

        quantity = _as_decimal(item.get("qty") if item.get("qty") is not None else item.get("quantity"), "0")
        unit_price = _as_decimal(item.get("unitprice") if item.get("unitprice") is not None else item.get("unitPrice"), "0")
        tax = _as_decimal(item.get("taxamt") if item.get("taxamt") is not None else item.get("tax"), "0")
        delivery_date_raw = _clean_text(item.get("deliverydate") or item.get("deliveryDate"))
        delivery_date = _as_date(delivery_date_raw)

        if quantity < 0:
            errors.append(f"sdsdocdetail[{idx}].qty must be >= 0")
        if unit_price < 0:
            errors.append(f"sdsdocdetail[{idx}].unitprice must be >= 0")
        if tax < 0:
            errors.append(f"sdsdocdetail[{idx}].taxamt must be >= 0")
        if delivery_date_raw and not delivery_date:
            errors.append(f"sdsdocdetail[{idx}].deliverydate must be YYYY-MM-DD")

        effective_delivery_date = delivery_date or required_date or request_date

        amount_source = item.get("amount")
        if amount_source is None:
            amount_source = item.get("localamount")
        line_amount = _money(_as_decimal(amount_source, str((quantity * unit_price) + tax)))

        subtotal += _money(quantity * unit_price)
        total_tax += _money(tax)

        normalized_items.append(
            {
                "itemCode": item_code,
                "itemName": item_name,
                "locationCode": location_code,
                "description": description,
                "udfReason": _clean_text(item.get("udfReason") or item.get("udf_reason")),
                "project": line_project,
                "quantity": float(quantity),
                "unitPrice": float(_money(unit_price)),
                "tax": float(_money(tax)),
                "amount": float(line_amount),
                "deliveryDate": effective_delivery_date.isoformat() if effective_delivery_date else "",
                "stockQtyUom": _normalize_stock_qty_uom(
                    item.get("stockQtyUom") or item.get("stock_qty_uom") or "SUOMQTY"
                ),
            }
        )

    computed_total = _money(subtotal + total_tax)
    provided_total = _money(_as_decimal(payload.get("docamt"), str(computed_total)))
    if abs(provided_total - computed_total) > Decimal("0.01"):
        errors.append("docamt must equal sum of detail amounts")

    raw_status = payload.get("status")
    status = _decode_status(raw_status).upper() if raw_status is not None else ""
    if status and status not in {"DRAFT", "SUBMITTED"}:
        errors.append("status must be DRAFT/SUBMITTED or 0/1 for create")

    if errors:
        raise PurchaseRequestValidationError("; ".join(errors))

    return {
        "requestNumber": request_number,
        "requesterId": _clean_text(payload.get("code")) or "SYSTEM",
        "departmentId": _clean_text(payload.get("businessunit")) or "PROC",
        "costCenter": _clean_text(payload.get("businessunit")),
        "project": header_project,
        "supplierId": _clean_text(payload.get("agent")),
        "currency": _clean_text(payload.get("currencycode")) or "MYR",
        "requestDate": request_date.isoformat(),
        "requiredDate": required_date.isoformat(),
        "description": _clean_text(payload.get("description")),
        "justification": _clean_text(payload.get("justification")) or _clean_text(payload.get("description")),
        "deliveryLocation": _clean_text(payload.get("daddress1") or payload.get("address1")),
        "notes": _clean_text(payload.get("note")),
        "subtotalAmount": float(_money(subtotal)),
        "taxAmount": float(_money(total_tax)),
        "totalAmount": float(computed_total),
        "status": status,
        "lineItems": normalized_items,
        "sqlPayload": payload,
    }


def _validate_and_normalize(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("sdsdocdetail"), list):
        return _normalize_sql_api_payload(payload)

    errors: list[str] = []
    header_project = _clean_text(payload.get("project")) or "----"

    requester_id = _clean_text(payload.get("requesterId"))

    department_id = _clean_text(payload.get("departmentId"))

    currency = _clean_text(payload.get("currency")) or "MYR"

    # requestDate is the user-facing field; keep requestedDate as a compatibility alias.
    request_date_raw = _clean_text(payload.get("requestDate") or payload.get("requestedDate"))

    # requiredDate is not user-facing; default it to requestDate when missing.
    required_date_raw = _clean_text(payload.get("requiredDate"))

    request_date = _as_date(request_date_raw)
    required_date = _as_date(required_date_raw)

    # If requestDate is omitted (UI auto-sets), default to today's date.
    if request_date_raw and not request_date:
        errors.append("requestDate must be YYYY-MM-DD")
    if not request_date:
        request_date = datetime.utcnow().date()

    # requiredDate is an internal downstream field; ignore malformed legacy values.
    if required_date_raw and not required_date:
        required_date = request_date
    if not required_date:
        required_date = request_date

    if required_date < request_date:
        errors.append("requiredDate cannot be before requestDate")

    raw_status = payload.get("status")
    if isinstance(raw_status, (int, float)):
        pr_status = _clean_text(_decode_status(int(raw_status))).upper()
    else:
        pr_status = _clean_text(raw_status).upper() if raw_status is not None else ""
    if not pr_status:
        pr_status = "DRAFT"

    items = payload.get("lineItems")
    if not isinstance(items, list) or not items:
        errors.append("At least one line item is required")
        items = []

    normalized_items: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    total_tax = Decimal("0")

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"lineItems[{idx}] must be an object")
            continue

        item_code = _clean_text(item.get("itemCode"))
        location_code = _clean_text(item.get("locationCode") or item.get("location") or item.get("loc"))
        item_name = _clean_text(item.get("itemName"))
        description = _clean_text(item.get("description"))
        line_project = _clean_text(item.get("project")) or header_project

        if not item_code:
            errors.append(f"lineItems[{idx}].itemCode is required")
        if not item_name:
            errors.append(f"lineItems[{idx}].itemName is required")

        quantity = _as_decimal(item.get("quantity"))
        unit_price = _as_decimal(item.get("unitPrice"))
        tax = _as_decimal(item.get("tax"))
        delivery_date_raw = _clean_text(item.get("deliveryDate") or item.get("deliverydate"))
        delivery_date = _as_date(delivery_date_raw)

        if quantity < 0:
            errors.append(f"lineItems[{idx}].quantity must be >= 0")
        if quantity <= 0 and pr_status == "SUBMITTED":
            errors.append(f"lineItems[{idx}].quantity must be > 0 when submitting")
        if unit_price < 0:
            errors.append(f"lineItems[{idx}].unitPrice must be >= 0")
        if tax < 0:
            errors.append(f"lineItems[{idx}].tax must be >= 0")
        if delivery_date_raw and not delivery_date:
            errors.append(f"lineItems[{idx}].deliveryDate must be YYYY-MM-DD")

        effective_delivery_date = delivery_date or required_date

        line_amount = _money((quantity * unit_price) + tax)

        subtotal += _money(quantity * unit_price)
        total_tax += _money(tax)

        normalized_items.append(
            {
                "itemCode": item_code,
                "itemName": item_name,
                "locationCode": location_code,
                "description": description,
                "udfReason": _clean_text(item.get("udfReason") or item.get("udf_reason")),
                "project": line_project,
                "quantity": float(quantity),
                "unitPrice": float(_money(unit_price)),
                "tax": float(_money(tax)),
                "amount": float(line_amount),
                "deliveryDate": effective_delivery_date.isoformat() if effective_delivery_date else "",
                "stockQtyUom": _normalize_stock_qty_uom(
                    item.get("stockQtyUom") or item.get("stock_qty_uom") or "SUOMQTY"
                ),
            }
        )

    computed_total = _money(subtotal + total_tax)
    provided_total = _money(_as_decimal(payload.get("totalAmount"), str(computed_total)))

    if abs(provided_total - computed_total) > Decimal("0.01"):
        errors.append("totalAmount must equal sum of line items plus taxes")

    request_number = _clean_text(payload.get("requestNumber"))
    status = pr_status
    if status and status not in {"DRAFT", "SUBMITTED"}:
        errors.append("status must be DRAFT or SUBMITTED for create")

    if errors:
        raise PurchaseRequestValidationError("; ".join(errors))

    return {
        "requestNumber": request_number,
        "requesterId": requester_id,
        "departmentId": department_id,
        "costCenter": _clean_text(payload.get("costCenter")),
        "project": header_project,
        "supplierId": _clean_text(payload.get("supplierId")),
        "supplierName": _clean_text(payload.get("supplierName")),
        "currency": currency,
        "requestDate": request_date.isoformat() if request_date else request_date_raw,
        "requiredDate": required_date.isoformat() if required_date else required_date_raw,
        "description": _clean_text(payload.get("description")),
        "justification": _clean_text(payload.get("justification")),
        "deliveryLocation": _clean_text(payload.get("deliveryLocation")),
        "notes": _clean_text(payload.get("notes")),
        "subtotalAmount": float(_money(subtotal)),
        "taxAmount": float(_money(total_tax)),
        "totalAmount": float(computed_total),
        "status": status,
        "lineItems": normalized_items,
    }


def _resolve_initial_status(payload_status: str) -> str:
    return payload_status or "DRAFT"


def _build_upstream_payload(validated: dict[str, Any]) -> dict[str, Any]:
    source_sql_payload = validated.get("sqlPayload")
    if isinstance(source_sql_payload, dict):
        payload = dict(source_sql_payload)
        payload["sdsdocdetail"] = [dict(row) for row in (source_sql_payload.get("sdsdocdetail") or [])]
        request_date = _clean_text(payload.get("requestDate") or payload.get("requestedDate") or payload.get("docdate"))
        if request_date:
            payload["requestDate"] = request_date
            payload["requestedDate"] = request_date
            payload["docdate"] = request_date
            payload["postdate"] = request_date
            # Upstream still validates requiredDate; mirror it from requested date.
            payload["requiredDate"] = request_date
        return payload

    payload = dict(validated)
    payload["lineItems"] = [dict(item) for item in validated.get("lineItems", [])]
    request_date = _clean_text(payload.get("requestDate") or payload.get("requestedDate"))
    if request_date:
        payload["requestDate"] = request_date
        payload["requestedDate"] = request_date
        # Keep legacy SQL-style aliases aligned with requested date.
        payload["docdate"] = request_date
        payload["postdate"] = request_date
        # Upstream still validates requiredDate; mirror it from requested date.
        payload["requiredDate"] = request_date
    return payload


def _forward_to_upstream(payload: dict[str, Any], auth_header: str | None) -> tuple[str, str]:
    upstream_url = _clean_text(os.getenv("PROCUREMENT_CREATE_PR_URL"))
    if not upstream_url:
        return ("SKIPPED", "")

    timeout_seconds = int(_clean_text(os.getenv("PROCUREMENT_UPSTREAM_TIMEOUT", "8")) or "8")
    max_attempts = int(_clean_text(os.getenv("PROCUREMENT_UPSTREAM_RETRY", "2")) or "2")
    max_attempts = max(0, max_attempts)

    headers = {
        "Content-Type": "application/json",
    }
    service_token = _clean_text(os.getenv("PROCUREMENT_UPSTREAM_TOKEN"))
    if service_token:
        headers["Authorization"] = f"Bearer {service_token}"
    elif auth_header:
        headers["Authorization"] = auth_header

    last_error = ""
    for attempt in range(max_attempts + 1):
        try:
            response = requests.post(
                upstream_url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
            if 200 <= response.status_code < 300:
                try:
                    body = response.json() if response.text else {}
                except Exception:
                    body = {}
                ref = _clean_text(body.get("requestNumber") if isinstance(body, dict) else "")
                if not ref:
                    ref = _clean_text(body.get("id") if isinstance(body, dict) else "")
                return ("SENT", ref)

            if response.status_code >= 500 and attempt < max_attempts:
                time.sleep(0.4 * (attempt + 1))
                continue

            preview = (response.text or "").strip()[:300]
            raise RuntimeError(f"Upstream returned HTTP {response.status_code}: {preview}")
        except Exception as exc:
            last_error = str(exc)
            if attempt >= max_attempts:
                break
            time.sleep(0.4 * (attempt + 1))

    raise RuntimeError(last_error or "Failed to send purchase request to upstream API")


def create_purchase_request(
    payload: dict[str, Any],
    created_by: str,
    auth_header: str | None = None,
) -> dict[str, Any]:
    """Validate, persist, and optionally forward a purchase request."""
    ensure_purchase_request_schema()
    validated = _validate_and_normalize(payload)
    normalized_actor = _clean_text(created_by) or "system"
    now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    now_date = datetime.utcnow().date()

    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        detail_cols = _get_table_columns(cur, "PH_PQDTL")

        request_number = validated.get("requestNumber") or _next_request_number(cur, header_cols)
        if _request_number_exists(cur, header_cols, request_number):
            request_number = _next_request_number_from_seed(cur, header_cols, request_number)
        status = _resolve_initial_status(validated.get("status") or "")

        header_key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        detail_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        detail_fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
        detail_seq_col = _pick_existing(detail_cols, "SEQ", "LINE_NO", "LINENO")
        detail_location_col = _pick_existing(detail_cols, "LOCATION", "LOC", "STOCKLOCATION", "STORELOCATION")

        if not header_key_col:
            raise RuntimeError("PH_PQ primary key column not found (expected DOCKEY/PQKEY/ID)")
        if not detail_fk_col:
            raise RuntimeError("PH_PQDTL foreign key column not found (expected DOCKEY/PQKEY/REQUEST_ID/HEADER_ID)")

        header_id = _next_key(
            cur,
            "PH_PQ",
            header_key_col,
            ["GEN_PH_PQ_ID", "GEN_PH_PQ_DOCKEY", "GEN_PH_PQ", "SEQ_PH_PQ_DOCKEY"],
        )

        upstream_status = "PENDING"
        upstream_reference = ""
        status_col = _pick_existing(header_cols, "STATUS")
        status_is_numeric = bool(status_col and _column_is_numeric(cur, "PH_PQ", status_col))

        header_values = {
            header_key_col: header_id,
            "DOCNO": request_number,
            "DOCNOEX": request_number,
            "REQUESTNO": request_number,
            "PRNO": request_number,
            "DOCDATE": validated["requestDate"] or now_date,
            "POSTDATE": validated["requestDate"] or now_date,
            "TAXDATE": validated["requestDate"] or now_date,
            "REQUESTDATE": validated["requestDate"] or now_date,
            "REQUIREDDATE": validated["requiredDate"],
            "CODE": validated["supplierId"],
            "COMPANYNAME": validated.get("supplierName") or "",
            "DEPARTMENTID": validated["departmentId"],
            "COSTCENTER": validated["costCenter"],
            "PROJECT": validated.get("project", ""),
            "SUPPLIERID": validated["supplierId"],
            "SHIPPER": "----",
            "CURRENCYCODE": validated["currency"],
            "CURRENCY": validated["currency"],
            "CURRENCYRATE": 1,
            "DESCRIPTION": validated.get("description") or "",
            "JUSTIFICATION": validated["justification"],
            "DELIVERYLOCATION": validated["deliveryLocation"],
            "NOTES": validated["notes"],
            "SUBTOTAL": validated["subtotalAmount"],
            "SUBTOTALAMT": validated["subtotalAmount"],
            "TAXAMT": validated["taxAmount"],
            "DOCAMT": validated["totalAmount"],
            "TOTALAMT": validated["totalAmount"],
            "TOTAL_AMOUNT": validated["totalAmount"],
            "STATUS": _encode_status(status, status_is_numeric),
            "UDF_STATUS": "PENDING" if status == "SUBMITTED" else "",
            "UDFSTATUS": "PENDING" if status == "SUBMITTED" else "",
            "UPSTREAM_STATUS": upstream_status,
            "UPSTREAM_REFERENCE": upstream_reference,
            "CREATEDBY": normalized_actor,
            "CREATED_AT": now_iso,
            "UPDATEDBY": normalized_actor,
            "UPDATED_AT": now_iso,
        }
        _insert_dynamic(cur, "PH_PQ", header_values, header_cols)

        for idx, item in enumerate(validated["lineItems"], start=1):
            line_location = _clean_text(item.get("locationCode"))
            detail_values = {
                detail_fk_col: header_id,
                detail_seq_col: idx if detail_seq_col else None,
                "ITEMCODE": item["itemCode"],
                "ITEMNAME": item["itemName"],
                detail_location_col: line_location if detail_location_col else None,
                "LOCATION": line_location,
                "LOC": line_location,
                "STOCKLOCATION": line_location,
                "STORELOCATION": line_location,
                "PROJECT": item.get("project") or validated.get("project", ""),
                "DESCRIPTION": item["description"] or item["itemName"],
                "UDF_REASON": item.get("udfReason") or "",
                "QTY": item["quantity"],
                "QUANTITY": item["quantity"],
                "UNITPRICE": item["unitPrice"],
                "DISC": 0,
                "TAX": item["tax"],
                "DELIVERYDATE": item.get("deliveryDate") or validated["requiredDate"],
                "DELIVERY_DATE": item.get("deliveryDate") or validated["requiredDate"],
                "AMOUNT": item["amount"],
                "TOTAL": item["amount"],
                "CREATED_AT": now_iso,
            }
            if detail_key_col:
                detail_values[detail_key_col] = _next_key(
                    cur,
                    "PH_PQDTL",
                    detail_key_col,
                    ["GEN_PH_PQDTL_ID", "GEN_PH_PQDTL_DTLKEY", "GEN_PH_PQDTL", "SEQ_PH_PQDTL_DTLKEY"],
                )
            _apply_pqdtl_sqty_suom_columns(
                detail_values,
                detail_cols,
                float(item["quantity"]),
                str(item.get("stockQtyUom") or "SUOMQTY"),
            )
            _insert_dynamic(cur, "PH_PQDTL", detail_values, detail_cols)

        if status == "SUBMITTED":
            upstream_payload = _build_upstream_payload(
                {
                    **validated,
                    "requestNumber": request_number,
                    "status": status,
                }
            )
            upstream_status, upstream_reference = _forward_to_upstream(upstream_payload, auth_header)

            status_col = _pick_existing(header_cols, "STATUS")
            upstream_status_col = _pick_existing(header_cols, "UPSTREAM_STATUS")
            upstream_ref_col = _pick_existing(header_cols, "UPSTREAM_REFERENCE")
            status_is_numeric = bool(status_col and _column_is_numeric(cur, "PH_PQ", status_col))

            updates: list[str] = []
            values: list[Any] = []
            if status_col:
                updates.append(f"{status_col} = ?")
                values.append(_encode_status(status, status_is_numeric))
            if upstream_status_col:
                updates.append(f"{upstream_status_col} = ?")
                values.append(upstream_status)
            if upstream_ref_col:
                updates.append(f"{upstream_ref_col} = ?")
                values.append(upstream_reference)
            if updates:
                values.append(header_id)
                cur.execute(
                    f"UPDATE PH_PQ SET {', '.join(updates)} WHERE {header_key_col} = ?",
                    tuple(values),
                )

        con.commit()

        return {
            "id": header_id,
            "requestNumber": request_number,
            "status": status,
            "upstreamStatus": upstream_status if status == "SUBMITTED" else "PENDING",
            "upstreamReference": upstream_reference or None,
            "requestDate": validated["requestDate"],
            "requiredDate": validated["requiredDate"],
            "totalAmount": validated["totalAmount"],
            "currency": validated["currency"],
            "lineItemCount": len(validated["lineItems"]),
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def preview_purchase_request_number() -> str:
    """Return the next auto-generated purchase request number."""
    ensure_purchase_request_schema()

    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        return _next_request_number(cur, header_cols)
    finally:
        con.close()


def list_purchase_requests(limit: int = 200) -> list[dict[str, Any]]:
    """Return purchase request headers with nested detail lines for the eProcurement view."""
    ensure_purchase_request_schema()
    safe_limit = max(1, min(int(limit or 200), 1000))
    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        detail_cols = _get_table_columns(cur, "PH_PQDTL")

        header_key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        detail_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        detail_fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")

        if not header_key_col:
            raise RuntimeError("PH_PQ primary key column not found (expected DOCKEY/PQKEY/ID)")
        if not detail_fk_col:
            raise RuntimeError("PH_PQDTL foreign key column not found (expected DOCKEY/PQKEY/REQUEST_ID/HEADER_ID)")

        request_no_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO", "PURCHASEREQUESTNO")
        request_date_col = _pick_existing(header_cols, "DOCDATE", "REQUESTDATE")
        required_date_col = _pick_existing(header_cols, "REQUIREDDATE", "DUEDATE", "POSTDATE")
        requester_col = _pick_existing(header_cols, "REQUESTERID", "CODE")
        department_col = _pick_existing(header_cols, "DEPARTMENTID")
        supplier_col = _pick_existing(header_cols, "SUPPLIERID", "CODE")
        currency_col = _pick_existing(header_cols, "CURRENCYCODE", "CURRENCY")
        total_col = _pick_existing(header_cols, "TOTAL_AMOUNT", "TOTALAMT", "DOCAMT")
        status_col = _pick_existing(header_cols, "STATUS")
        udf_reason_col = _pick_existing(header_cols, "UDF_REASON")

        detail_seq_col = _pick_existing(detail_cols, "SEQ", "LINE_NO", "LINENO")
        item_code_col = _pick_existing(detail_cols, "ITEMCODE")
        item_name_col = _pick_existing(detail_cols, "ITEMNAME")
        detail_desc_col = _pick_existing(detail_cols, "DESCRIPTION")
        detail_location_col = _pick_existing(detail_cols, "LOCATION", "LOC", "STOCKLOCATION", "STORELOCATION")
        detail_qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY")
        detail_unit_price_col = _pick_existing(detail_cols, "UNITPRICE")
        detail_tax_col = _pick_existing(detail_cols, "TAX")
        detail_amount_col = _pick_existing(detail_cols, "AMOUNT", "TOTAL")
        detail_delivery_col = _pick_existing(detail_cols, "DELIVERYDATE", "DELIVERY_DATE", "REQUIREDDATE")

        def _h(col: str) -> str:
            return f"H.{col}" if col else "NULL"

        def _d(col: str) -> str:
            return f"D.{col}" if col else "NULL"

        order_date_col = request_date_col or header_key_col
        order_seq_col = detail_seq_col or detail_key_col

        query = f"""
            SELECT
                H.{header_key_col} AS HEADER_ID,
                {_h(request_no_col)} AS REQUEST_NO,
                {_h(request_date_col)} AS REQUEST_DATE,
                {_h(required_date_col)} AS REQUIRED_DATE,
                {_h(requester_col)} AS REQUESTER_ID,
                {_h(department_col)} AS DEPARTMENT_ID,
                {_h(supplier_col)} AS SUPPLIER_ID,
                {_h(currency_col)} AS CURRENCY,
                {_h(total_col)} AS TOTAL_AMOUNT,
                {_h(status_col)} AS STATUS,
                {_h(udf_reason_col)} AS UDF_REASON,
                {_d(detail_key_col)} AS DETAIL_ID,
                {_d(order_seq_col)} AS DETAIL_SEQ,
                {_d(item_code_col)} AS ITEM_CODE,
                {_d(item_name_col)} AS ITEM_NAME,
                {_d(detail_desc_col)} AS DETAIL_DESC,
                {_d(detail_location_col)} AS DETAIL_LOCATION,
                {_d(detail_qty_col)} AS DETAIL_QTY,
                {_d(detail_unit_price_col)} AS DETAIL_UNIT_PRICE,
                {_d(detail_tax_col)} AS DETAIL_TAX,
                {_d(detail_amount_col)} AS DETAIL_AMOUNT,
                {_d(detail_delivery_col)} AS DETAIL_DELIVERY_DATE
            FROM PH_PQ H
            LEFT JOIN PH_PQDTL D ON D.{detail_fk_col} = H.{header_key_col}
            ORDER BY H.{order_date_col} DESC, H.{header_key_col} DESC, D.{order_seq_col} ASC
        """

        cur.execute(query)
        rows = cur.fetchall() or []

        grouped: dict[int, dict[str, Any]] = {}
        ordered_headers: list[dict[str, Any]] = []

        def _num(value: Any) -> float:
            try:
                return float(value or 0)
            except Exception:
                return 0.0

        for row in rows:
            header_id = int(row[0])
            header = grouped.get(header_id)
            if header is None:
                header = {
                    "id": header_id,
                    "requestNumber": _clean_text(row[1]),
                    "requestDate": row[2].isoformat() if hasattr(row[2], "isoformat") and row[2] is not None else _clean_text(row[2]),
                    "requiredDate": row[3].isoformat() if hasattr(row[3], "isoformat") and row[3] is not None else _clean_text(row[3]),
                    "requesterId": _clean_text(row[4]),
                    "departmentId": _clean_text(row[5]),
                    "supplierId": _clean_text(row[6]),
                    "currency": _clean_text(row[7]),
                    "totalAmount": _num(row[8]),
                    "status": _decode_status(row[9]),
                    "udfReason": _clean_text(row[10]),
                    "details": [],
                }
                grouped[header_id] = header
                ordered_headers.append(header)

            detail_id = row[11]
            if detail_id is None and not _clean_text(row[13]):
                continue

            header["details"].append(
                {
                    "id": int(detail_id) if detail_id is not None else None,
                    "seq": int(row[12]) if row[12] is not None else len(header["details"]) + 1,
                    "itemCode": _clean_text(row[13]),
                    "itemName": _clean_text(row[14]),
                    "description": _clean_text(row[15]),
                    "locationCode": _clean_text(row[16]),
                    "quantity": _num(row[17]),
                    "unitPrice": _num(row[18]),
                    "tax": _num(row[19]),
                    "amount": _num(row[20]),
                    "deliveryDate": row[21].isoformat() if hasattr(row[21], "isoformat") and row[21] is not None else _clean_text(row[21]),
                }
            )

        return ordered_headers[:safe_limit]
    finally:
        con.close()


def transition_purchase_request_status(
    request_number: str,
    new_status: str,
    actor: str,
) -> dict[str, Any]:
    """Transition purchase request status with simple workflow guards."""
    ensure_purchase_request_schema()
    normalized_request_number = _clean_text(request_number)
    if new_status is None:
        normalized_status = ""
    elif isinstance(new_status, (int, float)):
        normalized_status = _decode_status(int(new_status)).upper()
    else:
        normalized_status = _decode_status(new_status).upper()
    normalized_actor = _clean_text(actor) or "system"

    if not normalized_request_number:
        raise PurchaseRequestValidationError("requestNumber is required")
    if normalized_status not in {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "CANCELLED"}:
        raise PurchaseRequestValidationError("Invalid target status")

    allowed = {
        "DRAFT": {"SUBMITTED", "CANCELLED"},
        "SUBMITTED": {"APPROVED", "REJECTED", "CANCELLED"},
        "APPROVED": set(),
        "REJECTED": set(),
        "CANCELLED": set(),
    }

    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        status_col = _pick_existing(header_cols, "STATUS")
        request_no_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO", "PURCHASEREQUESTNO")
        updated_by_col = _pick_existing(header_cols, "UPDATEDBY")
        updated_at_col = _pick_existing(header_cols, "UPDATED_AT")

        if not key_col or not status_col or not request_no_col:
            raise RuntimeError("PH_PQ is missing required columns for status transition")

        cur.execute(
            f"SELECT FIRST 1 {key_col}, {status_col} FROM PH_PQ WHERE {request_no_col} = ?",
            (normalized_request_number,),
        )
        row = cur.fetchone()
        if not row:
            raise PurchaseRequestValidationError("Purchase request not found")

        request_id = int(row[0])
        status_is_numeric = _column_is_numeric(cur, "PH_PQ", status_col)
        current_status = _decode_status(row[1])

        if normalized_status == current_status:
            return {
                "requestNumber": normalized_request_number,
                "status": current_status,
                "message": "Status unchanged",
            }

        if normalized_status not in allowed.get(current_status, set()):
            raise PurchaseRequestValidationError(
                f"Transition from {current_status} to {normalized_status} is not allowed"
            )

        updates = [f"{status_col} = ?"]
        params: list[Any] = [_encode_status(normalized_status, status_is_numeric)]
        if updated_by_col:
            updates.append(f"{updated_by_col} = ?")
            params.append(normalized_actor)
        if updated_at_col:
            now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            updates.append(f"{updated_at_col} = ?")
            params.append(now_iso)
        else:
            now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        params.append(request_id)
        cur.execute(
            f"UPDATE PH_PQ SET {', '.join(updates)} WHERE {key_col} = ?",
            tuple(params),
        )

        con.commit()
        return {
            "requestNumber": normalized_request_number,
            "previousStatus": current_status,
            "status": normalized_status,
            "updatedAt": now_iso,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def update_purchase_request(
    request_id: int,
    payload: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    """Update editable PR header/detail fields for an existing purchase request."""
    ensure_purchase_request_schema()

    try:
        normalized_request_id = int(request_id)
    except Exception as exc:
        raise PurchaseRequestValidationError("request_id must be a valid integer") from exc

    if not isinstance(payload, dict):
        raise PurchaseRequestValidationError("payload must be an object")

    required_date = _as_date(payload.get("requiredDate"))
    if payload.get("requiredDate") and not required_date:
        raise PurchaseRequestValidationError("requiredDate must be YYYY-MM-DD")

    cost_center = _clean_text(payload.get("costCenter"))
    currency = _clean_text(payload.get("currency"))
    description = _clean_text(payload.get("description"))
    delivery_location = _clean_text(payload.get("deliveryLocation"))

    line_items = payload.get("lineItems")
    if not isinstance(line_items, list) or not line_items:
        raise PurchaseRequestValidationError("lineItems[] is required")

    normalized_lines: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    for idx, line in enumerate(line_items, start=1):
        if not isinstance(line, dict):
            raise PurchaseRequestValidationError(f"lineItems[{idx}] must be an object")

        raw_detail_id = line.get("detailId")
        try:
            detail_id = int(raw_detail_id)
        except Exception as exc:
            raise PurchaseRequestValidationError(f"lineItems[{idx}].detailId is required") from exc

        quantity = _money(_as_decimal(line.get("quantity"), "0"))
        unit_price = _money(_as_decimal(line.get("unitPrice"), "0"))
        if quantity < 0:
            raise PurchaseRequestValidationError(f"lineItems[{idx}].quantity must be >= 0")
        if unit_price < 0:
            raise PurchaseRequestValidationError(f"lineItems[{idx}].unitPrice must be >= 0")

        delivery_date = _as_date(line.get("deliveryDate"))
        if line.get("deliveryDate") and not delivery_date:
            raise PurchaseRequestValidationError(f"lineItems[{idx}].deliveryDate must be YYYY-MM-DD")

        line_amount = _money(quantity * unit_price)
        subtotal += line_amount

        stock_uom_raw = _clean_text(line.get("stockQtyUom") or line.get("stock_qty_uom"))
        normalized_lines.append(
            {
                "detailId": detail_id,
                "description": _clean_text(line.get("description")),
                "udfReason": _clean_text(line.get("udfReason") or line.get("udf_reason")),
                "project": _clean_text(line.get("project") or payload.get("project")) or "----",
                "quantity": float(quantity),
                "unitPrice": float(unit_price),
                "tax": 0.0,
                "amount": float(line_amount),
                "deliveryDate": delivery_date.isoformat() if delivery_date else None,
                "stockQtyUom": _normalize_stock_qty_uom(stock_uom_raw) if stock_uom_raw else None,
            }
        )

    total_amount = float(_money(subtotal))
    normalized_actor = _clean_text(actor) or "system"
    now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        detail_cols = _get_table_columns(cur, "PH_PQDTL")

        header_key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        detail_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        detail_fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")

        if not header_key_col:
            raise RuntimeError("PH_PQ primary key column not found")
        if not detail_key_col or not detail_fk_col:
            raise RuntimeError("PH_PQDTL key columns not found")

        cur.execute(
            f"SELECT FIRST 1 {header_key_col}, {_pick_existing(header_cols, 'STATUS') or 'NULL'} FROM PH_PQ WHERE {header_key_col} = ?",
            (normalized_request_id,),
        )
        row = cur.fetchone()
        if not row:
            raise PurchaseRequestValidationError("Purchase request not found")

        current_status = _decode_status(row[1]).upper() if len(row) > 1 else ""
        if current_status and current_status != "DRAFT":
            raise PurchaseRequestValidationError("Only draft purchase requests can be edited")

        updates: list[str] = []
        values: list[Any] = []

        required_date_col = _pick_existing(header_cols, "REQUIREDDATE", "DUEDATE", "POSTDATE")
        cost_center_col = _pick_existing(header_cols, "COSTCENTER", "DEPARTMENTID")
        currency_cols = [c for c in ("CURRENCYCODE", "CURRENCY") if c in header_cols]
        description_col = _pick_existing(header_cols, "DESCRIPTION")
        delivery_loc_col = _pick_existing(header_cols, "DELIVERYLOCATION")
        subtotal_col = _pick_existing(header_cols, "SUBTOTAL", "SUBTOTALAMT")
        tax_col = _pick_existing(header_cols, "TAXAMT")
        total_cols = [c for c in ("DOCAMT", "TOTALAMT", "TOTAL_AMOUNT") if c in header_cols]
        updated_by_col = _pick_existing(header_cols, "UPDATEDBY")
        updated_at_col = _pick_existing(header_cols, "UPDATED_AT")

        if required_date_col and required_date:
            updates.append(f"{required_date_col} = ?")
            values.append(required_date)
        if cost_center_col:
            updates.append(f"{cost_center_col} = ?")
            values.append(cost_center)
        for col in currency_cols:
            updates.append(f"{col} = ?")
            values.append(currency or "MYR")
        if description_col:
            updates.append(f"{description_col} = ?")
            values.append(description)
        if delivery_loc_col:
            updates.append(f"{delivery_loc_col} = ?")
            values.append(delivery_location)
        if subtotal_col:
            updates.append(f"{subtotal_col} = ?")
            values.append(total_amount)
        if tax_col:
            updates.append(f"{tax_col} = ?")
            values.append(0)
        for col in total_cols:
            updates.append(f"{col} = ?")
            values.append(total_amount)
        if updated_by_col:
            updates.append(f"{updated_by_col} = ?")
            values.append(normalized_actor)
        if updated_at_col:
            updates.append(f"{updated_at_col} = ?")
            values.append(now_iso)

        if updates:
            values.append(normalized_request_id)
            cur.execute(
                f"UPDATE PH_PQ SET {', '.join(updates)} WHERE {header_key_col} = ?",
                tuple(values),
            )

        detail_desc_col = _pick_existing(detail_cols, "DESCRIPTION")
        detail_qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY")
        detail_unit_col = _pick_existing(detail_cols, "UNITPRICE")
        detail_tax_col = _pick_existing(detail_cols, "TAX", "TAXAMT")
        detail_amount_col = _pick_existing(detail_cols, "AMOUNT", "TOTAL")
        detail_delivery_col = _pick_existing(detail_cols, "DELIVERYDATE", "DELIVERY_DATE")
        detail_udf_reason_col = _pick_existing(detail_cols, "UDF_REASON")
        detail_project_col = _pick_existing(detail_cols, "PROJECT")

        updated_lines = 0
        for line in normalized_lines:
            line_updates: list[str] = []
            line_values: list[Any] = []

            if detail_desc_col:
                line_updates.append(f"{detail_desc_col} = ?")
                line_values.append(line["description"])
            if detail_qty_col:
                line_updates.append(f"{detail_qty_col} = ?")
                line_values.append(line["quantity"])
            if detail_unit_col:
                line_updates.append(f"{detail_unit_col} = ?")
                line_values.append(line["unitPrice"])
            if detail_tax_col:
                line_updates.append(f"{detail_tax_col} = ?")
                line_values.append(0)
            if detail_amount_col:
                line_updates.append(f"{detail_amount_col} = ?")
                line_values.append(line["amount"])
            if detail_delivery_col and line["deliveryDate"]:
                line_updates.append(f"{detail_delivery_col} = ?")
                line_values.append(line["deliveryDate"])
            if detail_udf_reason_col:
                line_updates.append(f"{detail_udf_reason_col} = ?")
                line_values.append(line["udfReason"])
            if detail_project_col:
                line_updates.append(f"{detail_project_col} = ?")
                line_values.append(line["project"])

            if line.get("stockQtyUom"):
                _append_pqdtl_sqty_suom_update(
                    line_updates,
                    line_values,
                    detail_cols,
                    line["quantity"],
                    str(line["stockQtyUom"]),
                )

            if not line_updates:
                continue

            line_values.extend([line["detailId"], normalized_request_id])
            cur.execute(
                f"UPDATE PH_PQDTL SET {', '.join(line_updates)} WHERE {detail_key_col} = ? AND {detail_fk_col} = ?",
                tuple(line_values),
            )
            updated_lines += int(cur.rowcount or 0)

        con.commit()
        return {
            "requestId": normalized_request_id,
            "updatedHeader": True,
            "updatedLines": updated_lines,
            "totalAmount": total_amount,
            "updatedAt": now_iso,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
