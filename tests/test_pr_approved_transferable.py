from utils.procurement_bidding import apply_transferable_flags_for_approved_pr
from utils.procurement_purchase_order_transfer import _detail_is_transferable


def test_apply_transferable_flags_when_header_approved_no_awards():
    details = [
        {"id": 1, "quantity": 10, "remainingQty": 10, "transferable": False},
        {"id": 2, "quantity": 5, "remainingQty": 0, "transferable": False},
        {"id": 3, "quantity": 3, "remainingQty": 3, "udfPqApproved": False},
    ]
    gate = {"prUdfStatus": "APPROVED", "lineAwards": [], "approvedBid": None}
    apply_transferable_flags_for_approved_pr(47, details, gate=gate)
    assert details[0]["transferable"] is True
    assert details[0]["udfPqApproved"] is True
    assert details[1]["transferable"] is False
    assert details[2]["transferable"] is False


def test_apply_transferable_flags_restricts_to_line_awards():
    details = [
        {"id": 10, "quantity": 10, "remainingQty": 10},
        {"id": 20, "quantity": 5, "remainingQty": 5},
    ]
    gate = {
        "prUdfStatus": "APPROVED",
        "lineAwards": [{"detailId": 10}],
        "approvedBid": None,
    }
    apply_transferable_flags_for_approved_pr(47, details, gate=gate)
    assert details[0]["transferable"] is True
    assert details[1]["transferable"] is False


def test_detail_is_transferable_honors_approved_header_without_line_flag():
    source = {"transferable": False, "udf_pqapproved": None}
    assert _detail_is_transferable(source, header_udf_status="APPROVED") is True


def test_detail_is_transferable_rejects_explicit_line_rejection_on_approved_header():
    source = {"transferable": False, "udf_pqapproved": 0}
    assert _detail_is_transferable(source, header_udf_status="APPROVED") is False
