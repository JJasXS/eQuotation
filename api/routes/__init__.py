"""FastAPI routes."""
from . import health, customers, debug, dashboard, suppliers, purchase_requests

__all__ = ['health', 'customers', 'debug', 'dashboard', 'suppliers', 'purchase_requests']
