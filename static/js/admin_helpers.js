/**
 * Shared front-end helpers for admin pages.
 *
 * Prefer loading eq_core.js first. This module adds admin-only helpers
 * (apiGet, toFixed, bindSelectableButtons) onto window.EQ.
 *
 * Usage:  <script src="/static/js/eq_core.js"></script>
 *         <script src="/static/js/admin_helpers.js"></script>
 *         const { escapeHtml, formatDate, apiGet } = window.EQ;
 */
(function () {
    'use strict';

    const core = window.EQCore || window.EQ || {};
    const escapeHtml = core.escapeHtml || function (value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };
    const formatDate = core.formatDate || function (value) {
        if (!value) return '-';
        const date = new Date(`${value}T00:00:00`);
        if (Number.isNaN(date.getTime())) return value;
        return value;
    };

    async function apiGet(url, { signal } = {}) {
        const resp = await fetch(url, { signal, headers: { Accept: 'application/json' } });
        let payload;
        try {
            payload = await resp.json();
        } catch (err) {
            throw new Error(`Invalid JSON response from ${url}`);
        }
        if (!resp.ok) {
            throw new Error((payload && payload.error) || `HTTP ${resp.status} from ${url}`);
        }
        if (payload && payload.success === false) {
            throw new Error(payload.error || 'Request failed');
        }
        return payload && Object.prototype.hasOwnProperty.call(payload, 'data') ? payload.data : payload;
    }

    function toFixed(value, digits = 2) {
        const n = Number(value);
        return Number.isFinite(n) ? n.toFixed(digits) : (0).toFixed(digits);
    }

    function bindSelectableButtons(buttons, onChange) {
        buttons.forEach((btn) => {
            btn.addEventListener('click', () => {
                buttons.forEach((b) => b.classList.toggle('active', b === btn));
                onChange(btn.dataset.value ?? btn.dataset.range ?? '', btn);
            });
        });
    }

    window.EQ = Object.assign({}, core, {
        escapeHtml,
        formatDate,
        apiGet,
        toFixed,
        bindSelectableButtons,
    });
})();
