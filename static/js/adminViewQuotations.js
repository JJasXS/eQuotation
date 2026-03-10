let activeQuotationsCache = [];
let cancelledQuotationsCache = [];
let pendingQuotationsCache = [];
let companyFilter = '';
let currentTab = 'active';

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
        setQuotationTab(currentTab);
    };

    clearBtn.onclick = function() {
        companyFilter = '';
        dropdown.value = '';
        setQuotationTab(currentTab);
    };
}

async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) return;

    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    try {
        // Fetch all quotations once, then split into Active/Cancelled/Pending using CANCELLED tri-state.
        const response = await fetch('/api/admin/get_all_quotations');
        const data = await response.json();

        if (!data.success) {
            content.innerHTML = '<div style="padding: 20px; text-align: center; color: #ff6b6b;">Failed to load quotations</div>';
            return;
        }

        const allQuotations = data.data || [];
        
        // Debug: log raw data with more detail
        console.log('[DEBUG] Total quotations fetched:', allQuotations.length);
        console.log('[DEBUG] Full sample data:', JSON.stringify(allQuotations.slice(0, 2), null, 2));
        
        activeQuotationsCache = allQuotations.filter(qt => qt.CANCELLED === false);
        cancelledQuotationsCache = allQuotations.filter(qt => qt.CANCELLED === true);
        pendingQuotationsCache = allQuotations.filter(qt => qt.CANCELLED === null);
        
        console.log('[DEBUG] Filtered caches - Active:', activeQuotationsCache.length, 'Cancelled:', cancelledQuotationsCache.length, 'Pending:', pendingQuotationsCache.length);

        const html = `
            <div style="padding: 16px;">
                <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #3d4654; padding-bottom: 10px;">
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <select id="company-filter-dropdown" style="padding: 8px 12px; border-radius: 6px; border: 1px solid #3d4654; background: #232a36; color: #e4e9f1; font-size: 13px; width: 240px;">
                            <option value="">All Companies</option>
                        </select>
                        <button id="company-filter-clear" style="padding: 8px 12px; border-radius: 6px; background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; cursor: pointer; font-size: 13px;">Clear</button>
                    </div>
                    <div style="flex: 1;"></div>
                    <div style="display: flex; gap: 8px;">
                        <button id="tab-active" onclick="setQuotationTab('active')" style="background: #4b6e9e; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            Active (${activeQuotationsCache.length})
                        </button>
                        <button id="tab-cancelled" onclick="setQuotationTab('cancelled')" style="background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            Cancelled (${cancelledQuotationsCache.length})
                        </button>
                        <button id="tab-pending" onclick="setQuotationTab('pending')" style="background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            Pending (${pendingQuotationsCache.length})
                        </button>
                    </div>
                </div>
                <div id="quotation-tab-content" style="background: #232a36; border: 1px solid #3d4654; border-radius: 8px; padding: 12px;"></div>
            </div>
        `;

        content.innerHTML = html;
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

    const activeList = filterQuotationsByCompany(activeQuotationsCache);
    const cancelledList = filterQuotationsByCompany(cancelledQuotationsCache);
    const pendingList = filterQuotationsByCompany(pendingQuotationsCache);

    if (tabName === 'cancelled') {
        tabContent.innerHTML = renderQuotationList(cancelledList, { isCancelled: true, isPending: false });

        cancelledBtn.style.background = '#a65c5c';
        cancelledBtn.style.color = '#fff';
        cancelledBtn.style.border = 'none';

        activeBtn.style.background = '#2d3440';
        activeBtn.style.color = '#9ba7b6';
        activeBtn.style.border = '1px solid #3d4654';

        pendingBtn.style.background = '#2d3440';
        pendingBtn.style.color = '#9ba7b6';
        pendingBtn.style.border = '1px solid #3d4654';
    } else if (tabName === 'pending') {
        tabContent.innerHTML = renderQuotationList(pendingList, { isCancelled: false, isPending: true });

        pendingBtn.style.background = '#b0892f';
        pendingBtn.style.color = '#fff';
        pendingBtn.style.border = 'none';

        activeBtn.style.background = '#2d3440';
        activeBtn.style.color = '#9ba7b6';
        activeBtn.style.border = '1px solid #3d4654';

        cancelledBtn.style.background = '#2d3440';
        cancelledBtn.style.color = '#9ba7b6';
        cancelledBtn.style.border = '1px solid #3d4654';
    } else {
        tabContent.innerHTML = renderQuotationList(activeList, { isCancelled: false, isPending: false });

        activeBtn.style.background = '#4b6e9e';
        activeBtn.style.color = '#fff';
        activeBtn.style.border = 'none';

        cancelledBtn.style.background = '#2d3440';
        cancelledBtn.style.color = '#9ba7b6';
        cancelledBtn.style.border = '1px solid #3d4654';

        pendingBtn.style.background = '#2d3440';
        pendingBtn.style.color = '#9ba7b6';
        pendingBtn.style.border = '1px solid #3d4654';
    }

    document.querySelectorAll('.quotation-card').forEach(card => {
        card.addEventListener('click', function(e) {
            if (!e.target.closest('.edit-button') && !e.target.closest('.toggle-cancelled-btn')) {
                toggleQuotationItems(this);
            }
        });
    });
}

