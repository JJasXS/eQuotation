#!/usr/bin/env python3
"""
Prepare a purchase request + supplier bid for manual "Save Item Awards" testing.

Usage (from repo root, server can be running):
  python scripts/setup_bidding_award_test.py
  python scripts/setup_bidding_award_test.py --auto-save-awards

Then in the browser:
  1. http://localhost:8880/admin/procurement/bidding
  2. Select the printed PR
  3. Tick each line for the winning supplier
  4. Click "Save Item Awards"
  5. Verify PR/PO show supplier code + company name in SQL / View e-PR
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ

apply_appsettings_to_environ(project_root=_REPO)
load_dotenv(_REPO / ".env", override=False)

from utils.db_utils import get_db_connection, set_db_config
from utils.procurement_bidding import (
    create_bid_invitations,
    ensure_bidding_schema,
    list_bids_for_request,
    save_line_awards,
    submit_supplier_bid,
)
from utils.procurement_purchase_request import _connect_db, create_purchase_request

# Default suppliers that exist in your SQL API list (adjust if needed).
WINNER_CODE = os.getenv("BIDDING_TEST_SUPPLIER", "400-U0001").strip()
WINNER_NAME = os.getenv("BIDDING_TEST_SUPPLIER_NAME", "UNION ALUMINIUM (SUZHOU) CO, LTD").strip()
OTHER_CODE = os.getenv("BIDDING_TEST_SUPPLIER_B", "400-J0001").strip()
OTHER_NAME = os.getenv("BIDDING_TEST_SUPPLIER_B_NAME", "JASON CORP").strip()


def _init_db() -> None:
    if not (os.getenv("TENANT_CODE") or "").strip():
        os.environ["TENANT_CODE"] = "TNT10004"
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_tenant_env_overrides()
    set_db_config(
        os.getenv("DB_PATH"),
        os.getenv("DB_USER") or "sysdba",
        os.getenv("DB_PASSWORD") or "masterkey",
        os.getenv("DB_HOST"),
    )


def _stock_lines(count: int = 1) -> list[dict]:
    con = get_db_connection()
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT FIRST {max(1, int(count))} TRIM(CODE), TRIM(DESCRIPTION)
            FROM ST_ITEM
            WHERE TRIM(COALESCE(CODE, '')) <> ''
            ORDER BY CODE
            """
        )
        rows = cur.fetchall() or []
        if not rows:
            raise RuntimeError("No ST_ITEM rows found — add a stock item first.")
        out: list[dict] = []
        for idx, row in enumerate(rows, start=1):
            code = str(row[0] or "").strip()
            name = str(row[1] or code).strip() or code
            out.append(
                {
                    "itemCode": code,
                    "itemName": name,
                    "description": name,
                    "locationCode": "----",
                    "qtySqty": 1,
                    "qtySuomqty": 0,
                    "unitPrice": 10.0 + idx,
                    "tax": 0,
                    "deliveryDate": (date.today() + timedelta(days=14)).isoformat(),
                }
            )
        return out
    finally:
        con.close()


def _first_stock_line() -> dict:
    return _stock_lines(1)[0]


