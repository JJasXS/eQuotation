let customerStatusChart = null;
const ADMIN_DASHBOARD_CACHE_TTL_MS = 5 * 60 * 1000;

function readDashboardCache(key) {
    try {
        const raw = sessionStorage.getItem(key);
        if (!raw) return null;
        const cached = JSON.parse(raw);
        if (!cached || Date.now() - Number(cached.at || 0) > ADMIN_DASHBOARD_CACHE_TTL_MS) {
            sessionStorage.removeItem(key);
            return null;
        }
        return cached.data || null;
    } catch {
        return null;
    }
}

function writeDashboardCache(key, data) {
    try {
        sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), data }));
    } catch {
        // Ignore browser storage limits/private mode.
    }
}

function attachDashboardNavigation() {
    const widgets = document.querySelectorAll('.dashboard-widget--interactive[data-href]');
    if (!widgets.length) {
        return;
    }

    widgets.forEach(widget => {
        const href = widget.dataset.href;
        if (!href) {
            return;
        }

        widget.addEventListener('click', () => {
            window.location.href = href;
        });

        widget.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                window.location.href = href;
            }
        });
    });
}

function renderCustomerStatusChart(items) {
    const canvas = document.getElementById('customer-status-chart');
    const summary = document.getElementById('customer-status-summary');

    if (!canvas || typeof Chart === 'undefined') {
        if (summary) {
            summary.textContent = 'Chart library failed to load.';
        }
        return;
    }

    const colorMap = {
        'Active': '#4b6e9e',
        'Active w/o invoice': '#e68b5a',
        'Inactive': '#c74d6f',
        'Suspend': '#7cce82',
        'Prospect': '#b49aff',
        'Pending': '#f7c873',
    };

    const labels = items.map(item => item.label);
    const counts = items.map(item => Number(item.count || 0));
    const backgroundColors = items.map(item => colorMap[item.label] || '#cccccc');
    const totalCustomers = counts.reduce((sum, count) => sum + count, 0);

    if (customerStatusChart) {
        customerStatusChart.destroy();
    }

    customerStatusChart = new Chart(canvas, {
        type: 'pie',
        data: {
            labels,
            datasets: [{
                data: counts,
                backgroundColor: backgroundColors,
                borderColor: '#161c28',
                borderWidth: 2,
                hoverOffset: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#d8deea',
                        padding: 18,
                        usePointStyle: true,
                    },
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const value = context.parsed || 0;
                            const percent = totalCustomers > 0 ? ((value / totalCustomers) * 100).toFixed(1) : '0.0';
                            return `${context.label}: ${value} (${percent}%)`;
                        },
                    },
                },
            },
        },
    });

    if (summary) {
        const activeItem = items.find(item => item.code === 'A');
        const awoItem = items.find(item => item.code === 'AWO');
        summary.innerHTML = `<strong>${totalCustomers}</strong> total customers. Active: <strong>${activeItem ? activeItem.count : 0}</strong>. Active w/o invoice: <strong>${awoItem ? awoItem.count : 0}</strong>.`;
    }
}

function renderSalesCycleWidget(data) {
    const convertedEl = document.getElementById('sales-cycle-converted');
    const avgEl = document.getElementById('sales-cycle-avg');
    const shortestEl = document.getElementById('sales-cycle-shortest');
    const longestEl = document.getElementById('sales-cycle-longest');
    const breakdownEl = document.getElementById('sales-cycle-breakdown');
    const totalInvoices = Number(data.total_converted_invoices || 0);
    const avgDays = Number(data.avg_sales_cycle_days || 0);

    const validDays = (Array.isArray(data.items) ? data.items : [])
        .map(item => Number(item.sales_cycle_days || 0))
        .filter(days => Number.isFinite(days) && days > 0);

    const shortestDays = validDays.length ? Math.min(...validDays) : 0;
    const longestDays = validDays.length ? Math.max(...validDays) : 0;

    if (convertedEl) convertedEl.textContent = String(totalInvoices);
    if (avgEl) avgEl.textContent = `${avgDays.toFixed(2)} days`;
    if (shortestEl) shortestEl.textContent = `${Math.round(shortestDays)} day(s)`;
    if (longestEl) longestEl.textContent = `${Math.round(longestDays)} day(s)`;
    if (breakdownEl) breakdownEl.textContent = 'Click this card for detail view.';
}

