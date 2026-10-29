"""Procurement page routes extracted from main.py."""
from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request, session

from utils.role_permissions import (
    ACCESS_TIER_SUPPLIER,
    can_access_admin_dashboard,
    can_access_purchase_menu,
    infer_access_tier_from_session,
    template_permission_context,
)

procurement_bp = Blueprint("procurement_pages", __name__)

_deps: dict = {}


def init_procurement_routes(**deps):
    _deps.clear()
    _deps.update(deps)


def _ui_path() -> str:
    return _deps.get("procurement_ui_path") or "/admin/procurement"


def _purchase_home_href() -> str:
    if can_access_admin_dashboard(session):
        return "/admin"
    return "/create-quotation"


def _render_purchase_access_denied(page_title: str = "Purchase"):
    ctx = {
        "user_type": session.get("user_type", ""),
        "user_email": session.get("user_email", ""),
        "page_header_title": page_title,
        "access_denied_message": (
            "Your account does not have a Purchase role "
            "(Admin, HOD, Purchasing Manager, or Director)."
        ),
        "home_href": _purchase_home_href(),
    }
    ctx.update(template_permission_context(session))
    return render_template("access_denied.html", **ctx), 403


@procurement_bp.route("/admin/procurement")
def admin_procurement_module():
    require_page_access = _deps["require_page_access"]
    page_error = require_page_access()
    if page_error:
        return page_error
    if not can_access_purchase_menu(session):
        return _render_purchase_access_denied("Purchase")
    ctx = {"user_type": session.get("user_type", ""), "user_email": session.get("user_email", "")}
    ctx.update(template_permission_context(session))
    return render_template("precurement/precurement.html", **ctx)


@procurement_bp.route("/admin/precurement/precurement")
def admin_procurement_legacy_typo_redirect():
    require_page_access = _deps["require_page_access"]
    page_error = require_page_access()
    if page_error:
        return page_error
    if not can_access_purchase_menu(session):
        return _render_purchase_access_denied("Purchase")
    tab = request.args.get("tab") or "report"
    return redirect(f'{_ui_path()}?tab={quote(str(tab), safe="")}', code=308)


@procurement_bp.route("/admin/procurement/bidding")
def admin_procurement_bidding_page():
    require_page_access = _deps["require_page_access"]
    render_protected_template = _deps["render_protected_template"]
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    if not can_access_purchase_menu(session) and not can_access_admin_dashboard(session):
        return _render_purchase_access_denied("Purchase > Supplier Bidding")
    return render_protected_template(
        "adminBidding.html",
        require_admin=False,
        user_type=session.get("user_type", "admin"),
        user_name=session.get("user_email", ""),
    )


@procurement_bp.route("/supplier/bidding")
def supplier_bidding_page():
    require_page_access = _deps["require_page_access"]
    render_protected_template = _deps["render_protected_template"]
    page_error = require_page_access()
    if page_error:
        return page_error
    if infer_access_tier_from_session(session) != ACCESS_TIER_SUPPLIER:
        if can_access_purchase_menu(session):
            return redirect(f"{_ui_path()}?tab=view")
        return redirect("/create-quotation")
    return render_protected_template(
        "supplierBidding.html",
        block_admin=True,
        admin_redirect=_ui_path(),
        user_type=session.get("user_type", "user"),
        supplier_code=session.get("supplier_code") or session.get("customer_code", ""),
        user_name=session.get("user_email", ""),
    )


def register_procurement_routes(app, **deps):
    init_procurement_routes(**deps)
    app.register_blueprint(procurement_bp)
