"""Write-path provider for SQL Accounting customer creates (REST vs COM SDK)."""
from __future__ import annotations

import os
from dataclasses import dataclass


PROVIDER_REST = "Rest"
PROVIDER_SDK = "Sdk"


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def normalize_write_provider(raw: str | None) -> str:
    """Return Rest or Sdk. Anything other than Sdk (case-insensitive) is Rest."""
    value = (raw or "").strip()
    if value.lower() == PROVIDER_SDK.lower():
        return PROVIDER_SDK
    return PROVIDER_REST


@dataclass(frozen=True)
class SqlAccountingWriteSettings:
    """Selecting adapter settings. Default Provider=Rest preserves current behavior."""

    provider: str
    block_rest_http: bool

    @property
    def is_sdk(self) -> bool:
        return self.provider == PROVIDER_SDK

    @property
    def is_rest(self) -> bool:
        return not self.is_sdk


def load_sql_accounting_write_settings() -> SqlAccountingWriteSettings:
    """
    Load write provider from environment.

    ``SQL_ACCOUNTING_WRITE_PROVIDER`` — ``Rest`` (default) or ``Sdk``.
    ``SQL_ACCOUNTING_BLOCK_REST_HTTP`` — when true, refuse REST writes (lab lock).
    """
    provider = normalize_write_provider(os.getenv("SQL_ACCOUNTING_WRITE_PROVIDER"))
    block_rest = _truthy("SQL_ACCOUNTING_BLOCK_REST_HTTP", False)
    return SqlAccountingWriteSettings(provider=provider, block_rest_http=block_rest)
