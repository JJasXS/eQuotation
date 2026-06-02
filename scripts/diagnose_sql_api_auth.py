"""Print SQL API env summary and probe GET /customer (no secrets in output)."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
from urllib.parse import quote

import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from utils.appsettings_env import apply_appsettings_to_environ
from utils.sql_api_sigv4 import resolve_sql_api_sigv4_service
from utils.tenant_bootstrap import apply_tenant_env_overrides


def main() -> int:
    apply_appsettings_to_environ()
    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
    apply_tenant_env_overrides()

    tenant = (os.getenv("TENANT_CODE") or "").strip()
    ak = (os.getenv("SQL_API_ACCESS_KEY") or "").strip()
    sk = (os.getenv("SQL_API_SECRET_KEY") or "").strip()
    host = (os.getenv("SQL_API_HOST") or "").strip()
    region = (os.getenv("SQL_API_REGION") or "").strip()
    service = resolve_sql_api_sigv4_service(host, os.getenv("SQL_API_SERVICE"))
    os.environ["SQL_API_SERVICE"] = service
    use_tls = (os.getenv("SQL_API_USE_TLS", "true") or "").strip().lower() in ("1", "true", "yes", "on")

    print(f"tenant={tenant!r}")
    print(f"SQL_API_HOST={host!r}")
    print(f"SQL_API_REGION={region!r}")
    print(f"SQL_API_SERVICE={service!r}")
    print(f"has_SQL_API_ACCESS_KEY={bool(ak)} access_key_len={len(ak)}")
    print(f"has_SQL_API_SECRET_KEY={bool(sk)} secret_key_len={len(sk)}")

    if not ak or not sk:
        print("FAIL: SQL API keys missing after tenant bootstrap.")
        return 1

    code = (sys.argv[1] if len(sys.argv) > 1 else "300-L0001").strip()
    scheme = "https" if use_tls else "http"
    url = f"{scheme}://{host.rstrip('/')}/customer?code={quote(code)}"
    creds = Credentials(ak, sk)
    aws_req = AWSRequest(method="GET", url=url, headers={"Accept": "application/json"})
    SigV4Auth(creds, service, region).add_auth(aws_req)
    prepared = aws_req.prepare()

    try:
        resp = requests.get(prepared.url, headers=dict(prepared.headers), timeout=(5.0, 15.0))
    except requests.RequestException as exc:
        print(f"FAIL: request error: {exc}")
        return 1

    preview = (resp.text or "")[:300].replace("\n", " ")
    print(f"GET /customer?code={code} -> HTTP {resp.status_code}")
    print(f"body_preview={preview!r}")

    if resp.status_code == 401:
        print(
            "\n401 = SigV4 keys rejected by api.sql.my for this book/tenant.\n"
            "Fix: update the tenant sqlApi secret in AWS (same accessKey/secretKey as SQL Account portal\n"
            "  Test Connection), then restart eQuotation. Do not use IAM user keys (AWS_ACCESS_KEY_ID) as SQL_API_*."
        )
        return 2
    if resp.status_code >= 400:
        return 3
    print("OK: SQL API accepted credentials for this request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
