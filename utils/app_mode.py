"""
App phase: developer testing vs live production.

  APP=dev  — developer testing (on-page OTP, no email; live SY_USER role refresh)
  APP=prod — live phase (email OTP; roles frozen at login)

Default when unset / unknown: prod.
"""
from __future__ import annotations

import os

APP_MODE_DEV = 'dev'
APP_MODE_PROD = 'prod'


def app_mode() -> str:
    """Return ``dev`` or ``prod`` from env ``APP`` (case-insensitive)."""
    raw = (os.getenv('APP') or '').strip().lower()
    if raw in (APP_MODE_DEV, 'development', 'develop'):
        return APP_MODE_DEV
    return APP_MODE_PROD


def is_dev_app() -> bool:
    """True only during the developer-testing phase (APP=dev)."""
    return app_mode() == APP_MODE_DEV


def is_prod_app() -> bool:
    """True for live / production phase (default)."""
    return app_mode() == APP_MODE_PROD
