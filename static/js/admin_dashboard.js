let customerStatusChart = null;

function renderCustomerStatusChart(items) {
    const canvas = document.getElementById('customer-status-chart');
    const summary = document.getElementById('customer-status-summary');

    if (!canvas || typeof Chart === 'undefined') {
        if (summary) {
            summary.textContent = 'Chart library failed to load.';
        }
        return;
    }

    const labels = items.map(item => item.label);
    const counts = items.map(item => item.count);
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
                backgroundColor: ['#4b6e9e', '#e68b5a', '#c74d6f', '#7cce82', '#b49aff'],
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
    loadCustomerStatusWidget();
});