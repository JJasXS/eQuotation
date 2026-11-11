"""Post-transfer Purchase Order sync mode (paid REST vs local Firebird only)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from api.config.sql_accounting_pr_award_sync import (
    CompanyIdentityCheck,
    parse_allowed_local_only_databases,
    verify_local_only_company_identity,
)

PO_SYNC_REST = "Rest"
PO_SYNC_LOCAL_ONLY = "LocalOnly"


def normalize_po_sync_mode(raw: str | None) -> str:
    """Return Rest or LocalOnly. Anything other than LocalOnly is Rest."""
    value = (raw or "").strip()
    if value.lower() == PO_SYNC_LOCAL_ONLY.lower():
        return PO_SYNC_LOCAL_ONLY
    return PO_SYNC_REST


@dataclass(frozen=True)
class SqlAccountingPoSyncSettings:
    """
    After local PH_PO / PH_PODTL / ST_XTRANS transfer.

    ``LocalOnly``: company Firebird is authoritative; skip paid /purchaseorder.
    ``Rest``: previous supplier-header PUT mirror (rollback; still blocked when
    ``SQL_ACCOUNTING_BLOCK_REST_HTTP`` is true).
    """

    mode: str

    @property
    def is_local_only(self) -> bool:
        return self.mode == PO_SYNC_LOCAL_ONLY

    @property
    def is_rest(self) -> bool:
        return not self.is_local_only


def load_sql_accounting_po_sync_settings() -> SqlAccountingPoSyncSettings:
    """
    ``SQL_ACCOUNTING_PO_SYNC_MODE`` — ``Rest`` (default) or ``LocalOnly``.

    LocalOnly requires ``SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE`` (or ``_DATABASES``),
    falling back to the PR-award LocalOnly allow-list env when unset.
    """
    mode = normalize_po_sync_mode(os.getenv("SQL_ACCOUNTING_PO_SYNC_MODE"))
    return SqlAccountingPoSyncSettings(mode=mode)


def verify_po_local_only_company_identity(
    *,
    db_path: str | None = None,
    allowed_raw: str | None = None,
    sdk_database_file: str | None = None,
) -> CompanyIdentityCheck:
    """Allow-list check for PO LocalOnly (same rules as PR award LocalOnly)."""
    raw = allowed_raw
    if raw is None:
        raw = (
            os.getenv("SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASES")
            or os.getenv("SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE")
            or os.getenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASES")
            or os.getenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE")
            or ""
        )
    return verify_local_only_company_identity(
        db_path=db_path,
        allowed_raw=raw,
        sdk_database_file=sdk_database_file,
    )


__all__ = [
    "PO_SYNC_LOCAL_ONLY",
    "PO_SYNC_REST",
    "SqlAccountingPoSyncSettings",
    "load_sql_accounting_po_sync_settings",
    "normalize_po_sync_mode",
    "parse_allowed_local_only_databases",
    "verify_po_local_only_company_identity",
]
