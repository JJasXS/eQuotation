"""SQL Account COM SDK login / session settings (env-driven, no hardcoded secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _database_file_from_env() -> str:
    """FDB file name for BizApp.Login (file name only). Prefer explicit SDK env, else DB_PATH basename."""
    explicit = (os.getenv("SQLACC_SDK_DATABASE_FILE") or "").strip()
    if explicit:
        return Path(explicit.replace("\\", "/")).name
    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        return ""
    return Path(db_path.replace("\\", "/")).name


@dataclass(frozen=True)
class SqlAccSdkSettings:
    """COM SDK options. Live COM is off unless AllowLiveCom is explicitly enabled."""

    prog_id: str
    allow_live_com: bool
    dcf_path: str
    database_file: str
    username: str
    password: str
    logout_after_use: bool
    customer_control_account: str
    login_timeout_seconds: float
    session_idle_seconds: float

    def login_ready(self) -> bool:
        return bool(
            self.allow_live_com
            and self.prog_id.strip()
            and self.dcf_path.strip()
            and self.database_file.strip()
            and self.username.strip()
            and self.password
        )

    def missing_login_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.allow_live_com:
            missing.append("SQLACC_SDK_ALLOW_LIVE_COM")
        if not self.dcf_path.strip():
            missing.append("SQLACC_SDK_DCF_PATH")
        if not self.database_file.strip():
            missing.append("SQLACC_SDK_DATABASE_FILE (or DB_PATH)")
        if not self.username.strip():
            missing.append("SQLACC_SDK_USER")
        if not self.password:
            missing.append("SQLACC_SDK_PASSWORD")
        return missing

    @property
    def company_identity_key(self) -> str:
        """Stable key for DCF + FDB identity (never share sessions across companies)."""
        return (
            f"{(self.dcf_path or '').strip().upper()}|"
            f"{(self.database_file or '').strip().upper()}"
        )


def load_sql_acc_sdk_settings() -> SqlAccSdkSettings:
    """
    Load COM SDK settings from environment.

    Credentials and company paths come only from env (tenant/local config) — never hardcoded.
    """
    timeout_raw = (os.getenv("SQLACC_SDK_LOGIN_TIMEOUT_SECONDS") or "120").strip()
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = 120.0
    idle_raw = (os.getenv("SQLACC_SDK_SESSION_IDLE_SECONDS") or "300").strip()
    try:
        idle = float(idle_raw)
    except ValueError:
        idle = 300.0
    return SqlAccSdkSettings(
        prog_id=(os.getenv("SQLACC_COM_PROG_ID") or "SQLAcc.BizApp").strip() or "SQLAcc.BizApp",
        allow_live_com=_truthy("SQLACC_SDK_ALLOW_LIVE_COM", False),
        dcf_path=(os.getenv("SQLACC_SDK_DCF_PATH") or "").strip(),
        database_file=_database_file_from_env(),
        username=(os.getenv("SQLACC_SDK_USER") or "").strip(),
        password=os.getenv("SQLACC_SDK_PASSWORD") or "",
        logout_after_use=_truthy("SQLACC_SDK_LOGOUT_AFTER_USE", True),
        customer_control_account=(os.getenv("SQLACC_SDK_CUSTOMER_CONTROL_ACCOUNT") or "").strip(),
        login_timeout_seconds=max(5.0, timeout),
        session_idle_seconds=max(0.0, idle),
    )


def redact_sdk_settings_for_log(settings: SqlAccSdkSettings) -> dict[str, Any]:
    """Safe dict for logs (no password)."""
    return {
        "prog_id": settings.prog_id,
        "allow_live_com": settings.allow_live_com,
        "dcf_path": settings.dcf_path or "(empty)",
        "database_file": settings.database_file or "(empty)",
        "username": settings.username or "(empty)",
        "has_password": bool(settings.password),
        "logout_after_use": settings.logout_after_use,
        "session_idle_seconds": settings.session_idle_seconds,
        "company_identity_key": settings.company_identity_key or "(empty)",
        "has_customer_control_account": bool(settings.customer_control_account),
        "login_timeout_seconds": settings.login_timeout_seconds,
        "login_ready": settings.login_ready(),
    }
