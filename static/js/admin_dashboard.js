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

document.addEventListener('DOMContentLoaded', () => {
    attachDashboardNavigation();
    loadCustomerStatusWidget();
    loadSalesCycleWidget();
});