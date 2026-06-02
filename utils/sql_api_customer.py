"""SQL Accounting GET /customer — master fields for create-quotation display."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from api.clients import SqlAccountingApiClient
from api.config import load_sql_accounting_api_settings

from utils.customer_display import _format_currency_display_value


def _customer_rows_from_sql_json(parsed: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
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


def _customer_detail_urls(customer_code: str) -> list[str]:
    settings = load_sql_accounting_api_settings()
    host = settings.host.strip().rstrip("/")
    scheme = "https" if settings.use_tls else "http"
    raw_path = (
        (os.getenv("SQL_API_CUSTOMER_DETAIL_PATH") or "").strip()
        or (settings.customer_create_path or "").strip()
        or "/customer/*"
    )
    if not raw_path.startswith("/"):
        raw_path = "/" + raw_path
    detail_path = (raw_path.replace("*", "").rstrip("/") or "/customer").strip()
    code_str = quote(str(customer_code).strip(), safe="")
    return [
        f"{scheme}://{host}{quote(detail_path, safe='/:?&=%')}?code={code_str}",
        f"{scheme}://{host}{quote(raw_path, safe='/:?&=%')}?code={code_str}",
        f"{scheme}://{host}{quote(detail_path.rstrip('/') + '/' + str(customer_code).strip(), safe='/:?&=%')}",
    ]


def fetch_sql_api_customer_row(customer_code: str) -> tuple[dict[str, Any] | None, int | None]:
    """
    Return the first customer row from SQL API GET ``/customer?code=…``.

    Returns ``(row_dict, http_status)``; ``(None, status)`` on failure; ``(None, None)`` if not configured.
    """
    code = str(customer_code or "").strip()
    if not code:
        return None, None

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return None, None

    client = SqlAccountingApiClient(settings)
    seen: set[str] = set()
    last_status: int | None = None

    for url in _customer_detail_urls(code):
        if url in seen:
            continue
        seen.add(url)
        status, parsed, _raw = client.get_json(url, timeout_seconds=min(15.0, settings.timeout_seconds + 5.0))
        last_status = status
        if status != 200:
            continue
        rows = _customer_rows_from_sql_json(parsed)
        if rows:
            return rows[0], status

    return None, last_status


def sql_api_currency_and_code(customer_code: str) -> dict[str, str]:
    """Currency + code from SQL API GET /customer only (e.g. ``----``; never Firebird/MYR fallback)."""
    row, status = fetch_sql_api_customer_row(customer_code)
    base = {
        "code": str(customer_code or "").strip(),
        "currencycode": "",
        "httpStatus": str(status) if status is not None else "",
    }
    if not row:
        return base

    code = str(row.get("code") or customer_code or "").strip()
    cc = _format_currency_display_value(row.get("currencycode") or row.get("currencyCode"))
    return {"code": code, "currencycode": cc, "httpStatus": str(status) if status is not None else "200"}


def apply_sql_api_currency_to_customer_payload(payload: dict[str, Any], customer_code: str) -> dict[str, Any]:
    """Overwrite CODE/CURRENCYCODE on get_user_info payload from SQL API GET /customer."""
    if not isinstance(payload, dict):
        return payload

    fields = sql_api_currency_and_code(customer_code)
    out = dict(payload)
    code = fields.get("code") or str(customer_code or "").strip()
    cc = str(fields.get("currencycode") or "").strip()
    # Do not fall back to Firebird AR_CUSTOMER or legacy CURRENCYCODE (may differ from SQL API cloud).

    if code:
        out["CODE"] = code
        out["sqlApiCustomerCode"] = code
    out["CURRENCYCODE"] = cc
    out["sqlApiCurrencyCode"] = cc

    scalars = dict(out.get("customerScalars") or {})
    if code:
        scalars["code"] = code
    scalars["currencycode"] = cc
    out["customerScalars"] = scalars

    display = out.get("displayFields")
    if isinstance(display, list):
        found = False
        for row in display:
            if not isinstance(row, dict):
                continue
            if str(row.get("key") or "").lower() == "currencycode":
                row["value"] = cc if cc != "" else "—"
                found = True
        if not found and cc != "":
            display.append({"key": "currencycode", "label": "Currencycode", "value": cc})

    return out
