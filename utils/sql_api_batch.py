"""Stock batch master — SQL Accounting GET/POST ``/batch`` with Firebird fallback.

When ``master_read_allows_paid_rest()`` is true, uses paid SigV4 ``/batch``.
Otherwise reads/writes ``ST_BATCH`` (+ ``ST_ITEM_BATCH``) on the company Firebird
database (ACC-ANOZ local profile). Never silently falls back to paid REST.
"""
from __future__ import annotations

import logging
import os
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings
from utils.firebird_helpers import _clean_text, _get_table_columns, _table_exists

logger = logging.getLogger(__name__)

_BATCH_CACHE_TTL_SECONDS = 60.0
_batch_cache: list[dict[str, Any]] | None = None
_batch_cache_at: float = 0.0

_ST_BATCH_REST_FIELDS = (
    "AUTOKEY",
    "CODE",
    "DESCRIPTION",
    "EXPDATE",
    "MFGDATE",
    "REMARK1",
    "REMARK2",
    "ISACTIVE",
    "ATTACHMENTS",
    "ROWVER",
    "UDF_THICKNESS",
    "UDF_WIDTH",
    "UDF_LENGTH",
    "UDF_DS",
    "UDF_DP",
    "UDF_DSYS",
    "UDF_DFS",
    "UDF_DFP",
    "UDF_DFSYS",
    "UDF_WTS",
    "UDF_WTP",
    "UDF_WTSYS",
    "UDF_FORMULA",
    "UDF_2UOM",
    "UDF_MTYPE",
    "UDF_FULL",
)


class SqlApiBatchError(RuntimeError):
    """SQL API / Firebird batch list/create could not complete."""


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


_BATCH_DIM_RE = re.compile(
    r"^\s*(?P<t>\d+(?:\.\d+)?)\s*mm\s*\*\s*(?P<w>\d+(?:\.\d+)?)\s*mm\s*\*\s*(?P<l>\d+(?:\.\d+)?)\s*mm\s*$",
    re.IGNORECASE,
)


def parse_batch_code_dimensions(batch: Any) -> tuple[str, str, str]:
    """
    Inverse of :func:`build_batch_code`.

    Returns ``(thickness, width, length)`` strings, or empty strings when the
    batch code does not match ``{T}mm*{W}mm*{L}mm``.
    """
    text = _clean_text(batch)
    if not text:
        return "", "", ""
    match = _BATCH_DIM_RE.match(text)
    if not match:
        return "", "", ""
    return match.group("t"), match.group("w"), match.group("l")


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


