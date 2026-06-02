"""Verify http://localhost:8881/create-quotation serves the table markup."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from flask.sessions import SecureCookieSessionInterface

import main

app = main.app
with app.test_request_context():
    si = SecureCookieSessionInterface()
    session_data = {
        "user_email": "t@t.com",
        "user_type": "customer",
        "logged_in": True,
        "customer_code": "TEST",
        "_permanent": True,
    }
    serializer = si.get_signing_serializer(app)
    cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
    cookies = {cookie_name: serializer.dumps(session_data)}

r = requests.get("http://127.0.0.1:8881/create-quotation", cookies=cookies, timeout=15)
text = r.text
print("status", r.status_code)
checks = {
    "quotation-lines-table": "quotation-lines-table" in text,
    "From catalog": "From catalog" in text,
    "create-quotation-lines-wrap": "create-quotation-lines-wrap" in text,
    "cq-lines-v3": "cq-lines-v3" in text,
    "cq-lines-critical": "cq-lines-critical" in text,
}
for name, ok in checks.items():
    print(f"  {name}: {'OK' if ok else 'MISSING'}")

old_div = 'id="quotation-items-list"' in text and "quotation-lines-table" not in text
print("  old_div_layout_only:", old_div)
print("  orderQuotation.css linked:", "orderQuotation.css" in text)

if not all(checks.values()) or old_div:
    sys.exit(1)
print("PASS")
