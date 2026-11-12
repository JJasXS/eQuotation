"""Regression: Batch Cancel must not fail on Windows cp1252 console logging."""
from __future__ import annotations

import io
from typing import Any
import main as app_main
from utils.csrf_protect import CSRF_HEADER_NAME
from utils.role_permissions import (
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_SALES_MGMT,
    ACCESS_TIER_SALES_STAFF,
)

_CSRF = "c" * 32


def _client():
    app_main.app.config["TESTING"] = True
    return app_main.app.test_client()


def _login(client, *, access_tier: str, email: str = "staff@example.com"):
    with client.session_transaction() as sess:
        sess["user_type"] = "admin" if access_tier != ACCESS_TIER_SALES_STAFF else "user"
        sess["access_tier"] = access_tier
        sess["user_email"] = email
        sess["_csrf_token"] = _CSRF
        sess["login_mode"] = "admin"


class _Cp1252Stdout(io.TextIOBase):
    """Stdout stand-in that rejects non-cp1252 characters (TEST Windows)."""

    encoding = "cp1252"

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def write(self, s: str) -> int:
        text = str(s)
        text.encode("cp1252")  # raises UnicodeEncodeError for ✓ ✗ → —
        self.chunks.append(text)
        return len(text)

    def flush(self) -> None:
        return None


class _FakeCursor:
    def __init__(self, *, exists: bool = True, cols: set[str] | None = None) -> None:
        self.exists = exists
        self.cols = cols or {"CANCELLED", "UPDATECOUNT", "UDF_STATUS", "DOCKEY"}
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._pending: Any = None
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.executed.append((sql, params))
        sql_u = " ".join(str(sql).upper().split())
        if "FROM SL_QT WHERE DOCKEY" in sql_u and sql_u.strip().startswith("SELECT 1"):
            self._pending = [(1,)] if self.exists else []
        elif "RDB$RELATION_FIELDS" in sql_u:
            self._pending = [(c,) for c in sorted(self.cols)]
        else:
            self._pending = []

    def fetchone(self):
        rows = self._pending or []
        self._pending = None
        return rows[0] if rows else None

    def fetchall(self):
        rows = self._pending or []
        self._pending = None
        return rows

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_safe_console_print_survives_cp1252_stdout(monkeypatch):
    sink = _Cp1252Stdout()
    monkeypatch.setattr(app_main.sys, "stdout", sink)
    # Must not raise even if caller passes glyphs Windows cannot encode.
    # cp1252 includes U+2014 (em dash) but not check/cross/arrow marks.
    app_main._safe_console_print(
        "[BATCH CANCEL] OK DOCKEY 1 CANCELLED \u2713 \u2192 \u2014 \u2717"
    )
    joined = "".join(sink.chunks)
    assert "DOCKEY 1" in joined
    assert "\u2713" not in joined
    assert "\u2717" not in joined
    assert "\u2192" not in joined
    joined.encode("cp1252")


def test_apply_cancel_returns_success_when_post_commit_log_would_break_cp1252(monkeypatch):
    """Historical bug: print('…—…') after commit raised and was reported as failure."""
    cur = _FakeCursor()
    con = _FakeConnection(cur)
    monkeypatch.setattr(app_main, "get_db_connection", lambda: con)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())

    # Force the old-style glyph through the safe logger path (must still succeed).
    original = app_main._safe_console_print

    def _log_with_em_dash(message: str, *, flush: bool = True) -> None:
        original(f"{message} — ✓ ✗ →", flush=flush)

    monkeypatch.setattr(app_main, "_safe_console_print", _log_with_em_dash)

    ok, err = app_main._apply_sl_qt_cancelled_toggle_firebird(42, True)
    assert ok is True
    assert err is None
    assert con.commits == 1
    assert con.rollbacks == 0
    assert con.closed is True
    update_sql = next(sql for sql, _ in cur.executed if str(sql).upper().lstrip().startswith("UPDATE"))
    assert "CANCELLED" in update_sql.upper()


def test_apply_cancel_not_found_does_not_commit(monkeypatch):
    cur = _FakeCursor(exists=False)
    con = _FakeConnection(cur)
    monkeypatch.setattr(app_main, "get_db_connection", lambda: con)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())

    ok, err = app_main._apply_sl_qt_cancelled_toggle_firebird(99, True)
    assert ok is False
    assert "not found" in (err or "").lower()
    assert con.commits == 0


