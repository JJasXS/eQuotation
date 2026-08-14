"""Location scope from SY_USER.UDF_LOCATION for View/Create e-PR."""
from utils.role_permissions import (
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_PURCH_STAFF,
    location_in_scope,
    session_location_scope,
    staff_locations_from_sy_user_row,
)


def test_staff_locations_from_sy_user_row_parses_single():
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": "KL"}) == ["KL"]
    assert staff_locations_from_sy_user_row({"udf_location": "kl"}) == ["KL"]


def test_staff_locations_from_sy_user_row_parses_multi():
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": "KL,JB"}) == ["KL", "JB"]
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": " kl ; jb "}) == ["KL", "JB"]
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": "KL|JB|KL"}) == ["KL", "JB"]


def test_staff_locations_from_sy_user_row_empty_cases():
    assert staff_locations_from_sy_user_row(None) == []
    assert staff_locations_from_sy_user_row({}) == []
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": ""}) == []
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": " , ; "}) == []


def test_staff_locations_keeps_dash_placeholder_as_real_location():
    """``----`` is a real ST_LOCATION code, not null."""
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": "----"}) == ["----"]
    assert staff_locations_from_sy_user_row({"UDF_LOCATION": "KL,----"}) == ["KL", "----"]


def test_session_location_scope_admin_bypass():
    assert session_location_scope({"access_tier": ACCESS_TIER_FULL_ADMIN, "staff_locations": ["KL"]}) is None
    assert session_location_scope({"access_tier": ACCESS_TIER_PURCH_MGMT, "staff_locations": ["KL"]}) is None


def test_session_location_scope_blank_means_all():
    assert session_location_scope({"access_tier": ACCESS_TIER_PURCH_STAFF}) is None
    assert session_location_scope({"access_tier": ACCESS_TIER_PURCH_STAFF, "staff_locations": []}) is None
    assert session_location_scope({"access_tier": ACCESS_TIER_PURCH_STAFF, "staff_locations": None}) is None


def test_session_location_scope_purchase_staff_restricted():
    assert session_location_scope(
        {"access_tier": ACCESS_TIER_PURCH_STAFF, "staff_locations": ["KL"]}
    ) == ["KL"]
    assert session_location_scope(
        {"access_tier": ACCESS_TIER_PURCH_STAFF, "staff_locations": ["kl", "JB", "----", ""]}
    ) == ["KL", "JB", "----"]


def test_session_location_scope_dash_location_restricts():
    assert session_location_scope(
        {"access_tier": ACCESS_TIER_PURCH_STAFF, "staff_locations": ["----"]}
    ) == ["----"]


def test_location_in_scope_rules():
    assert location_in_scope(None, "JB") is True
    assert location_in_scope(None, "----") is True
    assert location_in_scope(["KL"], "") is False
    assert location_in_scope(["KL"], "----") is False
    assert location_in_scope(["----"], "----") is True
    assert location_in_scope(["----"], "JB") is False
    assert location_in_scope(["KL"], "kl") is True
    assert location_in_scope(["KL"], "JB") is False
    assert location_in_scope(["KL", "JB"], "jb") is True
