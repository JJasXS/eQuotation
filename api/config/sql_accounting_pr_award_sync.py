"""Post-award Purchase Request sync mode (paid REST vs local Firebird only)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


AWARD_SYNC_REST = "Rest"
AWARD_SYNC_LOCAL_ONLY = "LocalOnly"


def normalize_award_sync_mode(raw: str | None) -> str:
    """Return Rest or LocalOnly. Anything other than LocalOnly (case-insensitive) is Rest."""
    value = (raw or "").strip()
    if value.lower() == AWARD_SYNC_LOCAL_ONLY.lower():
        return AWARD_SYNC_LOCAL_ONLY
    return AWARD_SYNC_REST


def _fdb_basename(path_or_name: str) -> str:
    text = (path_or_name or "").strip().replace("\\", "/")
    if not text:
        return ""
    return Path(text).name.upper()


def parse_allowed_local_only_databases(raw: str | None) -> set[str]:
    """Comma-separated FDB basenames allowed for LocalOnly (e.g. ACC-ANOZ.FDB)."""
    out: set[str] = set()
    for part in (raw or "").split(","):
        name = _fdb_basename(part)
        if name:
            out.add(name)
    return out


@dataclass(frozen=True)
class CompanyIdentityCheck:
    ok: bool
    local_database: str
    reason: str


def verify_local_only_company_identity(
    *,
    db_path: str | None = None,
    allowed_raw: str | None = None,
    sdk_database_file: str | None = None,
) -> CompanyIdentityCheck:
    """
    LocalOnly is allowed only when DB_PATH basename is explicitly allow-listed
    and (when set) SQLACC_SDK_DATABASE_FILE matches the same FDB basename.
    """
    local = _fdb_basename(db_path if db_path is not None else (os.getenv("DB_PATH") or ""))
    if not local:
        return CompanyIdentityCheck(
            ok=False,
            local_database="",
            reason="DB_PATH is missing; cannot verify company database for LocalOnly.",
        )

    allowed = parse_allowed_local_only_databases(
        allowed_raw
        if allowed_raw is not None
        else (
            os.getenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASES")
            or os.getenv("SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE")
            or ""
        )
    )
    if not allowed:
        return CompanyIdentityCheck(
            ok=False,
            local_database=local,
            reason=(
                "LocalOnly requires SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE "
                "(or _DATABASES) to list allowed FDB basename(s)."
            ),
        )
    if local not in allowed:
        return CompanyIdentityCheck(
            ok=False,
            local_database=local,
            reason=(
                f"DB_PATH basename {local} is not in allowed LocalOnly databases "
                f"{sorted(allowed)}."
            ),
        )

    sdk_raw = (
        sdk_database_file
        if sdk_database_file is not None
        else (os.getenv("SQLACC_SDK_DATABASE_FILE") or "")
    )
    sdk_name = _fdb_basename(sdk_raw)
    if sdk_name and sdk_name != local:
        return CompanyIdentityCheck(
            ok=False,
            local_database=local,
            reason=(
                f"SQLACC_SDK_DATABASE_FILE basename {sdk_name} does not match "
                f"DB_PATH basename {local}."
            ),
        )

    return CompanyIdentityCheck(ok=True, local_database=local, reason="ok")


@dataclass(frozen=True)
class SqlAccountingPrAwardSyncSettings:
    """Post-award sync. Default Rest preserves paid /purchaserequest mirror."""

    mode: str

    @property
    def is_local_only(self) -> bool:
        return self.mode == AWARD_SYNC_LOCAL_ONLY

    @property
    def is_rest(self) -> bool:
        return not self.is_local_only


def load_sql_accounting_pr_award_sync_settings() -> SqlAccountingPrAwardSyncSettings:
    """
    ``SQL_ACCOUNTING_PR_AWARD_SYNC_MODE`` — ``Rest`` (default) or ``LocalOnly``.

    LocalOnly also requires ``SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE``
    (or ``_DATABASES``) to match ``DB_PATH`` basename (e.g. ``ACC-ANOZ.FDB``).
    """
    mode = normalize_award_sync_mode(os.getenv("SQL_ACCOUNTING_PR_AWARD_SYNC_MODE"))
    return SqlAccountingPrAwardSyncSettings(mode=mode)


__all__ = [
    "AWARD_SYNC_LOCAL_ONLY",
    "AWARD_SYNC_REST",
    "CompanyIdentityCheck",
    "SqlAccountingPrAwardSyncSettings",
    "load_sql_accounting_pr_award_sync_settings",
    "normalize_award_sync_mode",
    "parse_allowed_local_only_databases",
    "verify_local_only_company_identity",
]
