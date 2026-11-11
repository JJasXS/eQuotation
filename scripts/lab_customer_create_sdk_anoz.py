"""Controlled ACC-ANOZ Customer Create via COM SDK (create-only CUD lab).

Requires SQLACC_SDK_* + ALLOW_LIVE_COM. Refuses if BLOCK_REST is false (lab profile).
Creates a unique CODE, verifies AR_CUSTOMER persistence, then exits (record kept).
Does not call paid SQL Accounting REST.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)


def _truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _apply_lab_env() -> None:
    os.environ["SQL_ACCOUNTING_BLOCK_REST_HTTP"] = "true"
    os.environ["SQL_ACCOUNTING_WRITE_PROVIDER"] = "Sdk"
    os.environ["SQL_ACCOUNTING_MASTER_READ_PROVIDER"] = "Firebird"
    os.environ["SQL_API_ACCESS_KEY"] = ""
    os.environ["SQL_API_SECRET_KEY"] = ""
    os.environ["SQL_API_HOST"] = "127.0.0.1"
    os.environ["SQLACC_SDK_ALLOW_LIVE_COM"] = "true"
    os.environ.setdefault("SQLACC_COM_PROG_ID", "SQLAcc.BizApp")
    os.environ.setdefault("SQLACC_SDK_DCF_PATH", r"\\192.168.100.201\Share\SQLACC.DCF")
    os.environ.setdefault("SQLACC_SDK_DATABASE_FILE", "ACC-ANOZ.FDB")
    os.environ.setdefault("SQLACC_SDK_USER", "ADMIN")
    os.environ.setdefault("DB_HOST", "192.168.100.201/3050")
    os.environ.setdefault("DB_PATH", "C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB")
    os.environ.setdefault("DB_USER", "sysdba")
    os.environ.setdefault("DB_PASSWORD", "masterkey")


def main() -> int:
    _apply_lab_env()
    if not (os.getenv("SQLACC_SDK_PASSWORD") or "").strip():
        print("FAIL: SQLACC_SDK_PASSWORD missing in environment / .env", flush=True)
        return 2
    if not _truthy("SQL_ACCOUNTING_BLOCK_REST_HTTP"):
        print("FAIL: BLOCK_REST_HTTP must be true for this lab", flush=True)
        return 2

    from api.adapters.sqlacc_session import get_sqlacc_session_manager
    from api.config import load_sql_accounting_api_settings
    from api.models import CustomerRequest
    from api.services.customer_payload import build_customer_create_payload
    from api.services.customer_write import build_customer_write_adapter

    # ACC-ANOZ AR_CUSTOMER.CODE is width 10 (e.g. 300-Y0001 = 9). Keep lab codes <= 10.
    stamp = time.strftime("%H%M%S")
    code = f"300-Z{stamp[-4:]}"  # e.g. 300-Z5914 (9 chars)
    req = CustomerRequest(
        code=code,
        company_name=f"EQ SDK LAB {stamp}",
        credit_term="30 Days",
        area="----",
        currency_code="----",
        address1="Lab Address 1",
        city="Klang",
        state="Selangor",
        country="MY",
        email=f"eq.lab.{stamp}@example.invalid",
    )
    payload = build_customer_create_payload(req)

    print(f"[LAB] Creating customer CODE={code} via Sdk on ACC-ANOZ…", flush=True)
    adapter = build_customer_write_adapter(load_sql_accounting_api_settings())
    try:
        response = adapter.create_customer(req, payload)
    except Exception as exc:
        print(f"FAIL: create_customer raised: {exc}", flush=True)
        return 1

    print(
        f"[LAB] Adapter OK saved={response.saved} code={response.code} "
        f"provider={getattr(response, 'write_provider', None)}",
        flush=True,
    )

    def _verify(app):
        ds = app.DBManager.NewDataSet(
            "SELECT FIRST 1 TRIM(CODE) AS CODE, TRIM(COMPANYNAME) AS COMPANYNAME, "
            "TRIM(CONTROLACCOUNT) AS CONTROLACCOUNT "
            f"FROM AR_CUSTOMER WHERE TRIM(CODE) = '{code.replace(chr(39), chr(39)+chr(39))}'"
        )
        if int(ds.RecordCount) <= 0:
            return None
        ds.First()
        fields = ds.Fields
        row = {}
        for i in range(int(fields.Count)):
            field = fields.Items(i)
            name = str(getattr(field, "FieldName", None) or f"F{i}")
            try:
                val = field.AsString
            except Exception:
                val = getattr(field, "value", "")
            row[name] = ("" if val is None else str(val)).strip()
        return row

    manager = get_sqlacc_session_manager()
    row = manager.run(_verify)
    if not row or (row.get("CODE") or "").strip().upper() != code.upper():
        print(f"FAIL: post-create Firebird/COM verify miss: {row!r}", flush=True)
        return 1

    print(
        f"PASS: CODE={row.get('CODE')} COMPANYNAME={row.get('COMPANYNAME')!r} "
        f"CONTROLACCOUNT={row.get('CONTROLACCOUNT')!r}",
        flush=True,
    )
    print(
        "NOTE: Lab customer left in ACC-ANOZ for inspection "
        f"(CODE={code}). Delete manually if needed.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
