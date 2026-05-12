"""
Verify TENANT_CODE-only bootstrap: Dynamo + Secrets Manager populate env (no keys in .env).

Clears SQL/OpenAI/API/SMTP password from the environment first so a parent shell cannot mask SM.

Usage (from repo root, AWS credentials configured, .env containing only TENANT_CODE=TNT10004):

  python scripts/test_tenant_aws_retrieval.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _strip_credential_env() -> None:
    # Prior shell may have left skip-SM on; this test expects real Secrets Manager reads.
    os.environ.pop("TENANT_BOOTSTRAP_SKIP_SECRETS", None)
    for k in (
        "SQL_API_ACCESS_KEY",
        "SQL_API_SECRET_KEY",
        "OPENAI_API_KEY",
        "API_ACCESS_KEY",
        "API_SECRET_KEY",
        "SMTP_PASSWORD",
    ):
        os.environ.pop(k, None)


def _redact(val: str | None) -> str:
    if not val:
        return "(empty)"
    s = val.strip()
    if len(s) <= 10:
        return "***"
    return f"{s[:4]}…{s[-4:]} (len={len(s)})"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)

    _strip_credential_env()

    from dotenv import load_dotenv

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ(project_root=root)
    load_dotenv(root / ".env", override=False)

    if not (os.getenv("TENANT_CODE") or os.getenv("TenantBootstrap__TenantCode") or "").strip():
        print("Set TENANT_CODE in .env first.", flush=True)
        return 1

    apply_tenant_env_overrides()

    print("--- After bootstrap (redacted) ---", flush=True)
    print("DB_HOST     ", os.getenv("DB_HOST"), flush=True)
    print("DB_PATH     ", os.getenv("DB_PATH"), flush=True)
    print("SQL_ACCESS  ", _redact(os.getenv("SQL_API_ACCESS_KEY")), flush=True)
    print("SQL_SECRET  ", _redact(os.getenv("SQL_API_SECRET_KEY")), flush=True)
    print("OPENAI_KEY  ", _redact(os.getenv("OPENAI_API_KEY")), flush=True)
    print("OPENAI_MODEL", os.getenv("OPENAI_MODEL"), flush=True)
    print("API_ACCESS  ", _redact(os.getenv("API_ACCESS_KEY")), flush=True)
    print("SMTP_SERVER ", os.getenv("SMTP_SERVER"), flush=True)
    print("SMTP_EMAIL  ", os.getenv("SMTP_EMAIL"), flush=True)
    print("SMTP_PASS   ", _redact(os.getenv("SMTP_PASSWORD")), flush=True)

    ok = (
        (os.getenv("SQL_API_ACCESS_KEY") or "").strip()
        and (os.getenv("SQL_API_SECRET_KEY") or "").strip()
        and (os.getenv("OPENAI_API_KEY") or "").strip()
        and (os.getenv("OPENAI_MODEL") or "").strip()
    )
    if not ok:
        print("FAIL: missing SQL keys and/or OpenAI key+model from Secrets Manager.", flush=True)
        return 1
    print("OK: SQL + OpenAI populated from AWS.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
