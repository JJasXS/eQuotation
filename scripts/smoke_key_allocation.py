"""Live Firebird smoke: PR/PO key generators stay ahead of MAX after catch-up."""
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
    from utils.db_utils import set_db_config
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    apply_tenant_env_overrides()

    db_path = (os.getenv("DB_PATH") or "").strip()
    db_host = (os.getenv("DB_HOST") or "").strip() or None
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_pass = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    if not db_path:
        print("FAIL: DB_PATH empty after tenant bootstrap")
        return 2

    set_db_config(db_path, db_user, db_pass, db_host)

    from utils.procurement_purchase_order_transfer import (
        _allocate_unique_purchase_order_number,
    )
    from utils.procurement_purchase_request import (
        _allocate_unique_request_number,
        _connect_db,
        _get_table_columns,
        _next_key,
        _pick_existing,
        _request_number_exists,
    )
    from utils.procurement_purchase_order_transfer import _purchase_order_number_exists

    targets = [
        (
            "PH_PQ",
            ["DOCKEY", "PQKEY", "ID"],
            ["GEN_PH_PQ_ID", "GEN_PH_PQ_DOCKEY", "GEN_PH_PQ", "SEQ_PH_PQ_DOCKEY"],
        ),
        (
            "PH_PQDTL",
            ["DTLKEY", "PQDTLKEY", "ID"],
            ["GEN_PH_PQDTL_ID", "GEN_PH_PQDTL_DTLKEY", "GEN_PH_PQDTL", "SEQ_PH_PQDTL_DTLKEY"],
        ),
        (
            "PH_PO",
            ["DOCKEY", "ID"],
            ["GEN_PH_PO_ID", "GEN_PH_PO_DOCKEY", "GEN_PH_PO", "SEQ_PH_PO_DOCKEY"],
        ),
        (
            "PH_PODTL",
            ["DTLKEY", "ID"],
            ["GEN_PH_PODTL_ID", "GEN_PH_PODTL_DTLKEY", "GEN_PH_PODTL", "SEQ_PH_PODTL_DTLKEY"],
        ),
        (
            "ST_XTRANS",
            ["DOCKEY", "ID"],
            ["GEN_ST_XTRANS_ID", "GEN_ST_XTRANS_DOCKEY", "GEN_ST_XTRANS", "SEQ_ST_XTRANS_DOCKEY"],
        ),
    ]

    con = _connect_db()
    failures: list[str] = []
    try:
        cur = con.cursor()
        print(f"OK connect DB_HOST={db_host!r} DB_PATH={db_path!r}")

        for table, key_candidates, gens in targets:
            cols = _get_table_columns(cur, table)
            if not cols:
                print(f"SKIP {table}: table missing")
                continue
            key_col = _pick_existing(cols, *key_candidates)
            if not key_col:
                print(f"SKIP {table}: no key column")
                continue

            cur.execute(f"SELECT COALESCE(MAX({key_col}), 0) FROM {table}")
            max_before = int((cur.fetchone() or [0])[0] or 0)

            keys = [_next_key(cur, table, key_col, gens) for _ in range(3)]
            # Header/xtrans tables have SQL Accounting generators named after the table.
            # Detail tables often have none — MAX+1 is expected until insert retry.
            has_table_gen = False
            try:
                cur.execute(f"SELECT GEN_ID({table}, 0) FROM RDB$DATABASE")
                has_table_gen = cur.fetchone() is not None
            except Exception:
                has_table_gen = False

            if has_table_gen:
                if len(set(keys)) != 3:
                    failures.append(f"{table}: non-unique keys {keys}")
                if min(keys) <= max_before:
                    failures.append(
                        f"{table}: allocated {keys} not strictly above MAX={max_before}"
                    )
                print(f"OK {table}.{key_col} MAX={max_before} allocated={keys} (generator)")
            else:
                if keys[0] != max_before + 1:
                    failures.append(
                        f"{table}: expected MAX+1 fallback, got {keys[0]} MAX={max_before}"
                    )
                print(
                    f"OK {table}.{key_col} MAX={max_before} fallback={keys[0]} "
                    f"(no table generator; insert retry covers races)"
                )

        # DOCNO uniqueness checks (no insert)
        pq_cols = _get_table_columns(cur, "PH_PQ")
        if pq_cols:
            pr_no = _allocate_unique_request_number(cur, pq_cols)
            if _request_number_exists(cur, pq_cols, pr_no):
                failures.append(f"PR DOCNO still exists after allocate: {pr_no}")
            else:
                print(f"OK PR DOCNO free: {pr_no}")

        po_cols = _get_table_columns(cur, "PH_PO")
        if po_cols:
            po_no = _allocate_unique_purchase_order_number(cur, po_cols)
            if _purchase_order_number_exists(cur, po_cols, po_no):
                failures.append(f"PO DOCNO still exists after allocate: {po_no}")
            else:
                print(f"OK PO DOCNO free: {po_no}")

        # Do not commit — GEN_ID is non-transactional anyway; no table inserts performed.
        try:
            con.rollback()
        except Exception:
            pass
    finally:
        con.close()

    if failures:
        print("FAIL:")
        for item in failures:
            print(" -", item)
        return 1

    print("PASS: key + DOCNO allocation smoke checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
