let activeQuotationsCache = [];
let cancelledQuotationsCache = [];
let companyFilter = '';

async function getAllUniqueCompanyNames() {
    try {
        console.log('[DEBUG] Fetching company names from database...');
        const response = await fetch('/api/get_company_names');
        const data = await response.json();
        
        if (data.success) {
            console.log('[DEBUG] Fetched companies:', data.data);
            return data.data || [];
        } else {
            console.error('[DEBUG] Failed to fetch companies:', data.error);
            return [];
        }
    } catch (error) {
        console.error('[DEBUG] Error fetching company names:', error);
        return [];
    }
}
async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) return;

    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    try {
        // Fetch active and cancelled quotations separately
        const [activeRes, cancelledRes] = await Promise.all([
            fetch('/api/admin/get_all_quotations?cancelled=false'),
            fetch('/api/admin/get_all_quotations?cancelled=true')
        ]);
        const activeData = await activeRes.json();
        const cancelledData = await cancelledRes.json();

        if (!activeData.success || !cancelledData.success) {
            content.innerHTML = `<div style="padding: 20px; text-align: center; color: #ff6b6b;">Failed to load quotations</div>`;
            return;
        }

        activeQuotationsCache = activeData.data || [];
        cancelledQuotationsCache = cancelledData.data || [];

        console.log(`[DEBUG] Active quotations: ${activeQuotationsCache.length}`, activeQuotationsCache);
        console.log(`[DEBUG] Cancelled quotations: ${cancelledQuotationsCache.length}`, cancelledQuotationsCache);

        let html = `
            <div style="padding: 16px;">
                <div style="display: flex; gap: 8px; margin-bottom: 12px; border-bottom: 1px solid #3d4654; padding-bottom: 10px;">
                    <button id="tab-active" onclick="setQuotationTab('active')" style="background: #4b6e9e; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        Active (${activeQuotationsCache.length})
                    </button>
                    <button id="tab-cancelled" onclick="setQuotationTab('cancelled')" style="background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        Cancelled (${cancelledQuotationsCache.length})
                    </button>
                </div>
                <div id="quotation-tab-content" style="background: #232a36; border: 1px solid #3d4654; border-radius: 8px; padding: 12px;"></div>
            </div>
        `;

        content.innerHTML = html;
        setQuotationTab('active');
    } catch (error) {
        content.innerHTML = '<div style="padding: 20px; text-align: center; color: #ff6b6b;">Failed to load quotations.</div>';
        console.error('Error loading quotations:', error);
    }
}

function setQuotationTab(tabName) {
    console.log(`[DEBUG] Switching to tab: ${tabName}`);
    const tabContent = document.getElementById('quotation-tab-content');
    const activeBtn = document.getElementById('tab-active');
    const cancelledBtn = document.getElementById('tab-cancelled');
    if (!tabContent || !activeBtn || !cancelledBtn) return;

    if (tabName === 'cancelled') {
        console.log(`[DEBUG] Rendering cancelled tab with ${cancelledQuotationsCache.length} items`);
        tabContent.innerHTML = renderQuotationList(cancelledQuotationsCache, true);
        cancelledBtn.style.background = '#a65c5c';
        cancelledBtn.style.color = '#fff';
        cancelledBtn.style.border = 'none';
        activeBtn.style.background = '#2d3440';
        activeBtn.style.color = '#9ba7b6';
        activeBtn.style.border = '1px solid #3d4654';
    } else {
        console.log(`[DEBUG] Rendering active tab with ${activeQuotationsCache.length} items`);
        tabContent.innerHTML = renderQuotationList(activeQuotationsCache, false);
        activeBtn.style.background = '#4b6e9e';
        activeBtn.style.color = '#fff';
        activeBtn.style.border = 'none';
        cancelledBtn.style.background = '#2d3440';
        cancelledBtn.style.color = '#9ba7b6';
        cancelledBtn.style.border = '1px solid #3d4654';
    }

    document.querySelectorAll('.quotation-card').forEach(card => {
        card.addEventListener('click', function(e) {
            // Don't toggle if clicking on edit button
            if (!e.target.closest('.edit-button')) {
                toggleQuotationItems(this);
            }
        });
    });
}

