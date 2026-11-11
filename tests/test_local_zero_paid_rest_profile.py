"""Local launcher profile: providers + hard block; no silent REST fallback."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from api.config.sql_accounting_master_read import master_read_allows_paid_rest
from api.config.sql_accounting_pr_award_sync import load_sql_accounting_pr_award_sync_settings
from api.config.sql_accounting_quotation_write import load_sql_accounting_quotation_write_settings
from api.config.sql_accounting_write import load_sql_accounting_write_settings


def _apply_local_zero_paid_rest(monkeypatch) -> None:
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    monkeypatch.setenv("SQL_ACCOUNTING_QUOTATION_WRITE_PROVIDER", "Sdk")
    monkeypatch.setenv("SQL_ACCOUNTING_WRITE_PROVIDER", "Sdk")
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    monkeypatch.setenv("SQL_ACCOUNTING_PR_AWARD_SYNC_MODE", "LocalOnly")
    monkeypatch.setenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE", "ACC-ANOZ.FDB")
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "LocalOnly")
    monkeypatch.setenv("SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE", "ACC-ANOZ.FDB")
    monkeypatch.setenv("SQL_API_ACCESS_KEY", "")
    monkeypatch.setenv("SQL_API_SECRET_KEY", "")


def test_local_profile_providers(monkeypatch):
    from api.config.sql_accounting_po_sync import load_sql_accounting_po_sync_settings

    _apply_local_zero_paid_rest(monkeypatch)
    assert load_sql_accounting_quotation_write_settings().is_sdk
    assert load_sql_accounting_write_settings().is_sdk
    assert load_sql_accounting_write_settings().block_rest_http is True
    assert load_sql_accounting_pr_award_sync_settings().is_local_only
    assert load_sql_accounting_po_sync_settings().is_local_only
    assert master_read_allows_paid_rest() is False


def test_rest_provider_cannot_bypass_block(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    monkeypatch.setenv("SQL_ACCOUNTING_WRITE_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    write = load_sql_accounting_write_settings()
    assert write.is_rest
    assert write.block_rest_http is True
    assert master_read_allows_paid_rest() is False


def test_local_profile_sql_client_cannot_reach_paid_host(monkeypatch):
    _apply_local_zero_paid_rest(monkeypatch)
    from api.clients.sql_accounting_client import SqlAccountingApiClient, SqlAccountingApiError
    from api.config import load_sql_accounting_api_settings

    client = SqlAccountingApiClient(load_sql_accounting_api_settings())
    with pytest.raises(SqlAccountingApiError, match="BLOCK_REST_HTTP"):
        client.get_json("https://api.sql.my/supplier")
    with pytest.raises(SqlAccountingApiError, match="BLOCK_REST_HTTP"):
        client.post_json("https://api.sql.my/batch", {"code": "x"})
    with pytest.raises(SqlAccountingApiError, match="BLOCK_REST_HTTP"):
        client.put_json("https://api.sql.my/purchaseorder/1", {})


def test_local_profile_batch_and_master_skip_paid_client(monkeypatch):
    _apply_local_zero_paid_rest(monkeypatch)
    from utils import sql_api_batch as batch_mod

    batch_mod._invalidate_batch_cache()
    with patch(
        "utils.sql_api_batch.fetch_batches_from_firebird",
        return_value=[{"code": "12mm*100mm*500mm"}],
    ):
        with patch(
            "utils.sql_api_batch.create_batch_in_firebird",
            return_value={"code": "12mm*100mm*500mm", "autokey": 1},
        ):
            with patch("utils.sql_api_batch.SqlAccountingApiClient") as mock_client:
                rows = batch_mod.fetch_batches(force_refresh=True)
                created = batch_mod.create_batch(
                    "12mm*100mm*500mm",
                    thickness="12",
                    width="100",
                    length="500",
                    stock={"CODE": "AL-1"},
                )
    assert rows[0]["code"] == "12mm*100mm*500mm"
    assert created["code"] == "12mm*100mm*500mm"
    mock_client.assert_not_called()


def test_local_profile_pr_sync_skips_without_keys(monkeypatch):
    """Paid PR mirror is skipped when keys empty (authoritative local Firebird)."""
    _apply_local_zero_paid_rest(monkeypatch)
    from utils.procurement_sql_api_sync import (
        post_purchaserequest_sql_api,
        sync_purchase_request_lines_sql_api_on_submit,
        sync_purchase_request_supplier_sql_api,
    )

    with patch("utils.procurement_sql_api_sync.SqlAccountingApiClient") as mock_client:
        assert sync_purchase_request_supplier_sql_api(1, "400-K0001").get("skipped") is True
        assert post_purchaserequest_sql_api({"docno": "PQ-1"}).get("skipped") is True
        assert sync_purchase_request_lines_sql_api_on_submit(1, "PQ-1", {}).get("skipped") is True
    mock_client.assert_not_called()
