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

    function _loginHtml(text) {
        const sample = String(text || '').slice(0, 500).toLowerCase();
        const isDoc = sample.indexOf('<!doctype') === 0 || sample.indexOf('<html') === 0;
        return isDoc && (sample.indexOf('<title>sign in</title>') !== -1 || sample.indexOf('login-page') !== -1);
    }

    function _authExpiredError() {
        const err = new Error('Session expired. Please sign in again.');
        err.authExpired = true;
        return err;
    }

    function _htmlResponseError(status, text) {
        if (status === 403) {
            return new Error('You do not have permission for this request.');
        }
        if (status === 404) {
            return new Error('API endpoint not found.');
        }
        if (status >= 500) {
            return new Error('The server could not complete this request.');
        }
        if (_loginHtml(text)) {
            return _authExpiredError();
        }
        return new Error('The server returned a page instead of data.');
    }

    async function readJsonResponse(response) {
        if (!response) {
            throw new Error('Empty response');
        }
        const finalUrl = String(response.url || '');
        const followedLogin = response.redirected && /\/login(?:[/?#]|$)/.test(finalUrl);
        if (response.status === 401 || followedLogin) {
            throw _authExpiredError();
        }
        const text = await response.text();
        const trimmed = text.trim();
        if (!trimmed) {
            throw new Error('Empty response from server.');
        }
        if (trimmed.charAt(0) === '<') {
            throw _htmlResponseError(response.status, trimmed);
        }
        try {
            return JSON.parse(trimmed);
        } catch (_err) {
            throw new Error('The server returned data that is not JSON.');
        }
    }

    function isAbortError(err) {
        if (!err) return false;
        if (err.name === 'AbortError') return true;
        const msg = String(err.message || err || '');
        return /aborted|AbortError/i.test(msg);
    }

    /**
     * GET/POST helper with optional timeoutMs. Pass options.signal to compose with caller abort.
     * Does not invent retries. Callers must not use this to auto-cancel financial writes unless they intend to.
     */
    async function fetchJson(url, options) {
        const opts = Object.assign({}, options || {});
        const timeoutMs = Number(opts.timeoutMs);
        delete opts.timeoutMs;
        let timer = null;
        let timedOut = false;
        const controller = (Number.isFinite(timeoutMs) && timeoutMs > 0) ? new AbortController() : null;
        if (controller) {
            const parent = opts.signal;
            if (parent) {
                if (parent.aborted) {
                    controller.abort();
                } else {
                    parent.addEventListener('abort', () => controller.abort(), { once: true });
                }
            }
            opts.signal = controller.signal;
            timer = setTimeout(() => {
                timedOut = true;
                try { controller.abort(); } catch (_e) { /* ignore */ }
            }, timeoutMs);
        }
        try {
            const resp = await fetch(url, opts);
            const payload = await readJsonResponse(resp);
            if (!resp.ok) {
                const msg = (payload && (payload.error || payload.message || payload.detail)) || `HTTP ${resp.status}`;
                throw new Error(String(msg));
            }
            return payload;
        } catch (err) {
            if (timedOut) {
                const e = new Error(`Request timed out after ${timeoutMs}ms`);
                e.name = 'TimeoutError';
                e.timeout = true;
                throw e;
            }
            throw err;
        } finally {
            if (timer) clearTimeout(timer);
        }
    }

    const api = {
        escapeHtml,
        formatDate,
        formatMoney,
        fetchJson,
        readJsonResponse,
        isAbortError,
    };
    global.EQCore = api;
    // Back-compat: older admin pages used window.EQ
    global.EQ = Object.assign({}, global.EQ || {}, api);
})(typeof window !== 'undefined' ? window : globalThis);
