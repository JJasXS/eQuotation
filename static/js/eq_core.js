/**
 * Shared front-end core helpers for eQuotation.
 * Load before page scripts: <script src="/static/js/eq_core.js"></script>
 *
 * Prefer these over redefining escapeHtml / formatMoney / formatDate / fetchJson.
 */
(function (global) {
    'use strict';

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    const DATE_FMT = new Intl.DateTimeFormat('en-MY', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });

    function formatDate(value) {
        if (!value) return '-';
        const raw = String(value);
        const date = new Date(raw.includes('T') ? raw : `${raw}T00:00:00`);
        if (Number.isNaN(date.getTime())) return raw;
        return DATE_FMT.format(date);
    }

    function formatMoney(value, currency) {
        const n = Number(value);
        const amount = Number.isFinite(n) ? n : 0;
        const prefix = currency ? `${String(currency).trim()} ` : '';
        return `${prefix}${amount.toLocaleString('en-MY', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}`;
    }

    async function fetchJson(url, options) {
        const resp = await fetch(url, options);
        let payload;
        try {
            payload = await resp.json();
        } catch (_err) {
            throw new Error(`Invalid JSON response from ${url}`);
        }
        if (!resp.ok) {
            const msg = (payload && (payload.error || payload.message || payload.detail)) || `HTTP ${resp.status}`;
            throw new Error(String(msg));
        }
        return payload;
    }

    const api = { escapeHtml, formatDate, formatMoney, fetchJson };
    global.EQCore = api;
    // Back-compat: older admin pages used window.EQ
    global.EQ = Object.assign({}, global.EQ || {}, api);
})(typeof window !== 'undefined' ? window : globalThis);
