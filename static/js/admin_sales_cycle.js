/* /admin/sales-cycle — master-detail invoice cycle browser.
 * Depends on /static/js/admin_helpers.js (window.EQ).
 */
(function () {
    'use strict';

    const { escapeHtml, formatDate, apiGet } = window.EQ;

    const LONG_THRESHOLD_DAYS = 30;

    const state = {
        items: [],
        sort: 'desc',
        selected: -1,
    };

    function sortedItems() {
        return [...state.items].sort((a, b) => {
            const aM = Number(a.sales_cycle_minutes || 0);
            const bM = Number(b.sales_cycle_minutes || 0);
            return state.sort === 'asc' ? aM - bM : bM - aM;
        });
    }

    function renderDetail(item) {
        const el = document.getElementById('sales-cycle-detail');
        if (!el) return;
        if (!item) {
            el.innerHTML = '<div class="ar-detail-placeholder">Select an invoice on the left to view details.</div>';
            return;
        }

        const invoiceLabel = escapeHtml(item.invoice_docno || `DOCKEY ${item.invoice_dockey}`);
        const quotationLabel = escapeHtml(item.quotation_docno || '-');
        const qtDate = escapeHtml(formatDate(item.quotation_docdate));
        const ivDate = escapeHtml(formatDate(item.invoice_docdate));
        const cycleDisplay = escapeHtml(item.sales_cycle_display || '-');
        const company = escapeHtml(item.company_name || '-');

        const invoiceItems = Array.isArray(item.invoice_items) ? item.invoice_items : [];
        const itemRows = invoiceItems.length
            ? invoiceItems.map(line => `
                <tr>
                    <td>${escapeHtml(line.itemcode || '-')}</td>
                    <td>${escapeHtml(line.description || '-')}</td>
                    <td class="num">${Number(line.qty || 0).toFixed(2)}</td>
                    <td>${escapeHtml(line.uom || '-')}</td>
                </tr>`).join('')
            : '<tr><td colspan="4" style="color:var(--ice-text-muted,#5a7a94);">No invoice items found.</td></tr>';

        el.innerHTML = `
            <h3 class="ar-detail-heading">${invoiceLabel}</h3>
            <div class="ar-meta-grid">
                <div><span>Invoice</span>&nbsp; ${invoiceLabel}</div>
                <div><span>Invoice Date</span>&nbsp; ${ivDate}</div>
                <div><span>Quotation</span>&nbsp; ${quotationLabel}</div>
                <div><span>Quotation Date</span>&nbsp; ${qtDate}</div>
                <div><span>Company</span>&nbsp; ${company}</div>
                <div><span>Cycle</span>&nbsp; ${cycleDisplay}</div>
            </div>
            <div class="ar-table-wrap">
                <table class="ar-table">
                    <thead>
                        <tr>
                            <th>Item Code</th>
                            <th>Description</th>
                            <th class="num">Qty</th>
                            <th>UOM</th>
                        </tr>
                    </thead>
                    <tbody>${itemRows}</tbody>
                </table>
            </div>`;
    }

    function selectRow(index) {
        const sorted = sortedItems();
        if (index < 0 || index >= sorted.length) {
            state.selected = -1;
            renderDetail(null);
            return;
        }

        state.selected = index;
        renderDetail(sorted[index]);

        document.querySelectorAll('#sales-cycle-list .ar-list-item').forEach((btn, i) => {
            const selected = i === index;
            btn.classList.toggle('is-selected', selected);
            btn.setAttribute('aria-selected', selected ? 'true' : 'false');
        });
    }

    function renderList(items) {
        const container = document.getElementById('sales-cycle-list');
        if (!container) return;

        if (!items.length) {
            container.innerHTML = '<div class="ia-empty">No QT to IV sales cycle records found.</div>';
            state.selected = -1;
            renderDetail(null);
            return;
        }

        const sorted = sortedItems();
        container.innerHTML = sorted.map((item, index) => {
            const invoiceLabel = escapeHtml(item.invoice_docno || `DOCKEY ${item.invoice_dockey}`);
            const quotationLabel = escapeHtml(item.quotation_docno || '-');
            const qtDate = escapeHtml(formatDate(item.quotation_docdate));
            const ivDate = escapeHtml(formatDate(item.invoice_docdate));
            const cycleDisplay = escapeHtml(item.sales_cycle_display || '-');
            const company = escapeHtml(item.company_name || '-');
            const days = Number(item.sales_cycle_days || 0);
            const badgeMod = days >= LONG_THRESHOLD_DAYS ? 'ar-badge--danger' : 'ar-badge--info';

            return `
            <button type="button" class="ar-list-item" data-index="${index}" aria-selected="false">
                <span class="ar-list-item-top">
                    <span class="ar-doc-no">${invoiceLabel}</span>
                    <span class="ar-badge ${badgeMod}">${cycleDisplay}</span>
                </span>
                <span class="ar-list-item-company">${company}</span>
                <span class="ar-list-item-sub">QT ${quotationLabel} (${qtDate}) → IV (${ivDate})</span>
            </button>`;
        }).join('');

        container.querySelectorAll('.ar-list-item').forEach(btn => {
            btn.addEventListener('click', () => selectRow(Number(btn.dataset.index)));
        });

        const pick = state.selected >= 0 && state.selected < sorted.length ? state.selected : 0;
        selectRow(pick);
    }

    function renderView() {
        renderList(state.items);
        document.getElementById('sc-sort-long')?.classList.toggle('active', state.sort === 'desc');
        document.getElementById('sc-sort-short')?.classList.toggle('active', state.sort === 'asc');
    }

    async function loadPage() {
        const totalEl = document.getElementById('sales-cycle-total');
        const avgEl = document.getElementById('sales-cycle-avg');
        const shortEl = document.getElementById('sales-cycle-shortest');
        const longEl = document.getElementById('sales-cycle-longest');
        const listEl = document.getElementById('sales-cycle-list');

        try {
            const data = await apiGet('/api/admin/sales_cycle_details');
            if (!Array.isArray(data?.items)) {
                throw new Error('Malformed response (missing items)');
            }

            state.items = data.items;
            state.selected = 0;

            if (totalEl) totalEl.textContent = String(data.total_converted_invoices ?? 0);
            if (avgEl) avgEl.textContent = `${Number(data.avg_sales_cycle_days || 0).toFixed(2)} days`;
            if (shortEl) shortEl.textContent = data.shortest_sales_cycle_display || '-';
            if (longEl) longEl.textContent = data.longest_sales_cycle_display || '-';

            renderView();
        } catch (error) {
            if (listEl) listEl.innerHTML = `<div class="ia-empty">${escapeHtml(error.message || 'Failed to load.')}</div>`;
            if (avgEl) avgEl.textContent = 'Error';
            renderDetail(null);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadPage();

        document.getElementById('sc-sort-long')?.addEventListener('click', () => {
            state.sort = 'desc';
            state.selected = 0;
            renderView();
        });

        document.getElementById('sc-sort-short')?.addEventListener('click', () => {
            state.sort = 'asc';
            state.selected = 0;
            renderView();
        });
    });
})();
