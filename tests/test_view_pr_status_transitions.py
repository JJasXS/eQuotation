"""View e-PR status transitions for Pending cancel and Draft panel moves."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routes.purchase_requests import update_purchase_request_header_status
from utils.procurement_purchase_request import (
    _encode_status,
    document_status_for_view_pr_udf,
    hidden_cancelled_draft_list_predicate,
    is_hidden_cancelled_draft,
)

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "js" / "procurement" / "precurement_app.js"


def _panels(doc_status: str, udf_status: str) -> set[str]:
    """Mirror View e-PR panel filters in precurement_app.js."""
    doc = str(doc_status or "").strip().upper()
    udf = str(udf_status or "").strip().upper()
    if is_hidden_cancelled_draft(doc, udf):
        return set()
    hits = set()
    if doc == "DRAFT":
        hits.add("DRAFT")
    if udf == "AWAITING" and doc == "SUBMITTED":
        hits.add("AWAITING")
    if udf == "PENDING" and doc == "SUBMITTED":
        hits.add("PENDING")
    if udf == "APPROVED":
        hits.add("APPROVED")
    if udf == "CANCELLED":
        hits.add("CANCELLED")
    return hits


def _apply(doc_status: str, udf_status: str, next_udf: str) -> tuple[str, str]:
    next_doc = document_status_for_view_pr_udf(doc_status, next_udf)
    return (next_doc or doc_status), next_udf


def test_document_status_pairs_match_existing_codes():
    assert document_status_for_view_pr_udf(0, "AWAITING") == "SUBMITTED"
    assert document_status_for_view_pr_udf("DRAFT", "CANCELLED") == "CANCELLED"
    assert document_status_for_view_pr_udf("SUBMITTED", "CANCELLED") is None
    assert document_status_for_view_pr_udf("SUBMITTED", "APPROVED") is None
    assert document_status_for_view_pr_udf("DRAFT", "APPROVED") is None
    assert _encode_status("SUBMITTED", True) == 1
    assert _encode_status("CANCELLED", True) == 4
    assert _encode_status("SUBMITTED", False) == "SUBMITTED"


def test_required_transitions_land_in_one_panel():
    pending_cancel = _apply("SUBMITTED", "PENDING", "CANCELLED")
    assert pending_cancel == ("SUBMITTED", "CANCELLED")
    assert _panels(*pending_cancel) == {"CANCELLED"}

    draft_awaiting = _apply("DRAFT", "", "AWAITING")
    assert draft_awaiting == ("SUBMITTED", "AWAITING")
    assert _panels(*draft_awaiting) == {"AWAITING"}

    draft_cancel = _apply("DRAFT", "", "CANCELLED")
    assert draft_cancel == ("CANCELLED", "CANCELLED")
    assert _panels(*draft_cancel) == set()
    assert is_hidden_cancelled_draft(*draft_cancel) is True


def test_cancelled_draft_stays_in_database_and_out_of_list():
    sql, params = hidden_cancelled_draft_list_predicate(
        "STATUS",
        "UDF_STATUS",
        status_is_numeric=True,
    )
    assert sql == (
        "NOT (COALESCE(H.STATUS, -1) IN (?, ?) AND UPPER(TRIM(COALESCE(H.UDF_STATUS, ''))) = ?)"
    )
    assert params == [0, 4, "CANCELLED"]
    assert is_hidden_cancelled_draft("SUBMITTED", "CANCELLED") is False
    assert is_hidden_cancelled_draft("CANCELLED", "PENDING") is False
    assert is_hidden_cancelled_draft("DRAFT", "CANCELLED") is True
    assert is_hidden_cancelled_draft(0, "CANCELLED") is True
    assert _panels("DRAFT", "CANCELLED") == set()
    assert _panels("SUBMITTED", "APPROVED") == {"APPROVED"}


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.statements = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchone(self):
        return self.row

    def close(self):
        return None


class _Conn:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        return None

    def close(self):
        return None


def _run_header_status(monkeypatch, row, udf_status: str, *, numeric: bool = True):
    from api.routes import purchase_requests as pr

    cursor = _Cursor(row)
    conn = _Conn(cursor)
    monkeypatch.setattr(pr, "_connect_db", lambda: conn)
    monkeypatch.setattr(
        pr,
        "_get_table_columns",
        lambda cur, table: {"DOCKEY", "UDF_STATUS", "STATUS"},
    )
    monkeypatch.setattr(pr, "_column_is_numeric", lambda cur, table, column: numeric)
    result = update_purchase_request_header_status(
        {"changes": [{"requestId": 501, "udfStatus": udf_status}]}
    )
    updates = [item for item in cursor.statements if "UPDATE PH_PQ" in item[0]]
    assert len(updates) == 1
    assert conn.committed is True
    return result, updates[0]


def test_pending_cancel_persists_udf_only(monkeypatch):
    result, (sql, params) = _run_header_status(monkeypatch, ("PENDING", 1), "CANCELLED")
    assert sql == "UPDATE PH_PQ SET UDF_STATUS = ? WHERE DOCKEY = ?"
    assert params == ("CANCELLED", 501)
    assert result["changes"] == [{
        "requestId": 501,
        "previousUdfStatus": "PENDING",
        "udfStatus": "CANCELLED",
    }]


def test_pending_approve_still_persists_udf_only(monkeypatch):
    result, (sql, params) = _run_header_status(monkeypatch, ("PENDING", 1), "APPROVED")
    assert sql == "UPDATE PH_PQ SET UDF_STATUS = ? WHERE DOCKEY = ?"
    assert params == ("APPROVED", 501)
    assert result["changes"][0]["udfStatus"] == "APPROVED"
    assert "docStatus" not in result["changes"][0]


def test_draft_awaiting_persists_submitted_document_status(monkeypatch):
    result, (sql, params) = _run_header_status(monkeypatch, ("", 0), "AWAITING")
    assert "UDF_STATUS = ?" in sql
    assert "STATUS = ?" in sql
    assert params == ("AWAITING", 1, 501)
    assert result["changes"][0]["docStatus"] == "SUBMITTED"
    assert result["changes"][0]["udfStatus"] == "AWAITING"


def test_draft_cancel_persists_cancelled_document_status(monkeypatch):
    result, (sql, params) = _run_header_status(monkeypatch, (None, "DRAFT"), "CANCELLED", numeric=False)
    assert params == ("CANCELLED", "CANCELLED", 501)
    assert result["changes"][0]["docStatus"] == "CANCELLED"
    assert result["changes"][0]["previousUdfStatus"] == ""


def test_draft_cannot_jump_straight_to_approved(monkeypatch):
    from api.routes import purchase_requests as pr

    cursor = _Cursor(("", 0))
    conn = _Conn(cursor)
    monkeypatch.setattr(pr, "_connect_db", lambda: conn)
    monkeypatch.setattr(
        pr,
        "_get_table_columns",
        lambda cur, table: {"DOCKEY", "UDF_STATUS", "STATUS"},
    )
    monkeypatch.setattr(pr, "_column_is_numeric", lambda cur, table, column: True)
    with pytest.raises(HTTPException) as exc:
        update_purchase_request_header_status(
            {"changes": [{"requestId": 501, "udfStatus": "APPROVED"}]}
        )
    assert exc.value.status_code == 400
    assert not any("UPDATE PH_PQ" in sql for sql, _params in cursor.statements)


def test_frontend_guards_pending_cancel_and_draft_label():
    text = APP_JS.read_text(encoding="utf-8")
    assert text.count("viewPrExplicitUdfIsCancelled(") >= 4
    assert "viewPrUdfOption('AWAITING', 'Awaiting Approval', current)" in text
    assert "targetUdfStatus: 'AWAITING'" in text
    assert "targetUdfStatus: 'CANCELLED'" in text
    assert "function isHiddenCancelledDraft" in text
    assert "goToViewPrStatus('DRAFT', { reload: true })" in text
