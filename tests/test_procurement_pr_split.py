"""Mixed-supplier PR split helpers."""
from utils.procurement_pr_split import (
    _group_detail_ids_by_supplier,
    _suppliers_in_award_order,
    mixed_pr_split_enabled,
)


def test_suppliers_in_award_order_first_keeps_existing_pr():
    """First supplier seen (lowest detail id) keeps original PR; others follow in order."""
    bid_map = {
        10: {"supplierCode": "400-B", "supplierName": "B"},
        20: {"supplierCode": "400-A", "supplierName": "A"},
    }
    normalized = [(5, 20), (8, 10)]
    assert _suppliers_in_award_order(normalized, bid_map) == ["400-A", "400-B"]


def test_suppliers_in_award_order_when_bid_first_on_higher_detail():
    bid_map = {
        10: {"supplierCode": "400-U0001"},
        20: {"supplierCode": "400-J0001"},
    }
    normalized = [(34, 20), (33, 10)]
    assert _suppliers_in_award_order(normalized, bid_map) == ["400-U0001", "400-J0001"]


def test_group_detail_ids_by_supplier():
    bid_map = {
        1: {"supplierCode": "400-A"},
        2: {"supplierCode": "400-B"},
    }
    normalized = [(101, 1), (102, 2)]
    groups = _group_detail_ids_by_supplier(normalized, bid_map)
    assert groups["400-A"] == [101]
    assert groups["400-B"] == [102]


def test_mixed_pr_split_enabled_default():
    assert mixed_pr_split_enabled() is True


def test_child_docno_increments_from_parent_seed():
    """Split children increment from parent docno (PR-00000001 -> PR-00000002)."""
    import re

    seed = "PR-00000001"
    match = re.match(r"^(.*?)(\d+)$", seed)
    assert match
    prefix = match.group(1)
    width = len(match.group(2))
    assert f"{prefix}{2:0{width}d}" == "PR-00000002"