function renderQtIvConversionWidget(data) {
    const totalEl = document.getElementById('conversion-total-qt');
    const avgEl = document.getElementById('conversion-avg');
    const topEl = document.getElementById('conversion-top');
    const lowEl = document.getElementById('conversion-low');
    const breakdownEl = document.getElementById('qt-iv-conversion-breakdown');
    const lines = Array.isArray(data.items) ? data.items : [];

    const pick = (obj, ...keys) => {
        for (const key of keys) {
            if (obj && Object.prototype.hasOwnProperty.call(obj, key)) {
                return obj[key];
            }
        }
        return undefined;
    };

    const grouped = lines.reduce((acc, item) => {
        const key = String(
            pick(item, 'qt_docno', 'QT_DOCNO', 'qt_dockey', 'QT_DOCKEY') || ''
        ).trim();
        if (!key) {
            return acc;
        }

        if (!acc[key]) {
            acc[key] = {
                qt_qty: 0,
                iv_qty: 0,
            };
        }

        acc[key].qt_qty += Number(pick(item, 'qt_qty', 'QT_QTY') || 0);
        acc[key].iv_qty += Number(pick(item, 'iv_qty', 'IV_QTY') || 0);
        return acc;
    }, {});

    const rows = Object.values(grouped).map(row => {
        const qtQty = Number(row.qt_qty || 0);
        const ivQty = Number(row.iv_qty || 0);
        const pct = qtQty > 0 ? (ivQty / qtQty) * 100 : 0;
        return {
            qt_qty: qtQty,
            iv_qty: ivQty,
            conversion_pct: Number(pct.toFixed(2)),
        };
    });

    const totalQt = rows.length;
    const groupedQtQty = rows.reduce((sum, row) => sum + row.qt_qty, 0);
    const groupedIvQty = rows.reduce((sum, row) => sum + row.iv_qty, 0);
    const apiQtQty = Number(data.total_qt_qty || data.TOTAL_QT_QTY || 0);
    const apiIvQty = Number(data.total_iv_qty || data.TOTAL_IV_QTY || 0);
    const totalQtQty = groupedQtQty > 0 ? groupedQtQty : apiQtQty;
    const totalIvQty = groupedIvQty > 0 ? groupedIvQty : apiIvQty;
    const weightedAvg = totalQtQty > 0 ? (totalIvQty / totalQtQty) * 100 : 0;
    const top = rows.length ? Math.max(...rows.map(row => row.conversion_pct)) : 0;
    const nonzeroRows = rows.filter(row => row.conversion_pct > 0);
    const low = nonzeroRows.length ? Math.min(...nonzeroRows.map(row => row.conversion_pct)) : 0;

    if (totalEl) totalEl.textContent = String(totalQt);
    if (avgEl) avgEl.textContent = `${weightedAvg.toFixed(2)}%`;
    if (topEl) topEl.textContent = `${top.toFixed(2)}%`;
    if (lowEl) lowEl.textContent = `${low.toFixed(2)}%`;

    if (breakdownEl) {
        const totalLines = Number(data.total_qt_lines || data.TOTAL_QT_LINES || lines.length || 0);
        const notInvoiced = Number(data.not_invoiced_lines || data.NOT_INVOICED_LINES || 0);
        const partial = Number(data.partial_lines || data.PARTIAL_LINES || 0);
        const fullOrOver = Number(data.full_or_over_lines || data.FULL_OR_OVER_LINES || 0);
        breakdownEl.innerHTML = `QT lines: <strong>${totalLines}</strong>. QT qty: <strong>${totalQtQty.toFixed(2)}</strong>. IV qty: <strong>${totalIvQty.toFixed(2)}</strong>. Not invoiced: <strong>${notInvoiced}</strong>, partial: <strong>${partial}</strong>, full/over: <strong>${fullOrOver}</strong>.`;
    }
}

