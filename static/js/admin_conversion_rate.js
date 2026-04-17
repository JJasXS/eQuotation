
let conversionRateChart = null;
let allConversionItems = [];
let currentFilter = 'all';

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function toDisplayDate(value) {
    if (!value) {
        return '-';
    }
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return new Intl.DateTimeFormat('en-MY', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    }).format(date);
}

function aggregateByQuotation(items) {
    const bucket = new Map();

    for (const item of items) {
        const key = item.qt_docno || `QT-${item.qt_dockey || ''}`;
        const qtQty = Number(item.qt_qty || 0);
        const ivQty = Number(item.iv_qty || 0);
        const qtDate = item.qt_docdate || null;

        if (!bucket.has(key)) {
            bucket.set(key, {
                qt_docno: key,
                qt_docdate: qtDate,
                customer_code: (item.customer_code || '').trim(),
                company_name: (item.customer_name || '').trim(),
                qt_qty: 0,
                iv_qty: 0,
                line_count: 0,
                lines: [],
            });
        }

        const row = bucket.get(key);
        row.qt_qty += qtQty;
        row.iv_qty += ivQty;
        row.line_count += 1;
        row.lines.push({
            itemcode: (item.itemcode || '').trim(),
            qt_qty: qtQty,
            iv_qty: ivQty,
            conversion_pct: Number(item.conversion_pct || 0),
            invoice_count: Number(item.invoice_count || 0),
            latest_iv_date: item.latest_iv_date || null,
        });
        if (!row.customer_code && item.customer_code) {
            row.customer_code = String(item.customer_code).trim();
        }
        if (!row.company_name && item.customer_name) {
            row.company_name = String(item.customer_name).trim();
        }
        if (!row.qt_docdate && qtDate) {
            row.qt_docdate = qtDate;
        }
    }

    return Array.from(bucket.values())
        .map(row => {
            const pct = row.qt_qty > 0 ? (row.iv_qty / row.qt_qty) * 100 : 0;
            return {
                ...row,
                conversion_pct: Number(pct.toFixed(2)),
            };
        })
        .sort((a, b) => {
            if (a.qt_docdate !== b.qt_docdate) {
                return (a.qt_docdate || '').localeCompare(b.qt_docdate || '');
            }
            return (a.qt_docno || '').localeCompare(b.qt_docno || '');
        });
}

