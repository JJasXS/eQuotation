"""Hard gate: paid SigV4 SQL Accounting HTTP refused when BLOCK_REST_HTTP is true."""
from __future__ import annotations

import pytest

from api.clients import SqlAccountingApiError
from api.clients.sql_accounting_client import SqlAccountingApiClient
from api.config.sql_accounting_api import SqlAccountingApiSettings


def _settings() -> SqlAccountingApiSettings:
    return SqlAccountingApiSettings(
        access_key="AKIA_TEST",
        secret_key="secret_test",
        host="api.sql.example.invalid",
        region="ap-southeast-1",
        service="execute-api",
        customer_create_path="/customer",
        quotation_create_path="/salesquotation",
        stock_item_list_path="/stockitem",
        area_list_path="/area",
        currency_list_path="/currency",
        use_tls=True,
        timeout_seconds=5.0,
        max_retries=0,
        dry_run=False,
        debug_payload=False,
    )


def test_post_json_refuses_when_block_rest(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    client = SqlAccountingApiClient(_settings())
    with pytest.raises(SqlAccountingApiError, match="BLOCK_REST_HTTP"):
        client.post_json("https://api.sql.example.invalid/customer", {"code": "X"})


def test_put_json_refuses_when_block_rest(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    client = SqlAccountingApiClient(_settings())
    with pytest.raises(SqlAccountingApiError, match="BLOCK_REST_HTTP"):
        client.put_json("https://api.sql.example.invalid/purchaseorder/1", {"code": "X"})


def test_get_json_refuses_when_block_rest(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    client = SqlAccountingApiClient(_settings())
    with pytest.raises(SqlAccountingApiError, match="BLOCK_REST_HTTP"):
        client.get_json("https://api.sql.example.invalid/supplier")


def test_post_json_allowed_when_block_off(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")
    client = SqlAccountingApiClient(_settings())
    calls: list[str] = []

    def _fake_post(*_a, **_k):
        calls.append("post")
        raise RuntimeError("network should not matter after gate")

    monkeypatch.setattr(client, "_sign_and_post", _fake_post)
    with pytest.raises(RuntimeError, match="network"):
        client.post_json("https://api.sql.example.invalid/customer", {"code": "X"})
    assert calls == ["post"]
