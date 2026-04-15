let customerStatusChart = null;

function attachDashboardNavigation() {
    const widget = document.getElementById('customer-status-widget');
    if (!widget) {
        return;
    }

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

document.addEventListener('DOMContentLoaded', () => {
    attachDashboardNavigation();
    loadCustomerStatusWidget();
});