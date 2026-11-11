"""Focused tests for supplier bid line validation (quote vs remarks-only)."""
from decimal import Decimal

import pytest

from utils.procurement_bidding import (
    BID_LINE_INCOMPLETE_MSG,
    BiddingValidationError,
    _normalize_bid_lines,
    _sum_priced_bid_amounts,
    is_priced_bid_line,
    submit_supplier_bid,
)


def _line(detail_id=1, qty=None, price=None, remarks="", lead=0, **extra):
    row = {"detailId": detail_id, "leadDays": lead, "remarks": remarks}
    if qty is not None:
        row["quantity"] = qty
    if price is not None:
        row["unitPrice"] = price
    row.update(extra)
    return row


def test_valid_full_quotation_accepted():
    out = _normalize_bid_lines([_line(qty=10, price=20, remarks="")])
    assert len(out) == 1
    assert out[0]["quantity"] == Decimal("10.00")
    assert out[0]["unitPrice"] == Decimal("20.00")
    assert out[0]["amount"] == Decimal("200.00")
    assert out[0]["isQuoted"] is True
    assert out[0]["remarks"] == ""


def test_valid_quotation_with_remarks_accepted():
    out = _normalize_bid_lines([_line(qty=10, price=20, remarks="Available")])
    assert out[0]["isQuoted"] is True
    assert out[0]["remarks"] == "Available"
    assert out[0]["amount"] == Decimal("200.00")


def test_partial_bid_mixed_quote_and_remarks():
    out = _normalize_bid_lines(
        [
            _line(1, qty=5, price=10),
            _line(2, qty=8, price=12, remarks="ok"),
            _line(3, remarks="No stock"),
        ]
    )
    assert len(out) == 3
    assert out[0]["isQuoted"] is True
    assert out[1]["isQuoted"] is True
    assert out[2]["isQuoted"] is False
    assert out[2]["quantity"] == Decimal("0.00")
    assert out[2]["unitPrice"] == Decimal("0.00")
    assert out[2]["amount"] == Decimal("0.00")
    assert out[2]["remarks"] == "No stock"
    assert _sum_priced_bid_amounts(out) == Decimal("146.00")


def test_one_item_remarks_only_accepted():
    out = _normalize_bid_lines([_line(remarks="No stock")])
    assert out[0]["isQuoted"] is False
    assert out[0]["remarks"] == "No stock"
    assert out[0]["amount"] == Decimal("0.00")
    assert _sum_priced_bid_amounts(out) == Decimal("0.00")


def test_multi_item_remarks_only_accepted():
    out = _normalize_bid_lines(
        [
            _line(1, remarks="No stock"),
            _line(2, remarks="Cannot supply"),
            _line(3, remarks="Any nonempty text"),
        ]
    )
    assert all(not row["isQuoted"] for row in out)
    assert _sum_priced_bid_amounts(out) == Decimal("0.00")


def test_completely_empty_rejected():
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines([_line()])


def test_missing_quote_and_remarks_rejected():
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines(
            [
                _line(1, qty=10, price=5),
                _line(2),
            ]
        )


def test_whitespace_only_remarks_rejected():
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines([_line(remarks="   ")])


def test_qty_without_price_rejected():
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines([_line(qty=10)])


def test_price_without_qty_rejected():
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines([_line(price=20)])


def test_zero_qty_and_price_without_remarks_rejected():
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines([_line(qty=0, price=0)])


def test_prefilled_qty_alone_not_valid_quotation():
    """Bid Qty prefilled from request qty with empty price must not pass."""
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        _normalize_bid_lines([_line(qty=25, price=0, remarks="")])


def test_incomplete_numerics_with_remarks_cleared_as_unquoted():
    """Incomplete qty/price with remarks must not save as a priced line."""
    out = _normalize_bid_lines([_line(qty=10, price=0, remarks="No stock")])
    assert out[0]["isQuoted"] is False
    assert out[0]["quantity"] == Decimal("0.00")
    assert out[0]["unitPrice"] == Decimal("0.00")
    assert out[0]["amount"] == Decimal("0.00")
    assert out[0]["remarks"] == "No stock"

    out2 = _normalize_bid_lines([_line(qty=0, price=20, remarks="Cannot supply")])
    assert out2[0]["isQuoted"] is False
    assert out2[0]["quantity"] == Decimal("0.00")
    assert out2[0]["unitPrice"] == Decimal("0.00")


def test_remarks_only_excluded_from_total():
    lines = _normalize_bid_lines(
        [
            _line(1, qty=2, price=50),
            _line(2, remarks="No stock"),
        ]
    )
    assert _sum_priced_bid_amounts(lines) == Decimal("100.00")
    assert is_priced_bid_line(lines[0]) is True
    assert is_priced_bid_line(lines[1]) is False