function renderQuotationList(list, options = {}) {
    const isCancelled = !!options.isCancelled;
    const isPending = !!options.isPending;

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
        const borderColor = isPending ? '#b0892f' : (isCancelled ? '#a65c5c' : '#4b6e9e');
        const badgeColor = isPending ? '#b0892f' : (isCancelled ? '#a65c5c' : '#4b6e9e');

        html += `
            <div class="quotation-card" data-dockey="${qt.DOCKEY}" style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid ${borderColor}; cursor: pointer; width: auto;">
                <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 12px;">
                    <span class="expand-arrow" style="color: #9ba7b6; font-size: 12px; transition: transform 0.2s; flex-shrink: 0;">?</span>
                    <span style="font-weight: 600; color: #e4e9f1; flex-shrink: 0;">${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                    <span style="color: #9ba7b6; font-size: 13px;">Customer: ${companyName} (${customerCode})</span>
                    <span style="color: #9ba7b6; font-size: 13px; white-space: nowrap;">Date: ${docDate} | Valid Until: ${validity}</span>
                    <span style="background: ${badgeColor}; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; flex-shrink: 0;">RM ${amount}</span>
                    ${!isCancelled ? `<button class="edit-button" onclick="editQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #5a8fc4; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; white-space: nowrap; flex-shrink: 0;">Edit</button>` : ''}
                    ${isPending ? `<button class="activate-btn" onclick="activateQuotation(${qt.DOCKEY}); event.stopPropagation();" style="background: #4b9e6e; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; white-space: nowrap; flex-shrink: 0;">Activate</button>` : ''}
                    ${!isPending ? `<button class="toggle-cancelled-btn" onclick="console.log('[BUTTON CLICK] DOCKEY:', ${qt.DOCKEY}, 'isCancelled param:', ${isCancelled}); event.stopPropagation(); toggleCancelledStatus(${qt.DOCKEY}, ${isCancelled});" style="background: ${isCancelled ? '#4b6e9e' : '#a65c5c'}; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; white-space: nowrap; flex-shrink: 0;">
                        ${isCancelled ? 'Restore' : 'Cancel'}
                    </button>` : ''}
                </div>
                <div class="quotation-items" style="display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #3d4654;">
                    <div style="text-align: center; color: #888; padding: 8px;">Loading items...</div>
                </div>
            </div>
        `;
    });

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
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right; font-weight: 600;">RM ${amount}</td>`;
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
        itemsDiv.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

function editQuotation(dockey) {
    alert(`Edit quotation DOCKEY: ${dockey}\nEdit functionality coming soon!`);
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadQuotations();
    await setupCompanyFilter();
});
