"""Discover Firebird generators used by PH_PQ / PH_PO / ST_XTRANS."""
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
    from utils.db_utils import get_db_connection, set_db_config
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    apply_tenant_env_overrides()
    set_db_config(
        os.environ["DB_PATH"],
        os.environ.get("DB_USER", "sysdba"),
        os.environ.get("DB_PASSWORD", "masterkey"),
        os.environ.get("DB_HOST") or None,
    )

    con = get_db_connection()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT TRIM(RDB$GENERATOR_NAME)
            FROM RDB$GENERATORS
            WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0
            ORDER BY 1
            """
        )
        names = [str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]]
        print(f"total user generators: {len(names)}")
        for n in names:
            # Generator names are identifiers from RDB$GENERATORS (not user input).
            cur.execute(f"SELECT GEN_ID({n}, 0) FROM RDB$DATABASE")
            print(f"  {n}={cur.fetchone()[0]}")

        print("--- MAX keys ---")
        for table, col in (
            ("PH_PQ", "DOCKEY"),
            ("PH_PQDTL", "DTLKEY"),
            ("PH_PO", "DOCKEY"),
            ("PH_PODTL", "DTLKEY"),
            ("ST_XTRANS", "DOCKEY"),
            ("PH_GR", "DOCKEY"),
            ("PH_PI", "DOCKEY"),
        ):
            try:
                cur.execute(f"SELECT COALESCE(MAX({col}), 0) FROM {table}")
                print(f"  MAX {table}.{col}={cur.fetchone()[0]}")
            except Exception as exc:
                print(f"  MAX {table}.{col} ERR {exc}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
