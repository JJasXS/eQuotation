"""save_draft_quotation API is customer-only (no real DB writes)."""
from unittest.mock import patch

import main as app_main
from utils.csrf_protect import CSRF_HEADER_NAME
from utils.role_permissions import ACCESS_TIER_CUSTOMER, ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_SALES_MGMT

_CSRF = "c" * 32


def _client():
    app_main.app.config["TESTING"] = True
    return app_main.app.test_client()


def _post_save_draft(client, *, json_body=None):
    return client.post(
        "/api/save_draft_quotation",
        json=json_body or {"description": "x", "items": []},
        headers={CSRF_HEADER_NAME: _CSRF},
    )


def test_save_draft_forbidden_for_full_admin():
    client = _client()
    with client.session_transaction() as sess:
        sess["user_type"] = "admin"
        sess["access_tier"] = ACCESS_TIER_FULL_ADMIN
        sess["user_email"] = "admin@example.com"
        sess["_csrf_token"] = _CSRF
    resp = _post_save_draft(client)
    assert resp.status_code == 403
    body = resp.get_json() or {}
    assert body.get("success") is False


def test_save_draft_forbidden_for_sales_mgmt():
    client = _client()
    with client.session_transaction() as sess:
        sess["user_type"] = "admin"
        sess["access_tier"] = ACCESS_TIER_SALES_MGMT
        sess["user_email"] = "sales@example.com"
        sess["_csrf_token"] = _CSRF
    resp = _post_save_draft(client)
    assert resp.status_code == 403


def test_save_draft_customer_reaches_service_with_mock():
    client = _client()
    with client.session_transaction() as sess:
        sess["user_type"] = "user"
        sess["access_tier"] = ACCESS_TIER_CUSTOMER
        sess["user_email"] = "cust@example.com"
        sess["customer_code"] = "C001"
        sess["_csrf_token"] = _CSRF
    with patch.object(app_main, "get_current_customer_code", return_value="C001"), patch.object(
        app_main,
        "save_draft_quotation",
        return_value={"success": True, "dockey": 1, "docno": "DRAFT-00001", "message": "ok"},
    ) as mocked:
        resp = _post_save_draft(
            client,
            json_body={"description": "Draft", "items": [{"product": "A", "qty": 1, "price": 1}]},
        )
    assert resp.status_code == 200
    body = resp.get_json() or {}
    assert body.get("success") is True
    assert mocked.called
