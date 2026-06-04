"""Split one purchase request into multiple PRs when line awards use different suppliers."""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from utils.procurement_purchase_request import (
    _as_decimal,
    _clean_text,
    _connect_db,
    _decode_status,
    _encode_status,
    _get_table_columns,
    _insert_dynamic,
    _money,
    _next_key,
    _next_request_number,
    _pick_existing,
    _request_number_exists,
    _column_is_numeric,
    set_purchase_request_header_supplier,
)


class PrSplitError(ValueError):
    """Raised when mixed-supplier PR split cannot complete."""


def mixed_pr_split_enabled() -> bool:
    raw = _clean_text(os.getenv("PROCUREMENT_SPLIT_PR_ON_MIXED_AWARDS", "true")).lower()
    return raw not in {"0", "false", "no", "off"}


def _suppliers_in_award_order(
    normalized: list[tuple[int, int]],
    bid_map: dict[int, dict[str, Any]],
) -> list[str]:
    """
    Unique supplier codes in award order (lowest detail id first, then first time each
    new supplier appears). The first entry keeps the existing PR; the rest get new PRs
    in this same order using the next PR document numbers.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for detail_id, bid_id in sorted(normalized, key=lambda pair: pair[0]):
        code = _clean_text(bid_map.get(bid_id, {}).get("supplierCode"))
        if not code or code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return ordered


def _group_detail_ids_by_supplier(
    normalized: list[tuple[int, int]],
    bid_map: dict[int, dict[str, Any]],
) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for detail_id, bid_id in normalized:
        code = _clean_text(bid_map.get(bid_id, {}).get("supplierCode"))
        if not code:
            continue
        groups.setdefault(code, []).append(int(detail_id))
    return groups


def _row_to_dict(cur: Any, row: Any) -> dict[str, Any]:
    if not row:
        return {}
    names = [str(d[0]).strip() for d in (cur.description or [])]
    return {names[i]: row[i] for i in range(len(names))}


def _load_header_row(cur: Any, request_dockey: int) -> dict[str, Any]:
    header_cols = _get_table_columns(cur, "PH_PQ")
    key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
    if not key_col:
        raise PrSplitError("PH_PQ key column not found")
    cur.execute(f"SELECT * FROM PH_PQ WHERE {key_col} = ?", (int(request_dockey),))
    row = cur.fetchone()
    if not row:
        raise PrSplitError(f"purchase request {request_dockey} not found")
    return _row_to_dict(cur, row)


def _increment_docno_seed(seed: str) -> str | None:
    """Increment trailing digits on a docno (greedy prefix so PR-00000001 -> PR-00000002)."""
    text = _clean_text(seed)
    match = re.match(r"^(.*)(\d+)$", text)
    if not match:
        return None
    prefix, digits = match.group(1), match.group(2)
    width = len(digits)
    try:
        next_num = int(digits) + 1
    except ValueError:
        return None
    return f"{prefix}{next_num:0{width}d}"


def _allocate_unique_request_number(
    cur: Any,
    header_cols: set[str],
    *,
    split_from_docno: str = "",
) -> str:
    """
    Next unused PR number for a split child.

    Increments from the parent PR docno (PR-00000001 -> PR-00000002), then keeps
    bumping until a free DOCNO is found.
    """
    seed = _clean_text(split_from_docno)
    if seed:
        match = re.match(r"^(.*)(\d+)$", seed)
        if match:
            prefix, digits = match.group(1), match.group(2)
            width = len(digits)
            try:
                start = int(digits) + 1
            except ValueError:
                start = 1
            for num in range(start, start + 5000):
                candidate = f"{prefix}{num:0{width}d}"
                if not _request_number_exists(cur, header_cols, candidate):
                    return candidate

    for _ in range(200):
        candidate = _next_request_number(cur, header_cols)
        if not _request_number_exists(cur, header_cols, candidate):
            return candidate
        bumped = _increment_docno_seed(candidate)
        if bumped and bumped != candidate:
            candidate = bumped
            continue
        break

    raise PrSplitError("could not allocate a unique PR document number")


def _supplier_name_for_code(bid_map: dict[int, dict[str, Any]], supplier_code: str) -> str:
    from utils.sql_api_supplier import resolve_supplier_company_name

    code = _clean_text(supplier_code)
    stored = ""
    for bid in bid_map.values():
        if _clean_text(bid.get("supplierCode")) == code:
            stored = _clean_text(bid.get("supplierName"))
            break
    return resolve_supplier_company_name(code, stored)


def apply_ph_pq_supplier_header(
    cur: Any,
    request_dockey: int,
    supplier_code: str,
    supplier_name: str = "",
    *,
    actor: str = "admin",
) -> None:
    """Set awarded supplier master on PH_PQ (same transaction as split)."""
    from utils.procurement_pr_sql_api import ph_pq_header_updates_from_sql_supplier
    from utils.sql_api_supplier import fetch_supplier_row_by_code, looks_like_email, resolve_supplier_company_name

    code = _clean_text(supplier_code)
    if not code:
        return

    sql_row = fetch_supplier_row_by_code(code)
    resolved_name = resolve_supplier_company_name(code, supplier_name)
    if sql_row:
        updates = ph_pq_header_updates_from_sql_supplier(sql_row)
        name = _clean_text(updates.get("COMPANYNAME")) or resolved_name
        if looks_like_email(name):
            name = resolved_name
    else:
        name = resolved_name
        updates = {
            "CODE": code,
            "COMPANYNAME": name,
            "CURRENCYCODE": "----",
            "CURRENCY": "----",
            "CURRENCYRATE": 1,
            "SHIPPER": "----",
        }

    header_cols = _get_table_columns(cur, "PH_PQ")
    key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
    if not key_col:
        return

    updates["UPDATEDBY"] = _clean_text(actor) or "admin"
    updates["UPDATED_AT"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    set_parts = [f"{col} = ?" for col in updates if col in header_cols]
    if not set_parts:
        return
    values = [updates[col] for col in updates if col in header_cols]
    values.append(int(request_dockey))
    cur.execute(
        f"UPDATE PH_PQ SET {', '.join(set_parts)} WHERE {key_col} = ?",
        tuple(values),
    )


def _recalc_header_amounts(cur: Any, request_dockey: int, header_cols: set[str]) -> None:
    """Recompute PH_PQ totals from detail lines (Python sum — TAX/AMOUNT may be non-numeric in Firebird)."""
    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    amt_col = _pick_existing(detail_cols, "AMOUNT", "TOTAL", "LINEAMOUNT")
    tax_col = _pick_existing(detail_cols, "TAXAMT", "TAX")
    qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY")
    price_col = _pick_existing(detail_cols, "UNITPRICE", "UNIT_PRICE")
    if not fk_col:
        return

    select_cols: list[str] = []
    if amt_col:
        select_cols.append(amt_col)
    if tax_col and tax_col not in select_cols:
        select_cols.append(tax_col)
    if qty_col and qty_col not in select_cols:
        select_cols.append(qty_col)
    if price_col and price_col not in select_cols:
        select_cols.append(price_col)
    if not select_cols:
        return

    cur.execute(
        f"SELECT {', '.join(select_cols)} FROM PH_PQDTL WHERE {fk_col} = ?",
        (int(request_dockey),),
    )
    rows = cur.fetchall() or []
    col_index = {name: idx for idx, name in enumerate(select_cols)}

    line_total = Decimal("0")
    tax_total = Decimal("0")
    for row in rows:
        if not row:
            continue
        amt = Decimal("0")
        if amt_col and amt_col in col_index:
            amt = _as_decimal(row[col_index[amt_col]], "0")
        if amt <= 0 and qty_col and price_col and qty_col in col_index and price_col in col_index:
            qty = _as_decimal(row[col_index[qty_col]], "0")
            price = _as_decimal(row[col_index[price_col]], "0")
            amt = _money(qty * price)
        tax = Decimal("0")
        if tax_col and tax_col in col_index:
            tax = _as_decimal(row[col_index[tax_col]], "0")
        line_total += _money(amt)
        tax_total += _money(tax)

    subtotal = _money(line_total)
    tax_amt = _money(tax_total)
    total = _money(subtotal + tax_amt)

    key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
    updates: list[str] = []
    values: list[Any] = []
    for col_name, val in (
        ("SUBTOTAL", subtotal),
        ("SUBTOTALAMT", subtotal),
        ("TAXAMT", tax_amt),
        ("DOCAMT", total),
        ("TOTALAMT", total),
        ("TOTAL_AMOUNT", total),
    ):
        col = _pick_existing(header_cols, col_name)
        if col:
            updates.append(f"{col} = ?")
            values.append(float(val))
    if not updates or not key_col:
        return
    values.append(int(request_dockey))
    cur.execute(
        f"UPDATE PH_PQ SET {', '.join(updates)} WHERE {key_col} = ?",
        tuple(values),
    )


def _create_split_pr_header(
    cur: Any,
    *,
    source: dict[str, Any],
    supplier_code: str,
    supplier_name: str,
    actor: str,
    split_from_docno: str,
    new_docno: str,
) -> tuple[int, str]:
    header_cols = _get_table_columns(cur, "PH_PQ")
    key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
    if not key_col:
        raise PrSplitError("PH_PQ key column not found")

    docno = _clean_text(new_docno)
    if not docno:
        raise PrSplitError("new PR document number is required")
    if _request_number_exists(cur, header_cols, docno):
        docno = _allocate_unique_request_number(cur, header_cols, split_from_docno=split_from_docno)
    new_id = _next_key(
        cur,
        "PH_PQ",
        key_col,
        ["GEN_PH_PQ_ID", "GEN_PH_PQ_DOCKEY", "GEN_PH_PQ", "SEQ_PH_PQ_DOCKEY"],
    )

    now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    who = _clean_text(actor) or "admin"
    note = _clean_text(source.get("DESCRIPTION") or source.get("JUSTIFICATION") or "")
    split_note = f"Split from {split_from_docno} — supplier {supplier_code}"
    if note:
        note = f"{note} | {split_note}"
    else:
        note = split_note

    status_raw = source.get("STATUS")
    status_col = _pick_existing(header_cols, "STATUS")
    status_is_numeric = bool(status_col and _column_is_numeric(cur, "PH_PQ", status_col))
    status_text = _decode_status(status_raw)

    header_values: dict[str, Any] = {
        key_col: new_id,
        "DOCNO": docno,
        "DOCNOEX": docno,
        "REQUESTNO": docno,
        "PRNO": docno,
        "CODE": supplier_code,
        "COMPANYNAME": supplier_name or supplier_code,
        "SUPPLIERID": supplier_code,
        "DESCRIPTION": note[:500] if note else split_note,
        "CREATEDBY": who,
        "CREATED_AT": now_iso,
        "UPDATEDBY": who,
        "UPDATED_AT": now_iso,
    }

    copy_cols = (
        "DOCDATE",
        "POSTDATE",
        "TAXDATE",
        "REQUESTDATE",
        "REQUIREDDATE",
        "DEPARTMENTID",
        "COSTCENTER",
        "PROJECT",
        "SHIPPER",
        "CURRENCYCODE",
        "CURRENCY",
        "CURRENCYRATE",
        "JUSTIFICATION",
        "DELIVERYLOCATION",
        "NOTES",
        "UDF_STATUS",
        "UDFSTATUS",
        "STATUS",
    )
    for col in copy_cols:
        if col in header_cols and col in source and source[col] is not None:
            if col == "STATUS":
                header_values[col] = _encode_status(status_text, status_is_numeric)
            else:
                header_values[col] = source[col]

    _insert_dynamic(cur, "PH_PQ", header_values, header_cols)
    return int(new_id), docno


def _move_details(
    cur: Any,
    *,
    from_dockey: int,
    to_dockey: int,
    detail_ids: list[int],
) -> None:
    if not detail_ids:
        return
    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
    if not fk_col or not dtl_col:
        raise PrSplitError("PH_PQDTL key columns not found")
    placeholders = ", ".join(["?"] * len(detail_ids))
    cur.execute(
        f"""
        UPDATE PH_PQDTL
        SET {fk_col} = ?
        WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
        """,
        tuple([int(to_dockey), int(from_dockey), *detail_ids]),
    )


def _repoint_line_awards(
    cur: Any,
    *,
    from_dockey: int,
    to_dockey: int,
    detail_ids: list[int],
) -> None:
    if not detail_ids or not _table_exists(cur, "PR_BID_LINE_AWARD"):
        return
    placeholders = ", ".join(["?"] * len(detail_ids))
    cur.execute(
        f"""
        UPDATE PR_BID_LINE_AWARD
        SET REQUEST_DOCKEY = ?
        WHERE REQUEST_DOCKEY = ? AND DETAIL_ID IN ({placeholders})
        """,
        tuple([int(to_dockey), int(from_dockey), *detail_ids]),
    )


def _table_exists(cur: Any, table_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?",
        (table_name.upper(),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _detail_rows_for_sql_post(cur: Any, request_dockey: int, detail_ids: list[int]) -> list[dict[str, Any]]:
    detail_cols = _get_table_columns(cur, "PH_PQDTL")
    fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
    dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
    item_col = _pick_existing(detail_cols, "ITEMCODE", "ITEM_CODE")
    desc_col = _pick_existing(detail_cols, "DESCRIPTION", "ITEMNAME")
    qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY")
    price_col = _pick_existing(detail_cols, "UNITPRICE", "UNIT_PRICE")
    tax_col = _pick_existing(detail_cols, "TAX", "TAXAMT")
    loc_col = _pick_existing(detail_cols, "LOCATION", "LOC")
    del_col = _pick_existing(detail_cols, "DELIVERYDATE", "DELIVERY_DATE")
    if not fk_col or not dtl_col:
        return []

    placeholders = ", ".join(["?"] * len(detail_ids))
    cur.execute(
        f"""
        SELECT {dtl_col}, {item_col or "ITEMCODE"}, {desc_col or "DESCRIPTION"},
               {qty_col or "QTY"}, {price_col or "UNITPRICE"}, {tax_col or "TAX"},
               {loc_col or "LOCATION"}, {del_col or "DELIVERYDATE"}
        FROM PH_PQDTL
        WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
        ORDER BY {dtl_col}
        """,
        tuple([int(request_dockey), *detail_ids]),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        if not row:
            continue
        qty = float(_as_decimal(row[3], "0"))
        price = float(_as_decimal(row[4], "0"))
        tax = float(_as_decimal(row[5], "0"))
        items.append(
            {
                "itemCode": _clean_text(row[1]),
                "itemName": _clean_text(row[2]) or _clean_text(row[1]),
                "description": _clean_text(row[2]) or _clean_text(row[1]),
                "locationCode": _clean_text(row[6]) or "----",
                "quantity": qty,
                "unitPrice": price,
                "tax": tax,
                "amount": float(_money(_as_decimal(qty) * _as_decimal(price) + _as_decimal(tax))),
                "deliveryDate": row[7].isoformat() if hasattr(row[7], "isoformat") else _clean_text(row[7]),
            }
        )
    return items


def split_purchase_request_for_mixed_awards(
    cur: Any,
    request_dockey: int,
    normalized: list[tuple[int, int]],
    bid_map: dict[int, dict[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """
    When multiple suppliers win line awards, the first supplier in award order keeps the
    existing PR; each following supplier gets a new PR using the next PR number sequence.
    """
    groups = _group_detail_ids_by_supplier(normalized, bid_map)
    if len(groups) <= 1:
        return {"split": False, "reason": "single supplier"}

    supplier_order = _suppliers_in_award_order(normalized, bid_map)
    if not supplier_order:
        raise PrSplitError("could not determine supplier order for split")

    existing_pr_supplier = supplier_order[0]

    source_header = _load_header_row(cur, request_dockey)
    header_cols = _get_table_columns(cur, "PH_PQ")
    docno_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO")
    split_from_docno = _clean_text(source_header.get(docno_col) if docno_col else "") or str(request_dockey)

    created: list[dict[str, Any]] = []
    for supplier_code in supplier_order[1:]:
        detail_ids = groups.get(supplier_code) or []
        if not detail_ids:
            continue
        supplier_name = _supplier_name_for_code(bid_map, supplier_code)

        new_docno = _allocate_unique_request_number(
            cur, header_cols, split_from_docno=split_from_docno
        )
        new_dockey, new_docno = _create_split_pr_header(
            cur,
            source=source_header,
            supplier_code=supplier_code,
            supplier_name=supplier_name,
            actor=actor,
            split_from_docno=split_from_docno,
            new_docno=new_docno,
        )
        _move_details(cur, from_dockey=request_dockey, to_dockey=new_dockey, detail_ids=detail_ids)
        _repoint_line_awards(
            cur,
            from_dockey=request_dockey,
            to_dockey=new_dockey,
            detail_ids=detail_ids,
        )
        _recalc_header_amounts(cur, new_dockey, header_cols)
        apply_ph_pq_supplier_header(cur, new_dockey, supplier_code, supplier_name, actor=actor)
        created.append(
            {
                "dockey": new_dockey,
                "docno": new_docno,
                "supplierCode": supplier_code,
                "supplierName": supplier_name,
                "detailIds": detail_ids,
            }
        )

    _recalc_header_amounts(cur, request_dockey, header_cols)
    apply_ph_pq_supplier_header(
        cur,
        request_dockey,
        existing_pr_supplier,
        _supplier_name_for_code(bid_map, existing_pr_supplier),
        actor=actor,
    )

    return {
        "split": True,
        "existingPrDockey": int(request_dockey),
        "existingPrDocno": split_from_docno,
        "existingPrSupplierCode": existing_pr_supplier,
        "existingPrSupplierName": _supplier_name_for_code(bid_map, existing_pr_supplier),
        "supplierOrder": supplier_order,
        "primaryDockey": int(request_dockey),
        "primaryDocno": split_from_docno,
        "primarySupplierCode": existing_pr_supplier,
        "childPrs": created,
    }


def sync_split_prs_to_sql_api(split_result: dict[str, Any], *, actor: str = "admin") -> dict[str, Any]:
    """PUT existing PR first (update), then POST each new split PR (create)."""
    from utils.procurement_pr_sql_api import build_purchaserequest_upstream_payload
    from utils.procurement_sql_api_sync import (
        post_purchaserequest_sql_api,
        put_purchaserequest_lines_and_supplier_sql_api,
    )
    from utils.sql_api_supplier import resolve_supplier_company_name

    if not split_result.get("split"):
        return {"skipped": True}

    outcomes: dict[str, Any] = {"children": [], "primary": None}
    primary_dockey = int(
        split_result.get("existingPrDockey") or split_result.get("primaryDockey") or 0
    )
    primary_code = _clean_text(
        split_result.get("existingPrSupplierCode") or split_result.get("primarySupplierCode")
    )
    primary_docno = _clean_text(
        split_result.get("existingPrDocno") or split_result.get("primaryDocno")
    )

    con = _connect_db()
    try:
        cur = con.cursor()
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
        dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        primary_ids: list[int] = []
        if fk_col and dtl_col:
            cur.execute(
                f"SELECT {dtl_col} FROM PH_PQDTL WHERE {fk_col} = ? ORDER BY {dtl_col}",
                (primary_dockey,),
            )
            primary_ids = [int(r[0]) for r in (cur.fetchall() or []) if r and r[0] is not None]

        primary_name = _clean_text(
            split_result.get("existingPrSupplierName") or split_result.get("primarySupplierName")
        )
        try:
            set_purchase_request_header_supplier(
                primary_dockey,
                primary_code,
                primary_name,
                actor=actor,
            )
        except Exception as exc:
            print(
                f"[PROCUREMENT PR SPLIT] primary header sync warning dockey={primary_dockey}: {exc}",
                flush=True,
            )
        try:
            outcomes["primary"] = put_purchaserequest_lines_and_supplier_sql_api(
                primary_dockey,
                primary_code,
                request_number=primary_docno,
                keep_dtlkeys=set(primary_ids),
            )
        except Exception as exc:
            outcomes["primary"] = {"synced": False, "error": str(exc)}
            print(f"[PROCUREMENT PR SPLIT] primary PUT warning dockey={primary_dockey}: {exc}", flush=True)

        for child in split_result.get("childPrs") or []:
            if not isinstance(child, dict):
                continue
            child_dockey = int(child.get("dockey") or 0)
            child_code = _clean_text(child.get("supplierCode"))
            child_docno = _clean_text(child.get("docno"))
            detail_ids = [int(x) for x in (child.get("detailIds") or [])]
            line_items = _detail_rows_for_sql_post(cur, child_dockey, detail_ids)
            src = _load_header_row(cur, child_dockey)
            req_date = src.get("DOCDATE") or src.get("REQUESTDATE") or date.today()
            if hasattr(req_date, "isoformat"):
                req_date = req_date.isoformat()[:10]
            else:
                req_date = _clean_text(req_date)[:10] or date.today().isoformat()

            payload = build_purchaserequest_upstream_payload(
                {
                    "requestNumber": child_docno,
                    "requestDate": str(req_date),
                    "departmentId": _clean_text(src.get("DEPARTMENTID")) or "PROC",
                    "project": _clean_text(src.get("PROJECT")) or "----",
                    "description": _clean_text(src.get("DESCRIPTION")),
                    "status": "SUBMITTED",
                    "supplierId": child_code,
                    "supplierName": resolve_supplier_company_name(
                        child_code,
                        _clean_text(child.get("supplierName")),
                    ),
                    "lineItems": line_items,
                    "totalAmount": sum(float(i.get("amount") or 0) for i in line_items),
                },
                request_number=child_docno,
            )
            try:
                post_result = post_purchaserequest_sql_api(payload, preferred_dockey=child_dockey)
                outcomes["children"].append({"dockey": child_dockey, "docno": child_docno, **post_result})
            except Exception as exc:
                outcomes["children"].append(
                    {"dockey": child_dockey, "docno": child_docno, "synced": False, "error": str(exc)}
                )
            try:
                set_purchase_request_header_supplier(child_dockey, child_code, actor=actor)
            except Exception as exc:
                print(f"[PROCUREMENT PR SPLIT] child POST/header sync warning dockey={child_dockey}: {exc}", flush=True)
    finally:
        con.close()

    return outcomes
