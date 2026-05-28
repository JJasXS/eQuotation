"""Show 5 sample rows from ST_ITEM in the tenant-bound database."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)

    from dotenv import load_dotenv

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides
    from utils.db_utils import build_firebird_dsn

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    apply_tenant_env_overrides()

    import fdb  # type: ignore

    dsn = build_firebird_dsn(
        (os.getenv("DB_PATH") or "").strip(),
        (os.getenv("DB_HOST") or "").strip() or None,
    )
    con = fdb.connect(
        dsn=dsn,
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
        charset="UTF8",
    )

    try:
        cur = con.cursor()
        cur.execute(
            "SELECT CAST(RDB$FIELD_NAME AS VARCHAR(63)) "
            "FROM RDB$RELATION_FIELDS "
            "WHERE RDB$RELATION_NAME = 'ST_ITEM' "
            "ORDER BY RDB$FIELD_POSITION"
        )
        cols = [str(r[0]).strip() for r in cur.fetchall()]
        cur.close()
        print(f"ST_ITEM has {len(cols)} columns. First 30:")
        print("  ", ", ".join(cols[:30]))
        print()

        wanted_candidates = [
            "CODE",
            "DESCRIPTION",
            "STOCKGROUP",
            "ITEMTYPE",
            "SUOM",
            "REMARK1",
            "SHELF",
        ]
        upper_cols = {c.upper() for c in cols}
        selected = [c for c in wanted_candidates if c in upper_cols][:6]
        if "CODE" not in selected:
            selected.insert(0, "CODE")
        select_list = ", ".join(
            f"CAST(COALESCE({c}, '') AS VARCHAR(160))" for c in selected
        )

        sql = (
            f"SELECT FIRST 5 {select_list} "
            "FROM ST_ITEM "
            "WHERE TRIM(COALESCE(CODE, '')) <> '' "
            "ORDER BY CODE"
        )
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
    finally:
        con.close()

    print(f"Got {len(rows)} row(s). Columns: {selected}")
    print()
    widths = []
    for c in selected:
        u = c.upper()
        if u == "CODE":
            widths.append(14)
        elif u == "DESCRIPTION":
            widths.append(40)
        elif u in ("SUOM", "ITEMTYPE", "STOCKGROUP", "SHELF"):
            widths.append(12)
        else:
            widths.append(20)
    print(" | ".join(c.ljust(w) for c, w in zip(selected, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        line = []
        for val, w in zip(r, widths):
            line.append(str(val or "").strip().ljust(w)[:w])
        print(" | ".join(line))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
