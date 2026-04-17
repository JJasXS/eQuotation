let salesCycleChart = null;
let salesCycleItems = [];
let salesCycleSort = 'desc';

function formatDisplayDate(value) {
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

function sortedSalesCycleItems(items) {
    const sorted = [...items];
    sorted.sort((a, b) => {
        // Sort by minutes (longest to shortest or vice versa)
        if (salesCycleSort === 'asc') {
            return a.sales_cycle_minutes - b.sales_cycle_minutes;
        }
        return b.sales_cycle_minutes - a.sales_cycle_minutes;
    });
    return sorted;
}

function renderSalesCycleChart(items) {
    const canvas = document.getElementById('sales-cycle-chart');
    if (!canvas || typeof Chart === 'undefined') {
        return;
    }

    if (!items.length) {
        if (salesCycleChart) {
            salesCycleChart.destroy();
            salesCycleChart = null;
        }
        return;
    }

    const sorted = sortedSalesCycleItems(items);

    const labels = sorted.map(item => item.invoice_docno || `DOCKEY ${item.invoice_dockey}`);
    // Use minutes for value, but display as hours if <1 day, else days
    const values = sorted.map(item => item.sales_cycle_minutes);
    const maxMinutes = values.length ? Math.max(...values) : 0;
    const chartWrap = canvas.parentElement;

    if (chartWrap) {
        chartWrap.style.minHeight = `${Math.max(420, sorted.length * 36)}px`;
    }

    const backgroundColors = sorted.map(item => {
        if (item.sales_cycle_days >= 30) return 'rgba(199, 77, 111, 0.82)';
        if (item.sales_cycle_days >= 14) return 'rgba(230, 139, 90, 0.82)';
        return 'rgba(106, 143, 199, 0.82)';
    });

    if (salesCycleChart) {
        salesCycleChart.destroy();
    }

    salesCycleChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Sales Cycle',
                data: values,
                fill: false,
                borderColor: '#6a8fc7',
                backgroundColor: '#6a8fc7',
                tension: 0.3,
                pointBackgroundColor: backgroundColors,
                pointBorderColor: '#9bb8ea',
                pointRadius: 5,
                pointHoverRadius: 7,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: {
                        color: '#d8deea',
                        autoSkip: false,
                        maxRotation: 40,
                        minRotation: 30,
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.08)',
                    },
                    title: {
                        display: true,
                        text: 'Invoice',
                        color: '#b8c7e0',
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
                    labels: {
                        color: '#d8deea',
                    },
                },
                tooltip: {
                    callbacks: {
                        title(context) {
                            const index = context[0].dataIndex;
                            const item = sorted[index];
                            const invoiceLabel = item.invoice_docno || `DOCKEY ${item.invoice_dockey}`;
                            return `Invoice: ${invoiceLabel}`;
                        },
                        label(context) {
                            const index = context.dataIndex;
                            const item = sorted[index];
                            const qtDocNo = item.quotation_docno || '-';
                            const qtDate = formatDisplayDate(item.quotation_docdate);
                            const ivDate = formatDisplayDate(item.invoice_docdate);
                            return [
                                `Cycle: ${item.sales_cycle_display}`,
                                `Quotation: ${qtDocNo} (${qtDate})`,
                                `Invoice date: ${ivDate}`,
                            ];
                        },
                    },
                },
            },
        },
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
    container.innerHTML = sorted.map(item => {
        const invoiceLabel = item.invoice_docno || `DOCKEY ${item.invoice_dockey}`;
        const quotationLabel = item.quotation_docno || '-';
        const qtDate = formatDisplayDate(item.quotation_docdate);
        const ivDate = formatDisplayDate(item.invoice_docdate);
        const company = item.company_name ? `<span class="company-pill">${item.company_name}</span>` : '';
        return `
            <div class="analytics-list-item">
                <span>${invoiceLabel} · ${item.sales_cycle_display} ${company}</span>
                <span>QT ${quotationLabel} (${qtDate}) → IV (${ivDate})</span>
            </div>
        `;
    }).join('');
}

function renderSalesCycleView() {
    renderSalesCycleChart(salesCycleItems);
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

    const sortEl = document.getElementById('sales-cycle-sort');
    if (sortEl) {
        sortEl.addEventListener('change', (event) => {
            salesCycleSort = event.target.value;
            renderSalesCycleView();
        });
    }
});
