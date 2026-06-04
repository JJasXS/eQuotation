"""Bid line item labels after mixed-supplier PR split."""
from utils.procurement_bidding import (
    _enrich_bid_lines_from_pr_details,
    _merged_pr_detail_item_map,
    _re_enrich_bids_from_pr_details,
)


class _FakeCursor:
    def __init__(self, maps: dict[int, dict[int, dict[str, str]]]):
        self._maps = maps

    def execute(self, *_args, **_kwargs):
        return None

    def fetchall(self):
        return []


def test_enrich_bid_lines_from_child_detail_map():
    lines = [{"detailId": 42, "itemCode": "", "description": ""}]
    detail_map = {42: {"itemCode": "ITEM-B", "description": "Widget B"}}
    out = _enrich_bid_lines_from_pr_details(None, 0, lines, detail_map)
    assert out[0]["itemCode"] == "ITEM-B"
    assert out[0]["description"] == "Widget B"


def test_merged_detail_map_prefers_later_child_rows(monkeypatch):
    parent_map = {10: {"itemCode": "OLD", "description": "Old desc"}}
    child_map = {10: {"itemCode": "ITEM-B", "description": "Widget B"}}

    def fake_fetch(_cur, dockey):
        if dockey == 1:
            return parent_map
        if dockey == 2:
            return child_map
        return {}

    monkeypatch.setattr(
        "utils.procurement_bidding._fetch_pr_detail_item_map",
        fake_fetch,
    )
    merged = _merged_pr_detail_item_map(_FakeCursor({}), 1, 2)
    assert merged[10]["itemCode"] == "ITEM-B"


def test_re_enrich_bids_fills_missing_item_labels(monkeypatch):
    monkeypatch.setattr(
        "utils.procurement_bidding._merged_pr_detail_item_map",
        lambda _cur, *ids: {99: {"itemCode": "ITEM-2", "description": "Second item"}},
    )
    bids = [{"lines": [{"detailId": 99, "itemCode": "", "description": ""}]}]
    _re_enrich_bids_from_pr_details(_FakeCursor({}), bids, 1, 2)
    assert bids[0]["lines"][0]["itemCode"] == "ITEM-2"
    assert bids[0]["lines"][0]["description"] == "Second item"
