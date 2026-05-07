"""Shared safe HTTP JSON helpers for Flask app and utilities."""
import json
import logging
import os
import time

import requests

from utils.http_timeouts import parse_timeout_env

logger = logging.getLogger(__name__)

_EQ_HTTP_PROFILE = (os.getenv("EQ_HTTP_PROFILE", "") or "").strip().lower() in ("1", "true", "yes", "on")
_SLOW_MS = float((os.getenv("EQ_HTTP_SLOW_MS", "") or "1000").strip() or "1000")


def _maybe_len_estimate(body: object, raw_text: str) -> int:
    if raw_text:
        return len(raw_text.encode("utf-8", errors="replace"))
    try:
        return len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 0


def timeout_for_url(url, fastapi_base=None, php_base=None):
    """
    Pick (connect, read) timeout from URL prefix: FastAPI base, then PHP base, else internal.
    """
    u = (url or '').strip()
    candidates = []
    if fastapi_base:
        candidates.append((fastapi_base.rstrip('/'), 'FASTAPI_REQUEST_TIMEOUT', 3.0, 15.0))
    if php_base:
        candidates.append((php_base.rstrip('/'), 'PHP_API_REQUEST_TIMEOUT', 3.0, 10.0))
    candidates.sort(key=lambda x: -len(x[0]))
    for base, key, dc, dr in candidates:
        if base and u.startswith(base):
            return parse_timeout_env(key, dc, dr)
    return parse_timeout_env('INTERNAL_HTTP_REQUEST_TIMEOUT', 2.0, 12.0)


def http_request_json(
    method,
    url,
    *,
    fastapi_base=None,
    php_base=None,
    timeout=None,
    headers=None,
    params=None,
    json=None,
    data=None,
):
    """
    HTTP request with consistent timeouts, status check, and JSON parse.
    Returns (parsed_body, response). Raises requests.HTTPError on HTTP >= 400,
    ValueError on empty or non-JSON body.
    """
    t = timeout if timeout is not None else timeout_for_url(url, fastapi_base, php_base)
    t0 = time.perf_counter()
    r = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=json,
        data=data,
        timeout=t,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if r.status_code >= 400:
        if _EQ_HTTP_PROFILE or elapsed_ms >= _SLOW_MS:
            logger.warning(
                "http %s %s -> %s in %.0fms (error)",
                method,
                url,
                r.status_code,
                elapsed_ms,
            )
        preview = (r.text or '').strip().replace('\n', ' ')[:240]
        raise requests.exceptions.HTTPError(f"HTTP {r.status_code} from {url}: {preview}")
    text = (r.text or '').strip()
    if not text:
        raise ValueError(f"Empty response body from {url}")
    try:
        body = r.json()
    except ValueError as e:
        preview = text[:240]
        raise ValueError(f"Non-JSON response from {url}: {preview}") from e

    if _EQ_HTTP_PROFILE:
        nbytes = _maybe_len_estimate(body, text)
        logger.info(
            "http %s %s -> 200 in %.0fms ~%sB",
            method,
            url,
            elapsed_ms,
            nbytes,
        )
    elif elapsed_ms >= _SLOW_MS:
        logger.warning(
            "slow http %s %s -> 200 in %.0fms (threshold %.0fms)",
            method,
            url,
            elapsed_ms,
            _SLOW_MS,
        )
    return body, r
