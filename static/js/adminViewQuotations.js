let activeQuotationsCache = [];
let cancelledQuotationsCache = [];
let pendingQuotationsCache = [];
let companyFilter = '';
/** One or more of: active, pending, cancelled. At least one must stay selected. */
let selectedQuotationTabFilters = new Set(['active']);
let selectedActiveQuotations = new Set();
let selectedQuotationDockey = null;
const quotationDetailCache = new Map();

/** Date filter (YYYY-MM-DD from input type=date) */
let adminDateFrom = '';
let adminDateTo = '';
/** First page shows 5 rows; each "more" adds 10 */
let listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };

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
    const a = filterQuotationsByCompany(filterQuotationsByDate(activeQuotationsCache, df, dt));
    const p = filterQuotationsByCompany(filterQuotationsByDate(pendingQuotationsCache, df, dt));
    const c = filterQuotationsByCompany(filterQuotationsByDate(cancelledQuotationsCache, df, dt));
    return { active: a, pending: p, cancelled: c };
}

function isPendingQuotation(qt) {
    // Pending: CANCELLED not set yet, or SL_QT.UPDATECOUNT is null.
    // Active/Cancelled only when both CANCELLED and UPDATECOUNT are set (not pending).
    const cancelledUnset = qt.CANCELLED === null || qt.CANCELLED === undefined;
    const updateCountUnset = qt.UPDATECOUNT === null || qt.UPDATECOUNT === undefined;
    return cancelledUnset || updateCountUnset;
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
    
    if (!confirm('Are you sure you want to activate this quotation?')) {
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
            setQuotationTab('active');
        } else {
            alert('Failed to activate quotation: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('[ERROR] activateQuotation exception:', err);
        alert('Error activating quotation: ' + err);
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
        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
        refreshQuotationListView();
    };

    clearBtn.onclick = function() {
        companyFilter = '';
        dropdown.value = '';
        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
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
        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
        refreshQuotationListView();
    };
    clearBtn.onclick = function() {
        fromEl.value = '';
        toEl.value = '';
        adminDateFrom = '';
        adminDateTo = '';
        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
        refreshQuotationListView();
    };

    fromEl.value = adminDateFrom || '';
    toEl.value = adminDateTo || '';
}

function getCombinedQuotationList() {
    const { active, pending, cancelled } = getFilteredAdminLists();
    const out = [];
    const parts = [
        ['active', active],
        ['pending', pending],
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
 * Toggle a status filter (Active / Pending / Cancelled). Multiple can be on at once.
 * At least one filter must remain selected.
 */
window.toggleQuotationFilter = function (name) {
    if (!['active', 'pending', 'cancelled'].includes(name)) {
        return;
    }
    if (selectedQuotationTabFilters.has(name) && selectedQuotationTabFilters.size <= 1) {
        return;
    }
    if (selectedQuotationTabFilters.has(name)) {
        selectedQuotationTabFilters.delete(name);
    } else {
        selectedQuotationTabFilters.add(name);
    }
    if (selectedQuotationTabFilters.size === 0) {
        selectedQuotationTabFilters.add('active');
    }
    refreshQuotationListView();
};

function refreshQuotationListView() {
    const tabContent = document.getElementById('quotation-tab-content');
    const activeBtn = document.getElementById('tab-active');
    const cancelledBtn = document.getElementById('tab-cancelled');
    const pendingBtn = document.getElementById('tab-pending');
    if (!tabContent || !activeBtn || !cancelledBtn || !pendingBtn) {
        return;
    }

    const { active: activeList, pending: pendingList, cancelled: cancelledList } = getFilteredAdminLists();

    activeBtn.textContent = `Active (${activeList.length})`;
    pendingBtn.textContent = `Pending (${pendingList.length})`;
    cancelledBtn.textContent = `Cancelled (${cancelledList.length})`;

    activeBtn.classList.toggle('active', selectedQuotationTabFilters.has('active'));
    pendingBtn.classList.toggle('active', selectedQuotationTabFilters.has('pending'));
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
            ) {
                selectedQuotationDockey = Number(this.dataset.dockey);
                refreshQuotationListView();
            }
        });
    });

    updateActiveDeleteControls();
    renderQuotationDetail(visibleList, {});
}

