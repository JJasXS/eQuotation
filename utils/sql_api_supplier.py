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
    code_path = quote(str(supplier_code).strip(), safe="/:")
    # Path GET ``/supplier/:CODE`` returns ``sdsbranch``; ``?code=`` often omits branches.
    return [
        f"{scheme}://{host}{quote(detail_path.rstrip('/') + '/' + code_path, safe='/:?&=%')}",
        f"{scheme}://{host}{quote(detail_path, safe='/:?&=%')}?code={code_str}",
        f"{scheme}://{host}{quote(raw_path, safe='/:?&=%')}?code={code_str}",
    ]


def _supplier_row_has_billing_branch(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    branches = row.get("sdsbranch") or row.get("SDSBRANCH") or []
    return isinstance(branches, list) and len(branches) > 0


def fetch_sql_api_supplier_row(supplier_code: str) -> tuple[dict[str, Any] | None, int | None]:
    """
    Return supplier master from SQL API detail GET.

    Prefers ``GET /supplier/:CODE`` (includes ``sdsbranch``) over ``?code=`` (header-only).
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
    fallback: dict[str, Any] | None = None

    for url in _supplier_detail_urls(code):
        if url in seen:
            continue
        seen.add(url)
        status, parsed, _raw = client.get_json(url, timeout_seconds=min(15.0, settings.timeout_seconds + 5.0))
        last_status = status
        if status != 200:
            continue
        rows = _supplier_rows_from_sql_json(parsed)
        if not rows:
            continue
        row = rows[0]
        if _supplier_row_has_billing_branch(row):
            return row, status
        if fallback is None:
            fallback = row

    if fallback is not None:
        return fallback, last_status
    return None, last_status


def _supplier_list_url(offset: int, limit: int) -> str:
    settings = load_sql_accounting_api_settings()
    host = settings.host.strip().rstrip("/")
    scheme = "https" if settings.use_tls else "http"
    path = (os.getenv("SQL_API_SUPPLIER_LIST_PATH") or "/supplier").strip()
    if not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{host}{quote(path, safe='/:?&=%')}?offset={int(offset)}&limit={int(limit)}"


def fetch_supplier_row_by_code(supplier_code: str) -> dict[str, Any] | None:
    """
    Load one supplier master row from SQL API GET ``/supplier?code=…``,
    falling back to paginated GET ``/supplier?offset=…&limit=…`` (same as Create e-PR supplier list).
    """
    code = str(supplier_code or "").strip()
    if not code:
        return None

    row, _status = fetch_sql_api_supplier_row(code)
    if row and _supplier_row_has_billing_branch(row):
        return row
    header_only = row

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        return None

    client = SqlAccountingApiClient(settings)
    want = code.upper()
    offset = 0
    limit = 50
    max_pages = 40

    for _ in range(max_pages):
        url = _supplier_list_url(offset, limit)
        status, parsed, _raw = client.get_json(url, timeout_seconds=min(20.0, settings.timeout_seconds + 5.0))
        if status != 200:
            break
        rows = _supplier_rows_from_sql_json(parsed)
        if not rows:
            break
        for item in rows:
            item_code = str(item.get("code") or item.get("CODE") or "").strip()
            if item_code.upper() == want:
                if _supplier_row_has_billing_branch(item):
                    return item
                detail_row, _ = fetch_sql_api_supplier_row(code)
                if detail_row and _supplier_row_has_billing_branch(detail_row):
                    return detail_row
                return detail_row or item
        pagination = parsed.get("pagination") if isinstance(parsed, dict) else {}
        total_count = None
        if isinstance(pagination, dict) and pagination.get("count") is not None:
            try:
                total_count = int(pagination.get("count"))
            except (TypeError, ValueError):
                total_count = None
        offset += limit
        if len(rows) < limit:
            break
        if total_count is not None and offset >= total_count:
            break

    if header_only:
        return header_only
    return None


def sql_api_currency_and_code(supplier_code: str) -> dict[str, str]:
    """Currency + code from SQL API GET /supplier only (no Firebird/MYR fallback)."""
    row = fetch_supplier_row_by_code(supplier_code)
    status = "200" if row else ""
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


def _supplier_clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def looks_like_email(value: Any) -> bool:
    text = _supplier_clean(value)
    if not text or "@" not in text:
        return False
    local, _, domain = text.partition("@")
    return bool(local.strip()) and "." in domain


def resolve_supplier_company_name(supplier_code: str, stored_name: str = "") -> str:
    """Prefer SQL API company name; never use an email address as PH_PQ / PR company name."""
    code = _supplier_clean(supplier_code)
    stored = _supplier_clean(stored_name)
    company = ""
    if code:
        row = fetch_supplier_row_by_code(code)
        if isinstance(row, dict):
            raw = _supplier_clean(
                row.get("companyname") or row.get("companyName") or row.get("COMPANYNAME")
            )
            if raw and not looks_like_email(raw):
                company = raw
    if company and (looks_like_email(stored) or not stored):
        return company
    if stored and not looks_like_email(stored):
        return stored
    return company or code or stored

def supplier_billing_branch(supplier_row: dict[str, Any]) -> dict[str, Any]:
    """Prefer BILLING branch from SQL API ``sdsbranch`` array."""
    if not isinstance(supplier_row, dict):
        return {}
    branches = supplier_row.get("sdsbranch") or supplier_row.get("SDSBRANCH") or []
    if not isinstance(branches, list):
        return {}
    billing: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    for raw in branches:
        if not isinstance(raw, dict):
            continue
        if fallback is None:
            fallback = raw
        bt = _supplier_clean(raw.get("branchtype")).upper()
        bn = _supplier_clean(raw.get("branchname")).upper()
        if bt == "B" or bn == "BILLING":
            billing = raw
            break
    return billing or fallback or {}


def supplier_master_document_fields(supplier_row: dict[str, Any]) -> dict[str, Any]:
    """
    Flat supplier + billing branch fields for PH_PQ / PH_PO / SQL API PUT.

    Built from GET ``/supplier/*?code=…`` (header + ``sdsbranch``).
    """
    if not isinstance(supplier_row, dict):
        return {}

    branch = supplier_billing_branch(supplier_row)
    code = _supplier_clean(supplier_row.get("code") or supplier_row.get("CODE"))
    company = _supplier_clean(
        supplier_row.get("companyname") or supplier_row.get("companyName") or supplier_row.get("COMPANYNAME")
    )
    if looks_like_email(company):
        company = ""
    credit = _supplier_clean(supplier_row.get("creditterm") or supplier_row.get("creditTerm"))
    cc = _format_currency_display_value(
        supplier_row.get("currencycode") or supplier_row.get("currencyCode")
    ) or "----"

    def branch_val(*keys: str) -> str:
        for key in keys:
            v = _supplier_clean(branch.get(key))
            if v:
                return v
        return ""

    addr = {
        "address1": branch_val("address1", "ADDRESS1"),
        "address2": branch_val("address2", "ADDRESS2"),
        "address3": branch_val("address3", "ADDRESS3"),
        "address4": branch_val("address4", "ADDRESS4"),
        "postcode": branch_val("postcode", "POSTCODE"),
        "city": branch_val("city", "CITY"),
        "state": branch_val("state", "STATE"),
        "country": branch_val("country", "COUNTRY"),
        "phone1": branch_val("phone1", "PHONE1"),
        "phone2": branch_val("phone2", "PHONE2"),
        "mobile": branch_val("mobile", "MOBILE"),
        "fax1": branch_val("fax1", "FAX1"),
        "fax2": branch_val("fax2", "FAX2"),
        "attention": branch_val("attention", "ATTENTION"),
        "branchname": branch_val("branchname", "BRANCHNAME") or "BILLING",
    }

    fields: dict[str, Any] = {
        "code": code,
        "companyname": company or code,
        "companyname2": _supplier_clean(supplier_row.get("companyname2")),
        "controlaccount": _supplier_clean(supplier_row.get("controlaccount")),
        "companycategory": _supplier_clean(supplier_row.get("companycategory")) or "----",
        "area": _supplier_clean(supplier_row.get("area")) or "----",
        "agent": _supplier_clean(supplier_row.get("agent")) or "----",
        "currencycode": cc,
        "currencyrate": str(supplier_row.get("currencyrate") or supplier_row.get("currencyRate") or "1"),
        "terms": credit,
        "creditterm": credit,
        "creditlimit": _supplier_clean(supplier_row.get("creditlimit")),
        "overduelimit": _supplier_clean(supplier_row.get("overduelimit")),
        "statementtype": _supplier_clean(supplier_row.get("statementtype")),
        "taxexemptno": _supplier_clean(supplier_row.get("taxexemptno")),
        "taxexpdate": _supplier_clean(supplier_row.get("taxexpdate")),
        "brn": _supplier_clean(supplier_row.get("brn")),
        "brn2": _supplier_clean(supplier_row.get("brn2")),
        "gstno": _supplier_clean(supplier_row.get("gstno")),
        "salestaxno": _supplier_clean(supplier_row.get("salestaxno")),
        "servicetaxno": _supplier_clean(supplier_row.get("servicetaxno")),
        "tin": _supplier_clean(supplier_row.get("tin")),
        "idno": _supplier_clean(supplier_row.get("idno")),
        "tourismno": _supplier_clean(supplier_row.get("tourismno")),
        "sic": _supplier_clean(supplier_row.get("sic")) or "00000",
        "irbm_classification": _supplier_clean(supplier_row.get("irbm_classification")),
        "peppolid": _supplier_clean(supplier_row.get("peppolid")),
        "businessunit": _supplier_clean(supplier_row.get("businessunit")),
        "taxarea": _supplier_clean(supplier_row.get("taxarea")),
        "biznature": _supplier_clean(supplier_row.get("biznature")),
        "email": supplier_primary_email_from_sql_api_row(supplier_row),
        **addr,
    }

    try:
        fields["idtype"] = int(supplier_row.get("idtype") if supplier_row.get("idtype") is not None else 0)
    except (TypeError, ValueError):
        fields["idtype"] = 0
    try:
        fields["submissiontype"] = int(
            supplier_row.get("submissiontype") if supplier_row.get("submissiontype") is not None else 0
        )
    except (TypeError, ValueError):
        fields["submissiontype"] = 0

    _delivery_aliases = (
        ("daddress1", "address1"),
        ("daddress2", "address2"),
        ("daddress3", "address3"),
        ("daddress4", "address4"),
        ("dpostcode", "postcode"),
        ("dcity", "city"),
        ("dstate", "state"),
        ("dcountry", "country"),
        ("dattention", "attention"),
        ("dphone1", "phone1"),
        ("dmobile", "mobile"),
        ("dfax1", "fax1"),
    )
    for dkey, skey in _delivery_aliases:
        if addr.get(skey):
            fields[dkey] = addr[skey]

    return {
        k: v
        for k, v in fields.items()
        if v is not None and (not isinstance(v, str) or _supplier_clean(v) != "")
    }


def supplier_sdsbranch_for_document_put(supplier_row: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Billing branch row for SQL API PUT ``sdsbranch`` (Delivery tab in SQL Accounting).
    """
    if not isinstance(supplier_row, dict):
        return []
    branch = supplier_billing_branch(supplier_row)
    if not branch:
        return []
    code = _supplier_clean(supplier_row.get("code"))
    try:
        dtlkey = int(branch.get("dtlkey")) if branch.get("dtlkey") is not None else -1
    except (TypeError, ValueError):
        dtlkey = -1
    entry: dict[str, Any] = {
        "dtlkey": dtlkey,
        "code": code,
        "branchtype": _supplier_clean(branch.get("branchtype")) or "B",
        "branchname": _supplier_clean(branch.get("branchname")) or "BILLING",
        "address1": _supplier_clean(branch.get("address1")),
        "address2": _supplier_clean(branch.get("address2")),
        "address3": _supplier_clean(branch.get("address3")),
        "address4": _supplier_clean(branch.get("address4")),
        "postcode": _supplier_clean(branch.get("postcode")),
        "city": _supplier_clean(branch.get("city")),
        "state": _supplier_clean(branch.get("state")),
        "country": _supplier_clean(branch.get("country")),
        "attention": _supplier_clean(branch.get("attention")),
        "phone1": _supplier_clean(branch.get("phone1")),
        "phone2": _supplier_clean(branch.get("phone2")),
        "mobile": _supplier_clean(branch.get("mobile")),
        "fax1": _supplier_clean(branch.get("fax1")),
        "fax2": _supplier_clean(branch.get("fax2")),
    }
    email = supplier_primary_email_from_sql_api_row(supplier_row)
    if email:
        entry["email"] = email
    return [entry]
