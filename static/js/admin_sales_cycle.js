// Chart.js chart removed as per user request.
let salesCycleItems = [];
let salesCycleSort = 'desc';

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatDisplayDate(value) {
    if (!value) return '-';
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('en-MY', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    }).format(date);
}

function sortedSalesCycleItems(items) {
    return [...items].sort((a, b) => {
        const aMinutes = Number(a.sales_cycle_minutes || 0);
        const bMinutes = Number(b.sales_cycle_minutes || 0);
        return salesCycleSort === 'asc' ? aMinutes - bMinutes : bMinutes - aMinutes;
    });
}

function renderSalesCycleList(items) {
    const container = document.getElementById('sales-cycle-list');
    if (!container) {
        return;
    }

    if (!items.length) {
        container.innerHTML = '<div class="analytics-empty">No QT to IV sales cycle records found.</div>';
        return;
    }

    const sorted = sortedSalesCycleItems(items);
    container.innerHTML = sorted.map((item, index) => {
        const invoiceLabel = item.invoice_docno || `DOCKEY ${item.invoice_dockey}`;
        const quotationLabel = item.quotation_docno || '-';
        const qtDate = formatDisplayDate(item.quotation_docdate);
        const ivDate = formatDisplayDate(item.invoice_docdate);
        const company = item.company_name ? `<span class="company-pill">${escapeHtml(item.company_name)}</span>` : '';
        const invoiceItems = Array.isArray(item.invoice_items) ? item.invoice_items : [];
        const invoiceItemsRows = invoiceItems.length
            ? invoiceItems.map(line => `
                <tr>
                    <td>${escapeHtml(line.itemcode || '-')}</td>
                    <td>${escapeHtml(line.description || '-')}</td>
                    <td>${Number(line.qty || 0).toFixed(2)}</td>
                    <td>${escapeHtml(line.uom || '-')}</td>
                </tr>
            `).join('')
            : '<tr><td colspan="4">No invoice items found.</td></tr>';
        return `
            <div class="conversion-detail-card">
                <button type="button" class="conversion-detail-toggle" aria-expanded="false" aria-controls="sales-cycle-panel-${index}">
                    <span>${escapeHtml(invoiceLabel)} · ${escapeHtml(item.sales_cycle_display)} ${company}</span>
                    <span>QT ${escapeHtml(quotationLabel)} (${escapeHtml(qtDate)}) → IV (${escapeHtml(ivDate)}) <span class="conversion-caret">▼</span></span>
                </button>
                <div class="conversion-detail-panel" id="sales-cycle-panel-${index}" hidden>
                    <div class="conversion-detail-grid">
                        <div><strong>Invoice:</strong> ${escapeHtml(invoiceLabel)}</div>
                        <div><strong>Invoice Date:</strong> ${escapeHtml(ivDate)}</div>
                        <div><strong>Quotation:</strong> ${escapeHtml(quotationLabel)}</div>
                        <div><strong>Quotation Date:</strong> ${escapeHtml(qtDate)}</div>
                        <div><strong>Company:</strong> ${escapeHtml(item.company_name || '-')}</div>
                        <div><strong>Invoice DOCKEY:</strong> ${escapeHtml(item.invoice_dockey)}</div>
                        <div><strong>Cycle Days:</strong> ${escapeHtml(item.sales_cycle_days)}</div>
                        <div><strong>Cycle Minutes:</strong> ${escapeHtml(item.sales_cycle_minutes)}</div>
                    </div>
                    <div class="conversion-detail-table-wrap">
                        <table class="conversion-detail-table">
                            <thead>
                                <tr>
                                    <th>Item Code</th>
                                    <th>Description</th>
                                    <th>Qty</th>
                                    <th>UOM</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${invoiceItemsRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    setupSalesCycleAccordion();
}

function setupSalesCycleAccordion() {
    const toggles = document.querySelectorAll('#sales-cycle-list .conversion-detail-toggle');
    toggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const expanded = toggle.getAttribute('aria-expanded') === 'true';
            const panelId = toggle.getAttribute('aria-controls');
            const panel = panelId ? document.getElementById(panelId) : null;
            if (!panel) {
                return;
            }

            toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
            panel.hidden = expanded;

            const caret = toggle.querySelector('.conversion-caret');
            if (caret) {
                caret.textContent = expanded ? '▼' : '▲';
            }
        });
    });
}

function renderSalesCycleView() {
    renderSalesCycleList(salesCycleItems);
}

async function loadSalesCycleDetailPage() {
    const totalEl = document.getElementById('sales-cycle-total');
    const avgEl = document.getElementById('sales-cycle-avg');
    const shortestEl = document.getElementById('sales-cycle-shortest');
    const longestEl = document.getElementById('sales-cycle-longest');
    const listEl = document.getElementById('sales-cycle-list');

    try {
        const response = await fetch('/api/admin/sales_cycle_details');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load sales cycle details');
        }

        const data = payload.data;
        salesCycleItems = data.items;

        if (totalEl) totalEl.textContent = String(data.total_converted_invoices ?? 0);
        if (avgEl) avgEl.textContent = `${Number(data.avg_sales_cycle_days || 0).toFixed(2)} days`;
        if (shortestEl) shortestEl.textContent = data.shortest_sales_cycle_display || '-';
        if (longestEl) longestEl.textContent = data.longest_sales_cycle_display || '-';

        renderSalesCycleView();
    } catch (error) {
        if (listEl) {
            listEl.innerHTML = `<div class="analytics-empty">${error.message || 'Failed to load sales cycle details.'}</div>`;
        }
        if (avgEl) {
            avgEl.textContent = 'Error';
        }
    }
}


document.addEventListener('DOMContentLoaded', () => {
    loadSalesCycleDetailPage();

    const toggle = document.getElementById('sales-cycle-sort-toggle');
    if (toggle) {
        // Default: left (desc)
        toggle.setAttribute('aria-pressed', salesCycleSort === 'asc' ? 'true' : 'false');
        toggle.addEventListener('click', () => {
            salesCycleSort = salesCycleSort === 'desc' ? 'asc' : 'desc';
            toggle.setAttribute('aria-pressed', salesCycleSort === 'asc' ? 'true' : 'false');
            renderSalesCycleView();
        });
        toggle.addEventListener('keydown', (e) => {
            if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                salesCycleSort = salesCycleSort === 'desc' ? 'asc' : 'desc';
                toggle.setAttribute('aria-pressed', salesCycleSort === 'asc' ? 'true' : 'false');
                renderSalesCycleView();
            }
        });
    }
});