function renderQuotationList(list, isCancelled) {
    if (!list || list.length === 0) {
        return '<div style="padding: 12px; text-align: center; color: #888;">No quotations</div>';
    }

    let html = '';
    list.forEach(qt => {
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = qt.DOCDATE || '-';
        const validity = qt.VALIDITY || '-';
        const description = qt.DESCRIPTION || 'Quotation';
        const companyName = qt.COMPANYNAME || 'N/A';
        const customerCode = qt.CODE || 'N/A';
        const borderColor = isCancelled ? '#a65c5c' : '#4b6e9e';
        const badgeColor = isCancelled ? '#a65c5c' : '#4b6e9e';

        html += `
            <div class="quotation-card" data-dockey="${qt.DOCKEY}" style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid ${borderColor}; cursor: pointer; width: auto;">
                <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 12px;">
                    <span class="expand-arrow" style="color: #9ba7b6; font-size: 12px; transition: transform 0.2s; flex-shrink: 0;">▼</span>
                    <span style="font-weight: 600; color: #e4e9f1; flex-shrink: 0;">${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                    <span style="color: #9ba7b6; font-size: 13px;">Customer: ${companyName} (${customerCode})</span>
                    <span style="color: #9ba7b6; font-size: 13px; white-space: nowrap;">Date: ${docDate} | Valid Until: ${validity}</span>
                    <span style="background: ${badgeColor}; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; flex-shrink: 0;">RM ${amount}</span>
                    ${!isCancelled ? `<button class="edit-button" onclick="editQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #5a8fc4; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; white-space: nowrap; flex-shrink: 0;">Edit</button>` : ''}
                    <button class="toggle-cancelled-btn" onclick="event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, ${isCancelled})" style="background: ${isCancelled ? '#4b6e9e' : '#a65c5c'}; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; white-space: nowrap; flex-shrink: 0;">
                        ${isCancelled ? 'Restore' : 'Cancel'}
                    </button>
                </div>
                <div class="quotation-items" style="display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #3d4654;">
                    <div style="text-align: center; color: #888; padding: 8px;">Loading items...</div>
                </div>
            </div>
        `;
    // Toggle CANCELLED status for a quotation (exposed globally)
    window.toggleCancelledStatus = async function(dockey, isCancelled) {
        try {
            const newStatus = !isCancelled;
            const response = await fetch(`/api/admin/update_quotation_cancelled`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dockey, cancelled: newStatus })
            });
            const data = await response.json();
            if (data.success) {
                loadQuotations();
            } else {
                alert('Failed to update status: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            alert('Error updating status: ' + err);
        }
    }
    });

    return html;
}

async function toggleQuotationItems(card) {
    const itemsDiv = card.querySelector('.quotation-items');
    const arrow = card.querySelector('.expand-arrow');
    const dockey = card.dataset.dockey;

    if (itemsDiv.style.display === 'none') {
        // Expand - fetch items if not loaded
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
                        itemsHtml = '<table style="width: 100%; border-collapse: collapse;">';
                        itemsHtml += '<thead><tr style="color: #9ba7b6; font-size: 12px; text-align: left;">';
                        itemsHtml += '<th style="padding: 6px;">Item</th>';
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Qty</th>';
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Price</th>';
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Amount</th>';
                        itemsHtml += '</tr></thead><tbody>';

                        items.forEach(item => {
                            const qty = Number(item.QTY || 0).toFixed(2);
                            const price = Number(item.UNITPRICE || 0).toFixed(2);
                            const amount = Number(item.AMOUNT || 0).toFixed(2);

                            itemsHtml += '<tr style="color: #e4e9f1; font-size: 13px; border-top: 1px solid #3d4654;">';
                            itemsHtml += `<td style="padding: 8px 6px;"><div style="font-weight: 500;">${item.ITEMCODE}</div><div style="color: #9ba7b6; font-size: 11px;">${item.DESCRIPTION}</div></td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right;">${qty}</td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right;">RM ${price}</td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right;">RM ${amount}</td>`;
                            itemsHtml += '</tr>';
                        });

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
        // Collapse
        itemsDiv.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

function editQuotation(dockey) {
    // Placeholder for edit functionality - will be implemented later
    alert(`Edit quotation DOCKEY: ${dockey}\nEdit functionality coming soon!`);
    console.log('Edit quotation:', dockey);
}


// Load quotations and setup filter on page load
document.addEventListener('DOMContentLoaded', () => {
    loadQuotations();
    setupCompanyFilter();
});

function filterQuotationsByCompany(list) {
    if (!companyFilter) {
        console.log('[DEBUG] No company filter, returning all items');
        return list;
    }
    const filtered = list.filter(qt => {
        const company = (qt.COMPANYNAME || '').toLowerCase().trim();
        const matches = company === companyFilter.toLowerCase();
        return matches;
    });
    console.log(`[DEBUG] Filtered ${list.length} items by "${companyFilter}" -> ${filtered.length} items`);
    return filtered;
}

async function setupCompanyFilter() {
    const dropdown = document.getElementById('company-filter-dropdown');
    const clearBtn = document.getElementById('company-filter-clear');
    if (!dropdown || !clearBtn) {
        console.log('[DEBUG] Dropdown or clear button not found');
        return;
    }

    // Populate dropdown from database
    const companies = await getAllUniqueCompanyNames();
    console.log('[DEBUG] Found companies:', companies);
    dropdown.innerHTML = '<option value="">All Companies</option>' +
        companies.map(name => `<option value="${name}">${name}</option>`).join('');

    dropdown.onchange = function() {
        companyFilter = dropdown.value;
        console.log('[DEBUG] Company filter changed to:', companyFilter);
        setQuotationTab(currentTab);
    };
    clearBtn.onclick = function() {
        companyFilter = '';
        dropdown.value = '';
        console.log('[DEBUG] Company filter cleared');
        setQuotationTab(currentTab);
    };
}

let currentTab = 'active';

// Patch setQuotationTab to remember current tab and filter
const originalSetQuotationTab = setQuotationTab;
setQuotationTab = function(tabName) {
    currentTab = tabName;
    originalSetQuotationTab(tabName);
};

// Patch renderQuotationList to filter by company
const originalRenderQuotationList = renderQuotationList;
renderQuotationList = function(list, isCancelled) {
    return originalRenderQuotationList(filterQuotationsByCompany(list), isCancelled);
};

// Setup filter after DOM loaded
const origLoadQuotations = loadQuotations;
loadQuotations = async function() {
    await origLoadQuotations();
    setupCompanyFilter();
};
