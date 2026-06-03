"""Supplier list endpoint — SigV4-signed GET proxy to SQL Accounting API."""
from __future__ import annotations

import logging
import os

import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from fastapi import APIRouter, Depends, HTTPException, Query

from api.routes.customers import verify_api_keys

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Suppliers"])

# Reuse a single session across requests (connection pooling, not recreated per call).
_supplier_session = requests.Session()


def _make_sigv4_get(url: str, params: dict) -> requests.Response:
    """Send a SigV4-signed GET request to the SQL Accounting external API."""
    access_key = (os.getenv("SQL_API_ACCESS_KEY") or os.getenv("API_ACCESS_KEY") or "").strip()
    secret_key = (os.getenv("SQL_API_SECRET_KEY") or os.getenv("API_SECRET_KEY") or "").strip()
    region = (os.getenv("SQL_API_REGION") or "ap-southeast-1").strip()
    service = (os.getenv("SQL_API_SERVICE") or "execute-api").strip()
    # Use a shorter timeout than the default 30s; the UI shows 504 in the logs when this hits.
    timeout = float(os.getenv("SQL_API_TIMEOUT_SECONDS") or "12")

    # Build query string manually so SigV4 signs the canonical URL
    if params:
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        full_url = f"{url}?{qs}"
    else:
        full_url = url

    creds = Credentials(access_key, secret_key)
    aws_request = AWSRequest(method="GET", url=full_url, data=b"", headers={})
    SigV4Auth(creds, service, region).add_auth(aws_request)
    prepared = aws_request.prepare()

    return _supplier_session.get(
        prepared.url,
        headers=dict(prepared.headers),
        timeout=timeout,
    )


def _external_supplier_host_url() -> str:
    use_tls = (os.getenv("SQL_API_USE_TLS") or "true").strip().lower() in ("1", "true", "yes", "on")
    host = (os.getenv("SQL_API_HOST") or "api.sql.my").strip().rstrip("/")
    scheme = "https" if use_tls else "http"
    return f"{scheme}://{host}"


def _external_supplier_list_paths() -> list[str]:
    """SQL Accounting list routes (Postman often uses GET /supplier/*)."""
    custom = (os.getenv("SQL_API_SUPPLIER_LIST_PATH") or "").strip()
    paths: list[str] = []
    if custom:
        paths.append(custom if custom.startswith("/") else f"/{custom}")
    for candidate in ("/supplier/*", "/supplier"):
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _external_supplier_list_url(path: str) -> str:
    base = _external_supplier_host_url()
    p = (path or "/supplier").strip()
    if not p.startswith("/"):
        p = "/" + p
    return f"{base}{p}"


def _external_supplier_url() -> str:
    """Default supplier list URL (used by auth email lookup)."""
    paths = _external_supplier_list_paths()
    return _external_supplier_list_url(paths[0] if paths else "/supplier")


@router.get("/supplier")
def list_suppliers(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _: None = Depends(verify_api_keys),
):
    """Proxy supplier list from SQL Accounting external API with SigV4 signing."""
    params = {"offset": offset, "limit": limit}
    last_status = 502
    last_detail = "Supplier API unavailable"
    for path in _external_supplier_list_paths():
        url = _external_supplier_list_url(path)
        print(
            f"[SQL API SUPPLIER] GET list offset={offset} limit={limit} → {url}",
            flush=True,
        )
        try:
            resp = _make_sigv4_get(url, params)
        except requests.exceptions.Timeout:
            raise HTTPException(status_code=504, detail="Supplier API request timed out")
        except requests.exceptions.ConnectionError as exc:
            raise HTTPException(status_code=503, detail=f"Cannot reach supplier API: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error fetching suppliers")
            raise HTTPException(status_code=500, detail=str(exc))

        if resp.ok:
            try:
                body = resp.json()
            except ValueError:
                raise HTTPException(status_code=502, detail="Supplier API returned non-JSON response")
            rows = body.get("data", []) if isinstance(body, dict) else []
            if isinstance(rows, list) and rows:
                sample = [
                    str((r or {}).get("code") or "").strip()
                    for r in rows[:3]
                    if isinstance(r, dict)
                ]
                print(
                    f"[SQL API SUPPLIER] OK {url} → {len(rows)} row(s)"
                    f"{f' (e.g. {sample})' if sample else ''}",
                    flush=True,
                )
                return body
            if isinstance(rows, list) and not rows:
                print(f"[SQL API SUPPLIER] OK {url} → empty data[], try next path", flush=True)
                continue
            return body

        last_status = resp.status_code
        last_detail = f"Supplier API {url} returned {resp.status_code}"
        print(f"[SQL API SUPPLIER] FAIL {url} → HTTP {resp.status_code}", flush=True)
        logger.warning("Supplier list %s -> %s: %s", url, resp.status_code, resp.text[:200])

    print(f"[SQL API SUPPLIER] All list paths failed (last HTTP {last_status})", flush=True)
    raise HTTPException(status_code=502, detail=last_detail)
