"""Cancelled tab: PR UDF status mapping and bid submit guards (no DB writes)."""
import pytest

from utils.procurement_bidding import (
    BiddingValidationError,
    is_pr_line_awards_locked,
    normalize_pr_udf_status,
    submit_supplier_bid,
)


def test_normalize_inactive_udf_is_cancelled():
    assert normalize_pr_udf_status("CANCELLED") == "CANCELLED"
    assert normalize_pr_udf_status("inactive") == "CANCELLED"
    assert normalize_pr_udf_status("APPROVED") == "APPROVED"
    assert normalize_pr_udf_status("ACTIVE") == "APPROVED"


def test_cancelled_pr_locks_awards():
    assert is_pr_line_awards_locked("CANCELLED") is True
    assert is_pr_line_awards_locked("INACTIVE") is True


def test_submit_bid_rejects_cancelled_pr(monkeypatch):
    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchone(self):
            # INVITE_ID, STATUS, SUPPLIER_NAME
            return (1, "OPEN", "Acme")

    class _Con:
        def cursor(self):
            return _Cur()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("utils.procurement_bidding._connect_db", lambda: _Con())
    monkeypatch.setattr(
        "utils.procurement_bidding.get_pr_udf_status_local",
        lambda _dk: "CANCELLED",
    )
    monkeypatch.setattr(
        "utils.procurement_bidding._normalize_bid_lines",
        lambda lines: lines or [{"detailId": 1, "quantity": 1, "unitPrice": 1, "taxAmt": 0, "amount": 1, "leadDays": 0, "remarks": ""}],
    )

    with pytest.raises(BiddingValidationError, match="cancelled"):
        submit_supplier_bid(
            request_dockey=99,
            request_no="PR-99",
            supplier_code="S1",
            supplier_name="Acme",
            bid_lines=[{"detailId": 1, "quantity": 1, "unitPrice": 1}],
            remarks="",
            created_by="S1",
        )


def test_list_invitations_marks_cancelled(monkeypatch):
    from utils import procurement_bidding as pb

    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchall(self):
            # invite + bid join columns used by list_supplier_invitations
            return [
                (
                    10,  # INVITE_ID
                    50,  # REQUEST_DOCKEY
                    "PR-50",
                    "S1",
                    "Acme",
                    "OPEN",
                    None,  # CREATED_AT
                    None,  # BID_ID
                    None,  # BID_HDR_STATUS
                    None,  # BID_CREATED_AT
                    None,  # BID_APPROVED_AT
                )
            ]

    class _Con:
        def cursor(self):
            return _Cur()

        def close(self):
            return None

    monkeypatch.setattr(pb, "_connect_db", lambda: _Con())
    monkeypatch.setattr(pb, "_fetch_bid_amount_stats_by_bid_ids", lambda _ids: {})
    monkeypatch.setattr(
        pb,
        "_fetch_pr_card_facts",
        lambda _keys: {
            50: {
                "requestDescription": "Cancelled PR",
                "project": "",
                "docDate": None,
                "requestDeliveryDate": "01-01-2026",
                "lineCount": 2,
                "firstItem": "Item A",
            }
        },
    )
    monkeypatch.setattr(pb, "map_pr_udf_status_local", lambda _ids: {50: "CANCELLED"})

    rows = pb.list_supplier_invitations("S1")
    assert len(rows) == 1
    assert rows[0]["requestUdfStatus"] == "CANCELLED"
    assert rows[0]["prCancelled"] is True
    assert rows[0]["supplierCode"] == "S1"
    assert rows[0]["requestNumber"] == "PR-50"
    assert rows[0]["lineCount"] == 2
