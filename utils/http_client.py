"""Shared safe HTTP JSON helpers for Flask app and utilities."""
import requests

from utils.http_timeouts import parse_timeout_env


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
    r = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=json,
        data=data,
        timeout=t,
    )
    if r.status_code >= 400:
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
    return body, r
