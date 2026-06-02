"""Diagnose currency MYR vs ---- for jason.choo2004@gmail.com (login → customer → SQL API → SL_QT)."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.tenant_bootstrap import apply_tenant_env_overrides

EMAIL = (sys.argv[1] if len(sys.argv) > 1 else "jason.choo2004@gmail.com").strip().lower()


def main() -> int:
    apply_appsettings_to_environ()
    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
    apply_tenant_env_overrides()

    from utils import get_db_connection
    from utils.db_utils import set_db_config

    set_db_config(
        os.getenv("DB_PATH"),
        os.getenv("DB_USER") or "sysdba",
        os.getenv("DB_PASSWORD") or "masterkey",
        os.getenv("DB_HOST"),
    )
    from utils.quotation_api import _build_salesquotation_payload, _resolve_quotation_currency_code
    from utils.sql_api_customer import fetch_sql_api_customer_row, sql_api_currency_and_code

    print(f"=== Currency diagnose for login email: {EMAIL!r} ===\n")
    print(f"TENANT={os.getenv('TENANT_CODE')!r} DB_PATH={os.getenv('DB_PATH')!r}\n")

    con = get_db_connection()
    cur = con.cursor()

    # 1) Resolve customer code like auth (branch email, then UDF_EMAIL*)
    customer_code = None
    matched = None
    cur.execute(
        """
        SELECT CODE, EMAIL FROM AR_CUSTOMERBRANCH
        WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
        """,
        (EMAIL,),
    )
    row = cur.fetchone()
    if row:
        customer_code, matched = str(row[0]).strip(), "AR_CUSTOMERBRANCH.EMAIL"
    if not customer_code:
        cur.execute(
            """
            SELECT TRIM(RF.RDB$FIELD_NAME)
            FROM RDB$RELATION_FIELDS RF
            WHERE TRIM(RF.RDB$RELATION_NAME) = 'AR_CUSTOMER'
            """
        )
        cols = {str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]}
        udf_cols = sorted(
            c for c in cols if c == "UDF_EMAIL" or (c.startswith("UDF_EMAIL") and c[9:].isdigit())
        )

        def udf_sort(c: str) -> tuple:
            if c == "UDF_EMAIL":
                return (0, 0)
            suf = c[9:]
            return (1, int(suf) if suf.isdigit() else 999)

        for email_col in sorted(udf_cols, key=udf_sort):
            cur.execute(
                f"SELECT CODE FROM AR_CUSTOMER WHERE UPPER(TRIM({email_col})) = UPPER(TRIM(?))",
                (EMAIL,),
            )
            r2 = cur.fetchone()
            if r2 and r2[0]:
                customer_code = str(r2[0]).strip()
                matched = f"AR_CUSTOMER.{email_col}"
                break
    if not customer_code:
        cur.execute(
            "SELECT CODE FROM AR_CUSTOMER WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))",
            (EMAIL,),
        )
        r3 = cur.fetchone()
        if r3 and r3[0]:
            customer_code = str(r3[0]).strip()
            matched = "AR_CUSTOMER.EMAIL"

    print(f"1) Login lookup -> CODE={customer_code!r} via {matched!r}")
    if not customer_code:
        print("   FAIL: no AR_CUSTOMER match for this email")
        return 1

    # 2) Local AR_CUSTOMER master currency (Firebird — often MYR even when SQL API shows ----)
    ar_cc = None
    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS RF
        WHERE TRIM(RF.RDB$RELATION_NAME) = 'AR_CUSTOMER'
        """
    )
    ar_cols = {str(r[0]).strip().upper() for r in cur.fetchall() if r and r[0]}
    if "CURRENCYCODE" in ar_cols:
        cur.execute(
            "SELECT CURRENCYCODE, COMPANYNAME FROM AR_CUSTOMER WHERE CODE = ?",
            (customer_code,),
        )
        ar_row = cur.fetchone()
        if ar_row:
            ar_cc = str(ar_row[0] or "").strip()
            print(f"2) Local AR_CUSTOMER.CURRENCYCODE = {ar_cc!r}  company={ar_row[1]!r}")
    else:
        print("2) Local AR_CUSTOMER has no CURRENCYCODE column")

    # 3) SQL API GET /customer
    sql_row, sql_status = fetch_sql_api_customer_row(customer_code)
    sql_fields = sql_api_currency_and_code(customer_code)
    print(f"3) SQL API GET /customer HTTP status={sql_status!r}")
    print(f"   sql_api_currency_and_code = {sql_fields!r}")
    if sql_row:
        print(f"   row.currencycode = {sql_row.get('currencycode')!r}")

    # 4) Recent quotations in SL_QT for this customer
    cur.execute(
        """
        SELECT FIRST 8 DOCNO, DOCDATE, CURRENCYCODE, PROJECT, COMPANYNAME
        FROM SL_QT
        WHERE CODE = ?
        ORDER BY DOCDATE DESC, DOCKEY DESC
        """,
        (customer_code,),
    )
    qt_rows = cur.fetchall() or []
    print(f"\n4) Recent SL_QT for CODE={customer_code!r} (newest first):")
    if not qt_rows:
        print("   (no rows)")
    for r in qt_rows:
        print(
            f"   DOCNO={r[0]!r} DOCDATE={r[1]!r} CURRENCYCODE={r[2]!r} "
            f"PROJECT={r[3]!r} COMPANY={str(r[4] or '')[:40]!r}"
        )

    # 5) Payload eQuotation would send (with customerDetailCurrency = ---- as on create screen)
    display_cc = str(sql_fields.get("currencycode") or "").strip() or "----"
    data = {
        "companyName": "DIAG",
        "customerDetailCurrency": display_cc,
        "currencyCode": "MYR",
        "customerScalars": {"currencycode": "MYR", "code": customer_code},
        "items": [
            {
                "itemCode": "TEST",
                "description": "diag",
                "quantity": 1,
                "unitPrice": 0,
                "taxCode": "",
            }
        ],
    }
    resolved = _resolve_quotation_currency_code(data, customer_code)
    print(f"\n5) _resolve_quotation_currency_code (customerDetailCurrency={display_cc!r}) -> {resolved!r}")
    try:
        payload = _build_salesquotation_payload(customer_code, data, doc_no="QT-DIAG-00000")
        print(f"   POST /salesquotation header currencycode = {payload.get('currencycode')!r}")
        print(f"   project (often ---- in list) = {payload.get('project')!r}")
    except Exception as exc:
        print(f"   _build_salesquotation_payload error: {exc}")

    print("\n=== Interpretation ===")
    print(
        "- In SQL Accounting quotation lists, PROJECT='----' is NOT currency; CURRENCYCODE is the currency column."
    )
    if qt_rows and str(qt_rows[0][3] or "").strip() == "----" and str(qt_rows[0][2] or "").strip().upper() == "MYR":
        print(
            "- Your newest rows show PROJECT=---- and CURRENCYCODE=MYR (typical when customer currency is ----)."
        )
    if resolved == "----" and qt_rows and str(qt_rows[0][2] or "").strip().upper() == "MYR":
        print(
            "- eQuotation POST payload uses currencycode=---- but SL_QT stores MYR: SQL Accounting cloud"
            " rewrites placeholder ---- to company default MYR on save (not an eQuotation MYR fallback)."
        )
    if sql_status == 401:
        print(
            "- SQL API GET /customer returned 401 from this machine; fix tenant sqlApi keys / restart server"
            " so create-quotation can read currency from API. Local AR_CUSTOMER.CURRENCYCODE is still shown above."
        )
    if ar_cc == "----":
        print(f"- Local customer master AR_CUSTOMER.CURRENCYCODE is already {ar_cc!r} (matches create screen).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
