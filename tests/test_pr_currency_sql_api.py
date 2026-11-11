"""Purchase request currency from supplier master (REST or Firebird under block)."""
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
    mock_api.return_value = {
        "currencycode": "----",
        "code": "400-P0001",
        "httpStatus": "200",
        "source": "sql_api_supplier_get",
    }
    assert resolve_pr_currency_code("400-P0001") == "----"


@patch("utils.procurement_pr_sql_api.sql_api_currency_and_code")
def test_resolve_pr_currency_raises_when_empty(mock_api):
    mock_api.return_value = {
        "currencycode": "",
        "code": "400-P0001",
        "httpStatus": "404",
        "source": "",
    }
    with pytest.raises(ValueError, match="Currency not returned"):
        resolve_pr_currency_code("400-P0001")


def test_sql_api_currency_uses_firebird_when_blocked(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.sql_api_supplier import sql_api_currency_and_code

    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_supplier_row_by_code",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_firebird_supplier_master_fields",
        lambda code: {"code": code, "currencycode": "----"},
    )
    with patch("utils.sql_api_supplier.SqlAccountingApiClient") as mock_client:
        fields = sql_api_currency_and_code("400-K0001")
    assert fields["currencycode"] == "----"
    assert fields["source"] == "firebird_ap_supplier"
    mock_client.assert_not_called()


def test_sql_api_currency_no_firebird_when_rest_miss(monkeypatch):
    """Rest mode: missing paid row must not invent Firebird currency."""
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    from utils.sql_api_supplier import sql_api_currency_and_code

    called = {"fb": 0}
    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_supplier_row_by_code",
        lambda *_a, **_k: None,
    )

    def _fb(_code):
        called["fb"] += 1
        return {"code": _code, "currencycode": "USD"}

    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_firebird_supplier_master_fields",
        _fb,
    )
    fields = sql_api_currency_and_code("400-K0001")
    assert fields["currencycode"] == ""
    assert called["fb"] == 0
