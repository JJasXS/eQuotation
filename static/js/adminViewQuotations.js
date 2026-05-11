let draftsQuotationsCache = [];
let reviewedQuotationsCache = [];
let cancelledQuotationsCache = [];
let pendingQuotationsCache = [];
let companyFilter = '';
/** One or more of: drafts, pending, reviewed, cancelled. At least one must stay selected. */
let selectedQuotationTabFilters = new Set(['reviewed']);
let selectedActiveQuotations = new Set();
let selectedPendingQuotations = new Set();
let selectedQuotationDockey = null;
const quotationDetailCache = new Map();

/** Date filter (YYYY-MM-DD from input type=date) */
let adminDateFrom = '';
let adminDateTo = '';
/** First page shows 5 rows; each "more" adds 10 */
let listVisibleLimit = { drafts: 5, pending: 5, reviewed: 5, cancelled: 5 };

function isCustomerMyQuotationsPage() {
    try {
        return document.body && document.body.getAttribute('data-quotations-list-source') === 'mine';
    } catch (e) {
        return false;
    }
}

/** Avoid cache collisions between SL_QT and SL_QTDRAFT rows that share a dockey (edge case). */
function quotationDetailCacheKey(row) {
    if (!row || row.DOCKEY == null) return '';
    const dk = Number(row.DOCKEY);
    if (!Number.isFinite(dk)) return '';
    return row._sourceSlQtDraft ? `${dk}_slqtdraft` : `${dk}_slqt`;
}

function buildViewQuotationsShellHtml(showAdminFilters) {
    const filterInner = showAdminFilters
        ? `
                        <label style="display: flex; align-items: center; gap: 6px; color: #87684d; font-size: 13px;">From
                            <input type="date" id="quotation-date-from" style="padding: 6px 10px; border-radius: 6px; border: 1px solid #e2cfab; background: #fffaf0; color: #4f3b2a; font-size: 13px;">
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; color: #87684d; font-size: 13px;">To
                            <input type="date" id="quotation-date-to" style="padding: 6px 10px; border-radius: 6px; border: 1px solid #e2cfab; background: #fffaf0; color: #4f3b2a; font-size: 13px;">
                        </label>
                        <button type="button" id="quotation-date-apply" style="padding: 8px 12px; border-radius: 6px; background: #b9894a; color: #fff; border: none; cursor: pointer; font-size: 13px;">Apply</button>
                        <button type="button" id="quotation-date-clear" style="padding: 8px 12px; border-radius: 6px; background: #f8efdd; color: #7b5a36; border: 1px solid #e2cfab; cursor: pointer; font-size: 13px;">Clear dates</button>
                        <select id="company-filter-dropdown" style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e2cfab; background: #fffaf0; color: #4f3b2a; font-size: 13px; width: 240px;">
                            <option value="">All Companies</option>
                        </select>
                        <button id="company-filter-clear" style="padding: 8px 12px; border-radius: 6px; background: #f8efdd; color: #7b5a36; border: 1px solid #e2cfab; cursor: pointer; font-size: 13px;">Clear</button>
                    `
        : `
                        <p style="margin:0;color:#87684d;font-size:13px;line-height:1.4;">Showing quotations for your customer account (read-only — same layout as staff view).</p>
                    `;
    return `
            <div class="admin-quotations-view" style="padding: 16px;">
                <div class="quotation-page-header">
                    <div class="quotation-page-header-controls">
                        ${filterInner}
                    </div>
                    <div class="approvals-tabs quotation-page-header-tabs">
                        <button type="button" id="tab-drafts" class="approval-tab ${selectedQuotationTabFilters.has('drafts') ? 'active' : ''}" onclick="toggleQuotationFilter('drafts')">
                            Drafts (${draftsQuotationsCache.length})
                        </button>
                        <button type="button" id="tab-pending" class="approval-tab ${selectedQuotationTabFilters.has('pending') ? 'active' : ''}" onclick="toggleQuotationFilter('pending')">
                            Pending (${pendingQuotationsCache.length})
                        </button>
                        <button type="button" id="tab-reviewed" class="approval-tab ${selectedQuotationTabFilters.has('reviewed') ? 'active' : ''}" onclick="toggleQuotationFilter('reviewed')">
                            Reviewed (${reviewedQuotationsCache.length})
                        </button>
                        <button type="button" id="tab-cancelled" class="approval-tab ${selectedQuotationTabFilters.has('cancelled') ? 'active' : ''}" onclick="toggleQuotationFilter('cancelled')">
                            Cancelled (${cancelledQuotationsCache.length})
                        </button>
                    </div>
                </div>
                <div id="quotation-tab-content" style="padding-top: 12px;"></div>
            </div>
        `;
}

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function parseQuotationDate(raw) {
    if (raw == null || raw === '') return null;
    const s = String(raw).trim();
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10));
    const t = Date.parse(s);
    if (!isNaN(t)) return new Date(t);
    return null;
}

