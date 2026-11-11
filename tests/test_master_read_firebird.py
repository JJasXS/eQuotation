"""Phase 2.2: master-data GET Firebird vs REST provider (mock; no shared TEST writes)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.config.sql_accounting_master_read import (
    PROVIDER_FIREBIRD,
    PROVIDER_REST,
    master_read_allows_paid_rest,
    normalize_master_read_provider,
)


def test_normalize_master_read_defaults_to_firebird():
    assert normalize_master_read_provider(None) == PROVIDER_FIREBIRD
    assert normalize_master_read_provider("") == PROVIDER_FIREBIRD
    assert normalize_master_read_provider("firebird") == PROVIDER_FIREBIRD
    assert normalize_master_read_provider("Rest") == PROVIDER_REST
    assert normalize_master_read_provider("REST") == PROVIDER_REST


def test_block_rest_http_forces_no_paid_master_get(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    assert master_read_allows_paid_rest() is False


def test_rest_provider_allows_paid_when_not_blocked(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")
    assert master_read_allows_paid_rest() is True


def test_firebird_provider_blocks_paid(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    monkeypatch.delenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", raising=False)
    assert master_read_allows_paid_rest() is False


@patch("utils.sql_api_reference_lists.SqlAccountingApiClient")
@patch("utils.sql_api_reference_lists.load_sql_accounting_api_settings")
def test_area_sql_api_skipped_when_firebird(mock_settings, mock_client, monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.sql_api_reference_lists import fetch_area_codes_sql_api

    assert fetch_area_codes_sql_api() is None
    mock_client.assert_not_called()


@patch("utils.sql_api_reference_lists.SqlAccountingApiClient")
@patch("utils.sql_api_reference_lists.load_sql_accounting_api_settings")
def test_area_sql_api_rest_rollback_returns_codes(mock_settings, mock_client_cls, monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "0")
    settings = mock_settings.return_value
    settings.dry_run = False
    settings.access_key = "ak"
    settings.secret_key = "sk"
    settings.area_list_path = "/area"
    settings.timeout_seconds = 10.0
    settings.resolved_list_get_url.return_value = "https://api.example/area"

    client = mock_client_cls.return_value
    client.get_json.return_value = (
        200,
        {"data": [{"code": "PPS", "isactive": True}, {"code": "KL", "isactive": False}]},
        "",
    )
    from utils.sql_api_reference_lists import fetch_area_codes_sql_api

    codes = fetch_area_codes_sql_api()
    assert codes == ["PPS"]
    mock_client_cls.assert_called_once()


@patch("utils.stock_items_catalog.fetch_stock_items", return_value=[{"CODE": "A1", "DESCRIPTION": "Item"}])
@patch("utils.stock_items_catalog._try_fetch_stock_items_sql_api")
def test_stock_catalog_firebird_skips_sql_api(mock_sql, mock_fb, monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.stock_items_catalog import fetch_stock_items_catalog_uncached

    with patch("utils.db_utils.get_db_connection") as mock_con:
        mock_con.return_value.cursor.return_value = MagicMock()
        rows = fetch_stock_items_catalog_uncached()
    assert rows == [{"CODE": "A1", "DESCRIPTION": "Item"}]
    mock_sql.assert_not_called()


@patch("utils.stock_items_catalog._fetch_stock_items_from_firebird", return_value=[])
@patch("utils.stock_items_catalog._try_fetch_stock_items_sql_api", return_value=[{"CODE": "S1"}])
def test_stock_catalog_rest_uses_sql_when_present(mock_sql, mock_fb, monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")
    from utils.stock_items_catalog import fetch_stock_items_catalog_uncached

    rows = fetch_stock_items_catalog_uncached()
    assert rows == [{"CODE": "S1"}]
    mock_sql.assert_called_once()
    mock_fb.assert_not_called()


@patch("utils.stock_items_catalog._fetch_stock_items_from_firebird", return_value=[{"CODE": "FB"}])
@patch("utils.stock_items_catalog._try_fetch_stock_items_sql_api", return_value=None)
def test_stock_catalog_rest_empty_sql_falls_back_firebird(mock_sql, mock_fb, monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "0")
    from utils.stock_items_catalog import fetch_stock_items_catalog_uncached

    assert fetch_stock_items_catalog_uncached() == [{"CODE": "FB"}]


def test_projects_firebird_mode_uses_local_loader(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from main import _fetch_procurement_projects_uncached

    with patch("main._load_projects_from_firebird_fallback") as mock_fb:
        mock_fb.return_value = [
            {"code": "NON-PROJECT", "description": "Non", "isactive": True},
            {"code": "OFF", "description": "Off", "isactive": False},
        ]
        with patch("utils.sql_api_projects.fetch_projects_from_sql_api") as mock_api:
            rows = _fetch_procurement_projects_uncached()
    assert len(rows) == 1
    assert rows[0]["code"] == "NON-PROJECT"
    mock_api.assert_not_called()


def test_projects_rest_rollback_calls_sql_api(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")
    from main import _fetch_procurement_projects_uncached

    with patch("utils.sql_api_projects.fetch_projects_from_sql_api") as mock_api:
        mock_api.return_value = [{"code": "P1", "description": "P1", "isactive": True}]
        with patch("main._load_projects_from_firebird_fallback") as mock_fb:
            rows = _fetch_procurement_projects_uncached()
    assert rows[0]["code"] == "P1"
    mock_api.assert_called_once()
    mock_fb.assert_not_called()


def test_projects_firebird_empty_results(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from main import _fetch_procurement_projects_uncached

    with patch("main._load_projects_from_firebird_fallback", return_value=[]):
        assert _fetch_procurement_projects_uncached() == []


def test_supplier_sql_fetch_skipped_under_block(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    from main import _fetch_all_suppliers_from_sql_api_uncached

    with patch("main.http_request_json") as mock_http:
        assert _fetch_all_suppliers_from_sql_api_uncached() == []
        mock_http.assert_not_called()


def test_supplier_detail_skipped_when_firebird(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.sql_api_supplier import fetch_sql_api_supplier_row

    with patch("utils.sql_api_supplier.SqlAccountingApiClient") as mock_client:
        row, status = fetch_sql_api_supplier_row("400-A0001")
    assert row is None and status is None
    mock_client.assert_not_called()


def test_customer_detail_skipped_when_firebird(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.sql_api_customer import fetch_sql_api_customer_row

    with patch("utils.sql_api_customer.SqlAccountingApiClient") as mock_client:
        row, status = fetch_sql_api_customer_row("300-C0001")
    assert row is None and status is None
    mock_client.assert_not_called()


def test_fastapi_supplier_route_skips_paid(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from api.routes import suppliers as suppliers_mod

    with patch.object(suppliers_mod, "_make_sigv4_get") as mock_get:
        body = suppliers_mod.list_suppliers(offset=0, limit=50, _=None)
    assert body["data"] == []
    assert body["pagination"]["count"] == 0
    mock_get.assert_not_called()


def test_auth_supplier_external_skipped_when_firebird(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from api.routes import auth as auth_mod

    with patch.object(auth_mod, "_make_sigv4_get") as mock_get:
        supplier, code = auth_mod._lookup_supplier_via_external_api("a@b.com")
    assert supplier is None and code is None
    mock_get.assert_not_called()


def test_batch_attach_skips_paid_when_firebird(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.sql_api_batch import attach_batch_codes_to_lines

    lines = [
        {
            "itemCode": "AL-1",
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
        }
    ]
    with patch("utils.sql_api_batch.fetch_batches") as mock_fetch:
        with patch("utils.sql_api_batch.create_batch") as mock_create:
            out = attach_batch_codes_to_lines(lines)
    assert out[0].get("batch") in (None, "")
    mock_fetch.assert_not_called()
    mock_create.assert_not_called()


def test_batch_fetch_raises_when_blocked(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    from utils.sql_api_batch import SqlApiBatchError, fetch_batches

    with pytest.raises(SqlApiBatchError, match="blocked"):
        fetch_batches(force_refresh=True)


def test_currency_sql_api_skipped_when_firebird(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    with patch("utils.sql_api_reference_lists.SqlAccountingApiClient") as mock_client:
        from utils.sql_api_reference_lists import fetch_currency_codes_sql_api

        assert fetch_currency_codes_sql_api() is None
    mock_client.assert_not_called()


def test_supplier_row_by_code_no_list_walk_when_firebird(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    from utils.sql_api_supplier import fetch_supplier_row_by_code

    with patch("utils.sql_api_supplier.SqlAccountingApiClient") as mock_client:
        assert fetch_supplier_row_by_code("400-A0001") is None
    mock_client.assert_not_called()
