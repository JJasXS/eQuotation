"""Verify quotation save currency matches SQL API GET /customer (not payload MYR)."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.quotation_api import _build_salesquotation_payload
from utils.sql_api_customer import sql_api_currency_and_code
from utils.tenant_bootstrap import apply_tenant_env_overrides

CUSTOMER = (sys.argv[1] if len(sys.argv) > 1 else "300-L0001").strip()


def main() -> int:
    apply_appsettings_to_environ()
    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
    apply_tenant_env_overrides()

    sql_fields = sql_api_currency_and_code(CUSTOMER)
    sql_cc = str(sql_fields.get("currencycode") or "").strip() or "----"
    print(f"SQL API GET /customer {CUSTOMER!r} -> currencycode={sql_cc!r}")

    data = {
        "companyName": "E2E TEST",
        "currencyCode": "MYR",
        "customerDetailCurrency": sql_cc,
        "currencyRate": "1.00",
        "customerScalars": {"currencycode": "MYR", "code": CUSTOMER},
        "items": [
            {
                "itemCode": "TEST",
                "description": "test",
                "quantity": 1,
                "unitPrice": 0,
                "taxCode": "",
            }
        ],
    }
    payload = _build_salesquotation_payload(CUSTOMER, data, doc_no="QT-E2E-CURRENCY")
    header_cc = str(payload.get("currencycode") or "").strip()
    print(f"/salesquotation payload currencycode={header_cc!r}")

    if header_cc != sql_cc:
        print(f"FAIL: payload {header_cc!r} != SQL API {sql_cc!r}")
        return 1
    if header_cc == "MYR" and sql_cc == "----":
        print("FAIL: payload fell back to MYR while SQL API has ----")
        return 2
    print("OK: save payload currency matches create-quotation SQL API source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
