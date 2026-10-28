"""Auto-approve PH_PQ.UDF_STATUS when item awards are saved."""
from __future__ import annotations

import pytest

from utils.procurement_bidding import (
    BiddingValidationError,
    _promote_pr_udf_approved_after_awards,
)


class _Cursor:
    def __init__(self, rows_by_id: dict[int, tuple]):
        self.rows_by_id = rows_by_id
        self.statements: list[tuple[str, tuple | None]] = []
        self.rowcount = 1
        self._pending_id: int | None = None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        text = str(sql or "")
        if "SELECT FIRST 1" in text.upper() and "FROM PH_PQ" in text.upper() and params:
            try:
                self._pending_id = int(params[-1])
            except Exception:
                self._pending_id = None
        else:
            self._pending_id = None

    def fetchone(self):
        if self._pending_id is None:
            return None
        return self.rows_by_id.get(self._pending_id)


def test_promote_pending_to_approved_for_parent_and_children(monkeypatch):
    from utils import procurement_bidding as bidding
    from utils import procurement_purchase_request as ppr

    cur = _Cursor(
        {
            159: ("PENDING", 1),
            160: ("PENDING", 1),
        }
    )
    monkeypatch.setattr(
        bidding,
        "_get_table_columns",
        lambda _cur, table: {"DOCKEY", "UDF_STATUS", "STATUS"},
    )
    monkeypatch.setattr(ppr, "_column_is_numeric", lambda _cur, table, column: True)

    applied = _promote_pr_udf_approved_after_awards(cur, {159, 160, 0})

    updates = [item for item in cur.statements if "UPDATE PH_PQ" in item[0]]
    assert len(updates) == 2
    assert updates[0] == (
        "UPDATE PH_PQ SET UDF_STATUS = ? WHERE DOCKEY = ?",
        ("APPROVED", 159),
    )
    assert updates[1] == (
        "UPDATE PH_PQ SET UDF_STATUS = ? WHERE DOCKEY = ?",
        ("APPROVED", 160),
    )
    assert [c["requestId"] for c in applied] == [159, 160]
    assert all(c["udfStatus"] == "APPROVED" for c in applied)
    assert all(c["previousUdfStatus"] == "PENDING" for c in applied)


def test_promote_already_approved_is_idempotent(monkeypatch):
    from utils import procurement_bidding as bidding
    from utils import procurement_purchase_request as ppr

    cur = _Cursor({42: ("APPROVED", 1)})
    monkeypatch.setattr(
        bidding,
        "_get_table_columns",
        lambda _cur, table: {"DOCKEY", "UDF_STATUS", "STATUS"},
    )
    monkeypatch.setattr(ppr, "_column_is_numeric", lambda _cur, table, column: True)

    applied = _promote_pr_udf_approved_after_awards(cur, [42])
    updates = [item for item in cur.statements if "UPDATE PH_PQ" in item[0]]
    assert len(updates) == 1
    assert updates[0][1] == ("APPROVED", 42)
    assert applied[0]["previousUdfStatus"] == "APPROVED"


def test_promote_rejects_awaiting_to_approved(monkeypatch):
    from utils import procurement_bidding as bidding
    from utils import procurement_purchase_request as ppr

    cur = _Cursor({77: ("AWAITING", 1)})
    monkeypatch.setattr(
        bidding,
        "_get_table_columns",
        lambda _cur, table: {"DOCKEY", "UDF_STATUS", "STATUS"},
    )
    monkeypatch.setattr(ppr, "_column_is_numeric", lambda _cur, table, column: True)

    with pytest.raises(BiddingValidationError, match="Invalid UDF_STATUS transition"):
        _promote_pr_udf_approved_after_awards(cur, [77])


def test_promote_empty_dockeys_noop():
    cur = _Cursor({})
    assert _promote_pr_udf_approved_after_awards(cur, set()) == []
