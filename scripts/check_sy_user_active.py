"""Check SY_USER.ISACTIVE for a login email."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.tenant_bootstrap import apply_tenant_env_overrides

EMAIL = (sys.argv[1] if len(sys.argv) > 1 else "jason.choo2004@gmail.com").strip()


def parse_active(value) -> bool:
    s = "" if value is None else str(value).strip()
    return s in ("1", "Y", "y", "TRUE", "true", "True")


def main() -> int:
    apply_appsettings_to_environ()
    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
    apply_tenant_env_overrides()

    import fdb
    from utils.db_utils import build_firebird_dsn

    dsn = build_firebird_dsn(os.getenv("DB_PATH"), os.getenv("DB_HOST") or None)
    print(f"Email: {EMAIL}")
    print(f"TENANT_CODE: {os.getenv('TENANT_CODE')!r}")
    print(f"DB: host={os.getenv('DB_HOST')!r} path={os.getenv('DB_PATH')!r}")
    print()

    con = fdb.connect(
        dsn=dsn,
        user=os.getenv("DB_USER") or "SYSDBA",
        password=os.getenv("DB_PASSWORD") or "masterkey",
        charset="UTF8",
    )
    cur = con.cursor()

    cur.execute(
        """
        SELECT CODE, NAME, EMAIL, ISACTIVE
        FROM SY_USER
        WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
        """,
        (EMAIL,),
    )
    rows = cur.fetchall()
    if not rows:
        print("SY_USER.EMAIL: no row found")
    else:
        for row in rows:
            code, name, email, isactive = row
            active = parse_active(isactive)
            print("SY_USER.EMAIL match:")
            print(f"  CODE={code!r} NAME={name!r} EMAIL={email!r}")
            print(f"  ISACTIVE raw={isactive!r} ({type(isactive).__name__})")
            print(f"  Treated as active: {active}")
            if not active:
                print("  => Login blocked: ISACTIVE must be 1, Y, or TRUE")

    cur.execute(
        """
        SELECT TRIM(RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS
        WHERE RDB$RELATION_NAME = 'SY_USER' AND RDB$FIELD_NAME STARTING WITH 'UDF_'
        """,
    )
    udfs = [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
    for col in sorted(c for c in udfs if "EMAIL" in c.upper()):
        try:
            cur.execute(
                f"""
                SELECT CODE, NAME, {col}, ISACTIVE
                FROM SY_USER
                WHERE UPPER(TRIM({col})) = UPPER(TRIM(?))
                """,
                (EMAIL,),
            )
            for row in cur.fetchall() or []:
                print(f"\n{col} match:")
                print(f"  CODE={row[0]!r} NAME={row[1]!r} {col}={row[2]!r} ISACTIVE={row[3]!r}")
                print(f"  Treated as active: {parse_active(row[3])}")
        except Exception as exc:
            print(f"\n{col}: query failed: {exc}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
