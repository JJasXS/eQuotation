"""Keep /api and /php responses JSON when auth redirects or HTML errors leak through."""
from urllib.parse import urlparse

from flask import jsonify

_API_PREFIXES = ("/api/", "/php/")
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def _is_api_path(path: str) -> bool:
    text = path or ""
    return any(text.startswith(prefix) for prefix in _API_PREFIXES)


def _is_login_location(location: str) -> bool:
    raw = (location or "").strip()
    if not raw:
        return False
    path = urlparse(raw).path or raw
    return path.rstrip("/") == "/login"


def _json_error(message: str, status: int):
    response = jsonify({"success": False, "error": message})
    response.status_code = status
    return response


def _looks_like_login_page(preview: str) -> bool:
    text = (preview or "").lstrip().lower()
    if not (text.startswith("<!doctype") or text.startswith("<html")):
        return False
    return "<title>sign in</title>" in text or "login-page" in text


def _html_error(status: int, preview: str):
    """Map an HTML API body to JSON. 403/404/5xx stay those statuses."""
    if status == 401 or (status < 400 and _looks_like_login_page(preview)):
        return _json_error("Session expired. Please log in again.", 401)
    if status == 403:
        return _json_error("You do not have permission for this request.", 403)
    if status == 404:
        return _json_error("API endpoint not found.", 404)
    if status >= 500:
        return _json_error("The server could not complete this request.", status)
    if status >= 400:
        return _json_error("The server could not return data for this request.", status)
    return _json_error("The server could not return data for this request.", 502)


def rewrite_api_html_response(path: str, response):
    """Return JSON for API HTML bodies and login redirects. Leave other responses unchanged."""
    if not _is_api_path(path):
        return response
    location = response.headers.get("Location", "")
    if response.status_code in _REDIRECT_STATUSES and _is_login_location(location):
        return _json_error("Session expired. Please log in again.", 401)
    mimetype = (response.mimetype or "").split(";")[0].strip().lower()
    if mimetype != "text/html":
        return response
    try:
        preview = response.get_data(as_text=True)[:500]
    except Exception:
        return response
    return _html_error(response.status_code, preview)
