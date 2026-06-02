"""Purchase request currency must come from SQL API GET /supplier only."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from utils.procurement_pr_sql_api import resolve_pr_currency_code, strip_client_pr_currency_fields


def test_strip_client_pr_currency_fields():
    payload = {"currency": "MYR", "currencycode": "MYR", "supplierId": "400-P0001"}
    out = strip_client_pr_currency_fields(payload)
    assert "currency" not in out
    assert "currencycode" not in out
    assert out["supplierId"] == "400-P0001"


@patch("utils.procurement_pr_sql_api.sql_api_currency_and_code")
def test_resolve_pr_currency_from_supplier(mock_api):
    mock_api.return_value = {"currencycode": "----", "code": "400-P0001", "httpStatus": "200"}
    assert resolve_pr_currency_code("400-P0001") == "----"


@patch("utils.procurement_pr_sql_api.sql_api_currency_and_code")
def test_resolve_pr_currency_raises_when_empty(mock_api):
    mock_api.return_value = {"currencycode": "", "code": "400-P0001", "httpStatus": "404"}
    with pytest.raises(ValueError, match="Currency not returned"):
        resolve_pr_currency_code("400-P0001")
