from pathlib import Path
import re

path = Path(r"c:\Users\sqlsupport\eQuotation\templates\precurement\precurement.html")
text = path.read_text(encoding="utf-8")

# 1) finalizeViewPrAfterApprovalSave: detail first, background list
old_finalize = """        async function finalizeViewPrAfterApprovalSave(selectedHeaderId) {
            const keepId = Number(selectedHeaderId || viewSelectedHeaderId || 0);
            await loadViewPurchaseRequests(true);
            if (keepId > 0) {
                viewSelectedHeaderId = keepId;
                const record = (viewPurchaseRequests || []).find((row) => Number(row.id || 0) === keepId);
                if (record) {
                    record.udfStatus = 'APPROVED';
                    record._originalUdfStatus = 'APPROVED';
                    delete record._pendingUdfStatus;
                    invalidateViewDetailCache(keepId);
                    viewLoadingDetailIds.add(keepId);
                    renderFilteredViewPurchaseRequests();
                    try {
                        await fetchViewPurchaseRequestDetail(record, true);
                    } catch (error) {
                        console.warn('[View PR] Failed to refresh detail after approval:', error);
                    }
                    viewLoadingDetailIds.delete(keepId);
                    syncViewPrToUrl();
                    renderFilteredViewPurchaseRequests();
                    return;
                }
            }
            if (!selectViewPrFromUrlIfPresent()) {
                syncViewPrToUrl();
            }
            renderFilteredViewPurchaseRequests();
        }"""

new_finalize = """        async function finalizeViewPrAfterApprovalSave(selectedHeaderId) {
            const keepId = Number(selectedHeaderId || viewSelectedHeaderId || 0);
            if (keepId > 0) {
                viewSelectedHeaderId = keepId;
                const record = (viewPurchaseRequests || []).find((row) => Number(row.id || 0) === keepId);
                if (record) {
                    record.udfStatus = 'APPROVED';
                    record._originalUdfStatus = 'APPROVED';
                    delete record._pendingUdfStatus;
                    invalidateViewDetailCache(keepId);
                    viewLoadingDetailIds.add(keepId);
                    renderFilteredViewPurchaseRequests();
                    try {
                        await fetchViewPurchaseRequestDetail(record, true);
                    } catch (error) {
                        console.warn('[View PR] Failed to refresh detail after approval:', error);
                    }
                    viewLoadingDetailIds.delete(keepId);
                    syncViewPrToUrl();
                    renderFilteredViewPurchaseRequests();
                    loadViewPurchaseRequests(false, { background: true });
                    return;
                }
            }
            await loadViewPurchaseRequests(false, { background: true });
            if (!selectViewPrFromUrlIfPresent()) {
                syncViewPrToUrl();
            }
            renderFilteredViewPurchaseRequests();
        }"""

if old_finalize not in text:
    raise SystemExit("finalize block not found")
text = text.replace(old_finalize, new_finalize, 1)

# 2) loadViewPurchaseRequests signature + stale-while-revalidate + optional no_cache
text = text.replace(
    "        function loadViewPurchaseRequests(forceReload) {",
    "        function loadViewPurchaseRequests(forceReload, options) {\n            const loadOpts = options || {};",
    1,
)

text = text.replace(
    "            if (viewPurchaseRequestsLoaded && !forceReload) {",
    "            if (viewPurchaseRequestsLoaded && !forceReload && !loadOpts.background) {",
    1,
)

text = text.replace(
    "            const paintedFromCache = !forceReload && paintCachedViewPrListForInstantLoad();",
    """            const hasExistingList = viewPurchaseRequestsLoaded && (viewPurchaseRequests || []).length > 0;
            const paintedFromCache = (!forceReload && paintCachedViewPrListForInstantLoad())
                || (hasExistingList && (loadOpts.background || forceReload));""",
    1,
)

text = text.replace(
    "            const cacheBust = forceReload ? '&no_cache=1' : '';",
    "            const cacheBust = loadOpts.bustCache ? '&no_cache=1' : '';",
    1,
)

# Refresh button: bust server cache only on explicit Refresh
text = text.replace(
    'onclick="loadViewPurchaseRequests(true)"',
    'onclick="loadViewPurchaseRequests(true, { bustCache: true })"',
    1,
)

# 3) Show perf banner
text = text.replace(
    "            el.hidden = true;",
    "            el.hidden = false;",
    1,
)

# 4) Add supplierEnrichMs to perf banner
needle = "            const sup = Number(p.supplierMs);"
if needle in text and "supplierEnrichMs" not in text[text.find(needle):text.find(needle)+400]:
    text = text.replace(
        needle,
        needle
        + "\n\n            const supEnrich = Number(p.supplierEnrichMs);",
        1,
    )
    text = text.replace(
        "                parts.push(`supplier map ${sup} ms`);",
        "                parts.push(`supplier map ${sup} ms`);\n            }\n\n            if (Number.isFinite(supEnrich) && supEnrich > 0.05) {\n                parts.push(`supplier enrich ${supEnrich} ms`);",
        1,
    )

path.write_text(text, encoding="utf-8")
print("patched view PR perf")
