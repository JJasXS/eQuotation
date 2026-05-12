"""Load AREA / CURRENCY code lists from SQL Accounting list APIs (SigV4 GET)."""
from __future__ import annotations

import os
from typing import Any

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config.sql_accounting_api import SqlAccountingApiSettings, load_sql_accounting_api_settings


def _dedupe_preserve_order(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        key = c.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _paged_list_rows(
    client: SqlAccountingApiClient,
    settings: SqlAccountingApiSettings,
    list_path: str,
    *,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Collect all ``data`` rows from paginated SQL API list responses."""
    limit = max(1, min(500, int(os.getenv("SQL_API_REFERENCE_PAGE_LIMIT") or "200")))
    all_rows: list[dict[str, Any]] = []
    offset = 0
    total_expected = None

    while True:
        url = settings.resolved_list_get_url(list_path, {"offset": offset, "limit": limit})
        status, parsed, raw = client.get_json(url, timeout_seconds=timeout_seconds)
        if status >= 400:
            snippet = (raw or "")[:400].replace("\n", " ")
            raise SqlAccountingApiError(
                f"SQL API list HTTP {status}: {snippet}",
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


def _row_code(row: dict[str, Any]) -> str:
    v = row.get("code")
    if v is None:
        v = row.get("CODE")
    return str(v or "").strip()


def _row_is_active(row: dict[str, Any]) -> bool:
    v = row.get("isactive")
    if v is None:
        v = row.get("ISACTIVE")
    if v is None:
        return True
    if v is False or v == 0:
        return False
    if isinstance(v, str) and v.strip().lower() in ("false", "0", "no"):
        return False
    return True


def fetch_area_codes_sql_api() -> list[str] | None:
    """
    Return area ``code`` values from GET ``/area`` (or ``SQL_API_AREA_PATH``), or ``None`` if SQL API
    is not used (no keys, dry-run, path disabled, or request failed).
    """
    settings = load_sql_accounting_api_settings()
    if settings.dry_run or not settings.access_key or not settings.secret_key:
        return None
    path = (settings.area_list_path or "").strip()
    if not path:
        return None

    timeout = float(os.getenv("SQL_API_REFERENCE_LIST_TIMEOUT_SECONDS") or settings.timeout_seconds)
    client = SqlAccountingApiClient(settings)
    try:
        rows = _paged_list_rows(client, settings, path, timeout_seconds=timeout)
    except SqlAccountingApiError as exc:
        print(f"[sql_api_reference_lists] area list failed: {exc}", flush=True)
        return None

    codes: list[str] = []
    for row in rows:
        if not _row_is_active(row):
            continue
        c = _row_code(row)
        if c:
            codes.append(c)
    return _dedupe_preserve_order(codes)


def fetch_currency_codes_sql_api() -> list[str] | None:
    """
    Return currency ``code`` values from GET ``/currency`` (or ``SQL_API_CURRENCY_PATH``), or ``None``
    if SQL API is not used or the request failed.
    """
    settings = load_sql_accounting_api_settings()
    if settings.dry_run or not settings.access_key or not settings.secret_key:
        return None
    path = (settings.currency_list_path or "").strip()
    if not path:
        return None

    timeout = float(os.getenv("SQL_API_REFERENCE_LIST_TIMEOUT_SECONDS") or settings.timeout_seconds)
    client = SqlAccountingApiClient(settings)
    try:
        rows = _paged_list_rows(client, settings, path, timeout_seconds=timeout)
    except SqlAccountingApiError as exc:
        print(f"[sql_api_reference_lists] currency list failed: {exc}", flush=True)
        return None

    codes: list[str] = []
    for row in rows:
        c = _row_code(row)
        if c:
            codes.append(c)
    return _dedupe_preserve_order(codes)
