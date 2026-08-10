"""Inspect triggers / shared DTLKEY strategy for purchase tables."""
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
        for table in ("PH_PQ", "PH_PQDTL", "PH_PO", "PH_PODTL", "ST_XTRANS"):
            cur.execute(
                """
                SELECT TRIM(T.RDB$TRIGGER_NAME), T.RDB$TRIGGER_TYPE, T.RDB$TRIGGER_INACTIVE
                FROM RDB$TRIGGERS T
                WHERE T.RDB$RELATION_NAME = ?
                  AND COALESCE(T.RDB$SYSTEM_FLAG, 0) = 0
                ORDER BY 1
                """,
                (table,),
            )
            rows = cur.fetchall() or []
            print(f"--- triggers {table}: {len(rows)}")
            for name, ttype, inactive in rows:
                print(f"  {str(name).strip()} type={ttype} inactive={inactive}")
                cur.execute(
                    """
                    SELECT RDB$TRIGGER_SOURCE
                    FROM RDB$TRIGGERS
                    WHERE RDB$TRIGGER_NAME = ?
                    """,
                    (name,),
                )
                src_row = cur.fetchone()
                src = (src_row[0] if src_row else "") or ""
                if hasattr(src, "read"):
                    src = src.read()
                text = str(src)
                if "GEN_ID" in text.upper() or "GENERATOR" in text.upper():
                    print("    SOURCE:")
                    for line in text.splitlines():
                        if line.strip():
                            print("   ", line[:200])

        print("--- detail MAX across purchase DTL tables ---")
        for table in (
            "PH_PQDTL",
            "PH_PODTL",
            "PH_GRDTL",
            "PH_PIDTL",
            "SL_QTDTL",
            "SL_SODTL",
        ):
            try:
                cur.execute(f"SELECT COALESCE(MAX(DTLKEY),0), COUNT(*) FROM {table}")
                mx, cnt = cur.fetchone()
                print(f"  {table}: max={mx} count={cnt}")
            except Exception as exc:
                print(f"  {table}: ERR {exc}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
