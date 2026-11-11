"""Create AR_CUSTOMER via SQLAcc.BizApp (sqlSign UpsertParty create path, create-only)."""
from __future__ import annotations

import logging
from typing import Any

from api.clients import SqlAccountingApiError
from api.models import CustomerRequest
from api.services.customer_payload import normalize_credit_term

logger = logging.getLogger(__name__)

_BIZ_CUSTOMER = "AR_CUSTOMER"
_MAIN = "MainDataSet"
_BRANCH = "cdsBranch"


def _null_if_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _field_size(dataset: Any, name: str) -> int | None:
    """Return COM field Size when available (CHAR/VARCHAR width)."""
    try:
        field = dataset.Fields.FindField(name)
    except Exception:
        return None
    if field is None:
        return None
    for attr in ("Size", "size", "DataSize"):
        try:
            raw = getattr(field, attr, None)
            if raw is None:
                continue
            size = int(raw)
            if size > 0:
                return size
        except Exception:
            continue
    return None


def _set_field(dataset: Any, name: str, value: Any) -> None:
    field = dataset.Fields.FindField(name)
    if field is None:
        raise SqlAccountingApiError(
            f"AR_CUSTOMER field '{name}' not found on COM dataset.",
            status_code=500,
        )
    field.AsString = "" if value is None else str(value)


def _set_if(dataset: Any, name: str, value: Any) -> None:
    text = _null_if_empty(value)
    if text is None:
        return
    try:
        field = dataset.Fields.FindField(name)
        if field is None:
            return
        field.AsString = text
    except Exception:
        logger.debug("Optional COM field %s skipped", name, exc_info=True)


def _is_present_key(key: Any) -> bool:
    if key is None:
        return False
    if isinstance(key, bool):
        return key
    if isinstance(key, (int, float)):
        return key != 0
    text = str(key).strip()
    return bool(text) and text != "0"


def find_customer_key(biz: Any, code: str) -> Any | None:
    """Return FindKeyByRef result when CODE already exists."""
    code = (code or "").strip()
    if not code:
        return None
    for field in ("CODE", "Code"):
        try:
            key = biz.FindKeyByRef(field, code)
            if _is_present_key(key):
                return key
        except Exception:
            continue
    return None


def _query_first_row(app: Any, sql: str) -> dict[str, str] | None:
    ds = None
    try:
        ds = app.DBManager.NewDataSet(sql)
        if int(ds.RecordCount) <= 0:
            return None
        ds.First()
        fields = ds.Fields
        row: dict[str, str] = {}
        for i in range(int(fields.Count)):
            field = fields.Items(i)
            name = str(getattr(field, "FieldName", None) or f"F{i}")
            try:
                val = field.AsString
            except Exception:
                val = getattr(field, "value", "")
            row[name] = ("" if val is None else str(val)).strip()
        return row
    finally:
        ds = None


def _gl_exists(app: Any, control_code: str) -> bool:
    safe = control_code.replace("'", "''")
    row = _query_first_row(
        app,
        "SELECT FIRST 1 TRIM(CODE) AS CODE FROM GL_ACC "
        f"WHERE TRIM(CODE) = '{safe}'",
    )
    return bool(row and (row.get("CODE") or "").strip())


def resolve_control_account(app: Any, provided: str | None) -> str:
    """
    Resolve ControlAccount like sqlSign: prefer provided when it exists in GL_ACC,
    else first distinct AR_CUSTOMER.CONTROLACCOUNT that exists in GL_ACC.
    Never guess 300-000.
    """
    candidate = _null_if_empty(provided)
    if candidate and _gl_exists(app, candidate):
        return candidate

    rows_sql = (
        "SELECT DISTINCT TRIM(CONTROLACCOUNT) AS CONTROLACCOUNT FROM AR_CUSTOMER "
        "WHERE CONTROLACCOUNT IS NOT NULL AND TRIM(CONTROLACCOUNT) <> ''"
    )
    ds = None
    try:
        ds = app.DBManager.NewDataSet(rows_sql)
        if int(ds.RecordCount) <= 0:
            raise SqlAccountingApiError(
                "ControlAccount could not be resolved from the destination company. "
                "Set SQLACC_SDK_CUSTOMER_CONTROL_ACCOUNT to a valid GL_ACC code.",
                status_code=500,
            )
        ds.First()
        while not bool(ds.Eof):
            try:
                field = ds.Fields.FindField("CONTROLACCOUNT")
                raw = field.AsString if field is not None else ""
            except Exception:
                raw = ""
            pick = _null_if_empty(raw)
            if pick and _gl_exists(app, pick):
                return pick
            ds.Next()
    finally:
        ds = None

    raise SqlAccountingApiError(
        "ControlAccount is required for AR_CUSTOMER and could not be resolved. "
        "Set SQLACC_SDK_CUSTOMER_CONTROL_ACCOUNT or ensure existing customers have a valid ControlAccount.",
        status_code=500,
    )


