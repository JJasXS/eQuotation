"""SQL API supplier overlay for purchase order / request PUT payloads."""
from utils.procurement_sql_api_sync import (
    build_supplier_put_payload,
    merge_supplier_into_sql_api_document,
    sql_api_header_fields_from_supplier,
)


def test_sql_api_header_fields_from_supplier():
    row = {
        "code": "400-J0001",
        "companyname": "JASON CORP",
        "creditterm": "30 Days",
        "currencycode": "----",
        "area": "----",
        "agent": "----",
    }
    hdr = sql_api_header_fields_from_supplier(row)
    assert hdr["code"] == "400-J0001"
    assert hdr["companyname"] == "JASON CORP"
    assert hdr["terms"] == "30 Days"
    assert hdr["currencycode"] == "----"


def test_merge_supplier_into_sql_api_document_preserves_lines():
    existing = {
        "dockey": 99,
        "docno": "PO-00099",
        "code": "----",
        "companyname": "",
        "sdsdocdetail": [{"dtlkey": 1, "itemcode": "A", "qty": "5"}],
    }
    supplier = {"code": "400-J0001", "companyname": "JASON CORP", "creditterm": "30 Days", "currencycode": "----"}
    merged = merge_supplier_into_sql_api_document(existing, supplier)
    assert merged["dockey"] == 99
    assert merged["code"] == "400-J0001"
    assert merged["companyname"] == "JASON CORP"
    assert merged["terms"] == "30 Days"
    assert len(merged["sdsdocdetail"]) == 1


def test_build_supplier_put_payload_maps_delivery_without_sdsbranch_on_pr():
    existing = {
        "dockey": 29,
        "docno": "PR-26060013",
        "changed": False,
        "updatecount": 3,
        "sdsdocdetail": [{"dtlkey": 1, "updatecount": 5, "itemcode": "X"}],
    }
    supplier = {
        "code": "400-U0001",
        "companyname": "UNION ALUMINIUM (SUZHOU) CO, LTD",
        "sdsbranch": [
            {
                "branchtype": "B",
                "branchname": "BILLING",
                "address1": "Add1",
                "postcode": "11500",
                "city": "Air Itam",
                "country": "CN",
            }
        ],
    }
    payload = build_supplier_put_payload(
        existing,
        supplier,
        include_lines=False,
        include_sdsbranch=False,
    )
    assert payload["daddress1"] == "Add1"
    assert payload["dcountry"] == "CN"
    assert payload["changed"] is False
    assert payload["updatecount"] == 3
    assert "sdsbranch" not in payload