function renderConversionChart(items) {
    const canvas = document.getElementById('conversion-rate-chart');
    if (!canvas || typeof Chart === 'undefined') {
        return;
    }

    if (conversionRateChart) {
        conversionRateChart.destroy();
    }

    const labels = items.map(item => item.qt_docno);
    const values = items.map(item => item.conversion_pct);

    const neonLinePlugin = {
        id: 'neonLineGlow',
        beforeDatasetDraw(chart, args) {
            const { ctx } = chart;
            if (args.index !== 0) {
                return;
            }
            ctx.save();
            ctx.shadowColor = 'rgba(86, 201, 255, 0.85)';
            ctx.shadowBlur = 16;
            ctx.shadowOffsetX = 0;
            ctx.shadowOffsetY = 0;
        },
        afterDatasetDraw(chart, args) {
            const { ctx } = chart;
            if (args.index !== 0) {
                return;
            }
            ctx.restore();
        },
    };

    conversionRateChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Conversion %',
                    data: values,
                    borderColor: '#56c9ff',
                    backgroundColor: 'rgba(86, 201, 255, 0.14)',
                    pointBackgroundColor: '#ffd28a',
                    pointBorderColor: '#56c9ff',
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.34,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    callbacks: {
                        title(context) {
                            const item = items[context[0].dataIndex];
                            return `${item.qt_docno} (${toDisplayDate(item.qt_docdate)})`;
                        },
                        label(context) {
                            const item = items[context.dataIndex];
                            return [
                                `Conversion: ${context.parsed.y.toFixed(2)}%`,
                                `QT Qty: ${item.qt_qty.toFixed(2)}`,
                                `IV Qty: ${item.iv_qty.toFixed(2)}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: '#c9d8f0',
                        font: {
                            size: 10,
                        },
                        maxRotation: 60,
                        minRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 28,
                    },
                    grid: {
                        color: 'rgba(86, 201, 255, 0.12)',
                    },
                    title: {
                        display: true,
                        text: 'Quotation',
                        color: '#9fc4f5',
                    },
                },
                y: {
                    beginAtZero: true,
                    suggestedMax: 110,
                    ticks: {
                        color: '#c9d8f0',
                        callback: value => `${value}%`,
                    },
                    grid: {
                        color: 'rgba(168, 190, 220, 0.12)',
                    },
                    title: {
                        display: true,
                        text: 'Conversion %',
                        color: '#9fc4f5',
                    },
                },
            },
        },
        plugins: [neonLinePlugin],
    });
}

function renderConversionList(items) {
    const listEl = document.getElementById('conversion-rate-list');
    if (!listEl) {
        return;
    }

    if (!items.length) {
        listEl.innerHTML = '<div class="analytics-empty">No conversion records found.</div>';
        return;
    }

    listEl.innerHTML = items.map((item, idx) => {
        const linePreview = item.lines.slice(0, 6).map(line => `
            <tr>
                <td>${escapeHtml(line.itemcode || '-')}</td>
                <td>${line.qt_qty.toFixed(2)}</td>
                <td>${line.iv_qty.toFixed(2)}</td>
                <td>${line.conversion_pct.toFixed(2)}%</td>
                <td>${line.invoice_count}</td>
                <td>${escapeHtml(toDisplayDate(line.latest_iv_date))}</td>
            </tr>
        `).join('');

        return `
        <div class="conversion-detail-card" data-row-index="${idx}">
            <button type="button" class="conversion-detail-toggle" aria-expanded="false" aria-controls="conversion-detail-panel-${idx}">
                <span>${escapeHtml(item.qt_docno)} (${escapeHtml(toDisplayDate(item.qt_docdate))})${item.company_name ? ` <span class="company-pill">${escapeHtml(item.company_name)}</span>` : ''}</span>
                <span>${item.conversion_pct.toFixed(2)}% · IV ${item.iv_qty.toFixed(2)} / QT ${item.qt_qty.toFixed(2)} <span class="conversion-caret">▼</span></span>
            </button>
            <div class="conversion-detail-panel" id="conversion-detail-panel-${idx}" hidden>
                <div class="conversion-detail-grid">
                    <div><strong>Customer Code:</strong> ${escapeHtml(item.customer_code || '-')}</div>
                    <div><strong>QT Date:</strong> ${escapeHtml(toDisplayDate(item.qt_docdate))}</div>
                    <div><strong>Total Lines:</strong> ${item.line_count}</div>
                    <div><strong>Company:</strong> ${escapeHtml(item.company_name || '-')}</div>
                </div>
                <div class="conversion-detail-table-wrap">
                    <table class="conversion-detail-table">
                        <thead>
                            <tr>
                                <th>Item Code</th>
                                <th>QT Qty</th>
                                <th>IV Qty</th>
                                <th>Line %</th>
                                <th>Invoices</th>
                                <th>Latest IV</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${linePreview || '<tr><td colspan="6">No line details.</td></tr>'}
                        </tbody>
                    </table>
                </div>
                ${item.lines.length > 6 ? `<div class="analytics-empty">Showing first 6 of ${item.lines.length} lines.</div>` : ''}
            </div>
        </div>
    `;
    }).join('');

    setupConversionDetailAccordion();
}

function setupConversionDetailAccordion() {
    const toggles = document.querySelectorAll('.conversion-detail-toggle');
    toggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
            const panelId = toggle.getAttribute('aria-controls');
            const panel = panelId ? document.getElementById(panelId) : null;
            if (!panel) {
                return;
            }

            toggle.setAttribute('aria-expanded', isExpanded ? 'false' : 'true');
            panel.hidden = isExpanded;
            const caret = toggle.querySelector('.conversion-caret');
            if (caret) {
                caret.textContent = isExpanded ? '▼' : '▲';
            }
        });
    });
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
        if (lowEl) lowEl.textContent = '0.00%';
        return;
    }

    const totalQtQty = items.reduce((sum, row) => sum + row.qt_qty, 0);
    const totalIvQty = items.reduce((sum, row) => sum + row.iv_qty, 0);
    const weightedAvg = totalQtQty > 0 ? (totalIvQty / totalQtQty) * 100 : 0;
    const top = Math.max(...items.map(row => row.conversion_pct));
    const nonzeroRows = items.filter(row => Number(row.conversion_pct || 0) > 0);
    const low = nonzeroRows.length > 0
        ? Math.min(...nonzeroRows.map(row => row.conversion_pct))
        : null;

    if (totalEl) totalEl.textContent = String(items.length);
    if (avgEl) avgEl.textContent = `${weightedAvg.toFixed(2)}%`;
    if (topEl) topEl.textContent = `${top.toFixed(2)}%`;
    if (lowEl) lowEl.textContent = low === null ? 'N/A' : `${low.toFixed(2)}%`;
}

function filterByRange(items, range) {
    if (range === 'all') return items;
    if (range === '100+') return items.filter(row => row.conversion_pct >= 100);
    const [min, max] = range.split('-').map(Number);
    return items.filter(row => row.conversion_pct >= min && row.conversion_pct < max);
}

function updateConversionView() {
    const filtered = filterByRange(allConversionItems, currentFilter);
    renderStats(filtered);
    renderConversionChart(filtered);
    renderConversionList(filtered);
}

function setupFilterTabs() {
    const tabs = document.querySelectorAll('.conversion-filter-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentFilter = tab.getAttribute('data-range');
            updateConversionView();
        });
    });
}

async function loadConversionRatePage() {
    const listEl = document.getElementById('conversion-rate-list');
    try {
        const response = await fetch('/api/admin/qt_iv_conversion_report');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load conversion report');
        }

        const grouped = aggregateByQuotation(payload.data.items);
        allConversionItems = grouped;
        setupFilterTabs();
        updateConversionView();
    } catch (error) {
        if (listEl) {
            listEl.innerHTML = `<div class="analytics-empty">${error.message || 'Failed to load conversion details.'}</div>`;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadConversionRatePage();
});
