"""One-off: TLS + optional SigV4 POST smoke test to SQL Accounting API (api.sql.my)."""
from __future__ import annotations

import logging
import os
import sys

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

# Repo root
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))


def main() -> int:
    host = (os.getenv("SQL_API_HOST") or "api.sql.my").strip().rstrip("/")
    base = f"https://{host}" if os.getenv("SQL_API_USE_TLS", "true").lower() in ("1", "true", "yes") else f"http://{host}"

    print(f"1) TLS reachability: GET {base}/ (no SigV4)", flush=True)
    try:
        r = requests.get(f"{base}/", timeout=(5.0, 15.0), allow_redirects=True)
        print(f"   HTTP {r.status_code}, body_len={len(r.text or '')}", flush=True)
        if r.status_code == 502:
            print(
                "   NOTE: 502 = gateway reached you but upstream (origin) failed or is overloaded.",
                flush=True,
            )
    except requests.exceptions.RequestException as e:
        print(f"   FAIL: {type(e).__name__}: {e}", flush=True)
        return 1

    print(
        "2) SigV4 POST smoke (minimal JSON — expect 4xx from validation if API is healthy)",
        flush=True,
    )
    try:
        from api.clients.sql_accounting_client import SqlAccountingApiClient
        from api.config.sql_accounting_api import load_sql_accounting_api_settings

        settings = load_sql_accounting_api_settings()
        if not settings.access_key or not settings.secret_key:
            print("   SKIP: SQL_API_ACCESS_KEY / SQL_API_SECRET_KEY not set", flush=True)
            return 0

        client = SqlAccountingApiClient(settings)
        url = settings.resolved_create_url()
        post_timeout = min(25.0, float(settings.timeout_seconds) + 8.0)
        status, parsed, raw = client.post_json(url, {}, timeout_seconds=post_timeout)
        snippet = (raw or "")[:500].replace("\n", " ")
        print(f"   POST {url}", flush=True)
        print(f"   HTTP {status}, parsed_keys={list(parsed.keys()) if isinstance(parsed, dict) else None}", flush=True)
        print(f"   body_snippet={snippet!r}", flush=True)
        if status == 0 or status is None:
            return 1
        # Any HTTP response means we connected and got a reply (even 403/400).
        print("   OK: received an HTTP response from api.sql.my (API is reachable).", flush=True)
        return 0
    except Exception as e:
        print(f"   FAIL: {type(e).__name__}: {e}", flush=True)
        if "Read timed out" in str(e) or "ReadTimeout" in str(e):
            print(
                "   NOTE: Read timeout = TCP worked but origin did not finish the response in time.",
                flush=True,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
