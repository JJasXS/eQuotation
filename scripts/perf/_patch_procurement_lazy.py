"""One-shot patch: lazy stock-card / freshness / abort for precurement_app.js."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "static" / "js" / "procurement" / "precurement_app.js"
text = PATH.read_text(encoding="utf-8")

# Normalize to work on non-blank-line form then re-apply if needed.
# File currently has a blank line after every line; strip empties for editing, restore style.
lines = text.splitlines(keepends=True)
has_double = sum(1 for i in range(1, min(40, len(lines))) if lines[i].strip() == "" and lines[i - 1].strip() != "") > 10

def densify(s: str) -> str:
    return "\n".join(ln for ln in s.splitlines() if ln.strip() != "") + "\n"

def sparsify(s: str) -> str:
    out = []
    for ln in s.splitlines():
        out.append(ln)
        out.append("")
    return "\n".join(out) + "\n"

work = densify(text) if has_double else text

old_show = """            if (selected === 'report') {

                initStockCardUomDisplay();

                afterStockCardTableRender();

                // Refetch when coming back to the dashboard (not the first paint: DOMContentLoaded

                // already loads once while reportLoaded is still false).

                if (reportLoaded) {

                    loadStockCardRows();

                }

                return;

            }"""

old_show_dense = densify(old_show)

new_show_dense = """            if (selected === 'report') {
                initStockCardUomDisplay();
                afterStockCardTableRender();
                // Refresh only when data is missing or older than STOCK_CARD_FRESH_MS.
                const ageMs = stockCardLastLoadedAt ? (Date.now() - stockCardLastLoadedAt) : Infinity;
                if (!reportLoaded || ageMs >= STOCK_CARD_FRESH_MS) {
                    loadStockCardRows();
                }
                return;
            }"""

if old_show_dense not in work:
    raise SystemExit("showTab report block not found")
work = work.replace(old_show_dense, new_show_dense, 1)

# Add state after reportLoaded
anchor = "let reportLoaded = false;\n        let createPrLookupsStarted = false;"
if anchor not in work:
    raise SystemExit("reportLoaded anchor not found")
work = work.replace(
    anchor,
    """let reportLoaded = false;
        let createPrLookupsStarted = false;
        let stockCardLastLoadedAt = 0;
        let stockCardFetchController = null;
        let stockCardHiddenSince = 0;
        const STOCK_CARD_FRESH_MS = 60 * 1000;
        const STOCK_CARD_IDLE_HIDDEN_MS = 15 * 60 * 1000;""",
    1,
)

# Replace loadStockCardRows fetch block — find function start through end of function
start = work.find("        function loadStockCardRows() {")
if start < 0:
    raise SystemExit("loadStockCardRows not found")
# Find next function at same indent after start
next_fn = work.find("\n        function applyStockCardDateFilter()", start)
if next_fn < 0:
    raise SystemExit("applyStockCardDateFilter not found")
old_fn = work[start:next_fn]
new_fn = """        function loadStockCardRows() {
            initStockCardUomDisplay();
            const tbody = document.getElementById('stock-card-table-body');
            const loadingColumns = getStockCardTotalColumns(selectedStockCardLocations);
            if (getVisibleStockCardMetricGroups().length === 0) {
                tbody.innerHTML = `<tr><td class="code-col stock-card-code-col--fixed">…</td><td class="stock-card-no-cols-msg stock-card-status">Loading stock items...</td></tr>`;
            } else {
                tbody.innerHTML = `<tr><td colspan="${loadingColumns}" class="stock-card-status">Loading stock items...</td></tr>`;
            }
            setStockCardTableNoMetricColsClass();
            const fromDateInput = document.getElementById('stock-card-from-date');
            const fromDate = fromDateInput ? String(fromDateInput.value || '').trim() : '';
            const query = new URLSearchParams();
            if (fromDate) {
                query.set('from_date', fromDate);
                query.set('to_date', prTodayIso());
            }
            query.set('qty_mode', stockCardUomDisplayMode === 'sqty_only' ? 'SQTY' : 'SUOMQTY');
            const requestUrl = query.toString()
                ? `/api/admin/procurement/stock-card?${query.toString()}`
                : '/api/admin/procurement/stock-card';
            if (stockCardFetchController) {
                try { stockCardFetchController.abort(); } catch (e) { /* ignore */ }
            }
            const controller = new AbortController();
            stockCardFetchController = controller;
            const timeoutId = window.setTimeout(() => {
                try { controller.abort(); } catch (e) { /* ignore */ }
            }, 30000);
            fetch(requestUrl, { cache: 'no-store', signal: controller.signal })
                .then((res) => readProcurementJson(res))
                .then((payload) => {
                    if (controller.signal.aborted) return;
                    if (!payload.success) {
                        throw new Error(payload.error || 'Failed to load stock items');
                    }
                    const locations = Array.isArray(payload.locations) ? payload.locations : [];
                    const avgMonthsRaw = Array.isArray(payload.avg_sales_3m_months)
                        ? payload.avg_sales_3m_months
                        : (payload.filters && Array.isArray(payload.filters.avg_sales_3m_months)
                            ? payload.filters.avg_sales_3m_months
                            : []);
                    stockCardAvgSales3mMonths = avgMonthsRaw.map((m) => String(m || '').trim()).filter(Boolean);
                    const previousSelected = Array.isArray(selectedStockCardLocations)
                        ? selectedStockCardLocations.slice()
                        : [];
                    stockCardLocations = locations.slice();
                    const locationSet = new Set(locations);
                    if (!reportLoaded) {
                        const persisted = readPersistedStockCardLocations();
                        const persistedValid = Array.isArray(persisted)
                            ? persisted.map((c) => String(c || '').trim()).filter(Boolean).filter((code) => locationSet.has(code))
                            : [];
                        if (persistedValid.length) {
                            selectedStockCardLocations = persistedValid;
                        } else {
                            selectedStockCardLocations = locations.slice();
                        }
                    } else {
                        const preserved = previousSelected.filter((code) => locationSet.has(code));
                        if (!previousSelected.length) {
                            selectedStockCardLocations = [];
                        } else {
                            selectedStockCardLocations = preserved.length ? preserved : locations.slice();
                        }
                    }
                    persistStockCardSelectedLocations();
                    stockCardRows = Array.isArray(payload.data) ? payload.data : [];
                    stockCardStTrUdfSummary = payload.st_tr_udf_suomqty && typeof payload.st_tr_udf_suomqty === 'object'
                        ? payload.st_tr_udf_suomqty
                        : null;
                    reportLoaded = true;
                    stockCardLastLoadedAt = Date.now();
                    syncStockCardTable();
                })
                .catch((error) => {
                    if (controller.signal.aborted || (error && error.name === 'AbortError')) {
                        return;
                    }
                    if (isProcurementAuthExpired(error)) {
                        return;
                    }
                    console.error('Failed to load stock card rows:', error);
                    stockCardStTrUdfSummary = null;
                    const totalColumns = getStockCardTotalColumns(selectedStockCardLocations);
                    const msg = escapeHtml(error.message || 'Failed to load stock items.');
                    if (getVisibleStockCardMetricGroups().length === 0) {
                        tbody.innerHTML = `<tr><td class="code-col stock-card-code-col--fixed">-</td><td class="stock-card-no-cols-msg stock-card-status">${msg}</td></tr>`;
                    } else {
                        tbody.innerHTML = `<tr><td colspan="${totalColumns}" class="stock-card-status">${msg}</td></tr>`;
                    }
                    setStockCardTableNoMetricColsClass();
                })
                .finally(() => {
                    clearTimeout(timeoutId);
                    if (stockCardFetchController === controller) {
                        stockCardFetchController = null;
                    }
                });
        }

