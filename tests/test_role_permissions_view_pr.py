"""Purchase visibility = roles; e-PR/PO actions = UDF_APPROVEPQ / UDF_APPROVEPO."""
from utils.role_permissions import (
    ACCESS_TIER_CUSTOMER,
    ACCESS_TIER_DIRECTOR,
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_HOD,
    ACCESS_TIER_NO_ROLE,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_PURCH_USER,
    ACCESS_TIER_SALES_MGMT,
    ACCESS_TIER_SALES_STAFF,
    can_access_purchase_menu,
    can_apply_pr_header_udf_change,
    can_approve_purchase_requisition,
    can_see_view_pr,
    can_transfer_pr_to_po,
    compute_access_tier,
    hide_pr_awaiting_tab,
    hide_pr_approval_edits_for_pstaff,
    hide_pr_transfer_for_pstaff,
    staff_has_any_mapped_role_udf,
    staff_udf_from_sy_user_row,
)


def test_legacy_five_udfs_are_ignored():
    flags = staff_udf_from_sy_user_row(
        {
            "UDF_MANAGEMENT": "T",
            "UDF_PMANAGEMENT": "T",
            "UDF_PUSER": "T",
            "UDF_SMANAGEMENT": "T",
            "UDF_SUSER": "T",
        }
    )
    assert not any(flags.values())
    assert staff_has_any_mapped_role_udf(flags) is False
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf=flags,
            sy_user_row_present=True,
        )
        == ACCESS_TIER_NO_ROLE
    )


def test_ispurmgr_column_alias_maps():
    flags = staff_udf_from_sy_user_row({"UDF_ISPURMGR": "T"})
    assert flags.get("ispurmng") is True
    flags2 = staff_udf_from_sy_user_row({"UDF_ISPURMNG": "T"})
    assert flags2.get("ispurmng") is True


def test_ispuruser_and_approval_flags_map():
    flags = staff_udf_from_sy_user_row(
        {
            "UDF_ISPURUSER": "T",
            "UDF_APPROVEPQ": "T",
            "UDF_APPROVEPO": "T",
        }
    )
    assert flags.get("ispuruser") is True
    assert flags.get("approve_pq") is True
    assert flags.get("approve_po") is True


def test_ispurhod_maps_and_other_dept_hods_ignored():
    flags = staff_udf_from_sy_user_row({"UDF_ISPURHOD": "T"})
    assert flags.get("ispurhod") is True
    other = staff_udf_from_sy_user_row(
        {
            "UDF_ISSALESHOD": "T",
            "UDF_ISPRDHOD": "T",
            "UDF_ISSTRHOD": "T",
            "UDF_ISQAHOD": "T",
            "UDF_ISFINHOD": "T",
            "UDF_ISHOD": "T",
        }
    )
    assert other.get("ispurhod") is not True
    assert staff_has_any_mapped_role_udf(other) is False


def test_new_role_flags_map_and_priority():
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"isadmin": True, "ispurmng": True, "ispurhod": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_FULL_ADMIN
    )
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"ispurmng": True, "ispurhod": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_PURCH_MGMT
    )
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"ispurhod": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_HOD
    )
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"isdirector": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_DIRECTOR
    )
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"ispuruser": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_PURCH_USER
    )


def test_all_role_false_cannot_see_view_pr():
    session = {"access_tier": ACCESS_TIER_NO_ROLE}
    assert can_see_view_pr(session) is False
    assert can_access_purchase_menu(session) is False
    session = {"access_tier": ACCESS_TIER_SALES_STAFF}
    assert can_see_view_pr(session) is False
    session = {"access_tier": ACCESS_TIER_SALES_MGMT}
    assert can_see_view_pr(session) is False
    session = {"access_tier": ACCESS_TIER_CUSTOMER}
    assert can_see_view_pr(session) is False


def test_any_purchase_role_can_see_view_pr():
    for tier in (
        ACCESS_TIER_FULL_ADMIN,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_HOD,
        ACCESS_TIER_DIRECTOR,
        ACCESS_TIER_PURCH_USER,
    ):
        assert can_see_view_pr({"access_tier": tier}) is True
        assert can_access_purchase_menu({"access_tier": tier}) is True


def test_sales_tier_still_sees_purchase_when_role_flags_set():
    session = {
        "access_tier": ACCESS_TIER_SALES_MGMT,
        "staff_udf": {"isadmin": True},
    }
    assert can_see_view_pr(session) is True
    assert can_access_purchase_menu(session) is True


def test_customer_portal_never_sees_purchase_even_with_staff_udf():
    session = {
        "access_tier": ACCESS_TIER_CUSTOMER,
        "login_mode": "customer",
        "staff_udf": {"isadmin": True, "ispurmng": True, "ispurhod": True},
        "user_type": "user",
    }
    assert can_see_view_pr(session) is False
    assert can_access_purchase_menu(session) is False


def test_customer_login_mode_blocks_purchase_even_if_tier_polluted():
    session = {
        "access_tier": ACCESS_TIER_FULL_ADMIN,
        "login_mode": "customer",
        "staff_udf": {"isadmin": True},
        "user_type": "admin",
    }
    assert can_see_view_pr(session) is False
    assert can_access_purchase_menu(session) is False


def test_roles_see_all_tabs_actions_need_approval_udfs():
    """Role alone: all tabs visible; no approve / transfer without APPROVEPQ / APPROVEPO."""
    for tier in (
        ACCESS_TIER_HOD,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_DIRECTOR,
        ACCESS_TIER_PURCH_USER,
    ):
        session = {"access_tier": tier, "staff_udf": {}}
        assert hide_pr_awaiting_tab(session) is False
        assert hide_pr_transfer_for_pstaff(session) is True
        assert hide_pr_approval_edits_for_pstaff(session) is True
        assert can_approve_purchase_requisition(session) is False
        assert can_transfer_pr_to_po(session) is False
        assert can_apply_pr_header_udf_change(session, "DRAFT", "SUBMITTED") is True
        assert can_apply_pr_header_udf_change(session, "AWAITING", "PENDING") is False


def test_approvepq_enables_requisition_actions():
    session = {
        "access_tier": ACCESS_TIER_PURCH_USER,
        "staff_udf": {"ispuruser": True, "approve_pq": True},
    }
    assert can_approve_purchase_requisition(session) is True
    assert hide_pr_approval_edits_for_pstaff(session) is False
    assert can_apply_pr_header_udf_change(session, "AWAITING", "PENDING") is True
    assert can_transfer_pr_to_po(session) is False
    assert hide_pr_transfer_for_pstaff(session) is True


def test_approvepo_enables_transfer():
    session = {
        "access_tier": ACCESS_TIER_PURCH_MGMT,
        "staff_udf": {"ispurmng": True, "approve_po": True},
    }
    assert can_transfer_pr_to_po(session) is True
    assert hide_pr_transfer_for_pstaff(session) is False
    assert can_approve_purchase_requisition(session) is False


def test_admin_bypasses_approval_udfs():
    session = {"access_tier": ACCESS_TIER_FULL_ADMIN, "staff_udf": {"isadmin": True}}
    assert hide_pr_awaiting_tab(session) is False
    assert can_approve_purchase_requisition(session) is True
    assert can_transfer_pr_to_po(session) is True
    assert hide_pr_transfer_for_pstaff(session) is False
    assert hide_pr_approval_edits_for_pstaff(session) is False
    assert can_apply_pr_header_udf_change(session, "AWAITING", "PENDING") is True