async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) return;

    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    try {
        // Fetch all quotations once; tabs use CANCELLED + UPDATECOUNT (see isPendingQuotation).
        const response = await fetch('/api/admin/get_all_quotations');
        const data = await response.json();

        if (!data.success) {
            const message = data.error ? String(data.error) : 'Failed to load quotations';
            content.innerHTML = `<div style="padding: 20px; text-align: center; color: #ff6b6b;">${message}</div>`;
            return;
        }

        const allQuotations = data.data || [];
        
        // Debug: log raw data with more detail
        console.log('[DEBUG] Total quotations fetched:', allQuotations.length);
        console.log('[DEBUG] Full sample data:', JSON.stringify(allQuotations.slice(0, 2), null, 2));
        
        pendingQuotationsCache = allQuotations.filter(qt => isPendingQuotation(qt));
        cancelledQuotationsCache = allQuotations.filter(qt => !isPendingQuotation(qt) && qt.CANCELLED === true);
        activeQuotationsCache = allQuotations.filter(qt => !isPendingQuotation(qt) && qt.CANCELLED === false);

        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
        
        console.log('[DEBUG] Filtered caches - Active:', activeQuotationsCache.length, 'Cancelled:', cancelledQuotationsCache.length, 'Pending:', pendingQuotationsCache.length);

        const html = `
            <div class="admin-quotations-view" style="padding: 16px;">
                <div class="quotation-page-header">
                    <div class="quotation-page-header-controls">
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
                    </div>
                    <div class="approvals-tabs quotation-page-header-tabs">
                        <button type="button" id="tab-active" class="approval-tab ${selectedQuotationTabFilters.has('active') ? 'active' : ''}" onclick="toggleQuotationFilter('active')">
                            Active (${activeQuotationsCache.length})
                        </button>
                        <button type="button" id="tab-pending" class="approval-tab ${selectedQuotationTabFilters.has('pending') ? 'active' : ''}" onclick="toggleQuotationFilter('pending')">
                            Pending (${pendingQuotationsCache.length})
                        </button>
                        <button type="button" id="tab-cancelled" class="approval-tab ${selectedQuotationTabFilters.has('cancelled') ? 'active' : ''}" onclick="toggleQuotationFilter('cancelled')">
                            Cancelled (${cancelledQuotationsCache.length})
                        </button>
                    </div>
                </div>
                <div id="quotation-tab-content" style="padding-top: 12px;"></div>
            </div>
        `;

        content.innerHTML = html;
        setupDateFilter();
        refreshQuotationListView();
    } catch (error) {
        content.innerHTML = '<div style="padding: 20px; text-align: center; color: #ff6b6b;">Failed to load quotations.</div>';
        console.error('Error loading quotations:', error);
    }
}

function setQuotationTab(tabName) {
    if (!['active', 'pending', 'cancelled'].includes(tabName)) {
        return;
    }
    selectedQuotationTabFilters = new Set([tabName]);
    refreshQuotationListView();
}

