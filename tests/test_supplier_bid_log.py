"""Supplier bid log (full submitted lines + accept/reject decision)."""
from utils.procurement_bidding import build_supplier_bid_log


def test_bid_log_marks_accepted_and_rejected_lines(monkeypatch):
    monkeypatch.setattr(
        "utils.procurement_bidding.resolve_bidding_context",
        lambda _dk: {"biddingSourceDockey": 1, "prDetailIds": [10, 20], "docno": "PR-1"},
    )

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return (5, 1, "PR-1", "S1", "Supplier 1", "APPROVED", "", "u", None, "admin", None, "")

        def fetchall(self):
            return []

    class FakeCon:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr("utils.procurement_bidding._connect_db", lambda: FakeCon())
    monkeypatch.setattr("utils.procurement_bidding._ensure_pr_bid_hdr_udf_reason", lambda _c: None)
    monkeypatch.setattr(
        "utils.procurement_bidding._bid_hdr_row_to_lines",
        lambda _cur, _bid: [
            {"detailId": 10, "itemCode": "", "description": "", "quantity": 1, "unitPrice": 10, "amount": 10, "leadDays": 0, "remarks": "", "tax": 0},
            {"detailId": 20, "itemCode": "B", "description": "Item B", "quantity": 2, "unitPrice": 5, "amount": 10, "leadDays": 0, "remarks": "", "tax": 0},
        ],
    )
    monkeypatch.setattr(
        "utils.procurement_bidding._fetch_pr_detail_rows_by_dtlkeys",
        lambda _cur, _ids: {
            10: {"itemCode": "A", "description": "Item A", "quantity": 1, "suomQty": 0, "deliveryDate": None},
            20: {"itemCode": "B", "description": "Item B", "quantity": 2, "suomQty": 0, "deliveryDate": None},
        },
    )
    monkeypatch.setattr(
        "utils.procurement_bidding.get_merged_line_awards_for_request",
        lambda _dk: [{"detailId": 10, "supplierCode": "S1"}],
    )
    monkeypatch.setattr(
        "utils.procurement_bidding._re_enrich_bids_from_pr_details",
        lambda *_args, **_kwargs: None,
    )

    log = build_supplier_bid_log(1, "S1")
    assert len(log) == 2
    assert log[0]["itemCode"] == "A"
    assert log[0]["decision"] == "accepted"
    assert log[1]["decision"] == "not_accepted"
