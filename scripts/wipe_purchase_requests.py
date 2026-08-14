#!/usr/bin/env python3
"""Wipe local Firebird e-PR / bidding data for manual retesting.

Deletes only purchase-request + bidding tables. Does NOT touch stock, suppliers,
customers, or quotations. Use --dry-run first.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.db_utils import get_db_connection, set_db_config
from utils.tenant_bootstrap import apply_tenant_env_overrides

# Child → parent order where known. Unknown tables are skipped if missing.
CANDIDATE_TABLES = [
    "PR_BID_LINE_AWARD",
    "PR_BID_DTL",
    "PR_BID_LOG",
    "PR_BID_INVITE",
    "PR_RFQ_INVITE",
    "PR_SELECTED_SUPPLIER",
    "PR_PQ_SELECTED_SUPPLIER",
    "PR_BID_HDR",
    "PH_PQDTL",
    "PH_PQ",
    "PR_PO_FROM_PQ",  # transfer mapping if present
]


def bootstrap() -> None:
    apply_appsettings_to_environ()
    load_dotenv(".env", override=False)
    os.environ.setdefault("TENANT_BOOTSTRAP_SKIP_SECRETS", "1")
    apply_tenant_env_overrides()
    set_db_config(
        os.getenv("DB_PATH"),
        os.getenv("DB_USER"),
        os.getenv("DB_PASSWORD"),
        os.getenv("DB_HOST"),
    )


def table_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM RDB$RELATIONS
        WHERE RDB$SYSTEM_FLAG = 0
          AND TRIM(RDB$RELATION_NAME) = ?
        """,
        (name.upper(),),
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def count_rows(cur, name: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {name}")
    return int(cur.fetchone()[0] or 0)


def discover_extra_tables(cur) -> list[str]:
    cur.execute(
        """
        SELECT TRIM(RDB$RELATION_NAME)
        FROM RDB$RELATIONS
        WHERE RDB$SYSTEM_FLAG = 0
          AND (
            UPPER(TRIM(RDB$RELATION_NAME)) STARTING WITH 'PH_PQ'
            OR UPPER(TRIM(RDB$RELATION_NAME)) STARTING WITH 'PR_BID'
            OR UPPER(TRIM(RDB$RELATION_NAME)) STARTING WITH 'PR_RFQ'
            OR UPPER(TRIM(RDB$RELATION_NAME)) CONTAINING 'PQ_SUPPLIER'
          )
        ORDER BY 1
        """
    )
    return [str(r[0]).strip().upper() for r in (cur.fetchall() or []) if r and r[0]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count only; do not delete")
    parser.add_argument("--yes", action="store_true", help="Required to actually delete")
    args = parser.parse_args()

    bootstrap()
    con = get_db_connection()
    cur = con.cursor()
    try:
        discovered = discover_extra_tables(cur)
        ordered: list[str] = []
        for t in CANDIDATE_TABLES:
            if t not in ordered and table_exists(cur, t):
                ordered.append(t)
        for t in discovered:
            if t not in ordered:
                # Put unknown detail-ish tables before PH_PQ
                if t != "PH_PQ":
                    ordered.insert(max(0, len(ordered) - 1), t)
                else:
                    ordered.append(t)

        print("DB:", os.getenv("DB_HOST"), os.getenv("DB_PATH"))
        print("Tables to clear:")
        totals = {}
        for t in ordered:
            n = count_rows(cur, t)
            totals[t] = n
            print(f"  {t}: {n}")

        if args.dry_run or not args.yes:
            print("\nDry run only. Re-run with --yes to delete.")
            return 0

        for t in ordered:
            cur.execute(f"DELETE FROM {t}")
            print(f"DELETED {t}: {totals.get(t, 0)} rows")
        con.commit()
        print("\nDone. Refresh View e-PR — counts should be 0.")
        return 0
    except Exception as exc:
        try:
            con.rollback()
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
