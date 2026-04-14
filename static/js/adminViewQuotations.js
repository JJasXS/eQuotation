let activeQuotationsCache = [];
let cancelledQuotationsCache = [];
let pendingQuotationsCache = [];
let companyFilter = '';
let currentTab = 'active';
let selectedActiveQuotations = new Set();

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

window.toggleCancelledStatus = async function(dockey, isCancelled) {
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
            setQuotationTab(currentTab);
        } else {
            alert('Failed to update status: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('[ERROR] toggleCancelledStatus exception:', err);
        alert('Error updating status: ' + err);
    }
};

window.activateQuotation = async function(dockey) {
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
            setQuotationTab('active'); // Switch to active tab to show the newly activated quotation
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
        setQuotationTab(currentTab);
    };

    clearBtn.onclick = function() {
        companyFilter = '';
        dropdown.value = '';
        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
        setQuotationTab(currentTab);
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
        setQuotationTab(currentTab);
    };
    clearBtn.onclick = function() {
        fromEl.value = '';
        toEl.value = '';
        adminDateFrom = '';
        adminDateTo = '';
        listVisibleLimit = { active: 5, pending: 5, cancelled: 5 };
        setQuotationTab(currentTab);
    };

    fromEl.value = adminDateFrom || '';
    toEl.value = adminDateTo || '';
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
                <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;">
                    <label style="display: flex; align-items: center; gap: 6px; color: #9ba7b6; font-size: 13px;">From
                        <input type="date" id="quotation-date-from" style="padding: 6px 10px; border-radius: 6px; border: 1px solid #3d4654; background: #232a36; color: #e4e9f1; font-size: 13px;">
                    </label>
                    <label style="display: flex; align-items: center; gap: 6px; color: #9ba7b6; font-size: 13px;">To
                        <input type="date" id="quotation-date-to" style="padding: 6px 10px; border-radius: 6px; border: 1px solid #3d4654; background: #232a36; color: #e4e9f1; font-size: 13px;">
                    </label>
                    <button type="button" id="quotation-date-apply" style="padding: 8px 12px; border-radius: 6px; background: #4b6e9e; color: #fff; border: none; cursor: pointer; font-size: 13px;">Apply</button>
                    <button type="button" id="quotation-date-clear" style="padding: 8px 12px; border-radius: 6px; background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; cursor: pointer; font-size: 13px;">Clear dates</button>
                </div>
                <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 12px;">
                    <select id="company-filter-dropdown" style="padding: 8px 12px; border-radius: 6px; border: 1px solid #3d4654; background: #232a36; color: #e4e9f1; font-size: 13px; width: 240px;">
                        <option value="">All Companies</option>
                    </select>
                    <button id="company-filter-clear" style="padding: 8px 12px; border-radius: 6px; background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; cursor: pointer; font-size: 13px;">Clear</button>
                </div>

                <div class="approvals-tabs" style="margin: 0 -16px;">
                    <button id="tab-active" class="approval-tab" onclick="setQuotationTab('active')">
                        Active (${activeQuotationsCache.length})
                    </button>
                    <button id="tab-pending" class="approval-tab" onclick="setQuotationTab('pending')">
                        Pending (${pendingQuotationsCache.length})
                    </button>
                    <button id="tab-cancelled" class="approval-tab" onclick="setQuotationTab('cancelled')">
                        Cancelled (${cancelledQuotationsCache.length})
                    </button>
                </div>

                <div id="quotation-tab-content" style="padding-top: 12px;"></div>
            </div>
        `;

        content.innerHTML = html;
        setupDateFilter();
        setQuotationTab(currentTab);
    } catch (error) {
        content.innerHTML = '<div style="padding: 20px; text-align: center; color: #ff6b6b;">Failed to load quotations.</div>';
        console.error('Error loading quotations:', error);
    }
}

function setQuotationTab(tabName) {
    currentTab = tabName;

    const tabContent = document.getElementById('quotation-tab-content');
    const activeBtn = document.getElementById('tab-active');
    const cancelledBtn = document.getElementById('tab-cancelled');
    const pendingBtn = document.getElementById('tab-pending');
    if (!tabContent || !activeBtn || !cancelledBtn || !pendingBtn) return;

    const { active: activeList, pending: pendingList, cancelled: cancelledList } = getFilteredAdminLists();

    activeBtn.textContent = `Active (${activeList.length})`;
    pendingBtn.textContent = `Pending (${pendingList.length})`;
    cancelledBtn.textContent = `Cancelled (${cancelledList.length})`;

    activeBtn.classList.remove('active');
    pendingBtn.classList.remove('active');
    cancelledBtn.classList.remove('active');

    let tabKey = 'active';
    let html = '';
    if (tabName === 'cancelled') {
        html = renderQuotationList(cancelledList, { isCancelled: true, isPending: false }, 'cancelled');
        cancelledBtn.classList.add('active');
        tabKey = 'cancelled';
    } else if (tabName === 'pending') {
        html = renderQuotationList(pendingList, { isCancelled: false, isPending: true }, 'pending');
        pendingBtn.classList.add('active');
        tabKey = 'pending';
    } else {
        html = renderQuotationList(activeList, { isCancelled: false, isPending: false }, 'active');
        activeBtn.classList.add('active');
        tabKey = 'active';
    }

    tabContent.innerHTML = html;

    const moreBtn = tabContent.querySelector('.quotation-load-more-btn');
    if (moreBtn) {
        moreBtn.addEventListener('click', function handler() {
            listVisibleLimit[tabKey] = (listVisibleLimit[tabKey] || 5) + 10;
            setQuotationTab(tabKey);
        });
    }

    document.querySelectorAll('.quotation-card').forEach(card => {
        card.addEventListener('click', function(e) {
            if (
                !e.target.closest('.edit-button')
                && !e.target.closest('.activate-btn')
                && !e.target.closest('.toggle-cancelled-btn')
                && !e.target.closest('.quotation-checkbox-active')
            ) {
                toggleQuotationItems(this);
            }
        });
    });
}

function renderQuotationList(list, options = {}, tabKey = 'active') {
    const isCancelled = !!options.isCancelled;
    const isPending = !!options.isPending;
    const isActive = !isCancelled && !isPending;

    if (!list || list.length === 0) {
        return '<div style="padding: 12px; text-align: center; color: #888;">No quotations</div>';
    }

    const limit = listVisibleLimit[tabKey] != null ? listVisibleLimit[tabKey] : 5;
    const pageList = list.slice(0, limit);
    const hasMore = list.length > pageList.length;

    let controlsHtml = '';
    if (isActive) {
        controlsHtml = `
            <div class="active-tab-controls show">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 500; user-select: none; color: #e4e9f1;">
                    <input type="checkbox" id="select-all-active" onchange="toggleSelectAllActive(event)" style="width: 18px; height: 18px; cursor: pointer; accent-color: #dc3545;">
                    Select All
                </label>
                <button id="bulk-delete-active-btn" onclick="showDeleteConfirmActive()" class="btn-delete-active" disabled>
                    Delete Selected
                </button>
                <span id="selected-count-active" style="margin-left: auto; font-size: 14px; color: #9ba7b6; font-weight: 500;">0 selected</span>
            </div>
        `;
    }

    let html = controlsHtml;
    pageList.forEach(qt => {
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = formatDateForDisplay(qt.DOCDATE);
        const validity = formatDateForDisplay(qt.VALIDITY);
        const companyName = qt.COMPANYNAME || 'N/A';
        const customerCode = qt.CODE || 'N/A';
        const borderColor = isPending ? '#b0892f' : (isCancelled ? '#a65c5c' : '#4b6e9e');
        const badgeColor = isPending ? '#b0892f' : (isCancelled ? '#a65c5c' : '#4b6e9e');
        
        const checkboxHtml = isActive ? `<input type="checkbox" class="quotation-checkbox-active" data-dockey="${qt.DOCKEY}" onchange="handleActiveCheckboxChange(); event.stopPropagation();" style="width: 18px; height: 18px; cursor: pointer; accent-color: #dc3545; flex-shrink: 0;">` : '';

        html += `
            <div class="quotation-card" data-dockey="${qt.DOCKEY}" style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid ${borderColor}; cursor: pointer; display: flex; gap: 12px; align-items: flex-start;">
                ${checkboxHtml}
                <div style="flex: 1; min-width: 0;">
                    <div class="quotation-card__header-layout">
                        <div class="quotation-card__info">
                            <div class="quotation-card__info-grid">
                                <div class="quotation-card__field">
                                    <span class="quotation-card__field-label">QT Code</span>
                                    <div class="quotation-card__field-value">
                                        <span class="expand-arrow" style="color: #9ba7b6; font-size: 11px; transition: transform 0.2s;">▼</span>
                                        <span>${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                                    </div>
                                </div>
                                <div class="quotation-card__field">
                                    <span class="quotation-card__field-label">Customer Name</span>
                                    <div class="quotation-card__field-value quotation-card__field-value--wrap">${companyName} (${customerCode})</div>
                                </div>
                                <div class="quotation-card__field">
                                    <span class="quotation-card__field-label">Date</span>
                                    <div class="quotation-card__field-value">${docDate}</div>
                                </div>
                                <div class="quotation-card__field">
                                    <span class="quotation-card__field-label">Valid Until</span>
                                    <div class="quotation-card__field-value">${validity}</div>
                                </div>
                            </div>
                        </div>
                        <div class="quotation-card__amount-col">
                            <span class="quotation-card__amount" style="background: ${badgeColor};">RM ${amount}</span>
                        </div>
                        <div class="quotation-card__button-col">
                            <div class="quotation-card__side-actions">
                                ${isPending ? `<button class="edit-button" onclick="editQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #5a8fc4; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Edit</button>` : ''}
                                ${isPending ? `<button class="activate-btn" onclick="activateQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #4b9e6e; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Activate</button>` : ''}
                                ${!isPending && !isCancelled ? `<button class="toggle-cancelled-btn" onclick="console.log('[BUTTON CLICK] DOCKEY:', ${qt.DOCKEY}, 'isCancelled param:', ${isCancelled}); event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, ${isCancelled});" style="background: #a65c5c; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Cancel</button>` : ''}
                                ${isCancelled ? `<button class="toggle-cancelled-btn" onclick="console.log('[BUTTON CLICK] DOCKEY:', ${qt.DOCKEY}, 'isCancelled param:', ${isCancelled}); event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, ${isCancelled});" style="background: #4b6e9e; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; white-space: nowrap;">Restore</button>` : ''}
                            </div>
                        </div>
                    </div>
                    <div class="quotation-items" style="display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #3d4654;">
                        <div style="text-align: center; color: #888; padding: 8px;">Loading items...</div>
                    </div>
                </div>
            </div>
        `;
    });

    if (hasMore) {
        html += `
            <div style="text-align: center; padding: 12px;">
                <button type="button" class="quotation-load-more-btn" style="background: #3d4654; color: #e4e9f1; border: 1px solid #5a6575; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 13px;">more</button>
            </div>
        `;
    }

    return html;
}

async function toggleQuotationItems(card) {
    const itemsDiv = card.querySelector('.quotation-items');
    const arrow = card.querySelector('.expand-arrow');
    const dockey = card.dataset.dockey;

    if (itemsDiv.style.display === 'none') {
        if (!itemsDiv.dataset.loaded) {
            try {
                const response = await fetch(`/api/get_quotation_details?dockey=${dockey}`);
                const data = await response.json();

                if (data.success && data.data.items) {
                    const items = data.data.items;
                    let itemsHtml = '';

                    if (items.length === 0) {
                        itemsHtml = '<div style="color: #888; padding: 8px; text-align: center;">No items</div>';
                    } else {
                        itemsHtml = '<table class="quotation-items-table">';
                            itemsHtml += '<colgroup><col style="width:36%" /><col style="width:16%" /><col style="width:14%" /><col style="width:16%" /><col style="width:18%" /></colgroup>';
                            itemsHtml += '<thead><tr>';
                            itemsHtml += '<th scope="col">Item</th>';
                            itemsHtml += '<th scope="col">Price</th>';
                            itemsHtml += '<th scope="col">Qty</th>';
                            itemsHtml += '<th scope="col">Discount</th>';
                            itemsHtml += '<th scope="col">Subtotal</th>';
                            itemsHtml += '</tr></thead><tbody>';

                            let total = 0;
                            items.forEach(item => {
                                const qty = Number(item.QTY || 0).toFixed(2);
                                const price = Number(item.UNITPRICE || 0).toFixed(2);
                                const discount = Number(item.DISC || 0).toFixed(2);
                                const amount = Math.max(0, (item.QTY * item.UNITPRICE) - (item.DISC || 0)).toFixed(2);
                                total += parseFloat(amount);
                                itemsHtml += '<tr>';
                                itemsHtml += `<td><div style="font-weight: 500;">${item.ITEMCODE}</div><div style="color: #9ba7b6; font-size: 11px;">${item.DESCRIPTION}</div></td>`;
                                itemsHtml += `<td>RM ${price}</td>`;
                                itemsHtml += `<td>${qty}</td>`;
                                itemsHtml += `<td>RM ${discount}</td>`;
                                itemsHtml += `<td style="font-weight: 600;">RM ${amount}</td>`;
                                itemsHtml += '</tr>';
                            });
                            itemsHtml += `<tr class="quotation-items-total"><td colspan="4">TOTAL</td><td>RM ${total.toFixed(2)}</td></tr>`;
                            itemsHtml += '</tbody></table>';
                    }

                    itemsDiv.innerHTML = itemsHtml;
                    itemsDiv.dataset.loaded = 'true';
                } else {
                    itemsDiv.innerHTML = '<div style="color: #ff6b6b; padding: 8px; text-align: center;">Failed to load items</div>';
                }
            } catch (error) {
                console.error('Error fetching quotation items:', error);
                itemsDiv.innerHTML = '<div style="color: #ff6b6b; padding: 8px; text-align: center;">Error loading items</div>';
            }
        }

        itemsDiv.style.display = 'block';
        arrow.style.transform = 'rotate(-180deg)';
    } else {
        itemsDiv.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

function editQuotation(dockey) {
    // Redirect to update quotation page
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
