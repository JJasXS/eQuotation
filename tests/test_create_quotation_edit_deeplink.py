"""Draft Quotation edit: customers only; Admin/Staff Drafts are view-only."""
from utils.role_permissions import (
    ACCESS_TIER_CUSTOMER,
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_SALES_MGMT,
    ACCESS_TIER_SALES_STAFF,
    can_access_create_quotation,
    can_edit_own_draft_quotations,
    can_open_create_quotation_page,
)


def test_customer_can_blank_create_and_edit_own_draft_deeplink():
    session = {"access_tier": ACCESS_TIER_CUSTOMER}
    assert can_access_create_quotation(session) is True
    assert can_edit_own_draft_quotations(session) is True
    assert can_open_create_quotation_page(session) is True
    assert can_open_create_quotation_page(session, draft_dockey="42") is True
    assert can_open_create_quotation_page(session, dockey="99") is True


def test_customer_login_mode_allows_draft_edit_even_if_tier_missing():
    session = {"login_mode": "customer", "user_type": "user"}
    assert can_edit_own_draft_quotations(session) is True
    # Blank create still needs create-quotation access (customer tier inferred from user_type)
    assert can_open_create_quotation_page(session, draft_dockey="42") is True


def test_full_admin_cannot_create_or_open_draft_edit_deeplink():
    session = {"access_tier": ACCESS_TIER_FULL_ADMIN, "staff_udf": {"isadmin": True}}
    assert can_access_create_quotation(session) is False
    assert can_edit_own_draft_quotations(session) is False
    assert can_open_create_quotation_page(session) is False
    assert can_open_create_quotation_page(session, draft_dockey="42") is False
    assert can_open_create_quotation_page(session, dockey="99") is False


def test_sales_mgmt_can_blank_create_but_not_draft_edit_deeplink():
    session = {"access_tier": ACCESS_TIER_SALES_MGMT, "staff_udf": {"issalesmgr": True}}
    assert can_access_create_quotation(session) is True
    assert can_edit_own_draft_quotations(session) is False
    assert can_open_create_quotation_page(session) is True
    assert can_open_create_quotation_page(session, draft_dockey="7") is False
    assert can_open_create_quotation_page(session, dockey="8") is False


def test_sales_staff_can_blank_create_but_not_draft_edit_deeplink():
    session = {"access_tier": ACCESS_TIER_SALES_STAFF, "staff_udf": {"issales": True}}
    assert can_access_create_quotation(session) is True
    assert can_edit_own_draft_quotations(session) is False
    assert can_open_create_quotation_page(session, draft_dockey="3") is False


def test_purchasing_cannot_open_create_even_with_deeplink():
    session = {"access_tier": ACCESS_TIER_PURCH_MGMT, "staff_udf": {"ispurmng": True}}
    assert can_access_create_quotation(session) is False
    assert can_edit_own_draft_quotations(session) is False
    assert can_open_create_quotation_page(session, draft_dockey="42") is False
    assert can_open_create_quotation_page(session, dockey="99") is False
