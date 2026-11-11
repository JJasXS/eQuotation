"""Verify LocalOnly PO Transfer readiness on ACC-ANOZ (no Transfer execution).

Checks config gates, Firebird company identity, UDF_POSTATUS column, supplier
master Firebird path, and optionally prepares an identifiable test PR + bids
for manual Award → Approve → Transfer in the Local Website UI.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)


def _apply_local_zero_paid_rest() -> None:
    os.environ["SQL_ACCOUNTING_BLOCK_REST_HTTP"] = "true"
    os.environ["SQL_ACCOUNTING_MASTER_READ_PROVIDER"] = "Firebird"
    os.environ["SQL_ACCOUNTING_PR_AWARD_SYNC_MODE"] = "LocalOnly"
    os.environ["SQL_ACCOUNTING_PR_AWARD_LOCAL_ONLY_DATABASE"] = "ACC-ANOZ.FDB"
    os.environ["SQL_ACCOUNTING_PO_SYNC_MODE"] = "LocalOnly"
    os.environ["SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE"] = "ACC-ANOZ.FDB"
    os.environ["SQL_API_ACCESS_KEY"] = ""
    os.environ["SQL_API_SECRET_KEY"] = ""
    os.environ["SQL_API_HOST"] = "127.0.0.1"
    os.environ.setdefault("DB_HOST", "192.168.100.201/3050")
    os.environ["DB_PATH"] = (
        os.getenv("DB_PATH")
        if "ACC-ANOZ" in (os.getenv("DB_PATH") or "").upper()
        else "C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB"
    )
    os.environ.setdefault("DB_USER", "sysdba")
    os.environ.setdefault("DB_PASSWORD", "masterkey")
    os.environ["SQLACC_SDK_DATABASE_FILE"] = "ACC-ANOZ.FDB"


def _check_config() -> list[str]:
    from api.config.sql_accounting_master_read import master_read_allows_paid_rest
    from api.config.sql_accounting_po_sync import (
        load_sql_accounting_po_sync_settings,
        verify_po_local_only_company_identity,
    )
    from api.config.sql_accounting_pr_award_sync import load_sql_accounting_pr_award_sync_settings
    from api.config.sql_accounting_write import load_sql_accounting_write_settings

    issues: list[str] = []
    write = load_sql_accounting_write_settings()
    po = load_sql_accounting_po_sync_settings()
    award = load_sql_accounting_pr_award_sync_settings()
    identity = verify_po_local_only_company_identity()

    print("--- Config ---", flush=True)
    print(f"  BLOCK_REST_HTTP={write.block_rest_http}", flush=True)
    print(f"  master_read_allows_paid_rest={master_read_allows_paid_rest()}", flush=True)
    print(f"  PO_SYNC_MODE={po.mode} localOnly={po.is_local_only}", flush=True)
    print(f"  AWARD_SYNC_MODE={award.mode} localOnly={award.is_local_only}", flush=True)
    print(f"  DB_PATH={os.getenv('DB_PATH')}", flush=True)
    print(f"  identity.ok={identity.ok} db={identity.local_database} ({identity.reason})", flush=True)

    if not write.block_rest_http:
        issues.append("SQL_ACCOUNTING_BLOCK_REST_HTTP is not true")
    if master_read_allows_paid_rest():
        issues.append("Paid master REST is still allowed")
    if not po.is_local_only:
        issues.append("SQL_ACCOUNTING_PO_SYNC_MODE is not LocalOnly")
    if not award.is_local_only:
        issues.append("SQL_ACCOUNTING_PR_AWARD_SYNC_MODE is not LocalOnly")
    if not identity.ok or identity.local_database != "ACC-ANOZ.FDB":
        issues.append(f"Company identity not ACC-ANOZ.FDB: {identity}")
    return issues


def _check_firebird() -> list[str]:
    import fdb
    from utils.db_utils import build_firebird_dsn
    from utils.sql_api_supplier import fetch_firebird_supplier_master_fields
    from utils.procurement_sql_api_sync import sync_purchase_order_supplier_sql_api

    issues: list[str] = []
    print("--- Firebird / LocalOnly sync ---", flush=True)
    con = fdb.connect(
        dsn=build_firebird_dsn(os.environ["DB_PATH"], os.environ.get("DB_HOST")),
        user=os.environ.get("DB_USER") or "sysdba",
        password=os.environ.get("DB_PASSWORD") or "",
        charset="UTF8",
    )
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT FIRST 1 1 FROM RDB$RELATION_FIELDS "
            "WHERE RDB$RELATION_NAME='PH_PO' AND TRIM(RDB$FIELD_NAME)='UDF_POSTATUS'"
        )
        has_udf = cur.fetchone() is not None
        print(f"  PH_PO.UDF_POSTATUS column present={has_udf}", flush=True)
        if not has_udf:
            issues.append("PH_PO.UDF_POSTATUS missing (ApprovalPO status will not be set)")

        supplier = fetch_firebird_supplier_master_fields("400-K0001")
        print(
            f"  Firebird supplier 400-K0001: "
            f"name={supplier.get('companyname')!r} addr1={supplier.get('address1')!r}",
            flush=True,
        )
        if not supplier.get("companyname"):
            issues.append("Firebird supplier master empty for 400-K0001")
    finally:
        con.close()

    sync = sync_purchase_order_supplier_sql_api(1, "400-K0001", po_number="PO-VERIFY-ONLY")
    print(
        f"  LocalOnly sync probe: synced={sync.get('synced')} mode={sync.get('mode')} "
        f"skippedPaidRest={sync.get('skippedPaidRest')}",
        flush=True,
    )
    if sync.get("mode") != "localOnly" or not sync.get("skippedPaidRest"):
        issues.append(f"LocalOnly PO sync probe unexpected: {sync}")
    return issues


def _check_code_path() -> list[str]:
    issues: list[str] = []
    transfer_path = ROOT / "utils" / "procurement_purchase_order_transfer.py"
    text = transfer_path.read_text(encoding="utf-8")
    print("--- Code path ---", flush=True)
    checks = {
        "UDF_POSTATUS=PENDING": 'header_values["UDF_POSTATUS"] = "PENDING"' in text,
        "PH_PO insert": '"PH_PO"' in text and "_insert_dynamic" in text,
        "ST_XTRANS insert": '"ST_XTRANS"' in text,
        "LocalOnly pre-check": "verify_po_local_only_company_identity" in text,
        "post-sync LocalOnly": "sync_purchase_order_supplier_sql_api" in text,
    }
    for name, ok in checks.items():
        print(f"  {name}: {'OK' if ok else 'MISSING'}", flush=True)
        if not ok:
            issues.append(f"Code path missing: {name}")
    return issues


def _prepare_test_pr() -> int:
    """Create identifiable PR + bids; do not award, approve, or transfer."""
    from utils.db_utils import set_db_config
    from utils.procurement_bidding import (
        create_bid_invitations,
        ensure_bidding_schema,
        submit_supplier_bid,
    )
    from utils.procurement_pr_split import _allocate_unique_request_number
    from utils.procurement_purchase_request import (
        _connect_db,
        _get_table_columns,
        create_purchase_request,
    )

    set_db_config(
        os.environ["DB_PATH"],
        os.environ.get("DB_USER") or "sysdba",
        os.environ.get("DB_PASSWORD") or "masterkey",
        os.environ.get("DB_HOST"),
    )
    ensure_bidding_schema()

    winner = "400-K0001"
    other = "400-U0001"
    today = date.today()

    con = _connect_db()
    try:
        cur = con.cursor()
        header_cols = _get_table_columns(cur, "PH_PQ")
        # Identifiable lab series so manual testers can find it.
        next_pr_no = _allocate_unique_request_number(
            cur,
            header_cols,
            split_from_docno="PR-EQPO25",
        )
        cur.execute(
            "SELECT FIRST 1 TRIM(CODE), TRIM(DESCRIPTION) FROM ST_ITEM "
            "WHERE TRIM(COALESCE(CODE, '')) <> '' ORDER BY CODE"
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("No ST_ITEM rows on ACC-ANOZ")
        item_code = str(row[0]).strip()
        item_name = str(row[1] or item_code).strip()
    finally:
        con.close()

    payload = {
        "requestDate": today.isoformat(),
        "departmentId": "PROC",
        "requesterId": "eq-po25-lab",
        "project": "----",
        "description": "EQ Phase2.5 LocalOnly PO Transfer lab (manual Award→Approve→Transfer)",
        "status": "SUBMITTED",
        "requestNumber": next_pr_no,
        "suppliers": [
            {"code": winner, "name": "K3 METAL SERVICE CENTRE SDN BHD", "email": ""},
            {"code": other, "name": "UNION ALUMINIUM (SUZHOU) CO, LTD", "email": ""},
        ],
        "lineItems": [
            {
                "itemCode": item_code,
                "itemName": item_name,
                "description": item_name,
                "locationCode": "----",
                "qtySqty": 2,
                "qtySuomqty": 0,
                "unitPrice": 12.5,
                "tax": 0,
                "deliveryDate": (today + timedelta(days=14)).isoformat(),
            }
        ],
    }
    created = create_purchase_request(payload, created_by="eq-po25-lab")
    request_id = int(created["id"])
    request_no = str(created["requestNumber"])

    create_bid_invitations(
        request_dockey=request_id,
        request_no=request_no,
        suppliers=payload["suppliers"],
        created_by="eq-po25-lab",
    )

    con = _connect_db()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT FIRST 1 DTLKEY, ITEMCODE, QTY, UNITPRICE FROM PH_PQDTL "
            "WHERE DOCKEY = ? ORDER BY SEQ",
            (request_id,),
        )
        dtl = cur.fetchone()
        if not dtl:
            raise RuntimeError("PR created without detail lines")
        detail_id = int(dtl[0])
        qty = float(dtl[2] or 2)
    finally:
        con.close()

    bid_line = {
        "detailId": detail_id,
        "itemCode": item_code,
        "description": item_name,
        "quantity": qty,
        "unitPrice": 11.0,
        "tax": 0,
        "remarks": "EQ-PO25 lab bid winner",
    }
    submit_supplier_bid(
        request_dockey=request_id,
        request_no=request_no,
        supplier_code=winner,
        supplier_name="K3 METAL SERVICE CENTRE SDN BHD",
        bid_lines=[bid_line],
        remarks="EQ-PO25 lab",
        created_by=winner,
    )
    submit_supplier_bid(
        request_dockey=request_id,
        request_no=request_no,
        supplier_code=other,
        supplier_name="UNION ALUMINIUM (SUZHOU) CO, LTD",
        bid_lines=[{**bid_line, "unitPrice": 13.0, "remarks": "EQ-PO25 lab other"}],
        remarks="EQ-PO25 lab other",
        created_by=other,
    )

    print("--- Test PR prepared (NO transfer executed) ---", flush=True)
    print(f"  DOCNO={request_no} DOCKEY={request_id} DTLKEY={detail_id}", flush=True)
    print(f"  Item={item_code} qty={qty}", flush=True)
    print(f"  Award winner to use: {winner}", flush=True)
    print("", flush=True)
    print("Manual UI steps:", flush=True)
    print("  1. Ensure Local Website was restarted after LocalOnly PO changes", flush=True)
    print("  2. Login admin: http://127.0.0.1:8880/login", flush=True)
    print(f"  3. Bidding: select {request_no}, tick lines under {winner}, Save Item Awards", flush=True)
    print("  4. View e-PR: confirm APPROVED + UDF_SUPCODE after award", flush=True)
    print("  5. Transfer to PO (do not re-run if first transfer succeeds)", flush=True)
    print("  6. After transfer, run verification SQL below", flush=True)
    print("", flush=True)
    print("Post-transfer verification SQL (ACC-ANOZ):", flush=True)
    print(
        f"  -- replace DOCNO after transfer\n"
        f"  SELECT DOCNO, DOCKEY, CODE, COMPANYNAME, ADDRESS1, UDF_POSTATUS, DOCAMT\n"
        f"  FROM PH_PO WHERE DESCRIPTION CONTAINING 'EQ Phase2.5' OR DOCNO STARTING WITH 'PO-'\n"
        f"  ORDER BY DOCKEY DESC ROWS 5;\n"
        f"  SELECT D.DTLKEY, D.ITEMCODE, D.QTY, D.UNITPRICE, D.FROMDOCKEY, D.FROMDTLKEY\n"
        f"  FROM PH_PODTL D JOIN PH_PO H ON H.DOCKEY=D.DOCKEY\n"
        f"  WHERE D.FROMDOCKEY={request_id};\n"
        f"  SELECT CODE, FROMDOCTYPE, TODOCTYPE, FROMDOCKEY, TODOCKEY, FROMDTLKEY, TODTLKEY, QTY\n"
        f"  FROM ST_XTRANS WHERE FROMDOCKEY={request_id} AND FROMDOCTYPE='PQ';",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prepare-pr",
        action="store_true",
        help="Create identifiable ACC-ANOZ PR + bids for manual Award→Transfer (no transfer)",
    )
    args = parser.parse_args()

    _apply_local_zero_paid_rest()
    issues = []
    issues.extend(_check_config())
    issues.extend(_check_code_path())
    issues.extend(_check_firebird())

    if issues:
        print("--- FAIL ---", flush=True)
        for item in issues:
            print(f"  - {item}", flush=True)
        return 1

    print("--- PASS: LocalOnly PO Transfer gates ready ---", flush=True)
    if args.prepare_pr:
        return _prepare_test_pr()
    print("Re-run with --prepare-pr to create the manual test PR.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
