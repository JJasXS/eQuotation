"""Purchase-order paid REST sync refuses when BLOCK_REST without LocalOnly."""
from __future__ import annotations

import pytest

from utils.procurement_sql_api_sync import sync_purchase_order_supplier_sql_api


def test_po_supplier_sync_blocked_rest_raises_without_local_only(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    monkeypatch.setenv("SQL_ACCOUNTING_PO_SYNC_MODE", "Rest")
    with pytest.raises(RuntimeError, match="BLOCK_REST_HTTP"):
        sync_purchase_order_supplier_sql_api(12345, "400-K0001", po_number="PO-LAB-1")
