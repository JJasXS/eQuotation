"""PO post-transfer sync: LocalOnly vs blocked Rest (no SDK, no paid REST fallback)."""
from __future__ import annotations

import pytest

from api.config.sql_accounting_po_sync import (
    PO_SYNC_LOCAL_ONLY,
    load_sql_accounting_po_sync_settings,
    normalize_po_sync_mode,
)
from utils.procurement_sql_api_sync import sync_purchase_order_supplier_sql_api


def test_normalize_po_sync_mode():
    assert normalize_po_sync_mode("LocalOnly") == PO_SYNC_LOCAL_ONLY
    assert normalize_po_sync_mode("localonly") == PO_SYNC_LOCAL_ONLY
    assert normalize_po_sync_mode("Rest") == "Rest"
    assert normalize_po_sync_mode(None) == "Rest"


def test_po_sync_local_only_skips_rest(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "LocalOnly")
    monkeypatch.setenv("SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE", "ACC-ANOZ.FDB")
    monkeypatch.setenv("DB_PATH", r"C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB")
    monkeypatch.setenv("SQLACC_SDK_DATABASE_FILE", "ACC-ANOZ.FDB")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")

    calls: list[str] = []

    def _boom(*_a, **_k):
        calls.append("client")
        raise AssertionError("paid REST client must not be constructed")

    monkeypatch.setattr(
        "utils.procurement_sql_api_sync.SqlAccountingApiClient",
        _boom,
    )
    result = sync_purchase_order_supplier_sql_api(99, "400-K0001", po_number="PO-2026-0001")
    assert result["synced"] is True
    assert result["mode"] == "localOnly"
    assert result["skippedPaidRest"] is True
    assert result["skippedSdkRewrite"] is True
    assert result["localAuthoritative"] is True
    assert result["supplierCode"] == "400-K0001"
    assert calls == []


def test_po_sync_local_only_refuses_wrong_database(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "LocalOnly")
    monkeypatch.setenv("SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE", "ACC-ANOZ.FDB")
    monkeypatch.setenv("DB_PATH", r"C:/other/OTHER.FDB")
    monkeypatch.setenv("SQLACC_SDK_DATABASE_FILE", "OTHER.FDB")
    with pytest.raises(RuntimeError, match="LocalOnly PO sync refused"):
        sync_purchase_order_supplier_sql_api(1, "400-K0001", po_number="PO-X")


def test_po_sync_rest_blocked_raises_without_local_only(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    with pytest.raises(RuntimeError, match="BLOCK_REST_HTTP"):
        sync_purchase_order_supplier_sql_api(1, "400-K0001", po_number="PO-X")


def test_load_po_sync_settings(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "LocalOnly")
    assert load_sql_accounting_po_sync_settings().is_local_only is True
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "Rest")
    assert load_sql_accounting_po_sync_settings().is_rest is True
