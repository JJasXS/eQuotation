#!/usr/bin/env python3
"""Inspect SY_USER.UDF_LOCATION and PR visibility for an email."""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.db_utils import get_db_connection, set_db_config
from utils.firebird_helpers import get_table_columns
from utils.role_permissions import (
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_PURCH_STAFF,
    infer_access_tier_from_session,
    location_in_scope,
    session_location_scope,
    staff_locations_from_sy_user_row,
)
from utils.tenant_bootstrap import apply_tenant_env_overrides


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


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else "jason.choo2004@gmail.com").strip().lower()
    bootstrap()
    con = get_db_connection()
    cur = con.cursor()
    try:
        cols = get_table_columns(cur, "SY_USER")
        print("SY_USER has UDF_LOCATION:", "UDF_LOCATION" in cols)
        print("Location-ish cols:", sorted(c for c in cols if "LOC" in c or c.startswith("UDF")))

        email_cols = [c for c in ("EMAIL", "USEREMAIL", "UDF_EMAIL", "USERNAME", "USERID") if c in cols]
        loc_col = "UDF_LOCATION" if "UDF_LOCATION" in cols else ""
        name_cols = [c for c in ("USERNAME", "NAME", "USERID", "EMAIL", "UDF_EMAIL", "UDF_SUFFIX", "ROLES", "ROLE") if c in cols]
        select_cols = list(dict.fromkeys([*name_cols, loc_col] if loc_col else name_cols))
        if not select_cols:
            print("No usable SY_USER columns")
            return 1

        where = " OR ".join([f"LOWER(TRIM(COALESCE({c}, ''))) = ?" for c in email_cols]) or "1=0"
        params = tuple([email] * len(email_cols)) if email_cols else ()
        sql = f"SELECT {', '.join(select_cols)} FROM SY_USER WHERE {where}"
        print("SQL:", sql)
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        print(f"Matched SY_USER rows: {len(rows)}")
        for row in rows:
            row_map = {select_cols[i]: row[i] for i in range(len(select_cols))}
            print("ROW:", {k: (str(v).strip() if v is not None else None) for k, v in row_map.items()})
            locs = staff_locations_from_sy_user_row(row_map)
            print(" parsed staff_locations:", locs)

            # Simulate session tiers
            for tier in (ACCESS_TIER_PURCH_STAFF, ACCESS_TIER_PURCH_MGMT, ACCESS_TIER_FULL_ADMIN):
                sess = {"access_tier": tier, "staff_locations": locs}
                scope = session_location_scope(sess)
                print(
                    f"  tier={tier}: scope={scope} JB_in_scope={location_in_scope(scope, 'JB')}"
                )

        # Current PRs and their detail locations
        dtl_cols = get_table_columns(cur, "PH_PQDTL")
        hdr_cols = get_table_columns(cur, "PH_PQ")
        loc = "LOCATION" if "LOCATION" in dtl_cols else ""
        docno = "DOCNO" if "DOCNO" in hdr_cols else ("CODE" if "CODE" in hdr_cols else "")
        key = "DOCKEY" if "DOCKEY" in hdr_cols else ""
        if loc and key:
            cur.execute(
                f"""
                SELECT FIRST 20 H.{key}, {"H." + docno if docno else "H." + key}, D.{loc}, COUNT(*)
                FROM PH_PQ H
                JOIN PH_PQDTL D ON D.{key} = H.{key}
                GROUP BY H.{key}, {"H." + docno if docno else "H." + key}, D.{loc}
                ORDER BY 1 DESC
                """
            )
            print("\nCurrent PR detail locations:")
            for r in cur.fetchall() or []:
                print(" ", r)
        else:
            print("Could not query PR locations; loc/key missing", loc, key)
        return 0
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