function toYmd(d) {
    if (!d || isNaN(d.getTime())) return '';
    const y = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${mo}-${day}`;
}

/** Display as DD-MON-YYYY (e.g. 05-Mar-2026) */
function formatDateForDisplay(raw) {
    if (raw == null || raw === '' || raw === '-') return '-';
    const d = parseQuotationDate(raw);
    if (!d || isNaN(d.getTime())) return String(raw);
    const day = String(d.getDate()).padStart(2, '0');
    return `${day}-${MONTH_SHORT[d.getMonth()]}-${d.getFullYear()}`;
}

function filterQuotationsByDate(list, fromStr, toStr) {
    const from = fromStr || '';
    const to = toStr || '';
    if (!from && !to) return list;
    return list.filter(qt => {
        const d = parseQuotationDate(qt.DOCDATE);
        if (!d) return false;
        const ymd = toYmd(d);
        if (from && ymd < from) return false;
        if (to && ymd > to) return false;
        return true;
    });
}

function getFilteredAdminLists() {
    const df = adminDateFrom;
    const dt = adminDateTo;
    const d = filterQuotationsByCompany(filterQuotationsByDate(draftsQuotationsCache, df, dt));
    const p = filterQuotationsByCompany(filterQuotationsByDate(pendingQuotationsCache, df, dt));
    const r = filterQuotationsByCompany(filterQuotationsByDate(reviewedQuotationsCache, df, dt));
    const c = filterQuotationsByCompany(filterQuotationsByDate(cancelledQuotationsCache, df, dt));
    return { drafts: d, pending: p, reviewed: r, cancelled: c };
}

function normalizeWorkflowUdfStatus(qt) {
    return (qt.UDF_STATUS != null ? String(qt.UDF_STATUS) : '').trim().toUpperCase();
}

function isLegacyPendingQuotation(qt) {
    const cancelledUnset = qt.CANCELLED === null || qt.CANCELLED === undefined;
    const updateCountUnset = qt.UPDATECOUNT === null || qt.UPDATECOUNT === undefined;
    return cancelledUnset || updateCountUnset;
}

/** Match customer /view-quotation buckets (SL_QT.UDF_STATUS + legacy fallback). */
function quotationWorkflowBucket(qt) {
    const u = normalizeWorkflowUdfStatus(qt);
    if (u === 'DRAFT') {
        return 'drafts';
    }
    if (u === 'PENDING') {
        return 'pending';
    }
    if (u === 'CANCELLED') {
        return 'cancelled';
    }
    if (u === 'REVIEWED' || u === 'ACTIVE' || u === 'APPROVED') {
        return 'reviewed';
    }
    if (!u) {
        if (qt.CANCELLED === true) {
            return 'cancelled';
        }
        if (isLegacyPendingQuotation(qt)) {
            return 'pending';
        }
        return 'reviewed';
    }
    if (u === 'INACTIVE') {
        return 'cancelled';
    }
    return 'reviewed';
}

function hideQuotationStatusActionsFromPage() {
    return (
        typeof document !== 'undefined' &&
        document.body &&
        document.body.dataset.hideQuotationActions === 'true'
    );
}

window.toggleCancelledStatus = async function(dockey, isCancelled) {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    console.log('[DEBUG] toggleCancelledStatus called - dockey:', dockey, 'isCancelled:', isCancelled);
    
    try {
        const newStatus = !isCancelled;
        console.log('[DEBUG] Sending to backend: dockey:', dockey, 'cancelled:', newStatus);
        
        const response = await fetch('/api/admin/update_quotation_cancelled', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dockey, cancelled: newStatus })
        });
        
        console.log('[DEBUG] Response status:', response.status);
        const data = await response.json();
        console.log('[DEBUG] Response data:', data);

        if (data.success) {
            console.log('[DEBUG] Update successful, reloading quotations...');
            await loadQuotations();
        } else {
            alert('Failed to update status: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('[ERROR] toggleCancelledStatus exception:', err);
        alert('Error updating status: ' + err);
    }
};

window.activateQuotation = async function(dockey) {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    console.log('[DEBUG] activateQuotation called - dockey:', dockey);
    
    if (!confirm('Are you sure you want to mark this quotation as reviewed?')) {
        return;
    }
    
    try {
        console.log('[DEBUG] Sending to backend: dockey:', dockey, 'cancelled: false');
        
        const response = await fetch('/api/admin/update_quotation_cancelled', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dockey, cancelled: false })
        });
        
        console.log('[DEBUG] Response status:', response.status);
        const data = await response.json();
        console.log('[DEBUG] Response data:', data);

        if (data.success) {
            console.log('[DEBUG] Activation successful, reloading quotations...');
            await loadQuotations();
            setQuotationTab('reviewed');
        } else {
            alert('Failed to mark quotation as reviewed: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('[ERROR] activateQuotation exception:', err);
        alert('Error marking quotation as reviewed: ' + err);
    }
};

async function getAllUniqueCompanyNames() {
    try {
        const response = await fetch('/api/get_company_names');
        const data = await response.json();
        return data.success ? (data.data || []) : [];
    } catch (error) {
        console.error('Error fetching company names:', error);
        return [];
    }
}

function filterQuotationsByCompany(list) {
    if (!companyFilter) {
        return list;
    }

    return list.filter(qt => {
        const company = (qt.COMPANYNAME || '').toLowerCase().trim();
        return company === companyFilter.toLowerCase();
    });
}

async function setupCompanyFilter() {
    const dropdown = document.getElementById('company-filter-dropdown');
    const clearBtn = document.getElementById('company-filter-clear');
    if (!dropdown || !clearBtn) {
        return;
    }

    const companies = await getAllUniqueCompanyNames();
    dropdown.innerHTML = '<option value="">All Companies</option>' +
        companies.map(name => `<option value="${name}">${name}</option>`).join('');

    dropdown.onchange = function() {
        companyFilter = dropdown.value;
        listVisibleLimit = { drafts: 5, pending: 5, reviewed: 5, cancelled: 5 };
        refreshQuotationListView();
    };

    clearBtn.onclick = function() {
        companyFilter = '';
        dropdown.value = '';
        listVisibleLimit = { drafts: 5, pending: 5, reviewed: 5, cancelled: 5 };
        refreshQuotationListView();
    };
}

function setupDateFilter() {
    const fromEl = document.getElementById('quotation-date-from');
    const toEl = document.getElementById('quotation-date-to');
    const applyBtn = document.getElementById('quotation-date-apply');
    const clearBtn = document.getElementById('quotation-date-clear');
    if (!fromEl || !toEl || !applyBtn || !clearBtn) return;

    applyBtn.onclick = function() {
        adminDateFrom = fromEl.value || '';
        adminDateTo = toEl.value || '';
        listVisibleLimit = { drafts: 5, pending: 5, reviewed: 5, cancelled: 5 };
        refreshQuotationListView();
    };
    clearBtn.onclick = function() {
        fromEl.value = '';
        toEl.value = '';
        adminDateFrom = '';
        adminDateTo = '';
        listVisibleLimit = { drafts: 5, pending: 5, reviewed: 5, cancelled: 5 };
        refreshQuotationListView();
    };

    fromEl.value = adminDateFrom || '';
    toEl.value = adminDateTo || '';
}

function getCombinedQuotationList() {
    const { drafts, pending, reviewed, cancelled } = getFilteredAdminLists();
    const out = [];
    const parts = [
        ['drafts', drafts],
        ['pending', pending],
        ['reviewed', reviewed],
        ['cancelled', cancelled],
    ];
    for (const [key, list] of parts) {
        if (!selectedQuotationTabFilters.has(key)) {
            continue;
        }
        for (const q of list) {
            out.push({ ...q, _filterTab: key });
        }
    }
    return out;
}

/**
 * Select exactly one status tab (Drafts / Pending / Reviewed / Cancelled).
 */
window.toggleQuotationFilter = function (name) {
    if (!['drafts', 'pending', 'reviewed', 'cancelled'].includes(name)) {
        return;
    }
    if (selectedQuotationTabFilters.size === 1 && selectedQuotationTabFilters.has(name)) {
        return;
    }
    selectedQuotationTabFilters = new Set([name]);
    refreshQuotationListView();
};

function refreshQuotationListView() {
    if (!selectedQuotationTabFilters.has('pending')) {
        selectedPendingQuotations.clear();
    }

    const tabContent = document.getElementById('quotation-tab-content');
    const draftsBtn = document.getElementById('tab-drafts');
    const reviewedBtn = document.getElementById('tab-reviewed');
    const cancelledBtn = document.getElementById('tab-cancelled');
    const pendingBtn = document.getElementById('tab-pending');
    if (!tabContent || !draftsBtn || !reviewedBtn || !cancelledBtn || !pendingBtn) {
        return;
    }

    const { drafts: draftsList, pending: pendingList, reviewed: reviewedList, cancelled: cancelledList } =
        getFilteredAdminLists();

    draftsBtn.textContent = `Drafts (${draftsList.length})`;
    pendingBtn.textContent = `Pending (${pendingList.length})`;
    reviewedBtn.textContent = `Reviewed (${reviewedList.length})`;
    cancelledBtn.textContent = `Cancelled (${cancelledList.length})`;

    draftsBtn.classList.toggle('active', selectedQuotationTabFilters.has('drafts'));
    pendingBtn.classList.toggle('active', selectedQuotationTabFilters.has('pending'));
    reviewedBtn.classList.toggle('active', selectedQuotationTabFilters.has('reviewed'));
    cancelledBtn.classList.toggle('active', selectedQuotationTabFilters.has('cancelled'));

    const visibleList = getCombinedQuotationList();

    if (!visibleList.some((row) => Number(row.DOCKEY) === Number(selectedQuotationDockey))) {
        selectedQuotationDockey = visibleList.length ? Number(visibleList[0].DOCKEY) : null;
    }

    const html = `
        <div class="quotation-split-wrap">
            <div class="quotation-list-pane">
                ${renderQuotationList(visibleList, {}, 'combined', false)}
            </div>
            <div class="quotation-detail-pane" id="quotation-detail-pane">
                <div class="quotation-detail-empty">Select a quotation to view details.</div>
            </div>
        </div>
    `;
    tabContent.innerHTML = html;

    document.querySelectorAll('.quotation-card').forEach((card) => {
        card.addEventListener('click', function (e) {
            if (
                !e.target.closest('.edit-button')
                && !e.target.closest('.activate-btn')
                && !e.target.closest('.toggle-cancelled-btn')
                && !e.target.closest('.quotation-checkbox-active')
                && !e.target.closest('.quotation-checkbox-pending')
            ) {
                selectedQuotationDockey = Number(this.dataset.dockey);
                refreshQuotationListView();
            }
        });
    });

    updateActiveDeleteControls();
    updatePendingReviewControls();
    renderQuotationDetail(visibleList, {});
}

async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) return;

    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    try {
        quotationDetailCache.clear();
        const mine = isCustomerMyQuotationsPage();
        let allQuotations = [];

        if (mine) {
            const [mainRes, draftRes] = await Promise.all([
                fetch('/api/get_my_quotations').then((r) => r.json()),
                fetch('/api/get_my_draft_quotations').then((r) => r.json()),
            ]);
            if (!mainRes.success) {
                const message = mainRes.error ? String(mainRes.error) : 'Failed to load quotations';
                content.innerHTML = `<div style="padding: 20px; text-align: center; color: #ff6b6b;">${message}</div>`;
                return;
            }
            allQuotations = mainRes.data || [];
            draftsQuotationsCache = [];
            pendingQuotationsCache = [];
            reviewedQuotationsCache = [];
            cancelledQuotationsCache = [];
            allQuotations.forEach((qt) => {
                const b = quotationWorkflowBucket(qt);
                if (b === 'drafts') {
                    draftsQuotationsCache.push(qt);
                } else if (b === 'pending') {
                    pendingQuotationsCache.push(qt);
                } else if (b === 'cancelled') {
                    cancelledQuotationsCache.push(qt);
                } else {
                    reviewedQuotationsCache.push(qt);
                }
            });
            const slDrafts = draftRes && draftRes.success ? draftRes.data || [] : [];
            slDrafts.forEach((d) => {
                draftsQuotationsCache.push({
                    ...d,
                    _sourceSlQtDraft: true,
                    COMPANYNAME: d.COMPANYNAME || 'N/A',
                });
            });
        } else {
            const response = await fetch('/api/admin/get_all_quotations');
            const data = await response.json();

            if (!data.success) {
                const message = data.error ? String(data.error) : 'Failed to load quotations';
                content.innerHTML = `<div style="padding: 20px; text-align: center; color: #ff6b6b;">${message}</div>`;
                return;
            }

            allQuotations = data.data || [];

            draftsQuotationsCache = [];
            pendingQuotationsCache = [];
            reviewedQuotationsCache = [];
            cancelledQuotationsCache = [];
            allQuotations.forEach((qt) => {
                const b = quotationWorkflowBucket(qt);
                if (b === 'drafts') {
                    draftsQuotationsCache.push(qt);
                } else if (b === 'pending') {
                    pendingQuotationsCache.push(qt);
                } else if (b === 'cancelled') {
                    cancelledQuotationsCache.push(qt);
                } else {
                    reviewedQuotationsCache.push(qt);
                }
            });
        }

        listVisibleLimit = { drafts: 5, pending: 5, reviewed: 5, cancelled: 5 };

        const html = buildViewQuotationsShellHtml(!mine);

        content.innerHTML = html;
        if (!mine) {
            setupDateFilter();
        } else {
            adminDateFrom = '';
            adminDateTo = '';
        }
        refreshQuotationListView();
    } catch (error) {
        content.innerHTML = '<div style="padding: 20px; text-align: center; color: #ff6b6b;">Failed to load quotations.</div>';
        console.error('Error loading quotations:', error);
    }
}

function setQuotationTab(tabName) {
    if (!['drafts', 'pending', 'reviewed', 'cancelled'].includes(tabName)) {
        return;
    }
    selectedQuotationTabFilters = new Set([tabName]);
    refreshQuotationListView();
}

function renderQuotationList(list, options = {}, tabKey = 'reviewed', hasMore = false) {
    if (!list || list.length === 0) {
        return '<div style="padding: 12px; text-align: center; color: #7b5a36;">No quotations</div>';
    }

    const hideStatus = hideQuotationStatusActionsFromPage();
    const hasReviewedInList = list.some((qt) => (qt._filterTab || 'reviewed') === 'reviewed');
    const hasPendingInList = list.some((qt) => (qt._filterTab || '') === 'pending');
    let controlsHtml = '';
    if (hasPendingInList && !hideStatus) {
        controlsHtml += `
            <div class="active-tab-controls show">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 500; user-select: none; color: #5c4028;">
                    <input type="checkbox" id="select-all-pending" onchange="toggleSelectAllPending(event)" style="width: 18px; height: 18px; cursor: pointer; accent-color: #4b9e6e;">
                    Select All
                </label>
                <button type="button" id="bulk-review-pending-btn" onclick="performBulkReviewPending()" class="btn-bulk-review-pending" disabled>
                    Mark selected as reviewed
                </button>
                <span id="selected-count-pending" style="margin-left: auto; font-size: 14px; color: #87684d; font-weight: 500;">0 selected</span>
            </div>
        `;
    }
    if (hasReviewedInList && !hideStatus) {
        controlsHtml += `
            <div class="active-tab-controls show">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 500; user-select: none; color: #5c4028;">
                    <input type="checkbox" id="select-all-active" onchange="toggleSelectAllActive(event)" style="width: 18px; height: 18px; cursor: pointer; accent-color: #dc3545;">
                    Select All
                </label>
                <button id="bulk-delete-active-btn" onclick="showDeleteConfirmActive()" class="btn-delete-active" disabled>
                    Batch cancel selected
                </button>
                <span id="selected-count-active" style="margin-left: auto; font-size: 14px; color: #87684d; font-weight: 500;">0 selected</span>
            </div>
        `;
    }

    let html = controlsHtml;
    list.forEach(qt => {
        const filterTab = qt._filterTab || 'reviewed';
        const isPending = filterTab === 'pending';
        const isCancelled = filterTab === 'cancelled';
        const isReviewed = filterTab === 'reviewed';
        const isDrafts = filterTab === 'drafts';
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = formatDateForDisplay(qt.DOCDATE);
        const borderColor = isCancelled
            ? '#a65c5c'
            : isPending
              ? '#b0892f'
              : isDrafts
                ? '#6b7c9a'
                : '#2d5a8a';
        const badgeColor = borderColor;
        const isSelected = Number(qt.DOCKEY) === Number(selectedQuotationDockey);
        
        let checkboxHtml = '';
        if (!hideStatus && isReviewed) {
            checkboxHtml = `<input type="checkbox" class="quotation-checkbox-active" data-dockey="${qt.DOCKEY}" ${selectedActiveQuotations.has(Number(qt.DOCKEY)) ? 'checked' : ''} onchange="handleActiveCheckboxChange(); event.stopPropagation();" style="width: 18px; height: 18px; cursor: pointer; accent-color: #dc3545; flex-shrink: 0;">`;
        } else if (!hideStatus && isPending) {
            checkboxHtml = `<input type="checkbox" class="quotation-checkbox-pending" data-dockey="${qt.DOCKEY}" ${selectedPendingQuotations.has(Number(qt.DOCKEY)) ? 'checked' : ''} onchange="handlePendingCheckboxChange(); event.stopPropagation();" style="width: 18px; height: 18px; cursor: pointer; accent-color: #4b9e6e; flex-shrink: 0;">`;
        }

        html += `
            <div class="quotation-card ${isSelected ? 'is-selected' : ''}" data-dockey="${qt.DOCKEY}" style="background: #fffaf0; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid ${borderColor}; cursor: pointer; display: flex; gap: 12px; align-items: flex-start; border: 1px solid #ead8b5;">
                ${checkboxHtml}
                <div style="flex: 1; min-width: 0;">
                    <div class="quotation-card__header-layout">
                        <div class="quotation-card__info">
                            <div class="quotation-card__info-grid">
                                <div class="quotation-card__field">
                                    <span class="quotation-card__field-label">QT Code</span>
                                    <div class="quotation-card__field-value">
                                        <span>${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                                    </div>
                                </div>
                                <div class="quotation-card__field">
                                    <span class="quotation-card__field-label">Date</span>
                                    <div class="quotation-card__field-value">${docDate}</div>
                                </div>
                            </div>
                        </div>
                        <div class="quotation-card__amount-col">
                            <span class="quotation-card__amount" style="background: ${badgeColor};">RM ${amount}</span>
                        </div>
                        <div class="quotation-card__button-col">
                            <div class="quotation-card__side-actions">
                                ${isDrafts && !hideStatus ? `<button class="edit-button" onclick="editQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #5a8fc4; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Edit</button>` : ''}
                                ${isPending && !hideStatus ? `<button class="edit-button" onclick="editQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #5a8fc4; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Edit</button>` : ''}
                                ${isPending && !hideStatus ? `<button class="activate-btn" onclick="activateQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #4b9e6e; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Reviewed</button>` : ''}
                                ${isReviewed && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, false);" style="background: #a65c5c; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Cancel</button>` : ''}
                                ${isCancelled && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, true);" style="background: #4b6e9e; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Restore</button>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    return html;
}

async function renderQuotationDetail(currentList, options = {}) {
    const panel = document.getElementById('quotation-detail-pane');
    if (!panel) return;

    const selected = (currentList || []).find((row) => Number(row.DOCKEY) === Number(selectedQuotationDockey));
    if (!selected) {
        panel.innerHTML = '<div class="quotation-detail-empty">Select a quotation to view details.</div>';
        return;
    }

    const hideStatus = hideQuotationStatusActionsFromPage();
    const filterTab = selected._filterTab || 'reviewed';
    const isPending = filterTab === 'pending';
    const isCancelled = filterTab === 'cancelled';
    const isReviewed = filterTab === 'reviewed';
    const isDrafts = filterTab === 'drafts';
    const amount = Number(selected.DOCAMT || 0).toFixed(2);
    const docDate = formatDateForDisplay(selected.DOCDATE);
    const validity = formatDateForDisplay(selected.VALIDITY);
    const companyName = selected.COMPANYNAME || 'N/A';
    const customerCode = selected.CODE || 'N/A';

    panel.innerHTML = `
        <div class="quotation-detail-head">
            <div>
                <div class="quotation-detail-title">${selected.DOCNO || ('DOCKEY #' + selected.DOCKEY)}</div>
                <div class="quotation-detail-sub">${companyName} (${customerCode})</div>
            </div>
            <div class="quotation-detail-amount">RM ${amount}</div>
        </div>
        <div class="quotation-detail-meta">
            <span><strong>Date:</strong> ${docDate}</span>
            <span><strong>Valid Until:</strong> ${validity}</span>
        </div>
        <div class="quotation-detail-actions">
            ${isDrafts && !hideStatus ? `<button class="edit-button" onclick="editQuotation(${selected.DOCKEY})">Edit</button>` : ''}
            ${isPending && !hideStatus ? `<button class="edit-button" onclick="editQuotation(${selected.DOCKEY})">Edit</button>` : ''}
            ${isPending && !hideStatus ? `<button class="activate-btn" onclick="activateQuotation(${selected.DOCKEY})">Reviewed</button>` : ''}
            ${isReviewed && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="toggleCancelledStatus(${selected.DOCKEY}, false)">Cancel</button>` : ''}
            ${isCancelled && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="toggleCancelledStatus(${selected.DOCKEY}, true)">Restore</button>` : ''}
        </div>
        <div class="quotation-detail-items" id="quotation-detail-items">
            <div class="quotation-detail-loading">Loading items...</div>
        </div>
    `;

    const detailContainer = document.getElementById('quotation-detail-items');
    try {
        const cacheKey = quotationDetailCacheKey(selected);
        let items = cacheKey ? quotationDetailCache.get(cacheKey) : null;
        if (!items) {
            const detailUrl = selected._sourceSlQtDraft
                ? `/api/get_draft_quotation_details?dockey=${encodeURIComponent(selected.DOCKEY)}`
                : `/api/get_quotation_details?dockey=${encodeURIComponent(selected.DOCKEY)}`;
            const response = await fetch(detailUrl);
            const data = await response.json();
            if (!data.success || !data.data || !Array.isArray(data.data.items)) {
                throw new Error(data.error || 'Failed to load items');
            }
            items = data.data.items;
            if (cacheKey) {
                quotationDetailCache.set(cacheKey, items);
            }
        }

        if (!items.length) {
            detailContainer.innerHTML = '<div class="quotation-detail-empty">No items</div>';
            return;
        }

        let itemsHtml = '<table class="quotation-items-table">';
        itemsHtml += '<colgroup><col style="width:36%" /><col style="width:16%" /><col style="width:14%" /><col style="width:16%" /><col style="width:18%" /></colgroup>';
        itemsHtml += '<thead><tr>';
        itemsHtml += '<th scope="col">Item</th><th scope="col">Price</th><th scope="col">Qty</th><th scope="col">Discount</th><th scope="col">Subtotal</th>';
        itemsHtml += '</tr></thead><tbody>';
        let total = 0;
        items.forEach((item) => {
            const qty = Number(item.QTY || 0).toFixed(2);
            const price = Number(item.UNITPRICE || 0).toFixed(2);
            const discount = Number(item.DISC || 0).toFixed(2);
            const discNum = Number(item.DISC || 0);
            const amountRow = Math.max(0, Number(item.QTY || 0) * Number(item.UNITPRICE || 0) - discNum).toFixed(2);
            total += parseFloat(amountRow);
            // SL_QTDTL.ITEMCODE can be NULL when the line is description-only; JSON null must not render as the string "null".
            const itemCode = item.ITEMCODE != null ? String(item.ITEMCODE).trim() : '';
            const description = item.DESCRIPTION != null ? String(item.DESCRIPTION).trim() : '';
            const codeLine = itemCode
                ? `<div style="font-weight: 600; color:#4f3b2a;">${itemCode.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`
                : '';
            const descLine = description
                ? `<div style="color: #6d5238; font-size: 11px;">${description.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`
                : '';
            const itemCell = codeLine || descLine
                ? `<td>${codeLine}${descLine}</td>`
                : '<td><span style="color:#6d5238;">—</span></td>';
            itemsHtml += '<tr>';
            itemsHtml += itemCell;
            itemsHtml += `<td>RM ${price}</td><td>${qty}</td><td>RM ${discount}</td><td style="font-weight: 600;">RM ${amountRow}</td>`;
            itemsHtml += '</tr>';
        });
        itemsHtml += `<tr class="quotation-items-total"><td colspan="4">TOTAL</td><td>RM ${total.toFixed(2)}</td></tr>`;
        itemsHtml += '</tbody></table>';
        detailContainer.innerHTML = itemsHtml;
    } catch (error) {
        console.error('Error loading quotation detail items:', error);
        detailContainer.innerHTML = '<div class="quotation-detail-error">Failed to load items</div>';
    }
}

function editQuotation(dockey) {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    window.location.href = `/admin/update-quotation?dockey=${dockey}`;
}

// Reviewed tab: batch cancel (CANCELLED status — same as /api/admin/delete_quotations)
function toggleSelectAllActive(event) {
    const isChecked = event.target.checked;
    const checkboxes = document.querySelectorAll('.quotation-checkbox-active');
    selectedActiveQuotations.clear();
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
        if (isChecked) {
            selectedActiveQuotations.add(parseInt(checkbox.dataset.dockey));
        }
    });
    
    updateActiveDeleteControls();
}

