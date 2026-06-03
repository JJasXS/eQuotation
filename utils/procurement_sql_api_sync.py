"""Sync awarded supplier master onto SQL Accounting documents via GET + PUT."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from api.clients import SqlAccountingApiClient
from api.config import load_sql_accounting_api_settings

from utils.sql_api_supplier import (
    fetch_supplier_row_by_code,
    supplier_master_document_fields,
    supplier_sdsbranch_for_document_put,
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _api_root_url(path_env: str, default_path: str) -> str:
    settings = load_sql_accounting_api_settings()
    scheme = "https" if settings.use_tls else "http"
    host = settings.host.strip().rstrip("/")
    path = (os.getenv(path_env) or default_path).strip() or default_path
    if not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{host}{quote(path.rstrip("/"), safe='/:?&=%')}"


def _document_root(parsed: Any) -> dict[str, Any] | None:
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list) and parsed["data"]:
        first = parsed["data"][0]
        return first if isinstance(first, dict) else None
    if isinstance(parsed, list) and parsed:
        return parsed[0] if isinstance(parsed[0], dict) else None
    if isinstance(parsed, dict) and parsed.get("dockey") is not None:
        return parsed
    return None


def sql_api_header_fields_from_supplier(row: dict[str, Any]) -> dict[str, Any]:
    """Header fields shared by purchaserequest / purchaseorder PUT bodies."""
    flat = supplier_master_document_fields(row)
    skip = {"email", "creditterm", "creditlimit", "overduelimit", "statementtype", "biznature", "taxarea", "peppolid"}
    out: dict[str, Any] = {}
    for key, value in flat.items():
        if key in skip:
            continue
        if value is None or (isinstance(value, str) and not _clean_text(value)):
            continue
        out[key] = value
    if flat.get("creditterm"):
        out["terms"] = flat["creditterm"]
    if "area" not in out:
        out["area"] = "----"
    if "agent" not in out:
        out["agent"] = "----"
    # SQL Accounting Delivery tab reads daddress* / dphone* (not only address*).
    for src, dest in (
        ("address1", "daddress1"),
        ("address2", "daddress2"),
        ("address3", "daddress3"),
        ("address4", "daddress4"),
        ("postcode", "dpostcode"),
        ("city", "dcity"),
        ("state", "dstate"),
        ("country", "dcountry"),
        ("attention", "dattention"),
        ("phone1", "dphone1"),
        ("mobile", "dmobile"),
        ("fax1", "dfax1"),
    ):
        if flat.get(src) and not out.get(dest):
            out[dest] = flat[src]
    return out


def merge_supplier_into_sql_api_document(
    existing: dict[str, Any],
    supplier_row: dict[str, Any],
) -> dict[str, Any]:
    """Overlay supplier master onto an existing SQL API document payload (lines unchanged)."""
    merged = dict(existing)
    for key, value in sql_api_header_fields_from_supplier(supplier_row).items():
        if value is None:
            continue
        if _clean_text(value) == "" and key not in ("code", "companyname"):
            continue
        merged[key] = value
    return merged


_PUT_HEADER_KEYS = frozenset({
    "dockey", "docno", "docnoex", "docdate", "postdate", "taxdate", "updatecount",
    "code", "companyname", "companyname2", "area", "agent", "project",
    "terms", "shipper", "currencycode", "currencyrate", "description",
    "cancelled", "status", "docamt", "localdocamt", "branchname",
    "address1", "address2", "address3", "address4", "postcode", "city",
    "state", "country", "phone1", "phone2", "mobile", "fax1", "fax2",
    "attention", "daddress1", "daddress2", "daddress3", "daddress4",
    "dpostcode", "dcity", "dstate", "dcountry", "dattention", "dphone1",
    "dmobile", "dfax1", "tin", "brn", "brn2", "gstno", "salestaxno",
    "servicetaxno", "taxexemptno", "idno", "idtype", "tourismno", "sic",
    "submissiontype", "businessunit", "changed", "transferable",
})


def _strip_readonly_nested_fields(value: Any) -> Any:
    """Remove SQL API read-only keys from nested line/branch rows before PUT."""
    drop = frozenset(
        {"updatecount", "updateCount", "dirty", "lastmodified", "lastModified", "rowver"}
    )
    if isinstance(value, list):
        return [_strip_readonly_nested_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {k: _strip_readonly_nested_fields(v) for k, v in value.items() if k not in drop}


def build_supplier_put_payload(
    existing: dict[str, Any],
    supplier_row: dict[str, Any],
    *,
    include_lines: bool = True,
    include_sdsbranch: bool = True,
) -> dict[str, Any]:
    """
    Build a PUT body for SQL Accounting (header + optional lines).

    Full-document PUT can trigger SQL assertion errors; callers may retry with
    ``include_lines=False`` (header-only patch).
    """
    hdr = sql_api_header_fields_from_supplier(supplier_row)
    changed_flag = existing.get("changed")
    if changed_flag is None:
        changed_flag = False
    payload: dict[str, Any] = {"changed": bool(changed_flag), **hdr}
    # Only copy document identity/amounts from GET — merging the full header causes SQL assertion errors.
    for key in (
        "docnoex",
        "project",
        "shipper",
        "status",
        "docamt",
        "localdocamt",
        "currencyrate",
        "description",
    ):
        if key in existing and existing[key] is not None and key not in payload:
            payload[key] = existing[key]
    payload["dockey"] = int(existing.get("dockey") or payload.get("dockey") or 0)
    uc_raw = existing.get("updatecount") if existing.get("updatecount") is not None else existing.get("updateCount")
    try:
        payload["updatecount"] = int(uc_raw) if uc_raw is not None else 0
    except (TypeError, ValueError):
        payload["updatecount"] = 0
    if not payload.get("docno"):
        payload["docno"] = existing.get("docno")
    if not payload.get("docdate"):
        payload["docdate"] = existing.get("docdate")
    if not payload.get("postdate"):
        payload["postdate"] = existing.get("postdate")
    if not payload.get("taxdate"):
        payload["taxdate"] = existing.get("taxdate")
    if not payload.get("project"):
        payload["project"] = existing.get("project") or "----"
    if not payload.get("shipper"):
        payload["shipper"] = existing.get("shipper") or "----"
    if "status" not in payload and existing.get("status") is not None:
        payload["status"] = existing.get("status")
    if "docamt" not in payload and existing.get("docamt") is not None:
        payload["docamt"] = existing.get("docamt")
    if "localdocamt" not in payload and existing.get("localdocamt") is not None:
        payload["localdocamt"] = existing.get("localdocamt")
    if include_lines and isinstance(existing.get("sdsdocdetail"), list):
        payload["sdsdocdetail"] = _strip_readonly_nested_fields(existing["sdsdocdetail"])
    if include_sdsbranch:
        branches = supplier_sdsbranch_for_document_put(supplier_row)
        if branches:
            payload["sdsbranch"] = _strip_readonly_nested_fields(branches)
    allowed = _PUT_HEADER_KEYS | frozenset({"sdsdocdetail", "sdsbranch"})
    return {k: v for k, v in payload.items() if k in allowed}


def _put_supplier_with_retry(
    client: SqlAccountingApiClient,
    *,
    base_path: str,
    existing: dict[str, Any],
    supplier_row: dict[str, Any],
    timeout_seconds: float,
    include_sdsbranch: bool = True,
) -> tuple[int, str, bool]:
    """PUT supplier patch; retry header-only if full body fails."""
    put_dockey = int(existing.get("dockey") or 0)
    line_attempts = (False, True) if not include_sdsbranch else (True, False)
    for include_lines in line_attempts:
        payload = build_supplier_put_payload(
            existing,
            supplier_row,
            include_lines=include_lines,
            include_sdsbranch=include_sdsbranch,
        )
        status, preview = _put_document(
            client,
            base_path=base_path,
            dockey=put_dockey,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        if 200 <= status < 300:
            return status, preview, include_lines
        if include_lines:
            continue
        return status, preview, False
    return status, preview, False


def _get_document(
    client: SqlAccountingApiClient,
    *,
    base_path: str,
    dockey: int,
    docno: str = "",
    timeout_seconds: float,
) -> dict[str, Any] | None:
    candidates: list[str] = []
    if dockey > 0:
        candidates.append(f"{base_path}/{int(dockey)}")
        candidates.append(f"{base_path}/*?dockey={int(dockey)}")
    docno_clean = _clean_text(docno)
    if docno_clean:
        candidates.append(f"{base_path}/*?docno={quote(docno_clean, safe='')}")

    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        status, parsed, _raw = client.get_json(url, timeout_seconds=timeout_seconds)
        if status != 200:
            continue
        doc = _document_root(parsed)
        if doc:
            return doc
    return None


def _put_document(
    client: SqlAccountingApiClient,
    *,
    base_path: str,
    dockey: int,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> tuple[int, str]:
    url = f"{base_path}/{int(dockey)}"
    status, _parsed, raw = client.put_json(url, payload, timeout_seconds=timeout_seconds)
    preview = (raw or "").strip()[:300]
    return status, preview


def sync_purchase_request_supplier_sql_api(
    request_dockey: int,
    supplier_code: str,
    *,
    request_number: str = "",
) -> dict[str, Any]:
    """
    PUT ``/purchaserequest/:DOCKEY`` with supplier master from GET ``/supplier``.
    """
    code = _clean_text(supplier_code)
    dockey = int(request_dockey or 0)
    if not code or dockey <= 0:
        return {"skipped": True, "reason": "missing supplier or request dockey"}

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return {"skipped": True, "reason": "SQL API not configured"}

    supplier_row = fetch_supplier_row_by_code(code)
    if not supplier_row:
        return {"skipped": True, "reason": f"supplier {code!r} not found on SQL API"}

    client = SqlAccountingApiClient(settings)
    timeout = min(45.0, settings.timeout_seconds + 10.0)
    base = _api_root_url("SQL_API_PURCHASE_REQUEST_PATH", "/purchaserequest")

    existing = _get_document(
        client,
        base_path=base,
        dockey=dockey,
        docno=request_number,
        timeout_seconds=timeout,
    )
    if not existing:
        return {"skipped": True, "reason": "purchase request not found on SQL API"}

    put_dockey = int(existing.get("dockey") or dockey)
    status, preview, with_lines = _put_supplier_with_retry(
        client,
        base_path=base,
        existing=existing,
        supplier_row=supplier_row,
        timeout_seconds=timeout,
        include_sdsbranch=False,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"SQL API PUT purchaserequest/{put_dockey} returned HTTP {status}: {preview}")
    return {
        "synced": True,
        "dockey": put_dockey,
        "supplierCode": code,
        "httpStatus": status,
        "includedLines": with_lines,
    }


def _linked_po_dockeys_for_request(request_dockey: int) -> list[int]:
    """PO dockeys already linked to a purchase request via ST_XTRANS (PQ → PO)."""
    from utils.db_utils import get_db_connection
    from utils.procurement_purchase_request import _get_table_columns, _pick_existing

    dockey = int(request_dockey or 0)
    if dockey <= 0:
        return []

    con = get_db_connection()
    try:
        cur = con.cursor()
        xtrans_cols = _get_table_columns(cur, "ST_XTRANS")
        from_type = _pick_existing(xtrans_cols, "FROMDOCTYPE")
        from_key = _pick_existing(xtrans_cols, "FROMDOCKEY")
        to_type = _pick_existing(xtrans_cols, "TODOCTYPE")
        to_key = _pick_existing(xtrans_cols, "TODOCKEY")
        if not from_type or not from_key or not to_type or not to_key:
            return []

        cur.execute(
            f"""
            SELECT DISTINCT {to_key}
            FROM ST_XTRANS
            WHERE UPPER(TRIM(COALESCE({from_type}, ''))) IN ('PQ', 'PH_PQ')
              AND {from_key} = ?
              AND UPPER(TRIM(COALESCE({to_type}, ''))) IN ('PO', 'PH_PO')
              AND {to_key} IS NOT NULL
            """,
            (dockey,),
        )
        out: list[int] = []
        for row in cur.fetchall() or []:
            if not row or row[0] is None:
                continue
            try:
                po_id = int(row[0])
            except (TypeError, ValueError):
                continue
            if po_id > 0 and po_id not in out:
                out.append(po_id)
        return out
    finally:
        con.close()


def sync_linked_purchase_orders_for_request(
    request_dockey: int,
    supplier_code: str,
) -> list[dict[str, Any]]:
    """PUT supplier master onto each PO already linked to this PR."""
    results: list[dict[str, Any]] = []
    for po_dockey in _linked_po_dockeys_for_request(request_dockey):
        try:
            results.append(
                sync_purchase_order_supplier_sql_api(po_dockey, supplier_code)
            )
        except Exception as exc:
            results.append(
                {
                    "synced": False,
                    "dockey": po_dockey,
                    "error": str(exc),
                }
            )
    return results


def sync_purchase_order_supplier_sql_api(
    po_dockey: int,
    supplier_code: str,
    *,
    po_number: str = "",
) -> dict[str, Any]:
    """
    PUT ``/purchaseorder/:DOCKEY`` with supplier master from GET ``/supplier``.
    """
    code = _clean_text(supplier_code)
    dockey = int(po_dockey or 0)
    if not code or dockey <= 0:
        return {"skipped": True, "reason": "missing supplier or PO dockey"}

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return {"skipped": True, "reason": "SQL API not configured"}

    supplier_row = fetch_supplier_row_by_code(code)
    if not supplier_row:
        return {"skipped": True, "reason": f"supplier {code!r} not found on SQL API"}

    client = SqlAccountingApiClient(settings)
    timeout = min(60.0, settings.timeout_seconds + 15.0)
    base = _api_root_url("SQL_API_PURCHASE_ORDER_PATH", "/purchaseorder")

    existing = _get_document(
        client,
        base_path=base,
        dockey=dockey,
        docno=po_number,
        timeout_seconds=timeout,
    )
    if not existing:
        return {"skipped": True, "reason": "purchase order not found on SQL API"}

    put_dockey = int(existing.get("dockey") or dockey)
    status, preview, with_lines = _put_supplier_with_retry(
        client,
        base_path=base,
        existing=existing,
        supplier_row=supplier_row,
        timeout_seconds=timeout,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"SQL API PUT purchaseorder/{put_dockey} returned HTTP {status}: {preview}")
    return {
        "synced": True,
        "dockey": put_dockey,
        "poNumber": _clean_text(existing.get("docno") or po_number),
        "supplierCode": code,
        "httpStatus": status,
        "includedLines": with_lines,
    }


def _parsed_post_document(parsed: Any) -> dict[str, Any] | None:
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list) and parsed["data"]:
        first = parsed["data"][0]
        return first if isinstance(first, dict) else None
    if isinstance(parsed, dict) and parsed.get("dockey") is not None:
        return parsed
    return None


def post_purchaserequest_sql_api(
    payload: dict[str, Any],
    *,
    preferred_dockey: int = 0,
) -> dict[str, Any]:
    """POST ``/purchaserequest`` for a split child PR."""
    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return {"skipped": True, "reason": "SQL API not configured"}

    client = SqlAccountingApiClient(settings)
    timeout = min(60.0, settings.timeout_seconds + 15.0)
    base = _api_root_url("SQL_API_PURCHASE_REQUEST_PATH", "/purchaserequest")
    body = dict(payload)
    if preferred_dockey > 0 and "dockey" not in body:
        body["dockey"] = int(preferred_dockey)

    status, parsed, preview = client.post_json(base, body, timeout_seconds=timeout)
    if status < 200 or status >= 300:
        raise RuntimeError(f"SQL API POST purchaserequest returned HTTP {status}: {(preview or '')[:300]}")

    doc = _parsed_post_document(parsed) or {}
    return {
        "synced": True,
        "httpStatus": status,
        "dockey": int(doc.get("dockey") or preferred_dockey or 0),
        "docno": _clean_text(doc.get("docno") or body.get("docno")),
    }


def _local_pqdtl_pricing_by_dtlkey(
    request_dockey: int,
    keep_dtlkeys: set[int],
) -> dict[int, dict[str, float]]:
    """Read latest PH_PQDTL unit price / tax / amount for SQL API PUT merge."""
    if not keep_dtlkeys:
        return {}
    from utils.db_utils import get_db_connection
    from utils.procurement_purchase_request import _as_decimal, _get_table_columns, _money, _pick_existing

    con = get_db_connection()
    try:
        cur = con.cursor()
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
        dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        price_col = _pick_existing(detail_cols, "UNITPRICE", "UNIT_PRICE")
        tax_col = _pick_existing(detail_cols, "TAXAMT", "TAX")
        amt_col = _pick_existing(detail_cols, "AMOUNT", "TOTAL", "LINEAMOUNT")
        if not fk_col or not dtl_col or not price_col:
            return {}
        select_cols = [dtl_col, price_col]
        if tax_col:
            select_cols.append(tax_col)
        if amt_col:
            select_cols.append(amt_col)
        placeholders = ", ".join(["?"] * len(keep_dtlkeys))
        cur.execute(
            f"""
            SELECT {", ".join(select_cols)}
            FROM PH_PQDTL
            WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
            """,
            tuple([int(request_dockey), *sorted(keep_dtlkeys)]),
        )
        out: dict[int, dict[str, float]] = {}
        for row in cur.fetchall() or []:
            if not row or row[0] is None:
                continue
            try:
                dtlkey = int(row[0])
            except (TypeError, ValueError):
                continue
            unit_price = float(_money(_as_decimal(row[1], "0")))
            idx = 2
            tax = 0.0
            if tax_col:
                tax = float(_money(_as_decimal(row[idx], "0")))
                idx += 1
            amount = 0.0
            if amt_col:
                amount = float(_money(_as_decimal(row[idx], "0")))
            if amount <= 0:
                amount = float(_money(unit_price + tax))
            out[dtlkey] = {
                "unitprice": unit_price,
                "tax": tax,
                "amount": amount,
            }
        return out
    finally:
        con.close()


def _merge_local_pqdtl_prices_into_document(
    document: dict[str, Any],
    request_dockey: int,
    keep_dtlkeys: set[int],
) -> dict[str, Any]:
    """Overlay Firebird PH_PQDTL pricing onto SQL API sdsdocdetail before PUT."""
    pricing = _local_pqdtl_pricing_by_dtlkey(request_dockey, keep_dtlkeys)
    if not pricing:
        return document
    lines = document.get("sdsdocdetail") if isinstance(document.get("sdsdocdetail"), list) else []
    merged: list[dict[str, Any]] = []
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        try:
            dtlkey = int(ln.get("dtlkey") or 0)
        except (TypeError, ValueError):
            merged.append(ln)
            continue
        hit = pricing.get(dtlkey)
        if not hit:
            merged.append(ln)
            continue
        patched = dict(ln)
        patched["unitprice"] = hit["unitprice"]
        if "tax" in patched or hit.get("tax"):
            patched["tax"] = hit["tax"]
        if "taxamt" in patched:
            patched["taxamt"] = hit["tax"]
        patched["amount"] = hit["amount"]
        merged.append(patched)
    return {**document, "sdsdocdetail": merged}


def put_purchaserequest_lines_and_supplier_sql_api(
    request_dockey: int,
    supplier_code: str,
    *,
    request_number: str = "",
    keep_dtlkeys: set[int] | None = None,
) -> dict[str, Any]:
    """PUT PR with only retained detail lines and awarded supplier header."""
    code = _clean_text(supplier_code)
    dockey = int(request_dockey or 0)
    if not code or dockey <= 0:
        return {"skipped": True, "reason": "missing supplier or request dockey"}

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return {"skipped": True, "reason": "SQL API not configured"}

    supplier_row = fetch_supplier_row_by_code(code)
    if not supplier_row:
        return {"skipped": True, "reason": f"supplier {code!r} not found on SQL API"}

    client = SqlAccountingApiClient(settings)
    timeout = min(60.0, settings.timeout_seconds + 15.0)
    base = _api_root_url("SQL_API_PURCHASE_REQUEST_PATH", "/purchaserequest")

    existing = _get_document(
        client,
        base_path=base,
        dockey=dockey,
        docno=request_number,
        timeout_seconds=timeout,
    )
    if not existing:
        return {"skipped": True, "reason": "purchase request not found on SQL API"}

    keep = keep_dtlkeys or set()
    if keep:
        lines = existing.get("sdsdocdetail") if isinstance(existing.get("sdsdocdetail"), list) else []
        existing = {
            **existing,
            "sdsdocdetail": [
                ln
                for ln in lines
                if isinstance(ln, dict) and int(ln.get("dtlkey") or 0) in keep
            ],
        }
        existing = _merge_local_pqdtl_prices_into_document(existing, dockey, keep)

    put_dockey = int(existing.get("dockey") or dockey)
    status, preview, with_lines = _put_supplier_with_retry(
        client,
        base_path=base,
        existing=existing,
        supplier_row=supplier_row,
        timeout_seconds=timeout,
        include_sdsbranch=False,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"SQL API PUT purchaserequest/{put_dockey} returned HTTP {status}: {preview}")
    return {
        "synced": True,
        "dockey": put_dockey,
        "supplierCode": code,
        "httpStatus": status,
        "includedLines": with_lines,
        "lineCount": len(existing.get("sdsdocdetail") or []),
    }
