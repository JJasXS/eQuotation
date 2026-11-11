"""Atomic quotation email notification reservation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture(autouse=True)
def _clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EQ_RUNTIME_STORE_DIR", str(tmp_path))
    from utils import eq_local_store
    from utils import quotation_email_notify as qen

    eq_local_store._INITIALIZED_PATHS.clear()
    qen.clear_for_tests()
    yield
    qen.clear_for_tests()
    eq_local_store._INITIALIZED_PATHS.clear()


def test_reserve_then_sent_dedupes():
    from utils import quotation_email_notify as qen

    first = qen.reserve_notification(101)
    assert first["status"] == "reserved"
    qen.mark_sent(101, "a@example.com")
    second = qen.reserve_notification(101)
    assert second["status"] == "already_sent"


def test_failed_allows_retry():
    from utils import quotation_email_notify as qen

    assert qen.reserve_notification(202)["status"] == "reserved"
    qen.mark_failed(202, "smtp down")
    again = qen.reserve_notification(202)
    assert again["status"] == "reserved"
    assert again.get("reclaimed") is True


def test_concurrent_reserve_only_one_wins():
    from utils import quotation_email_notify as qen

    def attempt(_i):
        return qen.reserve_notification(303)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    reserved = [r for r in results if r.get("status") == "reserved" and not r.get("reclaimed")]
    in_progress = [r for r in results if r.get("status") == "in_progress"]
    assert len(reserved) == 1
    assert len(in_progress) == 7
