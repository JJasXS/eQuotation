"""Award / accept supplier copies SQL API GET /supplier master onto PH_PQ header."""
from utils.procurement_pr_sql_api import ph_pq_header_updates_from_sql_supplier
from utils.procurement_sql_api_sync import sql_api_header_fields_from_supplier
from utils.sql_api_supplier import supplier_master_document_fields

SAMPLE_SUPPLIER_U0001 = {
    "code": "400-U0001",
    "controlaccount": "400-000",
    "companyname": "UNION ALUMINIUM (SUZHOU) CO, LTD",
    "area": "----",
    "agent": "----",
    "creditterm": "30 Days",
    "currencycode": "----",
    "taxexemptno": "TaxNo",
    "brn": "BRN",
    "gstno": "GSTNO",
    "tin": "EI00000000030",
    "idno": "10",
    "sic": "00000",
    "submissiontype": 0,
    "udf_email01": "tebbytan@gmail.com",
    "sdsbranch": [
        {
            "branchtype": "B",
            "branchname": "BILLING",
            "address1": "Add1",
            "address2": "Add2",
            "postcode": "11500",
            "city": "Air Itam",
            "state": "Penang",
            "country": "CN",
            "attention": "UA",
            "phone1": "0112229383",
            "mobile": "023883622",
            "fax1": "0402277726",
        }
    ],
}


def test_supplier_master_document_fields_includes_branch_and_tax():
    flat = supplier_master_document_fields(SAMPLE_SUPPLIER_U0001)
    assert flat["code"] == "400-U0001"
    assert flat["address1"] == "Add1"
    assert flat["city"] == "Air Itam"
    assert flat["tin"] == "EI00000000030"
    assert flat["daddress1"] == "Add1"
    assert flat["terms"] == "30 Days"


def test_ph_pq_header_updates_maps_full_supplier():
    out = ph_pq_header_updates_from_sql_supplier(SAMPLE_SUPPLIER_U0001)
    assert out["CODE"] == "400-U0001"
    assert out["COMPANYNAME"] == "UNION ALUMINIUM (SUZHOU) CO, LTD"
    assert out["ADDRESS1"] == "Add1"
    assert out["CITY"] == "Air Itam"
    assert out["TIN"] == "EI00000000030"
    assert out["PHONE1"] == "0112229383"
    assert out["DADDRESS1"] == "Add1"
    assert "NOTE" not in out


def test_sql_api_put_header_includes_address_and_tax():
    hdr = sql_api_header_fields_from_supplier(SAMPLE_SUPPLIER_U0001)
    assert hdr["code"] == "400-U0001"
    assert hdr["address1"] == "Add1"
    assert hdr["terms"] == "30 Days"
    assert hdr["tin"] == "EI00000000030"
    assert hdr["branchname"] == "BILLING"
