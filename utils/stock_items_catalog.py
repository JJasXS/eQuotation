"""Single entry point for stock-item catalog rows (create-quotation, orders, chat).

Priority (no duplicate sources in one response):
1. SQL Accounting HTTP API list GET when ``SQL_API_STOCK_ITEM_LIST_PATH`` is set and keys exist.
2. Direct Firebird ``ST_ITEM`` via ``fetch_stock_items``.
"""

from __future__ import annotations

import os
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

    out: dict[str, Any] = {
        "CODE": code,
        "DESCRIPTION": desc,
        "STOCKGROUP": sval("STOCKGROUP", "stockgroup"),
        "REMARK1": sval("REMARK1", "remark1"),
        "REMARK2": sval("REMARK2", "remark2"),
        "UDF_STDPRICE": pick("UDF_STDPRICE", "udf_stdprice", "refprice"),
        "UDF_MOQ": pick("UDF_MOQ", "udf_moq"),
        "UDF_DLEADTIME": pick("UDF_DLEADTIME", "udf_dleadtime"),
        "UDF_BUNDLE": pick("UDF_BUNDLE", "udf_bundle"),
        "UDF_WEIGHT": pick("UDF_WEIGHT", "udf_weight"),
    }
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


def fetch_stock_items_catalog_uncached() -> list[dict[str, Any]]:
    """Load catalog rows for dropdowns / chat; SQL Accounting list GET when configured, else Firebird."""
    sql_items = _try_fetch_stock_items_sql_api()
    if sql_items:
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
