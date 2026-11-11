#!/usr/bin/env python3
from __future__ import annotations

import os

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.db_utils import get_db_connection, set_db_config
from utils.firebird_helpers import get_table_columns
from utils.role_permissions import (
    ACCESS_TIER_PURCH_STAFF,
    compute_access_tier,
    location_in_scope,
    session_location_scope,
    staff_locations_from_sy_user_row,
    staff_udf_from_sy_user_row,
)
from utils.tenant_bootstrap import apply_tenant_env_overrides


def main() -> None:
    apply_appsettings_to_environ()
    load_dotenv(".env", override=False)
    os.environ.setdefault("TENANT_BOOTSTRAP_SKIP_SECRETS", "1")
    apply_tenant_env_overrides()
    set_db_config(os.getenv("DB_PATH"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD"), os.getenv("DB_HOST"))

    email = "jason.choo2004@gmail.com"
    con = get_db_connection()
    cur = con.cursor()
    cols = get_table_columns(cur, "SY_USER")
    select = [
        c
        for c in (
            "NAME",
            "EMAIL",
            "UDF_LOCATION",
            "UDF_ISADMIN",
            "UDF_ISPURHOD",
            "UDF_ISPURMGR",
            "UDF_ISPURMNG",
            "UDF_ISDIRECTOR",
            "UDF_SSTAFF",
            "UDF_USER",
        )
        if c in cols
    ]
    cur.execute(
        f"SELECT {', '.join(select)} FROM SY_USER WHERE LOWER(TRIM(COALESCE(EMAIL,''))) = ?",
        (email,),
    )
    row = cur.fetchone()
    row_map = {select[i]: row[i] for i in range(len(select))}
    print("SY_USER:")
    for k, v in row_map.items():
        print(f"  {k}={v!r}")

    flags = staff_udf_from_sy_user_row(row_map)
    print("flags:", flags)
    locs = staff_locations_from_sy_user_row(row_map)
    print("locs:", locs)
    tier = compute_access_tier(
        is_supplier=False,
        is_customer=False,
        staff_udf=flags,
        sy_user_row_present=True,
    )
    print("tier:", tier)
    scope = session_location_scope({"access_tier": tier, "staff_locations": locs})
    print("scope:", scope)

    cur.execute(
        """
        SELECT H.DOCKEY, H.DOCNO, TRIM(COALESCE(D.LOCATION, '')), COUNT(*)
        FROM PH_PQ H
        JOIN PH_PQDTL D ON D.DOCKEY = H.DOCKEY
        GROUP BY H.DOCKEY, H.DOCNO, TRIM(COALESCE(D.LOCATION, ''))
        ORDER BY H.DOCKEY DESC
        """
    )
    print("PRs vs scope:")
    for dockey, docno, loc, n in cur.fetchall() or []:
        print(f"  {docno} loc={loc!r} lines={n} in_scope={location_in_scope(scope, loc)}")

    cur.close()
    con.close()


if __name__ == "__main__":
    main()
