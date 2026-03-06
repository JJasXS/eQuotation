let activeQuotationsCache = [];
let cancelledQuotationsCache = [];

async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) return;

    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    try {
        const response = await fetch('/api/get_my_quotations');
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

        activeQuotationsCache = quotations.filter(qt => !Boolean(qt.CANCELLED));
        cancelledQuotationsCache = quotations.filter(qt => Boolean(qt.CANCELLED));

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
    const tabContent = document.getElementById('quotation-tab-content');
    const activeBtn = document.getElementById('tab-active');
    const cancelledBtn = document.getElementById('tab-cancelled');
    if (!tabContent || !activeBtn || !cancelledBtn) return;

    if (tabName === 'cancelled') {
        tabContent.innerHTML = renderQuotationList(cancelledQuotationsCache, true);
        cancelledBtn.style.background = '#a65c5c';
        cancelledBtn.style.color = '#fff';
        cancelledBtn.style.border = 'none';
        activeBtn.style.background = '#2d3440';
        activeBtn.style.color = '#9ba7b6';
        activeBtn.style.border = '1px solid #3d4654';
    } else {
        tabContent.innerHTML = renderQuotationList(activeQuotationsCache, false);
        activeBtn.style.background = '#4b6e9e';
        activeBtn.style.color = '#fff';
        activeBtn.style.border = 'none';
        cancelledBtn.style.background = '#2d3440';
        cancelledBtn.style.color = '#9ba7b6';
        cancelledBtn.style.border = '1px solid #3d4654';
    }

    document.querySelectorAll('.quotation-card').forEach(card => {
        card.addEventListener('click', function() {
            toggleQuotationItems(this);
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
        const creditTerm = qt.CREDITTERM || 'N/A';
        const description = qt.DESCRIPTION || 'Quotation';
        const borderColor = isCancelled ? '#a65c5c' : '#4b6e9e';
        const badgeColor = isCancelled ? '#a65c5c' : '#4b6e9e';

        html += `
            <div class="quotation-card" data-dockey="${qt.DOCKEY}" style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid ${borderColor}; cursor: pointer;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 12px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="expand-arrow" style="color: #9ba7b6; font-size: 12px; transition: transform 0.2s;">▼</span>
                        <span style="font-weight: 600; color: #e4e9f1;">${qt.DOCNO || ('DOCKEY #' + qt.DOCKEY)}</span>
                    </div>
                    <span style="background: ${badgeColor}; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px;">RM ${amount}</span>
                </div>
                <div style="color: #9ba7b6; font-size: 13px; margin-bottom: 6px;">Date: ${docDate} | Valid Until: ${validity} | Terms: ${creditTerm}</div>
                <div style="color: #e4e9f1; font-size: 14px; margin-bottom: 8px;">${description}</div>
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
                itemsDiv.innerHTML = '<div style="color: #ff6b6b; padding: 8px; text-align: center;">Error loading items</div>';
                console.error('Error fetching quotation items:', error);
            }
        }

        itemsDiv.style.display = 'block';
        arrow.style.transform = 'rotate(180deg)';
    } else {
        // Collapse
        itemsDiv.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

document.addEventListener('DOMContentLoaded', loadQuotations);
