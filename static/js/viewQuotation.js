let activeQuotationsCache = [];
let cancelledQuotationsCache = [];
let draftQuotationsCache = [];
let pendingQuotationsCache = [];
let slQtDraftCache = [];
let slQtDraftLoaded = false;

function isPendingQuotation(qt) {
    // Priority rule: UPDATECOUNT determines Pending first.
    return qt.UPDATECOUNT === null || qt.UPDATECOUNT === undefined;
}

async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) return;

    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);
        const response = await fetch('/api/get_my_quotations', { signal: controller.signal });
        clearTimeout(timeoutId);
        const data = await response.json();

        if (!data.success) {
            content.innerHTML = `<div style="padding: 20px; text-align: center; color: #ff6b6b;">${data.error || 'Failed to load quotations'}</div>`;
            return;
        }

        const quotations = data.data || [];
        if (quotations.length === 0) {
            content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">No quotations found.</div>';
            return;
        }

        console.log('[DEBUG] First 3 quotations:', quotations.slice(0, 3).map(qt => ({
            DOCNO: qt.DOCNO,
            STATUS: qt.STATUS,
            CANCELLED: qt.CANCELLED,
            cancelledType: typeof qt.CANCELLED
        })));

        pendingQuotationsCache = quotations.filter(qt => isPendingQuotation(qt));
        cancelledQuotationsCache = quotations.filter(qt => !isPendingQuotation(qt) && qt.CANCELLED === true);
        activeQuotationsCache = quotations.filter(qt => !isPendingQuotation(qt) && qt.CANCELLED === false && qt.STATUS !== 'DRAFT');
        draftQuotationsCache = quotations.filter(qt => qt.STATUS === 'DRAFT');

        console.log(`[DEBUG] Filtered counts - Drafts: ${draftQuotationsCache.length}, Pending: ${pendingQuotationsCache.length}, Active: ${activeQuotationsCache.length}, Cancelled: ${cancelledQuotationsCache.length}`);

        let html = `
            <div style="padding: 16px;">
                <div style="display: flex; gap: 8px; margin-bottom: 12px; border-bottom: 1px solid #3d4654; padding-bottom: 10px;">
                    <button id="tab-drafts" onclick="setQuotationTab('drafts')" style="background: #5b82b6; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        📋 Drafts (${draftQuotationsCache.length})
                    </button>
                    <button id="tab-pending" onclick="setQuotationTab('pending')" style="background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                        ⏳ Pending (${pendingQuotationsCache.length})
                    </button>
                    <button id="tab-active" onclick="setQuotationTab('active')" style="background: #2d3440; color: #9ba7b6; border: 1px solid #3d4654; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;">
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
        setQuotationTab('drafts');
        
        updateDraftCountDisplay();
    } catch (error) {
        const message = error && error.name === 'AbortError'
            ? 'Request timed out while loading quotations. Please refresh and try again.'
            : 'Failed to load quotations.';
        content.innerHTML = `<div style="padding: 20px; text-align: center; color: #ff6b6b;">${message}</div>`;
        console.error('Error loading quotations:', error);
    }
}

function setQuotationTab(tabName) {
    const tabContent = document.getElementById('quotation-tab-content');
    const activeBtn = document.getElementById('tab-active');
    const cancelledBtn = document.getElementById('tab-cancelled');
    const draftsBtn = document.getElementById('tab-drafts');
    const pendingBtn = document.getElementById('tab-pending');
    if (!tabContent || !activeBtn || !cancelledBtn || !draftsBtn || !pendingBtn) return;

    activeBtn.style.background = '#2d3440';
    activeBtn.style.color = '#9ba7b6';
    activeBtn.style.border = '1px solid #3d4654';
    cancelledBtn.style.background = '#2d3440';
    cancelledBtn.style.color = '#9ba7b6';
    cancelledBtn.style.border = '1px solid #3d4654';
    draftsBtn.style.background = '#2d3440';
    draftsBtn.style.color = '#9ba7b6';
    draftsBtn.style.border = '1px solid #3d4654';
    pendingBtn.style.background = '#2d3440';
    pendingBtn.style.color = '#9ba7b6';
    pendingBtn.style.border = '1px solid #3d4654';

    if (tabName === 'cancelled') {
        tabContent.innerHTML = renderQuotationList(cancelledQuotationsCache, 'cancelled');
        cancelledBtn.style.background = '#a65c5c';
        cancelledBtn.style.color = '#fff';
        cancelledBtn.style.border = 'none';
    } else if (tabName === 'drafts') {
        draftsBtn.style.background = '#5b82b6';
        draftsBtn.style.color = '#fff';
        draftsBtn.style.border = 'none';
        loadSlQtDraftTab(tabContent);
    } else if (tabName === 'pending') {
        tabContent.innerHTML = renderQuotationList(pendingQuotationsCache, 'pending');
        pendingBtn.style.background = '#b0892f';
        pendingBtn.style.color = '#fff';
        pendingBtn.style.border = 'none';
    } else {
        tabContent.innerHTML = renderQuotationList(activeQuotationsCache, 'active');
        activeBtn.style.background = '#4b6e9e';
        activeBtn.style.color = '#fff';
        activeBtn.style.border = 'none';
    }

    attachQuotationCardListeners();
}

function renderQuotationList(list, listType) {
    if (!list || list.length === 0) {
        return '<div style="padding: 12px; text-align: center; color: #888;">No quotations</div>';
    }

    let html = '';
    list.forEach(qt => {
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = qt.DOCDATE || '-';
        const validity = qt.VALIDITY || '-';
        const creditTerm = qt.CREDITTERM || 'N/A';
        const description = qt.DESCRIPTION || 'Quotation';
        const isDraft = listType === 'draft';
        const isCancelled = listType === 'cancelled';
        const isPending = listType === 'pending';
        const borderColor = isCancelled ? '#a65c5c' : (isPending ? '#b0892f' : (isDraft ? '#5b82b6' : '#4b6e9e'));
        const badgeColor = isCancelled ? '#a65c5c' : (isPending ? '#b0892f' : (isDraft ? '#5b82b6' : '#4b6e9e'));

        const editButton = isDraft ? `<button onclick="event.stopPropagation(); editDraft(${qt.DOCKEY});" style="background: #5b82b6; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; margin-left: 8px;">Edit Draft</button>` : '';
        
        html += `
            <div class="quotation-card" data-dockey="${qt.DOCKEY}" style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid ${borderColor}; cursor: pointer; width: auto;">
                <div style="display: flex; align-items: center; gap: 16px; flex-wrap: nowrap; margin-bottom: 12px;">
                    <span class="expand-arrow" style="color: #9ba7b6; font-size: 12px; transition: transform 0.2s; flex-shrink: 0;">▼</span>
                    <span style="font-weight: 600; color: #e4e9f1; flex-shrink: 0;">${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                    <span style="color: #9ba7b6; font-size: 13px; white-space: nowrap;">Date: ${docDate} | Valid Until: ${validity} | Terms: ${creditTerm}</span>
                    <span style="color: #e4e9f1; font-size: 14px; flex-shrink: 0;">${description}</span>
                    <span style="background: ${badgeColor}; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; flex-shrink: 0; margin-left: auto;">RM ${amount}</span>
                    ${editButton}
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
    const isDraftSource = card.dataset.source === 'slqtdraft';

    if (itemsDiv.style.display === 'none') {
        if (!itemsDiv.dataset.loaded) {
            try {
                const endpoint = isDraftSource
                    ? `/api/get_draft_quotation_details?dockey=${dockey}`
                    : `/api/get_quotation_details?dockey=${dockey}`;
                const response = await fetch(endpoint);
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
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Price</th>';
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Qty</th>';
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Discount</th>';
                        itemsHtml += '<th style="padding: 6px; text-align: right;">Subtotal</th>';
                        itemsHtml += '</tr></thead><tbody>';

                        let total = 0;
                        items.forEach(item => {
                            const qty = Number(item.QTY || 0).toFixed(2);
                            const price = Number(item.UNITPRICE || 0).toFixed(2);
                            const discount = Number(item.DISC || 0).toFixed(2);
                            const amount = Math.max(0, (item.QTY * item.UNITPRICE) - (item.DISC || 0)).toFixed(2);
                            total += parseFloat(amount);

                            itemsHtml += '<tr style="color: #e4e9f1; font-size: 13px; border-top: 1px solid #3d4654;">';
                            itemsHtml += `<td style="padding: 8px 6px;"><div style="font-weight: 500;">${item.ITEMCODE || ''}</div><div style="color: #9ba7b6; font-size: 11px;">${item.DESCRIPTION || ''}</div></td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right;">RM ${price}</td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right;">${qty}</td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right;">RM ${discount}</td>`;
                            itemsHtml += `<td style="padding: 8px 6px; text-align: right; font-weight: 600;">RM ${amount}</td>`;
                            itemsHtml += '</tr>';
                        });

                        itemsHtml += `<tr style="background: #232a36; color: #f5b301; font-weight: bold;"><td colspan="4" style="padding: 8px 6px; text-align: right;">TOTAL</td><td style="padding: 8px 6px; text-align: right; font-weight: bold;">RM ${total.toFixed(2)}</td></tr>`;
                        itemsHtml += '</tbody></table>';
                    }

                    itemsDiv.innerHTML = itemsHtml;
                    itemsDiv.dataset.loaded = 'true';
                } else {
                    itemsDiv.innerHTML = '<div style="color: #ff6b6b; padding: 8px; text-align: center;">Failed to load items</div>';
                }
            } catch (error) {
                itemsDiv.innerHTML = '<div style="color: #ff6b6b; padding: 8px; text-align: center;">Error loading items</div>';
                console.error('Error fetching quotation items:', error);
            }
        }

        itemsDiv.style.display = 'block';
        arrow.style.transform = 'rotate(180deg)';
    } else {
        itemsDiv.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

async function loadSlQtDraftTab(tabContent) {
    if (slQtDraftLoaded) {
        tabContent.innerHTML = renderDraftList(slQtDraftCache);
        attachQuotationCardListeners();
        return;
    }
    tabContent.innerHTML = '<div style="padding: 12px; text-align: center; color: #888;">Loading drafts...</div>';
    try {
        const res = await fetch('/api/get_my_draft_quotations');
        const data = await res.json();
        if (!data.success) {
            tabContent.innerHTML = `<div style="padding: 12px; text-align: center; color: #ff6b6b;">${data.error || 'Failed to load drafts'}</div>`;
            return;
        }
        slQtDraftCache = data.data || [];
        slQtDraftLoaded = true;
        tabContent.innerHTML = renderDraftList(slQtDraftCache);
        attachQuotationCardListeners();
    } catch (e) {
        tabContent.innerHTML = '<div style="padding: 12px; text-align: center; color: #ff6b6b;">Error loading drafts</div>';
        console.error('loadSlQtDraftTab error:', e);
    }
}

function attachQuotationCardListeners() {
    document.querySelectorAll('.quotation-card').forEach(card => {
        card.addEventListener('click', function() {
            toggleQuotationItems(this);
        });
    });
}

function renderDraftList(list) {
    if (!list || list.length === 0) {
        return '<div style="padding: 12px; text-align: center; color: #888;">No saved drafts</div>';
    }
    let html = '';
    list.forEach(qt => {
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = qt.DOCDATE || '-';
        const validity = qt.VALIDITY || '-';
        const creditTerm = qt.CREDITTERM || 'N/A';
        const description = qt.DESCRIPTION || 'Draft Quotation';
        html += `
            <div class="quotation-card" data-dockey="${qt.DOCKEY}" data-source="slqtdraft" style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid #5b82b6; cursor: pointer;">
                <div style="display: flex; align-items: center; gap: 16px; flex-wrap: nowrap; margin-bottom: 12px;">
                    <span class="expand-arrow" style="color: #9ba7b6; font-size: 12px; transition: transform 0.2s; flex-shrink: 0;">▼</span>
                    <span style="font-weight: 600; color: #e4e9f1; flex-shrink: 0;">${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                    <span style="color: #9ba7b6; font-size: 13px; white-space: nowrap;">Date: ${docDate} | Valid Until: ${validity} | Terms: ${creditTerm}</span>
                    <span style="color: #e4e9f1; font-size: 14px; flex-shrink: 0;">${description}</span>
                    <span style="background: #5b82b6; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; flex-shrink: 0; margin-left: auto;">RM ${amount}</span>
                    <button onclick="event.stopPropagation(); editSlQtDraft(${qt.DOCKEY});" style="background: #5b82b6; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; margin-left: 8px;">Edit Draft</button>
                </div>
                <div class="quotation-items" style="display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #3d4654;">
                    <div style="text-align: center; color: #888; padding: 8px;">Loading items...</div>
                </div>
            </div>
        `;
    });
    return html;
}

function editSlQtDraft(dockey) {
    window.location.href = `/create-quotation?draftDockey=${dockey}`;
}

document.addEventListener('DOMContentLoaded', loadQuotations);

function updateDraftCountDisplay() {
    const draftDisplay = document.getElementById('draft-count-display');
    if (draftDisplay) {
        const count = draftQuotationsCache.length;
        draftDisplay.textContent = `📋 Drafts: ${count}`;
    }
}

function editDraft(dockey) {
    window.location.href = `/create-quotation?dockey=${dockey}`;
}

function viewDrafts() {
    setQuotationTab('drafts');
    document.getElementById('quotation-content').scrollIntoView({ behavior: 'smooth' });
}

function showDraftNotification(docno) {
    const notification = document.getElementById('draft-notification');
    if (!notification) return;
    
    const messageEl = notification.querySelector('.draft-notification-message');
    if (messageEl) {
        messageEl.innerHTML = `✓ Draft saved successfully!<br><strong>DOCNO: ${docno}</strong>`;
    }
    
    notification.classList.remove('hidden');
    
    setTimeout(() => {
        notification.classList.add('hidden');
    }, 5000);
}
