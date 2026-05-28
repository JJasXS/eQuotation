/* /admin/invoice-aging — bar chart + recent age list.
 * Depends on /static/js/admin_helpers.js (window.EQ) and Chart.js (global Chart).
 */
(function () {
    'use strict';

    const { escapeHtml, formatDate, apiGet } = window.EQ;

    const state = {
        chart: null,
        items: [],
        filter: 'all',
        offset: 0,
        limit: 10,
        hasMore: false,
    };

    const barLabelPlugin = {
        id: 'invoiceAgingBarLabelPlugin',
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            const dataset = chart.data.datasets[0];
            const meta = chart.getDatasetMeta(0);
            if (!dataset || !meta || !meta.data) return;

            ctx.save();
            ctx.font = '600 12px Segoe UI';
            ctx.textBaseline = 'middle';

            meta.data.forEach((bar, index) => {
                const label = dataset.barLabels?.[index];
                if (!label) return;
                const position = bar.tooltipPosition();
                ctx.fillStyle = '#fff';
                ctx.textAlign = 'right';
                ctx.fillText(label, position.x - 6, position.y);
            });

            ctx.restore();
        },
    };

    const thresholdPlugin = {
        id: 'invoiceAgingThresholdPlugin',
        afterDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            if (!chartArea || !scales?.x) return;

            const xScale = scales.x;
            const thresholds = [30, 60, 90];

            const zoneStart = xScale.getPixelForValue(90);
            const zoneEnd = xScale.getPixelForValue(xScale.max);
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
                if (Number.isNaN(x)) return;

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

    function renderChart(items) {
        const canvas = document.getElementById('invoice-aging-chart');
        if (!canvas || typeof Chart === 'undefined') return;

        const labels = items.map(item => item.company_name || item.code);
        const counts = items.map(item => item.days_ago);
        const docdates = items.map(item => item.docdate);
        const barLabels = items.map(item => item.days_ago_label === 'No invoice' ? '' : item.days_ago_label);
        const maxDays = counts.length ? Math.max(...counts) : 0;
        const xAxisMax = Math.max(90, maxDays + 5);

        const chartWrap = document.getElementById('invoice-aging-chart-wrap') || canvas.parentElement;
        if (chartWrap) {
            chartWrap.style.minHeight = `${Math.max(320, items.length * 38)}px`;
        }

        if (state.chart) state.chart.destroy();

        state.chart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Days Ago',
                    data: counts,
                    backgroundColor: '#3b8fc4',
                    borderColor: '#5aaee0',
                    borderWidth: 1,
                    borderRadius: 6,
                    maxBarThickness: 36,
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
                        ticks: { color: '#5a7a94', precision: 0 },
                        grid: { color: 'rgba(30, 80, 120, 0.1)' },
                    },
                    y: {
                        ticks: { color: '#1e3a52', autoSkip: false },
                        grid: { color: 'rgba(30, 80, 120, 0.07)' },
                    },
                },
                plugins: {
                    legend: { labels: { color: '#5a7a94' } },
                    tooltip: {
                        callbacks: {
                            title(context) {
                                const index = context[0].dataIndex;
                                return `${context[0].label} (${formatDate(docdates[index])})`;
                            },
                            label(context) {
                                return `Age: ${context.parsed.x} day(s)`;
                            },
                        },
                    },
                },
            },
            plugins: [thresholdPlugin, barLabelPlugin],
        });
    }

    function renderList(items) {
        const container = document.getElementById('invoice-aging-list');
        if (!container) return;

        if (!items.length) {
            container.innerHTML = '<div class="ia-empty">No invoice dates found in SL_IV.</div>';
            return;
        }

        container.innerHTML = items.map(item => {
            const noInvoice = item.days_ago_label === 'No invoice';
            const over90 = !noInvoice && item.days_ago > 90;
            const ageClass = noInvoice ? 'ia-age--no-invoice' : (over90 ? 'ia-age--over90' : '');
            const name = item.company_name || item.code;
            return `
            <div class="ia-list-item">
                <span class="ia-list-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
                <span class="ia-list-age ${ageClass}">${escapeHtml(formatDate(item.docdate))} · ${escapeHtml(item.days_ago_label || '-')}</span>
            </div>`;
        }).join('');
    }

    function applyFilter() {
        let filtered = state.items;
        if (state.filter !== 'all') {
            if (state.filter === '>90') {
                filtered = state.items.filter(item => item.days_ago > 90);
            } else {
                const maxDays = parseInt(state.filter, 10);
                if (Number.isFinite(maxDays)) {
                    filtered = state.items.filter(item => item.days_ago <= maxDays);
                }
            }
        }
        renderChart(filtered);
        renderList(filtered);
    }

    async function loadPage(reset = false) {
        const totalEl = document.getElementById('invoice-aging-total');
        const todayEl = document.getElementById('invoice-aging-today');
        const latestEl = document.getElementById('invoice-aging-latest');
        const listEl = document.getElementById('invoice-aging-list');
        const latestCompanyEl = document.getElementById('invoice-aging-latest-company');
        const moreBtn = document.getElementById('invoice-aging-more-btn');

        if (reset) {
            state.offset = 0;
            state.items = [];
            if (listEl) listEl.innerHTML = '<div class="ia-empty">Loading invoice aging details...</div>';
            if (moreBtn) moreBtn.style.display = 'none';
        }

        try {
            const data = await apiGet(`/api/admin/invoice_aging_summary?offset=${state.offset}&limit=${state.limit}`);
            const items = Array.isArray(data?.items) ? data.items : [];

            state.items = reset ? items : state.items.concat(items);
            state.offset += items.length;
            state.hasMore = !!data?.has_more;

            if (totalEl) totalEl.textContent = String(data?.total_codes ?? 0);
            if (todayEl) todayEl.textContent = formatDate(data?.today);
            if (latestEl) latestEl.textContent = data?.latest_invoice_age || 'No invoices';
            if (latestCompanyEl) latestCompanyEl.textContent = data?.latest_invoice_company || '-';

            applyFilter();

            if (moreBtn) moreBtn.style.display = state.hasMore ? '' : 'none';
        } catch (error) {
            if (listEl) listEl.innerHTML = `<div class="ia-empty">${escapeHtml(error.message || 'Failed to load invoice aging details.')}</div>`;
            if (latestEl) latestEl.textContent = 'Error';
            if (moreBtn) moreBtn.style.display = 'none';
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadPage(true);

        const filterEl = document.getElementById('invoice-aging-filter');
        if (filterEl) {
            filterEl.addEventListener('change', (e) => {
                state.filter = e.target.value;
                applyFilter();
            });
        }

        const moreBtn = document.getElementById('invoice-aging-more-btn');
        if (moreBtn) {
            moreBtn.addEventListener('click', () => loadPage(false));
        }
    });
})();
