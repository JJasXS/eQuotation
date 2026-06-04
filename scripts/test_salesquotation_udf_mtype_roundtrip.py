"""
Live round-trip: POST /salesquotation with udf_mtype on line, then verify API + SL_QTDTL.

Usage (repo root, .env with SQL_API_* and DB_PATH):
  .venv\\Scripts\\python.exe scripts/test_salesquotation_udf_mtype_roundtrip.py
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    repo = env_path.parent
    sys.path.insert(0, str(repo))
    from utils.appsettings_env import apply_appsettings_to_environ

    apply_appsettings_to_environ(project_root=repo)
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _pick_customer() -> str:
    import fdb

    from utils.db_utils import build_firebird_dsn

    db_path = (os.getenv("DB_PATH") or "").strip()
    db_host = (os.getenv("DB_HOST") or "").strip()
    if not db_path:
        raise SystemExit("DB_PATH required")
    dsn = build_firebird_dsn(db_path, db_host or None)
    con = fdb.connect(
        dsn=dsn,
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
        charset="UTF8",
    )
    cur = con.cursor()
    cur.execute(
        "SELECT FIRST 1 TRIM(CODE) FROM AR_CUSTOMER WHERE TRIM(COALESCE(CODE,''))<>'' ORDER BY CODE"
    )
    cr = cur.fetchone()
    cur.close()
    con.close()
    if not cr or not cr[0]:
        raise SystemExit("No customer")
    return str(cr[0]).strip()


def _collect_stocks_with_mtype(max_scan: int = 500) -> list[tuple[str, str, str]]:
    from utils.stock_items_catalog import (
        _try_fetch_stock_items_sql_api,
        fetch_stock_item_sql_api_by_code,
    )

    rows = _try_fetch_stock_items_sql_api() or []
    out: list[tuple[str, str, str]] = []
    for row in rows[:max_scan]:
        if not isinstance(row, dict):
            continue
        code = str(row.get("CODE") or row.get("code") or "").strip()
        if not code:
            continue
        mtype = str(row.get("UDF_MTYPE") or row.get("udf_mtype") or "").strip()
        if not mtype:
            detail = fetch_stock_item_sql_api_by_code(code)
            if detail:
                mtype = str(detail.get("UDF_MTYPE") or detail.get("udf_mtype") or "").strip()
        if mtype:
            desc = str(row.get("DESCRIPTION") or row.get("description") or code).strip()
            out.append((code, desc, mtype))
    return out


def _pick_stock_with_mtype_from_sql_api() -> tuple[str, str, str] | None:
    forced = (os.getenv("MTYPE_TEST_ITEM_CODE") or "").strip()
    hits = _collect_stocks_with_mtype()
    if forced:
        for code, desc, mtype in hits:
            if code.upper() == forced.upper():
                return code, desc, mtype
        from utils.stock_items_catalog import fetch_stock_item_sql_api_by_code

        detail = fetch_stock_item_sql_api_by_code(forced)
        if detail:
            mtype = str(detail.get("UDF_MTYPE") or detail.get("udf_mtype") or "").strip()
            if mtype:
                desc = str(detail.get("DESCRIPTION") or detail.get("description") or forced).strip()
                return forced, desc, mtype
        return None
    return hits[0] if hits else None


def _pick_from_firebird_mtype() -> tuple[str, str, str] | None:
    import fdb
    from utils.db_utils import build_firebird_dsn

    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        return None
    forced = (os.getenv("MTYPE_TEST_ITEM_CODE") or "").strip()
    dsn = build_firebird_dsn(db_path, (os.getenv("DB_HOST") or "").strip() or None)
    con = fdb.connect(
        dsn=dsn,
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
        charset="UTF8",
    )
    cur = con.cursor()
    if forced:
        cur.execute(
            """
            SELECT TRIM(CODE), TRIM(COALESCE(DESCRIPTION, '')),
                   TRIM(COALESCE(UDF_MTYPE, ''))
            FROM ST_ITEM
            WHERE TRIM(CODE) = ?
              AND TRIM(COALESCE(UDF_MTYPE, '')) <> ''
            """,
            (forced,),
        )
    else:
        cur.execute(
            """
            SELECT FIRST 1 TRIM(CODE), TRIM(COALESCE(DESCRIPTION, '')),
                   TRIM(COALESCE(UDF_MTYPE, ''))
            FROM ST_ITEM
            WHERE TRIM(COALESCE(CODE, '')) <> ''
              AND TRIM(COALESCE(UDF_MTYPE, '')) <> ''
            ORDER BY CODE
            """
        )
    row = cur.fetchone()
    cur.close()
    con.close()
    if not row or not row[0] or not row[2]:
        return None
    return str(row[0]).strip(), str(row[1] or row[0]).strip(), str(row[2]).strip()


def _pick_customer_and_item_with_mtype() -> tuple[str, str, str, str]:
    cust = _pick_customer()
    hit = _pick_stock_with_mtype_from_sql_api()
    if not hit:
        hit = _pick_from_firebird_mtype()
        if hit:
            print("[pick] using Firebird ST_ITEM.UDF_MTYPE (SQL API list/detail had no mtype)", flush=True)
    if hit:
        code, desc, mtype = hit
        return cust, code, desc, mtype
    raise SystemExit(
        "No stock item with udf_mtype. Run scripts/find_stock_items_with_mtype.py "
        "or set MTYPE_TEST_ITEM_CODE to a code with UDF_MTYPE."
    )


def main() -> int:
    _load_dotenv()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_tenant_env_overrides()

    from utils.db_utils import set_db_config

    set_db_config(
        os.getenv("DB_PATH"),
        os.getenv("DB_USER") or "sysdba",
        os.getenv("DB_PASSWORD") or "masterkey",
        os.getenv("DB_HOST"),
    )

    from api.clients import SqlAccountingApiClient, SqlAccountingApiError
    from api.config import load_sql_accounting_api_settings
    import utils.quotation_api as qa

    hits = _collect_stocks_with_mtype()
    print(f"[scan] {len(hits)} stock item(s) with udf_mtype in SQL API")
    for code, desc, mtype in hits[:10]:
        print(f"  - {code!r} mtype={mtype!r} desc={desc[:50]!r}")
    if len(hits) > 10:
        print(f"  ... +{len(hits) - 10} more")

    cust, code, desc, expected_mtype = _pick_customer_and_item_with_mtype()
    print(f"[pick] customer={cust!r} item={code!r} mtype={expected_mtype!r}")

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

    doc_no = f"QT-{random.randint(86000, 86999):05d}"
    data = {
        "description": "eQuotation mtype roundtrip test",
        "items": [
            {
                "product": desc,
                "qty": 1,
                "price": "1.00",
                "discount": 0,
            }
        ],
        "companyName": "API Mtype Test",
        "address1": "Addr1",
        "currencyCode": "MYR",
    }
    payload = qa._build_salesquotation_payload(cust, data, doc_no=doc_no)
    row = (payload.get("sdsdocdetail") or [{}])[0]
    built_mtype = str(row.get("udf_mtype") or "").strip()
    print(f"[build] itemcode={row.get('itemcode')!r} udf_mtype={built_mtype!r}")
    if built_mtype.upper() != expected_mtype.upper():
        print("FAIL: payload build missing udf_mtype (expected from catalog/ST_ITEM)")
        return 1

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
        print("[POST] no dockey:", json.dumps(parsed, indent=2)[:800])
        return 1
    print("[POST] dockey=", dockey, "docno=", doc_no)

    get_url = f"{base}/{dockey}"
    st, gp, _graw = client.get_json(get_url, timeout_seconds=30.0)
    print("[GET ] HTTP", st, get_url)
    if st >= 400:
        return 1
    gh = (gp or {}).get("data") or gp
    if isinstance(gh, list) and gh:
        gh = gh[0]
    lines = (gh or {}).get("sdsdocdetail") or []
    if not lines:
        print("FAIL: GET has no detail lines")
        return 1
    line0 = lines[0]
    api_mtype = str(
        line0.get("udf_mtype")
        or line0.get("udfMtype")
        or line0.get("UDF_MTYPE")
        or ""
    ).strip()
    print(f"[get ] udf_mtype={api_mtype!r}")
    if api_mtype.upper() != expected_mtype.upper():
        print("FAIL: GET line udf_mtype mismatch")
        return 2

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
        try:
            cur.execute(
                """
                SELECT TRIM(COALESCE(UDF_MTYPE,''))
                FROM SL_QTDTL WHERE DOCKEY=? ORDER BY SEQ
                """,
                (dockey,),
            )
            fb_rows = cur.fetchall()
            print("[FB  ] SL_QTDTL UDF_MTYPE:", fb_rows)
            if fb_rows and str(fb_rows[0][0] or "").strip().upper() != expected_mtype.upper():
                print("FAIL: Firebird SL_QTDTL.UDF_MTYPE mismatch")
                return 2
        except Exception as e:
            print("[FB  ] UDF_MTYPE check skipped:", e)
        cur.close()
        con.close()

    print("OK: udf_mtype roundtrip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