def _load_party_persistence(app: Any, code: str) -> dict[str, str] | None:
    safe = code.replace("'", "''")
    return _query_first_row(
        app,
        "SELECT FIRST 1 TRIM(CODE) AS CODE, TRIM(CONTROLACCOUNT) AS CONTROLACCOUNT "
        f"FROM AR_CUSTOMER WHERE TRIM(CODE) = '{safe}'",
    )


def create_customer_via_com(
    app: Any,
    customer: CustomerRequest,
    *,
    control_account_override: str | None = None,
) -> dict[str, Any]:
    """
    Create-only AR_CUSTOMER write (fail if CODE exists — no silent update).

    Field mapping follows sqlSign AR_CUSTOMER UpsertParty + eQuotation customer payload.
    """
    code = _null_if_empty(customer.code)
    if not code:
        raise SqlAccountingApiError(
            "Customer code is required for SDK create.",
            status_code=400,
        )

    biz = app.BizObjects.Find(_BIZ_CUSTOMER)
    if find_customer_key(biz, code) is not None:
        raise SqlAccountingApiError(
            f"Customer code '{code}' already exists (duplicate CODE).",
            status_code=422,
        )

    control = resolve_control_account(app, control_account_override)
    main = biz.DataSets.Find(_MAIN)
    branch = biz.DataSets.Find(_BRANCH)

    code_max = _field_size(main, "CODE")
    if code_max and len(code) > code_max:
        raise SqlAccountingApiError(
            f"Customer code '{code}' length {len(code)} exceeds AR_CUSTOMER.CODE size {code_max}.",
            status_code=400,
        )

    biz.New()
    _set_field(main, "CODE", code)
    _set_field(main, "CompanyName", _null_if_empty(customer.company_name) or code)
    _set_field(main, "ControlAccount", control)
    _set_field(main, "Area", _null_if_empty(customer.area) or "----")
    _set_field(main, "Agent", "----")
    credit = normalize_credit_term(customer.credit_term or "30 Days")
    _set_field(main, "CreditTerm", credit or "30 Days")
    _set_field(main, "CurrencyCode", _null_if_empty(customer.currency_code) or "----")
    _set_field(main, "Status", "A")
    _set_if(main, "TIN", customer.tin)
    _set_if(main, "BRN", customer.brn)
    _set_if(main, "BRN2", customer.brn2)
    _set_if(main, "SalesTaxNo", customer.sales_tax_no)
    _set_if(main, "ServiceTaxNo", customer.service_tax_no)
    _set_if(main, "TaxExemptNo", customer.tax_exempt_no)
    _set_if(main, "TaxExpDate", customer.tax_exp_date)
    if customer.idtype is not None:
        _set_if(main, "IDTYPE", customer.idtype)

    try:
        branch.Edit()
    except Exception:
        branch.Append()
    _set_field(branch, "BranchType", "B")
    _set_field(branch, "BranchName", "BILLING")
    _set_if(branch, "Address1", customer.address1)
    _set_if(branch, "Address2", customer.address2)
    _set_if(branch, "Address3", customer.address3)
    _set_if(branch, "Address4", customer.address4)
    _set_if(branch, "PostCode", customer.postcode)
    _set_if(branch, "City", customer.city)
    _set_if(branch, "State", customer.state)
    _set_field(branch, "Country", _null_if_empty(customer.country) or "MY")
    _set_if(branch, "Attention", customer.attention)
    _set_if(branch, "Phone1", customer.phone)
    email = customer.email or customer.udf_email
    _set_if(branch, "Email", email)
    branch.Post()

    try:
        biz.Save()
    except Exception as exc:
        try:
            biz.Close()
        except Exception:
            pass
        raise SqlAccountingApiError(
            f"AR_CUSTOMER Save failed: {exc}",
            status_code=502,
        ) from exc

    try:
        biz.Close()
    except Exception:
        logger.debug("AR_CUSTOMER Close after Save failed", exc_info=True)

    persisted = _load_party_persistence(app, code)
    if not persisted or not (persisted.get("CODE") or "").strip():
        raise SqlAccountingApiError(
            f"Save reported success but CODE '{code}' was not found after Close.",
            status_code=502,
        )
    found_control = (persisted.get("CONTROLACCOUNT") or "").strip()
    if found_control.upper() != control.upper():
        raise SqlAccountingApiError(
            f"Persisted ControlAccount '{found_control}' does not match resolved '{control}'.",
            status_code=502,
        )

    return {
        "code": persisted["CODE"],
        "companyName": customer.company_name,
        "controlAccount": found_control,
        "message": f"Created. ControlAccount={found_control}",
        "provider": "Sdk",
    }
