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


def _make_sigv4_get(url: str, params: dict) -> requests.Response:
    """Send a SigV4-signed GET request to the SQL Accounting external API."""
    access_key = (os.getenv("SQL_API_ACCESS_KEY") or os.getenv("API_ACCESS_KEY") or "").strip()
    secret_key = (os.getenv("SQL_API_SECRET_KEY") or os.getenv("API_SECRET_KEY") or "").strip()
    region = (os.getenv("SQL_API_REGION") or "ap-southeast-5").strip()
    service = (os.getenv("SQL_API_SERVICE") or "execute-api").strip()
    timeout = float(os.getenv("SQL_API_TIMEOUT_SECONDS") or "30")

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

    session = requests.Session()
    return session.get(
        prepared.url,
        headers=dict(prepared.headers),
        timeout=timeout,
    )


def _external_supplier_url() -> str:
    use_tls = (os.getenv("SQL_API_USE_TLS") or "true").strip().lower() in ("1", "true", "yes", "on")
    host = (os.getenv("SQL_API_HOST") or "api.sql.my").strip().rstrip("/")
    scheme = "https" if use_tls else "http"
    return f"{scheme}://{host}/supplier"


@router.get("/supplier")
def list_suppliers(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _: None = Depends(verify_api_keys),
):
    """Proxy supplier list from SQL Accounting external API with SigV4 signing."""
    url = _external_supplier_url()
    try:
        resp = _make_sigv4_get(url, {"offset": offset, "limit": limit})
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Supplier API request timed out")
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach supplier API: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error fetching suppliers")
        raise HTTPException(status_code=500, detail=str(exc))

    if not resp.ok:
        logger.warning("Supplier API returned %s: %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=502, detail=f"Supplier API returned {resp.status_code}")

    try:
        return resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Supplier API returned non-JSON response")