def test_delete_quotations_partial_success_under_cp1252(monkeypatch):
    client = _client()

    outcomes = {
        10: (True, None),
        11: (False, "Quotation DOCKEY 11 not found"),
        12: (True, None),
    }

    def _fake_apply(dockey: int, cancelled: bool):
        assert cancelled is True
        return outcomes[int(dockey)]

    monkeypatch.setattr(app_main, "_apply_sl_qt_cancelled_toggle_firebird", _fake_apply)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN, email="admin@example.com")

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [10, 11, 12]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    assert resp.status_code == 200
    body = resp.get_json() or {}
    assert body.get("success") is True
    assert body.get("cancelled_count") == 2
    assert body.get("failed_count") == 1
    assert body.get("deleted_count") == 2
    details = body.get("failed_details") or []
    assert any("11" in str(d) for d in details)


def test_delete_quotations_committed_cancel_not_marked_failed_if_log_raises(monkeypatch):
    """Even if a buggy logger raises after success, counts must stay correct."""
    client = _client()

    monkeypatch.setattr(
        app_main,
        "_apply_sl_qt_cancelled_toggle_firebird",
        lambda dockey, cancelled: (True, None),
    )

    def _boom(message: str, *, flush: bool = True) -> None:
        if "OK DOCKEY" in str(message):
            raise UnicodeEncodeError("charmap", "✗", 0, 1, "ordinal not in range(256)")
        return None

    monkeypatch.setattr(app_main, "_safe_console_print", _boom)
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN, email="admin@example.com")

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [7]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    assert resp.status_code == 200
    body = resp.get_json() or {}
    assert body.get("success") is True
    assert body.get("cancelled_count") == 1
    assert body.get("failed_count") == 0


def test_apply_cancel_writes_true_and_cancelled_status(monkeypatch):
    cur = _FakeCursor()
    con = _FakeConnection(cur)
    monkeypatch.setattr(app_main, "get_db_connection", lambda: con)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())

    ok, err = app_main._apply_sl_qt_cancelled_toggle_firebird(5, True)
    assert ok is True and err is None
    assert con.commits == 1
    update = next(p for sql, p in cur.executed if str(sql).upper().lstrip().startswith("UPDATE"))
    assert update[0] == "True"
    assert "CANCELLED" in update


def test_apply_restore_writes_false_and_reviewed_status(monkeypatch):
    cur = _FakeCursor()
    con = _FakeConnection(cur)
    monkeypatch.setattr(app_main, "get_db_connection", lambda: con)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())

    ok, err = app_main._apply_sl_qt_cancelled_toggle_firebird(5, False)
    assert ok is True and err is None
    assert con.commits == 1
    update = next(p for sql, p in cur.executed if str(sql).upper().lstrip().startswith("UPDATE"))
    assert update[0] == "False"
    assert "REVIEWED" in update


def test_batch_cancel_all_success_under_cp1252(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        app_main,
        "_apply_sl_qt_cancelled_toggle_firebird",
        lambda dockey, cancelled: (True, None),
    )
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN)

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [1, 2]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    body = resp.get_json() or {}
    assert resp.status_code == 200
    assert body.get("cancelled_count") == 2
    assert body.get("failed_count") == 0


def test_batch_cancel_all_failed_under_cp1252(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        app_main,
        "_apply_sl_qt_cancelled_toggle_firebird",
        lambda dockey, cancelled: (False, f"Quotation DOCKEY {dockey} not found"),
    )
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN)

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [8, 9]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    body = resp.get_json() or {}
    assert resp.status_code == 200
    assert body.get("success") is True
    assert body.get("cancelled_count") == 0
    assert body.get("failed_count") == 2
    assert body.get("failed_details")


def test_permission_full_admin_batch_cancel_allowed(monkeypatch):
    client = _client()
    called = []

    def _fake(dockey, cancelled):
        called.append((dockey, cancelled))
        return True, None

    monkeypatch.setattr(app_main, "_apply_sl_qt_cancelled_toggle_firebird", _fake)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN)

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [1]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    assert resp.status_code == 200
    assert called == [(1, True)]


def test_permission_sales_mgmt_batch_cancel_allowed(monkeypatch):
    client = _client()
    called = []

    def _fake(dockey, cancelled):
        called.append((dockey, cancelled))
        return True, None

    monkeypatch.setattr(app_main, "_apply_sl_qt_cancelled_toggle_firebird", _fake)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_SALES_MGMT, email="salesmgr@example.com")

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [2]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    assert resp.status_code == 200
    assert (resp.get_json() or {}).get("cancelled_count") == 1
    assert called == [(2, True)]


