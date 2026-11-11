"""ACC-ANOZ read verification: Firebird supplier master + LocalOnly PO sync (no writes)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)


def main() -> int:
    os.environ["SQL_ACCOUNTING_BLOCK_REST_HTTP"] = "true"
    os.environ["SQL_ACCOUNTING_MASTER_READ_PROVIDER"] = "Firebird"
    os.environ["SQL_ACCOUNTING_PO_SYNC_MODE"] = "LocalOnly"
    os.environ["SQL_ACCOUNTING_PO_LOCAL_ONLY_DATABASE"] = "ACC-ANOZ.FDB"
    os.environ["SQL_API_ACCESS_KEY"] = ""
    os.environ["SQL_API_SECRET_KEY"] = ""
    os.environ.setdefault("DB_HOST", "192.168.100.201/3050")
    os.environ.setdefault("DB_PATH", "C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB")
    os.environ.setdefault("DB_USER", "sysdba")
    os.environ.setdefault("DB_PASSWORD", "masterkey")
    os.environ.setdefault("SQLACC_SDK_DATABASE_FILE", "ACC-ANOZ.FDB")

    from utils.pr_route_helpers import resolve_supplier_master
    from utils.procurement_sql_api_sync import sync_purchase_order_supplier_sql_api
    from utils.sql_api_supplier import fetch_firebird_supplier_master_fields

    code = "400-K0001"
    fb = fetch_firebird_supplier_master_fields(code)
    if not fb or fb.get("code") != code:
        print(f"FAIL: Firebird supplier miss for {code}: {fb!r}", flush=True)
        return 1
    print(
        f"PASS supplier FB: code={fb.get('code')} name={fb.get('companyname')!r} "
        f"addr1={fb.get('address1')!r} tin={fb.get('tin')!r}",
        flush=True,
    )

    resolved = resolve_supplier_master(code, "fallback-name")
    if resolved.get("companyname") != fb.get("companyname"):
        print(f"FAIL: resolve_supplier_master mismatch {resolved!r}", flush=True)
        return 1
    print("PASS resolve_supplier_master uses Firebird under BLOCK_REST", flush=True)

    sync = sync_purchase_order_supplier_sql_api(1, code, po_number="PO-LOCALONLY-CHECK")
    if not sync.get("synced") or sync.get("mode") != "localOnly" or not sync.get("skippedPaidRest"):
        print(f"FAIL: LocalOnly sync shape {sync!r}", flush=True)
        return 1
    print(f"PASS LocalOnly PO sync: {sync.get('reason')}", flush=True)
    print("NOTE: no PH_PO write performed (read-only verification).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
