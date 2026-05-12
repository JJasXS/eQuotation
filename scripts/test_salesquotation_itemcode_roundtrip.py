"""
Live round-trip: POST /salesquotation then GET by dockey and verify SL_QTDTL.ITEMCODE in API + local DB.

Usage (from repo root, .env with SQL_API_* and DB_PATH):
  .venv\\Scripts\\python.exe scripts/test_salesquotation_itemcode_roundtrip.py

Uses ACC-TEST.FDB (or your DB_PATH) to pick a real customer + stock code, then posts minimal quotation.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _pick_customer_and_item() -> tuple[str, str, str]:
    import fdb

    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        raise SystemExit("DB_PATH required to pick customer/item")
    user = (os.getenv("DB_USER") or "sysdba").strip()
    pw = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    con = fdb.connect(dsn=db_path, user=user, password=pw, charset="UTF8")
    cur = con.cursor()
    cur.execute(
        "SELECT FIRST 1 TRIM(CODE) FROM AR_CUSTOMER WHERE TRIM(COALESCE(CODE,''))<>'' ORDER BY CODE"
    )
    cr = cur.fetchone()
    if not cr or not cr[0]:
        raise SystemExit("No AR_CUSTOMER.CODE in DB")
    cust = str(cr[0]).strip()

    cur.execute(
        """
        SELECT FIRST 1 TRIM(i.CODE), TRIM(COALESCE(i.DESCRIPTION, ''))
        FROM ST_ITEM i
        WHERE EXISTS (
            SELECT 1 FROM ST_ITEM_UOM u WHERE TRIM(u.CODE) = TRIM(i.CODE)
        )
          AND TRIM(COALESCE(i.CODE, '')) <> ''
          AND TRIM(i.CODE) SIMILAR TO '[A-Za-z]%'
        ORDER BY i.CODE
        """
    )
    ir = cur.fetchone()
    if not ir or not ir[0]:
        raise SystemExit("No suitable ST_ITEM.CODE in DB")
    code, desc = str(ir[0]).strip(), str(ir[1] or ir[0]).strip()

    cur.close()
    con.close()
    return cust, code, desc


def main() -> int:
    _load_dotenv()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    from api.clients import SqlAccountingApiClient, SqlAccountingApiError
    from api.config import load_sql_accounting_api_settings
    import utils.quotation_api as qa

    cust, item_code, item_desc = _pick_customer_and_item()
    print("[pick] customer=", cust, "item=", repr(item_code), "desc=", repr(item_desc))

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        raise SystemExit("SQL_API_ACCESS_KEY / SQL_API_SECRET_KEY required")

    client = SqlAccountingApiClient(settings)
    scheme = "https" if settings.use_tls else "http"
    host = settings.host.strip().rstrip("/")
    qpath = (settings.quotation_create_path or "/salesquotation").strip()
    if not qpath.startswith("/"):
        qpath = "/" + qpath
    base = f"{scheme}://{host}{qpath}"

    # Unique docno in app range
    doc_no = f"QT-{random.randint(85000, 89999):05d}"

    data = {
        "items": [
            {
                "product": item_desc,
                "itemCode": item_code,
                "qty": 1,
                "price": "10.00",
                "discount": 0,
                "deliveryDate": None,
            }
        ],
        "companyName": "API Itemcode Test",
        "address1": "Addr1",
        "address2": "",
        "currencyCode": "MYR",
    }

    payload = qa._build_salesquotation_payload(cust, data, doc_no=doc_no)
    d0 = (payload.get("sdsdocdetail") or [{}])[0]
    print("[build] line0 itemcode=", repr(d0.get("itemcode")), "seq=", d0.get("seq"))

    post_url = settings.resolved_quotation_create_url()
    try:
        status, parsed, raw = client.post_json(post_url, payload, timeout_seconds=90.0)
    except SqlAccountingApiError as e:
        print("[POST] transport error:", e)
        return 1

    print("[POST] HTTP", status, "raw[:400]=", (raw or "")[:400])
    if status >= 400:
        return 1

    dockey = 0
    if isinstance(parsed, dict):
        dockey = int(parsed.get("dockey") or 0)
        d2 = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
        dockey = int(dockey or d2.get("dockey") or d2.get("docKey") or 0)

    if not dockey:
        print("[POST] no dockey in response:", json.dumps(parsed, indent=2)[:800])
        return 1

    print("[POST] dockey=", dockey, "docno=", doc_no)

    get_url = f"{base}/{dockey}"
    st, gp, graw = client.get_json(get_url, timeout_seconds=30.0)
    print("[GET ] HTTP", st, get_url)
    if st >= 400:
        return 1
    gh = (gp or {}).get("data") or gp
    if isinstance(gh, list) and gh:
        gh = gh[0]
    lines = (gh or {}).get("sdsdocdetail") or []
    if lines:
        x = lines[0]
        print(
            "[GET ] line0 itemcode=", repr(x.get("itemcode")),
            "number=", repr(x.get("number")),
            "companyitemcode=", repr(x.get("companyitemcode")),
        )

    # Local Firebird truth
    db_path = (os.getenv("DB_PATH") or "").strip()
    if db_path:
        import fdb

        con = fdb.connect(
            dsn=db_path,
            user=(os.getenv("DB_USER") or "sysdba").strip(),
            password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
            charset="UTF8",
        )
        cur = con.cursor()
        cur.execute(
            "SELECT SEQ, TRIM(COALESCE(ITEMCODE,'')), TRIM(COALESCE(NUMBER,'')), DESCRIPTION FROM SL_QTDTL WHERE DOCKEY=? ORDER BY SEQ",
            (dockey,),
        )
        rows = cur.fetchall()
        print("[FB  ] SL_QTDTL rows:", rows)
        cur.close()
        con.close()
        ok = bool(rows and (rows[0][1] or "").strip() == item_code)
        if ok:
            print("OK: SL_QTDTL.ITEMCODE persisted as", item_code)
            return 0
        print("FAIL: SL_QTDTL.ITEMCODE not persisted")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
