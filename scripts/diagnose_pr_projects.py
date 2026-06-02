#!/usr/bin/env python3
"""Diagnose procurement project dropdown data source."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from utils.appsettings_env import apply_appsettings_to_environ
from utils.tenant_bootstrap import apply_tenant_env_overrides

apply_appsettings_to_environ(project_root=ROOT)
load_dotenv(ROOT / ".env", override=False)
apply_tenant_env_overrides()


def main() -> int:
    print("=== eQuotation PR projects diagnostic ===\n")
    print("PROJECT_CODE_FALLBACK env:", repr(os.getenv("PROJECT_CODE_FALLBACK")))
    print("SQL_API_PROJECT_LIST_PATH env:", repr(os.getenv("SQL_API_PROJECT_LIST_PATH")))
    print("TENANT_CODE env:", repr(os.getenv("TENANT_CODE")))

    from api.config import load_sql_accounting_api_settings

    settings = load_sql_accounting_api_settings()
    print("\nSQL API configured:", bool(settings.access_key and settings.secret_key))
    print("SQL API host:", settings.host)
    path = os.getenv("SQL_API_PROJECT_LIST_PATH") or "/project/*"
    print("Project list path:", path)
    if settings.access_key:
        print("Project list URL:", settings.resolved_list_get_url(path))

    from utils.sql_api_projects import SqlApiProjectsError, fetch_projects_from_sql_api

    print("\n--- fetch_projects_from_sql_api() ---")
    try:
        rows = fetch_projects_from_sql_api()
        codes = [r.get("code") for r in rows]
        print("OK:", len(rows), "row(s)")
        print("codes:", codes)
        print("sample:", json.dumps(rows[:3], indent=2))
        if any(str(c).startswith("P") and str(c)[1:].isdigit() for c in codes):
            print("WARNING: P1-P5 style codes came from SQL API response itself")
    except SqlApiProjectsError as exc:
        print("FAILED:", exc)
        return 1

    print("\n--- main._fetch_procurement_projects_uncached() ---")
    from main import _fetch_procurement_projects_uncached, _load_projects_from_env_fallback

    uncached = _fetch_procurement_projects_uncached()
    print("uncached codes:", [r.get("code") for r in uncached])
    env_fb = _load_projects_from_env_fallback()
    print("env fallback (should NOT be used by API):", [r.get("code") for r in env_fb])

    from utils.ttl_cache import sql_api_master_cache

    sql_api_master_cache.invalidate(("procurement", "projects", "v3_sqlapi_project_star_only"))
    sql_api_master_cache.invalidate(("procurement", "projects", "v2"))

    print("\n--- Flask test client (if app loads) ---")
    try:
        from main import app

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_email"] = "admin@test.local"
                sess["role"] = "admin"
            resp = client.get("/api/admin/procurement/projects")
            print("HTTP", resp.status_code)
            body = resp.get_json() or {}
            print("success:", body.get("success"), "source:", body.get("source"))
            data = body.get("data") or []
            print("data codes:", [d.get("code") for d in data if isinstance(d, dict)])
            if not body.get("success"):
                print("error:", body.get("error"))
    except Exception as exc:
        print("Flask test skipped:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
