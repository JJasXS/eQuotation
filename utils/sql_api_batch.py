"""SQL Accounting GET /batch/* + POST /batch — resolve stock batch codes for e-PR lines."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings

logger = logging.getLogger(__name__)

_BATCH_CACHE_TTL_SECONDS = 60.0
_batch_cache: list[dict[str, Any]] | None = None
_batch_cache_at: float = 0.0


class SqlApiBatchError(RuntimeError):
    """SQL API batch list/create could not complete."""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_dim_part(value: Any) -> str:
    """Normalize a dimension for batch code (strip trailing .0; drop blank/zero)."""
    raw = _clean_text(value)
    if not raw:
        return ""
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return raw
    if num == 0:
        return ""
    if num == int(num):
        return str(int(num))
    # Strip trailing zeros from decimals (e.g. 12.50 -> 12.5)
    text = f"{num:.6f}".rstrip("0").rstrip(".")
    return text or ""


def build_batch_code(thickness: Any, width: Any, length: Any) -> str:
    """
    Build ``{T}mm*{W}mm*{L}mm`` (e.g. ``12mm*100mm*500mm``).

    Returns empty string unless all three dimensions are present and non-zero.
    """
    t = _normalize_dim_part(thickness)
    w = _normalize_dim_part(width)
    length_s = _normalize_dim_part(length)
    if not t or not w or not length_s:
        return ""
    return f"{t}mm*{w}mm*{length_s}mm"


def _batch_path() -> str:
    """``SQL_API_BATCH_PATH`` default ``/batch``; empty string disables the feature."""
    if "SQL_API_BATCH_PATH" not in os.environ:
        return "/batch"
    return (os.environ.get("SQL_API_BATCH_PATH") or "").strip()


def _parse_batch_list_json(parsed: Any) -> list[dict[str, Any]]:
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
    return [r for r in raw_list if isinstance(r, dict)]


def _invalidate_batch_cache() -> None:
    global _batch_cache, _batch_cache_at
    _batch_cache = None
    _batch_cache_at = 0.0


def fetch_batches(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """
    Load batches from SQL Accounting SigV4 GET ``/batch/*`` (fallback ``/batch``).

    Raises ``SqlApiBatchError`` when keys are missing or the API does not return HTTP 200.
    """
    global _batch_cache, _batch_cache_at

    if (
        not force_refresh
        and _batch_cache is not None
        and (time.monotonic() - _batch_cache_at) < _BATCH_CACHE_TTL_SECONDS
    ):
        return list(_batch_cache)

    path = _batch_path()
    if not path:
        raise SqlApiBatchError("SQL_API_BATCH_PATH is empty (batch resolution disabled).")

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        raise SqlApiBatchError(
            "SQL API keys are not configured. Set SQL_API_ACCESS_KEY and SQL_API_SECRET_KEY."
        )

    client = SqlAccountingApiClient(settings)
    configured = path if path.startswith("/") else f"/{path}"
    path_candidates: list[str] = []
    if configured.endswith("/*"):
        path_candidates.append(configured)
        base = configured[:-2] or "/batch"
        if base not in path_candidates:
            path_candidates.append(base)
    else:
        path_candidates.append(configured)
        wildcard = configured.rstrip("/") + "/*"
        if wildcard not in path_candidates:
            path_candidates.insert(0, wildcard)
    for alt in ("/batch/*", "/batch"):
        if alt not in path_candidates:
            path_candidates.append(alt)

    last_status: int | None = None
    last_snippet = ""
    seen_urls: set[str] = set()

    for list_path in path_candidates:
        url = settings.resolved_list_get_url(list_path)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            status, parsed, raw = client.get_json(
                url,
                timeout_seconds=min(15.0, settings.timeout_seconds + 5.0),
            )
        except SqlAccountingApiError as exc:
            last_snippet = str(exc)
            continue

        last_status = status
        if status != 200:
            last_snippet = (raw or "")[:300].replace("\n", " ")
            continue

        rows = _parse_batch_list_json(parsed)
        _batch_cache = rows
        _batch_cache_at = time.monotonic()
        return list(rows)

    hint = f" (last HTTP {last_status})" if last_status is not None else ""
    raise SqlApiBatchError(
        f"SQL API batch list returned no usable response from {path_candidates!r}{hint}: {last_snippet}"
    )


def find_batch_by_code(code: str, batches: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Case-insensitive match on batch ``code``."""
    needle = _clean_text(code).lower()
    if not needle:
        return None
    rows = batches if batches is not None else fetch_batches()
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_code = _clean_text(row.get("code") or row.get("CODE")).lower()
        if row_code and row_code == needle:
            return row
    return None


def _stock_field(stock: dict[str, Any] | None, *keys: str, default: str = "") -> str:
    if not isinstance(stock, dict):
        return default
    lower = {str(k).lower(): v for k, v in stock.items()}
    for key in keys:
        v = stock.get(key)
        if v is None:
            v = lower.get(str(key).lower())
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return s
    return default


def _dim_string(value: Any) -> str:
    part = _normalize_dim_part(value)
    return part if part else "0"


def build_create_batch_payload(
    code: str,
    *,
    thickness: Any,
    width: Any,
    length: Any,
    stock: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build POST /batch body from dimensions + ST_ITEM catalog fields."""
    item_code = _stock_field(stock, "CODE", "code", "itemcode", "itemCode")
    description = _stock_field(stock, "DESCRIPTION", "description") or None

    udf_dp = _stock_field(stock, "udf_dp", "UDF_DP", default="0")
    udf_ds = _stock_field(stock, "udf_ds", "UDF_DS") or udf_dp
    udf_dsys = _stock_field(stock, "udf_dsys", "UDF_DSYS") or udf_ds

    udf_dfp = _stock_field(stock, "udf_dfp", "UDF_DFP", default="1000000")
    udf_dfs = _stock_field(stock, "udf_dfs", "UDF_DFS") or udf_dfp
    udf_dfsys = _stock_field(stock, "udf_dfsys", "UDF_DFSYS") or udf_dfs

    udf_wtp = _stock_field(stock, "udf_wtp", "UDF_WTP", default="0")
    udf_wts = _stock_field(stock, "udf_wts", "UDF_WTS") or udf_wtp
    udf_wtsys = _stock_field(stock, "udf_wtsys", "UDF_WTSYS") or udf_wts

    batchitem: list[dict[str, Any]] = []
    if item_code:
        batchitem.append({"itemcode": item_code})

    return {
        "code": code,
        "description": description,
        "expdate": None,
        "mfgdate": None,
        "remark1": None,
        "remark2": None,
        "isactive": True,
        "attachments": None,
        "rowver": 0,
        "udf_thickness": _dim_string(thickness),
        "udf_width": _dim_string(width),
        "udf_length": _dim_string(length),
        "udf_ds": udf_ds,
        "udf_dp": udf_dp,
        "udf_dsys": udf_dsys,
        "udf_dfs": udf_dfs,
        "udf_dfp": udf_dfp,
        "udf_dfsys": udf_dfsys,
        "udf_wts": udf_wts,
        "udf_wtp": udf_wtp,
        "udf_wtsys": udf_wtsys,
        "udf_formula": _stock_field(stock, "udf_formula", "UDF_FORMULA") or None,
        "udf_2uom": _stock_field(stock, "udf_2uom", "UDF_2UOM") or None,
        "udf_mtype": _stock_field(stock, "udf_mtype", "UDF_MTYPE") or None,
        "udf_full": False,
        "batchitem": batchitem,
        "docnosetkey": None,
    }


def create_batch(
    code: str,
    *,
    thickness: Any,
    width: Any,
    length: Any,
    stock: dict[str, Any] | None,
) -> dict[str, Any]:
    """POST a new stock batch to SQL Accounting. Invalidates the in-process list cache."""
    path = _batch_path()
    if not path:
        raise SqlApiBatchError("SQL_API_BATCH_PATH is empty (batch resolution disabled).")

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        raise SqlApiBatchError(
            "SQL API keys are not configured. Set SQL_API_ACCESS_KEY and SQL_API_SECRET_KEY."
        )

    post_path = path if path.startswith("/") else f"/{path}"
    if post_path.endswith("/*"):
        post_path = post_path[:-2] or "/batch"
    url = settings.resolved_list_get_url(post_path)
    payload = build_create_batch_payload(
        code,
        thickness=thickness,
        width=width,
        length=length,
        stock=stock,
    )
    client = SqlAccountingApiClient(settings)
    try:
        status, parsed, raw = client.post_json(
            url,
            payload,
            timeout_seconds=min(30.0, settings.timeout_seconds + 10.0),
        )
    except SqlAccountingApiError as exc:
        raise SqlApiBatchError(f"SQL API POST /batch failed: {exc}") from exc

    if status not in (200, 201):
        snippet = (raw or "")[:300].replace("\n", " ")
        raise SqlApiBatchError(f"SQL API POST /batch returned HTTP {status}: {snippet}")

    _invalidate_batch_cache()
    if isinstance(parsed, dict):
        return parsed
    return {"code": code, **payload}


def _line_dim(item: dict[str, Any], *keys: str) -> str:
    stock = item.get("stockDetail") if isinstance(item.get("stockDetail"), dict) else {}
    for key in keys:
        v = item.get(key)
        if v is not None and str(v).strip() not in ("", "0"):
            return str(v).strip()
    for key in keys:
        v = stock.get(key) if isinstance(stock, dict) else None
        if v is None and isinstance(stock, dict):
            v = stock.get(key.upper())
        if v is not None and str(v).strip() not in ("", "0"):
            return str(v).strip()
    return ""


def attach_batch_codes_to_lines(line_items: Any) -> list[dict[str, Any]]:
    """
    For each PR line with thickness/width/length, resolve ``batch`` to
    ``{T}mm*{W}mm*{L}mm`` via GET /batch/* (create via POST /batch when missing).

    Fail-soft: logs warnings and leaves ``batch`` unset on API errors so e-PR submit
    is never blocked. Short-circuits with no network when keys are absent or path disabled.
    """
    if not isinstance(line_items, list):
        return []

    path = _batch_path()
    if not path:
        return [item for item in line_items if isinstance(item, dict)]

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        logger.warning("SQL API batch resolution skipped: keys not configured")
        return [item for item in line_items if isinstance(item, dict)]

    batches: list[dict[str, Any]] | None = None
    created_codes: set[str] = set()

    for item in line_items:
        if not isinstance(item, dict):
            continue
        existing = _clean_text(item.get("batch"))
        if existing:
            continue

        thickness = _line_dim(item, "udf_thickness", "udfThickness", "UDF_THICKNESS")
        width = _line_dim(item, "udf_width", "udfWidth", "UDF_WIDTH")
        length = _line_dim(item, "udf_length", "udfLength", "UDF_LENGTH")
        code = build_batch_code(thickness, width, length)
        if not code:
            continue

        try:
            if batches is None:
                batches = fetch_batches()
            found = find_batch_by_code(code, batches)
            if found:
                item["batch"] = _clean_text(found.get("code") or found.get("CODE")) or code
                continue

            if code.lower() in created_codes:
                item["batch"] = code
                continue

            stock = item.get("stockDetail") if isinstance(item.get("stockDetail"), dict) else {}
            if not stock:
                stock = {
                    "CODE": _clean_text(item.get("itemCode") or item.get("itemcode")),
                    "DESCRIPTION": _clean_text(item.get("description") or item.get("itemName")),
                }
                for k, v in item.items():
                    if str(k).lower().startswith("udf_") and v is not None:
                        stock[str(k).lower()] = v

            create_batch(
                code,
                thickness=thickness,
                width=width,
                length=length,
                stock=stock,
            )
            created_codes.add(code.lower())
            item["batch"] = code
            # Keep local cache in sync for subsequent lines in this request.
            if batches is not None:
                batches.append({"code": code, "udf_thickness": thickness, "udf_width": width, "udf_length": length})
        except Exception as exc:
            logger.warning(
                "SQL API batch resolve failed for code=%r item=%r: %s",
                code,
                _clean_text(item.get("itemCode") or item.get("itemcode")),
                exc,
            )

    return [item for item in line_items if isinstance(item, dict)]
