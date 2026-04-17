let customerStatusChart = null;
let salesCycleChart = null;

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

    // Ensure 'Active' and 'Active w/o invoice' have distinct colors
    const colorMap = {
        'Active': '#4b6e9e',
        'Active w/o invoice': '#e68b5a',
        'Inactive': '#c74d6f',
        'Suspend': '#7cce82',
        'Prospect': '#b49aff',
        'Pending': '#f7c873',
    };
    const labels = items.map(item => item.label);
    const counts = items.map(item => item.count);
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
        const totalCustomers = counts.reduce((sum, count) => sum + count, 0);
        const activeItem = items.find(item => item.code === 'A');
        const awoItem = items.find(item => item.code === 'AWO');
        summary.innerHTML = `<strong>${totalCustomers}</strong> total customers. Active: <strong>${activeItem ? activeItem.count : 0}</strong>. Active w/o invoice: <strong>${awoItem ? awoItem.count : 0}</strong>.`;
    }
}

async function loadCustomerStatusWidget() {
    const summary = document.getElementById('customer-status-summary');
    try {
        const response = await fetch('/api/admin/customer_status_summary');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load customer status summary');
        }

        renderCustomerStatusChart(payload.data.items);
    } catch (error) {
        if (summary) {
            summary.textContent = error.message || 'Failed to load customer status summary.';
        }
    }
}

async function loadSalesCycleWidget() {
    const summaryEl = document.getElementById('sales-cycle-summary');
    const breakdownEl = document.getElementById('sales-cycle-breakdown');
    const canvas = document.getElementById('sales-cycle-chart');

    try {
        const response = await fetch('/api/admin/sales_cycle_details');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load sales cycle metrics');
        }

        const data = payload.data;
        const totalInvoices = Number(data.total_converted_invoices || 0);
        const avgDays = Number(data.avg_sales_cycle_days || 0);
        const sorted = [...data.items]
            .sort((a, b) => Number(b.sales_cycle_minutes || 0) - Number(a.sales_cycle_minutes || 0))
            .slice(0, 10);

        const labels = sorted.map(item => item.invoice_docno || `DOCKEY ${item.invoice_dockey}`);
        const values = sorted.map(item => Number(item.sales_cycle_minutes || 0));
        const backgroundColors = sorted.map(item => {
            const days = Number(item.sales_cycle_days || 0);
            if (days >= 30) return 'rgba(199, 77, 111, 0.82)';
            if (days >= 14) return 'rgba(230, 139, 90, 0.82)';
            return 'rgba(106, 143, 199, 0.82)';
        });

        if (summaryEl) {
            summaryEl.innerHTML = `<strong>${avgDays.toFixed(2)}</strong> average days`;
        }
        if (breakdownEl) {
            breakdownEl.innerHTML = `Top <strong>${labels.length}</strong> longest invoices shown. Converted invoices: <strong>${totalInvoices}</strong>.`;
        }

        if (canvas && typeof Chart !== 'undefined') {
            if (salesCycleChart) {
                salesCycleChart.destroy();
            }

            salesCycleChart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Sales Cycle',
                        data: values,
                        backgroundColor: backgroundColors,
                        borderColor: '#9bb8ea',
                        borderWidth: 1,
                        borderRadius: 8,
                        maxBarThickness: 28,
                    }],
                },
                options: {
                    indexAxis: 'x',
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            ticks: {
                                color: '#d8deea',
                                maxRotation: 40,
                                minRotation: 30,
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.08)',
                            },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: '#d8deea',
                                callback(value) {
                                    if (value < 1440) {
                                        return `${Math.round(value / 60)}h`;
                                    }
                                    return `${Math.round(value / 1440)}d`;
                                },
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.05)',
                            },
                            title: {
                                display: true,
                                text: 'Cycle Duration',
                                color: '#b8c7e0',
                            },
                        },
                    },
                    plugins: {
                        legend: {
                            display: false,
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    const item = sorted[context.dataIndex];
                                    return `Cycle: ${item.sales_cycle_display || `${item.sales_cycle_days || 0} day(s)`}`;
                                },
                            },
                        },
                    },
                },
            });
        }
    } catch (error) {
        if (summaryEl) {
            summaryEl.textContent = 'Sales cycle unavailable';
        }
        if (breakdownEl) {
            breakdownEl.textContent = error.message || 'Failed to load sales cycle metrics.';
        }
    }
}

