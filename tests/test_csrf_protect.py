"""CSRF token validation for cookie-authenticated mutations."""
from __future__ import annotations

from flask import Flask, jsonify, request, session

from utils.csrf_protect import (
    CSRF_HEADER_NAME,
    ensure_csrf_token,
    validate_csrf_request,
)


def _app():
    app = Flask(__name__)
    app.secret_key = "csrf-unit-test-secret-key-32chars"

    @app.before_request
    def _guard():
        return validate_csrf_request(request)

    @app.get("/api/csrf_token")
    def token():
        session["user_email"] = "u@example.com"
        return jsonify({"csrf_token": ensure_csrf_token()})

    @app.post("/api/create_quotation")
    def create_qt():
        return jsonify({"success": True})

    @app.post("/api/send_otp")
    def send_otp():
        return jsonify({"success": True})

    @app.post("/logout")
    def logout():
        session.clear()
        return jsonify({"success": True})

    return app


def test_mutating_api_requires_csrf_when_logged_in():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess["user_email"] = "u@example.com"
    resp = client.post("/api/create_quotation", json={})
    assert resp.status_code == 403
    assert "CSRF" in (resp.get_json() or {}).get("error", "")


def test_mutating_api_accepts_valid_csrf_header():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess["user_email"] = "u@example.com"
        sess["_csrf_token"] = "a" * 32
    resp = client.post(
        "/api/create_quotation",
        json={},
        headers={CSRF_HEADER_NAME: "a" * 32},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_send_otp_exempt_without_session():
    client = _app().test_client()
    resp = client.post("/api/send_otp", json={"email": "x@y.z"})
    assert resp.status_code == 200


def test_bearer_auth_bypasses_csrf():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess["user_email"] = "u@example.com"
    resp = client.post(
        "/api/create_quotation",
        json={},
        headers={"Authorization": "Bearer service-token"},
    )
    assert resp.status_code == 200


def test_cross_origin_rejected():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess["user_email"] = "u@example.com"
        sess["_csrf_token"] = "b" * 32
    resp = client.post(
        "/api/create_quotation",
        json={},
        headers={
            CSRF_HEADER_NAME: "b" * 32,
            "Origin": "https://evil.example",
        },
    )
    assert resp.status_code == 403
    assert "Cross-origin" in (resp.get_json() or {}).get("error", "")
