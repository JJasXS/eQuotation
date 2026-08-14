#!/usr/bin/env python3
"""Backfill PH_PODTL thickness/width/length from linked PQ lines (or BATCH).

Use after the PR→PO transfer UDF copy fix for POs created before that change.

  python scripts/backfill_po_dim_udfs.py --dry-run
  python scripts/backfill_po_dim_udfs.py
  python scripts/backfill_po_dim_udfs.py --docno PO-20260814-0001
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.db_utils import get_db_connection, set_db_config
from utils.firebird_helpers import _clean_text, get_table_columns, pick_existing
from utils.sql_api_batch import parse_batch_code_dimensions
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


def _missing(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not _clean_text(val):
        return True
    return False


def _load_pq_dims(cur, dockey: int, dtlkey: int) -> dict[str, str]:
    pq_cols = get_table_columns(cur, "PH_PQDTL")
    fk = pick_existing(pq_cols, "DOCKEY", "PQKEY")
    dtl = pick_existing(pq_cols, "DTLKEY", "PQDTLKEY", "ID")
    t_col = pick_existing(pq_cols, "UDF_THICKNESS")
    w_col = pick_existing(pq_cols, "UDF_WIDTH")
    l_col = pick_existing(pq_cols, "UDF_LENGTH")
    batch_col = pick_existing(pq_cols, "BATCH")
    if not fk or not dtl:
        return {}
    select = [c for c in (t_col, w_col, l_col, batch_col) if c]
    if not select:
        return {}
    cur.execute(
        f"SELECT {', '.join(select)} FROM PH_PQDTL WHERE {fk} = ? AND {dtl} = ?",
        (int(dockey), int(dtlkey)),
    )
    row = cur.fetchone()
    if not row:
        return {}
    out: dict[str, str] = {}
    idx = 0
    if t_col:
        if not _missing(row[idx]):
            out["thickness"] = _clean_text(row[idx])
        idx += 1
    if w_col:
        if not _missing(row[idx]):
            out["width"] = _clean_text(row[idx])
        idx += 1
    if l_col:
        if not _missing(row[idx]):
            out["length"] = _clean_text(row[idx])
        idx += 1
    if batch_col:
        batch = row[idx] if idx < len(row) else None
        if any(_missing(out.get(k)) for k in ("thickness", "width", "length")):
            bt, bw, bl = parse_batch_code_dimensions(batch)
            if bt and "thickness" not in out:
                out["thickness"] = bt
            if bw and "width" not in out:
                out["width"] = bw
            if bl and "length" not in out:
                out["length"] = bl
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--docno", action="append", default=[], help="Limit to PO DOCNO (repeatable)")
    parser.add_argument("--limit", type=int, default=50, help="Max recent POs to scan")
    args = parser.parse_args()
    bootstrap()

    con = get_db_connection()
    try:
        cur = con.cursor()
        po_cols = get_table_columns(cur, "PH_PO")
        dtl_cols = get_table_columns(cur, "PH_PODTL")
        po_key = pick_existing(po_cols, "DOCKEY", "ID")
        po_doc = pick_existing(po_cols, "DOCNO")
        d_key = pick_existing(dtl_cols, "DTLKEY", "ID")
        d_fk = pick_existing(dtl_cols, "DOCKEY")
        from_doc = pick_existing(dtl_cols, "FROMDOCTYPE")
        from_dockey = pick_existing(dtl_cols, "FROMDOCKEY")
        from_dtlkey = pick_existing(dtl_cols, "FROMDTLKEY")
        t_col = pick_existing(dtl_cols, "UDF_THICKNESS")
        w_col = pick_existing(dtl_cols, "UDF_WIDTH")
        l_col = pick_existing(dtl_cols, "UDF_LENGTH")
        batch_col = pick_existing(dtl_cols, "BATCH")
        item_col = pick_existing(dtl_cols, "ITEMCODE")
        if not all([po_key, po_doc, d_key, d_fk, from_doc, from_dockey, from_dtlkey, t_col, w_col, l_col]):
            print("PH_PO/PH_PODTL schema missing required columns", file=sys.stderr)
            return 1

        docnos = [d.strip() for d in args.docno if d and d.strip()]
        if docnos:
            placeholders = ", ".join(["?"] * len(docnos))
            cur.execute(
                f"""
                SELECT {po_key}, {po_doc}
                FROM PH_PO
                WHERE {po_doc} IN ({placeholders})
                ORDER BY {po_key} DESC
                """,
                tuple(docnos),
            )
        else:
            cur.execute(
                f"""
                SELECT FIRST {int(args.limit)} {po_key}, {po_doc}
                FROM PH_PO
                ORDER BY {po_key} DESC
                """
            )
        headers = cur.fetchall() or []
        if not headers:
            print("No purchase orders found.")
            return 0

        updated = 0
        skipped = 0
        for po_dockey, docno in headers:
            cur.execute(
                f"""
                SELECT {d_key}, {from_dockey}, {from_dtlkey},
                       {t_col}, {w_col}, {l_col},
                       {batch_col or t_col}, {item_col or t_col}
                FROM PH_PODTL
                WHERE {d_fk} = ?
                  AND UPPER(TRIM({from_doc})) = 'PQ'
                """,
                (int(po_dockey),),
            )
            lines = cur.fetchall() or []
            print(f"\n{docno} (dockey={po_dockey}) — {len(lines)} PQ-linked line(s)")
            for row in lines:
                dtlkey = int(row[0])
                pq_dockey = int(row[1] or 0)
                pq_dtlkey = int(row[2] or 0)
                cur_t, cur_w, cur_l = row[3], row[4], row[5]
                batch = row[6] if batch_col else None
                item = row[7] if item_col else ""
                if not _missing(cur_t) and not _missing(cur_w) and not _missing(cur_l):
                    print(f"  dtl={dtlkey} already has dims T={cur_t} W={cur_w} L={cur_l}")
                    skipped += 1
                    continue

                dims = _load_pq_dims(cur, pq_dockey, pq_dtlkey) if pq_dockey and pq_dtlkey else {}
                if any(_missing(dims.get(k)) for k in ("thickness", "width", "length")):
                    bt, bw, bl = parse_batch_code_dimensions(batch)
                    if bt and _missing(dims.get("thickness")):
                        dims["thickness"] = bt
                    if bw and _missing(dims.get("width")):
                        dims["width"] = bw
                    if bl and _missing(dims.get("length")):
                        dims["length"] = bl

                new_t = dims.get("thickness") if _missing(cur_t) else _clean_text(cur_t)
                new_w = dims.get("width") if _missing(cur_w) else _clean_text(cur_w)
                new_l = dims.get("length") if _missing(cur_l) else _clean_text(cur_l)
                if _missing(new_t) and _missing(new_w) and _missing(new_l):
                    print(
                        f"  dtl={dtlkey} item={item!r} — no PQ/batch dims "
                        f"(from PQ {pq_dockey}/{pq_dtlkey}, batch={batch!r})"
                    )
                    skipped += 1
                    continue

                print(
                    f"  dtl={dtlkey} item={item!r} -> T={new_t!r} W={new_w!r} L={new_l!r} "
                    f"(from PQ {pq_dockey}/{pq_dtlkey})"
                )
                if args.dry_run:
                    updated += 1
                    continue
                cur.execute(
                    f"""
                    UPDATE PH_PODTL
                    SET {t_col} = ?, {w_col} = ?, {l_col} = ?
                    WHERE {d_key} = ?
                    """,
                    (new_t or None, new_w or None, new_l or None, dtlkey),
                )
                updated += 1

        if args.dry_run:
            print(f"\nDry-run: would update {updated} line(s); skipped {skipped}.")
        else:
            con.commit()
            print(f"\nUpdated {updated} line(s); skipped {skipped}.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