def _fetch_pr_details(request_dockey: int) -> list[dict]:
    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT DTLKEY, ITEMCODE, DESCRIPTION, QTY, UNITPRICE, TAXAMT
            FROM PH_PQDTL
            WHERE DOCKEY = ?
            ORDER BY SEQ
            """,
            (int(request_dockey),),
        )
        out = []
        for row in cur.fetchall() or []:
            if not row:
                continue
            dtlkey = int(row[0])
            qty = float(row[3] or 0)
            out.append(
                {
                    "dtlkey": dtlkey,
                    "detailId": dtlkey,
                    "itemcode": str(row[1] or "").strip(),
                    "description": str(row[2] or "").strip(),
                    "qty": qty,
                    "unitprice": float(row[4] or 0),
                    "taxamt": float(row[5] or 0),
                }
            )
        return out
    finally:
        con.close()


def _read_ph_pq_supplier(request_dockey: int) -> dict:
    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT FIRST 1 DOCNO, CODE, COMPANYNAME, CURRENCYCODE FROM PH_PQ WHERE DOCKEY = ?",
            (int(request_dockey),),
        )
        row = cur.fetchone()
        if not row:
            return {}
        return {
            "docno": str(row[0] or "").strip(),
            "code": str(row[1] or "").strip(),
            "companyname": str(row[2] or "").strip(),
            "currencycode": str(row[3] or "").strip(),
        }
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup PR + bids for award testing")
    parser.add_argument(
        "--auto-save-awards",
        action="store_true",
        help="Save item awards in this script (same as clicking Save Item Awards)",
    )
    parser.add_argument(
        "--split-test",
        action="store_true",
        help="Create PR with 2 lines + 2 suppliers for mixed award / 2-PR split test",
    )
    args = parser.parse_args()

    _init_db()
    ensure_bidding_schema()

    today = date.today()
    lines = _stock_lines(2 if args.split_test else 1)

    from utils.procurement_pr_split import _allocate_unique_request_number
    from utils.procurement_purchase_request import _connect_db, _get_table_columns

    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        next_pr_no = _allocate_unique_request_number(
            cur,
            header_cols,
            split_from_docno="PR-26060015",
        )
    finally:
        con.close()

    payload = {
        "requestDate": today.isoformat(),
        "departmentId": "PROC",
        "requesterId": "award-test",
        "project": "----",
        "description": "2-PR split test" if args.split_test else "Award supplier sync test",
        "status": "SUBMITTED",
        "requestNumber": next_pr_no,
        "suppliers": [
            {"code": WINNER_CODE, "name": WINNER_NAME, "email": ""},
            {"code": OTHER_CODE, "name": OTHER_NAME, "email": ""},
        ],
        "lineItems": lines,
    }

    created = create_purchase_request(payload, created_by="award-test-script")
    request_id = int(created["id"])
    request_no = str(created["requestNumber"])

    create_bid_invitations(
        request_dockey=request_id,
        request_no=request_no,
        suppliers=payload["suppliers"],
        created_by="award-test-script",
    )

    details = _fetch_pr_details(request_id)
    if not details:
        print("ERROR: PR created but no PH_PQDTL lines found.", file=sys.stderr)
        return 1

    bid_lines = [
        {
            "detailId": d["detailId"],
            "itemCode": d["itemcode"],
            "description": d["description"],
            "quantity": d["qty"] or 1,
            "unitPrice": round(d["unitprice"] * 0.95, 2) or 9.5,
            "tax": 0,
            "remarks": "Test bid — winner",
        }
        for d in details
    ]

    submit_supplier_bid(
        request_dockey=request_id,
        request_no=request_no,
        supplier_code=WINNER_CODE,
        supplier_name=WINNER_NAME,
        bid_lines=bid_lines,
        remarks="Automated test bid (winner)",
        created_by=WINNER_CODE,
    )

    submit_supplier_bid(
        request_dockey=request_id,
        request_no=request_no,
        supplier_code=OTHER_CODE,
        supplier_name=OTHER_NAME,
        bid_lines=[
            {**row, "unitPrice": round(float(row["unitPrice"]) * 1.1, 2), "remarks": "Test bid — other"}
            for row in bid_lines
        ],
        remarks="Automated test bid (other supplier)",
        created_by=OTHER_CODE,
    )

    bids = list_bids_for_request(request_id)
    winner_bid = next(
        (b for b in bids if str(b.get("supplierCode") or "").strip() == WINNER_CODE),
        None,
    )
    if not winner_bid:
        print("ERROR: Winner bid not found after submit.", file=sys.stderr)
        return 1

    bid_id = int(winner_bid["bidId"])

    print("")
    print("=== Bidding award test data ready ===")
    print(f"  PR dockey (id):  {request_id}")
    print(f"  PR number:       {request_no}")
    print(f"  Winning supplier: {WINNER_CODE} — {WINNER_NAME}")
    print(f"  Winning bid id:  {bid_id}")
    print(f"  Line detail ids: {[d['detailId'] for d in details]}")
    print("")
    print("Manual UI steps:")
    print(f"  1. Restart eQuotation if you have not since the PR-split change")
    print(f"  2. Open http://localhost:8880/admin/procurement/bidding")
    print(f"  3. Select PR {request_no} (dockey {request_id})")
    if args.split_test and len(details) >= 2:
        d1, d2 = details[0]["detailId"], details[1]["detailId"]
        print(f"  4. Tick line 1 ({d1}) under {WINNER_CODE}")
        print(f"  5. Tick line 2 ({d2}) under {OTHER_CODE}")
        print("  6. Click Save Item Awards")
        print(f"     -> {request_no} stays for first supplier ticked (lowest line no): {WINNER_CODE}")
        print(f"     -> next PR number for {OTHER_CODE} will be PR-26060017 (or next free after parent)")
        print(f"  7. Check View e-PR: original {request_no} + the next created PR")
    else:
        print(f"  4. Under supplier {WINNER_CODE}, tick every line checkbox")
        print("  5. Click Save Item Awards")
        print(f"  6. Check GET /eq-sql-api/purchaserequest/{request_id} — code should be {WINNER_CODE}")
    print("")

    if args.auto_save_awards:
        awards = [{"detailId": d["detailId"], "bidId": bid_id} for d in details]
        result = save_line_awards(
            request_id,
            awards,
            actor="award-test-script",
            udf_reason="Auto test save awards",
        )
        header = _read_ph_pq_supplier(request_id)
        print("Auto save_item_awards result:")
        print(json.dumps(result, indent=2, default=str))
        print("PH_PQ header after awards:")
        print(json.dumps(header, indent=2))
        if header.get("code") == WINNER_CODE and header.get("companyname"):
            print("OK: Supplier applied on PH_PQ.")
        else:
            print("WARN: PH_PQ header still missing supplier — check server log for SQL API PUT.", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
