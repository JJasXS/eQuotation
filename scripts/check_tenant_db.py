"""Quick check: which DB does TNT10004 (or whatever TENANT_CODE is) connect to?"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)

    from dotenv import load_dotenv

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    code = (os.getenv("TENANT_CODE") or "").strip()
    print(f"--- TENANT_CODE: {code!r}")

    t0 = time.time()
    try:
        applied = apply_tenant_env_overrides()
        print(f"--- bootstrap applied: {applied} ({(time.time()-t0)*1000:.0f} ms)")
    except Exception as exc:
        print("--- bootstrap ERROR:", exc)
        traceback.print_exc()
        return 1

    db_host = (os.getenv("DB_HOST") or "").strip()
    db_path = (os.getenv("DB_PATH") or "").strip()
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_pass = (os.getenv("DB_PASSWORD") or "").strip()

    print("--- DB_HOST     :", db_host or "(empty)")
    print("--- DB_PATH     :", db_path or "(empty)")
    print("--- DB_USER     :", db_user or "(empty)")
    print(f"--- DB_PASSWORD : (hidden, {len(db_pass)} chars)")
    print("--- SQL_API_HOST:", os.getenv("SQL_API_HOST") or "(empty)")

    if not db_path:
        print("--- CONNECT SKIPPED: DB_PATH empty.")
        return 2

    try:
        import fdb  # type: ignore
    except Exception as exc:
        print("--- fdb import FAILED:", exc)
        return 3

    from utils.db_utils import build_firebird_dsn

    dsn = build_firebird_dsn(db_path, db_host or None)
    print("--- DSN         :", dsn)

    t0 = time.time()
    try:
        con = fdb.connect(
            dsn=dsn,
            user=db_user or "sysdba",
            password=db_pass or "masterkey",
            charset="UTF8",
        )
    except Exception as exc:
        print(f"--- CONNECT FAILED after {(time.time()-t0)*1000:.0f} ms: {exc}")
        return 4

    print(f"--- CONNECT OK ({(time.time()-t0)*1000:.0f} ms)")
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0"
        )
        row = cur.fetchone()
        cur.close()
        if row:
            print(f"---   user tables  : {int(row[0])}")

        cur = con.cursor()
        cur.execute(
            "SELECT FIRST 1 CAST(RDB$RELATION_NAME AS VARCHAR(63)) "
            "FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0 "
            "ORDER BY RDB$RELATION_NAME"
        )
        sample = cur.fetchone()
        cur.close()
        if sample and sample[0]:
            print("---   sample table :", str(sample[0]).strip())
    finally:
        try:
            con.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
