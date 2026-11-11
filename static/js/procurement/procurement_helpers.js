        function escapeHtml(value) {
            if (window.EQCore && typeof window.EQCore.escapeHtml === 'function') {
                return window.EQCore.escapeHtml(value);
            }
            return String(value)

                .replace(/&/g, '&amp;')

                .replace(/</g, '&lt;')

                .replace(/>/g, '&gt;')

                .replace(/\"/g, '&quot;')

                .replace(/'/g, '&#39;');

        }

        function escapeJs(value) {

            return String(value)

                .replace(/\\/g, '\\\\')

                .replace(/'/g, "\\'");

        }

        function formatMoney(value) {

            const num = Number(value || 0);

            if (!Number.isFinite(num)) {

                return '0.00';

            }

            return num.toFixed(2);

        }

        function formatPrDate(value) {

            const text = String(value || '').trim();

            if (!text) {

                return '-';

            }

            if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {

                return text;

            }

            const parsed = new Date(text);

            if (Number.isNaN(parsed.getTime())) {

                return text;

            }

            return parsed.toISOString().slice(0, 10);

        }

        function formatUdfStatusLabel(value) {
            const s = normalizeUdfStatus(value);
            if (!s) return '';
            if (s === 'AWAITING') return 'Awaiting Approval';
            if (s === 'PENDING') return 'Pending';
            return s;
        }

        function normalizeUdfStatus(value) {

            const text = String(value || '').trim().toUpperCase();

            if (!text) return '';

            if (text === 'ACTIVE') return 'APPROVED';

            if (text === 'INACTIVE') return 'CANCELLED';

            if (text === 'AWAITING' || text === 'AWAITING_APPROVAL' || text === 'AWAITING APPROVAL') return 'AWAITING';

            return text;

        }

