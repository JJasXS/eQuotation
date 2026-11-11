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
from utils.firebird_helpers import _clean_text


def _api_root_url(path_env: str, default_path: str) -> str:
    settings = load_sql_accounting_api_settings()
    scheme = "https" if settings.use_tls else "http"
    host = settings.host.strip().rstrip("/")
    path = (os.getenv(path_env) or default_path).strip() or default_path
    if not path.startswith("/"):
        path = "/" + path
    cleaned = path.rstrip("/")
    return f"{scheme}://{host}{quote(cleaned, safe='/:?&=%')}"


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
    from utils.firebird_helpers import _get_table_columns, _pick_existing

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
    from utils.firebird_helpers import _as_decimal, _get_table_columns, _money, _pick_existing

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


def _overlay_pr_line_udfs_from_enriched(
    existing_lines: list[dict[str, Any]],
    enriched_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge ``udf_*`` from freshly built lines onto SQL API GET rows (preserve dtlkey)."""
    by_seq: dict[int, dict[str, Any]] = {}
    for idx, row in enumerate(enriched_lines or [], start=1):
        if not isinstance(row, dict):
            continue
        try:
            seq = int(row.get("seq") or idx)
        except (TypeError, ValueError):
            seq = idx
        by_seq[seq] = row

    merged: list[dict[str, Any]] = []
    for ln in existing_lines or []:
        if not isinstance(ln, dict):
            continue
        try:
            seq = int(ln.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        src = by_seq.get(seq) or {}
        patched = dict(ln)
        for key, val in src.items():
            if not str(key).lower().startswith("udf_"):
                continue
            if val is None:
                continue
            if isinstance(val, str) and not _clean_text(val):
                continue
            patched[key] = val
        merged.append(patched)
    return merged


def _local_pqdtl_udfs_by_dtlkey(
    request_dockey: int,
    keep_dtlkeys: set[int],
) -> dict[int, dict[str, Any]]:
    """Read PH_PQDTL ``UDF_*`` columns for SQL API PUT overlay."""
    if not keep_dtlkeys:
        return {}
    from utils.db_utils import get_db_connection
    from utils.firebird_helpers import _get_table_columns, _pick_existing

    con = get_db_connection()
    try:
        cur = con.cursor()
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
        dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        udf_cols = sorted(c for c in detail_cols if str(c).upper().startswith("UDF_"))
        if not fk_col or not dtl_col or not udf_cols:
            return {}

        placeholders = ", ".join(["?"] * len(keep_dtlkeys))
        select_cols = ", ".join([dtl_col, *udf_cols])
        cur.execute(
            f"""
            SELECT {select_cols}
            FROM PH_PQDTL
            WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
            """,
            tuple([int(request_dockey), *sorted(keep_dtlkeys)]),
        )
        out: dict[int, dict[str, Any]] = {}
        for row in cur.fetchall() or []:
            if not row:
                continue
            dtlkey = int(row[0])
            fields: dict[str, Any] = {}
            for idx, col in enumerate(udf_cols, start=1):
                val = row[idx]
                if val is None:
                    continue
                if isinstance(val, str) and not _clean_text(val):
                    continue
                fields[str(col).lower()] = val
            if fields:
                out[dtlkey] = fields
        return out
    finally:
        con.close()


def _merge_local_pqdtl_prices_into_document(
    document: dict[str, Any],
    request_dockey: int,
    keep_dtlkeys: set[int],
) -> dict[str, Any]:
    """Overlay Firebird PH_PQDTL pricing + UDFs onto SQL API sdsdocdetail before PUT."""
    pricing = _local_pqdtl_pricing_by_dtlkey(request_dockey, keep_dtlkeys)
    udfs = _local_pqdtl_udfs_by_dtlkey(request_dockey, keep_dtlkeys)
    if not pricing and not udfs:
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
        udf_hit = udfs.get(dtlkey) or {}
        if not hit and not udf_hit:
            merged.append(ln)
            continue
        patched = dict(ln)
        if hit:
            patched["unitprice"] = hit["unitprice"]
            if "tax" in patched or hit.get("tax"):
                patched["tax"] = hit["tax"]
            if "taxamt" in patched:
                patched["taxamt"] = hit["tax"]
            patched["amount"] = hit["amount"]
        for key, val in udf_hit.items():
            patched[key] = val
        merged.append(patched)
    return {**document, "sdsdocdetail": merged}


def sync_purchase_request_lines_sql_api_on_submit(
    request_dockey: int,
    request_number: str,
    validated: dict[str, Any],
) -> dict[str, Any]:
    """
    After e-PR create/submit, push stock UDFs onto SQL Accounting ``/purchaserequest`` lines.

    Uses enriched ``sdsdocdetail`` from the validated payload; POST when the document is
    missing on SQL API, otherwise PUT with UDF overlay on existing detail rows.
    """
    dockey = int(request_dockey or 0)
    docno = _clean_text(request_number)
    if dockey <= 0 and not docno:
        return {"skipped": True, "reason": "missing dockey/docno"}

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return {"skipped": True, "reason": "SQL API not configured"}

    from utils.procurement_pr_sql_api import build_purchaserequest_upstream_payload

    payload = build_purchaserequest_upstream_payload(
        validated,
        request_number=docno or _clean_text(validated.get("requestNumber")),
    )
    enriched_lines = payload.get("sdsdocdetail") if isinstance(payload.get("sdsdocdetail"), list) else []

    client = SqlAccountingApiClient(settings)
    timeout = min(60.0, settings.timeout_seconds + 15.0)
    base = _api_root_url("SQL_API_PURCHASE_REQUEST_PATH", "/purchaserequest")

    existing = _get_document(
        client,
        base_path=base,
        dockey=dockey,
        docno=docno,
        timeout_seconds=timeout,
    )

    if not existing:
        body = dict(payload)
        if dockey > 0 and "dockey" not in body:
            body["dockey"] = dockey
        status, _parsed, preview = client.post_json(base, body, timeout_seconds=timeout)
        if status < 200 or status >= 300:
            raise RuntimeError(f"SQL API POST purchaserequest returned HTTP {status}: {(preview or '')[:300]}")
        return {"synced": True, "mode": "post", "httpStatus": status, "dockey": dockey, "docno": docno}

    put_dockey = int(existing.get("dockey") or dockey)
    existing_lines = existing.get("sdsdocdetail") if isinstance(existing.get("sdsdocdetail"), list) else []
    merged_lines = _overlay_pr_line_udfs_from_enriched(existing_lines, enriched_lines)
    doc_for_put = {**existing, "sdsdocdetail": merged_lines, "changed": False, "dockey": put_dockey}
    allowed = _PUT_HEADER_KEYS | frozenset({"sdsdocdetail"})
    put_body = {k: v for k, v in doc_for_put.items() if k in allowed or k == "changed"}
    put_body["sdsdocdetail"] = _strip_readonly_nested_fields(merged_lines)
    if docno and not put_body.get("docno"):
        put_body["docno"] = docno

    status, preview = _put_document(
        client,
        base_path=base,
        dockey=put_dockey,
        payload=put_body,
        timeout_seconds=timeout,
    )
    if status < 200 or status >= 300:
        hdr_only = {k: v for k, v in put_body.items() if k != "sdsdocdetail"}
        status, preview = _put_document(
            client,
            base_path=base,
            dockey=put_dockey,
            payload=hdr_only,
            timeout_seconds=timeout,
        )
        if status < 200 or status >= 300:
            raise RuntimeError(f"SQL API PUT purchaserequest/{put_dockey} returned HTTP {status}: {preview}")
        return {
            "synced": True,
            "mode": "put_header_only",
            "httpStatus": status,
            "dockey": put_dockey,
            "docno": docno,
            "warning": "line UDF PUT rejected; header-only retry succeeded",
        }

    return {
        "synced": True,
        "mode": "put_lines",
        "httpStatus": status,
        "dockey": put_dockey,
        "docno": docno,
        "lineCount": len(merged_lines),
    }


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


def _iso_date_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return str(value.isoformat())[:10]
        except Exception:
            return ""
    text = _clean_text(value)
    return text[:10] if text else ""


def _fmt_money_api(value: Any) -> str:
    from utils.firebird_helpers import _as_decimal, _money

    return str(_money(_as_decimal(value, "0")))


def _all_local_pqdtl_keys(request_dockey: int) -> set[int]:
    from utils.db_utils import get_db_connection
    from utils.firebird_helpers import _get_table_columns, _pick_existing

    con = get_db_connection()
    try:
        cur = con.cursor()
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
        dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        if not fk_col or not dtl_col:
            return set()
        cur.execute(
            f"SELECT {dtl_col} FROM PH_PQDTL WHERE {fk_col} = ?",
            (int(request_dockey),),
        )
        out: set[int] = set()
        for row in cur.fetchall() or []:
            if not row or row[0] is None:
                continue
            try:
                out.add(int(row[0]))
            except (TypeError, ValueError):
                continue
        return out
    finally:
        con.close()


def _build_purchaserequest_body_from_local(
    request_dockey: int,
    *,
    keep_dtlkeys: set[int] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Build SQL API purchaserequest body from local PH_PQ / PH_PQDTL (header supplier blank)."""
    from utils.db_utils import get_db_connection
    from utils.firebird_helpers import _as_decimal, _get_table_columns, _money, _pick_existing

    dockey = int(request_dockey or 0)
    if dockey <= 0:
        return "", None

    con = get_db_connection()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        detail_cols = _get_table_columns(cur, "PH_PQDTL")
        key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
        if not key_col:
            return "", None

        docno_col = _pick_existing(header_cols, "DOCNO", "REQUESTNO", "PRNO")
        date_col = _pick_existing(header_cols, "DOCDATE", "REQUESTDATE")
        desc_col = _pick_existing(header_cols, "DESCRIPTION")
        project_col = _pick_existing(header_cols, "PROJECT")
        currency_col = _pick_existing(header_cols, "CURRENCYCODE", "CURRENCY")
        amt_col = _pick_existing(header_cols, "DOCAMT", "TOTALAMT", "TOTAL_AMOUNT")
        udf_status_col = _pick_existing(header_cols, "UDF_STATUS", "UDFSTATUS")
        note_col = _pick_existing(header_cols, "NOTES", "NOTE")

        select_hdr = [key_col]
        for col in (docno_col, date_col, desc_col, project_col, currency_col, amt_col, udf_status_col, note_col):
            if col and col not in select_hdr:
                select_hdr.append(col)
        cur.execute(
            f"SELECT {', '.join(select_hdr)} FROM PH_PQ WHERE {key_col} = ?",
            (dockey,),
        )
        hdr = cur.fetchone()
        if not hdr:
            return "", None

        by_name = {select_hdr[i].upper(): hdr[i] for i in range(len(select_hdr))}
        docno = _clean_text(by_name.get((docno_col or "").upper()) if docno_col else "")
        request_date = _iso_date_value(by_name.get((date_col or "").upper()) if date_col else None)
        if not request_date:
            from datetime import date as _date

            request_date = _date.today().isoformat()
        project = _clean_text(by_name.get((project_col or "").upper()) if project_col else "") or "----"
        currency = _clean_text(by_name.get((currency_col or "").upper()) if currency_col else "") or "----"
        total = _fmt_money_api(by_name.get((amt_col or "").upper()) if amt_col else 0)
        udf_status = _clean_text(by_name.get((udf_status_col or "").upper()) if udf_status_col else "")
        description = _clean_text(by_name.get((desc_col or "").upper()) if desc_col else "")
        note = _clean_text(by_name.get((note_col or "").upper()) if note_col else "")

        fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
        dtl_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
        seq_col = _pick_existing(detail_cols, "SEQ", "LINE_NO", "LINENO")
        item_col = _pick_existing(detail_cols, "ITEMCODE")
        loc_col = _pick_existing(detail_cols, "LOCATION", "LOC")
        line_project_col = _pick_existing(detail_cols, "PROJECT")
        desc1_col = _pick_existing(detail_cols, "DESCRIPTION")
        desc2_col = _pick_existing(detail_cols, "DESCRIPTION2")
        qty_col = _pick_existing(detail_cols, "QTY", "QUANTITY")
        uom_col = _pick_existing(detail_cols, "UOM")
        sqty_col = _pick_existing(detail_cols, "SQTY")
        suom_col = _pick_existing(detail_cols, "SUOMQTY")
        price_col = _pick_existing(detail_cols, "UNITPRICE", "UNIT_PRICE")
        tax_col = _pick_existing(detail_cols, "TAXAMT", "TAX")
        line_amt_col = _pick_existing(detail_cols, "AMOUNT", "TOTAL", "LINEAMOUNT")
        delivery_col = _pick_existing(detail_cols, "DELIVERYDATE", "DELIVERY_DATE")
        batch_col = _pick_existing(detail_cols, "BATCH")
        udf_cols = sorted(c for c in detail_cols if str(c).upper().startswith("UDF_"))
        if not fk_col or not dtl_col:
            return docno, None

        line_select = [dtl_col]
        optional_line = [
            seq_col, item_col, loc_col, line_project_col, desc1_col, desc2_col,
            qty_col, uom_col, sqty_col, suom_col, price_col, tax_col, line_amt_col,
            delivery_col, batch_col, *udf_cols,
        ]
        for col in optional_line:
            if col and col not in line_select:
                line_select.append(col)

        keep = {int(k) for k in (keep_dtlkeys or set()) if int(k) > 0}
        if keep:
            placeholders = ", ".join(["?"] * len(keep))
            cur.execute(
                f"""
                SELECT {', '.join(line_select)}
                FROM PH_PQDTL
                WHERE {fk_col} = ? AND {dtl_col} IN ({placeholders})
                ORDER BY {seq_col or dtl_col}
                """,
                tuple([dockey, *sorted(keep)]),
            )
        else:
            cur.execute(
                f"""
                SELECT {', '.join(line_select)}
                FROM PH_PQDTL
                WHERE {fk_col} = ?
                ORDER BY {seq_col or dtl_col}
                """,
                (dockey,),
            )

        details: list[dict[str, Any]] = []
        for seq_idx, row in enumerate(cur.fetchall() or [], start=1):
            if not row:
                continue
            named = {line_select[i].upper(): row[i] for i in range(len(line_select))}
            try:
                dtlkey = int(named.get((dtl_col or "").upper()) or 0)
            except (TypeError, ValueError):
                dtlkey = 0
            unit_price = float(_money(_as_decimal(named.get((price_col or "").upper()) if price_col else 0, "0")))
            tax = float(_money(_as_decimal(named.get((tax_col or "").upper()) if tax_col else 0, "0")))
            amount = float(_money(_as_decimal(named.get((line_amt_col or "").upper()) if line_amt_col else 0, "0")))
            if amount <= 0:
                qty = float(_money(_as_decimal(named.get((qty_col or "").upper()) if qty_col else 0, "0")))
                amount = float(_money(unit_price * qty + tax))
            try:
                seq_val = int(named.get((seq_col or "").upper()) or seq_idx) if seq_col else seq_idx
            except (TypeError, ValueError):
                seq_val = seq_idx
            line: dict[str, Any] = {
                "seq": seq_val,
                "itemcode": _clean_text(named.get((item_col or "").upper()) if item_col else ""),
                "location": _clean_text(named.get((loc_col or "").upper()) if loc_col else "") or "----",
                "batch": _clean_text(named.get((batch_col or "").upper()) if batch_col else "") or None,
                "project": _clean_text(named.get((line_project_col or "").upper()) if line_project_col else "") or project,
                "description": _clean_text(named.get((desc1_col or "").upper()) if desc1_col else ""),
                "description2": _clean_text(named.get((desc2_col or "").upper()) if desc2_col else "") or None,
                "description3": None,
                "qty": _fmt_money_api(named.get((qty_col or "").upper()) if qty_col else 0),
                "uom": _clean_text(named.get((uom_col or "").upper()) if uom_col else "") or "UNIT",
                "rate": None,
                "sqty": _fmt_money_api(
                    named.get((sqty_col or "").upper())
                    if sqty_col
                    else (named.get((qty_col or "").upper()) if qty_col else 0)
                ),
                "suomqty": _fmt_money_api(
                    named.get((suom_col or "").upper())
                    if suom_col
                    else (named.get((qty_col or "").upper()) if qty_col else 0)
                ),
                "unitprice": _fmt_money_api(unit_price),
                "deliverydate": _iso_date_value(named.get((delivery_col or "").upper()) if delivery_col else None) or request_date,
                "disc": "0",
                "tax": _fmt_money_api(tax),
                "amount": _fmt_money_api(amount),
                "changed": False,
            }
            if dtlkey > 0:
                line["dtlkey"] = dtlkey
            for col in udf_cols:
                val = named.get(str(col).upper())
                if val is None:
                    continue
                if isinstance(val, str) and not _clean_text(val):
                    continue
                line[str(col).lower()] = val
            details.append(line)

        body: dict[str, Any] = {
            "dockey": dockey,
            "docno": docno,
            "docnoex": docno,
            "docdate": request_date,
            "postdate": request_date,
            "taxdate": request_date,
            "code": "----",
            "companyname": "",
            "project": project,
            "currencycode": currency,
            "currencyrate": "1",
            "shipper": "----",
            "description": description,
            "status": 1,
            "docamt": total,
            "note": note,
            "daddress1": None,
            "sdsdocdetail": details,
            "changed": False,
            "udf_status": udf_status or "APPROVED",
        }
        return docno, body
    finally:
        con.close()


def _blank_header_supplier_fields(document: dict[str, Any]) -> dict[str, Any]:
    """Keep SQL PR header vendor empty; line UDF_SUPCODE / UDF_SUPNAME hold awards."""
    out = dict(document)
    out["code"] = "----"
    out["companyname"] = ""
    out["companyname2"] = ""
    return out


def sync_purchase_request_sql_api_after_awards(
    request_dockey: int,
    *,
    keep_dtlkeys: set[int] | None = None,
) -> dict[str, Any]:
    """
    After Save Item Awards: one SQL Accounting create-or-update for the same DOCNO/DOCKEY.

    Header supplier stays blank; line UDF_SUPCODE / UDF_SUPNAME (and awarded prices) come from local PH_PQDTL.
    """
    dockey = int(request_dockey or 0)
    if dockey <= 0:
        return {"skipped": True, "reason": "missing request dockey"}

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return {"skipped": True, "reason": "SQL API not configured"}

    keep = {int(k) for k in (keep_dtlkeys or set()) if int(k) > 0}
    if not keep:
        keep = _all_local_pqdtl_keys(dockey)

    docno, body = _build_purchaserequest_body_from_local(dockey, keep_dtlkeys=keep or None)
    if not body:
        return {"skipped": True, "reason": "local purchase request not found"}

    client = SqlAccountingApiClient(settings)
    timeout = min(60.0, settings.timeout_seconds + 15.0)
    base = _api_root_url("SQL_API_PURCHASE_REQUEST_PATH", "/purchaserequest")

    existing = _get_document(
        client,
        base_path=base,
        dockey=dockey,
        docno=docno,
        timeout_seconds=timeout,
    )

    if not existing:
        status, _parsed, preview = client.post_json(base, body, timeout_seconds=timeout)
        if status < 200 or status >= 300:
            raise RuntimeError(
                f"SQL API POST purchaserequest returned HTTP {status}: {(preview or '')[:300]}"
            )
        print(
            f"[PROCUREMENT] SQL API PR created after awards dockey={dockey} docno={docno}",
            flush=True,
        )
        return {
            "synced": True,
            "mode": "post",
            "httpStatus": status,
            "dockey": dockey,
            "docno": docno,
            "lineCount": len(body.get("sdsdocdetail") or []),
        }

    put_dockey = int(existing.get("dockey") or dockey)
    lines = existing.get("sdsdocdetail") if isinstance(existing.get("sdsdocdetail"), list) else []
    if keep:
        existing = {
            **existing,
            "sdsdocdetail": [
                ln
                for ln in lines
                if isinstance(ln, dict) and int(ln.get("dtlkey") or 0) in keep
            ],
        }
        existing = _merge_local_pqdtl_prices_into_document(existing, dockey, keep)
    existing = _blank_header_supplier_fields(existing)
    if docno and not existing.get("docno"):
        existing["docno"] = docno
    existing["changed"] = False
    existing["dockey"] = put_dockey
    if body.get("udf_status"):
        existing["udf_status"] = body["udf_status"]
    if body.get("docamt") is not None:
        existing["docamt"] = body["docamt"]

    allowed = _PUT_HEADER_KEYS | frozenset({"sdsdocdetail", "udf_status", "note"})
    put_body = {k: v for k, v in existing.items() if k in allowed or k == "changed"}
    put_body["sdsdocdetail"] = _strip_readonly_nested_fields(put_body.get("sdsdocdetail") or [])

    status, preview = _put_document(
        client,
        base_path=base,
        dockey=put_dockey,
        payload=put_body,
        timeout_seconds=timeout,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"SQL API PUT purchaserequest/{put_dockey} returned HTTP {status}: {preview}")

    print(
        f"[PROCUREMENT] SQL API PR updated after awards dockey={put_dockey} docno={docno}",
        flush=True,
    )
    return {
        "synced": True,
        "mode": "put",
        "httpStatus": status,
        "dockey": put_dockey,
        "docno": docno,
        "lineCount": len(put_body.get("sdsdocdetail") or []),
    }
