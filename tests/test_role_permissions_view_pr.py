"""Purchase / View e-PR gates use UDF_ISADMIN / ISHOD / ISPURMNG / ISDIRECTOR only."""
from utils.role_permissions import (
    ACCESS_TIER_CUSTOMER,
    ACCESS_TIER_DIRECTOR,
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_HOD,
    ACCESS_TIER_NO_ROLE,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_SALES_MGMT,
    ACCESS_TIER_SALES_STAFF,
    can_access_purchase_menu,
    can_apply_pr_header_udf_change,
    can_see_view_pr,
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


def test_new_role_flags_map_and_priority():
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"isadmin": True, "ispurmng": True, "ishod": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_FULL_ADMIN
    )
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"ispurmng": True, "ishod": True},
            sy_user_row_present=True,
        )
        == ACCESS_TIER_PURCH_MGMT
    )
    assert (
        compute_access_tier(
            is_supplier=False,
            is_customer=False,
            staff_udf={"ishod": True},
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


def test_all_four_false_cannot_see_view_pr():
    session = {"access_tier": ACCESS_TIER_NO_ROLE}
    assert can_see_view_pr(session) is False
    assert can_access_purchase_menu(session) is False
    session = {"access_tier": ACCESS_TIER_SALES_STAFF}
    assert can_see_view_pr(session) is False
    session = {"access_tier": ACCESS_TIER_SALES_MGMT}
    assert can_see_view_pr(session) is False
    session = {"access_tier": ACCESS_TIER_CUSTOMER}
    assert can_see_view_pr(session) is False


def test_any_of_four_can_see_view_pr():
    for tier in (
        ACCESS_TIER_FULL_ADMIN,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_HOD,
        ACCESS_TIER_DIRECTOR,
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


def test_hod_hides_transfer_and_approval_edits():
    session = {"access_tier": ACCESS_TIER_HOD}
    assert hide_pr_transfer_for_pstaff(session) is True
    assert hide_pr_approval_edits_for_pstaff(session) is True
    assert hide_pr_awaiting_tab(session) is False


def test_hod_can_move_awaiting_to_pending():
    session = {"access_tier": ACCESS_TIER_HOD}
    assert can_apply_pr_header_udf_change(session, "AWAITING", "PENDING") is True
    assert can_apply_pr_header_udf_change(session, "AWAITING", "CANCELLED") is True
    assert can_apply_pr_header_udf_change(session, "PENDING", "APPROVED") is False
    assert can_apply_pr_header_udf_change(session, "AWAITING", "APPROVED") is False


def test_purch_mng_hides_awaiting_tab_only():
    session = {"access_tier": ACCESS_TIER_PURCH_MGMT}
    assert hide_pr_awaiting_tab(session) is True
    assert hide_pr_transfer_for_pstaff(session) is False
    assert hide_pr_approval_edits_for_pstaff(session) is False
    assert can_apply_pr_header_udf_change(session, "PENDING", "APPROVED") is True