function handleActiveCheckboxChange() {
    selectedActiveQuotations.clear();
    const checkboxes = document.querySelectorAll('.quotation-checkbox-active');
    
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            selectedActiveQuotations.add(parseInt(checkbox.dataset.dockey));
        }
    });
    
    updateActiveDeleteControls();
}

function updateActiveDeleteControls() {
    const count = selectedActiveQuotations.size;
    const countSpan = document.getElementById('selected-count-active');
    const deleteBtn = document.getElementById('bulk-delete-active-btn');
    const selectAllCheckbox = document.getElementById('select-all-active');
    
    if (countSpan) countSpan.textContent = `${count} selected`;
    if (deleteBtn) deleteBtn.disabled = count === 0;
    
    if (selectAllCheckbox) {
        const allCheckboxes = document.querySelectorAll('.quotation-checkbox-active');
        const allChecked = allCheckboxes.length > 0 && Array.from(allCheckboxes).every(cb => cb.checked);
        const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
        selectAllCheckbox.checked = allChecked;
        selectAllCheckbox.indeterminate = someChecked && !allChecked;
    }
}

function toggleSelectAllPending(event) {
    const isChecked = event.target.checked;
    const checkboxes = document.querySelectorAll('.quotation-checkbox-pending');
    selectedPendingQuotations.clear();

    checkboxes.forEach((checkbox) => {
        checkbox.checked = isChecked;
        if (isChecked) {
            selectedPendingQuotations.add(parseInt(checkbox.dataset.dockey, 10));
        }
    });

    updatePendingReviewControls();
}

