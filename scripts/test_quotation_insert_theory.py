#!/usr/bin/env python3
"""
Theoretical checks for quotation creation (payload + optional Firebird + optional SigV4 ping).

Does NOT create a quotation unless you pass --live-salesquotation (explicit; may create real data).

Usage (from repo root):
  .venv\\Scripts\\python.exe scripts/test_quotation_insert_theory.py
  .venv\\Scripts\\python.exe scripts/test_quotation_insert_theory.py --firebird-docno
  .venv\\Scripts\\python.exe scripts/test_quotation_insert_theory.py --sigv4-smoke
  .venv\\Scripts\\python.exe scripts/test_quotation_insert_theory.py --live-salesquotation
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.chdir(_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(_ROOT, ".env"))


def _sample_quotation_data(*, item_code: str) -> dict:
    return {
        "companyName": "Theory Test Co",
        "address1": "1 Test St",
        "phone1": "000",
        "validUntil": "2099-12-31",
        "currencyCode": "MYR",
        "items": [
            {
                "product": "Theory line A",
                "itemCode": item_code,
                "qty": 1,
                "price": 10.0,
                "discount": 0,
                "deliveryDate": "2099-01-01",
            },
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate quotation insert path (theory + optional live checks).")
    ap.add_argument(
        "--customer",
        default=(os.getenv("QUOTATION_TEST_CUSTOMER_CODE") or "").strip() or "TEST",
        help="Customer CODE for payload (default: env QUOTATION_TEST_CUSTOMER_CODE or TEST).",
    )
    ap.add_argument(
        "--item-code",
        default=(os.getenv("QUOTATION_TEST_ITEM_CODE") or "THEORY-ITEM").strip(),
        help="Sample ST_ITEM.CODE for the line (default: env QUOTATION_TEST_ITEM_CODE or THEORY-ITEM).",
    )
    ap.add_argument("--firebird-docno", action="store_true", help="Read SL_QT DOCNO patterns from Firebird.")
    ap.add_argument(
        "--sigv4-smoke",
        action="store_true",
        help="Signed POST {} to SQL_API customer path (validates keys/region/service; not a quotation).",
    )
    ap.add_argument(
        "--live-salesquotation",
        action="store_true",
        help="DANGER: actually POST /salesquotation once (may create a real quotation in SQL Accounting).",
    )
    args = ap.parse_args()

    print("=== 1) Build salesquotation JSON payload (local, no network) ===")
    from utils import quotation_api as qa

    customer = args.customer
    data = _sample_quotation_data(item_code=args.item_code)
    doc_no = "QT-00001"
    max_seq, existing = qa._read_qt_sequences_from_db(limit=50)
    if max_seq or existing:
        cand = qa._next_qt_docno_candidate(max_seq, existing, 0)
        if cand:
            doc_no = cand
    print(f"   Using doc_no={doc_no!r} (from Firebird scan if DB_PATH set, else placeholder)")

    payload = qa._build_salesquotation_payload(customer, data, doc_no=doc_no)
    details = payload.get("sdsdocdetail") or []
    if not details:
        print("FAIL: sdsdocdetail is empty (no line rows).")
        return 1
    row0 = details[0]
    ic = row0.get("itemcode") or row0.get("ITEMCODE")
    print(f"   Header code={payload.get('code')!r} docno={payload.get('docno')!r}")
    print(f"   Line[0] itemcode={ic!r} description={row0.get('description')!r}")
    print(f"   companyitemcode={row0.get('companyitemcode')!r}")
    if not str(ic or "").strip():
        print("WARN: itemcode is blank — real API may be slow or reject; set --item-code or QUOTATION_TEST_ITEM_CODE.")

    try:
        raw = json.dumps(payload, ensure_ascii=False)
    except TypeError as e:
        print(f"FAIL: payload is not JSON-serializable: {e}")
        return 1
    print(f"   JSON serializable OK, byte_len={len(raw.encode('utf-8'))}")

    if args.firebird_docno:
        print("\n=== 2) Firebird SL_QT DOCNO scan ===")
        mx, ex = qa._read_qt_sequences_from_db(limit=200)
        print(f"   max_seq={mx}, sample_existing_count={len(ex)}")

    if args.sigv4_smoke:
        print("\n=== 3) SigV4 smoke POST /customer (empty JSON) ===")
        from api.clients.sql_accounting_client import SqlAccountingApiClient, SqlAccountingApiError
        from api.config.sql_accounting_api import load_sql_accounting_api_settings

        settings = load_sql_accounting_api_settings()
        if not settings.access_key:
            print("   SKIP: no SQL_API_ACCESS_KEY")
        else:
            client = SqlAccountingApiClient(settings)
            url = settings.resolved_create_url()
            print(f"   POST {url!r} timeout=15s")
            try:
                status, parsed, text = client.post_json(url, {}, timeout_seconds=15.0)
                print(f"   HTTP {status}, body_prefix={text[:200]!r}")
            except SqlAccountingApiError as e:
                print(f"   transport_error: {e}")

    if args.live_salesquotation:
        print("\n=== 4) LIVE POST /salesquotation (one attempt) ===")
        from api.clients.sql_accounting_client import SqlAccountingApiClient, SqlAccountingApiError
        from api.config.sql_accounting_api import load_sql_accounting_api_settings

        settings = load_sql_accounting_api_settings()
        client = SqlAccountingApiClient(settings)
        url = settings.resolved_quotation_create_url()
        timeout = float(
            os.getenv("SQL_API_QUOTATION_TIMEOUT_SECONDS") or settings.timeout_seconds
        )
        print(f"   POST {url!r} timeout={timeout}s")
        try:
            status, parsed, text = client.post_json(
                url,
                payload,
                timeout_seconds=timeout,
            )
            print(f"   HTTP {status}")
            print(f"   parsed={repr(parsed)[:800]}")
            if status >= 400:
                print(f"   raw_prefix={text[:400]!r}")
        except SqlAccountingApiError as e:
            print(f"   FAILED: {e}")
            return 1

    print("\nOK: theoretical payload path is consistent. Use --live-salesquotation only if you intend to create data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
