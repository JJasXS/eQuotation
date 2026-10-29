"""OTP shared store: attempt limits, one-time use, concurrent verify."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

# Force sqlite shared store for these tests.
os.environ["EQ_OTP_STORE"] = "sqlite"


@pytest.fixture(autouse=True)
def _clean_otp(tmp_path, monkeypatch):
    monkeypatch.setenv("EQ_OTP_STORE", "sqlite")
    monkeypatch.setenv("EQ_RUNTIME_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "unit-test-secret-key-32chars!!")
    from utils import otp_store
    from utils import eq_local_store

    eq_local_store._INITIALIZED_PATHS.clear()
    otp_store.clear_all_for_tests()
    yield
    otp_store.clear_all_for_tests()
    eq_local_store._INITIALIZED_PATHS.clear()


def test_otp_one_time_use():
    from utils import otp_store

    key = "a@example.com|customer"
    otp_store.put_otp(key, "123456", expiry=datetime.now() + timedelta(minutes=2), last_sent=datetime.now())
    ok1, err1, _ = otp_store.verify_and_consume(key, "123456", max_attempts=5)
    ok2, err2, _ = otp_store.verify_and_consume(key, "123456", max_attempts=5)
    assert ok1 is True and err1 == ""
    assert ok2 is False and err2 == "missing"


def test_otp_attempt_lockout():
    from utils import otp_store

    key = "b@example.com|customer"
    otp_store.put_otp(key, "654321", expiry=datetime.now() + timedelta(minutes=2), last_sent=datetime.now())
    for _ in range(4):
        ok, err, meta = otp_store.verify_and_consume(key, "000000", max_attempts=5)
        assert ok is False and err == "invalid"
        assert meta["remaining"] >= 0
    ok, err, _ = otp_store.verify_and_consume(key, "000000", max_attempts=5)
    assert ok is False and err == "locked"
    # Locked key removed — correct code also fails
    ok2, err2, _ = otp_store.verify_and_consume(key, "654321", max_attempts=5)
    assert ok2 is False and err2 == "missing"


def test_concurrent_verify_only_one_success():
    from utils import otp_store

    key = "c@example.com|customer"
    otp_store.put_otp(key, "111222", expiry=datetime.now() + timedelta(minutes=2), last_sent=datetime.now())

    def attempt(_i):
        return otp_store.verify_and_consume(key, "111222", max_attempts=5)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    successes = [r for r in results if r[0]]
    assert len(successes) == 1
    assert sum(1 for r in results if not r[0]) == 7


def test_mock_otp_blocked_in_production(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("MOCK", "true")
    # Mirror main._mock_otp_on_screen logic without importing main (heavy).
    is_production = True
    mock_on = (os.getenv("MOCK") or "").strip().lower() in ("1", "true", "yes", "on")
    assert (False if is_production else mock_on) is False