def _rest_scalar(value: Any) -> Any:
    """Map Firebird cell values toward the REST ``/batch`` JSON shape."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return str(int(value))
        text = format(value, "f").rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip() or None
    if isinstance(value, str):
        return value.strip() or None
    return value


def _fb_row_to_rest(
    colnames: list[str],
    row: tuple[Any, ...],
    *,
    batchitem: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for idx, name in enumerate(colnames):
        out[name.lower()] = _rest_scalar(row[idx] if idx < len(row) else None)
    out["batchitem"] = list(batchitem or [])
    out.setdefault("docnosetkey", None)
    return out


def _open_batch_connection() -> Any:
    """Company Firebird connection (``set_db_config`` or process env)."""
    from utils.db_utils import build_firebird_dsn, get_db_connection

    try:
        return get_db_connection()
    except Exception:
        pass

    import fdb

    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        raise SqlApiBatchError(
            "Firebird DB_PATH is not configured for batch master (ST_BATCH)."
        )
    return fdb.connect(
        dsn=build_firebird_dsn(db_path, os.getenv("DB_HOST")),
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "").strip(),
        charset="UTF8",
    )


def _allocate_autokey(cur: Any, table_name: str, generator_name: str) -> int:
    """Next AUTOKEY from named generator, catching up past MAX when needed."""
    cur.execute(f"SELECT COALESCE(MAX(AUTOKEY), 0) FROM {table_name}")
    max_row = cur.fetchone()
    max_existing = int(max_row[0] if max_row and max_row[0] is not None else 0)
    cur.execute(f"SELECT GEN_ID({generator_name}, 1) FROM RDB$DATABASE")
    probe_row = cur.fetchone()
    if probe_row is None or probe_row[0] is None:
        raise SqlApiBatchError(f"Generator {generator_name} returned no value.")
    key = int(probe_row[0])
    if key > max_existing:
        return key
    jump = (max_existing + 1) - key
    cur.execute(f"SELECT GEN_ID({generator_name}, {int(jump)}) FROM RDB$DATABASE")
    catch_row = cur.fetchone()
    if catch_row is None or catch_row[0] is None:
        raise SqlApiBatchError(f"Generator {generator_name} catch-up failed.")
    return int(catch_row[0])


def _to_fb_number(value: Any, default: Any = None) -> Any:
    text = _clean_text(value)
    if not text:
        return default
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return default


def _load_batchitems_by_parent(cur: Any) -> dict[int, list[dict[str, Any]]]:
    if not _table_exists(cur, "ST_ITEM_BATCH"):
        return {}
    cols = _get_table_columns(cur, "ST_ITEM_BATCH")
    if "PARENTKEY" not in cols or "ITEMCODE" not in cols:
        return {}
    cur.execute("SELECT PARENTKEY, ITEMCODE FROM ST_ITEM_BATCH")
    grouped: dict[int, list[dict[str, Any]]] = {}
    for parent, itemcode in cur.fetchall() or []:
        if parent is None:
            continue
        code = _clean_text(itemcode)
        if not code:
            continue
        grouped.setdefault(int(parent), []).append({"itemcode": code})
    return grouped


def fetch_batches_from_firebird() -> list[dict[str, Any]]:
    """Load batch master rows from ``ST_BATCH`` (+ linked ``ST_ITEM_BATCH``)."""
    con = None
    cur = None
    try:
        con = _open_batch_connection()
        cur = con.cursor()
        if not _table_exists(cur, "ST_BATCH"):
            raise SqlApiBatchError("Firebird table ST_BATCH was not found.")
        cols = _get_table_columns(cur, "ST_BATCH")
        select_cols = [c for c in _ST_BATCH_REST_FIELDS if c in cols]
        if "CODE" not in select_cols:
            raise SqlApiBatchError("ST_BATCH.CODE column is missing.")
        cur.execute(f"SELECT {', '.join(select_cols)} FROM ST_BATCH ORDER BY AUTOKEY")
        raw_rows = cur.fetchall() or []
        items_by_parent = _load_batchitems_by_parent(cur)
        out: list[dict[str, Any]] = []
        for row in raw_rows:
            mapped = _fb_row_to_rest(select_cols, tuple(row))
            autokey = mapped.get("autokey")
            try:
                parent = int(autokey) if autokey is not None else None
            except (TypeError, ValueError):
                parent = None
            if parent is not None:
                mapped["batchitem"] = list(items_by_parent.get(parent) or [])
            out.append(mapped)
        return out
    except SqlApiBatchError:
        raise
    except Exception as exc:
        raise SqlApiBatchError(f"Firebird ST_BATCH list failed: {exc}") from exc
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if con is not None:
                con.close()
        except Exception:
            pass


def _fetch_st_batch_by_code(cur: Any, code: str) -> dict[str, Any] | None:
    cols = _get_table_columns(cur, "ST_BATCH")
    select_cols = [c for c in _ST_BATCH_REST_FIELDS if c in cols]
    if "CODE" not in select_cols:
        return None
    cur.execute(
        f"SELECT FIRST 1 {', '.join(select_cols)} FROM ST_BATCH "
        f"WHERE TRIM(UPPER(CODE)) = ?",
        (code.upper(),),
    )
    row = cur.fetchone()
    if not row:
        return None
    mapped = _fb_row_to_rest(select_cols, tuple(row))
    items_by_parent = _load_batchitems_by_parent(cur)
    try:
        parent = int(mapped["autokey"]) if mapped.get("autokey") is not None else None
    except (TypeError, ValueError):
        parent = None
    if parent is not None:
        mapped["batchitem"] = list(items_by_parent.get(parent) or [])
    return mapped


def _st_batch_insert_values(payload: dict[str, Any], *, autokey: int, code: str) -> dict[str, Any]:
    return {
        "AUTOKEY": autokey,
        "CODE": code,
        "DESCRIPTION": payload.get("description"),
        "EXPDATE": payload.get("expdate"),
        "MFGDATE": payload.get("mfgdate"),
        "REMARK1": payload.get("remark1"),
        "REMARK2": payload.get("remark2"),
        "ISACTIVE": bool(payload.get("isactive", True)),
        "ATTACHMENTS": payload.get("attachments"),
        "ROWVER": int(payload.get("rowver") or 0),
        "UDF_THICKNESS": _to_fb_number(payload.get("udf_thickness"), Decimal("0")),
        "UDF_WIDTH": _to_fb_number(payload.get("udf_width"), Decimal("0")),
        "UDF_LENGTH": _to_fb_number(payload.get("udf_length"), Decimal("0")),
        "UDF_DS": _to_fb_number(payload.get("udf_ds")),
        "UDF_DP": _to_fb_number(payload.get("udf_dp")),
        "UDF_DSYS": _to_fb_number(payload.get("udf_dsys")),
        "UDF_DFS": _to_fb_number(payload.get("udf_dfs")),
        "UDF_DFP": _to_fb_number(payload.get("udf_dfp")),
        "UDF_DFSYS": _to_fb_number(payload.get("udf_dfsys")),
        "UDF_WTS": _to_fb_number(payload.get("udf_wts")),
        "UDF_WTP": _to_fb_number(payload.get("udf_wtp")),
        "UDF_WTSYS": _to_fb_number(payload.get("udf_wtsys")),
        "UDF_FORMULA": payload.get("udf_formula"),
        "UDF_2UOM": payload.get("udf_2uom"),
        "UDF_MTYPE": payload.get("udf_mtype"),
        "UDF_FULL": bool(payload.get("udf_full", False)),
    }


def _insert_st_batch_row(cur: Any, payload: dict[str, Any], *, code: str) -> int:
    cols = _get_table_columns(cur, "ST_BATCH")
    autokey = _allocate_autokey(cur, "ST_BATCH", "ST_BATCH")
    insert_values = _st_batch_insert_values(payload, autokey=autokey, code=code)
    use_cols = [c for c in insert_values if c in cols]
    placeholders = ", ".join("?" for _ in use_cols)
    cur.execute(
        f"INSERT INTO ST_BATCH ({', '.join(use_cols)}) VALUES ({placeholders})",
        [insert_values[c] for c in use_cols],
    )
    return autokey


def _insert_st_item_batch_link(cur: Any, *, parent_key: int, item_code: str) -> None:
    if not item_code or not _table_exists(cur, "ST_ITEM_BATCH"):
        return
    item_cols = _get_table_columns(cur, "ST_ITEM_BATCH")
    if not {"AUTOKEY", "PARENTKEY", "ITEMCODE"} <= item_cols:
        return
    item_key = _allocate_autokey(cur, "ST_ITEM_BATCH", "ST_ITEM_BATCH")
    cur.execute(
        "INSERT INTO ST_ITEM_BATCH (AUTOKEY, PARENTKEY, ITEMCODE) VALUES (?, ?, ?)",
        (item_key, parent_key, item_code),
    )


def _payload_item_code(payload: dict[str, Any]) -> str:
    batchitem = payload.get("batchitem") if isinstance(payload.get("batchitem"), list) else []
    if not batchitem or not isinstance(batchitem[0], dict):
        return ""
    return _clean_text(batchitem[0].get("itemcode") or batchitem[0].get("ITEMCODE"))


def create_batch_in_firebird(
    code: str,
    *,
    thickness: Any,
    width: Any,
    length: Any,
    stock: dict[str, Any] | None,
) -> dict[str, Any]:
    """Insert ``ST_BATCH`` (+ optional ``ST_ITEM_BATCH``) matching POST ``/batch`` semantics."""
    payload = build_create_batch_payload(
        code,
        thickness=thickness,
        width=width,
        length=length,
        stock=stock,
    )
    want_code = _clean_text(payload.get("code") or code)
    if not want_code:
        raise SqlApiBatchError("Batch code is required for Firebird create.")
    if len(want_code) > 30:
        raise SqlApiBatchError(
            f"Batch code exceeds ST_BATCH.CODE length 30: {want_code!r}"
        )

    con = None
    cur = None
    try:
        con = _open_batch_connection()
        cur = con.cursor()
        if not _table_exists(cur, "ST_BATCH"):
            raise SqlApiBatchError("Firebird table ST_BATCH was not found.")

        existing = _fetch_st_batch_by_code(cur, want_code)
        if existing:
            return existing

        autokey = _insert_st_batch_row(cur, payload, code=want_code)
        _insert_st_item_batch_link(
            cur, parent_key=autokey, item_code=_payload_item_code(payload)
        )
        con.commit()
        created = _fetch_st_batch_by_code(cur, want_code)
        return created or {**payload, "autokey": autokey, "code": want_code}
    except SqlApiBatchError:
        if con is not None:
            try:
                con.rollback()
            except Exception:
                pass
        raise
    except Exception as exc:
        if con is not None:
            try:
                con.rollback()
            except Exception:
                pass
        try:
            if cur is not None:
                raced = _fetch_st_batch_by_code(cur, want_code)
                if raced:
                    return raced
        except Exception:
            pass
        raise SqlApiBatchError(f"Firebird ST_BATCH create failed: {exc}") from exc
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if con is not None:
                con.close()
        except Exception:
            pass


def _paged_batch_rows(
    client: SqlAccountingApiClient,
    settings: Any,
    list_path: str,
    *,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Collect all ``data`` rows from paginated GET ``/batch`` responses."""
    limit = max(1, min(500, int(os.getenv("SQL_API_REFERENCE_PAGE_LIMIT") or "200")))
    all_rows: list[dict[str, Any]] = []
    offset = 0
    total_expected: int | None = None

    while True:
        url = settings.resolved_list_get_url(list_path, {"offset": offset, "limit": limit})
        status, parsed, raw = client.get_json(url, timeout_seconds=timeout_seconds)
        if status != 200:
            snippet = (raw or "")[:300].replace("\n", " ")
            raise SqlAccountingApiError(
                f"SQL API batch list HTTP {status}: {snippet}",
                status_code=status,
                response_body=raw,
            )
        if not isinstance(parsed, dict):
            break
        chunk = parsed.get("data")
        if not isinstance(chunk, list):
            break
        for row in chunk:
            if isinstance(row, dict):
                all_rows.append(row)
        pag = parsed.get("pagination")
        if isinstance(pag, dict) and pag.get("count") is not None:
            try:
                total_expected = int(pag.get("count") or 0)
            except (TypeError, ValueError):
                total_expected = None
        if not chunk:
            break
        if total_expected is not None and len(all_rows) >= total_expected:
            break
        if len(chunk) < limit:
            break
        offset += limit
        if offset > 200_000:
            break
    return all_rows


