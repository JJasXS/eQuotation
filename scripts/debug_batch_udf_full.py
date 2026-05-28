"""Debug ST_BATCH sort-first flag for procurement on-hand breakdown."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True, help="ST_ITEM.CODE")
    ap.add_argument("--location", required=True, help="ST_TR.LOCATION")
    ap.add_argument("--batches", nargs="*", help="Optional batch codes to inspect on ST_BATCH")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)

    from dotenv import load_dotenv

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides
    from utils.db_utils import build_firebird_dsn
    from utils.procurement_stock_card_queries import (
        _get_table_columns,
        _pick_existing,
        _pick_st_batch_sort_first_column,
        fetch_procurement_metric_breakdown,
    )
    from utils.role_permissions import _truthy

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    apply_tenant_env_overrides()

    import fdb

    con = fdb.connect(
        dsn=build_firebird_dsn(
            (os.getenv("DB_PATH") or "").strip(),
            (os.getenv("DB_HOST") or "").strip() or None,
        ),
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
        charset="UTF8",
    )
    cur = con.cursor()

    batch_cols = _get_table_columns(cur, "ST_BATCH")
    sort_col = _pick_st_batch_sort_first_column(batch_cols)
    b_batch = _pick_existing(batch_cols, "BATCH", "BATCHNO", "LOT", "BATCHCODE", "CODE")
    print(f"ST_BATCH sort-first column: {sort_col!r} (batch key column: {b_batch!r})")

    if args.batches and sort_col and b_batch:
        for batch in args.batches:
            cur.execute(
                f"""
                SELECT B.{b_batch}, B.{sort_col}, CAST(B.{sort_col} AS VARCHAR(40))
                FROM ST_BATCH B
                WHERE TRIM(COALESCE(CAST(B.{b_batch} AS VARCHAR(120)), '')) = ?
                """,
                (batch.strip(),),
            )
            print(f"\nST_BATCH rows for {batch!r}:")
            for row in cur.fetchall() or []:
                print(f"  {row[0]!r} flag={row[1]!r} truthy={_truthy(row[1])}")

    payload = fetch_procurement_metric_breakdown(
        cur, "avail_qty", args.item.strip(), args.location.strip()
    )
    print(f"\nBreakdown ({payload.get('title')}):")
    for i, row in enumerate(payload.get("rows") or []):
        print(
            f"  {i + 1}. batch={row.get('batch')!r} "
            f"sort_first={row.get('sort_first_flag')!r} "
            f"sqty={row.get('sqty')} suom={row.get('suomqty')}"
        )
    print("note:", (payload.get("summary") or {}).get("note"))

    cur.close()
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
