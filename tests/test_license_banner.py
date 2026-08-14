"""Subscription countdown copy and WhatsApp support link."""
from datetime import date
from urllib.parse import unquote

from utils.tenant_bootstrap import (
    _RUNTIME,
    _RUNTIME_LOCK,
    build_support_whatsapp_url,
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
    assert ctx["license_banner_title"] == "Subscription expires in 10 days"
    assert ctx["license_banner_body"] == (
        "Please renew your subscription to avoid service interruption."
    )


def test_license_banner_7_days_left():
    _set_expiry("2026-08-21")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_title"] == "Your subscription expires in 7 days."
    assert ctx["license_banner_body"] == ""


def test_license_banner_3_days_left():
    _set_expiry("2026-08-17")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_title"] == "Your subscription expires in 3 days."
    assert ctx["license_banner_body"] == (
        "Please renew soon to avoid service interruption."
    )


def test_license_banner_1_day_left():
    _set_expiry("2026-08-15")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_title"] == "Your subscription expires tomorrow."
    assert ctx["license_banner_body"] == (
        "Please renew to maintain uninterrupted access."
    )


def test_license_banner_hidden_when_far():
    _set_expiry("2027-04-30")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_show"] is False


def test_license_banner_expired():
    _set_expiry("2026-08-04")
    today = date(2026, 8, 14)
    assert license_days_remaining(today=today) == -10
    ctx = license_banner_context(today=today)
    assert ctx["license_banner_show"] is True
    assert ctx["license_expired"] is True
    assert ctx["license_banner_title"] == "Subscription Expired"
    assert ctx["license_banner_body"] == "Your subscription has expired."
    assert ctx["license_banner_detail"] == (
        "Please contact ProAcc System to renew your subscription and restore access."
    )


def test_license_banner_expires_today():
    _set_expiry("2026-08-14")
    today = date(2026, 8, 14)
    ctx = license_banner_context(today=today)
    assert ctx["license_expired"] is True
    assert ctx["license_banner_title"] == "Subscription Expired"


def test_whatsapp_url_normalizes_local_my_number():
    url = build_support_whatsapp_url("018-397 7796")
    assert url.startswith("https://wa.me/60183977796?text=")
    assert "renew" in unquote(url).lower()


def test_whatsapp_url_empty_without_number():
    assert build_support_whatsapp_url("") == ""
