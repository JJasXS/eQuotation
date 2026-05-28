/**
 * Shared front-end helpers for admin pages.
 *
 * Exposes a small `EQ` namespace with pure utilities to avoid duplicating
 * escapeHtml / formatDisplayDate / fetch wrappers across admin_*.js files.
 *
 * Usage:  <script src="/static/js/admin_helpers.js"></script>
 *         const { escapeHtml, formatDate, apiGet } = window.EQ;
 */
(function () {
    'use strict';

    /** HTML-escape any value (null/undefined → ''). */
    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /** Format ISO date (YYYY-MM-DD) or pass-through into "5 Mar 2026". */
    const DATE_FMT = new Intl.DateTimeFormat('en-MY', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });

    function formatDate(value) {
        if (!value) return '-';
        const date = new Date(`${value}T00:00:00`);
        if (Number.isNaN(date.getTime())) return value;
        return DATE_FMT.format(date);
    }

    /**
     * GET JSON. Throws if non-2xx OR payload.success === false.
     * Returns payload.data (or the whole payload if no `data` key).
     */
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

    /** Return a number with N decimals; 0 if value isn't finite. */
    function toFixed(value, digits = 2) {
        const n = Number(value);
        return Number.isFinite(n) ? n.toFixed(digits) : (0).toFixed(digits);
    }

    /**
     * Wire up a list of buttons that share a `data-*` attribute as a single-select toggle.
     * @param {NodeListOf<HTMLElement>|HTMLElement[]} buttons
     * @param {(value: string, btn: HTMLElement) => void} onChange
     */
    function bindSelectableButtons(buttons, onChange) {
        buttons.forEach((btn) => {
            btn.addEventListener('click', () => {
                buttons.forEach((b) => b.classList.toggle('active', b === btn));
                onChange(btn.dataset.value ?? btn.dataset.range ?? '', btn);
            });
        });
    }

    window.EQ = Object.freeze({
        escapeHtml,
        formatDate,
        apiGet,
        toFixed,
        bindSelectableButtons,
    });
})();