"""
work = work[:start] + new_fn + work[next_fn:]

# Replace DOMContentLoaded block
dom_start = work.find("        document.addEventListener('DOMContentLoaded', function () {")
if dom_start < 0:
    raise SystemExit("DOMContentLoaded not found")
# end at closing of that listener — find matching close before end of IIFE-ish
# Use the known trailing showTab catch
dom_marker = "                    showTab('report');\n\n                }\n\n        });"
# densified version:
dom_end_pat = "                    showTab('report');\n                } catch (e) {\n                    showTab('report');\n                }\n\n        });"
# Find from densify of original
old_dom_dense = densify("""        document.addEventListener('DOMContentLoaded', function () {

                initStockDashboardLayout();

                loadStockCardRows();

                afterStockCardTableRender();

                bindPurchaseRequestDeliveryLocationSync();

                if (!tryRestorePurchaseRequestDraftItems()) {
                    initPurchaseRequestForm();
                }
                const prNoEl = document.getElementById('pr-request-number');
                if (prNoEl && !String(prNoEl.value || '').trim()) {
                    loadNextPurchaseRequestNumber();
                }

                window.addEventListener('resize', afterStockCardTableRender);

                document.addEventListener('visibilitychange', () => {

                    if (document.visibilityState !== 'visible') return;

                    const panel = document.getElementById('panel-report');

                    if (!panel || panel.style.display === 'none') return;

                    if (!reportLoaded) return;

                    if (stockCardVisibilityRefreshTimer) {

                        clearTimeout(stockCardVisibilityRefreshTimer);

                    }

                    stockCardVisibilityRefreshTimer = setTimeout(() => {

                        stockCardVisibilityRefreshTimer = null;

                        loadStockCardRows();

                    }, 400);

                });

                // Select initial view based on URL query param (e.g. ?tab=report|view|create)

                try {

                    const params = new URLSearchParams(window.location.search || '');

                    const tab = String(params.get('tab') || 'report').trim();

                    applyViewStatusFromUrl();

                    showTab(tab);

                } catch (e) {

                    showTab('report');

                }

        });""")

new_dom_dense = """        document.addEventListener('DOMContentLoaded', function () {
                initStockDashboardLayout();
                afterStockCardTableRender();
                bindPurchaseRequestDeliveryLocationSync();
                window.addEventListener('resize', afterStockCardTableRender);
                document.addEventListener('visibilitychange', () => {
                    if (document.visibilityState !== 'visible') {
                        stockCardHiddenSince = Date.now();
                        if (stockCardVisibilityRefreshTimer) {
                            clearTimeout(stockCardVisibilityRefreshTimer);
                            stockCardVisibilityRefreshTimer = null;
                        }
                        return;
                    }
                    const hiddenFor = stockCardHiddenSince ? (Date.now() - stockCardHiddenSince) : 0;
                    stockCardHiddenSince = 0;
                    const panel = document.getElementById('panel-report');
                    if (!panel || panel.style.display === 'none') return;
                    if (!reportLoaded) return;
                    if (hiddenFor >= STOCK_CARD_IDLE_HIDDEN_MS) {
                        // Long idle: refresh only if still stale when user needs report.
                    }
                    const ageMs = stockCardLastLoadedAt ? (Date.now() - stockCardLastLoadedAt) : Infinity;
                    if (ageMs < STOCK_CARD_FRESH_MS) return;
                    if (stockCardVisibilityRefreshTimer) {
                        clearTimeout(stockCardVisibilityRefreshTimer);
                    }
                    stockCardVisibilityRefreshTimer = setTimeout(() => {
                        stockCardVisibilityRefreshTimer = null;
                        loadStockCardRows();
                    }, 400);
                });
                // Select initial view based on URL query param (e.g. ?tab=report|view|create)
                // Stock card / create-PR lookups load only for the active tab via showTab.
                try {
                    const params = new URLSearchParams(window.location.search || '');
                    const tab = String(params.get('tab') || 'report').trim();
                    applyViewStatusFromUrl();
                    if (tab === 'create') {
                        if (!tryRestorePurchaseRequestDraftItems()) {
                            initPurchaseRequestForm();
                        }
                        const prNoEl = document.getElementById('pr-request-number');
                        if (prNoEl && !String(prNoEl.value || '').trim()) {
                            loadNextPurchaseRequestNumber();
                        }
                    }
                    showTab(tab);
                } catch (e) {
                    showTab('report');
                }
        });"""

if old_dom_dense not in work:
    # maybe already partially densified differently
    idx = work.find("document.addEventListener('DOMContentLoaded'")
    print("DOM snippet nearby:", repr(work[idx:idx+500]))
    raise SystemExit("DOMContentLoaded block not found for replace")
work = work.replace(old_dom_dense, new_dom_dense, 1)

out = sparsify(work) if has_double else work
PATH.write_text(out, encoding="utf-8")
print(f"patched {PATH} double_spaced={has_double}")
