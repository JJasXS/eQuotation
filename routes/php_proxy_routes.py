"""XAMPP PHP proxy routes — consolidated from main.py."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

php_proxy_bp = Blueprint("php_proxy", __name__)

_proxy_post = None
_proxy_get = None
_http_request_json = None
_base_api_url = None
_endpoint_paths = None
_require_api_auth = None


def init_php_proxy_routes(
    *,
    proxy_post,
    proxy_get,
    http_request_json,
    base_api_url,
    endpoint_paths,
    require_api_auth,
):
    global _proxy_post, _proxy_get, _http_request_json, _base_api_url, _endpoint_paths, _require_api_auth
    _proxy_post = proxy_post
    _proxy_get = proxy_get
    _http_request_json = http_request_json
    _base_api_url = base_api_url
    _endpoint_paths = endpoint_paths or {}
    _require_api_auth = require_api_auth


def _path(key: str | None, literal: str) -> str:
    if key and _endpoint_paths and key in _endpoint_paths:
        return _endpoint_paths[key]
    return literal


@php_proxy_bp.route("/php/deleteOrderDetail.php", methods=["POST"])
def proxy_delete_order_detail():
    return _proxy_post(
        "/php/deleteOrderDetail.php",
        error_message="Failed to delete order detail",
        log_context="deleteOrderDetail",
    )


@php_proxy_bp.route("/php/updateOrderStatus.php", methods=["POST"])
def proxy_update_order_status():
    return _proxy_post(
        _path("updateorderstatus", "/php/updateOrderStatus.php"),
        admin_only=True,
        error_message="Failed to update order status",
        log_context="status update",
    )


@php_proxy_bp.route("/php/updateOrderDetail.php", methods=["POST"])
def proxy_update_order_detail():
    return _proxy_post(
        _path("updateorderdetail", "/php/updateOrderDetail.php"),
        admin_only=True,
        error_message="Failed to update order detail",
        log_context="updateOrderDetail",
    )


@php_proxy_bp.route("/php/insertOrderDetail.php", methods=["POST"])
def proxy_insert_order_detail():
    return _proxy_post(
        _path("insertorderdetail", "/php/insertOrderDetail.php"),
        admin_only=True,
        error_message="Failed to insert order detail",
        log_context="insertOrderDetail",
    )


@php_proxy_bp.route("/php/requestOrderChange.php", methods=["POST"])
def proxy_request_order_change():
    return _proxy_post(
        "/php/requestOrderChange.php",
        error_message="Failed to submit change request",
        log_context="change request",
        timeout_message="Request timed out. Please check if XAMPP is running.",
        connection_message="Cannot connect to database server. Please ensure XAMPP is running.",
        include_exception_detail=True,
    )


@php_proxy_bp.route("/php/getOrderDetails.php")
def proxy_get_order_details():
    orderid = request.args.get("orderid")
    if not orderid:
        return jsonify({"success": False, "error": "orderid parameter required"}), 400
    return _proxy_get(
        _path("getorderdetails", "/php/getOrderDetails.php"),
        params={"orderid": orderid},
        error_message="Failed to fetch order details",
        log_context="getOrderDetails",
    )


@php_proxy_bp.route("/php/getOrderRemarks.php")
def proxy_get_order_remarks():
    orderid = request.args.get("orderid")
    if not orderid:
        return jsonify({"success": False, "error": "orderid parameter required"}), 400
    return _proxy_get(
        "/php/getOrderRemarks.php",
        params={"orderid": orderid},
        error_message="Failed to fetch remarks",
        log_context="getOrderRemarks",
    )


@php_proxy_bp.route("/php/getOrdersByStatus.php")
def proxy_get_orders_by_status():
    auth_error = _require_api_auth()
    if auth_error:
        return auth_error

    status = request.args.get("status")
    if not status:
        return jsonify({"success": False, "error": "status parameter required"}), 400

    try:
        url = f"{_base_api_url}{_path('getordersbystatus', '/php/getOrdersByStatus.php')}?status={status}"
        user_type = session.get("user_type", "user")
        if user_type != "admin":
            customer_code = session.get("customer_code")
            if customer_code:
                url += f"&customerCode={customer_code}"
        body, resp = _http_request_json("GET", url)
        return jsonify(body), resp.status_code
    except Exception as e:
        print(f"Error proxying to XAMPP: {e}")
        return jsonify({"success": False, "error": "Failed to fetch orders from database"}), 500


def register_php_proxy_routes(app, **deps):
    init_php_proxy_routes(**deps)
    app.register_blueprint(php_proxy_bp)
