"""Supplier bidding row colour / award state helpers."""
from utils.procurement_bidding import get_supplier_bidding_award_state, is_pr_line_awards_locked


def test_line_awards_lock_only_after_save_or_cancelled():
    # Save Item is what promotes Pending → Approved; APPROVED alone must stay editable.
    assert is_pr_line_awards_locked("PENDING") is False
    assert is_pr_line_awards_locked("APPROVED") is False
    assert is_pr_line_awards_locked("APPROVED", has_line_awards=True) is True
    assert is_pr_line_awards_locked("PENDING", has_line_awards=True) is True
    assert is_pr_line_awards_locked("CANCELLED") is True


def test_full_award_not_partial(monkeypatch):
    monkeypatch.setattr(
        "utils.procurement_bidding.get_merged_line_awards_for_request",
        lambda _dk: [
            {"detailId": 1, "supplierCode": "S1"},
            {"detailId": 2, "supplierCode": "S1"},
        ],
    )
    monkeypatch.setattr(
        "utils.procurement_bidding.resolve_bidding_context",
        lambda _dk: {"prDetailIds": [1, 2], "biddingSourceDockey": _dk},
    )
    my_bid = {"lines": [{"detailId": 1}, {"detailId": 2}]}
    state = get_supplier_bidding_award_state(10, "S1", my_bid)
    assert state["awardedDetailIds"] == [1, 2]
    assert state["hasLineAwards"] is True
    assert state["hasPartialLineAwards"] is False


def test_mixed_suppliers_is_partial(monkeypatch):
    monkeypatch.setattr(
        "utils.procurement_bidding.get_merged_line_awards_for_request",
        lambda _dk: [
            {"detailId": 1, "supplierCode": "S1"},
            {"detailId": 2, "supplierCode": "S2"},
        ],
    )
    monkeypatch.setattr(
        "utils.procurement_bidding.resolve_bidding_context",
        lambda _dk: {"prDetailIds": [1, 2], "biddingSourceDockey": _dk},
    )
    state = get_supplier_bidding_award_state(10, "S1", {"lines": [{"detailId": 1}]})
    assert state["hasPartialLineAwards"] is True
    assert state["awardedDetailIds"] == [1]


def test_subset_award_is_partial(monkeypatch):
    monkeypatch.setattr(
        "utils.procurement_bidding.get_merged_line_awards_for_request",
        lambda _dk: [{"detailId": 1, "supplierCode": "S1"}],
    )
    monkeypatch.setattr(
        "utils.procurement_bidding.resolve_bidding_context",
        lambda _dk: {"prDetailIds": [1, 2], "biddingSourceDockey": _dk},
    )
    my_bid = {"lines": [{"detailId": 1}, {"detailId": 2}]}
    state = get_supplier_bidding_award_state(10, "S1", my_bid)
    assert state["hasPartialLineAwards"] is True
    assert state["awardedDetailIds"] == [1]
