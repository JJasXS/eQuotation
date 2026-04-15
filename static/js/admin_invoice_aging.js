let invoiceAgingChart = null;
let allInvoiceAgingItems = [];
let currentAgingFilter = 'all';

const invoiceAgingBarLabelPlugin = {
    id: 'invoiceAgingBarLabelPlugin',
    afterDatasetsDraw(chart) {
        const { ctx } = chart;
        const dataset = chart.data.datasets[0];
        const meta = chart.getDatasetMeta(0);
        if (!dataset || !meta || !meta.data) {
            return;
        }

        ctx.save();
        ctx.font = '600 12px Segoe UI';
        ctx.textBaseline = 'middle';

        meta.data.forEach((bar, index) => {
            const label = dataset.barLabels?.[index];
            if (!label) {
                return;
            }

            const position = bar.tooltipPosition();
            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'right';
            ctx.fillText(label, position.x - 10, position.y);
        });

        ctx.restore();
    },
};

const invoiceAgingThresholdPlugin = {
    id: 'invoiceAgingThresholdPlugin',
    afterDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        if (!chartArea || !scales?.x) {
            return;
        }

        const xScale = scales.x;
        const thresholds = [30, 60, 90];

        // Highlight the ">90 days" area.
        const zoneStart = xScale.getPixelForValue(90);
        const zoneEnd = xScale.getPixelForValue(xScale.max); // rightmost value
        const left = Math.min(zoneStart, zoneEnd);
        const right = Math.max(zoneStart, zoneEnd);

        ctx.save();
        ctx.fillStyle = 'rgba(255, 0, 0, 0.08)';
        ctx.fillRect(left, chartArea.top, right - left, chartArea.bottom - chartArea.top);

        ctx.font = '600 11px Segoe UI';
        ctx.fillStyle = '#ff0000';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText('>90 days', left + 6, chartArea.top + 6);

        thresholds.forEach((value, index) => {
            const x = xScale.getPixelForValue(value);
            if (Number.isNaN(x)) {
                return;
            }

            ctx.beginPath();
            ctx.setLineDash([4, 4]);
            ctx.strokeStyle = index === 2 ? '#ff8e72' : '#8fb5ec';
            ctx.lineWidth = 1;
            ctx.moveTo(x, chartArea.top);
            ctx.lineTo(x, chartArea.bottom);
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.fillStyle = index === 2 ? '#ffb39e' : '#b8cff1';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillText(`${value} days`, x, chartArea.top - 6);
        });

        ctx.restore();
    },
};

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

function renderInvoiceAgingChart(items) {
    const canvas = document.getElementById('invoice-aging-chart');
    if (!canvas || typeof Chart === 'undefined') {
        return;
    }

    // Show all companies, but remove 'No invoice' from barLabels only
    const labels = items.map(item => item.company_name || item.code);
    const counts = items.map(item => item.days_ago);
    const docdates = items.map(item => item.docdate);
    // Remove 'No invoice' from barLabels so it doesn't overlap
    const barLabels = items.map(item => item.days_ago_label === 'No invoice' ? '' : item.days_ago_label);
    const maxDays = counts.length ? Math.max(...counts) : 0;
    const xAxisMax = Math.max(90, maxDays + 5);

    const chartWrap = canvas.parentElement;
    if (chartWrap) {
        chartWrap.style.minHeight = `${Math.max(420, items.length * 42)}px`;
    }

    if (invoiceAgingChart) {
        invoiceAgingChart.destroy();
    }

    invoiceAgingChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Days Ago',
                data: counts,
                backgroundColor: '#6a8fc7',
                borderColor: '#9bb8ea',
                borderWidth: 1,
                borderRadius: 8,
                maxBarThickness: 42,
                barLabels,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    max: xAxisMax,
                    ticks: {
                        color: '#d8deea',
                        precision: 0,
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                    },
                },
                y: {
                    ticks: {
                        color: '#d8deea',
                        autoSkip: false,
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.06)',
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
                            return `${context[0].label} (${formatDisplayDate(docdates[index])})`;
                        },
                        label(context) {
                            return `Age: ${context.parsed.x} day(s)`;
                        },
                    },
                },
            },
        },
        plugins: [invoiceAgingThresholdPlugin, invoiceAgingBarLabelPlugin],
    });
}

function renderInvoiceAgingList(items) {
    const container = document.getElementById('invoice-aging-list');
    if (!container) {
        return;
    }

    if (!items.length) {
        container.innerHTML = '<div class="analytics-empty">No invoice dates found in SL_IV.</div>';
        return;
    }

    container.innerHTML = items.map(item => `
        <div class="analytics-list-item">
            <span>${item.company_name || item.code}</span>
            <span>${formatDisplayDate(item.docdate)} · ${item.days_ago_label}</span>
        </div>
    `).join('');
}

async function loadInvoiceAging() {
    const totalEl = document.getElementById('invoice-aging-total');
    const todayEl = document.getElementById('invoice-aging-today');
    const latestEl = document.getElementById('invoice-aging-latest');
    const listEl = document.getElementById('invoice-aging-list');
    const latestCompanyEl = document.getElementById('invoice-aging-latest-company');

    try {
        const response = await fetch('/api/admin/invoice_aging_summary');
        const payload = await response.json();

        if (!response.ok || !payload.success || !payload.data || !Array.isArray(payload.data.items)) {
            throw new Error(payload.error || 'Failed to load invoice aging data');
        }

        const items = payload.data.items;
        allInvoiceAgingItems = items;
        if (totalEl) {
            totalEl.textContent = String(payload.data.total_codes ?? 0);
        }
        if (todayEl) {
            todayEl.textContent = formatDisplayDate(payload.data.today);
        }

        if (latestEl) {
            latestEl.textContent = payload.data.latest_invoice_age || 'No invoices';
        }
        if (latestCompanyEl) {
            latestCompanyEl.textContent = payload.data.latest_invoice_company || '-';
        }

        applyAgingFilter();
    } catch (error) {
        if (listEl) {
            listEl.innerHTML = `<div class="analytics-empty">${error.message || 'Failed to load invoice aging details.'}</div>`;
        }
        if (latestEl) {
            latestEl.textContent = 'Error';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadInvoiceAging();
    const filterEl = document.getElementById('invoice-aging-filter');
    if (filterEl) {
        filterEl.addEventListener('change', (e) => {
            currentAgingFilter = e.target.value;
            applyAgingFilter();
        });
    }
});

function applyAgingFilter() {
    let filtered = allInvoiceAgingItems;
    if (currentAgingFilter !== 'all') {
        if (currentAgingFilter === 'active') {
            // Active with at least one invoice (not 'No invoice')
            filtered = allInvoiceAgingItems.filter(item => item.status === 'Active' && item.days_ago_label !== 'No invoice');
        } else if (currentAgingFilter === 'active_wo_invoice') {
            // Active but no invoice
            filtered = allInvoiceAgingItems.filter(item => item.status === 'Active' && item.days_ago_label === 'No invoice');
        } else if (currentAgingFilter === '>90') {
            filtered = allInvoiceAgingItems.filter(item => item.days_ago > 90);
        } else {
            const maxDays = parseInt(currentAgingFilter, 10);
            filtered = allInvoiceAgingItems.filter(item => item.days_ago <= maxDays);
        }
    }
    renderInvoiceAgingChart(filtered);
    renderInvoiceAgingList(filtered);
}
