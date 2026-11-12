"""Static checks for View Quotation manual Refresh (customer + admin; no real DB/API)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static" / "js" / "adminViewQuotations.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "adminViewQuotations.css").read_text(encoding="utf-8")


def test_refresh_helper_uses_soft_loadquotations():
    assert "function refreshQuotationsList" in JS or "refreshQuotationsList =" in JS
    assert "loadQuotations({ soft: true })" in JS
    assert "Boolean(options.soft)" in JS


def test_refresh_clears_detail_cache_and_dedupes_loads():
    assert "quotationDetailCache.clear()" in JS
    assert "quotationsLoadPromise" in JS
    assert "if (quotationsLoadPromise)" in JS


def test_soft_refresh_preserves_tab_selection_and_admin_filters():
    assert "preservedTab" in JS
    assert "preservedSelection" in JS
    assert "preservedFilters" in JS
    assert "selectedDockeyByTab[key] = preservedSelection[key]" in JS
    assert "companyFilter = preservedFilters.companyFilter" in JS


def test_refresh_button_is_on_status_menubar_for_admin_and_customer():
    assert "avq-quotations-refresh-btn" in JS
    assert "avq-status-menubar" in JS
    assert "avq-status-toolbar-actions" in JS
    assert "refreshQuotationsList()" in JS
    shell_chunk = JS.split("function buildViewQuotationsShellHtml")[1].split(
        "function parseQuotationDate"
    )[0]
    assert "avq-quotations-refresh-btn" in shell_chunk
    assert "role=\"tablist\"" in shell_chunk
    # Always built (admin + customer), not gated on showAdminFilters alone.
    assert "avq-status-menubar" in shell_chunk


def test_refresh_button_styles_exist_on_admin_quotations_pages():
    assert "avq-list-refresh-btn" in CSS
    assert "admin-quotations-view-page" in CSS
    assert ".avq-status-menubar" in CSS
    assert ".avq-status-toolbar-actions" in CSS
