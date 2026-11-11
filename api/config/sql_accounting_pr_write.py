"""Write-path provider for Purchase Request (REST vs COM SDK). Separate from quotation/customer."""
from __future__ import annotations

import os
from dataclasses import dataclass

from api.config.sql_accounting_write import (
    PROVIDER_REST,
    PROVIDER_SDK,
    normalize_write_provider,
)


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SqlAccountingPurchaseRequestWriteSettings:
    """Selecting adapter for PR awards sync. Default Rest preserves paid API path."""

    provider: str
    block_rest_http: bool
    cud_enabled: bool

    @property
    def is_sdk(self) -> bool:
        return self.provider == PROVIDER_SDK

    @property
    def is_rest(self) -> bool:
        return not self.is_sdk


def load_sql_accounting_pr_write_settings() -> SqlAccountingPurchaseRequestWriteSettings:
    """
    ``SQL_ACCOUNTING_PR_WRITE_PROVIDER`` — ``Rest`` (default) or ``Sdk``.
    ``SQL_ACCOUNTING_BLOCK_REST_HTTP`` — shared lab lock; refuse REST PR writes when true.
    ``SQLACC_SDK_PR_CUD_ENABLED`` — must be true for live COM New/Edit/Save (default false).
    """
    provider = normalize_write_provider(os.getenv("SQL_ACCOUNTING_PR_WRITE_PROVIDER"))
    block_rest = _truthy("SQL_ACCOUNTING_BLOCK_REST_HTTP", False)
    cud_enabled = _truthy("SQLACC_SDK_PR_CUD_ENABLED", False)
    return SqlAccountingPurchaseRequestWriteSettings(
        provider=provider,
        block_rest_http=block_rest,
        cud_enabled=cud_enabled,
    )


__all__ = [
    "PROVIDER_REST",
    "PROVIDER_SDK",
    "SqlAccountingPurchaseRequestWriteSettings",
    "load_sql_accounting_pr_write_settings",
    "normalize_write_provider",
]
