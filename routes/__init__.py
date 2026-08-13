"""Routes module for organizing Flask endpoints."""

from .quotation_routes import quotation_bp
from .auth_routes import auth_bp
from .php_proxy_routes import php_proxy_bp
from .procurement_routes import procurement_bp

__all__ = ["quotation_bp", "auth_bp", "php_proxy_bp", "procurement_bp"]
