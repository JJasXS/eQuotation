"""Static checks for Customer View Quotation manual Refresh (no real DB/API)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static" / "js" / "adminViewQuotations.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "adminViewQuotations.css").read_text(encoding="utf-8")


def test_customer_refresh_helper_is_gated_to_mine_pages():
    assert "function refreshCustomerQuotations" in JS or "refreshCustomerQuotations =" in JS
    assert "isCustomerMyQuotationsPage()" in JS
    assert "loadQuotations({ soft: true })" in JS
    # Must no-op / soft-load only for customer mine pages.
    assert "Boolean(options.soft) && mine" in JS


def test_customer_refresh_clears_detail_cache_and_dedupes_loads():
    assert "quotationDetailCache.clear()" in JS
    assert "quotationsLoadPromise" in JS
    assert "if (quotationsLoadPromise)" in JS


def test_customer_refresh_preserves_tab_and_selection_on_soft_reload():
    assert "preservedTab" in JS
    assert "preservedSelection" in JS
    assert "selectedDockeyByTab[key] = preservedSelection[key]" in JS


def test_refresh_button_markup_is_customer_list_header_only():
    assert "avq-customer-refresh-btn" in JS
    assert "avq-list-pane-header" in JS
    assert "Quotation list" in JS
    # Admin shell builder must not hardcode the customer refresh control.
    assert "avq-customer-refresh-btn" not in JS.split("function buildViewQuotationsShellHtml")[1].split(
        "function parseQuotationDate"
    )[0]


def test_refresh_button_styles_exist_for_customer_page():
    assert "avq-list-refresh-btn" in CSS
    assert "customer-my-quotations-page" in CSS
    assert ".avq-list-pane-header" in CSS