function handlePendingCheckboxChange() {
    selectedPendingQuotations.clear();
    document.querySelectorAll('.quotation-checkbox-pending').forEach((checkbox) => {
        if (checkbox.checked) {
            selectedPendingQuotations.add(parseInt(checkbox.dataset.dockey, 10));
        }
    });
    updatePendingReviewControls();
}

function updatePendingReviewControls() {
    const count = selectedPendingQuotations.size;
    const countSpan = document.getElementById('selected-count-pending');
    const reviewBtn = document.getElementById('bulk-review-pending-btn');
    const selectAllCheckbox = document.getElementById('select-all-pending');

    if (countSpan) countSpan.textContent = `${count} selected`;
    if (reviewBtn) reviewBtn.disabled = count === 0;

    if (selectAllCheckbox) {
        const allCheckboxes = document.querySelectorAll('.quotation-checkbox-pending');
        const allChecked = allCheckboxes.length > 0 && Array.from(allCheckboxes).every((cb) => cb.checked);
        const someChecked = Array.from(allCheckboxes).some((cb) => cb.checked);
        selectAllCheckbox.checked = allChecked;
        selectAllCheckbox.indeterminate = someChecked && !allChecked;
    }
}

window.performBulkReviewPending = async function performBulkReviewPending() {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    if (selectedPendingQuotations.size === 0) {
        return;
    }
    const dockeyArray = Array.from(selectedPendingQuotations);
    if (!confirm(`Mark ${dockeyArray.length} quotation(s) as reviewed?`)) {
        return;
    }

    try {
        const response = await fetch('/api/admin/batch_review_quotations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dockeyList: dockeyArray }),
        });
        const result = await response.json();

        if (result.success) {
            const n = result.reviewed_count != null ? result.reviewed_count : dockeyArray.length;
            const fail = result.failed_count || 0;
            const msg =
                fail > 0
                    ? `Marked ${n} as reviewed (${fail} failed).`
                    : `Marked ${n} quotation(s) as reviewed.`;
            showSuccessActive(msg);
            selectedPendingQuotations.clear();
            setQuotationTab('reviewed');
            setTimeout(() => loadQuotations(), 800);
        } else {
            showErrorActive(result.error || 'Batch review failed');
        }
    } catch (err) {
        showErrorActive('Error: ' + err.message);
    }
};

