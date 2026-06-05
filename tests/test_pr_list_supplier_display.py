"""PR list must show supplier company names, not bare codes."""
from main import _enrich_pr_list_supplier_display


def test_enrich_pr_list_supplier_display_replaces_code_with_company(monkeypatch):
    records = [{"id": 58, "supplierId": "400-P0001", "supplierName": "400-P0001"}]

    monkeypatch.setattr(
        "main._fetch_supplier_master_from_sql_api",
        lambda _codes: {
            "400-P0001": {"companyname": "PROACC", "udf_email": ""},
        },
    )
    monkeypatch.setattr(
        "main._resolve_supplier_company_display",
        lambda code, stored, master: str((master or {}).get(str(code).upper(), {}).get("companyname") or ""),
    )

    _enrich_pr_list_supplier_display(records)
    assert records[0]["supplierName"] == "PROACC"


def test_enrich_pr_list_supplier_display_clears_code_only_name(monkeypatch):
    records = [{"id": 59, "supplierId": "400-P0001", "supplierName": "400-P0001"}]

    monkeypatch.setattr("main._fetch_supplier_master_from_sql_api", lambda _codes: {})
    monkeypatch.setattr(
        "main._resolve_supplier_company_display",
        lambda code, stored, master: str(stored or ""),
    )

    _enrich_pr_list_supplier_display(records)
    assert records[0]["supplierName"] == ""


def test_enrich_pr_list_supplier_display_keeps_header_companyname(monkeypatch):
    records = [{"id": 58, "supplierId": "400-P0001", "supplierName": "PROACC"}]

    monkeypatch.setattr("main._fetch_supplier_master_from_sql_api", lambda _codes: {})
    monkeypatch.setattr(
        "main._resolve_supplier_company_display",
        lambda code, stored, master: "PROACC" if stored == "PROACC" else "",
    )

    _enrich_pr_list_supplier_display(records)
    assert records[0]["supplierName"] == "PROACC"


def test_enrich_pr_list_supplier_display_keeps_stored_when_master_misses(monkeypatch):
    records = [{"id": 58, "supplierId": "400-P0001", "supplierName": "PROACC"}]

    monkeypatch.setattr("main._fetch_supplier_master_from_sql_api", lambda _codes: {})
    monkeypatch.setattr(
        "main._resolve_supplier_company_display",
        lambda code, stored, master: "",
    )

    _enrich_pr_list_supplier_display(records)
    assert records[0]["supplierName"] == "PROACC"
