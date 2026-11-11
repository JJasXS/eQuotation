"""Local launcher profile: providers + hard block; no silent REST fallback."""
from __future__ import annotations

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
