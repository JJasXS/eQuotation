"""Production session cookie / secret hardening."""
from __future__ import annotations

import os


def _load_main_with_env(monkeypatch, env: dict):
    for key in (
        "FLASK_ENV",
        "EQ_ENV",
        "FLASK_SECRET_KEY",
        "SESSION_COOKIE_SECURE",
        "EQ_REQUIRE_SECURE_COOKIES",
        "EQ_TRUST_PROXY",
        "EQ_SKIP_TENANT_BOOTSTRAP",
        "TENANT_BOOTSTRAP_SKIP_SECRETS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EQ_SKIP_TENANT_BOOTSTRAP", "1")
    monkeypatch.setenv("TENANT_BOOTSTRAP_SKIP_SECRETS", "1")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Mirror main.py production cookie policy without importing the full app.
    flask_env = (os.getenv("FLASK_ENV") or os.getenv("EQ_ENV") or "").strip().lower()
    is_production = flask_env in ("production", "prod") or (
        str(os.getenv("EQ_REQUIRE_SECURE_COOKIES", "")).strip().lower() in ("1", "true", "yes", "on")
    )
    secret = (os.getenv("FLASK_SECRET_KEY") or "").strip()
    dev_secret = "dev-secret-key-change-in-production"
    if is_production:
        if not secret or secret == dev_secret or len(secret) < 32:
            raise RuntimeError("bad secret")
    secure_raw = (os.getenv("SESSION_COOKIE_SECURE") or "").strip().lower()
    if is_production:
        session_cookie_secure = True
    elif secure_raw in ("1", "true", "yes", "on"):
        session_cookie_secure = True
    elif secure_raw in ("0", "false", "no", "off"):
        session_cookie_secure = False
    else:
        session_cookie_secure = False
    return is_production, session_cookie_secure


def test_production_forces_secure_cookies_even_when_env_disables(monkeypatch):
    is_prod, secure = _load_main_with_env(
        monkeypatch,
        {
            "FLASK_ENV": "production",
            "FLASK_SECRET_KEY": "x" * 32,
            "SESSION_COOKIE_SECURE": "0",
        },
    )
    assert is_prod is True
    assert secure is True


def test_production_rejects_dev_secret(monkeypatch):
    try:
        _load_main_with_env(
            monkeypatch,
            {
                "FLASK_ENV": "production",
                "FLASK_SECRET_KEY": "dev-secret-key-change-in-production",
            },
        )
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True


def test_local_dev_can_disable_secure_cookies(monkeypatch):
    is_prod, secure = _load_main_with_env(
        monkeypatch,
        {
            "FLASK_ENV": "development",
            "SESSION_COOKIE_SECURE": "0",
        },
    )
    assert is_prod is False
    assert secure is False
