"""Split child PRs must resolve RFQ parent for bid loading after header normalization."""
from utils.procurement_bidding import (
    _infer_split_parent_from_bid_lines,
    _parse_split_from_docno,
    resolve_bidding_context,
)


def test_parse_split_from_docno_accepts_docref1_plain_pr():
    assert _parse_split_from_docno("PR-26060034") == "PR-26060034"
    assert _parse_split_from_docno("SPLIT_FROM:PR-26060034") == "PR-26060034"


def test_parse_split_from_docno_still_reads_legacy_description():
    assert _parse_split_from_docno("Split from PR-26060034 — supplier 400-J0001") == "PR-26060034"


def test_parse_split_from_docno_ignores_purchase_request_header():
    assert _parse_split_from_docno("Purchase Request") == ""


def test_infer_split_parent_from_bid_line_overlap(monkeypatch):
    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchone(self):
            return (58, "PR-26060034")

    monkeypatch.setattr("utils.procurement_bidding._table_exists", lambda _c, _t: True)
    parent_key, parent_docno = _infer_split_parent_from_bid_lines(_Cur(), 59, [101, 102])
    assert parent_key == 58
    assert parent_docno == "PR-26060034"


def test_resolve_bidding_context_uses_docref1(monkeypatch):
    class _Cur:
        description = [
            ("DOCKEY",),
            ("DOCNO",),
            ("DOCREF1",),
            ("CODE",),
            ("DESCRIPTION",),
        ]

        def execute(self, sql, params=None):
            self._sql = sql
            self._params = params

        def fetchone(self):
            if "FROM PH_PQ" in getattr(self, "_sql", ""):
                return (59, "PR-26060035", "PR-26060034", "400-J0001", "Purchase Request")
            return None

        def fetchall(self):
            if "PH_PQDTL" in getattr(self, "_sql", ""):
                return [(201,)]
            return []

    class _Con:
        def cursor(self):
            return _Cur()

        def close(self):
            return None

    monkeypatch.setattr("utils.procurement_bidding._connect_db", lambda: _Con())
    monkeypatch.setattr("utils.procurement_bidding._table_exists", lambda _c, _t: True)
    monkeypatch.setattr(
        "utils.procurement_bidding._get_table_columns",
        lambda _c, table: {"PH_PQ", "PH_PQDTL", "DOCKEY", "DOCNO", "DOCREF1", "CODE", "DESCRIPTION", "DTLKEY"},
    )
    monkeypatch.setattr("utils.procurement_bidding._pick_existing", lambda cols, *names: next((n for n in names if n in cols), ""))
    monkeypatch.setattr("utils.procurement_bidding._ph_pq_dockey_by_docno", lambda _c, docno: 58 if docno == "PR-26060034" else 0)

    ctx = resolve_bidding_context(59)
    assert ctx["isSplitChild"] is True
    assert ctx["splitFromDocno"] == "PR-26060034"
    assert ctx["biddingSourceDockey"] == 58
