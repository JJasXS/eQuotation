"""Auth page routes extracted from main.py."""
from __future__ import annotations

import csv
import os

from flask import Blueprint, make_response, redirect, render_template, request, session
from utils.csrf_protect import CSRF_COOKIE_NAME, clear_csrf_token

auth_bp = Blueprint("auth_pages", __name__)


@auth_bp.route("/login")
def login():
    """Show login page."""
    if "user_email" in session:
        if session.get("user_type") == "admin":
            return redirect("/admin")
        return redirect("/create-quotation")
    return render_template("login.html")


@auth_bp.route("/signInGuest")
def sign_in_guest():
    """Show minimal guest sign-in page (code + companyname)."""
    countries = []
    try:
        csv_path = os.path.join(os.path.dirname(__file__), "..", "csv", "CountryCodeWNames.csv")
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            seen = set()
            for row in reader:
                name = (row.get("name") or "").strip()
                alpha2 = (row.get("alpha-2") or "").strip().upper()
                if not name or not alpha2 or name in seen:
                    continue
                seen.add(name)
                countries.append({"name": name, "alpha2": alpha2})
    except Exception as e:
        print(f"[WARN] Failed to load countries CSV for signInGuest: {e}")
    return render_template("newSignInGuest.html", countries=countries)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Logout user. State-changing logout requires POST + CSRF (enforced globally).

    GET remains a safe redirect to /login without clearing the session (CSRF-safe).
    """
    if request.method == "GET":
        return redirect("/login")

    session.clear()
    clear_csrf_token()
    resp = make_response(redirect("/login"))
    resp.set_cookie(CSRF_COOKIE_NAME, "", max_age=0, path="/")
    return resp


def register_auth_routes(app):
    app.register_blueprint(auth_bp)
