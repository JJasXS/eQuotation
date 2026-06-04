from unittest.mock import patch

from utils.sql_api_supplier import looks_like_email, resolve_supplier_company_name


def test_looks_like_email():
    assert looks_like_email("jason.choo2004@gmail.com") is True
    assert looks_like_email("JASON CORP") is False


@patch("utils.sql_api_supplier.fetch_supplier_row_by_code")
def test_resolve_prefers_sql_api_company_over_stored_email(mock_fetch):
    mock_fetch.return_value = {"code": "400-J0001", "companyname": "JASON CORP"}
    assert (
        resolve_supplier_company_name("400-J0001", "jason.choo2004@gmail.com")
        == "JASON CORP"
    )


@patch("utils.sql_api_supplier.fetch_supplier_row_by_code")
def test_resolve_never_returns_email_as_company(mock_fetch):
    mock_fetch.return_value = {"code": "400-J0001", "companyname": "jason.choo2004@gmail.com"}
    assert resolve_supplier_company_name("400-J0001", "jason.choo2004@gmail.com") == "400-J0001"


@patch("utils.sql_api_supplier.fetch_supplier_row_by_code")
def test_resolve_keeps_valid_stored_name(mock_fetch):
    mock_fetch.return_value = None
    assert resolve_supplier_company_name("400-J0001", "JASON CORP") == "JASON CORP"
