"""Supplier email extraction from SQL API GET /supplier rows."""
from utils.sql_api_supplier import (
    enrich_supplier_row_for_procurement,
    supplier_emails_from_sql_api_row,
    supplier_primary_email_from_sql_api_row,
)


def test_primary_email_from_udf_email01():
    row = {
        "code": "400-J0001",
        "companyname": "JASON CORP",
        "udf_email01": "jason.choo2004@gmail.com",
        "udf_email02": None,
    }
    assert supplier_primary_email_from_sql_api_row(row) == "jason.choo2004@gmail.com"
    assert supplier_emails_from_sql_api_row(row) == ["jason.choo2004@gmail.com"]


def test_enrich_exposes_email_for_procurement_ui():
    row = {"code": "X", "udf_email03": "a@b.com"}
    out = enrich_supplier_row_for_procurement(row)
    assert out["email"] == "a@b.com"
    assert out["udf_email"] == "a@b.com"


def test_all_non_empty_udf_email_slots_collected():
    row = {
        "code": "400-J0001",
        "udf_email01": "one@example.com",
        "udf_email02": "two@example.com",
        "udf_email03": None,
        "udf_email04": "",
        "udf_email05": "one@example.com",
    }
    assert supplier_emails_from_sql_api_row(row) == [
        "one@example.com",
        "two@example.com",
    ]
