from pathlib import Path
import re

path = Path(r"c:\Users\sqlsupport\eQuotation\templates\precurement\precurement.html")
text = path.read_text(encoding="utf-8")

helpers = """
        function viewPrHeadersMarkedApprovedForSave() {
            const ids = new Set();
            viewHeaderStatusPendingChanges.forEach((change) => {
                if (normalizeUdfStatus(change.udfStatus) === 'APPROVED') {
                    const rid = Number(change.requestId || 0);
                    if (rid > 0) {
                        ids.add(rid);
                    }
                }
            });
            return ids;
        }

        function activateViewPrApprovedTabAfterSave(approvedHeaderIds) {
            const ids = approvedHeaderIds instanceof Set ? approvedHeaderIds : new Set();
            if (!ids.size) {
                const selectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;
                if (selectedId > 0) {
                    const header = (viewPurchaseRequests || []).find((row) => Number(row.id || 0) === selectedId);
                    if (header && normalizeUdfStatus(header._originalUdfStatus || header.udfStatus) === 'APPROVED') {
                        ids.add(selectedId);
                    }
                }
            }
            if (!ids.size) {
                return false;
            }
            viewStatusFilters = new Set(['APPROVED']);
            syncViewStatusFilterTabClasses();
            syncViewPrToUrl();
            return true;
        }

        async function finalizeViewPrAfterApprovalSave(selectedHeaderId) {
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
        }

"""

anchor = "        function applyViewStatusFromUrl() {"
if helpers.strip() in text:
    print("helpers already present")
elif anchor not in text:
    raise SystemExit("anchor for helpers not found")
else:
    text = text.replace(anchor, helpers + anchor, 1)
    print("inserted helpers")

old_reload = """                await loadViewPurchaseRequests(true);
                await refreshSelectedViewPurchaseRequestDetail(true);"""
new_reload = """                const keepSelectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;
                const approvedHeaderIds = viewPrHeadersMarkedApprovedForSave();
                activateViewPrApprovedTabAfterSave(approvedHeaderIds);
                await finalizeViewPrAfterApprovalSave(keepSelectedId);"""
if old_reload not in text:
    raise SystemExit("reload block not found")
text = text.replace(old_reload, new_reload, 1)
print("patched reload block")

# Patch cache sync loop to invalidate on approved
pattern = (
    r"(const affectedIds = new Set\(\[[\s\S]*?\]\);\s*)"
    r"(affectedIds\.forEach\(\(id\) => \{[\s\S]*?"
    r"if \(header && Array\.isArray\(header\.details\)\) \{[\s\S]*?"
    r"syncViewDetailCacheFromRecord\(header\);[\s\S]*?"
    r"\} else \{[\s\S]*?"
    r"invalidateViewDetailCache\(id\);[\s\S]*?"
    r"\}[\s\S]*?"
    r"\}\);)"
)
replacement = r"""\1const approvedIdsForCache = viewPrHeadersMarkedApprovedForSave();
                    affectedIds.forEach((id) => {
                        if (!id) return;
                        const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === id);
                        const headerApproved = approvedIdsForCache.has(id)
                            || (header && normalizeUdfStatus(header._originalUdfStatus || header.udfStatus) === 'APPROVED');
                        if (headerApproved) {
                            invalidateViewDetailCache(id);
                            return;
                        }
                        if (header && Array.isArray(header.details)) {
                            syncViewDetailCacheFromRecord(header);
                        } else {
                            invalidateViewDetailCache(id);
                        }
                    });"""
new_text, n = re.subn(pattern, replacement, text, count=1)
if n != 1:
    raise SystemExit(f"cache loop patch failed (matches={n})")
text = new_text
print("patched cache loop")

path.write_text(text, encoding="utf-8")
print("done")