def _fetch_batches_via_rest() -> list[dict[str, Any]]:
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
    if configured.endswith("/*"):
        configured = configured[:-2] or "/batch"
    configured = configured.rstrip("/") or "/batch"

    path_candidates: list[str] = [configured]
    for alt in ("/batch", "/batch/*"):
        if alt not in path_candidates:
            path_candidates.append(alt)

    last_status: int | None = None
    last_snippet = ""
    timeout = min(30.0, settings.timeout_seconds + 10.0)

    for list_path in path_candidates:
        try:
            if list_path.endswith("/*"):
                url = settings.resolved_list_get_url(list_path)
                status, parsed, raw = client.get_json(url, timeout_seconds=timeout)
                last_status = status
                if status != 200:
                    last_snippet = (raw or "")[:300].replace("\n", " ")
                    continue
                rows = _parse_batch_list_json(parsed)
            else:
                rows = _paged_batch_rows(client, settings, list_path, timeout_seconds=timeout)
        except SqlAccountingApiError as exc:
            last_snippet = str(exc)
            continue

        if list_path.endswith("/*") and len(rows) <= 1:
            last_snippet = f"{list_path} returned {len(rows)} row(s); preferring paginated /batch"
            continue

        if rows:
            return list(rows)

        if not list_path.endswith("/*"):
            return []

    hint = f" (last HTTP {last_status})" if last_status is not None else ""
    raise SqlApiBatchError(
        f"SQL API batch list returned no usable response from {path_candidates!r}{hint}: {last_snippet}"
    )


