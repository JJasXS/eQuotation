"""Fully transferred PRs are hidden from Admin/Staff active APPROVED lists."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from utils.procurement_pr_transfer_completion import (
    is_purchase_request_fully_transferred,
    remaining_transfer_qty_by_detail,
    sql_exclude_fully_transferred_pr,
    sql_pr_fully_transferred_predicate,
)


def test_remaining_transfer_qty_partial_and_full():
    remaining = remaining_transfer_qty_by_detail(
        {1: 10, 2: 5},
        {1: 10, 2: 2},
    )
    assert remaining[1] == Decimal("0")
    assert remaining[2] == Decimal("3")


def test_fully_transferred_requires_transfer_and_zero_remaining():
    assert (
        is_purchase_request_fully_transferred(
            detail_qty_by_id={1: 4, 2: 6},
            transferred_qty_by_id={1: 4, 2: 6},
        )
        is True
    )
    # Partial
    assert (
        is_purchase_request_fully_transferred(
            detail_qty_by_id={1: 4, 2: 6},
            transferred_qty_by_id={1: 4, 2: 2},
        )
        is False
    )
    # Never transferred / failed (no ST_XTRANS qty)
    assert (
        is_purchase_request_fully_transferred(
            detail_qty_by_id={1: 4},
            transferred_qty_by_id={},
        )
        is False
    )
    # Over-transfer still counts as complete for that line
    assert (
        is_purchase_request_fully_transferred(
            detail_qty_by_id={1: 4},
            transferred_qty_by_id={1: 5},
        )
        is True
    )


def test_fully_transferred_respects_transferable_subset():
    assert (
        is_purchase_request_fully_transferred(
            detail_qty_by_id={1: 4, 2: 10},
            transferred_qty_by_id={1: 4},
            transferable_detail_ids={1},
        )
        is True
    )
    assert (
        is_purchase_request_fully_transferred(
            detail_qty_by_id={1: 4, 2: 10},
            transferred_qty_by_id={1: 4},
            transferable_detail_ids={1, 2},
        )
        is False
    )


def test_sql_predicate_includes_st_xtrans_and_remaining(monkeypatch):
    detail_cols = {
        "DTLKEY",
        "DOCKEY",
        "QTY",
        "TRANSFERABLE",
        "UDF_PQAPPROVED",
    }
    xtrans_cols = {"FROMDOCTYPE", "FROMDOCKEY", "FROMDTLKEY", "QTY", "SQTY", "SUOMQTY"}
    header_cols = {"DOCKEY", "TRANSFERABLE", "UDF_STATUS"}

    def _cols(_cur, name):
        if name == "PH_PQDTL":
            return detail_cols
        if name == "ST_XTRANS":
            return xtrans_cols
        if name == "PH_PQ":
            return header_cols
        return set()

    monkeypatch.setattr(
        "utils.procurement_pr_transfer_completion._get_table_columns",
        _cols,
    )
    cur = MagicMock()
    expr = sql_pr_fully_transferred_predicate(cur, header_alias="H", header_key_col="DOCKEY")
    assert "ST_XTRANS" in expr
    assert "PH_PQDTL" in expr
    assert "TRANSFERRED_QTY" in expr
    assert "NOT EXISTS" in expr or "NOT EXISTS" in expr.replace("NOT (", "NOT ")
    assert "FROMDOCTYPE" in expr
    exclude = sql_exclude_fully_transferred_pr(cur, header_alias="H", header_key_col="DOCKEY")
    assert exclude.startswith("NOT ")
    assert "ST_XTRANS" in exclude


def test_list_view_approved_applies_exclude(monkeypatch):
    from utils import procurement_purchase_request as pr

    captured: dict[str, str] = {}

    class _Cur:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            if "COUNT(*)" in sql:
                self._rows = [(0,)]
            else:
                self._rows = []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return []

    class _Con:
        def cursor(self):
            return _Cur()

        def close(self):
            return None

    monkeypatch.setattr(pr, "_connect_db", lambda: _Con())
    monkeypatch.setattr(
        pr,
        "_get_table_columns",
        lambda _cur, name: {
            "PH_PQ": {
                "DOCKEY",
                "DOCNO",
                "DOCDATE",
                "STATUS",
                "UDF_STATUS",
                "TRANSFERABLE",
                "CODE",
                "COMPANYNAME",
                "PROJECT",
                "CURRENCYCODE",
                "DESCRIPTION",
                "DOCAMT",
            },
            "PH_PQDTL": {"DTLKEY", "DOCKEY", "QTY", "TRANSFERABLE"},
        }.get(name, set()),
    )
    monkeypatch.setattr(pr, "_column_is_numeric", lambda *_a, **_k: True)
    monkeypatch.setattr(pr, "_ph_pqdtl_header_fk_col", lambda _cur: "DOCKEY")
    monkeypatch.setattr(
        "utils.procurement_pr_transfer_completion._get_table_columns",
        lambda _cur, name: {
            "PH_PQDTL": {"DTLKEY", "DOCKEY", "QTY", "TRANSFERABLE", "UDF_PQAPPROVED"},
            "ST_XTRANS": {"FROMDOCTYPE", "FROMDOCKEY", "FROMDTLKEY", "QTY", "SQTY"},
            "PH_PQ": {"DOCKEY", "TRANSFERABLE"},
        }.get(name, set()),
    )

    records, page = pr.list_view_pr_headers_for_status("APPROVED", offset=0, limit=20)
    assert records == []
    assert page["viewStatus"] == "APPROVED"
    assert "ST_XTRANS" in captured["sql"]
    assert "NOT" in captured["sql"]

    captured.clear()
    pr.list_view_pr_headers_for_status("PENDING", offset=0, limit=20)
    assert "ST_XTRANS" not in (captured.get("sql") or "")


def test_map_counts_approved_excludes_full(monkeypatch):
    from utils import procurement_purchase_request as pr

    sql_by_tab: dict[str, str] = {}

    class _Cur:
        def __init__(self):
            self._last_sql = ""

        def execute(self, sql, params=None):
            self._last_sql = sql
            tab = "APPROVED" if "APPROVED" in str(params or ()) else "OTHER"
            if "UDF_STATUS" in sql and params:
                # tab value is last string-ish param typically
                for p in params or ():
                    if str(p).upper() in {"DRAFT", "AWAITING", "PENDING", "APPROVED", "CANCELLED"}:
                        tab = str(p).upper()
            sql_by_tab[tab] = sql

        def fetchone(self):
            return (0,)

        def fetchall(self):
            return []

    class _Con:
        def cursor(self):
            return _Cur()

        def close(self):
            return None

    monkeypatch.setattr(pr, "_connect_db", lambda: _Con())
    monkeypatch.setattr(
        pr,
        "_get_table_columns",
        lambda _cur, name: {
            "PH_PQ": {"DOCKEY", "STATUS", "UDF_STATUS"},
            "PH_PQDTL": {"DTLKEY", "DOCKEY", "QTY"},
        }.get(name, set()),
    )
    monkeypatch.setattr(pr, "_column_is_numeric", lambda *_a, **_k: True)
    monkeypatch.setattr(pr, "_ph_pqdtl_header_fk_col", lambda _cur: "DOCKEY")
    monkeypatch.setattr(
        "utils.procurement_pr_transfer_completion._get_table_columns",
        lambda _cur, name: {
            "PH_PQDTL": {"DTLKEY", "DOCKEY", "QTY", "TRANSFERABLE"},
            "ST_XTRANS": {"FROMDOCTYPE", "FROMDOCKEY", "FROMDTLKEY", "QTY", "SQTY"},
            "PH_PQ": {"DOCKEY", "TRANSFERABLE"},
        }.get(name, set()),
    )

    counts = pr.map_view_pr_status_counts()
    assert set(counts) >= {"APPROVED", "PENDING", "CANCELLED"}
    assert "ST_XTRANS" in (sql_by_tab.get("APPROVED") or "")
    assert "ST_XTRANS" not in (sql_by_tab.get("PENDING") or "")
    assert "ST_XTRANS" not in (sql_by_tab.get("CANCELLED") or "")
