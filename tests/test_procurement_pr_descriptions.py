"""PR header / line description normalization after bidding split."""
from utils.procurement_pr_descriptions import (
    DEFAULT_PR_HEADER_DESCRIPTION,
    is_placeholder_pr_line_description,
    is_split_pr_header_description,
    normalize_pr_header_description,
    resolve_pr_line_description,
)


def test_normalize_split_header_to_purchase_request():
    assert normalize_pr_header_description("Split from PR-26060029 — supplier 400-J0001") == (
        DEFAULT_PR_HEADER_DESCRIPTION
    )
    assert normalize_pr_header_description("Purchase Request | Split from PR-1 — supplier X") == (
        DEFAULT_PR_HEADER_DESCRIPTION
    )


def test_preserve_user_header_description():
    assert normalize_pr_header_description("Office supplies Q2") == "Office supplies Q2"


def test_placeholder_line_description_detected():
    assert is_placeholder_pr_line_description("Auto-selected from Overall Report (----)")
    assert not is_placeholder_pr_line_description("AL 6061-T6 ANOZ PL: 12.0MM")


def test_resolve_line_description_prefers_catalog_over_placeholder():
    resolved = resolve_pr_line_description(
        "AL 6061-T6 ANOZ PL: 12.0MM",
        "Auto-selected from Overall Report (----)",
        catalog_description="AL 6061-T6 ANOZ PL: 12.0MM",
    )
    assert resolved == "AL 6061-T6 ANOZ PL: 12.0MM"


def test_resolve_line_description_keeps_custom_text():
    resolved = resolve_pr_line_description(
        "ITEM-1",
        "Custom cut 1200mm",
        catalog_description="Generic item",
    )
    assert resolved == "Custom cut 1200mm"


def test_split_header_pattern():
    assert is_split_pr_header_description("Split from PR-26060029 — supplier 400-J0001")


def test_normalize_empty_header_to_purchase_request():
    assert normalize_pr_header_description("") == DEFAULT_PR_HEADER_DESCRIPTION
    assert normalize_pr_header_description(None) == DEFAULT_PR_HEADER_DESCRIPTION
