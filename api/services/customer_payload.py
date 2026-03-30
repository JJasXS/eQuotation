"""Build JSON bodies for SQL Accounting customer APIs from domain models."""
from __future__ import annotations

from typing import Any

from api.models import CustomerRequest


def normalize_credit_term(credit_term: str) -> str:
    """Match prior COM behavior: numeric terms become ``N Days``."""
    normalized = (credit_term or "").strip()
    if normalized.isdigit():
        return f"{normalized} Days"
    return normalized


def build_customer_create_payload(customer: CustomerRequest) -> dict[str, Any]:
    """
    Map ``CustomerRequest`` to the HTTP API JSON body.

    TODO(sql-accounting-api): Confirm the real endpoint's expected JSON schema,
    field names (camelCase vs snake_case), required keys, and nesting (flat vs
    ``customer`` / ``branch`` objects) against official API documentation.
    """
    # TODO(sql-accounting-api): Replace this structure with the documented payload
    # shape if the API expects different property names or nested objects.
    payload: dict[str, Any] = {
        # TODO: Confirm whether the API uses these keys or e.g. COMPANYNAME / Code.
        "code": customer.code,
        "company_name": customer.company_name,
        "credit_term": normalize_credit_term(customer.credit_term),
        "control_account": customer.control_account,
        "company_category": customer.company_category,
        "area": customer.area,
        "agent": customer.agent,
        "statement_type": customer.statement_type,
        "currency_code": customer.currency_code,
        "aging_on": customer.aging_on,
        "status": customer.status,
        "submission_type": customer.submission_type,
        "brn": customer.brn,
        "brn2": customer.brn2,
        "tin": customer.tin,
        "sales_tax_no": customer.sales_tax_no,
        "service_tax_no": customer.service_tax_no,
        "tax_exempt_no": customer.tax_exempt_no,
        "tax_exp_date": customer.tax_exp_date,
        "udf_email": customer.udf_email,
        "attachments": customer.attachments,
        "phone": customer.phone,
        "phone2": customer.phone2,
        "mobile": customer.mobile,
        "fax1": customer.fax1,
        "fax2": customer.fax2,
        "email": customer.email,
        "branch_type": customer.branch_type,
        "branch_name": customer.branch_name,
        "branch_dtlkey": customer.branch_dtlkey,
        "attention": customer.attention,
        "address1": customer.address1,
        "address2": customer.address2,
        "address3": customer.address3,
        "address4": customer.address4,
        "postcode": customer.postcode,
        "city": customer.city,
        "state": customer.state,
        "country": customer.country,
    }
    # Drop keys with value None to keep payload smaller (TODO: confirm API prefers nulls omitted).
    return {k: v for k, v in payload.items() if v is not None}
