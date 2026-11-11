"""Session CSRF tokens for cookie-authenticated browser mutations."""
from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlparse

from flask import Request, jsonify, session

CSRF_SESSION_KEY = "_csrf_token"
CSRF_COOKIE_NAME = "eq_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"

# Pre-auth / bootstrap endpoints that must work without a session CSRF token.
CSRF_EXEMPT_PATHS = frozenset(
    {
        "/api/send_otp",
        "/api/verify_otp",
        "/api/create_signin_user",
        "/api/create_signin_user_minimal",
        "/api/guide_capture_login",
        "/api/csrf_token",
    }
)


def ensure_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
        session.modified = True
    return token


def clear_csrf_token() -> None:
    session.pop(CSRF_SESSION_KEY, None)


def _extract_request_token(req: Request) -> str:
    header = (req.headers.get(CSRF_HEADER_NAME) or req.headers.get("X-Csrf-Token") or "").strip()
    if header:
        return header
    if req.form:
        form_token = (req.form.get(CSRF_FORM_FIELD) or "").strip()
        if form_token:
            return form_token
    try:
        data = req.get_json(silent=True) or {}
    except Exception:
        data = {}
    if isinstance(data, dict):
        return str(data.get(CSRF_FORM_FIELD) or "").strip()
    return ""


def tokens_match(expected: str, provided: str) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


def uses_non_cookie_auth(req: Request) -> bool:
    """Machine clients that authenticate without relying on the browser session cookie."""
    auth = (req.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer ") and len(auth) > 8:
        return True
    if (req.headers.get("X-Access-Key") or "").strip() and (req.headers.get("X-Secret-Key") or "").strip():
        return True
    return False


def origin_host_mismatch(req: Request) -> bool | None:
    """Return True if Origin mismatches host, False if Origin matches, None if Origin absent."""
    origin = (req.headers.get("Origin") or "").strip()
    if not origin:
        referer = (req.headers.get("Referer") or "").strip()
        if referer:
            origin = referer
        else:
            return None
    try:
        origin_host = (urlparse(origin).netloc or "").lower()
        req_host = (req.host or "").lower()
        if not origin_host or not req_host:
            return None
        return origin_host != req_host
    except Exception:
        return None


def csrf_failure(message: str = "CSRF validation failed", status: int = 403):
    return jsonify({"success": False, "error": message}), status


def should_enforce_csrf(req: Request) -> bool:
    if req.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return False
    path = str(req.path or "")
    if path in CSRF_EXEMPT_PATHS:
        return False
    if uses_non_cookie_auth(req):
        return False
    # Cookie-authenticated browser session (or logout which clears it).
    if "user_email" not in session and path != "/logout":
        return False
    if path.startswith("/api/") or path.startswith("/php/") or path in ("/chat", "/logout"):
        return True
    if path.startswith("/admin/api/"):
        return True
    return False


def validate_csrf_request(req: Request):
    """Return a Flask error response when CSRF/Origin checks fail; else None."""
    if not should_enforce_csrf(req):
        return None

    mismatch = origin_host_mismatch(req)
    if mismatch is True:
        return csrf_failure("Cross-origin request blocked")

    expected = session.get(CSRF_SESSION_KEY)
    if not isinstance(expected, str) or len(expected) < 32:
        # Logged-in session without token: mint and require client retry with cookie.
        ensure_csrf_token()
        return csrf_failure("CSRF token missing; refresh the page and retry")

    provided = _extract_request_token(req)
    if not tokens_match(expected, provided):
        return csrf_failure("CSRF token invalid or missing")
    return None
