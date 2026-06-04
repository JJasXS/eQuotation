"""List stock items that have UDF_MTYPE (SQL API detail first, then Firebird ST_ITEM)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))


def _load_dotenv() -> None:
    from utils.appsettings_env import apply_appsettings_to_environ

    apply_appsettings_to_environ(project_root=repo)
    env_path = repo / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
from utils.tenant_bootstrap import apply_tenant_env_overrides

apply_tenant_env_overrides()
from utils.db_utils import set_db_config

set_db_config(
    os.getenv("DB_PATH"),
    os.getenv("DB_USER") or "sysdba",
    os.getenv("DB_PASSWORD") or "masterkey",
    os.getenv("DB_HOST"),
)


def _mtype_from_row(row: dict) -> str:
    return str(row.get("UDF_MTYPE") or row.get("udf_mtype") or "").strip()


def from_firebird(limit: int = 50) -> list[tuple[str, str, str]]:
    import fdb
    from utils.db_utils import build_firebird_dsn

    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        return []
    dsn = build_firebird_dsn(db_path, (os.getenv("DB_HOST") or "").strip() or None)
    con = fdb.connect(
        dsn=dsn,
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
        charset="UTF8",
    )
    cur = con.cursor()
    try:
        cur.execute(
            f"""
            SELECT FIRST {int(limit)} TRIM(CODE), TRIM(COALESCE(DESCRIPTION, '')),
                   TRIM(COALESCE(UDF_MTYPE, ''))
            FROM ST_ITEM
            WHERE TRIM(COALESCE(CODE, '')) <> ''
              AND TRIM(COALESCE(UDF_MTYPE, '')) <> ''
            ORDER BY CODE
            """
        )
        out = [(str(a), str(b), str(c)) for a, b, c in cur.fetchall()]
    except Exception as e:
        print(f"[firebird] ST_ITEM UDF_MTYPE query failed: {e}", flush=True)
        out = []
    cur.close()
    con.close()
    return out


def from_sql_api(max_scan: int = 500) -> list[tuple[str, str, str]]:
    from utils.stock_items_catalog import (
        _try_fetch_stock_items_sql_api,
        fetch_stock_item_sql_api_by_code,
    )

    rows = _try_fetch_stock_items_sql_api() or []
    out: list[tuple[str, str, str]] = []
    for row in rows[:max_scan]:
        if not isinstance(row, dict):
            continue
        code = str(row.get("CODE") or row.get("code") or "").strip()
        if not code:
            continue
        mtype = _mtype_from_row(row)
        desc = str(row.get("DESCRIPTION") or row.get("description") or code).strip()
        if not mtype:
            detail = fetch_stock_item_sql_api_by_code(code)
            if detail:
                mtype = _mtype_from_row(detail)
                if mtype and not _mtype_from_row(row):
                    desc = str(detail.get("DESCRIPTION") or desc).strip()
        if mtype:
            out.append((code, desc, mtype))
    return out


def main() -> int:
    print(f"tenant={os.getenv('TENANT_CODE')!r} db={os.getenv('DB_PATH')!r}", flush=True)
    api_hits = from_sql_api()
    print(f"\n[SQL API] items with mtype: {len(api_hits)}", flush=True)
    for code, desc, mtype in api_hits[:25]:
        print(f"  {code!r} mtype={mtype!r} desc={desc[:60]!r}")
    if len(api_hits) > 25:
        print(f"  ... and {len(api_hits) - 25} more")

    fb_hits = from_firebird()
    print(f"\n[Firebird] items with mtype: {len(fb_hits)}", flush=True)
    for code, desc, mtype in fb_hits[:25]:
        print(f"  {code!r} mtype={mtype!r} desc={desc[:60]!r}")

    combined = api_hits or fb_hits
    if not combined:
        print("\nNo items with UDF_MTYPE found.", flush=True)
        return 1
    print(f"\nFirst test candidate: {combined[0][0]!r} -> {combined[0][2]!r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