function renderQuotationList(list, options = {}, tabKey = 'active', hasMore = false) {
    if (!list || list.length === 0) {
        return '<div style="padding: 12px; text-align: center; color: #7b5a36;">No quotations</div>';
    }

    const hideStatus = hideQuotationStatusActionsFromPage();
    const hasActiveInList = list.some((qt) => (qt._filterTab || 'active') === 'active');
    let controlsHtml = '';
    if (hasActiveInList && !hideStatus) {
        controlsHtml = `
            <div class="active-tab-controls show">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 500; user-select: none; color: #5c4028;">
                    <input type="checkbox" id="select-all-active" onchange="toggleSelectAllActive(event)" style="width: 18px; height: 18px; cursor: pointer; accent-color: #dc3545;">
                    Select All
                </label>
                <button id="bulk-delete-active-btn" onclick="showDeleteConfirmActive()" class="btn-delete-active" disabled>
                    Delete Selected
                </button>
                <span id="selected-count-active" style="margin-left: auto; font-size: 14px; color: #87684d; font-weight: 500;">0 selected</span>
            </div>
        `;
    }

    let html = controlsHtml;
    list.forEach(qt => {
        const filterTab = qt._filterTab || 'active';
        const isPending = filterTab === 'pending';
        const isCancelled = filterTab === 'cancelled';
        const isActive = filterTab === 'active';
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = formatDateForDisplay(qt.DOCDATE);
        const borderColor = isPending ? '#b0892f' : (isCancelled ? '#a65c5c' : '#4b6e9e');
        const badgeColor = isPending ? '#b0892f' : (isCancelled ? '#a65c5c' : '#4b6e9e');
        const isSelected = Number(qt.DOCKEY) === Number(selectedQuotationDockey);
        
        const checkboxHtml =
            !hideStatus && isActive
                ? `<input type="checkbox" class="quotation-checkbox-active" data-dockey="${qt.DOCKEY}" ${selectedActiveQuotations.has(Number(qt.DOCKEY)) ? 'checked' : ''} onchange="handleActiveCheckboxChange(); event.stopPropagation();" style="width: 18px; height: 18px; cursor: pointer; accent-color: #dc3545; flex-shrink: 0;">`
                : '';

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
                                ${isPending && !hideStatus ? `<button class="edit-button" onclick="editQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #5a8fc4; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Edit</button>` : ''}
                                ${isPending && !hideStatus ? `<button class="activate-btn" onclick="activateQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #4b9e6e; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Activate</button>` : ''}
                                ${!isPending && !isCancelled && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="console.log('[BUTTON CLICK] DOCKEY:', ${qt.DOCKEY}, 'isCancelled param:', ${isCancelled}); event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, ${isCancelled});" style="background: #a65c5c; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Cancel</button>` : ''}
                                ${isCancelled && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="console.log('[BUTTON CLICK] DOCKEY:', ${qt.DOCKEY}, 'isCancelled param:', ${isCancelled}); event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, ${isCancelled});" style="background: #4b6e9e; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Restore</button>` : ''}
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
    const filterTab = selected._filterTab || 'active';
    const isPending = filterTab === 'pending';
    const isCancelled = filterTab === 'cancelled';
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
            ${isPending && !hideStatus ? `<button class="edit-button" onclick="editQuotation(${selected.DOCKEY})">Edit</button>` : ''}
            ${isPending && !hideStatus ? `<button class="activate-btn" onclick="activateQuotation(${selected.DOCKEY})">Activate</button>` : ''}
            ${!isPending && !isCancelled && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="toggleCancelledStatus(${selected.DOCKEY}, false)">Cancel</button>` : ''}
            ${isCancelled && !hideStatus ? `<button class="toggle-cancelled-btn" onclick="toggleCancelledStatus(${selected.DOCKEY}, true)">Restore</button>` : ''}
        </div>
        <div class="quotation-detail-items" id="quotation-detail-items">
            <div class="quotation-detail-loading">Loading items...</div>
        </div>
    `;

    const detailContainer = document.getElementById('quotation-detail-items');
    try {
        let items = quotationDetailCache.get(Number(selected.DOCKEY));
        if (!items) {
            const response = await fetch(`/api/get_quotation_details?dockey=${selected.DOCKEY}`);
            const data = await response.json();
            if (!data.success || !data.data || !Array.isArray(data.data.items)) {
                throw new Error(data.error || 'Failed to load items');
            }
            items = data.data.items;
            quotationDetailCache.set(Number(selected.DOCKEY), items);
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
            const amountRow = Math.max(0, (item.QTY * item.UNITPRICE) - (item.DISC || 0)).toFixed(2);
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

// Active Tab Delete Functions
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

function showDeleteConfirmActive() {
    if (hideQuotationStatusActionsFromPage()) {
        return;
    }
    if (selectedActiveQuotations.size === 0) return;
    
    const modal = document.getElementById('delete-modal-active');
    if (!modal) {
        showErrorActive('Delete modal not found');
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
            showSuccessActive(`${result.deleted_count || dockeyArray.length} quotation(s) deleted successfully`);
            selectedActiveQuotations.clear();
            setTimeout(() => loadQuotations(), 1500);
        } else {
            showErrorActive(result.error || 'Failed to delete quotations');
        }
    } catch (error) {
        showErrorActive('Error deleting quotations: ' + error.message);
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
    await setupCompanyFilter();
});
