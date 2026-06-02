"""SQL Accounting GET /supplier — master fields for e-Procurement (currency on purchase request)."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from api.clients import SqlAccountingApiClient
from api.config import load_sql_accounting_api_settings

from utils.customer_display import _format_currency_display_value


def _supplier_rows_from_sql_json(parsed: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [r for r in parsed if isinstance(r, dict)]
    if not isinstance(parsed, dict):
        return []
    data = parsed.get("data")
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return [parsed]


def _supplier_detail_urls(supplier_code: str) -> list[str]:
    settings = load_sql_accounting_api_settings()
    host = settings.host.strip().rstrip("/")
    scheme = "https" if settings.use_tls else "http"
    raw_path = (
        (os.getenv("SQL_API_SUPPLIER_DETAIL_PATH") or "").strip()
        or "/supplier/*"
    )
    if not raw_path.startswith("/"):
        raw_path = "/" + raw_path
    detail_path = (raw_path.replace("*", "").rstrip("/") or "/supplier").strip()
    code_str = quote(str(supplier_code).strip(), safe="")
    return [
        f"{scheme}://{host}{quote(detail_path, safe='/:?&=%')}?code={code_str}",
        f"{scheme}://{host}{quote(raw_path, safe='/:?&=%')}?code={code_str}",
        f"{scheme}://{host}{quote(detail_path.rstrip('/') + '/' + str(supplier_code).strip(), safe='/:?&=%')}",
    ]


def fetch_sql_api_supplier_row(supplier_code: str) -> tuple[dict[str, Any] | None, int | None]:
    """
    Return the first supplier row from SQL API GET ``/supplier?code=…``.

    Returns ``(row_dict, http_status)``; ``(None, status)`` on failure; ``(None, None)`` if not configured.
    """
    code = str(supplier_code or "").strip()
    if not code:
        return None, None

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return None, None

    client = SqlAccountingApiClient(settings)
    seen: set[str] = set()
    last_status: int | None = None

    for url in _supplier_detail_urls(code):
        if url in seen:
            continue
        seen.add(url)
        status, parsed, _raw = client.get_json(url, timeout_seconds=min(15.0, settings.timeout_seconds + 5.0))
        last_status = status
        if status != 200:
            continue
        rows = _supplier_rows_from_sql_json(parsed)
        if rows:
            return rows[0], status

    return None, last_status


def sql_api_currency_and_code(supplier_code: str) -> dict[str, str]:
    """Currency + code from SQL API GET /supplier only (no Firebird/MYR fallback)."""
    row, status = fetch_sql_api_supplier_row(supplier_code)
    base = {
        "code": str(supplier_code or "").strip(),
        "currencycode": "",
        "httpStatus": str(status) if status is not None else "",
    }
    if not row:
        return base

    code = str(row.get("code") or supplier_code or "").strip()
    cc = _format_currency_display_value(row.get("currencycode") or row.get("currencyCode"))
    return {"code": code, "currencycode": cc, "httpStatus": str(status) if status is not None else "200"}


def supplier_emails_from_sql_api_row(row: dict[str, Any] | None) -> list[str]:
    """Unique emails from SQL API supplier row (udf_email, udf_email01..15). No Firebird overlay."""
    if not isinstance(row, dict):
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(val: Any) -> None:
        v = str(val or "").strip()
        if not v:
            return
        low = v.lower()
        if low in seen:
            return
        seen.add(low)
        out.append(v)

    for key in ("udf_email", "UDF_EMAIL", "email", "EMAIL"):
        add(row.get(key))
    for i in range(1, 16):
        add(row.get(f"udf_email{i:02d}"))
        add(row.get(f"UDF_EMAIL{i:02d}"))
    return out


def supplier_primary_email_from_sql_api_row(row: dict[str, Any] | None) -> str:
    emails = supplier_emails_from_sql_api_row(row)
    return emails[0] if emails else ""


def enrich_supplier_row_for_procurement(row: dict[str, Any]) -> dict[str, Any]:
    """Expose primary ``email`` / ``udf_email`` from SQL API UDF fields for the Create e-PR UI."""
    out = dict(row)
    emails = supplier_emails_from_sql_api_row(row)
    if emails:
        out["email"] = emails[0]
        out["udf_email"] = emails[0]
    out["emails"] = emails
    return out
