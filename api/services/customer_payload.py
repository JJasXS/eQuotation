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
    # Keep payload minimal and let SQL API apply default values server-side.
    payload: dict[str, Any] = {
        "companyname": customer.company_name,
        "area": customer.area,
        "currencycode": customer.currency_code,
        "tin": customer.tin,
        "brn2": customer.brn2,
        "salestaxno": customer.sales_tax_no,
        "servicetaxno": customer.service_tax_no,
        "taxexpdate": customer.tax_exp_date,
        "taxexemptno": customer.tax_exempt_no,
        "idtype": customer.idtype,
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
    if customer.code:
        payload["code"] = customer.code
    # Only include credit term when explicitly provided by caller.
    if customer.credit_term and customer.credit_term.strip() != "30 Days":
        payload["creditterm"] = normalize_credit_term(customer.credit_term)
    # Drop keys with value None to keep payload smaller (TODO: confirm API prefers nulls omitted).
    return {k: v for k, v in payload.items() if v is not None}
