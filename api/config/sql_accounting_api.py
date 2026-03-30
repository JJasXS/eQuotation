"""Environment-driven settings for the SQL Accounting HTTP API (SigV4)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class SqlAccountingApiSettings:
    """Settings for SigV4-signed calls to SQL Accounting API Gateway."""

    access_key: str
    secret_key: str
    host: str
    region: str
    service: str
    customer_create_path: str
    use_tls: bool
    timeout_seconds: float
    max_retries: int
    dry_run: bool
    debug_payload: bool

    def resolved_create_url(self) -> str:
        """Full URL for customer create POST. Path should start with ``/``."""
        scheme = "https" if self.use_tls else "http"
        host = self.host.strip().rstrip("/")
        path = self.customer_create_path.strip()
        if not path.startswith("/"):
            path = "/" + path
        # Path is used as-is; query strings are not expected for this endpoint.
        return f"{scheme}://{host}{quote(path, safe='/:?&=%')}"


def load_sql_accounting_api_settings() -> SqlAccountingApiSettings:
    """
    Load settings from the environment.

    Required for live calls (``SQL_API_DRY_RUN`` false): ``SQL_API_ACCESS_KEY``,
    ``SQL_API_SECRET_KEY``, and ``SQL_API_CUSTOMER_CREATE_PATH`` (see validation in service).
    """
    access_key = (os.getenv("SQL_API_ACCESS_KEY") or "").strip()
    secret_key = (os.getenv("SQL_API_SECRET_KEY") or "").strip()
    host = (os.getenv("SQL_API_HOST") or "api.sql.my").strip()
    region = (os.getenv("SQL_API_REGION") or "ap-southeast-1").strip()
    service = (os.getenv("SQL_API_SERVICE") or "execute-api").strip()
    path = (os.getenv("SQL_API_CUSTOMER_CREATE_PATH") or "").strip()
    use_tls = _truthy("SQL_API_USE_TLS", True)
    timeout_seconds = _float("SQL_API_TIMEOUT_SECONDS", 30.0)
    max_retries = max(0, _int("SQL_API_MAX_RETRIES", 3))
    dry_run = _truthy("SQL_API_DRY_RUN", False)
    debug_payload = _truthy("SQL_API_DEBUG_PAYLOAD", False)

    return SqlAccountingApiSettings(
        access_key=access_key,
        secret_key=secret_key,
        host=host,
        region=region,
        service=service,
        customer_create_path=path,
        use_tls=use_tls,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        dry_run=dry_run,
        debug_payload=debug_payload,
    )


def redact_settings_for_log(settings: SqlAccountingApiSettings) -> dict[str, Any]:
    """Safe dict for logs (no secret material)."""
    return {
        "host": settings.host,
        "region": settings.region,
        "service": settings.service,
        "customer_create_path": settings.customer_create_path or "(empty)",
        "use_tls": settings.use_tls,
        "timeout_seconds": settings.timeout_seconds,
        "max_retries": settings.max_retries,
        "dry_run": settings.dry_run,
        "debug_payload": settings.debug_payload,
        "has_access_key": bool(settings.access_key),
        "has_secret_key": bool(settings.secret_key),
    }