def test_permission_sales_staff_batch_cancel_denied(monkeypatch):
    client = _client()
    called = []

    def _fake(dockey, cancelled):
        called.append((dockey, cancelled))
        return True, None

    monkeypatch.setattr(app_main, "_apply_sl_qt_cancelled_toggle_firebird", _fake)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_SALES_STAFF, email="sstaff@example.com")

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [3]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    assert resp.status_code == 403
    assert called == []


def test_permission_sales_staff_single_cancel_denied(monkeypatch):
    client = _client()
    called = []
    monkeypatch.setattr(
        app_main,
        "_apply_sl_qt_cancelled_toggle_firebird",
        lambda dockey, cancelled: called.append((dockey, cancelled)) or (True, None),
    )
    _login(client, access_tier=ACCESS_TIER_SALES_STAFF, email="sstaff@example.com")

    resp = client.post(
        "/api/admin/cancel_single_quotation",
        json={"dockey": 4},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    assert resp.status_code == 403
    assert called == []


def test_single_cancel_success_under_cp1252(monkeypatch):
    client = _client()
    calls = []

    def _fake(dockey, cancelled):
        calls.append((dockey, cancelled))
        return True, None

    monkeypatch.setattr(app_main, "_apply_sl_qt_cancelled_toggle_firebird", _fake)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_SALES_MGMT)

    resp = client.post(
        "/api/admin/cancel_single_quotation",
        json={"dockey": 15},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    body = resp.get_json() or {}
    assert resp.status_code == 200
    assert body.get("success") is True
    assert calls == [(15, True)]


def test_restore_via_update_quotation_cancelled(monkeypatch):
    client = _client()
    calls = []

    def _fake(dockey, cancelled):
        calls.append((dockey, cancelled))
        return True, None

    monkeypatch.setattr(app_main, "_apply_sl_qt_cancelled_toggle_firebird", _fake)
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    # Skip activation email side effects.
    monkeypatch.setattr(
        app_main,
        "fetch_quotation_details_for_email",
        lambda *_a, **_k: {"success": False},
    )
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN)

    resp = client.post(
        "/api/admin/update_quotation_cancelled",
        json={"dockey": 20, "cancelled": False},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    body = resp.get_json() or {}
    assert resp.status_code == 200
    assert body.get("success") is True
    assert calls == [(20, False)]


def test_batch_review_restore_partial_success(monkeypatch):
    client = _client()
    outcomes = {30: (True, None), 31: (False, "not found")}

    monkeypatch.setattr(
        app_main,
        "_apply_sl_qt_cancelled_toggle_firebird",
        lambda dockey, cancelled: (
            outcomes[int(dockey)] if cancelled is False else (False, "wrong flag")
        ),
    )
    monkeypatch.setattr(app_main.sys, "stdout", _Cp1252Stdout())
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN)

    resp = client.post(
        "/api/admin/batch_review_quotations",
        json={"dockeyList": [30, 31]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    body = resp.get_json() or {}
    assert resp.status_code == 200
    assert body.get("reviewed_count") == 1
    assert body.get("failed_count") == 1


def test_no_unicodeencodeerror_when_batch_logs_old_glyphs(monkeypatch):
    """Original TEST bug: logging \u2717 after success must not break the response."""
    client = _client()
    sink = _Cp1252Stdout()
    monkeypatch.setattr(app_main.sys, "stdout", sink)
    monkeypatch.setattr(
        app_main,
        "_apply_sl_qt_cancelled_toggle_firebird",
        lambda dockey, cancelled: (True, None),
    )

    # Inject historical glyph-bearing messages into the safe logger.
    real = app_main._safe_console_print

    def _legacyish(message: str, *, flush: bool = True) -> None:
        real(f"{message} \u2713 \u2717 \u2192", flush=flush)

    monkeypatch.setattr(app_main, "_safe_console_print", _legacyish)
    _login(client, access_tier=ACCESS_TIER_FULL_ADMIN)

    resp = client.post(
        "/api/admin/delete_quotations",
        json={"dockeyList": [100]},
        headers={CSRF_HEADER_NAME: _CSRF},
    )
    body = resp.get_json() or {}
    assert resp.status_code == 200
    assert body.get("cancelled_count") == 1
    assert body.get("failed_count") == 0
    "".join(sink.chunks).encode("cp1252")
