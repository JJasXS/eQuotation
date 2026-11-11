"""Master-data GET provider: Firebird vs paid SQL Accounting REST."""
from __future__ import annotations

import os
from dataclasses import dataclass

from api.config.sql_accounting_write import load_sql_accounting_write_settings

PROVIDER_FIREBIRD = "Firebird"
PROVIDER_REST = "Rest"


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def normalize_master_read_provider(raw: str | None) -> str:
    """Return Firebird or Rest. Default Firebird (Phase 2.2)."""
    value = (raw or "").strip()
    if value.lower() == PROVIDER_REST.lower():
        return PROVIDER_REST
    return PROVIDER_FIREBIRD


@dataclass(frozen=True)
class SqlAccountingMasterReadSettings:
    """
    Master list/detail GET routing.

    ``Firebird`` (default): company-file reads only; no paid api.sql.my GET.
    ``Rest``: previous REST-first behavior (rollback until equivalence verified).
    ``SQL_ACCOUNTING_BLOCK_REST_HTTP=true`` forces Firebird-only (no silent REST).
    """

    provider: str

    @property
    def is_firebird(self) -> bool:
        return self.provider == PROVIDER_FIREBIRD

    @property
    def is_rest(self) -> bool:
        return self.provider == PROVIDER_REST


def load_sql_accounting_master_read_settings() -> SqlAccountingMasterReadSettings:
    """Load ``SQL_ACCOUNTING_MASTER_READ_PROVIDER`` (Firebird|Rest)."""
    provider = normalize_master_read_provider(os.getenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER"))
    return SqlAccountingMasterReadSettings(provider=provider)


def master_read_allows_paid_rest() -> bool:
    """
    True only when paid SigV4 master GETs are permitted.

    False when Provider=Firebird or ``SQL_ACCOUNTING_BLOCK_REST_HTTP`` is set.
    """
    if load_sql_accounting_write_settings().block_rest_http:
        return False
    return load_sql_accounting_master_read_settings().is_rest
