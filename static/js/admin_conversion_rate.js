/* /admin/conversion-rate — master-detail QT→IV conversion browser.
 * Depends on /static/js/admin_helpers.js (window.EQ).
 */
(function () {
    'use strict';

    const { escapeHtml, formatDate, apiGet, toFixed } = window.EQ;

    const state = {
        items: [],
        filter: 'all',
        selected: -1,
    };

    function pctBadgeMod(pct) {
        if (pct === 0)  return 'ar-badge--muted';
        if (pct >= 100) return 'ar-badge--success';
        if (pct >= 50)  return 'ar-badge--info';
        return 'ar-badge--danger';
    }

    function aggregateByQuotation(items) {
        const bucket = new Map();
        for (const item of items) {
            const key = item.qt_docno || `QT-${item.qt_dockey || ''}`;
            if (!bucket.has(key)) {
                bucket.set(key, {
                    qt_docno: key,
                    qt_docdate: item.qt_docdate || null,
                    customer_code: (item.customer_code || '').trim(),
                    company_name: (item.customer_name || '').trim(),
                    qt_qty: 0, iv_qty: 0, line_count: 0, lines: [],
                });
            }
            const row = bucket.get(key);
            const qtQty = Number(item.qt_qty || 0);
            const ivQty = Number(item.iv_qty || 0);
            row.qt_qty += qtQty;
            row.iv_qty += ivQty;
            row.line_count += 1;
            row.lines.push({
                itemcode: (item.itemcode || '').trim(),
                qt_qty: qtQty, iv_qty: ivQty,
                conversion_pct: Number(item.conversion_pct || 0),
                invoice_count: Number(item.invoice_count || 0),
                latest_iv_date: item.latest_iv_date || null,
            });
            if (!row.customer_code && item.customer_code) row.customer_code = String(item.customer_code).trim();
            if (!row.company_name && item.customer_name) row.company_name = String(item.customer_name).trim();
            if (!row.qt_docdate && item.qt_docdate) row.qt_docdate = item.qt_docdate;
        }

        return Array.from(bucket.values())
            .map(row => ({
                ...row,
                conversion_pct: Number((row.qt_qty > 0 ? (row.iv_qty / row.qt_qty) * 100 : 0).toFixed(2)),
            }))
            .sort((a, b) => (a.qt_docdate || '').localeCompare(b.qt_docdate || '') ||
                            (a.qt_docno || '').localeCompare(b.qt_docno || ''));
    }

    function filterByRange(items, range) {
        if (range === 'all') return items;
        if (range === '100+') return items.filter(r => r.conversion_pct >= 100);
        const [min, max] = range.split('-').map(Number);
        return items.filter(r => r.conversion_pct >= min && r.conversion_pct < max);
    }

    const filteredItems = () => filterByRange(state.items, state.filter);

    function renderDetail(item) {
        const el = document.getElementById('conversion-rate-detail');
        if (!el) return;
        if (!item) {
            el.innerHTML = '<div class="ar-detail-placeholder">Select a quotation on the left to view details.</div>';
            return;
        }

        const pct = Number(item.conversion_pct || 0);
        const lines = item.lines || [];
        const lineRows = lines.map(line => `
            <tr>
                <td>${escapeHtml(line.itemcode || '-')}</td>
                <td class="num">${toFixed(line.qt_qty)}</td>
                <td class="num">${toFixed(line.iv_qty)}</td>
                <td class="num">${toFixed(line.conversion_pct)}%</td>
                <td class="num">${line.invoice_count}</td>
                <td>${escapeHtml(formatDate(line.latest_iv_date))}</td>
            </tr>`).join('');

        el.innerHTML = `
            <h3 class="ar-detail-heading">${escapeHtml(item.qt_docno)} · ${pct.toFixed(2)}%</h3>
            <div class="ar-meta-grid">
                <div><span>Customer Code</span>&nbsp; ${escapeHtml(item.customer_code || '-')}</div>
                <div><span>QT Date</span>&nbsp; ${escapeHtml(formatDate(item.qt_docdate))}</div>
                <div><span>Total Lines</span>&nbsp; ${item.line_count}</div>
                <div><span>Company</span>&nbsp; ${escapeHtml(item.company_name || '-')}</div>
                <div><span>IV / QT Qty</span>&nbsp; ${toFixed(item.iv_qty)} / ${toFixed(item.qt_qty)}</div>
            </div>
            <div class="ar-table-wrap">
                <table class="ar-table">
                    <thead>
                        <tr>
                            <th>Item Code</th>
                            <th class="num">QT Qty</th>
                            <th class="num">IV Qty</th>
                            <th class="num">Line %</th>
                            <th class="num">Invoices</th>
                            <th>Latest IV Date</th>
                        </tr>
                    </thead>
                    <tbody>${lineRows || '<tr><td colspan="6">No line details.</td></tr>'}</tbody>
                </table>
            </div>`;
    }

    function selectRow(index) {
        const items = filteredItems();
        if (index < 0 || index >= items.length) {
            state.selected = -1;
            renderDetail(null);
            return;
        }
        state.selected = index;
        renderDetail(items[index]);

        document.querySelectorAll('#conversion-rate-list .ar-list-item').forEach((btn, i) => {
            const selected = i === index;
            btn.classList.toggle('is-selected', selected);
            btn.setAttribute('aria-selected', selected ? 'true' : 'false');
        });
    }

    function renderList(items) {
        const listEl = document.getElementById('conversion-rate-list');
        if (!listEl) return;

        if (!items.length) {
            listEl.innerHTML = '<div class="ia-empty">No conversion records found.</div>';
            state.selected = -1;
            renderDetail(null);
            return;
        }

        listEl.innerHTML = items.map((item, idx) => {
            const pct = Number(item.conversion_pct || 0);
            const badgeMod = pctBadgeMod(pct);
            return `
            <button type="button" class="ar-list-item" data-index="${idx}" aria-selected="false">
                <span class="ar-list-item-top">
                    <span class="ar-doc-no">${escapeHtml(item.qt_docno)}</span>
                    <span class="ar-badge ${badgeMod}">${pct.toFixed(2)}%</span>
                </span>
                ${item.company_name ? `<span class="ar-list-item-company">${escapeHtml(item.company_name)}</span>` : ''}
                <span class="ar-list-item-sub">IV ${toFixed(item.iv_qty)} / QT ${toFixed(item.qt_qty)} · ${escapeHtml(formatDate(item.qt_docdate))}</span>
            </button>`;
        }).join('');

        listEl.querySelectorAll('.ar-list-item').forEach(btn => {
            btn.addEventListener('click', () => selectRow(Number(btn.dataset.index)));
        });

        const pick = state.selected >= 0 && state.selected < items.length ? state.selected : 0;
        selectRow(pick);
    }

    function renderStats(items) {
        const totalEl = document.getElementById('conversion-total-qt');
        const avgEl = document.getElementById('conversion-avg');
        const topEl = document.getElementById('conversion-top');
        const lowEl = document.getElementById('conversion-low');

        if (!items.length) {
            if (totalEl) totalEl.textContent = '0';
            if (avgEl) avgEl.textContent = '0.00%';
            if (topEl) topEl.textContent = '0.00%';
            if (lowEl) lowEl.textContent = 'N/A';
            return;
        }

        const totalQtQty = items.reduce((s, r) => s + r.qt_qty, 0);
        const totalIvQty = items.reduce((s, r) => s + r.iv_qty, 0);
        const weightedAvg = totalQtQty > 0 ? (totalIvQty / totalQtQty) * 100 : 0;
        const top = Math.max(...items.map(r => r.conversion_pct));
        const nonzero = items.filter(r => Number(r.conversion_pct) > 0);
        const low = nonzero.length ? Math.min(...nonzero.map(r => r.conversion_pct)) : null;

        if (totalEl) totalEl.textContent = String(items.length);
        if (avgEl) avgEl.textContent = `${weightedAvg.toFixed(2)}%`;
        if (topEl) topEl.textContent = `${top.toFixed(2)}%`;
        if (lowEl) lowEl.textContent = low === null ? 'N/A' : `${low.toFixed(2)}%`;
    }

    function updateView() {
        const items = filteredItems();
        renderStats(items);
        renderList(items);

        document.querySelectorAll('.ar-pill-btn[data-range]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.range === state.filter);
        });
    }

    async function loadPage() {
        const listEl = document.getElementById('conversion-rate-list');
        try {
            const data = await apiGet('/api/admin/qt_iv_conversion_report');
            if (!Array.isArray(data?.items)) {
                throw new Error('Malformed response (missing items)');
            }

            state.items = aggregateByQuotation(data.items);
            state.selected = 0;
            updateView();
        } catch (error) {
            if (listEl) listEl.innerHTML = `<div class="ia-empty">${escapeHtml(error.message || 'Failed to load.')}</div>`;
            renderDetail(null);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadPage();

        document.querySelectorAll('.ar-pill-btn[data-range]').forEach(btn => {
            btn.addEventListener('click', () => {
                state.filter = btn.dataset.range;
                state.selected = 0;
                updateView();
            });
        });
    });
})();
