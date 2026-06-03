"""SQL API supplier fetch must load ``sdsbranch`` (billing address) for PR/PO sync."""
from utils.sql_api_supplier import (
    _supplier_detail_urls,
    _supplier_row_has_billing_branch,
    supplier_master_document_fields,
)

SAMPLE_WITH_BRANCH = {
    "code": "400-U0001",
    "companyname": "UNION ALUMINIUM (SUZHOU) CO, LTD",
    "sdsbranch": [
        {
            "branchtype": "B",
            "branchname": "BILLING",
            "address1": "Add1",
            "postcode": "11500",
            "city": "Air Itam",
            "state": "Penang",
            "country": "CN",
        }
    ],
}


def test_supplier_detail_urls_path_before_query(monkeypatch):
    monkeypatch.setenv("SQL_API_HOST", "api.sql.my")
    monkeypatch.setenv("SQL_API_USE_TLS", "true")
    urls = _supplier_detail_urls("400-U0001")
    assert len(urls) >= 2
    assert "/supplier/400-U0001" in urls[0]
    assert "code=400-U0001" in urls[1]


def test_supplier_row_has_billing_branch():
    assert _supplier_row_has_billing_branch(SAMPLE_WITH_BRANCH)
    assert not _supplier_row_has_billing_branch({"code": "X", "sdsbranch": []})
    assert not _supplier_row_has_billing_branch({"code": "X"})


def test_header_only_supplier_has_no_delivery_fields():
    flat = supplier_master_document_fields({"code": "400-U0001", "companyname": "X"})
    assert flat.get("code") == "400-U0001"
    assert "daddress1" not in flat
    assert flat.get("branchname") == "BILLING"


def test_full_supplier_maps_delivery_from_branch():
    flat = supplier_master_document_fields(SAMPLE_WITH_BRANCH)
    assert flat["daddress1"] == "Add1"
    assert flat["dpostcode"] == "11500"
    assert flat["dcity"] == "Air Itam"
    assert flat["dcountry"] == "CN"
