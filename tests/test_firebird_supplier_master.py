"""Firebird AP_SUPPLIER master used when paid /supplier GET is blocked."""
from __future__ import annotations

from utils.pr_route_helpers import resolve_supplier_master


def test_resolve_supplier_master_uses_firebird_when_rest_blocked(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")

    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_supplier_row_by_code",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_firebird_supplier_master_fields",
        lambda code: {
            "code": code,
            "companyname": "K3 METAL SERVICE CENTRE SDN BHD",
            "address1": "NO. 16, JALAN TSB 6,",
            "city": "Sungai Buloh",
            "currencycode": "----",
            "terms": "30 Days",
            "tin": "C1875315090",
            "daddress1": "NO. 16, JALAN TSB 6,",
        },
    )
    fields = resolve_supplier_master("400-K0001", "fallback")
    assert fields["code"] == "400-K0001"
    assert "K3 METAL" in fields["companyname"]
    assert fields["address1"].startswith("NO. 16")
    assert fields["tin"] == "C1875315090"


def test_resolve_supplier_master_prefers_rest_row(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")

    called = {"fb": 0}

    def _rest(_code):
        return {"code": "400-K0001", "companyname": "FROM REST", "sdsbranch": []}

    def _fb(_code):
        called["fb"] += 1
        return {"code": "400-K0001", "companyname": "FROM FB"}

    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_supplier_row_by_code",
        _rest,
    )
    monkeypatch.setattr(
        "utils.sql_api_supplier.fetch_firebird_supplier_master_fields",
        _fb,
    )
    monkeypatch.setattr(
        "utils.sql_api_supplier.supplier_master_document_fields",
        lambda row: {"code": row["code"], "companyname": row["companyname"]},
    )
    fields = resolve_supplier_master("400-K0001")
    assert fields["companyname"] == "FROM REST"
    assert called["fb"] == 0