def fetch_batches(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """
    Load batches from Firebird ``ST_BATCH`` or paid SigV4 GET ``/batch``.

    Note: ``GET /batch/*`` often returns a truncated single-row sample and must not be
    preferred over the paginated ``/batch`` list when Rest is enabled.

    Raises ``SqlApiBatchError`` when the active provider cannot return a usable list.
    """
    global _batch_cache, _batch_cache_at

    if (
        not force_refresh
        and _batch_cache is not None
        and (time.monotonic() - _batch_cache_at) < _BATCH_CACHE_TTL_SECONDS
    ):
        return list(_batch_cache)

    from api.config.sql_accounting_master_read import master_read_allows_paid_rest

    if master_read_allows_paid_rest():
        rows = _fetch_batches_via_rest()
    else:
        rows = fetch_batches_from_firebird()

    _batch_cache = rows
    _batch_cache_at = time.monotonic()
    return list(rows)


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


def _create_batch_via_rest(
    code: str,
    *,
    thickness: Any,
    width: Any,
    length: Any,
    stock: dict[str, Any] | None,
) -> dict[str, Any]:
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

    if isinstance(parsed, dict):
        return parsed
    return {"code": code, **payload}


def create_batch(
    code: str,
    *,
    thickness: Any,
    width: Any,
    length: Any,
    stock: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create a stock batch via Firebird or paid POST ``/batch``. Invalidates list cache."""
    from api.config.sql_accounting_master_read import master_read_allows_paid_rest

    if master_read_allows_paid_rest():
        result = _create_batch_via_rest(
            code, thickness=thickness, width=width, length=length, stock=stock
        )
    else:
        result = create_batch_in_firebird(
            code, thickness=thickness, width=width, length=length, stock=stock
        )
    _invalidate_batch_cache()
    return result


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
    ``{T}mm*{W}mm*{L}mm`` via batch master (create when missing).

    Fail-soft: logs warnings and leaves ``batch`` unset on errors so e-PR submit
    is never blocked. Short-circuits when path disabled. Paid REST keys are only
    required when master-read Rest is enabled.
    """
    if not isinstance(line_items, list):
        return []

    path = _batch_path()
    if not path:
        return [item for item in line_items if isinstance(item, dict)]

    from api.config.sql_accounting_master_read import master_read_allows_paid_rest

    if master_read_allows_paid_rest():
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
            if batches is not None:
                batches.append(
                    {
                        "code": code,
                        "udf_thickness": thickness,
                        "udf_width": width,
                        "udf_length": length,
                    }
                )
        except Exception as exc:
            logger.warning(
                "SQL API batch resolve failed for code=%r item=%r: %s",
                code,
                _clean_text(item.get("itemCode") or item.get("itemcode")),
                exc,
            )

    return [item for item in line_items if isinstance(item, dict)]
