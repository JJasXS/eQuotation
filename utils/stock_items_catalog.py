"""Single entry point for stock-item catalog rows (create-quotation, orders, chat).

Priority (no duplicate sources in one response):
1. SQL Accounting HTTP API list GET when ``SQL_API_STOCK_ITEM_LIST_PATH`` is set and keys exist.
2. Direct Firebird ``ST_ITEM`` via ``fetch_stock_items``.
"""

from __future__ import annotations

import os
import re
from typing import Any

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings
from utils.sql_query_helpers import fetch_stock_items


def _dedupe_by_stock_code(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in items:
        code = str(row.get("CODE") or row.get("code") or "").strip()
        if code:
            key = code.upper()
            if key in seen:
                continue
            seen.add(key)
        out.append(row)
    return out


def _normalize_sql_api_stock_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Map SQL Accounting stockitem JSON (often lower/snake case) to legacy uppercase keys."""

    def pick(*names: str) -> Any:
        for n in names:
            if n in raw and raw[n] is not None:
                return raw[n]
        lower = {str(k).lower(): v for k, v in raw.items()}
        for n in names:
            v = lower.get(n.lower())
            if v is not None:
                return v
        return None

    def sval(key: str, *aliases: str) -> str:
        v = pick(key, *aliases)
        if v is None:
            return ""
        return str(v).strip()

    code = sval("CODE", "code")
    desc = sval("DESCRIPTION", "description")
    if not desc and code:
        desc = code

    uom = sval("UOM", "uom")
    suom = sval("SUOM", "suom")
    out: dict[str, Any] = {
        "CODE": code,
        "DESCRIPTION": desc,
        "UOM": uom,
        "SUOM": suom,
        "STOCKGROUP": sval("STOCKGROUP", "stockgroup"),
        "REMARK1": sval("REMARK1", "remark1"),
        "REMARK2": sval("REMARK2", "remark2"),
        "UDF_STDPRICE": pick("UDF_STDPRICE", "udf_stdprice", "refprice"),
        "UDF_MOQ": pick("UDF_MOQ", "udf_moq"),
        "UDF_DLEADTIME": pick("UDF_DLEADTIME", "udf_dleadtime"),
        "UDF_BUNDLE": pick("UDF_BUNDLE", "udf_bundle"),
        "UDF_WEIGHT": pick("UDF_WEIGHT", "udf_weight"),
        "UDF_WTP": pick("UDF_WTP", "udf_wtp"),
        "UDF_THICKNESS": pick("UDF_THICKNESS", "udf_thickness"),
        "UDF_WIDTH": pick("UDF_WIDTH", "udf_width"),
        "UDF_LENGTH": pick("UDF_LENGTH", "udf_length"),
        "UDF_MTYPE": pick("UDF_MTYPE", "udf_mtype"),
        "UDF_DS": pick("UDF_DS", "udf_ds"),
        "UDF_DP": pick("UDF_DP", "udf_dp"),
        "UDF_2UOM": pick("UDF_2UOM", "udf_2uom"),
        "UDF_FORMULA": pick("UDF_FORMULA", "udf_formula"),
    }
    # Carry through every stock-item UDF from SQL API (display layer picks what to show).
    for key, val in raw.items():
        key_s = str(key)
        if not key_s.lower().startswith("udf_"):
            continue
        norm_key = key_s.upper()
        if out.get(norm_key) is None and val is not None:
            out[norm_key] = val
    # Preserve nested structures when present (pricing/UOM consumers).
    for copy_key in ("sdsuom", "sdsbom", "dockey"):
        if copy_key in raw:
            out[copy_key] = raw[copy_key]
    return out


def derive_stock_prices_from_catalog(stockitems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build rows like ``fetch_stock_item_prices_for_chat``:
    ``CODE``, ``DESCRIPTION``, ``STOCKVALUE`` from ``UDF_STDPRICE``.
    """
    out: list[dict[str, Any]] = []
    for it in stockitems:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("DESCRIPTION") or "").strip()
        if not desc:
            continue
        raw_val = it.get("UDF_STDPRICE")
        if raw_val is None or str(raw_val).strip() == "":
            continue
        try:
            val = float(str(raw_val).replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        if val <= 0:
            continue
        code = str(it.get("CODE") or "").strip()
        out.append({"CODE": code, "DESCRIPTION": desc, "STOCKVALUE": raw_val})
    return out


def _parse_stock_list_json(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        raw_list = parsed
    elif isinstance(parsed, dict):
        raw_list = parsed.get("data")
        if raw_list is None:
            raw_list = parsed.get("items") or parsed.get("results")
    else:
        return []

    if not isinstance(raw_list, list):
        return []

    out: list[dict[str, Any]] = []
    for row in raw_list:
        if isinstance(row, dict):
            out.append(_normalize_sql_api_stock_row(row))
    return out


def _parse_stock_detail_json(parsed: Any) -> dict[str, Any] | None:
    """Normalize GET /stockitem/{code} body to one catalog row."""
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, dict):
            return _normalize_sql_api_stock_row(data)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return _normalize_sql_api_stock_row(data[0])
        if parsed.get("code") or parsed.get("CODE"):
            return _normalize_sql_api_stock_row(parsed)
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        return _normalize_sql_api_stock_row(parsed[0])
    return None


def fetch_stock_item_sql_api_by_code(code: str) -> dict[str, Any] | None:
    """
    Load one stock item from SQL Accounting GET ``/stockitem/{code}``.

    The list endpoint often omits UDFs; detail GET supplies ``udf_mtype`` for quotation lines.
    """
    item_code = str(code or "").strip()
    if not item_code:
        return None
    settings = load_sql_accounting_api_settings()
    if settings.dry_run or not settings.access_key or not settings.secret_key:
        return None
    path = (settings.stock_item_list_path or "").strip()
    if not path:
        return None
    client = SqlAccountingApiClient(settings)
    try:
        status, parsed, raw = client.get_json(
            settings.resolved_stock_item_detail_url(item_code),
            timeout_seconds=float(
                os.getenv("SQL_API_STOCK_ITEM_TIMEOUT_SECONDS") or settings.timeout_seconds
            ),
        )
    except SqlAccountingApiError as exc:
        print(f"[stock_items_catalog] SQL API stock detail failed for {item_code!r}: {exc}", flush=True)
        return None
    if status >= 400:
        snippet = (raw or "")[:300].replace("\n", " ")
        print(
            f"[stock_items_catalog] SQL API stock detail HTTP {status} for {item_code!r}: {snippet}",
            flush=True,
        )
        return None
    return _parse_stock_detail_json(parsed)


def _try_fetch_stock_items_sql_api() -> list[dict[str, Any]] | None:
    """
    Returns a non-empty list when the SQL API returned stock rows.
    Returns [] when the list endpoint is configured but returned no rows (caller may fall back).
    Returns None when SQL stock list is not configured, dry-run, or the request failed.
    """
    settings = load_sql_accounting_api_settings()
    if settings.dry_run:
        return None
    path = (settings.stock_item_list_path or "").strip()
    if not path:
        return None
    if not settings.access_key or not settings.secret_key:
        return None

    client = SqlAccountingApiClient(settings)
    try:
        status, parsed, raw = client.get_json(
            settings.resolved_stock_item_list_url(),
            timeout_seconds=float(
                os.getenv("SQL_API_STOCK_ITEM_TIMEOUT_SECONDS") or settings.timeout_seconds
            ),
        )
    except SqlAccountingApiError as exc:
        print(f"[stock_items_catalog] SQL API stock list failed: {exc}", flush=True)
        return None

    if status >= 400:
        snippet = (raw or "")[:400].replace("\n", " ")
        print(f"[stock_items_catalog] SQL API stock list HTTP {status}: {snippet}", flush=True)
        return None

    items = _parse_stock_list_json(parsed)
    items = _dedupe_by_stock_code(items)
    return items


def find_catalog_stock_item(
    *,
    code: str = "",
    description: str = "",
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Match a catalog row by CODE or DESCRIPTION (case-insensitive trim)."""
    code_q = str(code or "").strip()
    desc_q = str(description or "").strip()
    if not code_q and not desc_q:
        return None
    rows = items if items is not None else fetch_stock_items_catalog_uncached()

    def norm(s: str) -> str:
        return " ".join(str(s or "").strip().split())

    desc_n = norm(desc_q)
    code_n = norm(code_q)
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_code = norm(str(row.get("CODE") or row.get("code") or ""))
        row_desc = norm(str(row.get("DESCRIPTION") or row.get("description") or ""))
        if code_n and row_code and row_code.upper() == code_n.upper():
            return row
        if desc_n and row_desc and row_desc.upper() == desc_n.upper():
            return row
        if desc_n and row_code and row_code.upper() == desc_n.upper():
            return row
    return None


def catalog_row_needs_sql_api_detail(row: dict[str, Any] | None) -> bool:
    """List GET often omits weight UDFs; detail GET supplies ``udf_ds`` / ``udf_mtype``."""
    if not isinstance(row, dict):
        return True
    if not _catalog_field_str(row, "UDF_DS", "udf_ds"):
        return True
    if not _catalog_field_str(row, "UDF_MTYPE", "udf_mtype"):
        return True
    return False


_PR_CATALOG_DETAIL_UDF_KEYS = (
    "udf_thickness",
    "udf_width",
    "udf_length",
    "udf_dp",
    "udf_dfp",
    "udf_wtp",
    "udf_formula",
    "udf_costkg",
    "udf_mtype",
    "udf_2uom",
)


def catalog_row_needs_pr_stock_detail(row: dict[str, Any] | None) -> bool:
    """Purchase-request lines need dimensional / pricing UDFs from stockitem detail GET."""
    if not isinstance(row, dict):
        return True
    for key in _PR_CATALOG_DETAIL_UDF_KEYS:
        if not _catalog_field_str(row, key.upper(), key):
            return True
    return False


def _catalog_field_str(item: dict[str, Any], *keys: str) -> str:
    """Read a scalar catalog field; preserves ``0`` (do not treat as empty)."""
    lower = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        v = item.get(key)
        if v is None:
            v = lower.get(str(key).lower())
        if v is None:
            continue
        return str(v).strip()
    return ""


def _udf_camel_case(key: str) -> str:
    """``udf_ds`` / ``UDF_DS`` → ``udfDs`` for JSON APIs consumed by the browser."""
    k = str(key).strip().lower()
    if not k.startswith("udf_"):
        return k
    parts = k.split("_")
    if len(parts) < 2:
        return k
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _normalize_udf_api_key(key: str) -> str:
    """Normalize ``udfDs`` / ``UDF_DS`` / ``udf_ds`` → ``udf_ds`` for SQL Accounting payloads."""
    k = str(key).strip()
    if not k:
        return ""
    if k.lower().startswith("udf_"):
        return k.lower()
    if k.startswith("udf") and len(k) > 3:
        tail = k[3:]
        if tail and tail[0].isupper():
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", tail).lower()
            return f"udf_{snake}" if snake else k.lower()
    return k.lower()


def stock_item_udf_fields_from_row(item: dict[str, Any] | None) -> dict[str, Any]:
    """All ``udf_*`` scalars from a catalog / ST_ITEM row (any key casing)."""
    if not isinstance(item, dict):
        return {}
    out: dict[str, Any] = {}
    for key, val in item.items():
        norm = _normalize_udf_api_key(str(key))
        if not norm.startswith("udf_"):
            continue
        if val is None:
            continue
        if isinstance(val, bool):
            out[norm] = val
        elif isinstance(val, (int, float)):
            out[norm] = val
        else:
            s = str(val).strip()
            if s != "":
                out[norm] = s
    return out


def stock_item_udf_fields_for_js(item: dict[str, Any] | None) -> dict[str, str]:
    """CamelCase UDF map for pricing API / create-quotation JS."""
    raw = stock_item_udf_fields_from_row(item)
    out: dict[str, str] = {}
    for key, val in raw.items():
        if val is None:
            continue
        out[_udf_camel_case(key)] = str(val).strip() if not isinstance(val, str) else val.strip()
    return out


def stock_item_udf_fields_for_api(item: dict[str, Any] | None) -> dict[str, Any]:
    """Lowercase ``udf_*`` map for SQL Accounting document line POST bodies."""
    return dict(stock_item_udf_fields_from_row(item))


def _firebird_stock_row_for_code(item_code: str) -> dict[str, Any]:
    """Load ST_ITEM row (all UDF_* columns) when SQL API catalog row is missing fields."""
    code = str(item_code or "").strip()
    if not code:
        return {}
    try:
        from utils.db_utils import get_db_connection
        from utils.sql_query_helpers import fetch_stock_items

        con = get_db_connection()
        cur = con.cursor()
        rows = fetch_stock_items(cur)
        cur.close()
        con.close()
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_code = str(row.get("CODE") or "").strip()
            if row_code.upper() == code.upper():
                return row
    except Exception:
        pass
    return {}


def _resolve_catalog_stock_for_line(
    item: dict[str, Any],
    *,
    needs_sql_api_detail: Any | None = None,
) -> dict[str, Any]:
    """SQL API catalog first, then description/code match, then Firebird ST_ITEM."""
    code = str(
        item.get("itemCode") or item.get("itemcode") or item.get("code") or ""
    ).strip()
    desc = str(
        item.get("product") or item.get("description") or item.get("itemName") or ""
    ).strip()
    stock: dict[str, Any] = {}
    for blob_key in ("stockDetail", "stockApi", "stockCatalog", "catalogRow"):
        blob = item.get(blob_key)
        if isinstance(blob, dict):
            stock.update(blob)
    if not stock:
        hit = find_catalog_stock_item_prefer_sql_api(code=code, description=desc)
        if isinstance(hit, dict):
            stock = hit
    if not stock and (code or desc):
        hit = find_catalog_stock_item(code=code, description=desc)
        if isinstance(hit, dict):
            stock = hit
    detail_check = needs_sql_api_detail or catalog_row_needs_sql_api_detail
    if code and detail_check(stock):
        detail = fetch_stock_item_sql_api_by_code(code)
        if detail:
            stock = {**detail, **stock}
    if not _catalog_field_str(stock, "UDF_MTYPE", "udf_mtype") and code:
        fb = _firebird_stock_row_for_code(code)
        if fb:
            stock = {**fb, **stock}
    return stock


def _attach_catalog_stock_to_line_item(item: dict[str, Any], stock: dict[str, Any]) -> dict[str, Any]:
    """Merge catalog / ST_ITEM UDFs onto a document line dict (mutates ``item``)."""
    if stock:
        item["stockDetail"] = {**stock, **(item.get("stockDetail") or {})}
    for udf_key, udf_val in merge_item_and_stock_udf_fields_for_api(item, stock).items():
        if udf_val is None:
            continue
        item[udf_key] = udf_val
    for camel_key, camel_val in stock_item_udf_fields_for_js(stock).items():
        if camel_val is None or str(camel_val).strip() == "":
            continue
        if not str(item.get(camel_key) or "").strip():
            item[camel_key] = camel_val
    mtype = _catalog_field_str(stock, "UDF_MTYPE", "udf_mtype") or _catalog_field_str(
        item, "UDF_MTYPE", "udf_mtype"
    )
    if mtype:
        item["udf_mtype"] = mtype
        item["udfMtype"] = mtype
        item["UDF_MTYPE"] = mtype
    code = str(item.get("itemCode") or item.get("itemcode") or item.get("code") or "").strip()
    if code:
        item["itemCode"] = code
    elif stock:
        sc = str(stock.get("CODE") or stock.get("code") or "").strip()
        if sc:
            item["itemCode"] = sc
    return item


def enrich_quotation_submit_line_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    Attach catalog stock row + lowercase ``udf_*`` keys on a create-quotation line dict.

    Call after ``itemCode`` / product description are known so ``udf_mtype`` is copied from
    ST_ITEM / SQL API stockitem onto the line sent to ``/salesquotation``.
    """
    if not isinstance(item, dict):
        return item
    stock = _resolve_catalog_stock_for_line(item)
    return _attach_catalog_stock_to_line_item(item, stock)


def enrich_pr_submit_line_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    Attach stock catalog UDFs (thickness, width, length, density, formula, mtype, etc.)
    onto a purchase-request line before SQL API ``/purchaserequest`` sync.
    """
    if not isinstance(item, dict):
        return item
    stock = _resolve_catalog_stock_for_line(item, needs_sql_api_detail=catalog_row_needs_pr_stock_detail)
    return _attach_catalog_stock_to_line_item(item, stock)


def merge_item_and_stock_udf_fields_for_api(
    item: dict[str, Any],
    stock: dict[str, Any] | None,
) -> dict[str, Any]:
    """Line request fields override catalog / ST_ITEM master UDFs."""
    out = stock_item_udf_fields_for_api(stock)
    for key, val in (item or {}).items():
        norm = _normalize_udf_api_key(str(key))
        if not norm.startswith("udf_"):
            continue
        if val is None:
            continue
        out[norm] = val
    return out


def stock_item_dimension_display_fields(item: dict[str, Any] | None) -> dict[str, str]:
    """Thickness / width / length for create-quotation panel (from stockitem API / ST_ITEM)."""
    if not isinstance(item, dict):
        return {"udfThickness": "", "udfWidth": "", "udfLength": ""}
    return {
        "udfThickness": _catalog_field_str(item, "UDF_THICKNESS", "udf_thickness"),
        "udfWidth": _catalog_field_str(item, "UDF_WIDTH", "udf_width"),
        "udfLength": _catalog_field_str(item, "UDF_LENGTH", "udf_length"),
    }


def stock_item_catalog_display_fields(item: dict[str, Any] | None) -> dict[str, str]:
    """MOQ / lead / bundle / dimensions from a catalog row (SQL API shape normalized)."""
    if not isinstance(item, dict):
        return {
            "udfMoq": "",
            "udfDleadtime": "",
            "udfBundle": "",
            "udfThickness": "",
            "udfWidth": "",
            "udfLength": "",
        }
    dims = stock_item_dimension_display_fields(item)
    base = {
        "udfMoq": _catalog_field_str(item, "UDF_MOQ", "udf_moq"),
        "udfDleadtime": _catalog_field_str(item, "UDF_DLEADTIME", "udf_dleadtime"),
        "udfBundle": _catalog_field_str(item, "UDF_BUNDLE", "udf_bundle"),
        **dims,
    }
    for camel, val in stock_item_udf_fields_for_js(item).items():
        if camel not in base or not str(base.get(camel) or "").strip():
            base[camel] = val
    return base


def _merge_catalog_over_local(
    catalog_fields: dict[str, str],
    local_fields: dict[str, str],
) -> dict[str, str]:
    """SQL API / catalog values win; Firebird fills only missing keys."""
    out = dict(catalog_fields)
    for key, val in local_fields.items():
        if not str(out.get(key) or "").strip() and str(val or "").strip():
            out[key] = str(val).strip()
    return out


def find_catalog_stock_item_prefer_sql_api(
    *,
    code: str = "",
    description: str = "",
    cached_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
  Match a stock row: live SQL API list GET first, then ``cached_items`` / uncached catalog.

  Use this for per-product lookups (pricing, dimensions) so a Firebird-backed process
  cache does not mask a working SQL API.
    """
    sql_items = _try_fetch_stock_items_sql_api()
    if sql_items:
        hit = find_catalog_stock_item(code=code, description=description, items=sql_items)
        if hit:
            return hit
    if cached_items is not None:
        return find_catalog_stock_item(code=code, description=description, items=cached_items)
    return find_catalog_stock_item(code=code, description=description)


def fetch_stock_items_catalog_uncached() -> list[dict[str, Any]]:
    """Load catalog rows for dropdowns / chat; SQL Accounting list GET when configured, else Firebird."""
    sql_items = _try_fetch_stock_items_sql_api()
    # ``[]`` means SQL API responded successfully with no rows — do not replace with Firebird.
    if sql_items is not None:
        return sql_items

    from utils.db_utils import get_db_connection

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        return _dedupe_by_stock_code(fetch_stock_items(cur))
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if con:
                con.close()
        except Exception:
            pass
