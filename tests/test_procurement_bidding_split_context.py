"""Split child PRs must resolve RFQ parent only from explicit split metadata."""
from utils.procurement_bidding import (
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


def _patch_resolve(monkeypatch, *, header_row, detail_rows, parent_map, columns=None):
    cols = columns or {
        "PH_PQ",
        "PH_PQDTL",
        "DOCKEY",
        "DOCNO",
        "DOCREF1",
        "CODE",
        "DESCRIPTION",
        "DTLKEY",
    }

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
            # Header load in resolve_bidding_context; parent lookup is monkeypatched.
            if "FROM PH_PQ" in getattr(self, "_sql", ""):
                return header_row
            return None

        def fetchall(self):
            if "PH_PQDTL" in getattr(self, "_sql", ""):
                return detail_rows
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
        lambda _c, table: cols,
    )
    monkeypatch.setattr(
        "utils.procurement_bidding._pick_existing",
        lambda c, *names: next((n for n in names if n in c), ""),
    )
    monkeypatch.setattr(
        "utils.procurement_bidding._ph_pq_dockey_by_docno",
        lambda _c, docno: int(parent_map.get(docno, 0) or 0),
    )


def test_resolve_bidding_context_uses_docref1(monkeypatch):
    _patch_resolve(
        monkeypatch,
        header_row=(59, "PR-26060035", "PR-26060034", "400-J0001", "Purchase Request"),
        detail_rows=[(201,)],
        parent_map={"PR-26060034": 58},
    )
    ctx = resolve_bidding_context(59)
    assert ctx["isSplitChild"] is True
    assert ctx["splitFromDocno"] == "PR-26060034"
    assert ctx["biddingSourceDockey"] == 58
    assert ctx["splitFromDockey"] == 58


def test_resolve_bidding_context_uses_legacy_description_when_docref_empty(monkeypatch):
    _patch_resolve(
        monkeypatch,
        header_row=(
            59,
            "PR-26060035",
            "",
            "400-J0001",
            "Split from PR-26060034 — supplier 400-J0001",
        ),
        detail_rows=[(201,)],
        parent_map={"PR-26060034": 58},
    )
    ctx = resolve_bidding_context(59)
    assert ctx["isSplitChild"] is True
    assert ctx["splitFromDocno"] == "PR-26060034"
    assert ctx["biddingSourceDockey"] == 58


def test_resolve_bidding_context_ignores_reused_dtlkey_without_split_metadata(monkeypatch):
    """ANOZ case: PR-26110004 DTLKEY=4 overlaps orphan RFQ bid SOURCE_DTLKEY."""
    _patch_resolve(
        monkeypatch,
        header_row=(80, "PR-26110004", None, "", "Purchase Request"),
        detail_rows=[(4,)],
        parent_map={},
    )
    ctx = resolve_bidding_context(80)
    assert ctx["isSplitChild"] is False
    assert ctx["splitFromDocno"] == ""
    assert ctx["splitFromDockey"] == 0
    assert ctx["biddingSourceDockey"] == 80
    assert ctx["prDetailIds"] == [4]


def test_resolve_bidding_context_ignores_orphan_parent_docref(monkeypatch):
    """DOCREF1 set but parent PH_PQ row deleted → do not invent a bidding source."""
    _patch_resolve(
        monkeypatch,
        header_row=(80, "PR-26110004", "PR-26050002", "", "Purchase Request"),
        detail_rows=[(4,)],
        parent_map={},  # parent missing
    )
    ctx = resolve_bidding_context(80)
    assert ctx["isSplitChild"] is False
    assert ctx["biddingSourceDockey"] == 80
    assert ctx["splitFromDockey"] == 0


def test_resolve_bidding_context_no_metadata_stays_self(monkeypatch):
    _patch_resolve(
        monkeypatch,
        header_row=(12, "PR-26110001", "", "", "Purchase Request"),
        detail_rows=[(1,), (2,)],
        parent_map={"PR-OLD": 99},
    )
    ctx = resolve_bidding_context(12)
    assert ctx["isSplitChild"] is False
    assert ctx["biddingSourceDockey"] == 12
