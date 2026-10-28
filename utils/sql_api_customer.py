"""SQL Accounting GET /customer — master fields for create-quotation display."""
from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

_CURRENCY_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_CURRENCY_CACHE_SECONDS = 120.0

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

    from api.clients import SqlAccountingApiError

    client = SqlAccountingApiClient(settings)
    seen: set[str] = set()
    last_status: int | None = None
    best: dict[str, Any] | None = None
    best_status: int | None = None

    urls = _customer_detail_urls(code)
    # Default: one URL shape only (fast). Set EQ_CUSTOMER_SQL_TRY_ALL=1 to probe alternates.
    try_all = str(os.getenv("EQ_CUSTOMER_SQL_TRY_ALL", "")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not try_all:
        urls = urls[:1]

    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        try:
            # One signed attempt. Customer display must not stack transport retries.
            # Keep Create Quotation snappy: one short attempt per URL shape.
            status, parsed, _raw = client.get_json(
                url,
                timeout_seconds=2.5,
                max_attempts=1,
                retry_transport=False,
            )
        except SqlAccountingApiError:
            # The host is unreachable. Other path shapes on the same host will fail too.
            return best, best_status if best is not None else None
        last_status = status
        if status != 200:
            continue
        rows = _customer_rows_from_sql_json(parsed)
        if not rows:
            continue
        row = rows[0]
        if _sql_customer_row_has_address(row):
            return row, status
        if best is None:
            best = row
            best_status = status

    return best, best_status if best is not None else last_status


def _sql_customer_row_has_address(row: dict[str, Any]) -> bool:
    for key in ("address1", "ADDRESS1"):
        if str(row.get(key) or "").strip():
            return True
    branches = row.get("sdsbranch")
    if not isinstance(branches, list):
        return False
    for branch in branches:
        if isinstance(branch, dict) and str(branch.get("address1") or branch.get("ADDRESS1") or "").strip():
            return True
    return False


def currency_fields_from_sql_row(
    row: dict[str, Any] | None,
    customer_code: str,
    status: int | None,
) -> dict[str, str]:
    """Currency fields from one SQL customer row. Does not call the network."""
    cc = ""
    if isinstance(row, dict):
        cc = _format_currency_display_value(row.get("currencycode") or row.get("currencyCode"))
    return {
        "code": str(customer_code or "").strip(),
        "currencycode": cc,
        "httpStatus": str(status) if status is not None else "",
    }


def sql_api_currency_and_code(customer_code: str) -> dict[str, str]:
    """Currency + code from SQL API GET /customer only (e.g. ``----``; never Firebird/MYR fallback)."""
    key = str(customer_code or "").strip().upper()
    cached = _CURRENCY_CACHE.get(key)
    if key and cached and (time.monotonic() - cached[0]) < _CURRENCY_CACHE_SECONDS:
        return cached[1]
    row, status = fetch_sql_api_customer_row(customer_code)
    fields = currency_fields_from_sql_row(row, customer_code, status)
    currency = str(fields.get("currencycode") or "").strip()
    if key and currency and currency not in ("-", "—"):
        _CURRENCY_CACHE[key] = (time.monotonic(), fields)
    return fields


def _firebird_customer_currency(customer_code: str) -> str:
    """Local AR_CUSTOMER.CURRENCYCODE when SQL API keys are not configured."""
    code = str(customer_code or "").strip()
    if not code:
        return ""
    try:
        from utils.db_utils import get_db_connection

        con = get_db_connection()
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT TRIM(CURRENCYCODE) FROM AR_CUSTOMER WHERE UPPER(TRIM(CODE)) = UPPER(TRIM(?))",
                (code,),
            )
            row = cur.fetchone()
            if not row:
                return ""
            return _format_currency_display_value(row[0])
        finally:
            con.close()
    except Exception:
        return ""


def apply_sql_api_currency_to_customer_payload(
    payload: dict[str, Any],
    customer_code: str,
    sql_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Overwrite CODE/CURRENCYCODE on get_user_info payload from SQL API GET /customer."""
    if not isinstance(payload, dict):
        return payload

    fields = sql_fields if sql_fields is not None else sql_api_currency_and_code(customer_code)
    out = dict(payload)
    # The signed-in AR_CUSTOMER.CODE is the quotation customer. A SQL API row must not replace it.
    code = str(customer_code or "").strip() or str(fields.get("code") or "").strip()
    cc = str(fields.get("currencycode") or "").strip()
    # SQL Accounting currency wins when the GET returns one. Otherwise use this customer's
    # AR_CUSTOMER.CURRENCYCODE (keys missing, HTTP error, or an empty currency field).
    if not cc or cc in ("-", "—"):
        cc = _firebird_customer_currency(code or customer_code)

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
