"""Per-line UDF_SUPCODE / UDF_SUPNAME on award save (no mixed PR split)."""
from __future__ import annotations

from utils.procurement_bidding import (
    _apply_awarded_suppliers_to_pr_details,
    _first_award_supplier,
)


class _Cursor:
    def __init__(self, columns: set[str]):
        self.columns = set(columns)
        self.statements: list[tuple[str, tuple | None]] = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.statements.append((sql, params))


def test_apply_awarded_suppliers_updates_both_udf_columns(monkeypatch):
    from utils import procurement_bidding as bidding

    cur = _Cursor({"DTLKEY", "DOCKEY", "UDF_SUPCODE", "UDF_SUPNAME", "ITEMCODE"})
    monkeypatch.setattr(bidding, "_table_exists", lambda _cur, name: name == "PH_PQDTL")
    monkeypatch.setattr(
        bidding,
        "_get_table_columns",
        lambda _cur, table: set(cur.columns),
    )

    bid_map = {
        10: {"supplierCode": "400-J0001", "supplierName": "JASON CORP"},
        20: {"supplierCode": "400-K0001", "supplierName": "KLEK SDN BHD"},
    }
    updated = _apply_awarded_suppliers_to_pr_details(
        cur,
        [(101, 10), (102, 20)],
        bid_map,
    )
    assert updated == 2
    updates = [item for item in cur.statements if "UPDATE PH_PQDTL" in item[0]]
    assert len(updates) == 2
    assert updates[0][1] == ("400-J0001", "JASON CORP", 101)
    assert updates[1][1] == ("400-K0001", "KLEK SDN BHD", 102)
    assert "UDF_SUPCODE = ?" in updates[0][0]
    assert "UDF_SUPNAME = ?" in updates[0][0]


def test_apply_awarded_suppliers_noop_without_columns(monkeypatch):
    from utils import procurement_bidding as bidding

    cur = _Cursor({"DTLKEY", "DOCKEY", "ITEMCODE"})
    monkeypatch.setattr(bidding, "_table_exists", lambda _cur, name: name == "PH_PQDTL")
    monkeypatch.setattr(
        bidding,
        "_get_table_columns",
        lambda _cur, table: set(cur.columns),
    )
    updated = _apply_awarded_suppliers_to_pr_details(
        cur,
        [(101, 10)],
        {10: {"supplierCode": "400-J0001", "supplierName": "JASON"}},
    )
    assert updated == 0
    assert cur.statements == []


def test_first_award_supplier_by_lowest_detail_id():
    bid_map = {
        10: {"supplierCode": "400-B", "supplierName": "B"},
        20: {"supplierCode": "400-A", "supplierName": "A"},
    }
    assert _first_award_supplier([(8, 10), (5, 20)], bid_map) == ("400-A", "A")


def test_save_line_awards_does_not_call_split(monkeypatch):
    from utils import procurement_bidding as bidding

    calls = {"split": 0}

    def _boom(*_a, **_k):
        calls["split"] += 1
        raise AssertionError("split must not be called")

    monkeypatch.setattr(
        "utils.procurement_pr_split.split_purchase_request_for_mixed_awards",
        _boom,
        raising=False,
    )
    monkeypatch.setattr(bidding, "_ensure_line_supplier_udf_columns_ready", lambda: None)
    monkeypatch.setattr(bidding, "assert_pr_line_awards_editable", lambda *_a, **_k: None)

    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchall(self):
            return [(10, 159, "400-A", "A"), (20, 159, "400-B", "B")]

        def fetchone(self):
            return None

        def close(self):
            return None

    class _Con:
        def cursor(self):
            return _Cur()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(bidding, "_connect_db", lambda: _Con())
    monkeypatch.setattr(bidding, "_table_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(bidding, "_next_key", lambda *_a, **_k: 1)
    monkeypatch.setattr(bidding, "_apply_awarded_suppliers_to_pr_details", lambda *_a, **_k: 2)
    monkeypatch.setattr(bidding, "_apply_awarded_bid_pricing_to_pr_details", lambda *_a, **_k: {159})
    monkeypatch.setattr(bidding, "_promote_pr_udf_approved_after_awards", lambda *_a, **_k: [])
    monkeypatch.setattr(
        bidding,
        "_first_award_supplier",
        lambda *_a, **_k: ("400-A", "A"),
    )

    # Bid DTL validation: return matching pairs for both awards.
    fetch_seq = {
        "bids": [(10, 159, "400-A", "A"), (20, 159, "400-B", "B")],
        "dtl": [(10, 101), (20, 102)],
    }

    class _Cur2(_Cur):
        def __init__(self):
            self._n = 0

        def fetchall(self):
            self._n += 1
            if self._n == 1:
                return fetch_seq["bids"]
            return fetch_seq["dtl"]

    class _Con2(_Con):
        def cursor(self):
            return _Cur2()

    monkeypatch.setattr(bidding, "_connect_db", lambda: _Con2())
    monkeypatch.setattr(bidding, "_clear_header_supplier_local", lambda *_a, **_k: None)
    monkeypatch.setattr(bidding, "_sync_line_awards_sql_api_background", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "utils.procurement_pr_split._recalc_header_amounts",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(bidding, "_get_table_columns", lambda *_a, **_k: {"DOCKEY", "UDF_STATUS"})

    result = bidding.save_line_awards(
        159,
        [{"detailId": 101, "bidId": 10}, {"detailId": 102, "bidId": 20}],
        "admin@test",
    )
    assert calls["split"] == 0
    assert "split" not in result
    assert result["supplierCount"] == 2
    assert result["lineSupplierUpdates"] == 2
    assert result["udfStatus"] == "APPROVED"
    assert result.get("sqlSyncQueued") is True