async function loadCustomerStatusWidget() {
    const summary = document.getElementById('customer-status-summary');
    const cached = readDashboardCache('adminDashboard.customerStatus');
    if (cached && Array.isArray(cached.items)) {
        renderCustomerStatusChart(cached.items);
    }
    try {
        const response = await fetch('/api/admin/customer_status_summary');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load customer status summary');
        }

        renderCustomerStatusChart(payload.data.items);
        writeDashboardCache('adminDashboard.customerStatus', { items: payload.data.items });
    } catch (error) {
        if (summary && !cached) {
            summary.textContent = error.message || 'Failed to load customer status summary.';
        }
    }
}

async function loadSalesCycleWidget() {
    const convertedEl = document.getElementById('sales-cycle-converted');
    const avgEl = document.getElementById('sales-cycle-avg');
    const shortestEl = document.getElementById('sales-cycle-shortest');
    const longestEl = document.getElementById('sales-cycle-longest');
    const breakdownEl = document.getElementById('sales-cycle-breakdown');
    const cached = readDashboardCache('adminDashboard.salesCycle');
    if (cached) {
        renderSalesCycleWidget(cached);
    }

    try {
        const response = await fetch('/api/admin/sales_cycle_details');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load sales cycle metrics');
        }

        renderSalesCycleWidget(payload.data);
        writeDashboardCache('adminDashboard.salesCycle', payload.data);
    } catch (error) {
        if (cached) return;
        if (convertedEl) convertedEl.textContent = '0';
        if (avgEl) avgEl.textContent = '0.00 days';
        if (shortestEl) shortestEl.textContent = '0 day(s)';
        if (longestEl) longestEl.textContent = '0 day(s)';
        if (breakdownEl) breakdownEl.textContent = error.message || 'Failed to load sales cycle metrics.';
    }
}

async function loadQtIvConversionWidget() {
    const totalEl = document.getElementById('conversion-total-qt');
    const avgEl = document.getElementById('conversion-avg');
    const topEl = document.getElementById('conversion-top');
    const lowEl = document.getElementById('conversion-low');
    const breakdownEl = document.getElementById('qt-iv-conversion-breakdown');
    const cached = readDashboardCache('adminDashboard.qtIvConversion');
    if (cached) {
        renderQtIvConversionWidget(cached);
    }

    try {
        const candidateUrls = [
            '/api/admin/qt_iv_conversion_report',
            '/api/admin/qt-iv-conversion-report',
        ];

        let data = null;
        let lastError = null;

        for (const url of candidateUrls) {
            try {
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        Accept: 'application/json',
                    },
                });

                const raw = await response.text();
                const contentType = (response.headers.get('content-type') || '').toLowerCase();
                const looksJson = contentType.includes('application/json') || raw.trim().startsWith('{') || raw.trim().startsWith('[');

                if (!looksJson) {
                    const preview = raw.trim().slice(0, 80).replace(/\s+/g, ' ');
                    throw new Error(`Non-JSON response from ${url} (${response.status}): ${preview || 'empty response'}`);
                }

                let payload;
                try {
                    payload = JSON.parse(raw);
                } catch {
                    throw new Error(`Invalid JSON payload from ${url} (${response.status})`);
                }

                if (!response.ok) {
                    const err = (payload && (payload.error || payload.detail)) || `HTTP ${response.status}`;
                    throw new Error(`${url}: ${err}`);
                }

                if (payload && payload.success === true && payload.data && typeof payload.data === 'object') {
                    data = payload.data;
                    break;
                }

                if (payload && typeof payload === 'object' && Object.prototype.hasOwnProperty.call(payload, 'total_qt_lines')) {
                    data = payload;
                    break;
                }

                throw new Error(`${url}: Unexpected QT->IV response format`);
            } catch (err) {
                lastError = err;
            }
        }

        if (!data) {
            throw lastError || new Error('Failed to load QT->IV conversion report');
        }

        renderQtIvConversionWidget(data);
        writeDashboardCache('adminDashboard.qtIvConversion', data);
    } catch (error) {
        if (cached) return;
        if (totalEl) totalEl.textContent = '0';
        if (avgEl) avgEl.textContent = '0.00%';
        if (topEl) topEl.textContent = '0.00%';
        if (lowEl) lowEl.textContent = '0.00%';
        if (breakdownEl) {
            breakdownEl.textContent = error.message || 'Failed to load QT->IV conversion report.';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    attachDashboardNavigation();
    loadCustomerStatusWidget();
    loadSalesCycleWidget();
    loadQtIvConversionWidget();
});
