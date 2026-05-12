"""
Smoke test for TENANT_CODE + appsettings.json + AWS Secrets Manager.

  cd eQuotation
  set TENANT_CODE=TNT10004
  python scripts/tenant_smoke_test.py

Optional:
  --no-openai       Skip one chat.completions call
  --no-firebird     Skip fdb.connect
  --post-quotation  Live POST /salesquotation (creates data; uses create_or_update_quotation)

Requires: appsettings.json, IAM or credentials for Secrets Manager, reachable tenant API,
  and secrets referenced by the tenant (e.g. proacc/shared/openai, proacc/tenant/.../sqlApiCredentials).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _bootstrap_env() -> None:
    root = _repo_root()
    sys.path.insert(0, str(root))
    os.chdir(root)

    from dotenv import load_dotenv

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)
    apply_tenant_env_overrides()


def _test_openai() -> None:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    if not key or key.startswith("unset-"):
        raise SystemExit("OPENAI_API_KEY missing after tenant bootstrap")
    from openai import OpenAI

    client = OpenAI(api_key=key)
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        max_tokens=8,
    )
    text = (r.choices[0].message.content or "").strip()
    print(f"[openai] model={model!r} reply={text!r}", flush=True)


def _test_firebird() -> None:
    import fdb

    from utils.db_utils import build_firebird_dsn

    db_path = (os.getenv("DB_PATH") or "").strip()
    db_host = (os.getenv("DB_HOST") or "").strip()
    if not db_path:
        raise SystemExit("DB_PATH missing after tenant bootstrap")
    user = (os.getenv("DB_USER") or "sysdba").strip()
    pw = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    dsn = build_firebird_dsn(db_path, db_host or None)
    con = fdb.connect(dsn=dsn, user=user, password=pw, charset="UTF8")
    con.close()
    print("[firebird] connect OK", flush=True)


def _test_quotation_config() -> None:
    from api.config import load_sql_accounting_api_settings

    s = load_sql_accounting_api_settings()
    if not s.access_key or not s.secret_key:
        raise SystemExit("SQL API keys missing after tenant bootstrap")
    url = s.resolved_quotation_create_url()
    print(f"[quotation] POST target {url!r} dry_run={s.dry_run}", flush=True)


def _test_quotation_post() -> None:
    import random

    import fdb

    from utils.db_utils import build_firebird_dsn
    from utils import create_or_update_quotation

    db_path = (os.getenv("DB_PATH") or "").strip()
    db_host = (os.getenv("DB_HOST") or "").strip()
    user = (os.getenv("DB_USER") or "sysdba").strip()
    pw = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    dsn = build_firebird_dsn(db_path, db_host or None)
    con = fdb.connect(dsn=dsn, user=user, password=pw, charset="UTF8")
    cur = con.cursor()
    cur.execute(
        "SELECT FIRST 1 TRIM(CODE) FROM AR_CUSTOMER WHERE TRIM(COALESCE(CODE,''))<>'' ORDER BY CODE"
    )
    cr = cur.fetchone()
    if not cr or not cr[0]:
        cur.close()
        con.close()
        raise SystemExit("No AR_CUSTOMER.CODE")
    cust = str(cr[0]).strip()
    cur.execute(
        """
        SELECT FIRST 1 TRIM(i.CODE), TRIM(COALESCE(i.DESCRIPTION, ''))
        FROM ST_ITEM i
        WHERE EXISTS (SELECT 1 FROM ST_ITEM_UOM u WHERE TRIM(u.CODE) = TRIM(i.CODE))
          AND TRIM(COALESCE(i.CODE, '')) <> ''
        ORDER BY i.CODE
        """
    )
    ir = cur.fetchone()
    cur.close()
    con.close()
    if not ir or not ir[0]:
        raise SystemExit("No ST_ITEM")
    item_code, item_desc = str(ir[0]).strip(), str(ir[1] or ir[0]).strip()
    doc_no = f"QT-{random.randint(85000, 89999):05d}"
    data = {
        "items": [{"product": item_desc, "itemcode": item_code, "quantity": 1, "unitPrice": 1.0}],
        "companyName": "SmokeTest",
    }
    base = (os.getenv("BASE_API_URL") or "http://localhost:8080").rstrip("/")
    out = create_or_update_quotation(base, cust, data)
    if not out.get("success"):
        raise SystemExit(f"quotation failed: {out}")
    print(f"[quotation] created docno={out.get('docno')!r} dockey={out.get('dockey')!r}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-openai", action="store_true")
    ap.add_argument("--no-firebird", action="store_true")
    ap.add_argument("--post-quotation", action="store_true", help="Live salesquotation POST (creates data)")
    args = ap.parse_args()

    if not (os.getenv("TENANT_CODE") or os.getenv("TenantBootstrap__TenantCode") or "").strip():
        print("Set TENANT_CODE (e.g. in .env) before running.", flush=True)
        return 1

    _bootstrap_env()

    code = (os.getenv("TENANT_CODE") or "").strip()
    print(f"[bootstrap] tenant={code!r}", flush=True)

    _test_quotation_config()
    if not args.no_firebird:
        _test_firebird()
    if not args.no_openai:
        _test_openai()
    if args.post_quotation:
        _test_quotation_post()

    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
