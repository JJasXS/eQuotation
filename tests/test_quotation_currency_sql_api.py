"""Quotation currency: SQL API GET /customer only (e.g. ----), never payload or MYR fallback."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from utils.customer_display import _format_currency_display_value
from utils.quotation_api import (
    _build_salesquotation_payload,
    _merge_customer_scalars_into_salesquotation_header,
    _resolve_quotation_currency_code,
    _strip_client_currency_fields,
)
from utils.sql_api_customer import apply_sql_api_currency_to_customer_payload


CUSTOMER = "300-L0001"


def _minimal_quotation_data(**overrides):
    base = {
        "companyName": "DME TECHNOLOGY SDN BHD",
        "currencyCode": "MYR",
        "customerDetailCurrency": "MYR",
        "customerScalars": {"currencycode": "MYR", "code": CUSTOMER},
        "items": [
            {
                "itemCode": "TEST-ITEM",
                "description": "Line 1",
                "quantity": 1,
                "unitPrice": 0,
                "taxCode": "",
            }
        ],
    }
    base.update(overrides)
    return base


@patch("utils.sql_api_customer.sql_api_currency_and_code")
def test_resolve_ignores_payload_myr_uses_sql_api_only(mock_sql_api):
    mock_sql_api.return_value = {"code": CUSTOMER, "currencycode": "----", "httpStatus": "200"}
    data = _minimal_quotation_data(currencyCode="MYR", customerDetailCurrency="MYR")
    assert _resolve_quotation_currency_code(data, CUSTOMER) == "----"


@patch("utils.sql_api_customer.sql_api_currency_and_code")
def test_resolve_raises_when_sql_api_empty(mock_sql_api):
    mock_sql_api.return_value = {"code": CUSTOMER, "currencycode": "", "httpStatus": "401"}
    with pytest.raises(ValueError, match="SQL API GET /customer"):
        _resolve_quotation_currency_code(_minimal_quotation_data(), CUSTOMER)


@patch("utils.sql_api_customer.sql_api_currency_and_code")
def test_strip_removes_client_currency_fields(mock_sql_api):
    mock_sql_api.return_value = {"code": CUSTOMER, "currencycode": "----", "httpStatus": "200"}
    data = _strip_client_currency_fields(_minimal_quotation_data())
    assert data.get("currencyCode") is None
    assert data.get("customerDetailCurrency") is None
    assert "currencycode" not in (data.get("customerScalars") or {})


@patch("utils.sql_api_customer.sql_api_currency_and_code")
def test_build_salesquotation_header_currency_from_sql_api(mock_sql_api):
    mock_sql_api.return_value = {"code": CUSTOMER, "currencycode": "----", "httpStatus": "200"}
    data = _strip_client_currency_fields(_minimal_quotation_data())
    payload = _build_salesquotation_payload(CUSTOMER, data, doc_no="QT-99999")
    assert payload["currencycode"] == "----"
    assert payload["currencycode"] != "MYR"


@patch("utils.sql_api_customer.sql_api_currency_and_code")
def test_merge_scalars_myr_does_not_override_header_currency(mock_sql_api):
    mock_sql_api.return_value = {"code": CUSTOMER, "currencycode": "----", "httpStatus": "200"}
    header = {"currencycode": "----", "companyname": ""}
    data = _minimal_quotation_data(customerScalars={"currencycode": "MYR"})
    _merge_customer_scalars_into_salesquotation_header(header, data)
    assert header.get("currencycode") != "MYR"


def test_format_currency_display_keeps_dashes():
    assert _format_currency_display_value("----") == "----"


@patch("utils.sql_api_customer.sql_api_currency_and_code")
def test_apply_sql_api_currency_overwrites_legacy_myr(mock_sql_api):
    mock_sql_api.return_value = {"code": CUSTOMER, "currencycode": "----", "httpStatus": "200"}
    out = apply_sql_api_currency_to_customer_payload(
        {"CODE": "OLD", "CURRENCYCODE": "MYR", "customerScalars": {"currencycode": "MYR"}},
        CUSTOMER,
    )
    assert out["CURRENCYCODE"] == "----"
    assert out["sqlApiCurrencyCode"] == "----"
    assert out["customerScalars"]["currencycode"] == "----"


def test_live_sql_api_customer_currency_if_configured():
    from api.config import load_sql_accounting_api_settings
    from utils.sql_api_customer import sql_api_currency_and_code

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        pytest.skip("SQL API keys not configured")

    fields = sql_api_currency_and_code(CUSTOMER)
    cc = str(fields.get("currencycode") or "").strip()
    if not cc:
        pytest.skip(f"SQL API returned no currency for {CUSTOMER} (status={fields.get('httpStatus')!r})")
    assert cc == "----", f"expected ---- from SQL API for {CUSTOMER}, got {cc!r}"