def test_is_priced_bid_line_helpers():
    assert is_priced_bid_line({"quantity": 1, "unitPrice": 1}) is True
    assert is_priced_bid_line({"quantity": 0, "unitPrice": 1, "remarks": "x"}) is False
    assert is_priced_bid_line({"quantity": 1, "unitPrice": 0}) is False
    assert is_priced_bid_line(None) is False


def test_invalid_submit_never_opens_db(monkeypatch):
    """Validation runs before DB connect — invalid payload must not write."""
    opened = {"count": 0}

    def boom():
        opened["count"] += 1
        raise AssertionError("DB should not be opened for invalid bid lines")

    monkeypatch.setattr("utils.procurement_bidding._connect_db", boom)
    with pytest.raises(BiddingValidationError, match=BID_LINE_INCOMPLETE_MSG):
        submit_supplier_bid(
            request_dockey=1,
            request_no="PR-1",
            supplier_code="S1",
            supplier_name="Supplier",
            bid_lines=[_line()],
            remarks="",
            created_by="tester",
        )
    assert opened["count"] == 0


def test_multi_supplier_normalize_independent():
    """Each supplier payload validates independently (no shared state)."""
    a = _normalize_bid_lines([_line(1, qty=1, price=2), _line(2, remarks="No stock")])
    b = _normalize_bid_lines([_line(1, qty=3, price=4), _line(2, qty=5, price=6)])
    c = _normalize_bid_lines([_line(1, remarks="n/a"), _line(2, remarks="none")])
    assert _sum_priced_bid_amounts(a) == Decimal("2.00")
    assert _sum_priced_bid_amounts(b) == Decimal("42.00")
    assert _sum_priced_bid_amounts(c) == Decimal("0.00")
    assert a[1]["remarks"] == "No stock"
    assert b[1]["isQuoted"] is True
    assert all(not row["isQuoted"] for row in c)


def test_pr_mixed_quote_and_remarks_only_payload():
    """Regression: two quoted lines + one remarks-only (PR-26100061 style) must accept."""
    payload = [
        {"detailId": 171, "quantity": 4, "unitPrice": 5, "leadDays": 0, "remarks": ""},
        {"detailId": 172, "quantity": 4, "unitPrice": 6, "leadDays": 0, "remarks": ""},
        {"detailId": 173, "quantity": 0, "unitPrice": 0, "leadDays": 0, "remarks": "test"},
    ]
    out = _normalize_bid_lines(payload)
    assert len(out) == 3
    assert out[0]["isQuoted"] is True and out[0]["amount"] == Decimal("20.00")
    assert out[1]["isQuoted"] is True and out[1]["amount"] == Decimal("24.00")
    assert out[2]["isQuoted"] is False
    assert out[2]["quantity"] == Decimal("0.00")
    assert out[2]["unitPrice"] == Decimal("0.00")
    assert out[2]["amount"] == Decimal("0.00")
    assert out[2]["remarks"] == "test"
    assert _sum_priced_bid_amounts(out) == Decimal("44.00")


def test_submit_path_mixed_remarks_only_passes_normalize(monkeypatch):
    """submit_supplier_bid must get past validation for mixed quote + remarks-only."""
    opened = {"count": 0}

    class _BoomCon:
        def cursor(self):
            raise RuntimeError("reached-db-after-validation")

        def close(self):
            return None

        def rollback(self):
            return None

    def _connect():
        opened["count"] += 1
        return _BoomCon()

    monkeypatch.setattr("utils.procurement_bidding._connect_db", _connect)
    with pytest.raises(RuntimeError, match="reached-db-after-validation"):
        submit_supplier_bid(
            request_dockey=176,
            request_no="PR-26100061",
            supplier_code="400-K0001",
            supplier_name="Supplier",
            bid_lines=[
                _line(171, qty=4, price=5),
                _line(172, qty=4, price=6),
                _line(173, remarks="test"),
            ],
            remarks="",
            created_by="tester",
        )
    assert opened["count"] == 1


def test_old_qty_gt_zero_error_no_longer_raised_for_remarks_only():
    """Stale validator used 'bid quantity must be > 0'; remarks-only must not hit that."""
    out = _normalize_bid_lines([_line(173, qty=0, price=0, remarks="test")])
    assert out[0]["isQuoted"] is False
    assert out[0]["remarks"] == "test"
    assert out[0]["quantity"] == Decimal("0.00")
    assert out[0]["unitPrice"] == Decimal("0.00")
