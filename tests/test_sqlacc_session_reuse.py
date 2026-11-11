"""SDK session reuse, idle timeout, concurrency, and recovery."""
from __future__ import annotations

import threading
import time

import pytest

from api.adapters.sqlacc_session import SqlAccSessionError, SqlAccSessionManager
from api.config.sql_acc_sdk import SqlAccSdkSettings


class _FakeApp:
    def __init__(self) -> None:
        self.is_login = False
        self.logins = 0
        self.logouts = 0
        self.last_login = None

    @property
    def IsLogin(self):
        return self.is_login

    def Login(self, user, password, dcf, fdb):
        self.last_login = (user, dcf, fdb)
        self.logins += 1
        self.is_login = True

    def Logout(self):
        self.logouts += 1
        self.is_login = False


class _FakeSta:
    def run(self, func, *, timeout_seconds=None):
        return func()

    def close(self):
        return None


def _settings(**overrides) -> SqlAccSdkSettings:
    base = dict(
        prog_id="SQLAcc.BizApp",
        allow_live_com=True,
        dcf_path=r"\\server\Share\SQLACC.DCF",
        database_file="ACC-ANOZ.FDB",
        username="ADMIN",
        password="secret",
        logout_after_use=False,
        customer_control_account="",
        login_timeout_seconds=30.0,
        session_idle_seconds=300.0,
    )
    base.update(overrides)
    return SqlAccSdkSettings(**base)


def _manager(**overrides) -> tuple[SqlAccSessionManager, _FakeApp]:
    app = _FakeApp()
    clock = {"t": 1000.0}

    def _now():
        return clock["t"]

    mgr = SqlAccSessionManager(
        _settings(**overrides),
        sta_queue=_FakeSta(),  # type: ignore[arg-type]
        dispatch_factory=lambda prog: app,
        monotonic_clock=_now,
    )
    return mgr, app, clock


def test_reuses_login_when_logout_after_use_false():
    mgr, app, _clock = _manager(logout_after_use=False)
    assert mgr.run(lambda a: a.IsLogin) is True
    assert mgr.run(lambda a: a.IsLogin) is True
    assert app.logins == 1
    assert app.logouts == 0
    assert mgr.login_count == 1


def test_logout_after_use_logs_out_each_call():
    mgr, app, _clock = _manager(logout_after_use=True)
    mgr.run(lambda a: True)
    mgr.run(lambda a: True)
    assert app.logins == 2
    assert app.logouts == 2


def test_idle_timeout_forces_relogin():
    mgr, app, clock = _manager(logout_after_use=False, session_idle_seconds=60)
    mgr.run(lambda a: True)
    clock["t"] += 61
    mgr.run(lambda a: True)
    assert app.logins == 2
    assert app.logouts >= 1


def test_company_identity_change_forces_relogin():
    mgr, app, _clock = _manager(logout_after_use=False)
    mgr.run(lambda a: True)
    # Swap settings to a different FDB identity.
    mgr._settings = _settings(database_file="ACC-OTHER.FDB", logout_after_use=False)
    mgr.run(lambda a: True)
    assert app.logins == 2
    assert app.last_login is not None
    assert app.last_login[2] == "ACC-OTHER.FDB"


def test_failure_logs_out_and_does_not_auto_retry():
    mgr, app, _clock = _manager(logout_after_use=False)
    calls = {"n": 0}

    def _boom(a):
        calls["n"] += 1
        raise SqlAccSessionError("boom")

    with pytest.raises(SqlAccSessionError, match="boom"):
        mgr.run(_boom)
    assert calls["n"] == 1
    assert app.is_login is False
    assert app.logouts >= 1


def test_concurrency_serialized():
    mgr, app, _clock = _manager(logout_after_use=False)
    active = 0
    max_active = 0
    lock = threading.Lock()

    def _work(a):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return True

    threads = [threading.Thread(target=lambda: mgr.run(_work)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_active == 1
    assert app.logins == 1
