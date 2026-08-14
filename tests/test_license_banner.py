"""License countdown banner helpers from AWS tenant config."""
from datetime import date

from utils.tenant_bootstrap import (
    _RUNTIME,
    _RUNTIME_LOCK,
    license_banner_context,
    license_days_remaining,
)


def _set_expiry(expiry: str) -> None:
    with _RUNTIME_LOCK:
        _RUNTIME["license_expiry"] = expiry
        _RUNTIME["license_status"] = "ACTIVE"


def test_license_banner_10_days_left():
    _set_expiry("2026-08-24")
    today = date(2026, 8, 14)
    assert license_days_remaining(today=today) == 10
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_show"] is True
    assert ctx["license_banner_text"] == "10 days left"


def test_license_banner_1_day_left():
    _set_expiry("2026-08-15")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_text"] == "1 day left"


def test_license_banner_hidden_when_far():
    _set_expiry("2027-04-30")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_show"] is False


def test_license_banner_expired():
    _set_expiry("2026-08-01")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_text"] == "License expired"