async function loadQtIvConversionWidget() {
    const summaryEl = document.getElementById('qt-iv-conversion-summary');
    const breakdownEl = document.getElementById('qt-iv-conversion-breakdown');

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
                        'Accept': 'application/json',
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

                // Flask proxy shape: { success: true, data: { ... } }
                if (payload && payload.success === true && payload.data && typeof payload.data === 'object') {
                    data = payload.data;
                    break;
                }

                // Direct FastAPI shape: { total_qt_lines, ... }
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
            if (lastError && /404/.test(String(lastError.message || ''))) {
                throw new Error('QT->IV conversion proxy route is unavailable on the current Flask server. Restart the Flask app so the new /api/admin/qt_iv_conversion_report route is loaded.');
            }
            throw lastError || new Error('Failed to load QT->IV conversion report');
        }

        const totalLines = Number(data.total_qt_lines || 0);
        const totalQtQty = Number(data.total_qt_qty || 0);
        const totalIvQty = Number(data.total_iv_qty || 0);
        const overallPct = Number(data.overall_conversion_pct || 0);
        const notInvoiced = Number(data.not_invoiced_lines || 0);
        const partial = Number(data.partial_lines || 0);
        const fullOrOver = Number(data.full_or_over_lines || 0);

        if (summaryEl) {
            summaryEl.innerHTML = `<strong>${overallPct.toFixed(2)}%</strong> overall conversion`;
        }
        if (breakdownEl) {
            breakdownEl.innerHTML = `QT lines: <strong>${totalLines}</strong>. QT qty: <strong>${totalQtQty.toFixed(2)}</strong>. IV qty: <strong>${totalIvQty.toFixed(2)}</strong>. Not invoiced: <strong>${notInvoiced}</strong>, partial: <strong>${partial}</strong>, full/over: <strong>${fullOrOver}</strong>.`;
        }

        // Render line chart of each quotation's conversion %
        const chartEl = document.getElementById('qt-iv-conversion-chart');
        if (chartEl && typeof Chart !== 'undefined' && Array.isArray(data.items)) {
            // Sort by date, then docno
            const sorted = [...data.items].sort((a, b) => {
                if (a.qt_docdate !== b.qt_docdate) {
                    return (a.qt_docdate || '').localeCompare(b.qt_docdate || '');
                }
                return (a.qt_docno || '').localeCompare(b.qt_docno || '');
            });

            // Ignore 0% conversions for lowest calculation and chart points.
            const nonzeroItems = sorted.filter(item => Number(item.conversion_pct || 0) > 0);
            const labels = nonzeroItems.map(item => item.qt_docno || '');
            const values = nonzeroItems.map(item => Number(item.conversion_pct || 0));

            const lowestNonzero = values.length > 0 ? Math.min(...values) : null;

            if (breakdownEl) {
                const baseText = `QT lines: <strong>${totalLines}</strong>. QT qty: <strong>${totalQtQty.toFixed(2)}</strong>. IV qty: <strong>${totalIvQty.toFixed(2)}</strong>. Not invoiced: <strong>${notInvoiced}</strong>, partial: <strong>${partial}</strong>, full/over: <strong>${fullOrOver}</strong>.`;
                const lowestText = lowestNonzero !== null
                    ? ` Lowest nonzero conversion: <strong>${lowestNonzero.toFixed(2)}%</strong>.`
                    : ' Lowest nonzero conversion: <strong>N/A</strong>.';
                breakdownEl.innerHTML = `${baseText}${lowestText}`;
            }

            if (window.qtIvConversionChart) {
                window.qtIvConversionChart.destroy();
            }
            window.qtIvConversionChart = new Chart(chartEl, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Conversion %',
                        data: values,
                        borderColor: '#4b6e9e',
                        backgroundColor: 'rgba(75, 110, 158, 0.15)',
                        pointBackgroundColor: '#e68b5a',
                        pointRadius: 3,
                        fill: true,
                        tension: 0.2,
                    }],
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
                                label: function(context) {
                                    return `QT ${context.label}: ${context.parsed.y.toFixed(2)}%`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: 'Quotation',
                                color: '#b8c7e0',
                            },
                            ticks: {
                                color: '#d8deea',
                                font: {
                                    size: 9,
                                },
                                maxRotation: 60,
                                minRotation: 30,
                                autoSkip: true,
                                maxTicksLimit: 20,
                            },
                            grid: {
                                color: 'rgba(255,255,255,0.08)',
                            },
                        },
                        y: {
                            beginAtZero: true,
                            max: 120,
                            title: {
                                display: true,
                                text: 'Conversion %',
                                color: '#b8c7e0',
                            },
                            ticks: {
                                color: '#d8deea',
                                callback: value => value + '%',
                            },
                            grid: {
                                color: 'rgba(255,255,255,0.05)',
                            },
                        },
                    },
                },
            });
        }
    } catch (error) {
        if (summaryEl) {
            summaryEl.textContent = 'QT->IV conversion unavailable';
        }
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