function showDeleteConfirmActive() {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    if (selectedActiveQuotations.size === 0) return;
    
    const modal = document.getElementById('delete-modal-active');
    if (!modal) {
        showErrorActive('Batch cancel dialog not found');
        return;
    }
    
    document.getElementById('delete-count-active').textContent = selectedActiveQuotations.size;
    modal.style.display = 'flex';
    
    document.getElementById('cancel-delete-active-btn').onclick = closeDeleteModalActive;
    document.getElementById('confirm-delete-active-btn').onclick = performBulkDeleteActive;
}

function closeDeleteModalActive() {
    const modal = document.getElementById('delete-modal-active');
    if (modal) modal.style.display = 'none';
}

async function performBulkDeleteActive() {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    const dockeyArray = Array.from(selectedActiveQuotations);
    closeDeleteModalActive();
    
    if (dockeyArray.length === 0) {
        showErrorActive('No quotations selected');
        return;
    }
    
    try {
        const payload = { dockeyList: dockeyArray };
        
        const response = await fetch('/api/admin/delete_quotations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        if (result.success) {
            const n = result.cancelled_count != null ? result.cancelled_count : (result.deleted_count != null ? result.deleted_count : dockeyArray.length);
            const fail = result.failed_count || 0;
            const msg =
                fail > 0
                    ? `Batch cancel: ${n} quotation(s) set to CANCELLED (${fail} failed).`
                    : `Batch cancel: ${n} quotation(s) set to CANCELLED.`;
            showSuccessActive(msg);
            selectedActiveQuotations.clear();
            setTimeout(() => loadQuotations(), 1500);
        } else {
            showErrorActive(result.error || 'Batch cancel failed');
        }
    } catch (error) {
        showErrorActive('Batch cancel error: ' + error.message);
    }
}

function showSuccessActive(message) {
    const messageEl = document.getElementById('success-message-active');
    if (!messageEl) {
        alert('✓ ' + message);
        return;
    }
    messageEl.querySelector('span').textContent = '✓ ' + message;
    messageEl.style.display = 'block';
    setTimeout(() => {
        messageEl.style.display = 'none';
    }, 4000);
}

function showErrorActive(message) {
    const messageEl = document.getElementById('error-message-active');
    if (!messageEl) {
        alert('Error: ' + message);
        return;
    }
    messageEl.querySelector('span').textContent = message;
    messageEl.style.display = 'block';
    setTimeout(() => {
        messageEl.style.display = 'none';
    }, 4000);
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadQuotations();
    if (!isCustomerMyQuotationsPage()) {
        await setupCompanyFilter();
    }
});
