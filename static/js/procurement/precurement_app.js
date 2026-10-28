        function readProcurementJson(response) {
            const reader = window.EQCore && window.EQCore.readJsonResponse;
            const pending = typeof reader === 'function' ? reader(response) : response.json();
            return Promise.resolve(pending).catch((error) => {
                if (error && error.authExpired) {
                    window.location.assign('/login');
                }
                throw error;
            });
        }

        function isProcurementAuthExpired(error) {
            return !!(error && error.authExpired);
        }

        function isRequestAbortError(error) {
            if (!error) return false;
            const name = String(error.name || '');
            const message = String(error.message || '').toLowerCase();
            return name === 'AbortError' || message.includes('aborted');
        }

        const STOCK_CARD_VISIBLE_BODY_ROWS = 16;

        function afterStockCardTableRender() {

            setTimeout(() => {

                syncStockCardHeaderStickyOffset();

                syncStockCardTableWrapMaxHeight();

            }, 0);

        }

        /** Limit vertical viewport to ~16 data rows so the vertical scrollbar appears when there are more items. */

        function syncStockCardTableWrapMaxHeight() {

            const wrap = document.getElementById('stock-card-table-wrap');

            const tbody = document.getElementById('stock-card-table-body');

            const thead = document.getElementById('stock-card-table-head');

            if (!wrap || !tbody || !thead) return;

            const dataRow = Array.from(tbody.querySelectorAll('tr')).find((tr) => {

                const codeTd = tr.querySelector('td.code-col');

                if (!codeTd) return false;

                if (tr.querySelector('td.stock-card-status')) return false;

                if (codeTd.classList.contains('stock-card-no-cols-msg')) return false;

                return true;

            });

            if (!dataRow || dataRow.offsetHeight < 8) {

                wrap.style.removeProperty('max-height');

                return;

            }

            const rowH = dataRow.offsetHeight;

            const theadH = thead.offsetHeight || 0;

            const fudge = 6;

            wrap.style.maxHeight = `${theadH + STOCK_CARD_VISIBLE_BODY_ROWS * rowH + fudge}px`;

        }

        /** Multi-row thead: measure row heights so sticky location / UOM rows sit under the group row. */

        function syncStockCardHeaderStickyOffset() {

            const thead = document.getElementById('stock-card-table-head');

            if (!thead) return;

            const rows = thead.querySelectorAll('tr');

            if (rows.length < 2) {

                thead.style.removeProperty('--stock-card-hdr1-h');

                thead.style.removeProperty('--stock-card-hdr12-h');

                return;

            }

            const h1 = rows[0].offsetHeight || 0;

            if (h1 > 0) {

                thead.style.setProperty('--stock-card-hdr1-h', `${h1}px`);

            }

            if (rows.length >= 3) {

                const h2 = rows[1].offsetHeight || 0;

                thead.style.setProperty('--stock-card-hdr12-h', `${h1 + h2}px`);

            } else {

                thead.style.removeProperty('--stock-card-hdr12-h');

            }

        }

        let reportLoaded = false;
        let createPrLookupsStarted = false;

        function ensureCreatePrLookups() {
            if (createPrLookupsStarted) return;
            createPrLookupsStarted = true;
            loadPrWarehouseLocations();
            loadPurchaseRequestProducts();
            loadSuppliers();
            loadProjects();
        }

        let stockCardVisibilityRefreshTimer = null;

        let stockCardRows = [];

        let stockCardItemSearch = '';

        let stockCardStTrUdfSummary = null;

        let stockCardLocations = [];

        let selectedStockCardLocations = [];

        let stockCardBreakdownRequestId = 0;

        const STOCK_DASHBOARD_LAYOUT_LS = 'procurementStockDashboardLayout';

        function getStockDashboardLayoutEl() {

            return document.getElementById('stock-dashboard-layout');

        }

        function syncStockDashboardSplitBodyClass() {

            const layoutRoot = getStockDashboardLayoutEl();

            const bodyEl = document.querySelector('.stock-dashboard-body');

            const dock = document.getElementById('stock-card-breakdown-dock');

            if (!layoutRoot || !bodyEl || !dock) return;

            const isSplit = layoutRoot.getAttribute('data-layout') === 'split';

            const dockHidden = dock.style.display === 'none' || dock.getAttribute('aria-hidden') === 'true';

            bodyEl.classList.toggle('stock-dashboard-body--split-breakdown-closed', isSplit && dockHidden);

        }

        function applyStockDashboardLayout(mode) {

            const root = getStockDashboardLayoutEl();

            if (!root) return;

            const m = mode === 'split' ? 'split' : 'vertical';

            root.setAttribute('data-layout', m);

            try {

                localStorage.setItem(STOCK_DASHBOARD_LAYOUT_LS, m);

            } catch (e) { /* ignore */ }

            document.querySelectorAll('input[name="stock-dashboard-layout"]').forEach((inp) => {

                inp.checked = inp.value === m;

            });

            syncStockDashboardSplitBodyClass();

            setTimeout(() => { afterStockCardTableRender(); }, 0);

        }

        function onStockDashboardLayoutChange(radio) {

            if (!radio) return;

            applyStockDashboardLayout(radio.value);

        }

        function initStockDashboardLayout() {

            // Orientation UI is hidden; always use vertical layout (ignore saved split).

            applyStockDashboardLayout('vertical');

        }

        let stockCardBuySelections = {};

        let viewPurchaseRequestsLoaded = false;

        let viewPurchaseRequests = [];

        const VIEW_PR_LIST_PAGE_SIZE = 6;

        const VIEW_PR_LIST_CACHE_KEY = 'procurementViewPrFirstPageV3_page15';

        const VIEW_PR_LIST_CACHE_TTL_MS = 5 * 60 * 1000;

        let viewPrListTotal = null;

        let viewPrListHasMore = false;

        let viewPrListLoadingMore = false;

        let viewPrPrevListPerf = null;

        let viewSelectedHeaderId = null;

        let viewLoadingDetailIds = new Set();

        let viewDetailFetchControllers = new Map();

        let viewDetailFetchPromises = new Map();
        let viewDetailFetchStartedAtMs = new Map();

        let viewDetailCache = new Map();

        const VIEW_DETAIL_CACHE_TTL_MS = 2 * 60 * 1000;

        let viewTransferSavingHeaderIds = new Set();

        let viewApprovalPendingChanges = new Map();

        let viewHeaderStatusPendingChanges = new Map();

        let viewApprovalSaving = false;

        const VIEW_STATUS_FILTER_OPTIONS = ['DRAFT', 'AWAITING', 'PENDING', 'APPROVED', 'CANCELLED'];

        const VIEW_PR_TAB_LABELS = {

            DRAFT: 'Draft',

            APPROVED: 'Approved',

            PENDING: 'Pending',

            CANCELLED: 'Cancelled',
            AWAITING: 'Awaiting Approval',

        };

        let viewStatusFilters = new Set(['PENDING']);

        let viewBulkSelectedHeaderIds = new Set();

        /** Bulk PR→PO consolidation workspace state */
        let viewBulkTransferOpen = false;
        let bulkTransferLines = [];
        let bulkTransferFilterOptions = { suppliers: [], locations: [], items: [] };
        let bulkTransferSelectedLines = new Map(); // key `${requestId}:${detailId}` -> { requestId, detailId, quantity, remainingQty, ... }
        let bulkTransferLoading = false;
        let bulkTransferSubmitting = false;
        let bulkTransferScopeAll = false; // true = show every eligible line
        let bulkTransferAllLines = []; // unscoped cache from last fetch

        function bulkTransferLineKey(requestId, detailId) {
            return `${Number(requestId) || 0}:${Number(detailId) || 0}`;
        }

        function setBulkTransferMessage(text, isError) {
            const el = document.getElementById('bulk-transfer-message');
            if (!el) return;
            const msg = String(text || '').trim();
            el.textContent = msg;
            el.classList.toggle('is-error', !!isError && !!msg);
            el.hidden = !msg;
        }

        let _procurementConfirmResolver = null;

        function resolveProcurementConfirmModal(ok) {
            const modal = document.getElementById('pr-confirm-modal');
            if (modal) {
                modal.hidden = true;
                modal.setAttribute('aria-hidden', 'true');
            }
            const resolver = _procurementConfirmResolver;
            _procurementConfirmResolver = null;
            if (typeof resolver === 'function') resolver(Boolean(ok));
        }

        function showProcurementConfirmModal(options) {
            const opts = options || {};
            const modal = document.getElementById('pr-confirm-modal');
            const titleEl = document.getElementById('pr-confirm-modal-title');
            const bodyEl = document.getElementById('pr-confirm-modal-body');
            const listEl = document.getElementById('pr-confirm-modal-list');
            const noteEl = document.getElementById('pr-confirm-modal-note');
            const okBtn = document.getElementById('pr-confirm-modal-ok');
            const cancelBtn = document.getElementById('pr-confirm-modal-cancel');
            if (!modal || !listEl) {
                return Promise.resolve(window.confirm(String(opts.body || opts.title || 'Confirm?')));
            }
            if (titleEl) titleEl.textContent = String(opts.title || 'Confirm');
            if (bodyEl) bodyEl.textContent = String(opts.body || '');
            if (noteEl) noteEl.textContent = String(opts.note || '');
            if (okBtn) okBtn.textContent = String(opts.confirmLabel || 'Confirm');
            if (cancelBtn) cancelBtn.textContent = String(opts.cancelLabel || 'Cancel');
            const items = Array.isArray(opts.items) ? opts.items : [];
            listEl.className = 'pr-confirm-modal__list' + (items.some((it) => Array.isArray(it && it.children) && it.children.length) ? ' pr-confirm-modal__list--accordion' : '');
            listEl.innerHTML = items.map((item, idx) => {
                const label = escapeHtml(String((item && item.label) || ''));
                const meta = escapeHtml(String((item && item.meta) || ''));
                const children = Array.isArray(item && item.children) ? item.children : [];
                if (!children.length) {
                    return `<li class="pr-confirm-modal__row"><strong>${label}</strong><span>${meta}</span></li>`;
                }
                const hasTableCols = children.some((child) => child && (child.item || child.qty || child.description));
                let childHtml = '';
                if (hasTableCols) {
                    const rows = children.map((child) => {
                        const item = escapeHtml(String((child && (child.item || child.title || child.label)) || '-'));
                        const desc = escapeHtml(String((child && (child.description || child.detail || '')) || '-'));
                        const qty = escapeHtml(String((child && child.qty) || '-'));
                        const uom = escapeHtml(String((child && child.uom) || ''));
                        const price = escapeHtml(String((child && child.price) || '-'));
                        return `<tr>
                            <td class="col-item">${item}</td>
                            <td class="col-desc">${desc}</td>
                            <td class="col-qty">${qty}</td>
                            <td class="col-uom">${uom || '-'}</td>
                            <td class="col-price">${price}</td>
                        </tr>`;
                    }).join('');
                    childHtml = `<div class="pr-confirm-modal__table-wrap">
                        <table class="pr-confirm-modal__table">
                            <thead>
                                <tr>
                                    <th>Item</th>
                                    <th>Description</th>
                                    <th>Qty</th>
                                    <th>UOM</th>
                                    <th>Unit price</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>`;
                } else {
                    childHtml = children.map((child) => {
                        const title = escapeHtml(String((child && (child.title || child.label)) || '-'));
                        const detail = escapeHtml(String((child && (child.detail || child.meta)) || ''));
                        return `<div class="pr-confirm-modal__line">
                            <div class="pr-confirm-modal__line-title">${title}</div>
                            <div class="pr-confirm-modal__line-detail">${detail}</div>
                        </div>`;
                    }).join('');
                }
                const openAttr = idx === 0 ? ' open' : '';
                return `<li class="pr-confirm-modal__group${openAttr === ' open' ? ' is-open' : ''}">
                    <button type="button" class="pr-confirm-modal__group-toggle" aria-expanded="${idx === 0 ? 'true' : 'false'}" onclick="toggleProcurementConfirmGroup(this)">
                        <span class="pr-confirm-modal__group-main">
                            <span class="pr-confirm-modal__chevron" aria-hidden="true"></span>
                            <strong>${label}</strong>
                        </span>
                        <span class="pr-confirm-modal__group-meta">${meta}</span>
                    </button>
                    <div class="pr-confirm-modal__group-body"${idx === 0 ? '' : ' hidden'}>
                        ${childHtml}
                    </div>
                </li>`;
            }).join('');
            listEl.hidden = !items.length;
            modal.hidden = false;
            modal.setAttribute('aria-hidden', 'false');
            try { (okBtn || cancelBtn)?.focus(); } catch (e) {}
            return new Promise((resolve) => {
                _procurementConfirmResolver = resolve;
            });
        }

        function toggleProcurementConfirmGroup(btn) {
            if (!btn) return;
            const group = btn.closest('.pr-confirm-modal__group');
            if (!group) return;
            const body = group.querySelector('.pr-confirm-modal__group-body');
            const willOpen = !group.classList.contains('is-open');
            group.classList.toggle('is-open', willOpen);
            btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            if (body) body.hidden = !willOpen;
        }

        function isViewApprovedTabActive() {
            return (
                viewStatusFilters instanceof Set
                && viewStatusFilters.size === 1
                && viewStatusFilters.has('APPROVED')
            );
        }

        /** Bulk Transfer / Consolidate only belong on the Approved tab. */
        function syncViewPrApprovedOnlyToolbarActions() {
            const approved = isViewApprovedTabActive();
            const transferToggle = document.getElementById('view-bulk-transfer-toggle');
            const consolidateBtn = document.getElementById('view-bulk-consolidate-btn');
            if (transferToggle) {
                transferToggle.hidden = !approved;
                transferToggle.setAttribute('aria-hidden', approved ? 'false' : 'true');
            }
            if (consolidateBtn) {
                consolidateBtn.hidden = !approved;
                consolidateBtn.setAttribute('aria-hidden', approved ? 'false' : 'true');
            }
            if (!approved && viewBulkTransferOpen) {
                try { toggleViewBulkTransferPanel(false); } catch (e) { /* ignore */ }
            }
        }

        function onBulkTransferToolbarClick() {
            if (document.body.classList.contains('procurement-hide-transfer')) {
                alert('Transfer is disabled for this account.');
                return;
            }
            if (!isViewApprovedTabActive() && !viewBulkTransferOpen) {
                alert('Bulk Transfer is only available on the Approved tab.');
                return;
            }
            // If the advanced consolidate panel is open, Exit closes it.
            if (viewBulkTransferOpen) {
                toggleViewBulkTransferPanel(false);
                return;
            }
            runBulkTransferLikeDetailButton();
        }

        function getBulkTransferTargetHeaders() {
            const headers = [];
            const seen = new Set();
            const pushId = (rawId) => {
                const id = Number(rawId || 0);
                if (!id || seen.has(id)) return;
                const row = (viewPurchaseRequests || []).find((r) => Number(r.id || 0) === id);
                if (!row) return;
                seen.add(id);
                headers.push(row);
            };
            if (viewBulkSelectedHeaderIds && viewBulkSelectedHeaderIds.size) {
                for (const id of viewBulkSelectedHeaderIds) pushId(id);
            } else if (viewSelectedHeaderId != null) {
                pushId(viewSelectedHeaderId);
            }
            return headers;
        }

        async function runBulkTransferLikeDetailButton() {
            if (bulkTransferSubmitting) return;
            let headers = getBulkTransferTargetHeaders();
            if (!headers.length) {
                alert('Open a purchase request (or tick PR checkboxes on the left), then click Bulk Transfer to PO.');
                return;
            }

            bulkTransferSubmitting = true;
            try {
                for (const header of headers) {
                    if (!Array.isArray(header.details) || !header.details.length) {
                        try {
                            await fetchViewPurchaseRequestDetail(header, false);
                        } catch (e) {
                            console.warn('[BULK TRANSFER] detail load failed', header && header.id, e);
                        }
                    }
                }
                // Refresh references after detail hydrate.
                headers = getBulkTransferTargetHeaders();

                const jobs = [];
                for (const header of headers) {
                    const selectedRows = getSelectedTransferDetails(header)
                        .filter((detail) => Number(detail.id || 0) > 0 && isDetailChecked(detail) && getDetailTransferQuantity(detail) > 0);
                    if (!selectedRows.length) continue;
                    if (!isPurchaseRequestTransferReady(header)) continue;
                    const selectedDetails = selectedRows.map((detail) => ({
                        detailId: Number(detail.id || 0),
                        quantity: getDetailTransferQuantity(detail),
                        transferable: true,
                    }));
                    const displayLines = selectedRows.map((detail) => {
                        const qty = getDetailTransferQuantity(detail);
                        const code = String(detail.itemCode || detail.itemName || '-').trim() || '-';
                        const desc = String(detail.description || detail.itemName || '').trim() || '-';
                        const uom = String(detail.uom || '').trim();
                        const price = detail.unitPrice != null ? Number(detail.unitPrice) : null;
                        const priceText = Number.isFinite(price)
                            ? (typeof formatMoney === 'function' ? formatMoney(price) : String(price))
                            : '-';
                        return {
                            item: code,
                            description: desc,
                            qty: String(qty),
                            uom: uom || '-',
                            price: priceText,
                        };
                    });
                    jobs.push({
                        headerId: Number(header.id || 0),
                        requestNumber: String(header.requestNumber || ''),
                        selectedDetails,
                        displayLines,
                    });
                }

                if (!jobs.length) {
                    alert('No transferable selected lines on the chosen PR(s). Open the PR, keep approved lines selected with qty > 0, then try again.');
                    return;
                }

                const confirmItems = jobs.map((job) => ({
                    label: job.requestNumber || String(job.headerId),
                    meta: `${job.selectedDetails.length} line(s)`,
                    children: job.displayLines || [],
                }));
                const ok = await showProcurementConfirmModal({
                    title: 'Transfer to Purchase Order',
                    body: 'Transfer selected lines to Purchase Order?',
                    note: 'Same action as the detail Transfer to Purchase Order button.',
                    items: confirmItems,
                    confirmLabel: 'Transfer',
                    cancelLabel: 'Cancel',
                });
                if (!ok) return;

                const poNumbers = [];
                const errors = [];
                for (const job of jobs) {
                    viewTransferSavingHeaderIds.add(Number(job.headerId));
                    try {
                        const res = await fetch('/api/admin/procurement/purchase-requests/transfer-to-po', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                requestId: Number(job.headerId),
                                requestNumber: String(job.requestNumber || ''),
                                transferLines: job.selectedDetails,
                            }),
                        });
                        const data = await readProcurementJson(res);
                        if (!res.ok || !data.success) {
                            throw new Error(data.error || `Transfer failed (HTTP ${res.status})`);
                        }
                        const nums = Array.isArray(data?.data?.poNumbers)
                            ? data.data.poNumbers.filter(Boolean)
                            : [];
                        if (nums.length) {
                            poNumbers.push(...nums);
                        } else if (data?.data?.poNumber) {
                            poNumbers.push(data.data.poNumber);
                        }
                        invalidateViewDetailCache(job.headerId);
                    } catch (err) {
                        errors.push(`${job.requestNumber || job.headerId}: ${err.message || 'failed'}`);
                    } finally {
                        viewTransferSavingHeaderIds.delete(Number(job.headerId));
                    }
                }

                try {
                    await loadViewPurchaseRequests(true, { bustCache: true });
                } catch (e) {}

                if (poNumbers.length) {
                    const uniquePos = Array.from(new Set(poNumbers.map((v) => String(v))));
                    let msg = `Transfer completed. Purchase Order(s): ${uniquePos.join(', ')}`;
                    if (errors.length) msg += `\n\nSome failed:\n${errors.join('\n')}`;
                    alert(msg);
                } else {
                    alert(errors.length ? `Transfer failed.\n${errors.join('\n')}` : 'Transfer failed.');
                }
            } finally {
                bulkTransferSubmitting = false;
                try { renderFilteredViewPurchaseRequests(); } catch (e) {}
            }
        }

        function toggleViewBulkTransferPanel(forceOpen) {
            if (document.body.classList.contains('procurement-hide-transfer')) {
                setBulkTransferMessage('Transfer is disabled for this account.', true);
                return;
            }
            const wasOpen = !!viewBulkTransferOpen;
            const open = typeof forceOpen === 'boolean' ? forceOpen : !wasOpen;
            if (open && !isViewApprovedTabActive()) {
                setBulkTransferMessage('Consolidate / Bulk Transfer is only available on the Approved tab.', true);
                alert('Consolidate / Bulk Transfer is only available on the Approved tab.');
                return;
            }
            viewBulkTransferOpen = open;
            const split = document.getElementById('view-pr-split-workspace');
            const panel = document.getElementById('view-bulk-transfer-panel');
            const toggle = document.getElementById('view-bulk-transfer-toggle');
            const bulkBar = document.getElementById('view-pr-bulk-pending-bar');
            if (split) split.hidden = open;
            if (panel) panel.hidden = !open;
            if (toggle) {
                toggle.textContent = open ? 'Exit bulk transfer' : 'Bulk Transfer to PO';
                toggle.classList.toggle('is-active', open);
                toggle.setAttribute('aria-pressed', open ? 'true' : 'false');
            }
            if (bulkBar && open) bulkBar.hidden = true;
            // Clear prior transfer summary only when opening from closed.
            if (open && !wasOpen) {
                clearBulkTransferResultSummary();
                // Default: scope to checked/open PR so one-PR transfer does not dump every eligible line.
                bulkTransferScopeAll = false;
            }
            if (open) {
                loadBulkTransferCandidates(false);
            } else {
                setBulkTransferMessage('');
                closeBulkTransferFilterPopup();
            }
        }

        function getBulkTransferScopeTargets() {
            const ids = new Set();
            const numbers = new Set();
            if (viewBulkSelectedHeaderIds && viewBulkSelectedHeaderIds.size) {
                for (const rawId of viewBulkSelectedHeaderIds) {
                    const id = Number(rawId || 0);
                    if (!id) continue;
                    ids.add(id);
                    const row = (viewPurchaseRequests || []).find((r) => Number(r.id || 0) === id);
                    const num = String((row && row.requestNumber) || '').trim().toUpperCase();
                    if (num) numbers.add(num);
                }
            } else if (viewSelectedHeaderId != null) {
                const id = Number(viewSelectedHeaderId || 0);
                if (id) {
                    ids.add(id);
                    const row = (viewPurchaseRequests || []).find((r) => Number(r.id || 0) === id);
                    const num = String((row && row.requestNumber) || '').trim().toUpperCase();
                    if (num) numbers.add(num);
                }
            }
            return { ids, numbers };
        }

        function applyBulkTransferScope(lines) {
            const all = Array.isArray(lines) ? lines : [];
            bulkTransferAllLines = all.slice();
            if (bulkTransferScopeAll) {
                bulkTransferLines = all.slice();
                return { scoped: false, label: 'all eligible' };
            }
            const scope = getBulkTransferScopeTargets();
            if (!scope.ids.size && !scope.numbers.size) {
                bulkTransferLines = all.slice();
                return { scoped: false, label: 'all eligible' };
            }
            bulkTransferLines = all.filter((line) => {
                const id = Number(line && line.requestId ? line.requestId : 0);
                const num = String((line && line.requestNumber) || '').trim().toUpperCase();
                return (id && scope.ids.has(id)) || (num && scope.numbers.has(num));
            });
            const labels = Array.from(scope.numbers);
            return {
                scoped: true,
                label: labels.length ? labels.join(', ') : `${scope.ids.size} selected PR(s)`,
            };
        }

        function setBulkTransferScopeAll(showAll) {
            bulkTransferScopeAll = !!showAll;
            const scopeInfo = applyBulkTransferScope(bulkTransferAllLines.length ? bulkTransferAllLines : bulkTransferLines);
            // Pre-select only currently visible scoped lines.
            bulkTransferSelectedLines.clear();
            bulkTransferSelectAllVisible();
            renderBulkTransferTable();
            updateBulkTransferSummary();
            updateBulkTransferScopeChip(scopeInfo);
            setBulkTransferMessage(
                scopeInfo.scoped
                    ? `${bulkTransferLines.length} line(s) for ${scopeInfo.label}.`
                    : `${bulkTransferLines.length} eligible line(s) loaded.`
            );
        }

        function updateBulkTransferScopeChip(scopeInfo) {
            const chip = document.getElementById('bulk-transfer-scope-chip');
            const btn = document.getElementById('bulk-transfer-scope-toggle');
            if (!chip && !btn) return;
            const info = scopeInfo || { scoped: !bulkTransferScopeAll && (getBulkTransferScopeTargets().ids.size > 0), label: '' };
            if (chip) {
                chip.textContent = info.scoped
                    ? `Scoped to ${info.label || 'selected PR(s)'}`
                    : 'Showing all eligible lines';
                chip.classList.toggle('is-scoped', !!info.scoped);
            }
            if (btn) {
                btn.hidden = false;
                btn.textContent = info.scoped ? 'Show all eligible' : 'Use selected PR only';
                btn.disabled = !info.scoped && !(getBulkTransferScopeTargets().ids.size || getBulkTransferScopeTargets().numbers.size);
            }
        }

        function updateBulkTransferFilterChip() {
            const chip = document.getElementById('bulk-transfer-filter-chip');
            const openBtn = document.getElementById('bulk-transfer-filter-open-btn');
            if (!chip) return;
            const filters = getBulkTransferFilterValues();
            const parts = [
                filters.supplier || 'All suppliers',
                filters.location || 'All locations',
                filters.item || 'All items',
            ];
            chip.textContent = parts.join(' · ');
            const activeCount = [filters.supplier, filters.location, filters.item].filter(Boolean).length;
            chip.classList.toggle('is-active', activeCount > 0);
            if (openBtn) {
                openBtn.textContent = activeCount > 0 ? `Filters (${activeCount})` : 'Filters';
                openBtn.classList.toggle('is-active', activeCount > 0);
            }
        }

        function openBulkTransferFilterPopup() {
            const popup = document.getElementById('bulk-transfer-filter-popup');
            if (!popup) return;
            popup.hidden = false;
            try {
                document.getElementById('bulk-transfer-filter-supplier')?.focus();
            } catch (e) {}
        }

        function closeBulkTransferFilterPopup() {
            const popup = document.getElementById('bulk-transfer-filter-popup');
            if (popup) popup.hidden = true;
        }

        function clearBulkTransferFilterPopup() {
            const supplier = document.getElementById('bulk-transfer-filter-supplier');
            const location = document.getElementById('bulk-transfer-filter-location');
            const item = document.getElementById('bulk-transfer-filter-item');
            if (supplier) supplier.value = '';
            if (location) location.value = '';
            if (item) item.value = '';
            updateBulkTransferFilterChip();
            loadBulkTransferCandidates(true);
            closeBulkTransferFilterPopup();
        }

        function applyBulkTransferFilterPopup() {
            updateBulkTransferFilterChip();
            loadBulkTransferCandidates(true);
            closeBulkTransferFilterPopup();
        }

        function getBulkTransferFilterValues() {
            return {
                supplier: String(document.getElementById('bulk-transfer-filter-supplier')?.value || '').trim(),
                location: String(document.getElementById('bulk-transfer-filter-location')?.value || '').trim(),
                item: String(document.getElementById('bulk-transfer-filter-item')?.value || '').trim(),
                search: String(document.getElementById('bulk-transfer-filter-search')?.value || '').trim(),
            };
        }

        function fillBulkTransferFilterSelect(selectId, values, selectedValue, allLabel) {
            const el = document.getElementById(selectId);
            if (!el) return;
            const selected = String(selectedValue || '');
            const opts = [`<option value="">${escapeHtml(allLabel)}</option>`];
            for (const value of values || []) {
                const v = String(value || '').trim();
                if (!v) continue;
                opts.push(`<option value="${escapeHtml(v)}"${v === selected ? ' selected' : ''}>${escapeHtml(v)}</option>`);
            }
            el.innerHTML = opts.join('');
        }

        async function loadBulkTransferCandidates(force) {
            if (bulkTransferLoading) return;
            if (!viewBulkTransferOpen && !force) return;
            bulkTransferLoading = true;
            const host = document.getElementById('bulk-transfer-table-host');
            if (host) host.innerHTML = '<div class="view-bulk-transfer-empty">Loading eligible lines...</div>';
            setBulkTransferMessage('');
            try {
                const filters = getBulkTransferFilterValues();
                const params = new URLSearchParams();
                params.set('limit', '1000');
                if (filters.supplier) params.set('supplier', filters.supplier);
                if (filters.location) params.set('location', filters.location);
                if (filters.item) params.set('item', filters.item);
                if (filters.search) params.set('search', filters.search);
                const res = await fetch(`/api/admin/procurement/purchase-requests/transfer-candidates?${params.toString()}`, {
                    headers: { 'Accept': 'application/json' },
                });
                const body = await readProcurementJson(res);
                if (!res.ok || !body.success) {
                    throw new Error(body.error || `Failed to load candidates (${res.status})`);
                }
                const data = body.data || {};
                const fetchedLines = Array.isArray(data.lines) ? data.lines : [];
                bulkTransferFilterOptions = data.filters || { suppliers: [], locations: [], items: [] };
                fillBulkTransferFilterSelect('bulk-transfer-filter-supplier', bulkTransferFilterOptions.suppliers, filters.supplier, 'All suppliers');
                fillBulkTransferFilterSelect('bulk-transfer-filter-location', bulkTransferFilterOptions.locations, filters.location, 'All locations');
                fillBulkTransferFilterSelect('bulk-transfer-filter-item', bulkTransferFilterOptions.items, filters.item, 'All items');
                updateBulkTransferFilterChip();
                const scopeInfo = applyBulkTransferScope(fetchedLines);
                // Prefer scoped lines as the working selection.
                bulkTransferSelectedLines.clear();
                const validKeys = new Set(
                    bulkTransferLines.map((line) => bulkTransferLineKey(line.requestId, line.detailId))
                );
                for (const line of bulkTransferLines) {
                    const key = bulkTransferLineKey(line.requestId, line.detailId);
                    if (!validKeys.has(key)) continue;
                    bulkTransferSelectedLines.set(key, {
                        requestId: Number(line.requestId),
                        detailId: Number(line.detailId),
                        quantity: Number(line.remainingQty || line.quantity || 0),
                        remainingQty: Number(line.remainingQty || line.quantity || 0),
                        requestNumber: line.requestNumber,
                        supplierCode: line.supplierCode,
                        supplierName: line.supplierName,
                        currencyCode: normalizeBulkTransferCurrency(line.currencyCode),
                        itemCode: line.itemCode,
                    });
                }
                renderBulkTransferTable();
                updateBulkTransferSummary();
                updateBulkTransferScopeChip(scopeInfo);
                setBulkTransferMessage(
                    scopeInfo.scoped
                        ? `${bulkTransferLines.length} line(s) for ${scopeInfo.label}. Use Show all eligible to include every PR.`
                        : `${bulkTransferLines.length} eligible line(s) loaded.`
                );
            } catch (err) {
                bulkTransferLines = [];
                if (host) host.innerHTML = `<div class="view-bulk-transfer-empty">${escapeHtml(err.message || 'Failed to load lines')}</div>`;
                setBulkTransferMessage(err.message || 'Failed to load lines', true);
                updateBulkTransferSummary();
            } finally {
                bulkTransferLoading = false;
            }
        }

        function onBulkTransferFilterChange() {
            loadBulkTransferCandidates(true);
        }

        function getVisibleBulkTransferLines() {
            return Array.isArray(bulkTransferLines) ? bulkTransferLines : [];
        }

        function normalizeBulkTransferCurrency(value) {
            const text = String(value == null ? '' : value).trim().toUpperCase();
            if (!text || text === '----' || text === '-' || text === 'N/A' || text === 'NA' || text === 'NONE' || text === 'NULL') {
                return 'MYR';
            }
            return text;
        }

        function cleanBulkTransferDisplayText(value) {
            if (value == null) return '';
            let text = String(value).trim();
            if ((text.startsWith("b'") && text.endsWith("'")) || (text.startsWith('b"') && text.endsWith('"'))) {
                text = text.slice(2, -1);
            }
            return text;
        }

        function groupBulkTransferLines(lines) {
            const groups = new Map();
            for (const line of lines) {
                const supplierCode = String(line.supplierCode || '').trim() || 'UNKNOWN';
                const currencyCode = normalizeBulkTransferCurrency(line.currencyCode);
                const key = `${supplierCode}||${currencyCode}`;
                if (!groups.has(key)) {
                    groups.set(key, {
                        supplierCode,
                        supplierName: String(line.supplierName || supplierCode).trim() || supplierCode,
                        currencyCode,
                        lines: [],
                    });
                }
                groups.get(key).lines.push(line);
            }
            return Array.from(groups.values()).sort((a, b) => {
                const left = `${a.supplierCode} ${a.currencyCode}`.toUpperCase();
                const right = `${b.supplierCode} ${b.currencyCode}`.toUpperCase();
                return left.localeCompare(right);
            });
        }

        function renderBulkTransferTable() {
            const host = document.getElementById('bulk-transfer-table-host');
            if (!host) return;
            const lines = getVisibleBulkTransferLines();
            if (!lines.length) {
                host.innerHTML = '<div class="view-bulk-transfer-empty">No eligible approved lines match the current filters.</div>';
                updateBulkTransferSummary();
                return;
            }
            const groups = groupBulkTransferLines(lines);
            const parts = ['<div class="view-bulk-transfer-groups">'];
            for (const group of groups) {
                const groupKey = `${group.supplierCode}||${group.currencyCode}`;
                const selectedInGroup = group.lines.filter((line) => (
                    bulkTransferSelectedLines.has(bulkTransferLineKey(line.requestId, line.detailId))
                )).length;
                const allSelected = selectedInGroup === group.lines.length && group.lines.length > 0;
                parts.push(`
                    <section class="view-bulk-transfer-group" data-group-key="${escapeHtml(groupKey)}">
                        <header class="view-bulk-transfer-group__head">
                            <label class="view-bulk-transfer-group__select">
                                <input type="checkbox" ${allSelected ? 'checked' : ''} onchange="onBulkTransferGroupSelectAll(this.checked, '${escapeHtml(group.supplierCode)}', '${escapeHtml(group.currencyCode)}')" />
                                <span>${escapeHtml(group.supplierName)} <span class="muted">(${escapeHtml(group.supplierCode)} · ${escapeHtml(group.currencyCode)})</span></span>
                            </label>
                            <span class="view-bulk-transfer-group__meta">${selectedInGroup}/${group.lines.length} selected · ${group.lines.length} line(s)</span>
                        </header>
                        <div class="view-bulk-transfer-table-scroll">
                            <table class="view-bulk-transfer-table">
                                <thead>
                                    <tr>
                                        <th class="col-check"></th>
                                        <th>PR</th>
                                        <th>Item</th>
                                        <th>Description</th>
                                        <th>Location</th>
                                        <th>UOM</th>
                                        <th>Remaining</th>
                                        <th>Transfer qty</th>
                                        <th>Unit price</th>
                                    </tr>
                                </thead>
                                <tbody>
                `);
                for (const line of group.lines) {
                    const key = bulkTransferLineKey(line.requestId, line.detailId);
                    const selected = bulkTransferSelectedLines.get(key);
                    const checked = !!selected;
                    const remaining = Number(line.remainingQty || 0);
                    const qty = checked ? Number(selected.quantity || remaining) : remaining;
                    parts.push(`
                        <tr class="view-bulk-transfer-row${checked ? ' is-selected' : ''}" data-key="${escapeHtml(key)}">
                            <td class="col-check">
                                <input type="checkbox" ${checked ? 'checked' : ''} onchange="onBulkTransferLineCheck(${Number(line.requestId)}, ${Number(line.detailId)}, this.checked)" />
                            </td>
                            <td>${escapeHtml(line.requestNumber || '-')}</td>
                            <td>${escapeHtml(line.itemCode || '-')}</td>
                            <td class="col-desc">${escapeHtml(cleanBulkTransferDisplayText(line.description) || '-')}</td>
                            <td>${escapeHtml(line.locationCode || '-')}</td>
                            <td>${escapeHtml(line.uom || 'UNIT')}</td>
                            <td>${escapeHtml(String(remaining))}</td>
                            <td>
                                <input type="number" class="view-bulk-transfer-qty" min="0" step="any" max="${escapeHtml(String(remaining))}"
                                    value="${escapeHtml(String(qty))}"
                                    ${checked ? '' : 'disabled'}
                                    onchange="onBulkTransferQtyChange(${Number(line.requestId)}, ${Number(line.detailId)}, this.value)"
                                    oninput="onBulkTransferQtyChange(${Number(line.requestId)}, ${Number(line.detailId)}, this.value)" />
                            </td>
                            <td>${escapeHtml(String(line.unitPrice ?? 0))}</td>
                        </tr>
                    `);
                }
                parts.push('</tbody></table></div></section>');
            }
            parts.push('</div>');
            host.innerHTML = parts.join('');
            updateBulkTransferSummary();
        }

        function onBulkTransferLineCheck(requestId, detailId, checked) {
            const key = bulkTransferLineKey(requestId, detailId);
            const line = (bulkTransferLines || []).find((row) => (
                Number(row.requestId) === Number(requestId) && Number(row.detailId) === Number(detailId)
            ));
            if (!line) return;
            if (checked) {
                const remaining = Number(line.remainingQty || 0);
                const existing = bulkTransferSelectedLines.get(key);
                bulkTransferSelectedLines.set(key, {
                    requestId: Number(requestId),
                    detailId: Number(detailId),
                    quantity: existing ? Number(existing.quantity || remaining) : remaining,
                    remainingQty: remaining,
                    supplierCode: line.supplierCode,
                    currencyCode: line.currencyCode,
                    requestNumber: line.requestNumber,
                });
            } else {
                bulkTransferSelectedLines.delete(key);
            }
            renderBulkTransferTable();
        }

        function onBulkTransferQtyChange(requestId, detailId, rawValue) {
            const key = bulkTransferLineKey(requestId, detailId);
            const selected = bulkTransferSelectedLines.get(key);
            if (!selected) return;
            const remaining = Number(selected.remainingQty || 0);
            let qty = Number(rawValue);
            if (!Number.isFinite(qty) || qty < 0) qty = 0;
            if (qty > remaining) qty = remaining;
            selected.quantity = qty;
            bulkTransferSelectedLines.set(key, selected);
            updateBulkTransferSummary();
        }

        function onBulkTransferGroupSelectAll(checked, supplierCode, currencyCode) {
            const lines = getVisibleBulkTransferLines().filter((line) => (
                String(line.supplierCode || '').trim() === String(supplierCode || '').trim()
                && String(line.currencyCode || 'MYR').trim() === String(currencyCode || 'MYR').trim()
            ));
            for (const line of lines) {
                const key = bulkTransferLineKey(line.requestId, line.detailId);
                if (checked) {
                    const remaining = Number(line.remainingQty || 0);
                    const existing = bulkTransferSelectedLines.get(key);
                    bulkTransferSelectedLines.set(key, {
                        requestId: Number(line.requestId),
                        detailId: Number(line.detailId),
                        quantity: existing ? Number(existing.quantity || remaining) : remaining,
                        remainingQty: remaining,
                        supplierCode: line.supplierCode,
                        currencyCode: line.currencyCode,
                        requestNumber: line.requestNumber,
                    });
                } else {
                    bulkTransferSelectedLines.delete(key);
                }
            }
            renderBulkTransferTable();
        }

        function bulkTransferSelectAllVisible() {
            for (const line of getVisibleBulkTransferLines()) {
                const key = bulkTransferLineKey(line.requestId, line.detailId);
                const remaining = Number(line.remainingQty || 0);
                const existing = bulkTransferSelectedLines.get(key);
                bulkTransferSelectedLines.set(key, {
                    requestId: Number(line.requestId),
                    detailId: Number(line.detailId),
                    quantity: existing ? Number(existing.quantity || remaining) : remaining,
                    remainingQty: remaining,
                    supplierCode: line.supplierCode,
                    currencyCode: line.currencyCode,
                    requestNumber: line.requestNumber,
                });
            }
            renderBulkTransferTable();
        }

        function bulkTransferClearSelection() {
            bulkTransferSelectedLines.clear();
            renderBulkTransferTable();
        }

        function summarizeBulkTransferSelection() {
            const selected = Array.from(bulkTransferSelectedLines.values()).filter((row) => Number(row.quantity) > 0);
            const prIds = new Set(selected.map((row) => Number(row.requestId)));
            const poKeys = new Set(selected.map((row) => `${String(row.supplierCode || '').toUpperCase()}||${String(row.currencyCode || 'MYR').toUpperCase()}`));
            return {
                selected,
                lineCount: selected.length,
                prCount: prIds.size,
                poCount: poKeys.size,
            };
        }

        function updateBulkTransferSummary() {
            const summary = document.getElementById('bulk-transfer-summary');
            const btn = document.getElementById('bulk-transfer-submit-btn');
            const info = summarizeBulkTransferSelection();
            const eligibleCount = (getVisibleBulkTransferLines() || []).length;
            const transferCount = info.lineCount || eligibleCount;
            if (summary) {
                if (info.lineCount) {
                    summary.textContent = `${info.lineCount} line(s) selected from ${info.prCount} PR(s) → ${info.poCount} PO(s). Confirm before transfer.`;
                } else if (eligibleCount) {
                    summary.textContent = `No lines ticked — Transfer to PO will use all ${eligibleCount} eligible line(s). Confirmation required.`;
                } else {
                    summary.textContent = 'No eligible lines loaded.';
                }
            }
            if (btn) {
                btn.disabled = !transferCount || bulkTransferSubmitting || document.body.classList.contains('procurement-hide-transfer');
                btn.textContent = info.lineCount
                    ? `Transfer selected to PO (${info.lineCount})`
                    : (eligibleCount ? `Transfer all eligible to PO (${eligibleCount})` : 'Transfer to PO');
            }
        }

        function clearBulkTransferResultSummary() {
            const box = document.getElementById('bulk-transfer-result');
            const body = document.getElementById('bulk-transfer-result-body');
            const lede = document.getElementById('bulk-transfer-result-lede');
            if (body) body.innerHTML = '';
            if (lede) lede.textContent = '';
            if (box) box.hidden = true;
        }

        function formatBulkTransferQty(value) {
            const n = Number(value);
            if (!Number.isFinite(n)) return '-';
            if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
            return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
        }

        function renderBulkTransferResultSummary(data) {
            const box = document.getElementById('bulk-transfer-result');
            const body = document.getElementById('bulk-transfer-result-body');
            const lede = document.getElementById('bulk-transfer-result-lede');
            if (!box || !body) return;
            const groups = Array.isArray(data && data.groups) ? data.groups : [];
            const poNumbers = Array.isArray(data && data.poNumbers)
                ? data.poNumbers.map((v) => String(v || '').trim()).filter(Boolean)
                : [];
            const totalLines = Number(data && data.lineCount);
            const totalQty = Number(data && data.transferredQty);
            const poCount = groups.length || poNumbers.length || 1;
            if (lede) {
                const lineBit = Number.isFinite(totalLines) && totalLines > 0 ? ` · ${totalLines} line(s)` : '';
                const qtyBit = Number.isFinite(totalQty) && totalQty > 0 ? ` · qty ${formatBulkTransferQty(totalQty)}` : '';
                lede.textContent = `Created ${poCount} purchase order(s)${lineBit}${qtyBit}.`;
            }

            const rows = [];
            if (groups.length) {
                groups.forEach((g, idx) => {
                    const po = String((g && g.poNumber) || poNumbers[idx] || '-').trim() || '-';
                    const supplierName = String((g && (g.supplierName || g.supplierCode)) || '').trim() || '-';
                    const supplierCode = String((g && g.supplierCode) || '').trim();
                    const currency = String((g && g.currencyCode) || 'MYR').trim() || 'MYR';
                    const prs = Array.isArray(g && g.requestNumbers)
                        ? g.requestNumbers.map((v) => String(v || '').trim()).filter(Boolean)
                        : [];
                    const lines = Number(g && g.lineCount);
                    const qty = Number(g && g.transferredQty);
                    const supplierLabel = supplierCode && supplierName && supplierName !== supplierCode
                        ? `${supplierName} (${supplierCode})`
                        : supplierName;
                    rows.push({
                        po,
                        supplierLabel,
                        currency,
                        lines: Number.isFinite(lines) ? String(lines) : '-',
                        qty: formatBulkTransferQty(qty),
                        prs: prs.length ? prs.join(', ') : '-',
                    });
                });
            } else {
                poNumbers.forEach((po) => {
                    rows.push({
                        po,
                        supplierLabel: '-',
                        currency: '-',
                        lines: '-',
                        qty: '-',
                        prs: '-',
                    });
                });
            }

            body.innerHTML = rows.map((row) => (
                `<tr>
                    <td class="view-bulk-transfer-result__po-cell">${escapeHtml(row.po)}</td>
                    <td>${escapeHtml(row.supplierLabel)}</td>
                    <td>${escapeHtml(row.currency)}</td>
                    <td>${escapeHtml(row.lines)}</td>
                    <td>${escapeHtml(row.qty)}</td>
                    <td>${escapeHtml(row.prs)}</td>
                </tr>`
            )).join('');

            box.hidden = false;
            try { box.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) {}
        }

        async function confirmBulkTransferToPo() {
            if (document.body.classList.contains('procurement-hide-transfer')) {
                alert('Transfer is disabled for this account.');
                return;
            }
            if (bulkTransferSubmitting) return;
            let info = summarizeBulkTransferSelection();
            if (!info.lineCount) {
                const eligible = getVisibleBulkTransferLines() || [];
                if (!eligible.length) {
                    alert('No eligible lines to transfer.');
                    return;
                }
                bulkTransferSelectAllVisible();
                info = summarizeBulkTransferSelection();
                if (!info.lineCount) {
                    alert('No eligible lines to transfer.');
                    return;
                }
            }
            const previewGroups = new Map();
            for (const row of info.selected) {
                const key = `${row.supplierCode || ''}||${normalizeBulkTransferCurrency(row.currencyCode)}`;
                if (!previewGroups.has(key)) {
                    previewGroups.set(key, {
                        supplierCode: row.supplierCode || '',
                        currencyCode: normalizeBulkTransferCurrency(row.currencyCode),
                        prs: new Set(),
                        lines: 0,
                    });
                }
                const g = previewGroups.get(key);
                g.prs.add(row.requestNumber || String(row.requestId));
                g.lines += 1;
            }
                        const confirmItems = Array.from(previewGroups.values()).map((g) => ({
                label: `${g.supplierCode} (${g.currencyCode})`,
                meta: `${g.lines} line(s)`,
                children: Array.from(g.prs).map((pr) => ({
                    title: pr,
                    detail: 'Included in this purchase order',
                })),
            }));
            const ok = await showProcurementConfirmModal({
                title: 'Create purchase orders',
                body: `Create ${info.poCount} purchase order(s) from ${info.lineCount} line(s) across ${info.prCount} PR(s)?`,
                note: 'One purchase order is created per supplier and currency.',
                items: confirmItems,
                confirmLabel: 'Create POs',
                cancelLabel: 'Cancel',
            });
            if (!ok) return;

            bulkTransferSubmitting = true;
            updateBulkTransferSummary();
            setBulkTransferMessage('Transferring selected lines...');
            try {
                const res = await fetch('/api/admin/procurement/purchase-requests/bulk-transfer-to-po', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    body: JSON.stringify({
                        lines: info.selected.map((row) => ({
                            requestId: Number(row.requestId),
                            detailId: Number(row.detailId),
                            quantity: Number(row.quantity),
                        })),
                    }),
                });
                const body = await readProcurementJson(res);
                if (!res.ok || !body.success) {
                    throw new Error(body.error || `Bulk transfer failed (${res.status})`);
                }
                const data = body.data || {};
                const poNumbers = Array.isArray(data.poNumbers) ? data.poNumbers.filter(Boolean) : [];
                bulkTransferSelectedLines.clear();
                renderBulkTransferResultSummary(data);
                await loadBulkTransferCandidates(true);
                try {
                    await loadViewPurchaseRequests(true, { bustCache: true });
                } catch (e) {}
                const poCount = poNumbers.length || (Array.isArray(data.groups) ? data.groups.length : 0) || 1;
                setBulkTransferMessage(`Transfer complete — created ${poCount} purchase order(s). See summary below.`);
            } catch (err) {
                setBulkTransferMessage(err.message || 'Bulk transfer failed', true);
                if (!isProcurementAuthExpired(err)) alert(err.message || 'Bulk transfer failed');
            } finally {
                bulkTransferSubmitting = false;
                updateBulkTransferSummary();
            }
        }

        let viewPrSearchText = '';

        let prEditState = null;

        let prFormEditState = null;

        const PROCUREMENT_PAGE_TITLES = {

            report: 'Purchase > Dashboard',

            view: 'Purchase > View e-PR',

            create: 'Purchase > Create e-PR'

        };

        function updateProcurementPageTitle(tabName) {

            const titleEl = document.querySelector('.app-page-header__title');

            if (titleEl) {

                titleEl.textContent = PROCUREMENT_PAGE_TITLES[tabName] || PROCUREMENT_PAGE_TITLES.report;

            }

        }

        function readViewStatusFromUrl() {
            try {
                const raw = new URLSearchParams(window.location.search || '').get('status');
                const s = String(raw || '').trim().toUpperCase();
                return VIEW_STATUS_FILTER_OPTIONS.includes(s) ? s : null;
            } catch (e) {
                return null;
            }
        }

        function readViewPrUrlParams() {
            try {
                const params = new URLSearchParams(window.location.search || '');
                const idRaw = params.get('id') || params.get('prId') || params.get('request_id') || '';
                const id = Number(idRaw) || 0;
                const docno = String(
                    params.get('docno') || params.get('pr') || params.get('requestNumber') || ''
                ).trim();
                const status = String(params.get('status') || '').trim().toUpperCase();
                return {
                    id: id > 0 ? id : 0,
                    docno,
                    status: VIEW_STATUS_FILTER_OPTIONS.includes(status) ? status : null,
                };
            } catch (e) {
                return { id: 0, docno: '', status: null };
            }
        }

        function syncViewStatusToUrl() {
            syncViewPrToUrl();
        }

        function syncViewPrToUrl() {
            try {
                const url = new URL(window.location.href);
                const tab = String(url.searchParams.get('tab') || '').toLowerCase();
                if (tab !== 'view') {
                    return;
                }
                const active = viewStatusFilters instanceof Set ? [...viewStatusFilters][0] : null;
                if (active && VIEW_STATUS_FILTER_OPTIONS.includes(active)) {
                    url.searchParams.set('status', active.toLowerCase());
                } else {
                    url.searchParams.delete('status');
                }
                const selectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;
                const record = selectedId > 0
                    ? (viewPurchaseRequests || []).find((row) => Number(row.id || 0) === selectedId)
                    : null;
                if (record && selectedId > 0) {
                    url.searchParams.set('id', String(selectedId));
                    const docno = String(record.requestNumber || '').trim();
                    if (docno) {
                        url.searchParams.set('docno', docno);
                    } else {
                        url.searchParams.delete('docno');
                    }
                } else {
                    url.searchParams.delete('id');
                    url.searchParams.delete('docno');
                }
                history.replaceState({ viewPrId: selectedId > 0 ? selectedId : null }, '', url);
            } catch (e) { /* ignore */ }
        }

        function findViewPrRowFromUrlParams() {
            const { id, docno } = readViewPrUrlParams();
            if (!(id > 0) && !docno) return null;
            const rows = viewPurchaseRequests || [];
            if (id > 0) {
                const byId = rows.find((row) => Number(row.id || 0) === id);
                if (byId) return byId;
            }
            if (docno) {
                const key = docno.toUpperCase();
                return rows.find(
                    (row) => String(row.requestNumber || '').trim().toUpperCase() === key
                ) || null;
            }
            return null;
        }

        function selectViewPrFromUrlIfPresent(options) {
            const opts = options || {};
            const row = findViewPrRowFromUrlParams();
            if (!row) return false;
            const rowId = Number(row.id || 0);
            if (!rowId) return false;
            if (viewSelectedHeaderId != null && Number(viewSelectedHeaderId) === rowId && !opts.force) {
                syncViewPrToUrl();
                return true;
            }
            selectViewPurchaseRequest(rowId, { fromUrl: true });
            syncViewPrToUrl();
            return true;
        }

        function viewPrHeadersMarkedApprovedForSave() {
            const ids = new Set();
            viewHeaderStatusPendingChanges.forEach((change) => {
                if (normalizeUdfStatus(change.udfStatus) === 'APPROVED') {
                    const rid = Number(change.requestId || 0);
                    if (rid > 0) {
                        ids.add(rid);
                    }
                }
            });
            return ids;
        }

        function activateViewPrApprovedTabAfterSave(approvedHeaderIds) {
            const ids = approvedHeaderIds instanceof Set ? approvedHeaderIds : new Set();
            if (!ids.size) {
                const selectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;
                if (selectedId > 0) {
                    const header = (viewPurchaseRequests || []).find((row) => Number(row.id || 0) === selectedId);
                    if (header && normalizeUdfStatus(header._originalUdfStatus || header.udfStatus) === 'APPROVED') {
                        ids.add(selectedId);
                    }
                }
            }
            if (!ids.size) {
                return false;
            }
            viewStatusFilters = new Set(['APPROVED']);
            syncViewStatusFilterTabClasses();
            syncViewPrToUrl();
            return true;
        }

        async function finalizeViewPrAfterApprovalSave(selectedHeaderId, options) {
            const opts = options && typeof options === 'object' ? options : {};
            const keepId = Number(selectedHeaderId || viewSelectedHeaderId || 0);
            const rawTarget = String(opts.targetUdfStatus || '').trim().toUpperCase();
            const targetUdf = rawTarget ? normalizeUdfStatus(rawTarget) : '';
            if (keepId > 0) {
                viewSelectedHeaderId = keepId;
                const record = (viewPurchaseRequests || []).find((row) => Number(row.id || 0) === keepId);
                if (record) {
                    if (targetUdf === 'PENDING') {
                        record.udfStatus = 'PENDING';
                        record._originalUdfStatus = 'PENDING';
                        delete record._pendingUdfStatus;
                        invalidateViewDetailCache(keepId);
                        goToViewPrStatus('PENDING', { reload: true });
                        syncViewPrToUrl();
                        return;
                    }
                    if (targetUdf === 'CANCELLED') {
                        const docBefore = viewPrDocStatus(record);
                        const fromDraftPanel = opts.fromDraftPanel === true
                            || (viewStatusFilters instanceof Set && viewStatusFilters.has('DRAFT'));
                        const hideCancelledDraft = fromDraftPanel || docBefore === 'DRAFT' || docBefore === 'CANCELLED';
                        record.udfStatus = 'CANCELLED';
                        record._originalUdfStatus = 'CANCELLED';
                        delete record._pendingUdfStatus;
                        invalidateViewDetailCache(keepId);
                        if (hideCancelledDraft) {
                            record.status = 'CANCELLED';
                            viewPurchaseRequests = (viewPurchaseRequests || []).filter(
                                (row) => Number(row.id || 0) !== keepId
                            );
                            viewSelectedHeaderId = null;
                            goToViewPrStatus('DRAFT', { reload: true });
                        } else {
                            goToViewPrStatus('CANCELLED', { reload: true });
                        }
                        syncViewPrToUrl();
                        return;
                    }
                    if (targetUdf === 'AWAITING') {
                        record.udfStatus = 'AWAITING';
                        record._originalUdfStatus = 'AWAITING';
                        if (String(record.status || '').trim().toUpperCase() === 'DRAFT') {
                            record.status = 'SUBMITTED';
                        }
                        delete record._pendingUdfStatus;
                        invalidateViewDetailCache(keepId);
                        goToViewPrStatus('AWAITING', { reload: true });
                        syncViewPrToUrl();
                        return;
                    }
                    if (targetUdf === 'APPROVED') {
                        record.udfStatus = 'APPROVED';
                        record._originalUdfStatus = 'APPROVED';
                        delete record._pendingUdfStatus;
                    }
                    if (targetUdf === 'APPROVED' || !targetUdf) {
                        invalidateViewDetailCache(keepId);
                        viewLoadingDetailIds.add(keepId);
                        renderFilteredViewPurchaseRequests();
                        try {
                            await fetchViewPurchaseRequestDetail(record, true);
                        } catch (error) {
                            console.warn('[View PR] Failed to refresh detail after approval:', error);
                        }
                        viewLoadingDetailIds.delete(keepId);
                        syncViewPrToUrl();
                        renderFilteredViewPurchaseRequests();
                        loadViewPurchaseRequests(false, { background: true });
                        return;
                    }
                }
            }
            await loadViewPurchaseRequests(false, { background: true });
            if (!selectViewPrFromUrlIfPresent()) {
                syncViewPrToUrl();
            }
            renderFilteredViewPurchaseRequests();
        }

        function applyViewStatusFromUrl() {
            const fromUrl = readViewStatusFromUrl();
            if (!fromUrl) {
                return;
            }
            viewStatusFilters = new Set([fromUrl]);
            syncViewStatusFilterTabClasses();
        }

        function setProcurementUrlTab(tabName) {

            try {

                const url = new URL(window.location.href);

                url.searchParams.set('tab', String(tabName || 'report').toLowerCase());

                history.replaceState({}, '', url);

            } catch (e) { /* ignore */ }

        }

        function openStockReportSettingsDrawer() {
            /* Filters are always visible on desktop; keep as no-op for callers. */
        }

        function closeStockReportSettingsDrawer() {
            closeAllStockMultiSelects();
            document.body.classList.remove('stock-report-settings-drawer-open');
        }

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeStockReportSettingsDrawer();
        });

        function showTab(tabName) {
            try { closeStockReportSettingsDrawer(); } catch (e) {}

            const target = String(tabName || 'report').toLowerCase();

            const tabs = ['report', 'view', 'create'];

            const selected = tabs.includes(target) ? target : 'report';

            updateProcurementPageTitle(selected);

            tabs.forEach((name) => {

                const tabButton = document.getElementById(`tab-${name}`);

                if (tabButton) {

                    tabButton.classList.toggle('is-active', name === selected);
                    tabButton.setAttribute('aria-selected', name === selected ? 'true' : 'false');

                }

                const panel = document.getElementById(`panel-${name}`);

                if (panel) {

                    panel.style.display = name === selected ? '' : 'none';

                }

            });

            setProcurementUrlTab(selected);

            if (selected === 'report') {

                initStockCardUomDisplay();

                afterStockCardTableRender();

                // Refetch when coming back to the dashboard (not the first paint: DOMContentLoaded

                // already loads once while reportLoaded is still false).

                if (reportLoaded) {

                    loadStockCardRows();

                }

                return;

            }

            if (selected === 'view') {

                loadViewPurchaseRequests(false);

                return;

            }

            if (selected === 'create') {
                ensureCreatePrLookups();
                if (!Array.isArray(window.purchaseRequestItems) || !window.purchaseRequestItems.length) {
                    initPurchaseRequestForm();
                }
                if (Array.isArray(window.purchaseRequestItems)) {
                    window.purchaseRequestItems.forEach((it) => {
                        cachePrLineUdfWtp(it, null);
                        if (resolvePrLineUdfWeight(it) != null && Number(it.qtySqty || 0) > 0) {
                            applyPrLineSuomFromSqtyUdfWeight(it);
                            syncPrLineQuantityDerived(it);
                        }
                    });
                }
                renderPurchaseRequestLineItems();
            }

        }

        const STOCK_CARD_UOM_LS = 'procurementStockCardUomDisplay';

        const STOCK_CARD_SELECTED_LOCATIONS_LS = 'procurementStockCardSelectedLocations';
        const PURCHASE_REQUEST_DRAFT_LS_KEY = 'procurementCreatePrDraftItemsV1';

        let stockCardUomDisplayMode = 'suom_only';

        function persistStockCardSelectedLocations() {

            try {

                localStorage.setItem(STOCK_CARD_SELECTED_LOCATIONS_LS, JSON.stringify(selectedStockCardLocations));

            } catch (e) { /* ignore */ }

        }

        function readPersistedStockCardLocations() {

            try {

                const raw = localStorage.getItem(STOCK_CARD_SELECTED_LOCATIONS_LS);

                if (!raw) return null;

                const arr = JSON.parse(raw);

                return Array.isArray(arr) ? arr : null;

            } catch (e) {

                return null;

            }

        }

        function initStockCardUomDisplay() {

            try {

                const v = localStorage.getItem(STOCK_CARD_UOM_LS);

                if (v === 'sqty_only' || v === 'suom_only' || v === 'both') {

                    stockCardUomDisplayMode = v;

                }

            } catch (e) { /* ignore */ }

            document.querySelectorAll('input[name="stock-card-uom-col"]').forEach((el) => {

                el.checked = el.value === stockCardUomDisplayMode;

            });

        }

        function onStockCardUomDisplayChange(radio) {

            if (!radio) return;

            const v = String(radio.value || '').trim();

            stockCardUomDisplayMode = (v === 'sqty_only' || v === 'suom_only' || v === 'both') ? v : 'suom_only';

            try {

                localStorage.setItem(STOCK_CARD_UOM_LS, stockCardUomDisplayMode);

            } catch (e) { /* ignore */ }

            stockCardBuySelections = {};

            updateStockReportFilterSummary();

            if (reportLoaded) {

                loadStockCardRows();

            } else {

                syncStockCardTable();

            }

        }

        function stockCardSubcolsPerLocation() {

            return stockCardUomDisplayMode === 'both' ? 2 : 1;

        }

        function defaultPrStockQtyUom() {

            return stockCardUomDisplayMode === 'sqty_only' ? 'SQTY' : 'SUOMQTY';

        }

        /** Unit price applies to SQTY if present, otherwise SUOMQTY (same rule as server). */

        function linePricingQty(item) {

            const qs = Number(item.qtySqty || 0);

            const qu = Number(item.qtySuomqty || 0);

            if (qs > 0) return qs;

            if (qu > 0) return qu;

            return Number(item.quantity || 0);

        }

        function deriveStockQtyUomForPayload(item) {

            const qs = Number(item.qtySqty || 0);

            const qu = Number(item.qtySuomqty || 0);

            if (qs > 0 && qu <= 0) return 'SQTY';

            if (qu > 0 && qs <= 0) return 'SUOMQTY';

            if (qs > 0 && qu > 0) return 'SQTY';

            return defaultPrStockQtyUom();

        }

        function syncPrLineQuantityDerived(item) {

            if (!item) return;

            item.quantity = linePricingQty(item);

            item.stockQtyUom = deriveStockQtyUomForPayload(item);

        }

        /** Positive UDF_WTP from catalog row (SQL API / ST_ITEM); omitted or invalid → no auto SUOM. */

        function prItemUdfWeight(product) {

            if (!product) return null;

            const raw = product.UDF_WTP != null
                ? product.UDF_WTP
                : (product.udf_wtp != null ? product.udf_wtp : (product.UDF_WEIGHT != null ? product.UDF_WEIGHT : product.udf_weight));

            if (raw === null || raw === undefined || raw === '') return null;

            const n = Number(String(raw).replace(/,/g, '').trim());

            if (!Number.isFinite(n) || n <= 0) return null;

            return n;

        }

        const PR_LINE_STOCK_UDF_KEYS = [
            'udf_thickness', 'udf_width', 'udf_length', 'udf_dp', 'udf_dfp',
            'udf_wtp', 'udf_2uom', 'udf_formula', 'udf_costkg', 'udf_mtype',
            'udf_stdprice', 'udf_dleadtime', 'udf_moq', 'udf_bundle',
        ];

        function prCatalogUdfScalar(product, key) {
            const v = prCatalogScalar(product, key, key.toUpperCase());
            if (v == null || v === '') return null;
            if (String(v).trim() === '0') return null;
            return v;
        }

        const PR_LINE_DIM_UDF_KEYS = ['udf_thickness', 'udf_width', 'udf_length'];

        /** Prefer user-edited line dimension; else catalog product value. */
        function prLineDimValue(item, product, key) {
            if (item && item.dimsEdited && item.dimsEdited[key]) {
                const edited = item[key];
                if (edited != null && String(edited).trim() !== '') return String(edited).trim();
                return '';
            }
            if (item && item[key] != null && String(item[key]).trim() !== '' && String(item[key]).trim() !== '0') {
                return String(item[key]).trim();
            }
            return (typeof prCatalogUdfValue === 'function' ? prCatalogUdfValue(product, key) : '') || '';
        }

        function updatePurchaseRequestDimension(index, key, value) {
            if (!window.purchaseRequestItems || !window.purchaseRequestItems[index]) return;
            if (!PR_LINE_DIM_UDF_KEYS.includes(key)) return;
            const item = window.purchaseRequestItems[index];
            const raw = value == null ? '' : String(value).trim();
            item[key] = raw;
            item.dimsEdited = { ...(item.dimsEdited || {}), [key]: true };
            const detail = { ...(item.stockDetail || {}) };
            if (raw === '') {
                delete detail[key];
                delete detail[key.toUpperCase()];
            } else {
                detail[key] = raw;
                detail[key.toUpperCase()] = raw;
            }
            item.stockDetail = detail;
            if (typeof savePurchaseRequestDraftItems === 'function') {
                savePurchaseRequestDraftItems();
            }
        }

        /** Copy ST_ITEM / catalog UDFs onto a PR line for display + SQL API submit. */
        function mergePrLineCatalogUdfs(item, product) {
            if (!item) return item;
            const src = product || (typeof findPrProductByCode === 'function' ? findPrProductByCode(item.itemCode) : null);
            if (!src || typeof src !== 'object') return item;
            const dimsEdited = (item.dimsEdited && typeof item.dimsEdited === 'object') ? item.dimsEdited : {};
            const detail = { ...(item.stockDetail || {}) };
            PR_LINE_STOCK_UDF_KEYS.forEach((key) => {
                if (dimsEdited[key]) return;
                const v = prCatalogUdfScalar(src, key);
                if (v == null) return;
                item[key] = v;
                detail[key] = v;
                detail[key.toUpperCase()] = v;
            });
            Object.keys(src).forEach((k) => {
                const kl = String(k).toLowerCase();
                if (!kl.startsWith('udf_')) return;
                if (dimsEdited[kl]) return;
                const v = src[k];
                if (v == null || String(v).trim() === '') return;
                item[kl] = v;
                detail[kl] = v;
            });
            item.stockDetail = { ...src, ...detail };
            return item;
        }

        function prLineStockFieldsForPayload(item) {
            const out = {};
            if (!item || typeof item !== 'object') return out;
            PR_LINE_STOCK_UDF_KEYS.forEach((key) => {
                const v = item[key];
                if (v == null || String(v).trim() === '') return;
                out[key] = v;
            });
            if (item.stockDetail && typeof item.stockDetail === 'object') {
                out.stockDetail = item.stockDetail;
            }
            return out;
        }

        /** SUOMQTY = SQTY × UDF_WTP when the item has a positive WTP in ST_ITEM. */
        function cachePrLineUdfWtp(item, product) {
            if (!item) return null;
            const src = product || findPrProductByCode(item.itemCode);
            const w = prItemUdfWeight(src);
            if (w != null) item.udfWtp = w;
            return w;
        }

        function resolvePrLineUdfWeight(item) {
            if (!item) return null;
            if (item.udfWtp != null && item.udfWtp !== '') {
                const n = Number(String(item.udfWtp).replace(/,/g, '').trim());
                if (Number.isFinite(n) && n > 0) return n;
            }
            return cachePrLineUdfWtp(item, null);
        }

        function applyPrLineSuomFromSqtyUdfWeight(item) {
            if (!item) return;
            const w = resolvePrLineUdfWeight(item);
            if (w == null) return;
            const qs = Number(item.qtySqty || 0);
            item.qtySuomqty = Math.round(qs * w * 10000) / 10000;
        }

        function refreshPrLineSuomQtyDisplay(index, item, sqInputEl) {
            if (!item) return;
            applyPrLineSuomFromSqtyUdfWeight(item);
            syncPrLineQuantityDerived(item);
            const row = document.querySelector(`#pr-line-items-body tr[data-pr-index="${index}"]`);
            const w = resolvePrLineUdfWeight(item);
            if (!row || w == null) return;
            const suEl = row.querySelector('[data-pr-field="qtySuomqty"]');
            setTimeout(() => {
                const active = sqInputEl && document.body && document.body.contains(sqInputEl) ? sqInputEl : null;
                if (suEl && suEl.tagName === 'SPAN') {
                    suEl.textContent = formatStockCardNumber(Number(item.qtySuomqty || 0));
                }
                if (active && typeof active.focus === 'function') {
                    try { active.focus({ preventScroll: true }); } catch (_) { active.focus(); }
                }
            }, 0);
        }

        /** Merge stock-card SQTY + SUOMQTY selections into one PR line per item + location (fixes duplicate rows / wrong qty). */

        function mergeBuySelectionsForCreatePr(selectedEntries) {

            const map = new Map();

            selectedEntries.forEach((entry) => {

                if (!entry || !entry.selected) return;

                const code = String(entry.itemCode || '').trim();

                const loc = String(entry.locationCode || '').trim();

                const k = `${code}||${loc}`;

                const uom = String(entry.stockQtyUom || '').toUpperCase() === 'SQTY' ? 'SQTY' : 'SUOMQTY';

                const q = Number(entry.quantity || 0);

                let row = map.get(k);

                if (!row) {

                    row = { itemCode: code, locationCode: loc, qtySqty: 0, qtySuomqty: 0 };

                    map.set(k, row);

                }

                if (uom === 'SQTY') {

                    row.qtySqty = q;

                } else {

                    row.qtySuomqty = q;

                }

            });

            return Array.from(map.values());

        }

        function stockCardSingleUomLabel() {

            if (stockCardUomDisplayMode === 'sqty_only') return 'SQTY';

            if (stockCardUomDisplayMode === 'suom_only') return 'SUOMQTY';

            return 'SQTY';

        }

        const stockCardMetricGroups = [

            { key: 'avail_qty_by_location', label: 'Qty on Hand', maps: { sqty: 'avail_qty_sqty_by_location', suom: 'avail_qty_suom_by_location' } },

            { key: 'po_qty_by_location', label: 'P.O Qty', maps: { sqty: 'po_qty_sqty_by_location', suom: 'po_qty_suom_by_location' } },

            { key: 'so_qty_by_location', label: 'S.O Qty', maps: { sqty: 'so_qty_sqty_by_location', suom: 'so_qty_suom_by_location' } },

            { key: 'jo_qty_by_location', label: 'J.O Qty', maps: { sqty: 'jo_qty_sqty_by_location', suom: 'jo_qty_suom_by_location' } },

            { key: 'qty_by_location', label: 'Avail. Qty', maps: { sqty: 'qty_sqty_by_location', suom: 'qty_suom_by_location' } },

            { key: 'need_to_buy_by_location', label: 'Order', maps: { sqty: 'need_to_buy_sqty_by_location', suom: 'need_to_buy_suom_by_location' } },

            { key: 'pending_pr_by_location', label: 'Pending PR', maps: { sqty: 'pending_pr_sqty_by_location', suom: 'pending_pr_suom_by_location' } },
            { key: 'avg_sales_3m_by_location', label: 'Avg Sales 3M', maps: { sqty: 'avg_sales_3m_sqty_by_location', suom: 'avg_sales_3m_suom_by_location' } },

        ];

        const STOCK_METRIC_FILTER_LS_KEY = 'procurement-stock-card-metric-filter-v1';

        let stockCardMetricFilter = null;
        let stockCardAvgSales3mMonths = [];

        function loadStockMetricFilter() {

            stockCardMetricFilter = {};

            try {

                const raw = localStorage.getItem(STOCK_METRIC_FILTER_LS_KEY);

                if (raw) {

                    const o = JSON.parse(raw);

                    if (o && typeof o === 'object') {

                        stockCardMetricFilter = { ...o };

                    }

                }

            } catch (e) {

                stockCardMetricFilter = {};

            }

        }

        function saveStockMetricFilter() {

            try {

                if (stockCardMetricFilter && typeof stockCardMetricFilter === 'object') {

                    localStorage.setItem(STOCK_METRIC_FILTER_LS_KEY, JSON.stringify(stockCardMetricFilter));

                }

            } catch (e) { /* ignore */ }

        }

        function ensureStockCardMetricFilterShape() {

            loadStockMetricFilter();

            let changed = false;

            stockCardMetricGroups.forEach((g) => {

                if (stockCardMetricFilter[g.key] === undefined) {

                    stockCardMetricFilter[g.key] = true;

                    changed = true;

                }

            });

            if (changed) {

                saveStockMetricFilter();

            }

        }

        function isMetricGroupVisible(key) {

            ensureStockCardMetricFilterShape();

            if (stockCardMetricFilter[key] === undefined) {

                return true;

            }

            return stockCardMetricFilter[key] !== false;

        }

        function getVisibleStockCardMetricGroups() {

            ensureStockCardMetricFilterShape();

            return stockCardMetricGroups.filter((g) => stockCardMetricFilter[g.key] !== false);

        }

        function stockCardUomModeSummaryLabel() {
            if (stockCardUomDisplayMode === 'sqty_only') return 'SQTY only';
            if (stockCardUomDisplayMode === 'both') return 'SQTY + SUOMQTY';
            return 'SUOMQTY only';
        }

        function stockCardLocationSummaryLabel() {
            const all = Array.isArray(stockCardLocations) ? stockCardLocations : [];
            const selected = Array.isArray(selectedStockCardLocations) ? selectedStockCardLocations : [];
            const n = selected.length;
            const total = all.length;
            if (total > 0 && n === total) return `All locations (${total})`;
            if (n === 0) return '0 locations selected';
            if (n === 1) return '1 location selected';
            return `${n} locations selected`;
        }

        function stockCardColumnSummaryLabel() {
            ensureStockCardMetricFilterShape();
            const total = stockCardMetricGroups.length;
            const n = stockCardMetricGroups.filter((g) => isMetricGroupVisible(g.key)).length;
            if (n === total) return `All column groups (${total})`;
            if (n === 0) return '0 groups selected';
            if (n === 1) return '1 group selected';
            return `${n} groups selected`;
        }

        function updateStockReportFilterSummary() {
            const el = document.getElementById('stock-report-filter-summary');
            const locValue = document.getElementById('stock-location-ms-value');
            const colValue = document.getElementById('stock-column-ms-value');
            const locLabel = stockCardLocationSummaryLabel();
            const colLabel = stockCardColumnSummaryLabel();
            const uomLabel = stockCardUomModeSummaryLabel();
            if (locValue) locValue.textContent = locLabel;
            if (colValue) colValue.textContent = colLabel;
            if (el) {
                el.textContent = `${locLabel} · ${colLabel} · ${uomLabel}`;
            }
        }

        function closeAllStockMultiSelects() {
            ['location', 'column'].forEach((kind) => {
                const root = document.getElementById(kind === 'location' ? 'stock-location-ms' : 'stock-column-ms');
                const trigger = document.getElementById(kind === 'location' ? 'stock-location-ms-trigger' : 'stock-column-ms-trigger');
                const menu = document.getElementById(kind === 'location' ? 'stock-location-ms-menu' : 'stock-column-ms-menu');
                if (root) root.classList.remove('is-open');
                if (menu) menu.hidden = true;
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            });
        }

        function toggleStockMultiSelect(kind) {
            const isLocation = kind === 'location';
            const root = document.getElementById(isLocation ? 'stock-location-ms' : 'stock-column-ms');
            const trigger = document.getElementById(isLocation ? 'stock-location-ms-trigger' : 'stock-column-ms-trigger');
            const menu = document.getElementById(isLocation ? 'stock-location-ms-menu' : 'stock-column-ms-menu');
            if (!root || !menu || !trigger) return;
            const willOpen = menu.hidden;
            closeAllStockMultiSelects();
            if (!willOpen) return;
            menu.hidden = false;
            root.classList.add('is-open');
            trigger.setAttribute('aria-expanded', 'true');
        }

        document.addEventListener('mousedown', function (ev) {
            const t = ev.target;
            if (!(t instanceof Element)) return;
            if (t.closest('.stock-ms')) return;
            closeAllStockMultiSelects();
        });

        function renderStockColumnFilterPanel() {
            ensureStockCardMetricFilterShape();
            const host = document.getElementById('stock-column-filter-chips');
            if (!host) return;
            const colMenu = document.getElementById('stock-column-ms-menu');
            const wasOpen = !!(colMenu && !colMenu.hidden);
            const parts = [];
            stockCardMetricGroups.forEach((g) => {
                const on = isMetricGroupVisible(g.key);
                const safeId = String(g.key || '').replace(/[^a-z0-9_]/gi, '_');
                parts.push(
                    `<label class="stock-ms__option"><input type="checkbox" id="stock-col-filter-${safeId}" ${on ? 'checked' : ''} onchange="onStockColumnMetricFilterChange('${escapeJs(g.key)}', this.checked)" /> <span>${escapeHtml(g.label)}</span></label>`,
                );
            });
            host.innerHTML = parts.join('');
            updateStockReportFilterSummary();
            if (wasOpen) {
                const root = document.getElementById('stock-column-ms');
                const trigger = document.getElementById('stock-column-ms-trigger');
                const menu = document.getElementById('stock-column-ms-menu');
                if (root) root.classList.add('is-open');
                if (menu) menu.hidden = false;
                if (trigger) trigger.setAttribute('aria-expanded', 'true');
            }
        }

        function onStockColumnMetricFilterChange(key, checked) {
            ensureStockCardMetricFilterShape();
            stockCardMetricFilter[key] = !!checked;
            saveStockMetricFilter();
            syncStockCardTable();
        }

        function selectAllStockCardMetricGroups() {
            ensureStockCardMetricFilterShape();
            stockCardMetricGroups.forEach((g) => {
                stockCardMetricFilter[g.key] = true;
            });
            saveStockMetricFilter();
            syncStockCardTable();
        }

        function clearAllStockCardMetricGroups() {
            ensureStockCardMetricFilterShape();
            stockCardMetricGroups.forEach((g) => {
                stockCardMetricFilter[g.key] = false;
            });
            saveStockMetricFilter();
            syncStockCardTable();
        }

        function toggleStockReportAdvancedSettings() {

            const wrap = document.getElementById('stock-report-advanced-settings');

            const btn = document.getElementById('stock-report-advanced-toggle');

            if (!wrap) {

                return;

            }

            wrap.classList.toggle('stock-report-advanced-settings--collapsed');

            const collapsed = wrap.classList.contains('stock-report-advanced-settings--collapsed');

            wrap.setAttribute('aria-hidden', collapsed ? 'true' : 'false');

            if (btn) {

                btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');

                btn.textContent = collapsed ? 'Report qty & layout…' : 'Hide report qty & layout';

            }

        }

        function sumStockCardMapAcrossLocations(row, mapKey, locationColumns) {

            const m = row && row[mapKey] ? row[mapKey] : {};

            const locs = Array.isArray(locationColumns) ? locationColumns : [];

            if (!locs.length) {

                return Object.keys(m).reduce((acc, k) => acc + Number(m[k] || 0), 0);

            }

            return locs.reduce((acc, loc) => acc + Number(m[loc] || 0), 0);

        }

        function getStockCardTotalColumns(locations) {

            const locs = Array.isArray(locations) ? locations : [];

            const visibleGroups = getVisibleStockCardMetricGroups();

            const G = visibleGroups.length;

            if (G === 0) {

                return 2;

            }

            if (!locs.length) {

                return 1 + G;

            }

            const sub = stockCardSubcolsPerLocation();

            const L = locs.length;

            const perGroup = sub === 2 ? L * 2 : L;

            return 1 + G * perGroup;

        }

        function setStockCardTableNoMetricColsClass() {

            const table = document.getElementById('stock-card-table');

            if (!table) {

                return;

            }

            const empty = getVisibleStockCardMetricGroups().length === 0;

            table.classList.toggle('stock-card-table--no-metric-cols', empty);

        }

        function canEditPrLineSelection(header) {
            const s = normalizeUdfStatus((header && (header._originalUdfStatus || header.udfStatus)) || '');
            return s === 'AWAITING' || s === 'PENDING' || s === 'APPROVED';
        }

        function isCancelledPurchaseRequest(header) {
            return normalizeUdfStatus((header && (header._originalUdfStatus || header.udfStatus)) || '') === 'CANCELLED';
        }

        function toApprovalBool(value) {

            const text = String(value ?? '').trim().toUpperCase();

            if (text === '1' || text === 'TRUE' || text === 'Y' || text === 'YES' || text === 'T') return true;

            if (text === '0' || text === 'FALSE' || text === 'N' || text === 'NO' || text === 'F') return false;

            return Boolean(value);

        }

        function hasPendingApprovalChangesForHeader(headerId) {

            const target = Number(headerId || 0);

            if (!target) return false;

            for (const change of viewApprovalPendingChanges.values()) {

                if (Number(change.requestId || 0) === target) {

                    return true;

                }

            }

            return false;

        }

        function hasPendingHeaderStatusChangesForHeader(headerId) {

            return viewHeaderStatusPendingChanges.has(String(headerId));

        }

        /** Header can receive UDF status save (not cancelled; doc status allows review). Does not require list selection or loaded line items. */

        function isPrEligibleForHeaderStatusSave(header) {

            if (!header) {

                return false;

            }

            const id = Number(header.id || 0);

            if (!id) {

                return false;

            }

            if (viewLoadingDetailIds.has(id)) {

                return false;

            }

            const udf = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);

            if (udf === 'CANCELLED') {

                return false;

            }

            const docSt = String(header.status || '').trim().toUpperCase();

            if (docSt === 'CANCELLED') {

                return false;

            }

            return docSt === 'DRAFT' || docSt === 'SUBMITTED' || docSt === 'APPROVED';

        }

        /** Selected PR can receive approval / transfer-qty updates (not cancelled; doc status allows review). */

        function isPrEligibleForAvailabilityUpdate(header) {

            if (!header) {

                return false;

            }

            const id = Number(header.id || 0);

            if (!id) {

                return false;

            }

            if (viewSelectedHeaderId == null || Number(viewSelectedHeaderId) !== id) {

                return false;

            }

            if (viewLoadingDetailIds.has(id)) {

                return false;

            }

            const details = header.details;

            if (!Array.isArray(details) || details.length === 0) {

                return false;

            }

            return isPrEligibleForHeaderStatusSave(header);

        }

        function isViewPrUpdateSaveEligible() {

            if (viewApprovalPendingChanges.size > 0) {

                const headerIds = new Set(Array.from(viewApprovalPendingChanges.values()).map((c) => Number(c.requestId)));

                for (const hid of headerIds) {

                    const h = viewPurchaseRequests.find((row) => Number(row.id || 0) === hid);

                    if (!h || !isPrEligibleForAvailabilityUpdate(h)) {

                        return false;

                    }

                }

            }

            if (viewHeaderStatusPendingChanges.size > 0) {

                for (const ch of viewHeaderStatusPendingChanges.values()) {

                    const h = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(ch.requestId));

                    if (!h || !isPrEligibleForHeaderStatusSave(h)) {

                        return false;

                    }

                }

            }

            return true;

        }

        function updateViewApprovalButtonState() {

            const btn = document.getElementById('view-pr-update-btn');

            if (!btn) return;

            const hideAppr = document.body.classList.contains('procurement-hide-pr-approval-edits');

            const hasChanges = viewApprovalPendingChanges.size > 0 || viewHeaderStatusPendingChanges.size > 0;

            const saving = viewApprovalSaving;

            const eligible = hasChanges && isViewPrUpdateSaveEligible();

            btn.disabled = hideAppr || saving || !eligible;

            btn.textContent = saving ? 'Saving...' : 'Update';

            btn.title = 'Save pending approval status and line selections.';

        }

        function rowSavedUdfStatus(row) {

            return normalizeUdfStatus(row?._originalUdfStatus || row?.udfStatus);

        }

        function rowPrStatusUpper(row) {

            return String(row?.status || '').trim().toUpperCase();

        }

        function viewPrDocStatus(row) {
            const raw = String(row?.status ?? '').trim().toUpperCase();
            if (raw === '0') return 'DRAFT';
            if (raw === '1') return 'SUBMITTED';
            if (raw === '2') return 'APPROVED';
            if (raw === '3') return 'REJECTED';
            if (raw === '4') return 'CANCELLED';
            return raw;
        }

        function isHiddenCancelledDraft(row) {
            const udf = rowSavedUdfStatus(row);
            const doc = viewPrDocStatus(row);
            return udf === 'CANCELLED' && (doc === 'DRAFT' || doc === 'CANCELLED');
        }

        function rowMatchesViewStatusFilter(row, statusFilter) {

            if (isHiddenCancelledDraft(row)) {
                return false;
            }

            const f = String(statusFilter || '').toUpperCase();

            if (f === 'DRAFT') {
                if (rowPrStatusUpper(row) !== 'DRAFT') {
                    return false;
                }
                const udf = rowSavedUdfStatus(row);
                return !udf || udf === 'DRAFT';
            }

            return rowSavedUdfStatus(row) === f;

        }

        function getViewStatusFilterCounts() {

            const rows = viewPurchaseRequests || [];

            const counts = {};

            VIEW_STATUS_FILTER_OPTIONS.forEach((s) => {

                counts[s] = rows.filter((row) => rowMatchesViewStatusFilter(row, s)).length;

            });

            return counts;

        }

        function getFilteredViewPurchaseRequests() {

            const filters = viewStatusFilters instanceof Set ? viewStatusFilters : new Set(['PENDING']);

            const searchText = String(viewPrSearchText || '').trim().toUpperCase();

            const sortLatest = (rows) => (rows || []).slice().sort((a, b) => {

                const ad = new Date(a.requestDate || a.requiredDate || 0).getTime();

                const bd = new Date(b.requestDate || b.requiredDate || 0).getTime();

                const aTime = Number.isFinite(ad) ? ad : 0;

                const bTime = Number.isFinite(bd) ? bd : 0;

                if (bTime !== aTime) return bTime - aTime;

                return Number(b.id || 0) - Number(a.id || 0);

            });

            let rows = (viewPurchaseRequests || []).filter((row) => !isHiddenCancelledDraft(row));

            if (filters.size) {

                rows = rows.filter((row) => Array.from(filters).some((f) => rowMatchesViewStatusFilter(row, f)));

            }

            if (searchText) {

                rows = rows.filter((row) => String(row.requestNumber || '').toUpperCase().includes(searchText));

            }

            return sortLatest(rows);

        }

        function onViewPrSearchChange(value) {

            viewPrSearchText = String(value || '');

            renderFilteredViewPurchaseRequests();

        }

        function syncViewStatusFilterTabClasses() {

            const tabs = document.querySelectorAll('#view-pr-filter-tabs .view-pr-filter-tab');

            const counts = getViewStatusFilterCounts();

            tabs.forEach((tab) => {

                const tabStatus = String(tab.getAttribute('data-status') || '').toUpperCase();

                const on = viewStatusFilters.has(tabStatus);

                tab.classList.toggle('is-active', on);
                tab.setAttribute('aria-selected', on ? 'true' : 'false');

                tab.classList.toggle('active', on);

                const n = Number(counts[tabStatus] || 0);

                const label = VIEW_PR_TAB_LABELS[tabStatus] || tabStatus;

                tab.textContent = `${label} (${n})`;

            });

            try { syncViewPrApprovedOnlyToolbarActions(); } catch (e) { /* ignore */ }

        }

        function goToViewPrStatus(status, options) {
            const s = String(status || '').trim().toUpperCase();
            const opts = options && typeof options === 'object' ? options : {};
            if (VIEW_STATUS_FILTER_OPTIONS.includes(s)) {
                viewStatusFilters = new Set([s]);
                try {
                    const url = new URL(window.location.href);
                    url.searchParams.set('tab', 'view');
                    url.searchParams.set('status', s.toLowerCase());
                    history.replaceState({}, '', url);
                } catch (e) { /* ignore */ }
            }
            showTab('view');
            try { syncViewStatusFilterTabClasses(); } catch (e) { /* ignore */ }
            try { syncViewStatusToUrl(); } catch (e) { /* ignore */ }
            if (opts.reload !== false) {
                try { loadViewPurchaseRequests(true, { bustCache: true }); } catch (e) { /* ignore */ }
            } else {
                try { renderFilteredViewPurchaseRequests(); } catch (e) { /* ignore */ }
            }
        }

        function toggleViewStatusFilter(status) {

            const s = String(status || '').toUpperCase();

            if (!VIEW_STATUS_FILTER_OPTIONS.includes(s)) {

                return;

            }

            viewBulkSelectedHeaderIds.clear();

            viewStatusFilters = new Set([s]);

            syncViewStatusFilterTabClasses();

            syncViewPrApprovedOnlyToolbarActions();

            renderFilteredViewPurchaseRequests();

            syncViewStatusToUrl();

            if (viewSelectedHeaderId != null) {

                refreshSelectedViewPurchaseRequestDetail(true);

            }

        }

        function isViewPendingBulkSelectMode() {
            // List bulk select for Awaiting / Pending / Approved tabs.
            return (
                viewStatusFilters instanceof Set
                && viewStatusFilters.size === 1
                && (viewStatusFilters.has('AWAITING') || viewStatusFilters.has('PENDING') || viewStatusFilters.has('APPROVED'))
            );
        }

        function getViewListBulkTargetUdfStatus() {
            if (!(viewStatusFilters instanceof Set) || viewStatusFilters.size !== 1) {
                return '';
            }
            if (viewStatusFilters.has('PENDING')) {
                return 'APPROVED';
            }
            if (viewStatusFilters.has('AWAITING')) {
                return 'PENDING';
            }
            return '';
        }

        function pruneViewBulkSelectionToFilteredList() {

            if (!isViewPendingBulkSelectMode()) {

                return;

            }

            const visible = new Set(getFilteredViewPurchaseRequests().map((r) => Number(r.id || 0)));

            for (const id of [...viewBulkSelectedHeaderIds]) {

                if (!visible.has(id)) {

                    viewBulkSelectedHeaderIds.delete(id);

                }

            }

        }

        function syncViewPendingBulkBar() {

            const bar = document.getElementById('view-pr-bulk-pending-bar');

            if (!bar) {

                return;

            }

            const hide = document.body.classList.contains('procurement-hide-pr-approval-edits');

            if (!isViewPendingBulkSelectMode() || hide) {

                bar.hidden = true;
                syncViewListBulkMasterCheckbox();

                return;

            }

            bar.hidden = false;

            const n = viewBulkSelectedHeaderIds.size;

            const hint = document.getElementById('view-pr-bulk-selection-count');

            if (hint) {

                hint.textContent = n === 0 ? 'No PRs selected.' : `${n} selected`;

            }

            const approveBtn = document.getElementById('view-pr-bulk-approve-btn');

            if (approveBtn) {

                approveBtn.disabled = n === 0;
                const targetUdf = getViewListBulkTargetUdfStatus();
                if (targetUdf === 'APPROVED') {
                    approveBtn.textContent = n === 0 ? 'Approve selected' : `Approve selected (${n})`;
                    approveBtn.hidden = false;
                } else if (targetUdf === 'PENDING') {
                    approveBtn.textContent = n === 0 ? 'Mark selected Pending' : `Mark selected Pending (${n})`;
                    approveBtn.hidden = false;
                } else {
                    approveBtn.textContent = 'Update selected';
                    approveBtn.hidden = true;
                }

            }

            const actions = bar.querySelector('.view-pr-bulk-pending-bar__actions');
            if (actions && approveBtn) {
                actions.hidden = !!approveBtn.hidden;
            }

                    syncViewListBulkMasterCheckbox();
        }

        function onViewPrBulkCardCheckboxChange(event, headerId) {

            if (document.body.classList.contains('procurement-hide-pr-approval-edits')) {

                if (event && event.target) {

                    event.target.checked = !event.target.checked;

                }

                return;

            }

            if (event) {

                event.stopPropagation();

            }

            const id = Number(headerId);

            if (!id) {

                return;

            }

            if (event && event.target && event.target.checked) {

                viewBulkSelectedHeaderIds.add(id);

            } else {

                viewBulkSelectedHeaderIds.delete(id);

            }

            syncViewPendingBulkBar();

        }

        function onViewPrListBulkSelectAllChange(el) {
            if (!el) {
                return;
            }
            if (el.checked) {
                viewPrBulkSelectAllPending();
            } else {
                viewPrBulkClearSelection();
            }
        }

        function syncViewListBulkMasterCheckbox() {
            const wrap = document.getElementById('view-pr-list-bulk-select-wrap');
            const master = document.getElementById('view-pr-list-bulk-select-all');
            if (!wrap || !master) {
                return;
            }
            const hide = document.body.classList.contains('procurement-hide-pr-approval-edits');
            const active = isViewPendingBulkSelectMode() && !hide;
            wrap.hidden = !active;
            if (!active) {
                master.checked = false;
                master.indeterminate = false;
                return;
            }
            const visibleIds = getFilteredViewPurchaseRequests()
                .map((r) => Number(r.id || 0))
                .filter((id) => id > 0);
            const selectedVisible = visibleIds.filter((id) => viewBulkSelectedHeaderIds.has(id));
            const all = visibleIds.length > 0 && selectedVisible.length === visibleIds.length;
            const some = selectedVisible.length > 0 && !all;
            master.checked = all;
            master.indeterminate = some;
        }

        function viewPrBulkSelectAllPending() {

            if (!isViewPendingBulkSelectMode()) {

                return;

            }

            getFilteredViewPurchaseRequests().forEach((row) => {

                const id = Number(row.id || 0);

                if (id) {

                    viewBulkSelectedHeaderIds.add(id);

                }

            });

            syncViewPendingBulkBar();

            renderFilteredViewPurchaseRequests();

        }

        function viewPrBulkClearSelection() {

            viewBulkSelectedHeaderIds.clear();

            syncViewPendingBulkBar();

            renderFilteredViewPurchaseRequests();

        }

        function queueHeaderUdfPendingFromSaved(requestId, value) {

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(requestId));

            if (!header) {

                return false;

            }

            const saved = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);
            const normalizedTarget = normalizeUdfStatus(value);
            const allowedFrom = {
                AWAITING: new Set(['AWAITING', 'PENDING', 'CANCELLED']),
                PENDING: new Set(['PENDING', 'APPROVED', 'CANCELLED']),
                APPROVED: new Set(['APPROVED', 'CANCELLED']),
                CANCELLED: new Set(['CANCELLED']),
                DRAFT: new Set(['DRAFT', 'AWAITING', 'PENDING', 'CANCELLED']),
                '': new Set(['', 'DRAFT', 'AWAITING', 'PENDING', 'CANCELLED']),
            };
            const allowed = allowedFrom[saved] || new Set([saved, 'CANCELLED']);
            if (!allowed.has(normalizedTarget)) {
                return false;
            }
            if (saved === 'AWAITING' && normalizedTarget === 'PENDING') {
                const suppliers = Array.isArray(header._suppliers) ? header._suppliers : [];
                if (!suppliers.length) {
                    alert('Select at least one supplier before moving to Pending (Awaiting RFQ).');
                    return false;
                }
            }

            if (saved === 'APPROVED' || saved === 'CANCELLED') {

                return false;

            }

            const normalized = normalizeUdfStatus(value);

            const original = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);

            const unchanged = normalized === original
                || (!normalized && (original === '' || original === 'DRAFT'))
                || (normalized === 'DRAFT' && !original);

            if (unchanged) {

                viewHeaderStatusPendingChanges.delete(String(requestId));

            } else {

                viewHeaderStatusPendingChanges.set(String(requestId), {

                    requestId: Number(requestId),
                    requestNumber: String((header && (header.requestNumber || header.docNo || header.docno)) || '').trim(),
                    udfStatus: normalized,

                });

            }

            return true;

        }

        function viewPrBulkQueueApproveSelected() {

            if (document.body.classList.contains('procurement-hide-pr-approval-edits')) {

                return;

            }

            if (!isViewPendingBulkSelectMode() || viewBulkSelectedHeaderIds.size === 0) {
                return;
            }

            const targetUdf = getViewListBulkTargetUdfStatus();
            if (!targetUdf) {
                return;
            }

            let any = false;

            for (const hid of viewBulkSelectedHeaderIds) {

                if (queueHeaderUdfPendingFromSaved(hid, targetUdf)) {

                    any = true;

                }

            }

            if (any) {

                updateViewApprovalButtonState();

                renderFilteredViewPurchaseRequests();

                if (typeof saveViewDetailApprovals === 'function') {
                    Promise.resolve(saveViewDetailApprovals()).catch((err) => {
                        console.warn('[VIEW PR] bulk approve save failed', err);
                    });
                }

            }

        }

        function renderFilteredViewPurchaseRequests() {

            pruneViewBulkSelectionToFilteredList();

            const rows = getFilteredViewPurchaseRequests();

            if (viewSelectedHeaderId != null && !rows.some((r) => Number(r.id || 0) === Number(viewSelectedHeaderId))) {

                viewSelectedHeaderId = null;

            }

            syncViewStatusFilterTabClasses();

            renderViewPurchaseRequests(rows);

            renderViewPurchaseRequestDetailPanel();

            updateViewApprovalButtonState();

            syncViewPendingBulkBar();

        }

        function getDetailMaxTransferQuantity(detail) {

            const remaining = Number(detail?.remainingQty);

            const quantity = Number(detail?.quantity || 0);

            if (Number.isFinite(remaining)) {

                return Math.max(0, remaining);

            }

            return Math.max(0, quantity);

        }

        function clampTransferQuantity(value, maxValue) {

            const max = Math.max(0, Number(maxValue || 0));

            const num = Number(value || 0);

            if (!Number.isFinite(num) || num <= 0) {

                return 0;

            }

            return Math.min(num, max);

        }

        function getDetailTransferQuantity(detail) {

            const max = getDetailMaxTransferQuantity(detail);

            return clampTransferQuantity(detail?.transferQty, max);

        }

        function getSelectedTransferDetails(header) {

            const details = Array.isArray(header?.details) ? header.details : [];

            return details.filter((detail) => getDetailTransferQuantity(detail) > 0);

        }

        function getSelectedTransferQuantityTotal(header) {

            return getSelectedTransferDetails(header).reduce((sum, detail) => sum + getDetailTransferQuantity(detail), 0);

        }

        function isPurchaseRequestTransferReady(header) {

            if (!header) return false;

            if (isCancelledPurchaseRequest(header)) return false;

            if (hasPendingHeaderStatusChangesForHeader(header.id)) return false;

            const selectedDetails = getSelectedTransferDetails(header);

            if (!selectedDetails.length) return false;

            return selectedDetails.every((detail) => isDetailChecked(detail));

        }

        function getPurchaseRequestTransferTitle(header) {

            if (!header) {

                return 'Purchase request not found.';

            }

            if (hasPendingHeaderStatusChangesForHeader(header.id)) {

                return 'Save header status changes before transferring this request.';

            }

            if (false) {

                return 'Save approval changes before transferring this request.';

            }

            const selectedDetails = getSelectedTransferDetails(header);

            if (!selectedDetails.length) {

                return 'Enter a transfer quantity greater than 0 for at least one approved row.';

            }

            if (!selectedDetails.every((detail) => isDetailChecked(detail))) {

                return 'Only rows marked transferable (approved) can be transferred.';

            }

            return `This request is ready to transfer ${formatStockCardNumber(getSelectedTransferQuantityTotal(header))} unit(s) to Purchase Order.`;

        }

        async function onTransferPurchaseRequest(headerId) {

            if (document.body.classList.contains('procurement-hide-transfer')) {

                return;

            }

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));

            if (!header || isCancelledPurchaseRequest(header)) {

                return;

            }

            if (!isPurchaseRequestTransferReady(header)) {

                alert(getPurchaseRequestTransferTitle(header));

                return;

            }

            const selectedDetails = getSelectedTransferDetails(header)

                .filter((detail) => Number(detail.id || 0) > 0)

                .map((detail) => ({

                    detailId: Number(detail.id || 0),

                    quantity: getDetailTransferQuantity(detail),
                    transferable: isDetailChecked(detail),

                }))

                .filter((line) => line.quantity > 0);

            if (!selectedDetails.length) {

                alert('Please set transfer quantity greater than zero on at least one approved detail row.');

                return;

            }

            viewTransferSavingHeaderIds.add(Number(headerId));

            renderFilteredViewPurchaseRequests();

            try {

                const res = await fetch('/api/admin/procurement/purchase-requests/transfer-to-po', {

                    method: 'POST',

                    headers: {

                        'Content-Type': 'application/json',

                    },

                    body: JSON.stringify({

                        requestId: Number(headerId),

                        requestNumber: String(header.requestNumber || ''),

                        transferLines: selectedDetails,

                    }),

                });

                const data = await readProcurementJson(res);

                if (!res.ok || !data.success) {

                    throw new Error(data.error || `Transfer failed (HTTP ${res.status})`);

                }

                const poNumbers = Array.isArray(data?.data?.poNumbers) ? data.data.poNumbers.filter(Boolean) : [];

                const poText = poNumbers.length ? poNumbers.join(', ') : (data?.data?.poNumber || '-');

                alert(`Transfer completed. Purchase Order(s): ${poText}`);

                invalidateViewDetailCache(headerId);

                loadViewPurchaseRequests(true);

            } catch (error) {

                if (!isProcurementAuthExpired(error)) alert(error.message || 'Transfer to Purchase Order failed.');

            } finally {

                viewTransferSavingHeaderIds.delete(Number(headerId));

                renderFilteredViewPurchaseRequests();

            }

        }

        function onTransferQuantityChange(headerId, detailId, rawValue) {

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));

            if (!header || !Array.isArray(header.details) || isCancelledPurchaseRequest(header)) {

                return;

            }

            const detail = header.details.find((row) => Number(row.id || 0) === Number(detailId));

            if (!detail) {

                return;

            }

            const maxTransfer = getDetailMaxTransferQuantity(detail);

            detail.transferQty = clampTransferQuantity(rawValue, maxTransfer);

            renderFilteredViewPurchaseRequests();

        }

        function getHeaderPendingUdfStatus(header) {

            const id = header ? String(header.id || '') : '';

            const pending = id ? viewHeaderStatusPendingChanges.get(id) : null;

            return pending ? normalizeUdfStatus(pending.udfStatus) : null;

        }

        function onHeaderUdfStatusChange(requestId, value) {

            if (document.body.classList.contains('procurement-hide-pr-approval-edits')) {

                return;

            }

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(requestId));

            if (!header) return;

            const saved = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);

            if (saved === 'APPROVED' || saved === 'CANCELLED') {

                renderFilteredViewPurchaseRequests();

                return;

            }

            queueHeaderUdfPendingFromSaved(requestId, value);

            updateViewApprovalButtonState();

            renderViewPurchaseRequestDetailPanel();

        }

        function onDetailApprovalChange(headerId, detailId, checked) {

            if (document.body.classList.contains('procurement-hide-pr-approval-edits')) {

                return;

            }

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));

            if (!header || !Array.isArray(header.details) || isCancelledPurchaseRequest(header)) {

                return;

            }

            const detail = header.details.find((row) => Number(row.id || 0) === Number(detailId));

            if (!detail) {

                return;

            }

            const original = toApprovalBool(detail._originalApproved);

            detail.udfPqApproved = Boolean(checked);
            detail.transferable = Boolean(checked);

            if (Boolean(checked) === original) {

                viewApprovalPendingChanges.delete(String(detailId));

            } else {

                viewApprovalPendingChanges.set(String(detailId), {

                    detailId: Number(detailId),

                    approved: Boolean(checked),

                    requestId: Number(headerId),

                });

            }

            updateViewApprovalButtonState();

            renderFilteredViewPurchaseRequests();

        }

        function viewPrExplicitUdfIsCancelled(headerId) {
            const sel = document.getElementById(`view-pr-detail-udf-${Number(headerId)}`);
            if (sel) {
                return normalizeUdfStatus(sel.value) === 'CANCELLED';
            }
            const pending = viewHeaderStatusPendingChanges.get(String(headerId));
            return !!(pending && normalizeUdfStatus(pending.udfStatus) === 'CANCELLED');
        }

        function onDetailApprovalToggleAll(headerId, checked) {
            if (document.body.classList.contains('procurement-hide-pr-approval-edits')) {
                return;
            }
            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));
            if (!header || !Array.isArray(header.details)) {
                return;
            }

            const nextChecked = Boolean(checked);
            header.details.forEach((detail) => {
                const detailId = Number(detail && detail.id ? detail.id : 0);
                if (!detailId) {
                    return;
                }
                const original = toApprovalBool(detail._originalApproved);
                detail.udfPqApproved = nextChecked;
                detail.transferable = nextChecked;
                if (nextChecked === original) {
                    viewApprovalPendingChanges.delete(String(detailId));
                } else {
                    viewApprovalPendingChanges.set(String(detailId), {
                        detailId,
                        approved: nextChecked,
                        requestId: Number(headerId),
                    });
                }
            });

            const selectable = header.details.filter((row) => Number(row && row.id ? row.id : 0) > 0);
            const hasChecked = selectable.some((row) => isDetailChecked(row));
            header.selectedLineCount = selectable.filter((row) => isDetailChecked(row)).length;
            header.lineCount = selectable.length;
            const savedUdf = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);
            // Only Pending auto-stages header → Approved; Awaiting keeps header UDF unchanged.
            if (savedUdf === 'PENDING' && !viewPrExplicitUdfIsCancelled(headerId)) {
                queueHeaderUdfPendingFromSaved(headerId, hasChecked ? 'APPROVED' : 'PENDING');
            }
            updateViewApprovalButtonState();
            renderViewPurchaseRequestDetailPanel();
            renderFilteredViewPurchaseRequests();
        }

        function onDetailApprovalChangeStageOnly(headerId, detailId, checked) {
            onDetailApprovalChange(headerId, detailId, checked);
            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));
            if (!header || !Array.isArray(header.details)) {
                return;
            }
            const savedUdf = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);
            const selectable = header.details.filter((row) => Number(row && row.id ? row.id : 0) > 0);
            const hasChecked = selectable.some((row) => isDetailChecked(row));
            header.selectedLineCount = selectable.filter((row) => isDetailChecked(row)).length;
            header.lineCount = selectable.length;
            // Stage only — Update button persists. Do not POST on checkbox click.
            if (savedUdf === 'PENDING' && !viewPrExplicitUdfIsCancelled(headerId)) {
                queueHeaderUdfPendingFromSaved(headerId, hasChecked ? 'APPROVED' : 'PENDING');
            }
            syncAllLineApprovalsBeforeHeaderApprove(headerId);
            updateViewApprovalButtonState();
            renderViewPurchaseRequestDetailPanel();
            renderFilteredViewPurchaseRequests();
        }

        async function onDetailApprovalChangeAutoHeader(headerId, detailId, checked) {
            onDetailApprovalChangeStageOnly(headerId, detailId, checked);
        }

        async function persistSingleDetailApprovalChange(headerId, detailId, checked) {
            const headerNum = Number(headerId || 0);
            const detailNum = Number(detailId || 0);
            if (!headerNum || !detailNum) {
                return;
            }
            try {
                const res = await fetch('/api/admin/procurement/purchase-requests/details/approval', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        changes: [{
                            detailId: detailNum,
                            approved: Boolean(checked),
                            requestId: headerNum,
                        }],
                    }),
                });
                const data = await readProcurementJson(res);
                if (!res.ok || !data.success) {
                    throw new Error(data.error || `Failed to save line approval (HTTP ${res.status})`);
                }

                const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === headerNum);
                if (header && Array.isArray(header.details)) {
                    const detail = header.details.find((row) => Number(row.id || 0) === detailNum);
                    if (detail) {
                        detail._originalApproved = Boolean(checked);
                        detail.udfPqApproved = Boolean(checked);
                        detail.transferable = Boolean(checked);
                    }
                }
                viewApprovalPendingChanges.delete(String(detailNum));
                updateViewApprovalButtonState();
            } catch (error) {
                console.warn('[View PR] Failed to auto-save line approval:', error);
            }
        }

        function syncAllLineApprovalsBeforeHeaderApprove(headerId) {
            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));
            if (!header || !Array.isArray(header.details)) {
                return;
            }
            const requestId = Number(header.id || headerId || 0);
            header.details.forEach((detail) => {
                const detailId = Number(detail && detail.id ? detail.id : 0);
                if (!detailId) return;
                const checked = isDetailChecked(detail);
                detail.udfPqApproved = checked;
                detail.transferable = checked;
                viewApprovalPendingChanges.set(String(detailId), {
                    detailId,
                    requestId,
                    approved: checked,
                });
            });
        }

        async function saveViewDetailApprovals() {
            if (document.body.classList.contains('procurement-hide-pr-approval-edits')) {
                return;
            }
            if (viewApprovalSaving || isCancelledPurchaseRequest(viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(viewSelectedHeaderId)))) {
                return;
            }

            try {
                const selectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;
                if (selectedId > 0) {
                    const sel = document.getElementById(`view-pr-detail-udf-${selectedId}`);
                    if (sel && typeof onHeaderUdfStatusChange === 'function') {
                        onHeaderUdfStatusChange(selectedId, sel.value);
                    }
                    // Always capture current checkbox state for the open PR.
                    syncAllLineApprovalsBeforeHeaderApprove(selectedId);
                    const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === selectedId);
                    const savedUdf = normalizeUdfStatus(header && (header._originalUdfStatus || header.udfStatus));
                    const hasChecked = !!(header && Array.isArray(header.details)
                        && header.details.some((row) => Number(row && row.id ? row.id : 0) > 0 && isDetailChecked(row)));
                    if (savedUdf === 'PENDING' && hasChecked && !viewPrExplicitUdfIsCancelled(selectedId)) {
                        queueHeaderUdfPendingFromSaved(selectedId, 'APPROVED');
                    }
                }
            } catch (e) { /* ignore */ }

            if (viewApprovalPendingChanges.size === 0 && viewHeaderStatusPendingChanges.size === 0) {
                alert('No changes to update. Select line items and/or change Status, then click Update.');
                return;
            }

            viewApprovalSaving = true;

            updateViewApprovalButtonState();

            try {
                let headerStatusSaveFailed = false;
                let bidInvitationResults = [];
                let headerStatusError = '';

                
                // When approving header, persist every line tick/untick so unchecked rows stay off.
                viewHeaderStatusPendingChanges.forEach((change) => {
                    if (normalizeUdfStatus(change.udfStatus) === 'APPROVED') {
                        syncAllLineApprovalsBeforeHeaderApprove(change.requestId);
                    }
                });

                if (viewApprovalPendingChanges.size > 0) {
                    const detailPayloadEarly = { changes: Array.from(viewApprovalPendingChanges.values()) };
                    const detailResEarly = await fetch('/api/admin/procurement/purchase-requests/details/approval', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(detailPayloadEarly),
                    });
                    const detailDataEarly = await readProcurementJson(detailResEarly);
                    if (!detailResEarly.ok || !detailDataEarly.success) {
                        throw new Error(detailDataEarly.error || `Failed to update approval details (HTTP ${detailResEarly.status})`);
                    }
                    viewApprovalPendingChanges.forEach((change) => {
                        const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(change.requestId));
                        if (!header || !Array.isArray(header.details)) return;
                        const detail = header.details.find((row) => Number(row.id || 0) === Number(change.detailId));
                        if (!detail) return;
                        detail._originalApproved = Boolean(change.approved);
                        detail.udfPqApproved = Boolean(change.approved);
                        detail.transferable = Boolean(change.approved);
                    });
                    viewApprovalPendingChanges.clear();
                }

if (viewHeaderStatusPendingChanges.size > 0) {

                    const headerPayload = {

                        changes: Array.from(viewHeaderStatusPendingChanges.values()),

                    };

                    const statusRes = await fetch('/api/admin/procurement/purchase-requests/header-status', {

                        method: 'POST',

                        headers: {

                            'Content-Type': 'application/json',

                        },

                        body: JSON.stringify(headerPayload),

                    });

                    const statusData = await readProcurementJson(statusRes);

                    try {
                        const payloadData = statusData && statusData.data;
                        if (payloadData && Array.isArray(payloadData.bidInvitationResults)) {
                            bidInvitationResults = payloadData.bidInvitationResults;
                        }
                        if (statusRes.ok && statusData.success && payloadData && Array.isArray(payloadData.changes)) {
                            payloadData.changes.forEach((applied) => {
                                const id = String(applied && applied.requestId || '');
                                const pending = id ? viewHeaderStatusPendingChanges.get(id) : null;
                                const docStatus = String(applied && applied.docStatus || '').trim().toUpperCase();
                                if (pending && docStatus) {
                                    pending.docStatus = docStatus;
                                }
                            });
                        }
                    } catch (e) { /* ignore */ }

                    if (!statusRes.ok || !statusData.success) {

                        const statusErr = statusData.error || `Failed to update header status (HTTP ${statusRes.status})`;
                        if (viewApprovalPendingChanges.size === 0) {
                            throw new Error(statusErr);
                        }
                        headerStatusSaveFailed = true;
                        headerStatusError = statusErr;

                    }

                }

                if (viewApprovalPendingChanges.size > 0) {

                    const detailPayload = {

                        changes: Array.from(viewApprovalPendingChanges.values()),

                    };

                    const res = await fetch('/api/admin/procurement/purchase-requests/details/approval', {

                        method: 'POST',

                        headers: {

                            'Content-Type': 'application/json',

                        },

                        body: JSON.stringify(detailPayload),

                    });

                    const data = await readProcurementJson(res);

                    if (!res.ok || !data.success) {

                        throw new Error(data.error || `Failed to update details (HTTP ${res.status})`);

                    }

                    viewApprovalPendingChanges.forEach((change) => {

                        const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(change.requestId));

                        if (!header || !Array.isArray(header.details)) return;

                        const detail = header.details.find((row) => Number(row.id || 0) === Number(change.detailId));

                        if (!detail) return;

                        detail._originalApproved = Boolean(change.approved);

                        detail.udfPqApproved = Boolean(change.approved);
                        detail.transferable = Boolean(change.approved);

                    });

                }

                if (!headerStatusSaveFailed) {
                    viewHeaderStatusPendingChanges.forEach((change) => {

                    const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(change.requestId));

                    if (!header) return;

                    header._originalUdfStatus = normalizeUdfStatus(change.udfStatus);

                    header.udfStatus = normalizeUdfStatus(change.udfStatus);

                    if (change.docStatus) {
                        header.status = change.docStatus;
                    }

                    delete header._pendingUdfStatus;

                    });
                }

                (() => {

                    const affectedIds = new Set([

                        ...Array.from(viewApprovalPendingChanges.values()).map((change) => Number(change.requestId || 0)),

                        ...Array.from(viewHeaderStatusPendingChanges.values()).map((change) => Number(change.requestId || 0)),

                    ]);

                    const approvedIdsForCache = viewPrHeadersMarkedApprovedForSave();
                    affectedIds.forEach((id) => {
                        if (!id) return;
                        const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === id);
                        const headerApproved = approvedIdsForCache.has(id)
                            || (header && normalizeUdfStatus(header._originalUdfStatus || header.udfStatus) === 'APPROVED');
                        if (headerApproved) {
                            invalidateViewDetailCache(id);
                            return;
                        }
                        if (header && Array.isArray(header.details)) {
                            syncViewDetailCacheFromRecord(header);
                        } else {
                            invalidateViewDetailCache(id);
                        }
                    });

                })();

                const keepSelectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;

                const approvedHeaderIdsForRefresh = viewPrHeadersMarkedApprovedForSave();

                const pendingHeaderIdsForRefresh = new Set(
                    Array.from(viewHeaderStatusPendingChanges.values())
                        .filter((c) => normalizeUdfStatus(c.udfStatus) === 'PENDING')
                        .map((c) => Number(c.requestId || 0))
                        .filter((id) => id > 0)
                );
                const cancelledHeaderIdsForRefresh = new Set(
                    Array.from(viewHeaderStatusPendingChanges.values())
                        .filter((c) => normalizeUdfStatus(c.udfStatus) === 'CANCELLED')
                        .map((c) => Number(c.requestId || 0))
                        .filter((id) => id > 0)
                );
                const awaitingHeaderIdsForRefresh = new Set(
                    Array.from(viewHeaderStatusPendingChanges.values())
                        .filter((c) => normalizeUdfStatus(c.udfStatus) === 'AWAITING')
                        .map((c) => Number(c.requestId || 0))
                        .filter((id) => id > 0)
                );
                if (!headerStatusSaveFailed && typeof bidInvitationResults !== 'undefined' && bidInvitationResults.length) {
                    const notes = bidInvitationResults.map((r) => {
                        if (!r) return '';
                        if (r.skipped && r.reason === 'already_invited') {
                            return `RFQ already invited (${r.inviteCount || 0}).`;
                        }
                        if (r.skipped && r.reason === 'no_suppliers') {
                            return 'No selected suppliers; RFQ not sent.';
                        }
                        if (r.reason === 'missing_portal_url') {
                            return 'Invites saved but SUPPLIER_PORTAL_BASE_URL is missing; emails not sent.';
                        }
                        if (r.skipped) {
                            return `RFQ skipped: ${r.reason || 'unknown'}`;
                        }
                        return `RFQ: ${r.inviteCount || 0} invite(s), ${r.emailsQueued || 0} email(s) queued.`;
                    }).filter(Boolean);
                    if (notes.length) {
                        alert(notes.join('\n'));
                    }
                }

                viewApprovalPendingChanges.clear();

                if (!headerStatusSaveFailed) {

                    viewHeaderStatusPendingChanges.clear();

                }

                viewBulkSelectedHeaderIds.clear();

                updateViewApprovalButtonState();

                                if (pendingHeaderIdsForRefresh && pendingHeaderIdsForRefresh.size) {
                    await finalizeViewPrAfterApprovalSave(keepSelectedId, { targetUdfStatus: 'PENDING' });
                } else if (approvedHeaderIdsForRefresh && approvedHeaderIdsForRefresh.size) {
                    activateViewPrApprovedTabAfterSave(approvedHeaderIdsForRefresh);
                    goToViewPrStatus('APPROVED', { reload: true });
                    await finalizeViewPrAfterApprovalSave(keepSelectedId, { targetUdfStatus: 'APPROVED' });
                } else if (cancelledHeaderIdsForRefresh && cancelledHeaderIdsForRefresh.size) {
                    await finalizeViewPrAfterApprovalSave(keepSelectedId, {
                        targetUdfStatus: 'CANCELLED',
                        fromDraftPanel: viewStatusFilters instanceof Set && viewStatusFilters.has('DRAFT'),
                    });
                } else if (awaitingHeaderIdsForRefresh && awaitingHeaderIdsForRefresh.size) {
                    await finalizeViewPrAfterApprovalSave(keepSelectedId, { targetUdfStatus: 'AWAITING' });
                } else {
                    await finalizeViewPrAfterApprovalSave(keepSelectedId, { targetUdfStatus: '' });
                }
                if (headerStatusSaveFailed) {
                    alert(`Line approvals saved, but header status update failed: ${headerStatusError || 'SQL API returned an error.'}`);
                }

            } catch (error) {

                if (!isProcurementAuthExpired(error)) alert(error.message || 'Failed to update approval details.');

            } finally {

                viewApprovalSaving = false;

                updateViewApprovalButtonState();

            }

        }

        /** SQTY / SUOMQTY per detail row for View PR (fallback when API only sends legacy QTY + basis). */

        function viewPrDetailSqtySuom(detail) {

            const basis = String(detail?.stockQtyUom || '').toUpperCase();

            let sq = Number(detail?.sqty != null ? detail.sqty : NaN);

            let su = Number(detail?.suomqty != null ? detail.suomqty : NaN);

            const q = Number(detail?.quantity || 0);

            if (!Number.isFinite(sq)) {

                sq = basis === 'SQTY' ? q : 0;

            }

            if (!Number.isFinite(su)) {

                su = basis === 'SUOMQTY' ? q : 0;

            }

            return { sqty: sq, suomqty: su };

        }

        
            function formatViewPrSupplierAddress(supplier) {
                if (!supplier || typeof supplier !== 'object') return '';
                const parts = [
                    supplier.address1, supplier.address2, supplier.address3, supplier.address4,
                    supplier.daddress1, supplier.daddress2, supplier.daddress3, supplier.daddress4,
                    supplier.city, supplier.state, supplier.postcode, supplier.country,
                ].map((v) => String(v || '').trim()).filter((v) => v && v.toUpperCase() !== 'N/A' && v !== '-');
                // de-dupe while preserving order
                const seen = new Set();
                const uniq = [];
                parts.forEach((p) => {
                    const k = p.toUpperCase();
                    if (seen.has(k)) return;
                    seen.add(k);
                    uniq.push(p);
                });
                return uniq.join(', ');
            }

        function viewPrUdfOption(value, label, picked) {
            const selected = picked === value ? ' selected' : '';
            return `<option value="${value}"${selected}>${label}</option>`;
        }

        function viewPrUdfStatusOptionsHtml(savedUdf, selectUdf, docStatus) {
            const saved = normalizeUdfStatus(savedUdf);
            const picked = normalizeUdfStatus(selectUdf);
            const doc = String(docStatus || '').trim().toUpperCase();
            if (saved === 'AWAITING') {
                const hidden = picked === 'AWAITING'
                    ? '<option value="AWAITING" selected hidden></option>'
                    : '';
                return [
                    hidden,
                    viewPrUdfOption('PENDING', 'Pending (Awaiting RFQ)', picked),
                    viewPrUdfOption('CANCELLED', 'Cancelled', picked),
                ].join('');
            }
            if (saved === 'PENDING') {
                return [
                    viewPrUdfOption('PENDING', 'Pending', picked),
                    viewPrUdfOption('APPROVED', 'Approved', picked),
                    viewPrUdfOption('CANCELLED', 'Cancelled', picked),
                ].join('');
            }
            if (doc === 'DRAFT' || saved === 'DRAFT') {
                const current = (picked === 'AWAITING' || picked === 'CANCELLED') ? picked : '';
                return [
                    viewPrUdfOption('', 'Draft', current),
                    viewPrUdfOption('AWAITING', 'Awaiting Approval', current),
                    viewPrUdfOption('CANCELLED', 'Cancelled', current),
                ].join('');
            }
            return [
                viewPrUdfOption('APPROVED', 'Approved', picked),
                viewPrUdfOption('CANCELLED', 'Cancelled', picked),
            ].join('');
        }

function buildViewPurchaseRequestDetailHtml(header) {

            const headerId = Number(header.id || 0);

            const details = Array.isArray(header.details) ? header.details : [];

            const isTransferring = viewTransferSavingHeaderIds.has(headerId);

            const canTransfer = isPurchaseRequestTransferReady(header);

            const transferTitle = getPurchaseRequestTransferTitle(header);

            const suppliers = Array.isArray(header._suppliers) && header._suppliers.length

                ? header._suppliers

                : [{ name: header.supplierName || header.supplierId || '-', email: header.supplierEmail || '' }];

            const supplierCodeList = suppliers
                .map((s) => String(s.code || s.supplierCode || s.supplierId || '').trim())
                .filter(Boolean);
            const requesterDisplay = supplierCodeList.length
                ? supplierCodeList.join(', ')
                : (String(header._requesterSupplierCodes || header.supplierId || '').trim()
                    || String(header.requesterId || header.requester || '').trim()
                    || '-');

            let supplierPrimary = String(header.supplierName || '').trim();

            if (!supplierPrimary && Array.isArray(header._suppliers) && header._suppliers.length) {

                const s0 = header._suppliers[0];

                supplierPrimary = String(s0.name || s0.companyname || s0.code || '').trim();

            }

            if (!supplierPrimary) {

                supplierPrimary = '-';

            }

            const savedUdfDisplay = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);
            const udfLocked = ['APPROVED', 'CANCELLED'].includes(normalizeUdfStatus(header._originalUdfStatus || header.udfStatus));
            const selectUdfRaw = normalizeUdfStatus(getHeaderPendingUdfStatus(header) || savedUdfDisplay);
            const selectUdf = (savedUdfDisplay === 'AWAITING' && !['AWAITING', 'PENDING', 'CANCELLED'].includes(selectUdfRaw))
                ? 'AWAITING'
                : selectUdfRaw;
            const hideApprovalEdits = document.body.classList.contains('procurement-hide-pr-approval-edits');
            const canEditLines = !hideApprovalEdits && savedUdfDisplay !== 'CANCELLED' && canEditPrLineSelection(header);

            const supplierRowsHtml = suppliers.map((supplier, idx) => {

                const name = String(supplier.name || supplier.companyname || supplier.code || '-').trim() || '-';

                const label = suppliers.length > 1 ? `Supplier ${idx + 1}` : 'Supplier';

                return `

                    <div class="view-pr-detail-supplier-row">

                        <strong>${escapeHtml(label)}</strong>

                        <span>${escapeHtml(name)}</span>
                        ${(() => {
                            const addr = formatViewPrSupplierAddress(supplier);
                            return addr ? `<div class="view-pr-detail-supplier-address muted">${escapeHtml(addr)}</div>` : '';
                        })()}

                    </div>

                `;

            }).join('');

            const selectableDetailCount = details.filter((detail) => Number(detail.id || 0) > 0).length;
            const selectedDetailCount = details.filter((detail) => Number(detail.id || 0) > 0 && isDetailChecked(detail)).length;
            const allDetailsSelected = selectableDetailCount > 0 && selectedDetailCount === selectableDetailCount;

            const lineBulkHint = savedUdfDisplay === 'APPROVED'
                ? 'Selected lines can be transferred'
                : savedUdfDisplay === 'PENDING'
                    ? 'Update to save · selected lines stage Approved'
                    : 'Update to save selected lines';

            const detailRows = details.length

                ? details.map((detail, idx) => {

                const { sqty: rowSqty, suomqty: rowSuom } = viewPrDetailSqtySuom(detail);
                const rowSelected = isDetailChecked(detail);
                const qtyControlHtml = savedUdfDisplay === 'CANCELLED'
                    ? `<span>${formatStockCardNumber(getDetailTransferQuantity(detail))}</span>`
                    : `<input type="number" class="view-pr-transfer-qty-input view-pr-transfer-qty-input--inline" min="0" max="${escapeHtml(String(getDetailMaxTransferQuantity(detail)))}" step="0.01" value="${escapeHtml(String(getDetailTransferQuantity(detail)))}" ${isDetailChecked(detail) && detail.id ? '' : 'disabled'} title="${escapeHtml(isDetailChecked(detail) ? `Enter transfer quantity up to ${formatStockCardNumber(getDetailMaxTransferQuantity(detail))}; total quantity is ${formatStockCardNumber(detail.quantity || 0)}.` : 'Tick approval first before setting transfer quantity.')}" onchange="onTransferQuantityChange(${headerId}, ${Number(detail.id || 0)}, this.value)" />`;

                return `

            <tr class="view-pr-detail-line${rowSelected ? ' is-selected' : ''}">

                <td class="col-approved view-pr-approved-cell">

                    <input

                        type="checkbox"

                        aria-label="Selected"

                        ${(!detail.id || !canEditLines) ? 'disabled' : ''}

                        ${isDetailChecked(detail) ? 'checked' : ''}

                        onchange="onDetailApprovalChangeStageOnly(${headerId}, ${Number(detail.id || 0)}, this.checked)"

                    />

                </td>

                <td class="col-line">${escapeHtml(detail.seq || (idx + 1))}</td>

                <td class="col-item-name">${escapeHtml(detail.itemCode || detail.itemName || '-')}</td>

                <td class="col-location col-batch">${escapeHtml(detail.locationCode || '-')}</td>

                <td class="view-pr-num col-sqty">${formatStockCardNumber(rowSqty)}</td>

                <td class="view-pr-num col-suomqty">${formatStockCardNumber(rowSuom)}</td>

                <td class="col-delivery-date">${formatPrDate(detail.deliveryDate || detail.requiredDate || '-')}</td>

                <td class="view-pr-num col-qty view-pr-transfer-ratio-cell">

                    ${qtyControlHtml}

                    <span class="view-pr-transfer-ratio-sep">/</span>

                    <span class="view-pr-transfer-ratio-total">${formatStockCardNumber(detail.quantity || 0)}</span>

                </td>

                <td class="view-pr-num col-unit-price${detail.isFinalChosenPrice ? ' is-approved-bid-price' : ''}">

                    ${formatMoney(detail.unitPrice || 0)}

                </td>

                <td class="view-pr-num col-amount">${formatMoney(detail.amount || 0)}</td>

            </tr>

        `;

            }).join('')

                : `<tr><td colspan="10" class="view-pr-detail-table-empty">No line items for this request.</td></tr>`;

            return `

            <div class="view-pr-detail-unified">

                <div class="view-pr-detail-panel-head view-pr-detail-panel-head--rich">

                    <div class="view-pr-detail-head-primary">

                        <div class="view-pr-detail-head-titles">

                            <h3 class="view-pr-detail-panel-title">${escapeHtml(header.requestNumber || '-')}</h3>

                        </div>

                    </div>

                    <div class="view-pr-detail-meta-strip">

                        <dl class="view-pr-detail-meta-dl">

                            <div class="view-pr-detail-meta-item">

                                <dt>Date</dt>

                                <dd>${formatPrDate(header.requestDate || header.requiredDate || '-')}</dd>

                            </div>

                            <div class="view-pr-detail-meta-item">

                                <dt>Requester</dt>

                                <dd>${requesterDisplay === '-' ? '<span class="view-pr-detail-meta-muted">Not specified</span>' : escapeHtml(requesterDisplay)}</dd>

                            </div>

                            <div class="view-pr-detail-meta-item view-pr-detail-meta-item--supplier">

                                <dt>Supplier</dt>

                                <dd>

                                    <div class="view-pr-detail-suppliers view-pr-detail-suppliers--header">${supplierRowsHtml}</div>

                                </dd>

                            </div>

                        </dl>

                    </div>

                </div>

                <div class="view-pr-detail-actions view-pr-detail-actions--toolbar">

                    <div class="view-pr-detail-summary">

                        Selected transfer qty: <strong>${formatStockCardNumber(getSelectedTransferQuantityTotal(header))}</strong>

                    </div>

                    ${savedUdfDisplay === 'CANCELLED' ? '' : `<button

                        type="button"

                        class="view-pr-transfer-btn ${(canTransfer && !isTransferring) ? '' : 'is-disabled'}"

                        onclick="onTransferPurchaseRequest(${headerId})"

                        ${canTransfer ? '' : 'disabled'}

                        title="${escapeHtml(transferTitle)}"

                    >${isTransferring ? 'Transferring...' : (canTransfer ? 'Transfer to Purchase Order' : 'Awaiting Approval')}</button>`}

                </div>

                <div class="view-pr-detail-wrap view-pr-detail-wrap--unified">

                    ${canEditLines && selectableDetailCount ? `
                    <div class="view-pr-line-bulk-bar" role="group" aria-label="Bulk line selection">
                        <label class="view-pr-line-bulk-bar__select">
                            <input
                                type="checkbox"
                                class="view-pr-line-bulk-master"
                                aria-label="Select all lines"
                                ${allDetailsSelected ? 'checked' : ''}
                                onchange="onDetailApprovalToggleAll(${headerId}, this.checked)"
                            />
                            <span class="view-pr-line-bulk-bar__label">Select all lines</span>
                            <span class="view-pr-line-bulk-bar__count">${selectedDetailCount} of ${selectableDetailCount} selected</span>
                        </label>
                        <span class="view-pr-line-bulk-bar__hint">${escapeHtml(lineBulkHint)}</span>
                    </div>` : ''}

                    <table class="view-pr-detail-table">

                        <colgroup>

                            <col class="col-approved" />

                            <col class="col-line" />

                            <col class="col-item-name" />

                            <col class="col-location" />

                            <col class="col-sqty" />

                            <col class="col-suomqty" />

                            <col class="col-delivery-date" />

                            <col class="col-qty" />

                            <col class="col-unit-price" />

                            <col class="col-amount" />

                        </colgroup>

                        <thead>

                            <tr>

                                <th class="col-approved">Select</th>

                                <th class="col-line">#</th>

                                <th class="col-item-name">Item code</th>

                                <th class="col-location col-batch">Location</th>

                                <th class="view-pr-num col-sqty">SQTY</th>

                                <th class="view-pr-num col-suomqty">SUOMQTY</th>

                                <th class="col-delivery-date">Delivery</th>

                                <th class="view-pr-num col-qty">Qty (x / total)</th>

                                <th class="view-pr-num col-unit-price">Unit</th>

                                <th class="view-pr-num col-amount">Amt</th>

                            </tr>

                        </thead>

                        <tbody>

                            ${detailRows}

                        </tbody>

                    </table>

                    <div class="view-pr-detail-total-row" aria-label="Purchase request total">
                        <span class="view-pr-detail-total-row__label">Total</span>
                        <span class="view-pr-detail-total-row__value">RM ${formatMoney(header.totalAmount || 0)}</span>
                    </div>

                    ${hideApprovalEdits || savedUdfDisplay === 'CANCELLED' ? '' : `
                    <div class="view-pr-detail-lines-footer">
                        <div class="view-pr-detail-status-actions">
                            <label class="view-pr-detail-status-label" for="view-pr-detail-udf-${headerId}">Status</label>
                            <select id="view-pr-detail-udf-${headerId}" class="view-pr-udf-status view-pr-detail-udf-status" onchange="onHeaderUdfStatusChange(${headerId}, this.value)" title="Approval status" ${udfLocked && savedUdfDisplay === 'APPROVED' ? 'disabled' : ''}>
                                ${viewPrUdfStatusOptionsHtml(savedUdfDisplay, selectUdf, header.status)}
                            </select>
                            <button type="button" class="view-pr-refresh-btn view-pr-detail-update-btn" onclick="saveViewDetailApprovals()">Update</button>
                        </div>
                    </div>`}

                </div>

            </div>

        `;

        }

        function renderViewPurchaseRequestDetailPanel() {

            const panel = document.getElementById('view-pr-detail-panel');

            if (!panel) {

                return;

            }

            const selectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : null;

            if (!selectedId) {
                document.body.classList.remove('view-pr-detail-drawer-open');
                const _backdrop = document.getElementById('view-pr-detail-drawer-backdrop');
                if (_backdrop) _backdrop.hidden = true;
                panel.innerHTML = '<div class="view-pr-detail-panel-empty view-pr-detail-panel-empty--hero"><p><strong>No purchase request selected</strong></p><p class="view-pr-detail-empty-hint">Tap a purchase request card to open details.</p></div>';

                return;

            }

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === selectedId);

            if (!header) {

                panel.innerHTML = '<div class="view-pr-detail-panel-empty">Purchase request not found.</div>';

                return;

            }

            if (viewLoadingDetailIds.has(selectedId)) {

                panel.innerHTML = '<div class="view-pr-detail-empty view-pr-detail-empty--loading">Loading line items…</div>';

                return;

            }

            if (!Array.isArray(header.details)) {
                const missingId = Number(header.id || 0);
                if (viewLoadingDetailIds.has(missingId) || viewDetailFetchPromises.has(missingId)) {

                panel.innerHTML = '<div class="view-pr-detail-empty view-pr-detail-empty--loading">Loading line items…</div>';
                } else {
                    const detailError = String(header._detailError || '').trim();
                    const msg = detailError ? `Failed to load line items: ${escapeHtml(detailError)}` : 'Line items are not loaded yet.';
                    panel.innerHTML = `<div class="view-pr-detail-empty">${msg} <button type="button" class="view-pr-refresh-btn" onclick="retryViewPurchaseRequestDetails(${missingId})">Retry</button></div>`;
                }

                return;

            }

            try {
                panel.innerHTML = buildViewPurchaseRequestDetailHtml(header);
            } catch (error) {
                console.error('Failed to render request detail panel:', error);
                const renderError = error && error.message ? String(error.message) : 'Unknown render error';
                header._detailError = renderError;
                panel.innerHTML = `<div class="view-pr-detail-empty">Failed to render line items: ${escapeHtml(renderError)} <button type="button" class="view-pr-refresh-btn" onclick="retryViewPurchaseRequestDetails(${Number(header.id || 0)})">Retry</button></div>`;
            }

        }

        function clearViewPrListDynamicNodes() {

            const pane = document.getElementById('view-pr-list');

            if (!pane) {

                return;

            }

            while (pane.firstChild) {

                pane.removeChild(pane.firstChild);

            }

        }

        function insertBeforeViewPrLoadMore(htmlString) {

            const pane = document.getElementById('view-pr-list');

            if (!pane) {

                return;

            }

            const trimmed = String(htmlString || '').trim();

            if (!trimmed) {

                return;

            }

            const tpl = document.createElement('template');

            tpl.innerHTML = trimmed;

            while (tpl.content.firstChild) {

                pane.appendChild(tpl.content.firstChild);

            }

        }

        function isViewPrPhoneLayout() {
            try {
                return window.matchMedia && window.matchMedia('(max-width: 900px)').matches;
            } catch (e) {
                return window.innerWidth <= 900;
            }
        }

        function openViewPrDetailDrawer() {
            if (!isViewPrPhoneLayout()) {
                document.body.classList.remove('view-pr-detail-drawer-open');
                const backdrop = document.getElementById('view-pr-detail-drawer-backdrop');
                if (backdrop) backdrop.hidden = true;
                return;
            }
            document.body.classList.add('view-pr-detail-drawer-open');
            const backdrop = document.getElementById('view-pr-detail-drawer-backdrop');
            if (backdrop) backdrop.hidden = false;
            const panel = document.getElementById('view-pr-items-panel');
            if (panel) {
                try { panel.scrollTop = 0; } catch (e) {}
            }
        }

        function closeViewPrDetailDrawer() {
            document.body.classList.remove('view-pr-detail-drawer-open');
            const backdrop = document.getElementById('view-pr-detail-drawer-backdrop');
            if (backdrop) backdrop.hidden = true;
            if (viewSelectedHeaderId != null) {
                viewSelectedHeaderId = null;
                try { renderFilteredViewPurchaseRequests(); } catch (e) {}
                try { syncViewPrToUrl(); } catch (e) {}
            }
        }

        function onViewPrCardActivate(event, headerId) {

            if (event && event.target && event.target.closest && event.target.closest('button, select, input, label, .pr-view-pr-row__bulk')) {

                return;

            }

            selectViewPurchaseRequest(headerId);

        }

        function onViewPrCardKeydown(event, headerId) {

            if (!event || event.target !== event.currentTarget) {

                return;

            }

            if (event.key === 'Enter' || event.key === ' ') {

                event.preventDefault();

                selectViewPurchaseRequest(headerId);

            }

        }

        function getViewPrEmptyListMessage() {
            const searchText = String(viewPrSearchText || '').trim();
            const filters = viewStatusFilters instanceof Set ? viewStatusFilters : new Set(['PENDING']);
            const active = VIEW_STATUS_FILTER_OPTIONS.filter((s) => filters.has(s));
            if (active.length === 1) {
                const label = VIEW_PR_TAB_LABELS[active[0]] || active[0];
                let msg = `No purchase requests under "${label}"`;
                if (searchText) {
                    msg += ` matching "${searchText}"`;
                }
                return `${msg}.`;
            }
            if (active.length > 1) {
                const quoted = active.map((s) => `"${VIEW_PR_TAB_LABELS[s] || s}"`).join(', ');
                let msg = `No purchase requests under ${quoted}`;
                if (searchText) {
                    msg += ` matching "${searchText}"`;
                }
                return `${msg}.`;
            }
            if (searchText) {
                return `No purchase requests matching "${searchText}".`;
            }
            return 'No purchase requests.';
        }

        function renderViewPurchaseRequests(rows) {

            const list = document.getElementById('view-pr-list');

            if (!list) {

                return;

            }

            list.style.maxHeight = '';

            clearViewPrListDynamicNodes();

            if (!Array.isArray(rows) || !rows.length) {

                insertBeforeViewPrLoadMore(

                    `<div class="view-pr-empty pr-view-empty--cards">${escapeHtml(getViewPrEmptyListMessage())}</div>`

                );

                return;

            }

            const cardParts = [];

            rows.forEach((header) => {

                const headerId = Number(header.id || 0);

                const prStatus = String(header.status || 'DRAFT').toUpperCase();

                const savedUdf = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);

                const pendingUdf = getHeaderPendingUdfStatus(header);

                const udf = savedUdf;

                const canEditDraft = prStatus === 'DRAFT' && udf !== 'CANCELLED';

                const isSelected = viewSelectedHeaderId != null && Number(viewSelectedHeaderId) === headerId;

                const borderColor = udf === 'CANCELLED' ? '#a65c5c' : (udf === 'APPROVED' ? '#2d6a4f' : '#b0892f');

                const badgeColor = borderColor;

                const onAwaitingTab = viewStatusFilters instanceof Set
                    && viewStatusFilters.size === 1
                    && viewStatusFilters.has('AWAITING');

                const pendingStatusHtml = !onAwaitingTab && pendingUdf && pendingUdf !== 'CANCELLED'

                    ? `<span class="view-pr-pending-status" title="Pending status change. Press Update to save.">→ ${escapeHtml(formatUdfStatusLabel(pendingUdf) || pendingUdf)}</span>`

                    : '';

                const editButtonHtml = canEditDraft

                    ? `<button type="button" class="edit-button view-pr-edit-inline-btn" onclick="openPurchaseRequestEdit(${headerId});" title="Edit draft purchase request">Edit</button>`

                    : '';

                
                let cardSelectedCount = (header.selectedLineCount == null || header.selectedLineCount === '') ? null : Number(header.selectedLineCount);
                let cardLineCount = (header.lineCount == null || header.lineCount === '') ? null : Number(header.lineCount);
                if (Array.isArray(header.details) && header.details.length) {
                    const selectable = header.details.filter((d) => Number(d && d.id ? d.id : 0) > 0);
                    cardLineCount = selectable.length;
                    cardSelectedCount = selectable.filter((d) => isDetailChecked(d)).length;
                    header.selectedLineCount = cardSelectedCount;
                    header.lineCount = cardLineCount;
                }
                const selectionCardHtml = buildViewPrSelectionBadgeHtml(cardSelectedCount, cardLineCount);

                const bulkMode = isViewPendingBulkSelectMode() && !document.body.classList.contains('procurement-hide-pr-approval-edits');

                const bulkSlot = bulkMode

                    ? `<span class="pr-view-pr-row__bulk" onclick="event.stopPropagation()">

                        <label class="pr-view-pr-row__bulk-label" title="Select for bulk approval">

                            <input

                                type="checkbox"

                                aria-label="Select purchase request for bulk approval"

                                ${viewBulkSelectedHeaderIds.has(headerId) ? 'checked' : ''}

                                onclick="event.stopPropagation()"

                                onchange="onViewPrBulkCardCheckboxChange(event, ${headerId})"

                            />

                        </label>

                    </span>`

                    : '';

                cardParts.push(`

            <div class="pr-view-pr-row${isSelected ? ' is-selected' : ''}" data-header-id="${headerId}" style="--pr-card-accent: ${borderColor}; --pr-card-badge: ${badgeColor};" role="button" tabindex="0" onclick="onViewPrCardActivate(event, ${headerId})" onkeydown="onViewPrCardKeydown(event, ${headerId})">

                <span class="pr-view-pr-row__code">${bulkSlot}${escapeHtml(header.requestNumber || '-')}</span>

                <span class="pr-view-pr-row__date">${formatPrDate(header.requestDate || '-')}</span>

                <span class="pr-view-pr-row__selected">

                    ${pendingStatusHtml}

                    ${selectionCardHtml}

                    ${editButtonHtml}

                </span>

                <span class="pr-view-pr-row__amount"><span class="pr-view-amount-pill" style="background: ${badgeColor};">RM ${formatMoney(header.totalAmount || 0)}</span></span>

            </div>

        `);

            });

            insertBeforeViewPrLoadMore(cardParts.join(''));

        }

        function selectViewPurchaseRequest(headerId, options) {
            const opts = options || {};

            if (!headerId) {

                return;

            }

            const id = Number(headerId);

            const record = viewPurchaseRequests.find((row) => Number(row.id || 0) === id);

            if (!record) {

                return;

            }

            if (viewSelectedHeaderId != null && Number(viewSelectedHeaderId) === id) {
                viewSelectedHeaderId = null;
                renderFilteredViewPurchaseRequests();
                if (!opts.fromUrl) {
                    syncViewPrToUrl();
                }
                if (isViewPrPhoneLayout()) {
                    document.body.classList.remove('view-pr-detail-drawer-open');
                    const _bd = document.getElementById('view-pr-detail-drawer-backdrop');
                    if (_bd) _bd.hidden = true;
                }
                return;
            }
            viewSelectedHeaderId = id;
            openViewPrDetailDrawer();

            const cached = viewDetailCache.get(id);

            if ((!Array.isArray(record.details) || !record.details.length) && shouldUseViewDetailCache(record, cached)) {
                hydrateViewPurchaseRequestDetails(record, {
                    details: Array.isArray(cached.details) ? cached.details : [],
                    totalAmount: cached.totalAmount,
                    suppliers: Array.isArray(cached.suppliers) ? cached.suppliers : [],
                });
            }

            if (Array.isArray(record.details) && record.details.length) {

                renderFilteredViewPurchaseRequests();
                if (!opts.fromUrl) {
                    syncViewPrToUrl();
                }

                return;

            }

            viewLoadingDetailIds.add(id);

            renderFilteredViewPurchaseRequests();
            if (!opts.fromUrl) {
                syncViewPrToUrl();
            }

            fetchViewPurchaseRequestDetail(record)

                .catch((error) => {

                    if (isProcurementAuthExpired(error)) {
                        return;
                    }
                    console.error('Failed to load request detail:', error);
                    record._detailError = error && error.message ? String(error.message) : 'Failed to load detail rows';

                    if (!Array.isArray(record.details)) {
                        record.details = [];
                    }

                })

                .finally(() => {

                    viewLoadingDetailIds.delete(id);

                    renderFilteredViewPurchaseRequests();

                });

        }

        function narrowViewPrSuppliersForApproved(header, suppliers) {
            const rows = Array.isArray(suppliers) ? suppliers : [];
            if (!rows.length) return rows;
            const udf = normalizeUdfStatus(header?._originalUdfStatus || header?.udfStatus);
            if (udf !== 'APPROVED') return rows;
            const awardedCodes = String(header?.supplierId || '')
                .split(',')
                .map((s) => s.trim())
                .filter((c) => c && c !== '----' && c !== '-');
            if (!awardedCodes.length) return rows;
            const wanted = new Set(awardedCodes.map((c) => c.toUpperCase()));
            const matched = rows.filter((s) => {
                const code = String(s.code || s.supplierCode || s.supplierId || '').trim().toUpperCase();
                return code && wanted.has(code);
            });
            return matched.length ? matched : rows;
        }

        function hydrateViewPurchaseRequestDetails(record, payload) {

            record._detailError = '';
            record.details = Array.isArray(payload.details) ? payload.details : [];

            record._suppliers = Array.isArray(payload.suppliers) ? payload.suppliers : [];

            record._suppliers = narrowViewPrSuppliersForApproved(record, record._suppliers);

            if (record._suppliers.length) {

                const supplierNames = record._suppliers

                    .map((s) => String(s.name || s.companyname || s.code || '').trim())

                    .filter(Boolean);

                const supplierEmails = record._suppliers

                    .map((s) => String(s.email || s.udf_email || '').trim())

                    .filter(Boolean);

                const supplierCodes = record._suppliers
                    .map((s) => String(s.code || s.supplierCode || s.supplierId || '').trim())
                    .filter(Boolean);
                if (supplierCodes.length) {
                    record._requesterSupplierCodes = supplierCodes.join(', ');
                }

                if (supplierNames.length) {

                    record.supplierName = supplierNames.join(', ');

                }

                if (supplierEmails.length) {

                    record.supplierEmail = supplierEmails.join(', ');

                }

            }

            const resolvedTotal = Number(payload.totalAmount);

            if (Number.isFinite(resolvedTotal)) {

                record.totalAmount = resolvedTotal;

            } else {

                record.totalAmount = record.details.reduce((sum, row) => {

                    const amount = Number(row && row.amount);

                    return sum + (Number.isFinite(amount) ? amount : 0);

                }, 0);

            }

            record.details.forEach((detail) => {

                detail._originalApproved = isDetailChecked(detail);

                detail.transferQty = detail._originalApproved

                    ? clampTransferQuantity(detail.remainingQty, getDetailMaxTransferQuantity(detail))

                    : 0;

            });

            viewDetailCache.set(Number(record.id || 0), {

                at: Date.now(),

                details: record.details,

                totalAmount: record.totalAmount,

                suppliers: record._suppliers,

            });

            return record;

        }

        function fetchWithFallback(primaryUrl, fallbackUrl, signal, requestId) {
            const fetchJson = (url) => fetch(url, { signal }).then((res) => readProcurementJson(res));

            return fetchJson(primaryUrl).then((payload) => {
                if (payload && payload.success) return payload;
                const firstError = payload && payload.error ? String(payload.error) : 'Failed to load detail rows';
                return fetchJson(fallbackUrl).then((fallbackPayload) => {
                    if (fallbackPayload && fallbackPayload.success) {
                        console.warn(`[VIEW PR] detail fallback endpoint used for request_id=${requestId}: ${firstError}`);
                        return fallbackPayload;
                    }
                    const fallbackError = fallbackPayload && fallbackPayload.error ? String(fallbackPayload.error) : firstError;
                    throw new Error(fallbackError || 'Failed to load detail rows');
                });
            });
        }

        function retryViewPurchaseRequestDetails(headerId) {
            const id = Number(headerId || viewSelectedHeaderId || 0);
            if (!id) return;
            const record = viewPurchaseRequests.find((row) => Number(row.id || 0) === id);
            if (!record) return;

            viewLoadingDetailIds.add(id);
            renderFilteredViewPurchaseRequests();
            fetchViewPurchaseRequestDetail(record, true)
                .catch((error) => {
                    if (isProcurementAuthExpired(error)) {
                        return;
                    }
                    console.error('Retry failed to load request detail:', error);
                    record._detailError = error && error.message ? String(error.message) : 'Failed to load detail rows';
                    if (!Array.isArray(record.details)) {
                        record.details = [];
                    }
                })
                .finally(() => {
                    viewLoadingDetailIds.delete(id);
                    renderFilteredViewPurchaseRequests();
                });
        }

        function shouldUseViewDetailCache(header, cached) {
            if (!cached || Date.now() - Number(cached.at || 0) > VIEW_DETAIL_CACHE_TTL_MS) {
                return false;
            }
            const details = Array.isArray(cached.details) ? cached.details : [];
            if (!details.length) {
                return false;
            }
            const headerStatus = normalizeUdfStatus(header?._originalUdfStatus || header?.udfStatus);
            if (headerStatus === 'APPROVED') {
                const hasTransferableLine = details.some((detail) => isDetailChecked(detail));
                if (!hasTransferableLine) {
                    return false;
                }
            }
            return true;
        }

        function invalidateViewDetailCache(headerId) {
            const id = Number(headerId || 0);
            if (!id) {
                return;
            }
            viewDetailCache.delete(id);
            try {
                const controller = viewDetailFetchControllers.get(id);
                if (controller) {
                    controller.abort();
                }
            } catch (e) { /* no-op */ }
            viewDetailFetchControllers.delete(id);
            viewDetailFetchPromises.delete(id);
            viewDetailFetchStartedAtMs.delete(id);
            const record = viewPurchaseRequests.find((row) => Number(row.id || 0) === id);
            if (record) {
                record.details = null;
                record._detailError = '';
            }
        }

        function syncViewDetailCacheFromRecord(record) {
            const id = Number(record?.id || 0);
            if (!id || !Array.isArray(record.details)) {
                return;
            }
            viewDetailCache.set(id, {
                at: Date.now(),
                details: record.details,
                totalAmount: record.totalAmount,
                suppliers: record._suppliers,
            });
        }

        function refreshSelectedViewPurchaseRequestDetail(forceRefresh) {
            const selectedId = viewSelectedHeaderId != null ? Number(viewSelectedHeaderId) : 0;
            if (!selectedId) {
                return Promise.resolve();
            }
            const record = viewPurchaseRequests.find((row) => Number(row.id || 0) === selectedId);
            if (!record) {
                return Promise.resolve();
            }
            if (forceRefresh) {
                invalidateViewDetailCache(selectedId);
            }
            viewLoadingDetailIds.add(selectedId);
            renderFilteredViewPurchaseRequests();
            return fetchViewPurchaseRequestDetail(record, Boolean(forceRefresh))
                .catch((error) => {
                    if (isProcurementAuthExpired(error)) {
                        return;
                    }
                    console.warn('[View PR] Failed to refresh selected detail:', error);
                    record._detailError = error && error.message ? String(error.message) : 'Failed to load detail rows';
                })
                .finally(() => {
                    viewLoadingDetailIds.delete(selectedId);
                    renderFilteredViewPurchaseRequests();
                });
        }

        function fetchViewPurchaseRequestDetail(record, forceRefresh) {

            const id = Number(record && record.id);

            if (!id) {

                return Promise.reject(new Error('Invalid purchase request id'));

            }

            const cached = viewDetailCache.get(id);

            if (!forceRefresh && shouldUseViewDetailCache(record, cached)) {

                return Promise.resolve(hydrateViewPurchaseRequestDetails(record, cached));

            }

            if (!forceRefresh && viewDetailFetchPromises.has(id)) {

                const startedAtMs = Number(viewDetailFetchStartedAtMs.get(id) || 0);
                const requestAgeMs = Date.now() - startedAtMs;
                if (startedAtMs > 0 && requestAgeMs > 12000) {
                    const staleController = viewDetailFetchControllers.get(id);
                    if (staleController) {
                        try { staleController.abort(); } catch (e) { /* no-op */ }
                    }
                    viewDetailFetchControllers.delete(id);
                    viewDetailFetchPromises.delete(id);
                    viewDetailFetchStartedAtMs.delete(id);
                } else {
                    return viewDetailFetchPromises.get(id);
                }

            }

            try {

                const prevController = viewDetailFetchControllers.get(id);

                if (prevController) prevController.abort();

            } catch (e) {

                // no-op

            }

            const requestNo = encodeURIComponent(String(record.requestNumber || ''));

            const controller = new AbortController();
            const detailFetchTimeoutId = window.setTimeout(() => controller.abort(), 30000);

            viewDetailFetchControllers.set(id, controller);

            const startedAt = performance.now();

            const fetchPromise = fetchWithFallback(
                `/api/admin/procurement/purchase-requests/details?request_id=${id}&request_no=${requestNo}`,
                `/api/admin/procurement/purchase-requests/${id}`,
                controller.signal,
                id
            ).then((payload) => {
                const elapsed = Math.round(performance.now() - startedAt);
                console.log(`[VIEW PR PERF] detail request_id=${id} loaded in ${elapsed}ms`);
                return hydrateViewPurchaseRequestDetails(record, payload);
            })

                .finally(() => {
                    window.clearTimeout(detailFetchTimeoutId);

                    if (viewDetailFetchControllers.get(id) === controller) {

                        viewDetailFetchControllers.delete(id);

                    }

                    if (viewDetailFetchPromises.get(id) === fetchPromise) {

                        viewDetailFetchPromises.delete(id);
                        viewDetailFetchStartedAtMs.delete(id);

                    }

                });

            viewDetailFetchStartedAtMs.set(id, Date.now());
            viewDetailFetchPromises.set(id, fetchPromise);

            return fetchPromise;

        }

        function updateViewPrListPerfBanner(clientMs, perf, pageRows, loadedCount, totalCount, append) {

            const el = document.getElementById('view-pr-list-perf');

            if (!el) return;

            el.hidden = true;

            const p = perf && typeof perf === 'object' ? perf : {};

            const srv = Number(p.totalMs);

            const upstream = Number(p.upstreamMs);

            const sup = Number(p.supplierMs);

            const supEnrich = Number(p.supplierEnrichMs);

            const qty = Number(p.qtyMs);

            const hadQty = Boolean(p.includeQty);

            const parts = [];

            parts.push(`Fetch ${Math.round(clientMs)} ms (browser round-trip)`);

            if (Number.isFinite(srv)) {

                parts.push(`server ${srv} ms`);

            }

            if (Number.isFinite(upstream)) {

                parts.push(`SQL API ${upstream} ms`);

            }

            const api = p.sqlApi && typeof p.sqlApi === 'object' ? p.sqlApi : {};

            if (p.cacheHit) {

                const age = Number(p.cacheAgeMs);

                parts.push(Number.isFinite(age) ? `cache hit age ${Math.round(age)} ms` : 'cache hit');

            }

            if (Number.isFinite(Number(api.dataQueryMs))) {

                parts.push(`FB data ${Number(api.dataQueryMs)} ms`);

            }

            if (Number.isFinite(Number(api.countQueryMs)) && Number(api.countQueryMs) > 0.05) {

                parts.push(`FB count ${Number(api.countQueryMs)} ms`);

            }

            if (api.skippedFullTableCount) {

                parts.push('no full-table COUNT');

            }

            const rmap = Number(p.recordsMapMs);

            if (Number.isFinite(rmap) && rmap > 0.5) {

                parts.push(`Flask map ${rmap} ms`);

            }

            if (Number.isFinite(sup)) {

                parts.push(`supplier map ${sup} ms`);
            }

            if (Number.isFinite(supEnrich) && supEnrich > 0.05) {
                parts.push(`supplier enrich ${supEnrich} ms`);

            }

            if (hadQty && Number.isFinite(qty)) {

                parts.push(`balance qty ${qty} ms`);

            } else {

                parts.push('balance qty omitted on list (faster; open a PR for line detail)');

            }

            const tot = Number.isFinite(Number(totalCount)) ? Number(totalCount) : null;

            parts.push(append ? `+${pageRows} rows` : `${pageRows} rows this request`);

            if (tot != null) {

                parts.push(`${loadedCount} loaded / ${tot} total`);

            }

            el.textContent = parts.join(' · ');

            if (!append && viewPrPrevListPerf && Number.isFinite(srv)) {

                const prev = viewPrPrevListPerf;

                const prevSrv = Number(prev.serverMs);

                if (Number.isFinite(prevSrv) && prevSrv > 0) {

                    const delta = Math.round(srv - prevSrv);

                    el.textContent += ` - vs previous first-page server load: ${delta >= 0 ? '+' : ''}${delta} ms`;

                }

            }

            if (!append) {

                viewPrPrevListPerf = { serverMs: srv, clientMs: Math.round(clientMs), at: Date.now() };

            }

        }

        function syncViewPrLoadMoreUi() {

            const wrap = document.getElementById('view-pr-load-more-wrap');

            const btn = document.getElementById('view-pr-load-more-btn');

            if (!wrap || !btn) return;

            const show = Boolean(viewPrListHasMore && viewPurchaseRequests.length);

            wrap.style.display = show ? '' : 'none';

            btn.disabled = viewPrListLoadingMore;

            const pageSize = VIEW_PR_LIST_PAGE_SIZE;
            btn.textContent = viewPrListLoadingMore ? 'Loading…' : `… more (+${pageSize})`;

            if (show) {

                btn.title = viewPrListTotal != null

                    ? `Load ${pageSize} more (${viewPurchaseRequests.length} of ${viewPrListTotal} shown)`

                    : `Load ${pageSize} more purchase requests`;

            } else {

                btn.removeAttribute('title');

            }

            bindViewPrListInfiniteScroll();
            window.requestAnimationFrame(() => maybeLoadMoreViewPrForScreen());

        }

        function bindViewPrListInfiniteScroll() {
            const list = document.getElementById('view-pr-list');
            if (!list || list.dataset.infiniteScrollBound === '1') return;
            list.dataset.infiniteScrollBound = '1';
            list.addEventListener('scroll', () => {
                maybeLoadMoreViewPrForScreen();
            }, { passive: true });
        }

        function maybeLoadMoreViewPrForScreen() {
            const list = document.getElementById('view-pr-list');
            if (!list || !viewPrListHasMore || viewPrListLoadingMore) return;
            if (list.clientHeight < 80) return;
            const gap = list.scrollHeight - list.scrollTop - list.clientHeight;
            const fillsScreen = list.scrollHeight > list.clientHeight + 8;
            if (!fillsScreen || gap < 140) {
                loadMoreViewPurchaseRequests();
            }
        }

        function saveViewPrListInstantCache(payload) {

            try {

                if (!payload || !payload.success || !Array.isArray(payload.data)) return;

                sessionStorage.setItem(VIEW_PR_LIST_CACHE_KEY, JSON.stringify({

                    at: Date.now(),

                    payload,

                }));

            } catch (e) { /* ignore storage limits/private mode */ }

        }

        function applyViewPrFirstPagePayload(payload, clientMs, isInstantCache) {

            const rows = Array.isArray(payload.data) ? payload.data : [];

            const pg = payload.pagination && typeof payload.pagination === 'object' ? payload.pagination : {};

            const totalRaw = pg.total;

            const totalNum = Number(totalRaw);

            viewPurchaseRequests = rows;

            viewPurchaseRequests.forEach((row) => {

                row.udfStatus = normalizeUdfStatus(row.udfStatus);

                row._originalUdfStatus = row.udfStatus;
                if (Array.isArray(row.suppliers) && row.suppliers.length) {
                    row._suppliers = row.suppliers;
                } else if (!Array.isArray(row._suppliers)) {
                    row._suppliers = [];
                }

            });

            viewPrListTotal = Number.isFinite(totalNum) ? totalNum : viewPurchaseRequests.length;

            viewPrListHasMore = Number.isFinite(totalNum)

                ? viewPurchaseRequests.length < totalNum

                : rows.length >= VIEW_PR_LIST_PAGE_SIZE;

            viewSelectedHeaderId = null;

            viewLoadingDetailIds = new Set();

            const keptIds = new Set(viewPurchaseRequests.map((row) => Number(row.id || 0)).filter(Boolean));

            viewDetailFetchControllers.forEach((controller, requestId) => {

                if (keptIds.has(Number(requestId))) return;

                try {

                    controller.abort();

                } catch (e) {

                    // no-op

                }

            });

            viewDetailFetchControllers = new Map();

            viewDetailFetchPromises = new Map();
            viewDetailFetchStartedAtMs = new Map();

            viewTransferSavingHeaderIds = new Set();

            viewApprovalPendingChanges = new Map();

            viewHeaderStatusPendingChanges = new Map();

            viewBulkSelectedHeaderIds.clear();

            viewApprovalSaving = false;

            viewPurchaseRequestsLoaded = true;

            const currentIds = new Set(viewPurchaseRequests.map((row) => Number(row.id || 0)).filter(Boolean));

            viewDetailCache.forEach((_value, key) => {

                if (!currentIds.has(Number(key))) {

                    viewDetailCache.delete(key);

                }

            });

            updateViewPrListPerfBanner(clientMs, payload.perf, rows.length, viewPurchaseRequests.length, viewPrListTotal, false);

            if (isInstantCache) {

                const perfEl = document.getElementById('view-pr-list-perf');

                if (perfEl) {

                    perfEl.textContent = `Instant cached view · ${perfEl.textContent}`;

                }

            }

            updateViewApprovalButtonState();

            renderFilteredViewPurchaseRequests();
            selectViewPrFromUrlIfPresent();
            syncViewPrLoadMoreUi();
            scheduleViewPrLineSelectionCountsEnrich(rows);
        }

        function buildViewPrListSkeletonHtml() {
            const n = Math.max(1, Math.min(Number(VIEW_PR_LIST_PAGE_SIZE) || 15, 15));
            let cards = '';
            for (let i = 0; i < n; i += 1) {
                cards += `
            <div class="pr-view-pr-row view-pr-card-skeleton" aria-hidden="true">
                <span class="view-pr-skel-bar view-pr-skel-bar--code"></span>
                <span class="view-pr-skel-bar view-pr-skel-bar--date"></span>
                <span class="view-pr-skel-bar view-pr-skel-bar--pill"></span>
                <span class="view-pr-skel-bar view-pr-skel-bar--amt"></span>
            </div>`;
            }
            return `<div class="view-pr-skeleton" aria-busy="true" aria-label="Loading purchase requests">${cards}</div>`;
        }

        function buildViewPrSelectionBadgeHtml(selected, total) {
            const selectedN = Number(selected);
            const totalN = Number(total);
            if (!(Number.isFinite(totalN) && totalN > 0)) {
                return '';
            }
            const selectedSafe = Number.isFinite(selectedN) ? Math.max(0, selectedN) : 0;
            const cls = selectedSafe > 0
                ? (selectedSafe >= totalN ? ' is-all' : ' is-partial')
                : '';
            return `<span class="pr-view-pr-row__selection${cls}" title="Selected line items">SELECTED ${selectedSafe}/${totalN}</span>`;
        }

        function patchViewPrCardSelectionBadge(headerId, selected, total) {
            const id = Number(headerId || 0);
            if (!id) return;
            const row = document.querySelector(`.pr-view-pr-row[data-header-id="${id}"]`);
            if (!row) return;
            const host = row.querySelector('.pr-view-pr-row__selected') || row;
            let badge = host.querySelector('.pr-view-pr-row__selection');
            const html = buildViewPrSelectionBadgeHtml(selected, total);
            if (!html) {
                if (badge) badge.remove();
                return;
            }
            if (badge) {
                badge.outerHTML = html;
            } else {
                host.insertAdjacentHTML('beforeend', html);
            }
        }

        function scheduleViewPrLineSelectionCountsEnrich(rows) {
            try {
                const list = Array.isArray(rows) ? rows : (viewPurchaseRequests || []);
                const missing = [];
                list.forEach((row) => {
                    const id = Number(row && row.id ? row.id : 0);
                    if (!id) return;
                    if (row.lineCount == null || row.selectedLineCount == null) {
                        missing.push(id);
                    }
                });
                if (!missing.length) return Promise.resolve();
                const url = `/api/admin/procurement/purchase-requests/line-selection-counts?ids=${missing.join(',')}`;
                return fetch(url)
                    .then((res) => readProcurementJson(res))
                    .then((payload) => {
                        if (!payload || !payload.success || !payload.data) return;
                        const data = payload.data || {};
                        (viewPurchaseRequests || []).forEach((row) => {
                            const id = Number(row && row.id ? row.id : 0);
                            if (!id) return;
                            const entry = data[String(id)] || data[id];
                            if (!entry) return;
                            const selected = Number(entry.selected || 0);
                            const total = Number(entry.total || 0);
                            row.selectedLineCount = selected;
                            row.lineCount = total;
                            patchViewPrCardSelectionBadge(id, selected, total);
                        });
                        try {
                            const raw = sessionStorage.getItem(VIEW_PR_LIST_CACHE_KEY);
                            if (raw) {
                                const cached = JSON.parse(raw);
                                if (cached && cached.payload && Array.isArray(cached.payload.data)) {
                                    const byId = new Map((viewPurchaseRequests || []).map((r) => [Number(r.id || 0), r]));
                                    cached.payload.data.forEach((row) => {
                                        const live = byId.get(Number(row.id || 0));
                                        if (!live) return;
                                        if (live.selectedLineCount != null) row.selectedLineCount = live.selectedLineCount;
                                        if (live.lineCount != null) row.lineCount = live.lineCount;
                                    });
                                    cached.at = Date.now();
                                    sessionStorage.setItem(VIEW_PR_LIST_CACHE_KEY, JSON.stringify(cached));
                                }
                            }
                        } catch (e) { /* ignore */ }
                    })
                    .catch((err) => {
                        console.warn('[VIEW PR] line-selection-counts enrich failed', err);
                    });
            } catch (e) {
                console.warn('[VIEW PR] line-selection-counts schedule failed', e);
                return Promise.resolve();
            }
        }

        function paintCachedViewPrListForInstantLoad() {

            try {

                const raw = sessionStorage.getItem(VIEW_PR_LIST_CACHE_KEY);

                if (!raw) return false;

                const cached = JSON.parse(raw);

                const ageMs = Date.now() - Number(cached?.at || 0);

                const payload = cached?.payload;

                if (!payload || !payload.success || !Array.isArray(payload.data) || ageMs > VIEW_PR_LIST_CACHE_TTL_MS) {

                    sessionStorage.removeItem(VIEW_PR_LIST_CACHE_KEY);

                    return false;

                }

                const copy = JSON.parse(JSON.stringify(payload));

                copy.perf = {

                    ...(copy.perf || {}),

                    cacheHit: true,

                    cacheAgeMs: Math.round(ageMs),

                    totalMs: 0,

                    upstreamMs: 0,

                };

                applyViewPrFirstPagePayload(copy, 0, true);

                return true;

            } catch (e) {

                return false;

            }

        }

        function loadMoreViewPurchaseRequests() {

            if (!viewPrListHasMore || viewPrListLoadingMore) {

                return Promise.resolve();

            }

            const offset = viewPurchaseRequests.length;

            viewPrListLoadingMore = true;

            syncViewPrLoadMoreUi();

            const startedAt = performance.now();

            const url = `/api/admin/procurement/purchase-requests?offset=${offset}&limit=${VIEW_PR_LIST_PAGE_SIZE}&fast=1&include_qty=0`;

            return fetch(url)

                .then((res) => readProcurementJson(res))

                .then((payload) => {

                    if (!payload.success) {

                        throw new Error(payload.error || 'Failed to load more');

                    }

                    const clientMs = performance.now() - startedAt;

                    const rows = Array.isArray(payload.data) ? payload.data : [];

                    const pg = payload.pagination && typeof payload.pagination === 'object' ? payload.pagination : {};

                    const totalRaw = pg.total;

                    const totalNum = Number(totalRaw);

                    const existing = new Set(viewPurchaseRequests.map((r) => Number(r.id || 0)).filter(Boolean));

                    rows.forEach((row) => {

                        const id = Number(row.id || 0);

                        if (id && existing.has(id)) {

                            return;

                        }

                        if (id) {

                            existing.add(id);

                        }

                        row.udfStatus = normalizeUdfStatus(row.udfStatus);

                        row._originalUdfStatus = row.udfStatus;
                if (Array.isArray(row.suppliers) && row.suppliers.length) {
                    row._suppliers = row.suppliers;
                } else if (!Array.isArray(row._suppliers)) {
                    row._suppliers = [];
                }

                        viewPurchaseRequests.push(row);

                    });

                    if (Number.isFinite(totalNum)) {

                        viewPrListTotal = totalNum;

                    }

                    viewPrListHasMore = Number.isFinite(totalNum)

                        ? viewPurchaseRequests.length < totalNum

                        : rows.length >= VIEW_PR_LIST_PAGE_SIZE;

                    console.log(`[VIEW PR PERF] list append offset=${offset} in ${Math.round(clientMs)}ms`);

                    updateViewPrListPerfBanner(clientMs, payload.perf, rows.length, viewPurchaseRequests.length, viewPrListTotal, true);

                    updateViewApprovalButtonState();
                    renderFilteredViewPurchaseRequests();
                    scheduleViewPrLineSelectionCountsEnrich(rows);
                })

                .catch((error) => {

                    console.error(error);

                    if (!isProcurementAuthExpired(error) && !isRequestAbortError(error)) alert(error.message || 'Failed to load more');

                })

                .finally(() => {

                    viewPrListLoadingMore = false;

                    syncViewPrLoadMoreUi();

                });

        }

        function loadViewPurchaseRequests(forceReload, options) {
            const loadOpts = options || {};

            if (viewPurchaseRequestsLoaded && !forceReload && !loadOpts.background) {

                return Promise.resolve();

            }

            const list = document.getElementById('view-pr-list');

            const perfEl = document.getElementById('view-pr-list-perf');

            const hasExistingList = viewPurchaseRequestsLoaded && (viewPurchaseRequests || []).length > 0;
            const paintedFromCache = (!forceReload && paintCachedViewPrListForInstantLoad())
                || (hasExistingList && (loadOpts.background || forceReload));

            if (list && !paintedFromCache) {

                clearViewPrListDynamicNodes();

                insertBeforeViewPrLoadMore(buildViewPrListSkeletonHtml());

            }

            if (perfEl && !paintedFromCache) {

                perfEl.textContent = '';

            }

            viewPrListHasMore = false;

            viewPrListTotal = null;

            syncViewPrLoadMoreUi();

            const startedAt = performance.now();

            const cacheBust = loadOpts.bustCache ? '&no_cache=1' : '';

            const url = `/api/admin/procurement/purchase-requests?offset=0&limit=${VIEW_PR_LIST_PAGE_SIZE}&fast=1&include_qty=0${cacheBust}`;

            return fetch(url)

                .then((res) => readProcurementJson(res))

                .then((payload) => {

                    if (!payload.success) {

                        throw new Error(payload.error || 'Failed to load e-Purchase Request records');

                    }

                    const clientMs = performance.now() - startedAt;

                    console.log(`[VIEW PR PERF] list first page in ${Math.round(clientMs)}ms (include_qty=0)`);

                    applyViewPrFirstPagePayload(payload, clientMs, false);

                    saveViewPrListInstantCache(payload);

                })

                .catch((error) => {

                    if (isProcurementAuthExpired(error)) {
                        return;
                    }

                    if (paintedFromCache) {

                        if (perfEl) {

                            perfEl.textContent = `Instant cached view · fresh refresh failed: ${escapeHtml(error.message || 'Failed to refresh')}`;

                        }

                        return;

                    }

                    viewPurchaseRequestsLoaded = false;

                    viewPrListHasMore = false;

                    viewPrListTotal = null;

                    viewApprovalPendingChanges = new Map();

                    viewHeaderStatusPendingChanges = new Map();

                    viewBulkSelectedHeaderIds.clear();

                    viewTransferSavingHeaderIds = new Set();

                    viewApprovalSaving = false;

                    updateViewApprovalButtonState();

                    if (perfEl) {

                        perfEl.textContent = '';

                    }

                    syncViewPrLoadMoreUi();

                    if (list) {

                        clearViewPrListDynamicNodes();

                        insertBeforeViewPrLoadMore(`<div class="view-pr-empty">${escapeHtml(error.message || 'Failed to load e-Purchase Request records.')}</div>`);

                    }

                });

        }

        function _toInputDate(value) {

            const text = String(value || '').trim();

            if (!text) return '';

            if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;

            const d = new Date(text);

            if (Number.isNaN(d.getTime())) return '';

            return d.toISOString().slice(0, 10);

        }

        function _showPrEditMessage(message, kind) {

            const el = document.getElementById('pr-edit-message');

            if (!el) return;

            el.style.display = '';

            el.className = `pr-form-message ${kind || 'info'}`;

            el.textContent = message || '';

        }

        function _clearPrEditMessage() {

            const el = document.getElementById('pr-edit-message');

            if (!el) return;

            el.style.display = 'none';

            el.textContent = '';

        }

        function renderPurchaseRequestEditLines() {

            const body = document.getElementById('pr-edit-lines-body');

            if (!body) return;

            const lines = Array.isArray(prEditState?.lineItems) ? prEditState.lineItems : [];

            if (!lines.length) {

                body.innerHTML = '<tr><td colspan="7" class="view-pr-empty">No editable detail rows found.</td></tr>';

                return;

            }

            body.innerHTML = lines.map((line, idx) => {

                const amount = Number(line.quantity || 0) * Number(line.unitPrice || 0);

                return `

                    <tr>

                        <td>${idx + 1}</td>

                        <td>${escapeHtml(line.itemName || line.itemCode || '-')}</td>

                        <td><input type="text" value="${escapeHtml(line.description || '')}" oninput="updatePurchaseRequestEditLine(${idx}, 'description', this.value)" /></td>

                        <td><input type="number" min="0.0001" step="0.0001" value="${escapeHtml(line.quantity || 0)}" oninput="updatePurchaseRequestEditLine(${idx}, 'quantity', this.value)" /></td>

                        <td><input type="number" min="0" step="0.01" value="${escapeHtml(line.unitPrice || 0)}" oninput="updatePurchaseRequestEditLine(${idx}, 'unitPrice', this.value)" /></td>

                        <td><input type="date" value="${escapeHtml(line.deliveryDate || '')}" oninput="updatePurchaseRequestEditLine(${idx}, 'deliveryDate', this.value)" /></td>

                        <td>${formatMoney(amount)}</td>

                    </tr>

                `;

            }).join('');

            recalcPurchaseRequestEditTotal();

        }

        function updatePurchaseRequestEditLine(index, key, value) {

            if (!prEditState || !Array.isArray(prEditState.lineItems) || !prEditState.lineItems[index]) return;

            if (key === 'quantity' || key === 'unitPrice') {

                const num = Number(value);

                prEditState.lineItems[index][key] = Number.isFinite(num) ? num : 0;

            } else {

                prEditState.lineItems[index][key] = value;

            }

            renderPurchaseRequestEditLines();

        }

        function recalcPurchaseRequestEditTotal() {

            const total = (prEditState?.lineItems || []).reduce((sum, line) => {

                return sum + (Number(line.quantity || 0) * Number(line.unitPrice || 0));

            }, 0);

            const el = document.getElementById('pr-edit-total-amount');

            if (el) {

                el.textContent = formatMoney(total);

            }

            return total;

        }

        async function openPurchaseRequestEdit(headerId) {

            const header = viewPurchaseRequests.find((row) => Number(row.id || 0) === Number(headerId));

            if (!header) {

                return;

            }

            const prStatus = String(header.status || '').trim().toUpperCase();
            const udf = normalizeUdfStatus(header._originalUdfStatus || header.udfStatus);

            if (udf === 'CANCELLED') {

                alert('Cancelled purchase requests cannot be edited.');

                return;

            }

            if (prStatus !== 'DRAFT') {

                alert('Only draft purchase requests can be edited.');

                return;

            }

            let payload = null;

            try {

                await fetchViewPurchaseRequestDetail(header, true);

                payload = {

                    success: true,

                    details: Array.isArray(header.details) ? header.details : [],

                    suppliers: Array.isArray(header._suppliers) ? header._suppliers : [],

                };

            } catch (error) {

                if (!isProcurementAuthExpired(error) && !isRequestAbortError(error)) alert(error.message || 'Failed to load PR details for edit');

                return;

            }

            const details = Array.isArray(payload.details) ? payload.details : [];

            header.details = details;

            if (Array.isArray(payload.suppliers)) {

                selectedSuppliers = payload.suppliers
                    .map((s) => ({

                        code: String(s.code || '').trim(),

                        name: String(s.name || '').trim(),

                        email: String(s.email || '').trim(),

                    }))

                    .filter((s) => s.code);

                _renderChips();

            }

            const lineItems = (details || []).map((d) => {

                const basis = String(d.stockQtyUom || '').toUpperCase();

                let qtySqty = Number(d.sqty != null ? d.sqty : NaN);

                let qtySuomqty = Number(d.suomqty != null ? d.suomqty : NaN);

                const q = Number(d.quantity || 0);

                if (!Number.isFinite(qtySqty)) {

                    qtySqty = basis === 'SQTY' ? q : 0;

                }

                if (!Number.isFinite(qtySuomqty)) {

                    qtySuomqty = basis === 'SUOMQTY' ? q : 0;

                }

                const row = {

                    detailId: Number(d.id || 0),

                    itemCode: String(d.itemCode || ''),

                    itemName: String(d.itemName || ''),

                    locationCode: String(d.locationCode || ''),

                    description: resolvePrLineDescription({
                        itemCode: String(d.itemCode || ''),
                        itemName: String(d.itemName || ''),
                        description: String(d.description || ''),
                    }),

                    uom: String(d.uom || d.UOM || ''),

                    udfReason: String(d.udfReason || ''),

                    project: String(d.project || header.project || ''),

                    qtySqty,

                    qtySuomqty,

                    quantity: q,

                    unitPrice: Number(d.unitPrice || 0),

                    deliveryDate: _toInputDate(d.deliveryDate || header.requestDate),

                    stockQtyUom: basis === 'SQTY' ? 'SQTY' : 'SUOMQTY',

                };

                syncPrLineQuantityDerived(row);

                return row;

            }).filter((d) => d.detailId > 0);

            if (!lineItems.length) {

                alert('No editable line items found for this purchase request.');

                return;

            }

            prFormEditState = {

                requestId: Number(header.id || 0),

                requestNumber: String(header.requestNumber || ''),

                currency: String(header.currency || ''),

            };

            document.getElementById('pr-request-number').value = String(header.requestNumber || '');

            const requestDateEl = document.getElementById('pr-request-date');

            if (requestDateEl) {

                requestDateEl.value = _toInputDate(header.requestDate);

            }

            renderProjectOptions(String(header.project || ''));

            

            

            window.purchaseRequestItems = lineItems;

            applyPurchaseRequestFormModeUI();

            renderPurchaseRequestLineItems();

            savePurchaseRequestDraftItems();
            savePurchaseRequestDraftItems();
            showTab('create');

            showPurchaseRequestMessage('Editing draft purchase request. Update line values and click Update Purchase Request.', 'info');

        }

        function closePurchaseRequestEdit() {

            prEditState = null;

            _clearPrEditMessage();

            const modal = document.getElementById('pr-edit-modal');

            if (modal) {

                modal.style.display = 'none';

            }

        }

        async function savePurchaseRequestEdit() {

            if (!prEditState || !prEditState.requestId) {

                return;

            }

            // Requested Date is system-controlled (DOCDATE). Keep existing value.

            prEditState.requestDate = String(document.getElementById('pr-edit-request-date').value || '').trim();

            prEditState.costCenter = String(document.getElementById('pr-edit-cost-center').value || '').trim();

            prEditState.currency = String(document.getElementById('pr-edit-currency').value || '').trim();

            prEditState.description = String(document.getElementById('pr-edit-description').value || '').trim();

            prEditState.deliveryLocation = String(document.getElementById('pr-edit-delivery-location').value || '').trim();

            // requested date is read-only; do not validate user input here.

            if (!Array.isArray(prEditState.lineItems) || !prEditState.lineItems.length) {

                _showPrEditMessage('At least one line item is required.', 'error');

                return;

            }

            const badLine = prEditState.lineItems.find((l) => {

                const q = Number(l.quantity);

                return Number.isNaN(q) || q < 0 || !(Number(l.unitPrice) >= 0);

            });

            if (badLine) {

                _showPrEditMessage('Each line needs quantity at least 0 and unit price at least 0.', 'error');

                return;

            }

            const payload = {

                // requiredDate is not user-facing; backend defaults it to requestDate when omitted.

                costCenter: prEditState.costCenter,

                project: getSelectedProjectCode(),

                currency: prEditState.currency,

                description: prEditState.description,

                deliveryLocation: prEditState.deliveryLocation,

                lineItems: prEditState.lineItems.map((l) => ({

                    detailId: Number(l.detailId || 0),

                    description: String(l.description || '').trim(),

                    udfReason: String(l.udfReason || '').trim(),

                    project: getSelectedProjectCode(),

                    quantity: Number(l.quantity || 0),

                    unitPrice: Number(l.unitPrice || 0),

                    deliveryDate: String(l.deliveryDate || '').trim(),

                })),

            };

            const btn = document.getElementById('pr-edit-save-btn');

            btn.disabled = true;

            btn.textContent = 'Saving...';

            _showPrEditMessage('Saving changes...', 'info');

            try {

                const res = await fetch(`/api/admin/procurement/purchase-requests/${prEditState.requestId}/edit`, {

                    method: 'PATCH',

                    headers: { 'Content-Type': 'application/json' },

                    body: JSON.stringify(payload),

                });

                const data = await readProcurementJson(res);

                if (!res.ok || !data.success) {

                    throw new Error(data.error || `Update failed (HTTP ${res.status})`);

                }

                _showPrEditMessage('Purchase request updated successfully.', 'success');

                await loadViewPurchaseRequests(true);

                closePurchaseRequestEdit();

            } catch (error) {

                if (!isProcurementAuthExpired(error)) _showPrEditMessage(error.message || 'Failed to update purchase request.', 'error');

            } finally {

                btn.disabled = false;

                btn.textContent = 'Save Changes';

            }

        }

        function formatAvgSales3mMonthLabel(yyyyMm) {
            const raw = String(yyyyMm || '').trim();
            const m = raw.match(/^(\d{4})-(\d{2})$/);
            if (!m) return raw;
            const monthIdx = Math.max(1, Math.min(12, parseInt(m[2], 10) || 0)) - 1;
            const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            return names[monthIdx] || raw;
        }

        function stockCardAvgSales3mRangeLabel() {
            const months = Array.isArray(stockCardAvgSales3mMonths) ? stockCardAvgSales3mMonths.filter(Boolean) : [];
            if (!months.length) return '';
            if (months.length === 1) return formatAvgSales3mMonthLabel(months[0]);
            return formatAvgSales3mMonthLabel(months[0]) + '–' + formatAvgSales3mMonthLabel(months[months.length - 1]);
        }

        function stockCardMetricGroupLabel(group) {
            const base = String((group && group.label) || '').trim() || 'Metric';
            if (group && group.key === 'avg_sales_3m_by_location') {
                const range = stockCardAvgSales3mRangeLabel();
                return range ? (base + ' (' + range + ')') : base;
            }
            return base;
        }

        function stockCardPlainQtyCell(bgClass, value, titleText) {
            const title = titleText ? ` title="${escapeHtml(titleText)}"` : '';
            return `<td class="${bgClass}"${title}>${formatStockCardNumber(value)}</td>`;
        }

        function stockCardQtyCellForGroup(group, bgClass, value, itemCode, locationCode, qtyMode) {
            if (group && group.key === 'avg_sales_3m_by_location') {
                const range = stockCardAvgSales3mRangeLabel();
                const title = range
                    ? ('Avg invoiced sales / 3 (' + range + ')')
                    : 'Avg invoiced sales over last 3 full months';
                return stockCardPlainQtyCell(bgClass, value, title);
            }
            return stockCardClickableQtyCell(bgClass, value, itemCode, locationCode, group.key, qtyMode);
        }

        function renderStockCardHeader(locations) {

            const locationColumns = Array.isArray(locations) ? locations : [];

            const thead = document.getElementById('stock-card-table-head');

            const sub = stockCardSubcolsPerLocation();

            const visibleMetricGroups = getVisibleStockCardMetricGroups();

            if (!visibleMetricGroups.length) {

                thead.innerHTML = `

                    <tr>

                        <th class="code-col stock-card-code-col--fixed" scope="col">ITEM CODE</th>

                        <th class="stock-card-no-cols-msg stock-card-no-cols-msg--head" scope="col"></th>

                    </tr>

                `;

                thead.className = locationColumns.length

                    ? 'stock-card-thead stock-card-thead--one-row stock-card-thead--no-metric-cols'

                    : 'stock-card-thead stock-card-thead--no-locs stock-card-thead--no-metric-cols';

                if (locationColumns.length) {

                    requestAnimationFrame(() => {

                        requestAnimationFrame(() => syncStockCardHeaderStickyOffset());

                    });

                }

                return;

            }

            if (!locationColumns.length) {

                const defaultColumns = visibleMetricGroups.map((group) => {

                    if (sub === 2) {

                        return `<th class="qty-col stock-card-expand"><div class="stock-card-th-stacked"><span class="stock-card-th-main">${escapeHtml(stockCardMetricGroupLabel(group))}</span><span class="stock-card-th-subpair"><span>SQTY</span><span>SUOMQTY</span></span></div></th>`;

                    }

                    return `<th class="qty-col stock-card-expand">${escapeHtml(stockCardMetricGroupLabel(group))} <span class="stock-card-th-note">(${stockCardSingleUomLabel()})</span></th>`;

                }).join('');

                thead.innerHTML = `

                    <tr>

                        <th class="code-col stock-card-expand">ITEM CODE</th>

                        ${defaultColumns}

                    </tr>

                `;

                if (thead) {

                    thead.className = 'stock-card-thead stock-card-thead--no-locs';

                }

                return;

            }

            const L = locationColumns.length;
            const both = sub === 2;
            const headerRows = both ? 3 : 2;

            if (thead) {
                thead.className = both
                    ? 'stock-card-thead stock-card-thead--three-row'
                    : 'stock-card-thead stock-card-thead--two-row';
            }

            const codeTh = `<th class="code-col" rowspan="${headerRows}" scope="col"><div class="stock-card-hdr-code">ITEM CODE</div></th>`;

            let groupRow = codeTh;
            visibleMetricGroups.forEach((group) => {
                const colspan = L * sub;
                groupRow += `<th class="qty-group-col stock-card-metric-group-th stock-card-group-sep" colspan="${colspan}" scope="colgroup"><span class="stock-card-metric-group-label">${escapeHtml(stockCardMetricGroupLabel(group))}</span></th>`;
            });

            let locationRow = '';
            visibleMetricGroups.forEach(() => {
                locationColumns.forEach((locationCode, idx) => {
                    const bg = (idx % 10) + 1;
                    const edge = `${idx === 0 ? ' location-first' : ''}${idx === L - 1 ? ' location-last' : ''}`;
                    const colspanAttr = both ? ' colspan="2"' : '';
                    locationRow += `<th class="qty-col location-bg-${bg}${edge} stock-card-header-cell" scope="col"${colspanAttr}><span class="stock-card-hdr-loc">${escapeHtml(locationCode)}</span></th>`;
                });
            });

            let html = `<tr>${groupRow}</tr><tr>${locationRow}</tr>`;

            if (both) {
                let uomRow = '';
                visibleMetricGroups.forEach(() => {
                    locationColumns.forEach((_, idx) => {
                        const bg = (idx % 10) + 1;
                        const first = idx === 0 ? ' location-first' : '';
                        const last = idx === L - 1 ? ' location-last' : '';
                        uomRow += `<th class="qty-col location-bg-${bg}${first} stock-card-header-cell stock-card-hdr-uom-cell" scope="col"><span class="stock-card-hdr-uom stock-card-hdr-uom--sq">SQTY</span></th>`;
                        uomRow += `<th class="qty-col location-bg-${bg}${last} stock-card-header-cell stock-card-hdr-uom-cell" scope="col"><span class="stock-card-hdr-uom stock-card-hdr-uom--su">SUOMQTY</span></th>`;
                    });
                });
                html += `<tr>${uomRow}</tr>`;
            }

            thead.innerHTML = html;

            requestAnimationFrame(() => {
                requestAnimationFrame(() => syncStockCardHeaderStickyOffset());
            });

        }

        function renderLocationFilters() {
            const host = document.getElementById('stock-location-ms-options');
            const menu = document.getElementById('stock-location-ms-menu');
            const wasOpen = !!(menu && !menu.hidden);
            const selected = Array.isArray(selectedStockCardLocations) ? selectedStockCardLocations : [];
            const all = Array.isArray(stockCardLocations) ? stockCardLocations : [];
            if (host) {
                if (!all.length) {
                    host.innerHTML = '<span class="location-empty">No locations available.</span>';
                } else {
                    host.innerHTML = all.map((locationCode, idx) => {
                        const checked = selected.includes(locationCode) ? 'checked' : '';
                        const safeId = `stock-loc-filter-${idx}`;
                        return `<label class="stock-ms__option"><input type="checkbox" id="${safeId}" ${checked} onchange="onStockLocationFilterChange('${escapeJs(locationCode)}', this.checked)" /> <span>${escapeHtml(locationCode)}</span></label>`;
                    }).join('');
                }
            }
            updateStockReportFilterSummary();
            if (wasOpen) {
                const root = document.getElementById('stock-location-ms');
                const trigger = document.getElementById('stock-location-ms-trigger');
                if (root) root.classList.add('is-open');
                if (menu) menu.hidden = false;
                if (trigger) trigger.setAttribute('aria-expanded', 'true');
            }
        }

        function onStockLocationFilterChange(locationCode, checked) {
            if (checked) {
                addLocationFilter(locationCode);
            } else {
                removeLocationFilter(locationCode);
            }
        }

        function addLocationFilter(locationCode) {
            if (!stockCardLocations.includes(locationCode) || selectedStockCardLocations.includes(locationCode)) {
                return;
            }
            selectedStockCardLocations.push(locationCode);
            persistStockCardSelectedLocations();
            syncStockCardTable();
        }

        function removeLocationFilter(locationCode) {
            selectedStockCardLocations = selectedStockCardLocations.filter((code) => code !== locationCode);
            persistStockCardSelectedLocations();
            syncStockCardTable();
        }

        function selectAllStockCardLocations() {
            selectedStockCardLocations = (Array.isArray(stockCardLocations) ? stockCardLocations : []).slice();
            persistStockCardSelectedLocations();
            syncStockCardTable();
        }

        function clearAllStockCardLocations() {
            selectedStockCardLocations = [];
            persistStockCardSelectedLocations();
            syncStockCardTable();
        }

        function savePurchaseRequestDraftItems() {
            try {
                if (!Array.isArray(window.purchaseRequestItems) || !window.purchaseRequestItems.length) {
                    localStorage.removeItem(PURCHASE_REQUEST_DRAFT_LS_KEY);
                    return;
                }
                const items = window.purchaseRequestItems.map((item) => ({
                    itemCode: String(item?.itemCode || '').trim(),
                    itemName: String(item?.itemName || '').trim(),
                    locationCode: String(item?.locationCode || '').trim(),
                    description: String(item?.description || '').trim(),
                    uom: String(item?.uom || '').trim(),
                    udfReason: String(item?.udfReason || '').trim(),
                    project: String(item?.project || '').trim(),
                    qtySqty: Number(item?.qtySqty || 0),
                    qtySuomqty: Number(item?.qtySuomqty || 0),
                    quantity: Number(item?.quantity || 0),
                    unitPrice: Number(item?.unitPrice || 0),
                    deliveryDate: String(item?.deliveryDate || '').trim(),
                    stockQtyUom: String(item?.stockQtyUom || '').trim().toUpperCase(),
                }));
                localStorage.setItem(PURCHASE_REQUEST_DRAFT_LS_KEY, JSON.stringify(items));
            } catch (_) {}
        }

        function clearPurchaseRequestDraftItems() {
            try {
                localStorage.removeItem(PURCHASE_REQUEST_DRAFT_LS_KEY);
            } catch (_) {}
        }

        function tryRestorePurchaseRequestDraftItems() {
            try {
                const raw = localStorage.getItem(PURCHASE_REQUEST_DRAFT_LS_KEY);
                if (!raw) return false;
                const parsed = JSON.parse(raw);
                if (!Array.isArray(parsed) || !parsed.length) return false;
                const restored = parsed.map((item) => {
                    const row = {
                        itemCode: String(item?.itemCode || '').trim(),
                        itemName: String(item?.itemName || '').trim(),
                        locationCode: String(item?.locationCode || '').trim(),
                        description: String(item?.description || '').trim(),
                        uom: String(item?.uom || '').trim(),
                        udfReason: String(item?.udfReason || '').trim(),
                        project: String(item?.project || '').trim(),
                        qtySqty: Number(item?.qtySqty || 0),
                        qtySuomqty: Number(item?.qtySuomqty || 0),
                        quantity: Number(item?.quantity || 0),
                        unitPrice: Number(item?.unitPrice || 0),
                        deliveryDate: String(item?.deliveryDate || '').trim() || prTodayIso(),
                        stockQtyUom: String(item?.stockQtyUom || defaultPrStockQtyUom()).trim().toUpperCase(),
                    };
                    syncPrLineQuantityDerived(row);
                    return row;
                });
                window.purchaseRequestItems = restored;
                return true;
            } catch (_) {
                return false;
            }
        }

        function isDetailChecked(detail) {
            if (!detail || typeof detail !== 'object') return false;
            if (Object.prototype.hasOwnProperty.call(detail, 'transferable') && detail.transferable != null && String(detail.transferable).trim() !== '') {
                return toApprovalBool(detail.transferable);
            }
            if (Object.prototype.hasOwnProperty.call(detail, 'TRANSFERABLE') && detail.TRANSFERABLE != null && String(detail.TRANSFERABLE).trim() !== '') {
                return toApprovalBool(detail.TRANSFERABLE);
            }
            if (Object.prototype.hasOwnProperty.call(detail, 'udfPqApproved') && detail.udfPqApproved != null && String(detail.udfPqApproved).trim() !== '') {
                return toApprovalBool(detail.udfPqApproved);
            }
            return false;
        }

        function goToCreateProcurement() {
            try { closeStockReportSettingsDrawer(); } catch (e) {}

            const selectedEntries = Object.entries(stockCardBuySelections)

                .map(([key, value]) => ({ key, ...value }))

                .filter((entry) => entry && entry.selected);

            if (!selectedEntries.length) {

                // No selection: go straight to create with a blank line item

                const selectedProjectCode = getSelectedProjectCode();

                const today = prTodayIso();

                const defU = defaultPrStockQtyUom();

                const row = {

                    itemCode: '',

                    itemName: '',

                    locationCode: getDefaultLineLocation(),

                    description: '',

                    uom: '',

                    udfReason: '',

                    project: selectedProjectCode,

                    qtySqty: defU === 'SQTY' ? 1 : 0,

                    qtySuomqty: defU === 'SUOMQTY' ? 1 : 0,

                    quantity: 1,

                    unitPrice: 0,

                    deliveryDate: today,

                    stockQtyUom: defU,

                };

                syncPrLineQuantityDerived(row);

                window.purchaseRequestItems = [row];
                savePurchaseRequestDraftItems();

                showTab('create');

                renderPurchaseRequestLineItems();

                showPurchaseRequestMessage('Starting a new e-Purchase Request.', 'info');

                return;

            }

            const mergedRows = mergeBuySelectionsForCreatePr(selectedEntries);

            window.purchaseRequestItems = mergedRows.map((row) => {

                const code = String(row.itemCode || '').trim();

                const locationCode = String(row.locationCode || '').trim();

                const locationText = locationCode ? ` (${locationCode})` : '';

                let itemName = code;

                const product = typeof findPrProductByCode === 'function' ? findPrProductByCode(code) : (window.prCatalogProducts || []).find((p) => String(p.CODE || '').trim() === code);

                if (product && product.DESCRIPTION) {

                    itemName = String(product.DESCRIPTION).trim();

                }

                const o = {

                    itemCode: code,

                    itemName: itemName,

                    locationCode,

                    description: itemName,

                    uom: '',

                    udfReason: '',

                    project: getSelectedProjectCode(),

                    qtySqty: Number(row.qtySqty || 0),

                    qtySuomqty: Number(row.qtySuomqty || 0),

                    unitPrice: 0,

                    deliveryDate: prTodayIso(),

                    stockQtyUom: defaultPrStockQtyUom(),

                };

                syncPrLineQuantityDerived(o);

                cachePrLineUdfWtp(o, product);
                mergePrLineCatalogUdfs(o, product);
                if (resolvePrLineUdfWeight(o) != null && Number(o.qtySqty || 0) > 0) {
                    applyPrLineSuomFromSqtyUdfWeight(o);
                    syncPrLineQuantityDerived(o);
                }

                return o;

            });

            showTab('create');

            renderPurchaseRequestLineItems();

            showPurchaseRequestMessage(`Loaded ${window.purchaseRequestItems.length} item(s) into Create e-Purchase Request.`, 'info');

        }

        function buySelectionKey(itemCode, locationCode, stockQtyUom) {

            const ic = String(itemCode || '').trim();

            const lc = String(locationCode || '').trim();

            const uom = stockQtyUom ? String(stockQtyUom).trim().toUpperCase() : '';

            return uom ? `${ic}||${lc}||${uom}` : `${ic}||${lc}`;

        }

        function stockCardSetBuyCheckbox(itemCode, locationCode, defaultQty, checkboxEl, stockQtyUom) {

            const uom = String(stockQtyUom || defaultPrStockQtyUom()).toUpperCase() === 'SQTY' ? 'SQTY' : 'SUOMQTY';

            const key = buySelectionKey(itemCode, locationCode, uom);

            const td = checkboxEl && checkboxEl.closest ? checkboxEl.closest('td') : null;

            let effDefault = defaultQty;

            if (uom === 'SUOMQTY' && td) {

                const attr = td.getAttribute('data-buy-default');

                if (attr !== null && attr !== '') {

                    const n = Number(attr);

                    if (Number.isFinite(n)) effDefault = n;

                }

            }

            const current = stockCardBuySelections[key] || {

                itemCode,

                locationCode: locationCode || '',

                selected: false,

                quantity: Number(effDefault || 0),

                stockQtyUom: uom,

            };

            current.selected = !!checkboxEl.checked;

            current.itemCode = itemCode;

            current.locationCode = locationCode || '';

            current.stockQtyUom = uom;

            if (uom === 'SUOMQTY') {

                current.quantity = Number(effDefault || 0);

            } else if (current.quantity == null || Number.isNaN(Number(current.quantity))) {

                current.quantity = Number(defaultQty || 0);

            }

            stockCardBuySelections[key] = current;

            if (td) {

                if (td.classList.contains('need-buy-td--su-static')) {

                    td.classList.remove('need-buy-selected');

                } else {

                    td.classList.toggle('need-buy-selected', current.selected);

                }

            }

        }

        function stockCardSetBuyQty(itemCode, locationCode, defaultQty, inputEl, stockQtyUom) {

            const uom = String(stockQtyUom || defaultPrStockQtyUom()).toUpperCase() === 'SQTY' ? 'SQTY' : 'SUOMQTY';

            const key = buySelectionKey(itemCode, locationCode, uom);

            const current = stockCardBuySelections[key] || {

                itemCode,

                locationCode: locationCode || '',

                selected: false,

                quantity: Number(defaultQty || 0),

                stockQtyUom: uom,

            };

            const v = parseFloat(String(inputEl.value || '').replace(/,/g, ''));

            current.quantity = Number.isFinite(v) && v >= 0 ? v : 0;

            current.itemCode = itemCode;

            current.locationCode = locationCode || '';

            current.stockQtyUom = uom;

            stockCardBuySelections[key] = current;

        }

        function stockCardSetBuyQtySu(itemCode, locationCode, defaultSu, defaultSq, inputEl) {

            const key = buySelectionKey(itemCode, locationCode, 'SUOMQTY');

            const v = parseFloat(String(inputEl.value || '').replace(/,/g, ''));

            const prev = stockCardBuySelections[key] || {

                itemCode,

                locationCode: locationCode || '',

                selected: false,

                quantity: Number(defaultSu || 0),

                quantitySq: Number(defaultSq || 0),

                stockQtyUom: 'SUOMQTY',

            };

            prev.quantity = Number.isFinite(v) && v >= 0 ? v : 0;

            if (prev.quantitySq == null || Number.isNaN(prev.quantitySq)) prev.quantitySq = Number(defaultSq || 0);

            prev.itemCode = itemCode;

            prev.locationCode = locationCode || '';

            prev.stockQtyUom = 'SUOMQTY';

            stockCardBuySelections[key] = prev;

        }

        /** Shortage SUOM for stock card: SQTY × UDF_WTP when catalog has WTP; otherwise report SU shortage. */

        function stockCardDerivedSuomShortage(itemCode, sqQty, reportShortageSu) {

            const w = prItemUdfWeight(typeof findPrProductByCode === 'function' ? findPrProductByCode(itemCode) : null);

            if (w == null) return Math.max(0, Number(reportShortageSu || 0));

            const sq = Math.max(0, Number(sqQty || 0));

            return Math.round(sq * w * 10000) / 10000;

        }

        function stockCardSetBuyQtySq(itemCode, locationCode, defaultSq, defaultSu, inputEl) {

            const key = buySelectionKey(itemCode, locationCode, 'SQTY');

            const v = parseFloat(String(inputEl.value || '').replace(/,/g, ''));

            const prev = stockCardBuySelections[key] || {

                itemCode,

                locationCode: locationCode || '',

                selected: false,

                quantity: Number(defaultSq || 0),

                quantitySq: Number(defaultSq || 0),

                stockQtyUom: 'SQTY',

            };

            prev.quantity = Number.isFinite(v) && v >= 0 ? v : 0;

            prev.quantitySq = Number.isFinite(v) && v >= 0 ? v : 0;

            prev.itemCode = itemCode;

            prev.locationCode = locationCode || '';

            prev.stockQtyUom = 'SQTY';

            stockCardBuySelections[key] = prev;

            const w = prItemUdfWeight(typeof findPrProductByCode === 'function' ? findPrProductByCode(itemCode) : null);

            if (w == null || !inputEl || !inputEl.closest) return;

            const sqNum = prev.quantity;

            const suNum = Math.max(0, Math.round(sqNum * w * 10000) / 10000);

            const suKey = buySelectionKey(itemCode, locationCode, 'SUOMQTY');

            const suSel = stockCardBuySelections[suKey];

            if (suSel) suSel.quantity = suNum;

            const sqTd = inputEl.closest('td');

            const suTd = sqTd && sqTd.nextElementSibling;

            /* Defer DOM updates so the active SQ input keeps focus (sync layout can blur in some browsers). */

            setTimeout(() => {

                if (!inputEl || !document.body || !document.body.contains(inputEl)) return;

                if (suTd && suTd.classList && suTd.classList.contains('need-buy-td--su-static')) {

                    suTd.setAttribute('data-buy-default', String(suNum));

                    const span = suTd.querySelector('.need-buy-readonly-qty');

                    if (span) span.textContent = formatStockCardNumber(suNum);

                }

            }, 0);

        }

        function stockCardNeedBuyCellClick(event, tdEl) {

            if (!tdEl || !event) return;

            const t = event.target;

            if (t && t.closest && t.closest('input.need-buy-qty-input')) return;

            if (t && t.closest && t.closest('.need-buy-qty-input')) return;

            const cb = tdEl.querySelector('input.need-buy-cb');

            if (!cb) return;

            cb.checked = !cb.checked;

            stockCardSetBuyCheckbox(

                tdEl.getAttribute('data-buy-item') || '',

                tdEl.getAttribute('data-buy-loc') || '',

                Number(tdEl.getAttribute('data-buy-default') || 0),

                cb,

                tdEl.getAttribute('data-buy-uom') || '',

            );

        }

        function getStockCardFilteredRows() {

            const q = String(stockCardItemSearch || '').trim().toLowerCase();

            if (!q) return stockCardRows;

            return (stockCardRows || []).filter((row) => String(row.code || '').toLowerCase().includes(q));

        }

        let stockCardItemSearchDebounceTimer = null;

        function onStockCardItemSearchInput(value) {

            stockCardItemSearch = String(value || '');

            if (stockCardItemSearchDebounceTimer) {

                clearTimeout(stockCardItemSearchDebounceTimer);

            }

            stockCardItemSearchDebounceTimer = setTimeout(() => {

                stockCardItemSearchDebounceTimer = null;

                syncStockCardTable();

            }, 140);

        }

        function syncStockCardTable() {

            renderStockColumnFilterPanel();

            renderLocationFilters();

            renderStockCardHeader(selectedStockCardLocations);

            renderStockCardRows(getStockCardFilteredRows(), selectedStockCardLocations, stockCardStTrUdfSummary);

            setStockCardTableNoMetricColsClass();

            afterStockCardTableRender();

        }

        function formatStockCardNumber(value) {

            const number = Number(value || 0);

            if (!Number.isFinite(number)) {

                return '0';

            }

            return number.toLocaleString(undefined, {

                minimumFractionDigits: 0,

                maximumFractionDigits: 4,

            });

        }

        function metricLabel(metricKey) {

            const found = stockCardMetricGroups.find((group) => group.key === metricKey);

            return found ? found.label : metricKey;

        }

        function formatStockCardMetaDate(value) {

            const txt = value != null ? String(value).trim() : '';

            if (!txt || txt === '-') return '-';

            const m = txt.match(/^(\d{4})-(\d{2})-(\d{2})/);

            if (m) return `${m[3]}/${m[2]}/${m[1]}`;

            return txt;

        }

        /** One grouped row per batch, with ST_BATCH metadata in dedicated columns. */

        function renderStTrQtyPairBreakdownRows(rows, itemCode, locationCode) {

            return rows.map((row, idx) => {

                const gClass = idx % 2 === 0

                    ? 'stock-card-breakdown-group-a'

                    : 'stock-card-breakdown-group-b';

                const batch = row.batch != null && String(row.batch).trim() ? String(row.batch).trim() : '-';

                const batchDesc = row.batch_description != null && String(row.batch_description).trim()

                    ? String(row.batch_description).trim()

                    : '-';

                const exp = formatStockCardMetaDate(row.expdate);

                const mfg = formatStockCardMetaDate(row.mfgdate);

                return `<tr class="${gClass}">`

                    + `<td class="stock-card-breakdown-batch-td">${escapeHtml(String(locationCode || row.location || batch || '-').trim() || '-')}</td>`

                    + `<td class="stock-card-breakdown-desc">${escapeHtml(String(itemCode || row.item_code || row.itemCode || '-').trim() || '-')}</td>`

                    + `<td>${escapeHtml(exp || '-')}</td>`

                    + `<td>${escapeHtml(mfg || '-')}</td>`

                    + `<td class="stock-card-breakdown-num">${formatStockCardNumber(row.sqty)}</td>`

                    + `<td class="stock-card-breakdown-num">${formatStockCardNumber(row.suomqty)}</td>`

                    + '</tr>';

            }).join('');

        }

        function renderStockCardBreakdownTable(payload, metricKey) {

            const thead = document.getElementById('stock-card-breakdown-thead');

            const body = document.getElementById('stock-card-breakdown-body');

            const table = document.getElementById('stock-card-breakdown-table');

            const metric = String(payload.metric || metricKey || '').replace('_by_location', '');

            const style = String(payload.breakdown_style || '');

            const rows = Array.isArray(payload.rows) ? payload.rows : [];

            if (table) {

                const compact =

                    metric === 'avail_qty'

                    || style === 'st_tr'

                    || style === 'st_tr_qty_pair'

                    || style === 'doc_net_pair'

                    || style === 'component_net_pair'

                    || metric === 'qty'

                    || metric === 'suom_qty'

                    || metric === 'need_to_buy';

                table.classList.toggle('stock-card-breakdown-table--compact', compact);

            }

            if (style === 'doc_net_pair') {

                thead.innerHTML = '<tr><th scope="col">Doc No</th><th scope="col">Date</th><th scope="col">Company / Party</th><th scope="col">Remarks</th><th scope="col" class="stock-card-breakdown-num">Net (SQTY)</th><th scope="col" class="stock-card-breakdown-num">Net (SUOMQTY)</th></tr>';

                if (!rows.length) {

                    body.innerHTML = '<tr><td colspan="6" class="stock-card-status">No supporting records found.</td></tr>';

                    return;

                }

                body.innerHTML = rows.map((row) => `

                    <tr>

                        <td>${escapeHtml(row.docno || '-')}</td>

                        <td>${escapeHtml(row.docdate || '-')}</td>

                        <td>${escapeHtml(row.party || '-')}</td>

                        <td class="stock-card-breakdown-detail">${escapeHtml(row.remarks || '-')}</td>

                        <td class="stock-card-breakdown-num">${formatStockCardNumber(row.outstanding_sqty)}</td>

                        <td class="stock-card-breakdown-num">${formatStockCardNumber(row.outstanding_suomqty)}</td>

                    </tr>

                `).join('');

                return;

            }

            if (style === 'component_net_pair') {

                thead.innerHTML = '<tr><th scope="col">Component</th><th scope="col">Details</th><th scope="col" class="stock-card-breakdown-num">Net (SQTY)</th><th scope="col" class="stock-card-breakdown-num">Net (SUOMQTY)</th></tr>';

                if (!rows.length) {

                    body.innerHTML = '<tr><td colspan="4" class="stock-card-status">No data.</td></tr>';

                    return;

                }

                body.innerHTML = rows.map((row) => `

                    <tr>

                        <td>${escapeHtml(row.docno || '-')}</td>

                        <td class="stock-card-breakdown-detail">${escapeHtml(row.remarks || '-')}</td>

                        <td class="stock-card-breakdown-num">${formatStockCardNumber(row.outstanding_sqty)}</td>

                        <td class="stock-card-breakdown-num">${formatStockCardNumber(row.outstanding_suomqty)}</td>

                    </tr>

                `).join('');

                return;

            }

            if (style === 'st_tr_qty_pair') {

                thead.innerHTML = '<tr><th scope="col">Location</th><th scope="col">Item code</th><th scope="col">Exp Date</th><th scope="col">Mfg Date</th><th scope="col" class="stock-card-breakdown-num">SQTY</th><th scope="col" class="stock-card-breakdown-num">SUOMQTY</th></tr>';

                if (!rows.length) {

                    body.innerHTML = '<tr><td colspan="6" class="stock-card-status">No ST_TR lines for this item/location.</td></tr>';

                    return;

                }

                body.innerHTML = renderStTrQtyPairBreakdownRows(rows, payload.item_code || payload.itemCode || '', payload.location || payload.locationCode || '');

                return;

            }

            if (metric === 'avail_qty' || style === 'st_tr') {

                thead.innerHTML = '<tr><th scope="col">Reference</th><th scope="col">Description</th><th scope="col" class="stock-card-breakdown-num">Qty</th></tr>';

                if (!rows.length) {

                    body.innerHTML = '<tr><td colspan="3" class="stock-card-status">No ST_TR lines for this item/location.</td></tr>';

                    return;

                }

                body.innerHTML = rows.map((row) => {

                    const q = row.outstanding_qty != null ? row.outstanding_qty : row.total_qty;

                    return `

                        <tr>

                            <td>${escapeHtml(row.docno != null && String(row.docno).trim() ? row.docno : '-')}</td>

                            <td>${escapeHtml(row.remarks != null && String(row.remarks).trim() ? row.remarks : (row.party || '-'))}</td>

                            <td class="stock-card-breakdown-num">${formatStockCardNumber(q)}</td>

                        </tr>`;

                }).join('');

                return;

            }

            if (metric === 'qty' || metric === 'suom_qty' || metric === 'need_to_buy') {

                thead.innerHTML = '<tr><th scope="col">Component</th><th scope="col">Details</th><th scope="col" class="stock-card-breakdown-num">Net</th></tr>';

                if (!rows.length) {

                    body.innerHTML = '<tr><td colspan="3" class="stock-card-status">No data.</td></tr>';

                    return;

                }

                body.innerHTML = rows.map((row) => `

                    <tr>

                        <td>${escapeHtml(row.docno || '-')}</td>

                        <td class="stock-card-breakdown-detail">${escapeHtml(row.remarks || '-')}</td>

                        <td class="stock-card-breakdown-num">${formatStockCardNumber(row.outstanding_qty)}</td>

                    </tr>

                `).join('');

                return;

            }

            thead.innerHTML = '<tr><th scope="col">Doc No</th><th scope="col">Date</th><th scope="col">Company / Party</th><th scope="col">Remarks</th><th scope="col" class="stock-card-breakdown-num">Total</th><th scope="col" class="stock-card-breakdown-num">Moved</th><th scope="col" class="stock-card-breakdown-num">Net</th></tr>';

            if (!rows.length) {

                body.innerHTML = '<tr><td colspan="7" class="stock-card-status">No supporting records found.</td></tr>';

                return;

            }

            body.innerHTML = rows.map((row) => `

                <tr>

                    <td>${escapeHtml(row.docno || '-')}</td>

                    <td>${escapeHtml(row.docdate || '-')}</td>

                    <td>${escapeHtml(row.party || '-')}</td>

                    <td>${escapeHtml(row.remarks || '-')}</td>

                    <td class="stock-card-breakdown-num">${formatStockCardNumber(row.total_qty)}</td>

                    <td class="stock-card-breakdown-num">${formatStockCardNumber(row.moved_qty)}</td>

                    <td class="stock-card-breakdown-num">${formatStockCardNumber(row.outstanding_qty)}</td>

                </tr>

            `).join('');

        }

        function openStockCardBreakdown(itemCode, locationCode, metricKey, qtyMode, batchOpt) {

            const dock = document.getElementById('stock-card-breakdown-dock');

            const body = document.getElementById('stock-card-breakdown-body');

            const headingPrimary = document.getElementById('stock-card-breakdown-heading-primary');

            const subtitle = document.getElementById('stock-card-breakdown-subtitle');

            const summary = document.getElementById('stock-card-breakdown-summary');

            const requestId = ++stockCardBreakdownRequestId;

            const qmRaw = String(qtyMode || '').toUpperCase();

            const resolvedQtyMode = qmRaw === 'BOTH' ? 'BOTH' : (qmRaw === 'SQTY' ? 'SQTY' : 'SUOMQTY');

            const batchParam = batchOpt != null ? String(batchOpt).trim() : '';

            if (dock) {

                dock.style.display = 'block';

                dock.setAttribute('aria-hidden', 'false');

            }

            syncStockDashboardSplitBodyClass();

            if (headingPrimary) headingPrimary.textContent = `${metricLabel(metricKey)} Breakdown`;

            if (subtitle) subtitle.textContent = `${itemCode} · ${locationCode}`;

            summary.innerHTML = 'Loading breakdown...';

            document.getElementById('stock-card-breakdown-thead').innerHTML = '<tr><th colspan="7">…</th></tr>';

            body.innerHTML = '<tr><td colspan="7" class="stock-card-status">Loading breakdown...</td></tr>';

            const fromDateInput = document.getElementById('stock-card-from-date');

            const fromDate = fromDateInput ? String(fromDateInput.value || '').trim() : '';

            const params = new URLSearchParams({

                item_code: itemCode,

                location: locationCode,

                metric: metricKey.replace('_by_location', ''),

                qty_mode: resolvedQtyMode,

            });

            if (fromDate) {

                params.set('from_date', fromDate);

                params.set('to_date', prTodayIso());

            }

            if (batchParam) {

                params.set('batch', batchParam);

            }

            fetch(`/api/admin/procurement/stock-card-breakdown?${params.toString()}`, { cache: 'no-store' })

                .then((res) => readProcurementJson(res))

                .then((payload) => {

                    if (requestId !== stockCardBreakdownRequestId) {

                        return;

                    }

                    if (!payload.success) {

                        throw new Error(payload.error || 'Failed to load breakdown');

                    }

                    if (headingPrimary) headingPrimary.textContent = payload.title || `${metricLabel(metricKey)} Breakdown`;

                    if (subtitle) subtitle.textContent = `${payload.item_code || itemCode} · ${payload.location || locationCode}`;

                    renderStockCardBreakdownTable(payload, metricKey);

                    const note = payload.summary && payload.summary.note ? escapeHtml(payload.summary.note) : '';

                    const valSq = payload.summary ? formatStockCardNumber(payload.summary.value) : '0';

                    const valSu = payload.summary && payload.summary.value_su != null && payload.summary.value_su !== undefined

                        ? formatStockCardNumber(payload.summary.value_su)

                        : null;

                    if (valSu != null) {

                        summary.innerHTML = `<strong>Total:</strong> ${valSq} <span class="stock-card-breakdown-note">(SQTY)</span> · ${valSu} <span class="stock-card-breakdown-note">(SUOMQTY)</span>${note ? ` <span class="stock-card-breakdown-note">${note}</span>` : ''}`;

                    } else {

                        summary.innerHTML = `<strong>Total:</strong> ${valSq}${note ? ` <span class="stock-card-breakdown-note">${note}</span>` : ''}`;

                    }

                })

                .catch((error) => {

                    if (isProcurementAuthExpired(error)) {
                        return;
                    }

                    if (requestId !== stockCardBreakdownRequestId) {

                        return;

                    }

                    summary.textContent = '';

                    document.getElementById('stock-card-breakdown-thead').innerHTML = '<tr><th colspan="7">Error</th></tr>';

                    body.innerHTML = `<tr><td colspan="7" class="stock-card-status">${escapeHtml(error.message || 'Failed to load breakdown.')}</td></tr>`;

                });

        }

        function closeStockCardBreakdown() {

            const dock = document.getElementById('stock-card-breakdown-dock');

            if (dock) {

                dock.style.display = 'none';

                dock.setAttribute('aria-hidden', 'true');

            }

            syncStockDashboardSplitBodyClass();

        }

        document.addEventListener('keydown', (ev) => {

            if (ev.key !== 'Escape') return;

            const dock = document.getElementById('stock-card-breakdown-dock');

            if (!dock || dock.style.display === 'none') return;

            closeStockCardBreakdown();

        });

        function buildStTrUdfSuomqtySummaryCard(summary) {

            if (!summary || typeof summary !== 'object') return '';

            const present = summary.udf_column_present === true;

            const valueHtml = present

                ? `<div class="report-summary-card-value">${formatStockCardNumber(summary.total)}</div><div class="report-summary-card-sublabel">Σ ST_TR.UDF_SUOMQTY</div>`

                : '<div class="report-summary-card-value">-</div><div class="report-summary-card-sublabel">Column not on ST_TR</div>';

            const note = summary.note

                ? `<div class="report-summary-card-note stock-card-breakdown-note">${escapeHtml(String(summary.note))}</div>`

                : '';

            return `

                <div class="report-summary-card report-summary-card--st-tr-udf" style="background:#e6eef8;color:#1a3550;">

                    <div class="report-summary-card-label">ST_TR UDF_SUOMQTY</div>

                    ${valueHtml}

                    ${note}

                </div>`;

        }

        function updateReportSummaryCards(rows, locations, stTrUdfSummary) {

            const el = document.getElementById('report-summary-cards');

            if (!el) return;

            const udfCardEarly = buildStTrUdfSuomqtySummaryCard(stTrUdfSummary);

            if (!rows || !rows.length) {

                el.innerHTML = udfCardEarly || '';

                return;

            }

            const locationColumns = Array.isArray(locations) ? locations : [];

            const sub = stockCardSubcolsPerLocation();

            const sumMapAllRows = (mapKey) => rows.reduce((acc, row) => acc + sumStockCardMapAcrossLocations(row, mapKey, locationColumns), 0);

            /* Summary cards always show full totals; table columns use Table columns checkboxes only. */

            const cards = [

                { label: 'Qty on Hand', maps: { sqty: 'avail_qty_sqty_by_location', suom: 'avail_qty_suom_by_location' }, bg: '#d8ecf8', color: '#124a5c' },

                { label: 'P.O Qty', maps: { sqty: 'po_qty_sqty_by_location', suom: 'po_qty_suom_by_location' }, bg: '#cfe6f5', color: '#153d66' },

                { label: 'S.O Qty', maps: { sqty: 'so_qty_sqty_by_location', suom: 'so_qty_suom_by_location' }, bg: '#d4e3f6', color: '#153d66' },

                { label: 'J.O Qty', maps: { sqty: 'jo_qty_sqty_by_location', suom: 'jo_qty_suom_by_location' }, bg: '#caf0e8', color: '#14532a' },

                { label: 'Avail. Qty', maps: { sqty: 'qty_sqty_by_location', suom: 'qty_suom_by_location' }, bg: '#dcd8f2', color: '#4a3168' },

                { label: 'Order', maps: { sqty: 'need_to_buy_sqty_by_location', suom: 'need_to_buy_suom_by_location' }, bg: '#f5d4dc', color: '#7a2222' },

                { label: 'Pending PR', maps: { sqty: 'pending_pr_sqty_by_location', suom: 'pending_pr_suom_by_location' }, bg: '#ccdff2', color: '#2d5a7a' },

            ];

            const metricCards = cards.map((c) => {

                const tSq = sumMapAllRows(c.maps.sqty);

                const tSu = sumMapAllRows(c.maps.suom);

                let valueHtml;

                if (sub === 2) {

                    valueHtml = `<div class="report-summary-card-value report-summary-card-value--dual"><span>${formatStockCardNumber(tSq)}</span><span class="report-summary-card-sep">/</span><span>${formatStockCardNumber(tSu)}</span></div><div class="report-summary-card-sublabel">SQTY / SUOMQTY</div>`;

                } else if (stockCardUomDisplayMode === 'suom_only') {

                    valueHtml = `<div class="report-summary-card-value">${formatStockCardNumber(tSu)}</div><div class="report-summary-card-sublabel">SUOMQTY</div>`;

                } else {

                    valueHtml = `<div class="report-summary-card-value">${formatStockCardNumber(tSq)}</div><div class="report-summary-card-sublabel">SQTY</div>`;

                }

                return `

                <div class="report-summary-card" style="background:${c.bg};color:${c.color};">

                    <div class="report-summary-card-label">${escapeHtml(String(c.label || '').toUpperCase())}</div>

                    ${valueHtml}

                </div>`;

            }).join('');

            el.innerHTML = udfCardEarly + metricCards;

        }

        function stockCardClickableQtyCell(bgClass, value, itemCode, locationCode, metricKey, qtyMode) {

            const jc = escapeJs(itemCode || '');

            const jl = escapeJs(locationCode || '');

            const jm = escapeJs(metricKey || '');

            const qm = qtyMode === 'SUOMQTY' ? 'SUOMQTY' : 'SQTY';

            return `<td class="${bgClass} stock-card-clickable-cell" title="Click to view breakdown (${qm})" onclick="openStockCardBreakdown('${jc}','${jl}','${jm}','${qm}')">${formatStockCardNumber(value)}</td>`;

        }

        function renderStockCardRows(rows, locations, stTrUdfSummary) {

            updateReportSummaryCards(rows, locations, stTrUdfSummary);

            const tbody = document.getElementById('stock-card-table-body');

            const locationColumns = Array.isArray(locations) ? locations : [];

            const noLocations = !locationColumns.length;

            const totalColumns = getStockCardTotalColumns(locationColumns);

            const sub = stockCardSubcolsPerLocation();

            const visibleMetricGroups = getVisibleStockCardMetricGroups();

            if (!visibleMetricGroups.length) {

                if (!rows || !rows.length) {

                    tbody.innerHTML = `<tr><td class="code-col stock-card-code-col--fixed">-</td><td class="stock-card-no-cols-msg stock-card-status">No stock items found.</td></tr>`;

                } else {

                    tbody.innerHTML = `<tr><td class="code-col stock-card-code-col--fixed">&nbsp;</td><td class="stock-card-no-cols-msg">No table column is selected</td></tr>`;

                }

                return;

            }

            if (!rows || !rows.length) {

                const q = String(stockCardItemSearch || '').trim();

                const emptyMsg =

                    q && stockCardRows && stockCardRows.length

                        ? 'No stock items match this code filter.'

                        : 'No stock items found.';

                tbody.innerHTML = `<tr><td colspan="${totalColumns}" class="stock-card-status">${escapeHtml(emptyMsg)}</td></tr>`;

                return;

            }

            const renderNeedBuyPair = (row, locationCode, idx, shortageSq, shortageSu) => {

                const itemCode = row.code || '';

                const bgClass = noLocations ? 'qty-col stock-card-expand' : `qty-col location-bg-${(idx % 10) + 1}`;

                const shortageSqNum = Math.max(0, Number(shortageSq || 0));

                const shortageSuNum = Math.max(0, Number(shortageSu || 0));

                const soloIsSu = stockCardUomDisplayMode === 'suom_only';

                const useForPr = sub === 2 ? shortageSuNum : (soloIsSu ? shortageSuNum : shortageSqNum);

                const key = buySelectionKey(itemCode, locationCode || '');

                const selection = stockCardBuySelections[key] || {

                    itemCode,

                    locationCode: locationCode || '',

                    selected: false,

                    quantity: useForPr,

                    quantitySq: shortageSqNum,

                };

                if (selection.quantitySq == null) selection.quantitySq = shortageSqNum;

                const qtyValSu = Number(selection.quantity != null ? selection.quantity : useForPr);

                const qtyStrSu = Number.isFinite(qtyValSu) ? String(qtyValSu) : String(useForPr);

                const qtyValSq = selection.quantitySq != null ? Number(selection.quantitySq) : shortageSqNum;

                const qtyStrSq = Number.isFinite(qtyValSq) ? String(qtyValSq) : String(shortageSqNum);

                const qtySolo = Number.isFinite(Number(selection.quantity)) ? Number(selection.quantity) : useForPr;

                const qtyStrSolo = String(qtySolo);

                const selectedClass = selection.selected ? ' need-buy-selected' : '';

                const jc = escapeJs(itemCode);

                const jl = escapeJs(locationCode || '');

                const dataItem = escapeHtml(itemCode);

                const dataLoc = escapeHtml(locationCode || '');

                const defPr = sub === 2 ? shortageSuNum : (soloIsSu ? shortageSuNum : shortageSqNum);

                if (sub === 2) {

                    const sqKey = buySelectionKey(itemCode, locationCode || '', 'SQTY');

                    const suKey = buySelectionKey(itemCode, locationCode || '', 'SUOMQTY');

                    const sqSelection = stockCardBuySelections[sqKey] || {

                        itemCode,

                        locationCode: locationCode || '',

                        selected: false,

                        quantity: shortageSqNum,

                        stockQtyUom: 'SQTY',

                    };

                    const sqQtyVal = Number(sqSelection.quantity != null ? sqSelection.quantity : shortageSqNum);

                    const derivedSuNum = stockCardDerivedSuomShortage(itemCode, sqQtyVal, shortageSuNum);

                    if (stockCardBuySelections[suKey]) {

                        stockCardBuySelections[suKey].quantity = derivedSuNum;

                    }

                    const sqQtyStr = Number.isFinite(sqQtyVal) ? String(sqQtyVal) : String(shortageSqNum);

                    const sqSelectedClass = sqSelection.selected ? ' need-buy-selected' : '';

                    const suCellTitle = prItemUdfWeight(typeof findPrProductByCode === 'function' ? findPrProductByCode(itemCode) : null) != null

                        ? 'SUOMQTY from SQTY × UDF_WTP; updates when you edit SQTY.'

                        : 'SUOMQTY shortage (from report).';

                    const sqTd = `

                        <td class="${bgClass} need-buy-td need-buy-td--sq need-buy-hitbox${sqSelectedClass}"

                            data-buy-item="${dataItem}" data-buy-loc="${dataLoc}" data-buy-default="${shortageSqNum}" data-buy-uom="SQTY"

                            onclick="stockCardNeedBuyCellClick(event, this)"

                            onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();stockCardNeedBuyCellClick(event, this);}"

                            tabindex="0"

                            title="SQTY for e-PR: click cell to include only SQTY; edit quantity"

                            ondblclick="openStockCardBreakdown('${jc}','${jl}','need_to_buy_by_location','SQTY')">

                            <div class="need-buy-editor need-buy-editor--solo need-buy-editor--with-cb">

                                <input type="text" inputmode="decimal" class="need-buy-qty-input need-buy-qty-input--text" autocomplete="off" value="${escapeHtml(sqQtyStr)}"

                                    title="SQTY shortage - editable"

                                    aria-label="SQTY need to buy"

                                    onclick="event.stopPropagation();" onkeydown="event.stopPropagation();"

                                    oninput="stockCardSetBuyQtySq('${jc}', '${jl}', ${shortageSqNum}, ${shortageSuNum}, this)" />

                                <input type="checkbox" class="need-buy-cb need-buy-cb--visual-off" title="Selected SQTY for PR" ${sqSelection.selected ? 'checked' : ''}

                                    aria-label="Selected SQTY for purchase request"

                                    onclick="event.stopPropagation(); stockCardSetBuyCheckbox('${jc}', '${jl}', ${shortageSqNum}, this, 'SQTY')" />

                            </div>

                        </td>`;

                    const editorTd = `

                        <td class="${bgClass} need-buy-td need-buy-td--su need-buy-td--su-static"

                            title="${escapeHtml(suCellTitle)}">

                            <div class="need-buy-editor need-buy-editor--su-static">

                                <span class="need-buy-readonly-qty" aria-label="SUOMQTY shortage">${formatStockCardNumber(derivedSuNum)}</span>

                            </div>

                        </td>`;

                    return sqTd + editorTd;

                }

                if (stockCardUomDisplayMode === 'suom_only') {

                    const suKeySolo = buySelectionKey(itemCode, locationCode || '', 'SUOMQTY');

                    if (stockCardBuySelections[suKeySolo]) {

                        stockCardBuySelections[suKeySolo].quantity = shortageSuNum;

                    }

                    return `

                    <td class="${bgClass} need-buy-td need-buy-td--su need-buy-td--su-static"

                        title="SUOMQTY shortage (from report).">

                        <div class="need-buy-editor need-buy-editor--su-static">

                            <span class="need-buy-readonly-qty" aria-label="SUOMQTY shortage">${formatStockCardNumber(shortageSuNum)}</span>

                        </div>

                    </td>`;

                }

                return `

                    <td class="${bgClass} need-buy-td need-buy-hitbox${selectedClass}"

                        data-buy-item="${dataItem}" data-buy-loc="${dataLoc}" data-buy-default="${defPr}" data-buy-uom="SQTY"

                        onclick="stockCardNeedBuyCellClick(event, this)"

                        onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();stockCardNeedBuyCellClick(event, this);}"

                        tabindex="0"

                        title="Click cell to select; edit quantity before New e-Purchase Request (SQTY basis)">

                        <div class="need-buy-editor">

                            <input type="text" inputmode="decimal" class="need-buy-qty-input need-buy-qty-input--text" autocomplete="off" value="${escapeHtml(qtyStrSolo)}"

                                title="SQTY shortage - editable"

                                onclick="event.stopPropagation();" onkeydown="event.stopPropagation();"

                                oninput="stockCardSetBuyQty('${jc}', '${jl}', ${shortageSqNum}, this, 'SQTY')" />

                            <input type="checkbox" class="need-buy-cb need-buy-cb--visual-off" title="Selected for PR" ${selection.selected ? 'checked' : ''}

                                aria-label="Selected for purchase request"

                                onclick="event.stopPropagation(); stockCardSetBuyCheckbox('${jc}', '${jl}', ${shortageSqNum}, this, 'SQTY')" />

                        </div>

                    </td>`;

            };

            const renderMetricGroup = (row, group) => {

                const sqKey = group.maps.sqty;

                const suKey = group.maps.suom;

                if (group.key === 'need_to_buy_by_location') {

                    if (noLocations) {

                        const tSq = sumStockCardMapAcrossLocations(row, sqKey, []);

                        const tSu = sumStockCardMapAcrossLocations(row, suKey, []);

                        if (sub === 2) {

                            return `<td class="qty-col stock-card-expand stock-card-cell-pair"><span class="stock-card-pair-line">${formatStockCardNumber(tSq)}</span><span class="stock-card-pair-line">${formatStockCardNumber(tSu)}</span></td>`;

                        }

                        return renderNeedBuyPair(row, '', 0, tSq, tSu);

                    }

                    let html = '';

                    locationColumns.forEach((locationCode, idx) => {

                        const shSq = Math.max(0, Number((row[sqKey] || {})[locationCode] || 0));

                        const shSu = Math.max(0, Number((row[suKey] || {})[locationCode] || 0));

                        html += renderNeedBuyPair(row, locationCode, idx, shSq, shSu);

                    });

                    return html;

                }

                if (group.key === 'pending_pr_by_location') {

                    if (noLocations) {

                        const tSq = sumStockCardMapAcrossLocations(row, sqKey, []);

                        const tSu = sumStockCardMapAcrossLocations(row, suKey, []);

                        if (sub === 2) {

                            return `<td class="qty-col stock-card-expand stock-card-cell-pair"><span class="stock-card-pair-line">${formatStockCardNumber(tSq)}</span><span class="stock-card-pair-line">${formatStockCardNumber(tSu)}</span></td>`;

                        }

                        if (stockCardUomDisplayMode === 'suom_only') {

                            return `<td class="qty-col stock-card-expand">${formatStockCardNumber(tSu)}</td>`;

                        }

                        return `<td class="qty-col stock-card-expand">${formatStockCardNumber(tSq)}</td>`;

                    }

                    let html = '';

                    locationColumns.forEach((locationCode, idx) => {

                        const bg = `qty-col location-bg-${(idx % 10) + 1}`;

                        const vSq = Number((row[sqKey] || {})[locationCode] || 0);

                        const vSu = Number((row[suKey] || {})[locationCode] || 0);

                        if (sub === 2) {

                            html += stockCardQtyCellForGroup(group, bg, vSq, row.code, locationCode, 'SQTY');

                            html += stockCardQtyCellForGroup(group, bg, vSu, row.code, locationCode, 'SUOMQTY');

                        } else if (stockCardUomDisplayMode === 'suom_only') {

                            html += stockCardQtyCellForGroup(group, bg, vSu, row.code, locationCode, 'SUOMQTY');

                        } else {

                            html += stockCardQtyCellForGroup(group, bg, vSq, row.code, locationCode, 'SQTY');

                        }

                    });

                    return html;

                }

                if (noLocations) {

                    const tSq = sumStockCardMapAcrossLocations(row, sqKey, []);

                    const tSu = sumStockCardMapAcrossLocations(row, suKey, []);

                    if (sub === 2) {

                        return `<td class="qty-col stock-card-expand stock-card-cell-pair"><span class="stock-card-pair-line">${formatStockCardNumber(tSq)}</span><span class="stock-card-pair-line">${formatStockCardNumber(tSu)}</span></td>`;

                    }

                    if (stockCardUomDisplayMode === 'suom_only') {

                        return `<td class="qty-col stock-card-expand">${formatStockCardNumber(tSu)}</td>`;

                    }

                    return `<td class="qty-col stock-card-expand">${formatStockCardNumber(tSq)}</td>`;

                }

                let html = '';

                locationColumns.forEach((locationCode, idx) => {

                    const bg = `qty-col location-bg-${(idx % 10) + 1}`;

                    const vSq = Number((row[sqKey] || {})[locationCode] || 0);

                    const vSu = Number((row[suKey] || {})[locationCode] || 0);

                    if (sub === 2) {

                        html += stockCardQtyCellForGroup(group, bg, vSq, row.code, locationCode, 'SQTY');

                        html += stockCardQtyCellForGroup(group, bg, vSu, row.code, locationCode, 'SUOMQTY');

                    } else if (stockCardUomDisplayMode === 'suom_only') {

                        html += stockCardQtyCellForGroup(group, bg, vSu, row.code, locationCode, 'SUOMQTY');

                    } else {

                        html += stockCardQtyCellForGroup(group, bg, vSq, row.code, locationCode, 'SQTY');

                    }

                });

                return html;

            };

            tbody.innerHTML = rows.map((row) => `

                <tr>

                    <td class="code-col${noLocations ? ' stock-card-expand' : ''}">${escapeHtml(row.code || '')}</td>

                    ${visibleMetricGroups.map((g) => renderMetricGroup(row, g)).join('')}

                </tr>

            `).join('');

        }

        function loadStockCardRows() {

            initStockCardUomDisplay();

            const tbody = document.getElementById('stock-card-table-body');

            const loadingColumns = getStockCardTotalColumns(selectedStockCardLocations);

            if (getVisibleStockCardMetricGroups().length === 0) {

                tbody.innerHTML = `<tr><td class="code-col stock-card-code-col--fixed">…</td><td class="stock-card-no-cols-msg stock-card-status">Loading stock items...</td></tr>`;

            } else {

                tbody.innerHTML = `<tr><td colspan="${loadingColumns}" class="stock-card-status">Loading stock items...</td></tr>`;

            }

            setStockCardTableNoMetricColsClass();

            const fromDateInput = document.getElementById('stock-card-from-date');

            const fromDate = fromDateInput ? String(fromDateInput.value || '').trim() : '';

            const query = new URLSearchParams();

            if (fromDate) {

                query.set('from_date', fromDate);

                query.set('to_date', prTodayIso());

            }

            query.set('qty_mode', stockCardUomDisplayMode === 'sqty_only' ? 'SQTY' : 'SUOMQTY');

            const requestUrl = query.toString()

                ? `/api/admin/procurement/stock-card?${query.toString()}`

                : '/api/admin/procurement/stock-card';

            fetch(requestUrl, { cache: 'no-store' })

                .then((res) => readProcurementJson(res))

                .then((payload) => {

                    if (!payload.success) {

                        throw new Error(payload.error || 'Failed to load stock items');

                    }

                    const locations = Array.isArray(payload.locations) ? payload.locations : [];

                    const avgMonthsRaw = Array.isArray(payload.avg_sales_3m_months)
                        ? payload.avg_sales_3m_months
                        : (payload.filters && Array.isArray(payload.filters.avg_sales_3m_months)
                            ? payload.filters.avg_sales_3m_months
                            : []);
                    stockCardAvgSales3mMonths = avgMonthsRaw.map((m) => String(m || '').trim()).filter(Boolean);

                    const previousSelected = Array.isArray(selectedStockCardLocations)

                        ? selectedStockCardLocations.slice()

                        : [];

                    stockCardLocations = locations.slice();

                    const locationSet = new Set(locations);

                    if (!reportLoaded) {

                        const persisted = readPersistedStockCardLocations();

                        const persistedValid = Array.isArray(persisted)

                            ? persisted.map((c) => String(c || '').trim()).filter(Boolean).filter((code) => locationSet.has(code))

                            : [];

                        if (persistedValid.length) {

                            selectedStockCardLocations = persistedValid;

                        } else {

                            selectedStockCardLocations = locations.slice();

                        }

                    } else {

                        const preserved = previousSelected.filter((code) => locationSet.has(code));

                        // Keep an intentional empty selection; otherwise fall back to all when none remain valid.

                        if (!previousSelected.length) {

                            selectedStockCardLocations = [];

                        } else {

                            selectedStockCardLocations = preserved.length ? preserved : locations.slice();

                        }

                    }

                    persistStockCardSelectedLocations();

                    stockCardRows = Array.isArray(payload.data) ? payload.data : [];

                    stockCardStTrUdfSummary = payload.st_tr_udf_suomqty && typeof payload.st_tr_udf_suomqty === 'object'

                        ? payload.st_tr_udf_suomqty

                        : null;

                    reportLoaded = true;

                    syncStockCardTable();

                })

                .catch((error) => {

                    if (isProcurementAuthExpired(error)) {
                        return;
                    }
                    console.error('Failed to load stock card rows:', error);

                    stockCardStTrUdfSummary = null;

                    const totalColumns = getStockCardTotalColumns(selectedStockCardLocations);

                    const msg = escapeHtml(error.message || 'Failed to load stock items.');

                    if (getVisibleStockCardMetricGroups().length === 0) {

                        tbody.innerHTML = `<tr><td class="code-col stock-card-code-col--fixed">-</td><td class="stock-card-no-cols-msg stock-card-status">${msg}</td></tr>`;

                    } else {

                        tbody.innerHTML = `<tr><td colspan="${totalColumns}" class="stock-card-status">${msg}</td></tr>`;

                    }

                    setStockCardTableNoMetricColsClass();

                });

        }

        function applyStockCardDateFilter() {
            try { closeStockReportSettingsDrawer(); } catch (e) {}

            loadStockCardRows();

        }

        function clearStockCardDateFilter() {
            try { closeStockReportSettingsDrawer(); } catch (e) {}

            const fromDateInput = document.getElementById('stock-card-from-date');

            if (fromDateInput) {

                fromDateInput.value = '';

            }

            loadStockCardRows();

        }

        function prTodayIso() {

            return new Date().toISOString().slice(0, 10);

        }

        function addDaysIso(baseIso, days) {

            const d = new Date(baseIso + 'T00:00:00');

            d.setDate(d.getDate() + days);

            return d.toISOString().slice(0, 10);

        }

        function showPurchaseRequestMessage(message, kind) {

            const el = document.getElementById('pr-form-message');

            if (!el) return;

            el.style.display = '';

            el.className = `pr-form-message ${kind || 'info'}`;

            el.textContent = message;

        }

        let prSuccessModalEscapeHandler = null;

        function closePurchaseRequestSuccessModal() {

            const modal = document.getElementById('pr-success-modal');

            if (modal) {

                modal.style.display = 'none';

                modal.setAttribute('aria-hidden', 'true');

            }

            if (prSuccessModalEscapeHandler) {

                document.removeEventListener('keydown', prSuccessModalEscapeHandler);

                prSuccessModalEscapeHandler = null;

            }

        }

        /**

         * In-app success dialog (replaces browser alert after PR submit).

         * @param {string} title - Short heading

         * @param {string} body - One or two sentences

         * @param {string|null|undefined} requestNumber - Shown prominently when provided

         */

        function showPurchaseRequestSuccessModal(title, body, requestNumber) {

            const modal = document.getElementById('pr-success-modal');

            const titleEl = document.getElementById('pr-success-modal-title');

            const bodyEl = document.getElementById('pr-success-modal-body');

            const wrap = document.getElementById('pr-success-modal-pr-wrap');

            const numEl = document.getElementById('pr-success-modal-request-no');

            const okBtn = document.getElementById('pr-success-modal-ok');

            if (!modal || !titleEl || !bodyEl) return;

            titleEl.textContent = title || 'Success';

            bodyEl.textContent = body || '';

            const rn = requestNumber != null ? String(requestNumber).trim() : '';

            if (rn && wrap && numEl) {

                numEl.textContent = rn;

                wrap.style.display = '';

            } else if (wrap) {

                wrap.style.display = 'none';

            }

            modal.style.display = '';

            modal.setAttribute('aria-hidden', 'false');

            if (prSuccessModalEscapeHandler) {

                document.removeEventListener('keydown', prSuccessModalEscapeHandler);

            }

            prSuccessModalEscapeHandler = (e) => {

                if (e.key === 'Escape') {

                    e.preventDefault();

                    closePurchaseRequestSuccessModal();

                }

            };

            document.addEventListener('keydown', prSuccessModalEscapeHandler);

            if (okBtn) {

                setTimeout(() => okBtn.focus(), 0);

            }

        }

        function applyPurchaseRequestFormModeUI() {

            const isEditMode = Boolean(prFormEditState && prFormEditState.requestId);

            const titleEl = document.getElementById('pr-form-title');

            const submitBtn = document.getElementById('pr-submit-btn');

            const draftBtn = document.getElementById('pr-save-draft-btn');

            const cancelBtn = document.getElementById('pr-cancel-edit-btn');

            const addItemBtn = document.getElementById('pr-add-item-btn');

            if (titleEl) {

                titleEl.textContent = isEditMode

                    ? `Edit e-Purchase Request ${prFormEditState.requestNumber || ''}`.trim()

                    : 'Create e-Purchase Request';

            }

            if (submitBtn) {

                submitBtn.textContent = isEditMode ? 'Submit PR' : 'Submit Purchase Request';

            }

            if (draftBtn) {

                draftBtn.style.display = '';

                draftBtn.textContent = isEditMode ? 'Update Draft' : 'Save as Draft';

            }

            if (cancelBtn) {

                cancelBtn.style.display = isEditMode ? '' : 'none';

            }

            if (addItemBtn) {

                addItemBtn.disabled = isEditMode;

                addItemBtn.title = isEditMode ? 'Adding new lines is not supported in edit mode.' : '';

            }

        }

        function cancelPurchaseRequestEditMode() {

            prFormEditState = null;

            initPurchaseRequestForm();

            showTab('view');

        }

        let prCatalogProducts = [];

        let prWarehouseLocations = [];

        let prProductUomCache = {};

        let prProductUomInFlight = new Set();

        function getDefaultLineLocation() {

            return (Array.isArray(prWarehouseLocations) && prWarehouseLocations.length)

                ? String(prWarehouseLocations[0])

                : '';

        }

        function getPrimarySupplierCurrency() {

            const s = (typeof selectedSuppliers !== 'undefined' && selectedSuppliers && selectedSuppliers[0]) ? selectedSuppliers[0] : null;

            if (!s) {

                return '';

            }

            const raw = s.currency ?? s.currencyCode ?? s.currencycode ?? s.CURRENCYCODE;

            const c = String(raw || '').trim();

            if (!c || c === '----' || c === '-') return '';
            return c;

        }

        async function loadPrWarehouseLocations() {

            try {

                const res = await fetch('/api/admin/procurement/locations');

                const data = await readProcurementJson(res);

                if (data.success && Array.isArray(data.locations)) {

                    prWarehouseLocations = data.locations;

                } else {

                    prWarehouseLocations = [];

                }

            } catch (e) {

                console.warn('[PR locations] load failed', e);

                prWarehouseLocations = [];

            }

            if (window.purchaseRequestItems && window.purchaseRequestItems.length) {

                const def = getDefaultLineLocation();

                if (def) {

                    window.purchaseRequestItems.forEach((it) => {

                        if (!String((it && it.locationCode) || '').trim()) {

                            it.locationCode = def;

                        }

                    });

                }

                renderPurchaseRequestLineItems();

            }

        }

        function buildPrLocationOptions(selectedCode) {

            const locs = prWarehouseLocations || [];

            const first = locs.length ? String(locs[0]).trim() : '';

            const sel = String(selectedCode || '').trim() || first;

            if (!locs.length) {

                return '<option value="">- No locations -</option>';

            }

            return locs

                .map((code) => {

                    const c = String(code || '').trim();

                    if (!c) return '';

                    const isSel = c === sel ? ' selected' : '';

                    return `<option value="${escapeHtml(c)}"${isSel}>${escapeHtml(c)}</option>`;

                })

                .filter(Boolean)

                .join('');

        }

        function onPurchaseRequestLocationChange(index, value) {

            if (prFormEditState && prFormEditState.requestId) {

                return;

            }

            if (!window.purchaseRequestItems || !window.purchaseRequestItems[index]) {

                return;

            }

            window.purchaseRequestItems[index].locationCode = String(value || '').trim();

        }

        function findPrProductByCode(itemCode) {

            const code = String(itemCode || '').trim();

            if (!code) return null;

            const codeUpper = code.toUpperCase();
            return prCatalogProducts.find((p) => {
                const c = String((p && (p.CODE != null ? p.CODE : p.code)) || '').trim();
                return c.toUpperCase() === codeUpper;
            }) || null;

        }

        function getPrProductUomOptions(product, itemCode) {

            const out = [];

            const seen = new Set();

            const pushUom = (raw) => {

                const v = String(raw || '').trim();

                if (!v) return;

                const k = v.toUpperCase();

                if (seen.has(k)) return;

                seen.add(k);

                out.push(v);

            };

            if (product && typeof product === 'object') {

                pushUom(product.uom);

                pushUom(product.UOM);

                let rows = [];

                if (Array.isArray(product.sdsuom)) {

                    rows = product.sdsuom;

                } else if (Array.isArray(product.SDSUOM)) {

                    rows = product.SDSUOM;

                } else if (typeof product.sdsuom === 'string' && product.sdsuom.trim()) {

                    try {

                        const parsed = JSON.parse(product.sdsuom);

                        rows = Array.isArray(parsed) ? parsed : [];

                    } catch (e) {

                        rows = [];

                    }

                } else if (typeof product.SDSUOM === 'string' && product.SDSUOM.trim()) {

                    try {

                        const parsed = JSON.parse(product.SDSUOM);

                        rows = Array.isArray(parsed) ? parsed : [];

                    } catch (e) {

                        rows = [];

                    }

                }

                rows.forEach((row) => {

                    if (!row || typeof row !== 'object') return;

                    pushUom(row.uom);

                    pushUom(row.UOM);

                });

            }

            const code = String(itemCode || (product && (product.CODE != null ? product.CODE : product.code)) || '').trim();

            const cached = code ? prProductUomCache[code] : null;

            if (Array.isArray(cached)) {

                cached.forEach((u) => pushUom(u));

            }

            if (!out.length) pushUom('UNIT');

            return out;

        }

        function ensurePrLineUom(item, product) {

            if (!item) return '';

            const options = getPrProductUomOptions(product, item.itemCode);

            const current = String(item.uom || item.UOM || '').trim();

            if (current && options.some((u) => String(u).toUpperCase() === current.toUpperCase())) {

                item.uom = current;

                return current;

            }

            item.uom = options[0] || '';

            return item.uom;

        }

        function buildPrLineUomOptions(item, product) {

            const selected = ensurePrLineUom(item, product);

            return getPrProductUomOptions(product, item.itemCode)

                .map((u) => {

                    const su = String(u || '').trim();

                    if (!su) return '';

                    const isSel = su.toUpperCase() === String(selected || '').toUpperCase() ? ' selected' : '';

                    return `<option value="${escapeHtml(su)}"${isSel}>${escapeHtml(su)}</option>`;

                })

                .filter(Boolean)

                .join('');

        }

        async function prefetchPrProductUoms(itemCode) {

            const code = String(itemCode || '').trim();

            if (!code) return;

            if (Array.isArray(prProductUomCache[code]) && prProductUomCache[code].length) return;

            if (prProductUomInFlight.has(code)) return;

            prProductUomInFlight.add(code);

            try {

                const res = await fetch(`/api/admin/procurement/stock-item-uoms?code=${encodeURIComponent(code)}`);

                const data = await readProcurementJson(res);

                if (res.ok && data && data.success && Array.isArray(data.uoms) && data.uoms.length) {

                    prProductUomCache[code] = data.uoms.map((u) => String(u || '').trim()).filter(Boolean);

                    if (window.purchaseRequestItems && window.purchaseRequestItems.length) {

                        window.purchaseRequestItems.forEach((it) => {

                            if (String(it.itemCode || '').trim() === code) {

                                ensurePrLineUom(it, findPrProductByCode(code));

                            }

                        });

                        renderPurchaseRequestLineItems();

                    }

                }

            } catch (e) {

                console.warn('[PR UOM] Failed to load per-item UOM list:', e);

            } finally {

                prProductUomInFlight.delete(code);

            }

        }

        function onPurchaseRequestUomChange(index, value) {

            if (prFormEditState && prFormEditState.requestId) return;

            if (!window.purchaseRequestItems || !window.purchaseRequestItems[index]) return;

            window.purchaseRequestItems[index].uom = String(value || '').trim();

        }

        function buildPrProductOptions(selectedCode) {

            const selected = String(selectedCode || '').trim();

            const options = ['<option value="">Select product...</option>'];

            prCatalogProducts.forEach((p) => {

                const code = String((p && (p.CODE != null ? p.CODE : p.code)) || '').trim();

                const desc = String((p && (p.DESCRIPTION != null ? p.DESCRIPTION : p.description)) || code || '').trim();

                if (!code || !desc) return;

                const isSelected = code === selected ? ' selected' : '';

                options.push(`<option value="${escapeHtml(code)}"${isSelected}>${escapeHtml(desc)}</option>`);

            });

            return options.join('');

        }

        function prCatalogLowerMap(obj) {
            const out = {};
            if (!obj || typeof obj !== 'object') return out;
            Object.keys(obj).forEach((k) => { out[String(k).toLowerCase()] = obj[k]; });
            return out;
        }

        function prCatalogScalar(product, ...keys) {
            if (!product || typeof product !== 'object') return '';
            const lower = prCatalogLowerMap(product);
            for (const key of keys) {
                const k = String(key || '');
                const v = product[k] != null
                    ? product[k]
                    : product[k.toUpperCase()] != null
                        ? product[k.toUpperCase()]
                        : lower[k.toLowerCase()];
                if (v == null) continue;
                const s = String(v).trim();
                if (s) return s;
            }
            return '';
        }

        function resolvePrCatalogTradeUom(product) {
            const u2 = prCatalogScalar(product, 'udf_2uom', 'UDF_2UOM');
            if (u2) return u2;
            const su = prCatalogScalar(product, 'suom', 'SUOM');
            if (su) return su;
            let rows = product && (product.sdsuom || product.SDSUOM);
            if (typeof rows === 'string' && rows.trim()) {
                try { rows = JSON.parse(rows); } catch (e) { rows = []; }
            }
            if (Array.isArray(rows)) {
                const baseRow = rows.find((r) => r && (r.isbase === true || String(r.isbase || '').toLowerCase() === 'true'));
                if (baseRow) {
                    const u = String((baseRow.uom != null ? baseRow.uom : baseRow.UOM) || '').trim();
                    if (u) return u;
                }
                for (const row of rows) {
                    const u = String((row && (row.uom != null ? row.uom : row.UOM)) || '').trim();
                    if (u) return u;
                }
            }
            return prCatalogScalar(product, 'uom', 'UOM');
        }

        function prCatalogProductCode(p) {
            return prCatalogScalar(p, 'CODE', 'code');
        }

        function prCatalogProductDesc(p) {
            return prCatalogScalar(p, 'DESCRIPTION', 'description') || prCatalogProductCode(p);
        }

        function prProductLabel(product) {
            const code = prCatalogProductCode(product);
            const desc = prCatalogProductDesc(product);
            if (!code) return desc;
            return desc && desc !== code ? `${code} — ${desc}` : code;
        }

        function normalizePrProductSearchText(value) {
            return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ');
        }

        let prCatalogPickerActiveInput = null;
        let prCatalogPickerActiveLineIndex = null;
        let prCatalogPickerCloseTimer = null;

        function getPrCatalogPickerOptions() {
            const options = [];
            const seen = new Set();
            (prCatalogProducts || []).forEach((p) => {
                const code = prCatalogProductCode(p);
                const desc = prCatalogProductDesc(p);
                if (!code) return;
                const key = normalizePrProductSearchText(code);
                if (seen.has(key)) return;
                seen.add(key);
                options.push({
                    code,
                    desc,
                    label: prProductLabel(p),
                });
            });
            options.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
            return options;
        }

        function ensurePrCatalogProductPicker() {
            let picker = document.getElementById('pr-catalog-product-picker');
            if (picker) return picker;
            picker = document.createElement('div');
            picker.id = 'pr-catalog-product-picker';
            picker.className = 'pr-catalog-product-picker';
            picker.hidden = true;
            picker.innerHTML = `
                <div class="pr-catalog-product-picker-header">Choose product</div>
                <input type="text" class="pr-catalog-product-picker-search" placeholder="Type to filter…" autocomplete="off" />
                <ul class="pr-catalog-product-picker-list" role="listbox"></ul>`;
            document.body.appendChild(picker);

            const search = picker.querySelector('.pr-catalog-product-picker-search');
            search.addEventListener('input', () => {
                if (prCatalogPickerActiveLineIndex != null) {
                    renderPrCatalogProductPickerList(prCatalogPickerActiveLineIndex, search.value);
                }
            });
            search.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') hidePrCatalogProductPicker();
            });
            document.addEventListener('mousedown', (event) => {
                if (picker.hidden) return;
                if (picker.contains(event.target)) return;
                if (event.target === prCatalogPickerActiveInput) return;
                hidePrCatalogProductPicker();
            });
            return picker;
        }

        function positionPrCatalogProductPicker(input, picker) {
            const rect = input.getBoundingClientRect();
            const width = Math.max(rect.width, 380);
            let left = rect.left;
            let top = rect.bottom + 4;
            if (left + width > window.innerWidth - 8) {
                left = Math.max(8, window.innerWidth - width - 8);
            }
            const maxHeight = 300;
            if (top + maxHeight > window.innerHeight - 8) {
                top = Math.max(8, rect.top - maxHeight - 4);
            }
            picker.style.left = `${left}px`;
            picker.style.top = `${top}px`;
            picker.style.width = `${width}px`;
        }

        function renderPrCatalogProductPickerList(lineIndex, filterText) {
            const picker = ensurePrCatalogProductPicker();
            const list = picker.querySelector('.pr-catalog-product-picker-list');
            const query = normalizePrProductSearchText(filterText);
            const item = window.purchaseRequestItems && window.purchaseRequestItems[lineIndex];
            const currentCode = item ? normalizePrProductSearchText(item.itemCode) : '';
            const matches = getPrCatalogPickerOptions().filter((opt) => {
                if (!query) return true;
                const blob = normalizePrProductSearchText(`${opt.label} ${opt.code} ${opt.desc}`);
                return blob.includes(query);
            });

            list.innerHTML = '';
            if (!matches.length) {
                const empty = document.createElement('li');
                empty.className = 'pr-catalog-product-picker-empty';
                empty.textContent = 'No products match';
                list.appendChild(empty);
                return;
            }

            const limit = 150;
            matches.slice(0, limit).forEach((opt) => {
                const row = document.createElement('li');
                row.className = 'pr-catalog-product-picker-option';
                row.setAttribute('role', 'option');
                row.textContent = opt.label;
                if (normalizePrProductSearchText(opt.code) === currentCode) {
                    row.classList.add('is-current');
                }
                row.addEventListener('mousedown', (event) => {
                    event.preventDefault();
                    applyPrCatalogProductSelection(lineIndex, opt.code);
                });
                list.appendChild(row);
            });
            if (matches.length > limit) {
                const more = document.createElement('li');
                more.className = 'pr-catalog-product-picker-more';
                more.textContent = `Showing ${limit} of ${matches.length} — type to narrow`;
                list.appendChild(more);
            }
        }

        function applyPrCatalogProductSelection(lineIndex, code) {
            hidePrCatalogProductPicker();
            onPurchaseRequestProductChange(lineIndex, code);
        }

        function showPrCatalogProductPicker(input, lineIndex) {
            if (!input || !Number.isFinite(lineIndex)) return;
            clearTimeout(prCatalogPickerCloseTimer);
            const picker = ensurePrCatalogProductPicker();
            prCatalogPickerActiveInput = input;
            prCatalogPickerActiveLineIndex = lineIndex;
            positionPrCatalogProductPicker(input, picker);
            const search = picker.querySelector('.pr-catalog-product-picker-search');
            search.value = '';
            renderPrCatalogProductPickerList(lineIndex, '');
            picker.hidden = false;
            requestAnimationFrame(() => search.focus());
        }

        function hidePrCatalogProductPicker() {
            const picker = document.getElementById('pr-catalog-product-picker');
            if (picker) picker.hidden = true;
            prCatalogPickerActiveInput = null;
            prCatalogPickerActiveLineIndex = null;
        }

        function bindPrCatalogProductInput(input) {
            if (!input || input.dataset.prCatalogPickerBound === '1') return;
            const lineIndex = parseInt(input.getAttribute('data-pr-index'), 10);
            if (!Number.isFinite(lineIndex)) return;
            input.dataset.prCatalogPickerBound = '1';
            input.setAttribute('autocomplete', 'off');
            input.setAttribute('spellcheck', 'false');
            if (!input.placeholder) {
                input.placeholder = 'Search or pick product…';
            }

            const openPicker = () => showPrCatalogProductPicker(input, lineIndex);
            input.addEventListener('focus', openPicker);
            input.addEventListener('click', openPicker);
            input.addEventListener('input', () => {
                if (prCatalogPickerActiveInput !== input) return;
                const picker = document.getElementById('pr-catalog-product-picker');
                const search = picker ? picker.querySelector('.pr-catalog-product-picker-search') : null;
                if (search) {
                    search.value = input.value;
                    renderPrCatalogProductPickerList(lineIndex, input.value);
                }
            });
            input.addEventListener('blur', () => {
                prCatalogPickerCloseTimer = setTimeout(hidePrCatalogProductPicker, 200);
            });

            const cell = input.closest('td');
            if (cell) cell.classList.add('pr-catalog-product-cell');
        }

        function initPrCatalogProductPickers() {
            document.querySelectorAll('#pr-line-items-body .pr-catalog-product-input').forEach((input) => {
                bindPrCatalogProductInput(input);
            });
        }

        function prCatalogUdfValue(product, key) {
            const v = prCatalogScalar(product, key, key.toUpperCase());
            if (!v) return '';
            if (String(v).trim() === '0') return '';
            return v;
        }

        function updatePurchaseRequestRowAmount(index) {

            const items = window.purchaseRequestItems || [];

            const item = items[index];

            if (!item) return;

            const pq = linePricingQty(item);

            const unitPrice = Number(item.unitPrice || 0);

            const amountCell = document.getElementById(`pr-amount-${index}`);

            if (amountCell) {

                amountCell.textContent = formatMoney(pq * unitPrice);

            }

        }

        function isPlaceholderPrLineDescription(value) {
            const text = String(value || '').trim();
            return /^Auto-selected from Overall Report/i.test(text);
        }

        function resolvePrLineDescription(item) {
            if (!item || typeof item !== 'object') {
                return '';
            }
            const code = String(item.itemCode || '').trim();
            const product = code && typeof findPrProductByCode === 'function' ? findPrProductByCode(code) : null;
            const catalogDesc = product
                ? String((product.DESCRIPTION != null ? product.DESCRIPTION : product.description) || '').trim()
                : '';
            const stored = String(item.description || item.itemName || '').trim();
            if (catalogDesc && (!stored || isPlaceholderPrLineDescription(stored))) {
                return catalogDesc;
            }
            if (stored && !isPlaceholderPrLineDescription(stored)) {
                return stored;
            }
            return catalogDesc || code || stored;
        }

        function onPurchaseRequestProductChange(index, itemCode) {

            if (prFormEditState && prFormEditState.requestId) return;

            if (!window.purchaseRequestItems || !window.purchaseRequestItems[index]) return;

            const code = String(itemCode || '').trim();

            const item = window.purchaseRequestItems[index];

            const product = findPrProductByCode(code);

            item.itemCode = code;

            if (product) {

                const description = String((product.DESCRIPTION != null ? product.DESCRIPTION : product.description) || code).trim();

                item.itemName = description;

                item.description = description;

            }

            ensurePrLineUom(item, product);
            prefetchPrProductUoms(code);
            cachePrLineUdfWtp(item, product);
            mergePrLineCatalogUdfs(item, product);
            applyPrLineSuomFromSqtyUdfWeight(item);

            syncPrLineQuantityDerived(item);

            renderPurchaseRequestLineItems();

        }

        async function loadPurchaseRequestProducts() {

            try {

                const response = await fetch('/api/get_stock_items');

                const data = await readProcurementJson(response);

                if (data.success && Array.isArray(data.items)) {

                    prCatalogProducts = data.items;

                    if (window.purchaseRequestItems && window.purchaseRequestItems.length) {

                        window.purchaseRequestItems.forEach((it) => {
                        mergePrLineCatalogUdfs(it, null);
                        cachePrLineUdfWtp(it, null);
                        if (resolvePrLineUdfWeight(it) != null && Number(it.qtySqty || 0) > 0) {
                            applyPrLineSuomFromSqtyUdfWeight(it);
                            syncPrLineQuantityDerived(it);
                        }
                    });

                        renderPurchaseRequestLineItems();

                    }

                }

            } catch (error) {

                console.warn('[PR Products] Failed to load product list:', error);

            }

        }

        function syncDeliveryLocationToLineItems() {

            // Line warehouse locations are chosen per line (dropdown), not copied from the header address field.

        }

        function bindPurchaseRequestDeliveryLocationSync() {

            const el = document.getElementById('pr-delivery-location');

            if (!el || el.dataset.prLocBound === '1') {

                return;

            }

            el.dataset.prLocBound = '1';

            const handler = () => syncDeliveryLocationToLineItems();

            el.addEventListener('input', handler);

            el.addEventListener('change', handler);

        }

        function renderPurchaseRequestLineItems() {

            const body = document.getElementById('pr-line-items-body');

            if (!body) return;

            const isEditMode = Boolean(prFormEditState && prFormEditState.requestId);

            if (!window.purchaseRequestItems || !window.purchaseRequestItems.length) {

                const selectedProjectCode = getSelectedProjectCode();

                const defLoc = getDefaultLineLocation();

                const today = prTodayIso();

                const defU = defaultPrStockQtyUom();

                const blank = {

                    itemCode: '',

                    itemName: '',

                    locationCode: defLoc,

                    description: '',

                    uom: '',

                    udfReason: '',

                    project: selectedProjectCode,

                    qtySqty: defU === 'SQTY' ? 1 : 0,

                    qtySuomqty: defU === 'SUOMQTY' ? 1 : 0,

                    quantity: 1,

                    unitPrice: 0,

                    deliveryDate: today,

                    stockQtyUom: defU,

                };

                syncPrLineQuantityDerived(blank);

                window.purchaseRequestItems = [blank];

            }

            window.purchaseRequestItems.forEach((it) => {

                if (it.qtySqty == null && it.qtySuomqty == null) {

                    const q = Number(it.quantity || 0);

                    const basis = String(it.stockQtyUom || defaultPrStockQtyUom()).toUpperCase();

                    it.qtySqty = basis === 'SQTY' ? q : 0;

                    it.qtySuomqty = basis === 'SUOMQTY' ? q : 0;

                }

                syncPrLineQuantityDerived(it);

            });

            body.innerHTML = window.purchaseRequestItems.map((item, idx) => {

                const product = findPrProductByCode(item.itemCode);

                if (item.itemCode) prefetchPrProductUoms(item.itemCode);

                if (product) {

                    const dn = String(product.DESCRIPTION || item.itemName || '').trim();

                    if (dn) item.itemName = dn;

                    if (!String(item.description || '').trim() || isPlaceholderPrLineDescription(item.description)) {
                        item.description = dn;
                    }

                }

                ensurePrLineUom(item, product);
                mergePrLineCatalogUdfs(item, product);

                if (!isEditMode) {

                    const def = getDefaultLineLocation();

                    if (def && !String(item.locationCode || '').trim()) {

                        item.locationCode = def;

                    }

                }

                const qtySqty = Number(item.qtySqty || 0);

                const qtySuomqty = Number(item.qtySuomqty || 0);

                const suomFromUdf = prItemUdfWeight(product) != null;

                const suomTitle = suomFromUdf

                    ? 'SUOMQTY from SQTY × UDF_WTP (read-only)'

                    : 'Stock quantity (SUOMQTY, read-only)';

                const pq = linePricingQty(item);

                const unitPrice = Number(item.unitPrice || 0);

                const amount = pq * unitPrice;

                const locVal = String(item.locationCode || '').trim();

                const locHtml = isEditMode

                    ? (locVal ? `<span class="pr-loc-readonly" title="${escapeHtml(locVal)}">${escapeHtml(locVal)}</span>` : '<span class="pr-loc-readonly pr-loc-placeholder">-</span>')

                    : `<select class="pr-line-location-select" onchange="onPurchaseRequestLocationChange(${idx}, this.value)">${buildPrLocationOptions(locVal)}</select>`;

                return `

                    <tr data-pr-index="${idx}">

                        <td class="pr-loc-cell">${locHtml}</td>

                        <td class="pr-item-code-cell">
                            <span class="pr-item-code-readonly" title="${escapeHtml(item.itemCode || '')}">${escapeHtml(item.itemCode || '-')}</span>
                        </td>

                        <td class="pr-code-cell">
                            ${isEditMode
                                ? `<span class="pr-desc-readonly" title="${escapeHtml(item.itemCode || '')}">${escapeHtml(prCatalogProductDesc(product || { CODE: item.itemCode || '', DESCRIPTION: item.itemCode || '' }) || '-')}</span>`
                                : `<input type="text" class="pr-catalog-product-input" data-pr-index="${idx}" value="${escapeHtml(prCatalogProductDesc(product || { CODE: item.itemCode || '', DESCRIPTION: item.itemCode || '' }))}" placeholder="Search or pick product…" autocomplete="off" spellcheck="false" />`}
                        </td>

                        <td class="pr-udf-cell">${isEditMode
                            ? `<span class="pr-udf-readonly">${escapeHtml(prLineDimValue(item, product, 'udf_thickness') || '-')}</span>`
                            : `<input type="number" class="pr-udf-input" min="0" step="0.01" data-pr-field="udf_thickness" value="${escapeHtml(prLineDimValue(item, product, 'udf_thickness'))}" oninput="updatePurchaseRequestDimension(${idx}, 'udf_thickness', this.value)" title="Thickness (mm)" />`}</td>
                        <td class="pr-udf-cell">${isEditMode
                            ? `<span class="pr-udf-readonly">${escapeHtml(prLineDimValue(item, product, 'udf_width') || '-')}</span>`
                            : `<input type="number" class="pr-udf-input" min="0" step="0.01" data-pr-field="udf_width" value="${escapeHtml(prLineDimValue(item, product, 'udf_width'))}" oninput="updatePurchaseRequestDimension(${idx}, 'udf_width', this.value)" title="Width (mm)" />`}</td>
                        <td class="pr-udf-cell">${isEditMode
                            ? `<span class="pr-udf-readonly">${escapeHtml(prLineDimValue(item, product, 'udf_length') || '-')}</span>`
                            : `<input type="number" class="pr-udf-input" min="0" step="0.01" data-pr-field="udf_length" value="${escapeHtml(prLineDimValue(item, product, 'udf_length'))}" oninput="updatePurchaseRequestDimension(${idx}, 'udf_length', this.value)" title="Length (mm)" />`}</td>
                        <td class="pr-udf-readonly">${escapeHtml(prCatalogUdfValue(product, 'udf_dp') || '-')}</td>
                        <td class="pr-udf-readonly">${escapeHtml(prCatalogUdfValue(product, 'udf_dfp') || '-')}</td>
                        <td class="pr-udf-readonly">${escapeHtml(prCatalogUdfValue(product, 'udf_costkg') || '-')}</td>
                        <td class="pr-udf-readonly">${escapeHtml(prCatalogUdfValue(product, 'udf_formula') || '-')}</td>

                        <td class="pr-stock-uom-cell"><span class="pr-stock-uom-readonly">${escapeHtml(resolvePrCatalogTradeUom(product) || '')}</span></td>

                        <td class="pr-qty-cell"><input type="number" class="pr-input-qty" data-pr-field="qtySqty" min="0" step="0.0001" value="${escapeHtml(qtySqty)}" oninput="updatePurchaseRequestItem(${idx}, 'qtySqty', this.value)" title="Stock quantity (SQTY)" /></td>

                        <td class="pr-qty-cell pr-qty-cell--suom">

                            <span class="pr-suom-readonly" data-pr-field="qtySuomqty" title="${escapeHtml(suomTitle)}">${formatStockCardNumber(qtySuomqty)}</span>

                        </td>

                        <td><input type="number" min="0" step="0.01" value="${escapeHtml(item.unitPrice || 0)}" oninput="updatePurchaseRequestItem(${idx}, 'unitPrice', this.value)" /></td>

                        <td><input type="date" value="${escapeHtml(item.deliveryDate || '')}" oninput="updatePurchaseRequestItem(${idx}, 'deliveryDate', this.value)" /></td>

                        <td class="pr-amount-cell" id="pr-amount-${idx}">${formatMoney(amount)}</td>

                        <td><button type="button" class="pr-row-remove" onclick="removePurchaseRequestLineItem(${idx})" ${isEditMode ? 'disabled title="Removing lines is not supported in edit mode."' : ''}>x</button></td>

                    </tr>

                `;

            }).join('');

            recalcPurchaseRequestTotals();
            initPrCatalogProductPickers();
            savePurchaseRequestDraftItems();

        }

        function updatePurchaseRequestItem(index, key, value) {

            if (!window.purchaseRequestItems || !window.purchaseRequestItems[index]) return;

            if (key === 'qtySqty' || key === 'qtySuomqty' || key === 'quantity' || key === 'unitPrice') {

                const num = Number(value);

                window.purchaseRequestItems[index][key] = Number.isFinite(num) ? num : 0;

                if (key === 'qtySqty' || key === 'qtySuomqty') {
                    const item = window.purchaseRequestItems[index];
                    if (key === 'qtySqty') {
                        const row = document.querySelector(`#pr-line-items-body tr[data-pr-index="${index}"]`);
                        const sqInputEl = row ? row.querySelector('[data-pr-field="qtySqty"]') : null;
                        refreshPrLineSuomQtyDisplay(index, item, sqInputEl);
                    } else {
                        syncPrLineQuantityDerived(item);
                    }
                    updatePurchaseRequestRowAmount(index);
                    recalcPurchaseRequestTotals();
                    return;
                }

            } else {

                window.purchaseRequestItems[index][key] = value;

            }

            updatePurchaseRequestRowAmount(index);

            recalcPurchaseRequestTotals();

        }

        function addPurchaseRequestLineItem() {

            if (prFormEditState && prFormEditState.requestId) {

                showPurchaseRequestMessage('Adding new lines is not supported while editing an existing purchase request.', 'error');

                return;

            }

            if (!window.purchaseRequestItems) window.purchaseRequestItems = [];

            const selectedProjectCode = getSelectedProjectCode();

            const today = prTodayIso();

            const defU = defaultPrStockQtyUom();

            const row = {

                itemCode: '',

                itemName: '',

                locationCode: getDefaultLineLocation(),

                description: '',

                uom: '',

                udfReason: '',

                project: selectedProjectCode,

                qtySqty: defU === 'SQTY' ? 1 : 0,

                qtySuomqty: defU === 'SUOMQTY' ? 1 : 0,

                quantity: 1,

                unitPrice: 0,

                deliveryDate: today,

                stockQtyUom: defU,

            };

            syncPrLineQuantityDerived(row);

            window.purchaseRequestItems.push(row);

            renderPurchaseRequestLineItems();

        }

        function removePurchaseRequestLineItem(index) {

            if (prFormEditState && prFormEditState.requestId) {

                showPurchaseRequestMessage('Removing lines is not supported while editing an existing purchase request.', 'error');

                return;

            }

            if (!window.purchaseRequestItems || window.purchaseRequestItems.length <= 1) {

                showPurchaseRequestMessage('At least one line item is required.', 'error');

                return;

            }

            window.purchaseRequestItems.splice(index, 1);

            renderPurchaseRequestLineItems();

        }

        function recalcPurchaseRequestTotals() {

            const items = window.purchaseRequestItems || [];

            let subtotal = 0;

            let taxTotal = 0;

            items.forEach((item) => {

                const pq = linePricingQty(item);

                const unitPrice = Number(item.unitPrice || 0);

                subtotal += pq * unitPrice;

            });

            const grand = subtotal + taxTotal;

            document.getElementById('pr-subtotal').textContent = formatMoney(subtotal);

            document.getElementById('pr-tax-total').textContent = formatMoney(taxTotal);

            document.getElementById('pr-grand-total').textContent = formatMoney(grand);

            return { subtotal, taxTotal, grand };

        }

        function buildPurchaseRequestPayload(status) {

            const totals = recalcPurchaseRequestTotals();

            const selectedProjectCode = getSelectedProjectCode();

            // Invited suppliers are for bidding only; SQL PR header has no vendor until award.

            const lineItems = (window.purchaseRequestItems || []).map((item) => {

                const pq = linePricingQty(item);

                const up = Number(item.unitPrice || 0);

                return {

                    itemCode: String(item.itemCode || '').trim(),

                    itemName: String(item.itemName || '').trim(),

                    locationCode: String(item.locationCode || '').trim(),

                    description: resolvePrLineDescription(item),

                    uom: String(item.uom || '').trim(),

                    udfReason: String(item.udfReason || '').trim(),

                    project: selectedProjectCode,

                    qtySqty: Number(item.qtySqty || 0),

                    qtySuomqty: Number(item.qtySuomqty || 0),

                    quantity: pq,

                    unitPrice: up,

                    deliveryDate: String(item.deliveryDate || '').trim(),

                    tax: 0,

                    amount: Number((pq * up).toFixed(2)),

                    stockQtyUom: deriveStockQtyUomForPayload(item),
                    ...prLineStockFieldsForPayload(item),

                };

            });

            return {

                requestNumber: document.getElementById('pr-request-number').value.trim(),

                costCenter: selectedProjectCode,

                project: selectedProjectCode,

                suppliers: selectedSuppliers.map((s) => ({ code: s.code, name: s.name, email: s.email || '' })),

                requestDate: String(document.getElementById('pr-request-date')?.value || '').trim() || prTodayIso(),

                description: 'Purchase Request',

                deliveryLocation: '',

                totalAmount: Number(totals.grand.toFixed(2)),

                status,

                lineItems,

            };

        }

        function validatePurchaseRequestPayload(payload) {

            if (!payload.requestDate) return 'requestDate is required';

            if (!Array.isArray(payload.lineItems) || !payload.lineItems.length) return 'At least one line item is required';

            const isSubmit = String(payload.status || '').toUpperCase() === 'SUBMITTED';

            for (let i = 0; i < payload.lineItems.length; i += 1) {

                const item = payload.lineItems[i];

                if (!item.itemCode) return `line ${i + 1}: itemCode is required`;

                if (!item.itemName) return `line ${i + 1}: itemName is required`;

                const qs = Number(item.qtySqty);

                const qu = Number(item.qtySuomqty);

                if (Number.isNaN(qs) || qs < 0 || Number.isNaN(qu) || qu < 0) {

                    return `line ${i + 1}: SQTY and SUOMQTY must be numbers >= 0`;

                }

                if (isSubmit && !(qs > 0 || qu > 0)) {

                    return `line ${i + 1}: enter SQTY and/or SUOMQTY (> 0) to submit`;

                }

                const pq = Number(item.quantity);

                if (Number.isNaN(pq) || pq < 0) {

                    return `line ${i + 1}: pricing quantity must be >= 0`;

                }

                if (!(Number(item.unitPrice) >= 0)) return `line ${i + 1}: unitPrice must be >= 0`;

            }

            return '';

        }

        async function submitPurchaseRequestInternal(status) {

            const btn = document.getElementById('pr-submit-btn');

            const draftBtn = document.getElementById('pr-save-draft-btn');

            const isEditMode = Boolean(prFormEditState && prFormEditState.requestId);

            if (isEditMode) {

                const selectedProjectCode = getSelectedProjectCode();

                const editLineItems = (window.purchaseRequestItems || []).map((item) => ({

                    detailId: Number(item.detailId || 0),

                    description: resolvePrLineDescription(item),

                    uom: String(item.uom || '').trim(),

                    udfReason: String(item.udfReason || '').trim(),

                    project: selectedProjectCode,

                    qtySqty: Number(item.qtySqty || 0),

                    qtySuomqty: Number(item.qtySuomqty || 0),

                    quantity: linePricingQty(item),

                    unitPrice: Number(item.unitPrice || 0),

                    deliveryDate: String(item.deliveryDate || '').trim(),

                    stockQtyUom: deriveStockQtyUomForPayload(item),
                    ...prLineStockFieldsForPayload(item),

                }));

                if (!editLineItems.length) {

                    showPurchaseRequestMessage('At least one line item is required', 'error');

                    return;

                }

                const isSubmitFromEdit = String(status || '').toUpperCase() === 'SUBMITTED';

                for (let i = 0; i < editLineItems.length; i += 1) {

                    const line = editLineItems[i];

                    if (!(line.detailId > 0)) {

                        showPurchaseRequestMessage(`line ${i + 1}: detailId is required for edit mode`, 'error');

                        return;

                    }

                    const qs = Number(line.qtySqty || 0);

                    const qu = Number(line.qtySuomqty || 0);

                    const pq = Number(line.quantity || 0);

                    if (Number.isNaN(qs) || qs < 0 || Number.isNaN(qu) || qu < 0) {

                        showPurchaseRequestMessage(`line ${i + 1}: SQTY / SUOMQTY must be numbers >= 0`, 'error');

                        return;

                    }

                    if (isSubmitFromEdit && !(qs > 0 || qu > 0)) {

                        showPurchaseRequestMessage(`line ${i + 1}: enter SQTY and/or SUOMQTY (> 0) to submit`, 'error');

                        return;

                    }

                    if (Number.isNaN(pq) || pq < 0) {

                        showPurchaseRequestMessage(`line ${i + 1}: pricing quantity invalid`, 'error');

                        return;

                    }

                    if (!(line.unitPrice >= 0)) {

                        showPurchaseRequestMessage(`line ${i + 1}: unitPrice must be >= 0`, 'error');

                        return;

                    }

                }

                const editPayload = {

                    // requiredDate is not user-facing; backend defaults it to requestDate when omitted.

                    costCenter: selectedProjectCode,

                    project: selectedProjectCode,

                    currency: (prFormEditState && prFormEditState.currency) ? String(prFormEditState.currency) : '',

                    description: '',

                    deliveryLocation: '',

                    suppliers: selectedSuppliers.map((s) => ({

                        code: String(s.code || '').trim(),

                        name: String(s.name || '').trim(),

                        email: String(s.email || '').trim(),

                    })),

                    lineItems: editLineItems,

                    ...(isSubmitFromEdit ? { submit: true } : {}),

                };

                try {

                    btn.disabled = true;

                    if (draftBtn) {

                        draftBtn.disabled = true;

                    }

                    btn.textContent = 'Saving...';

                    showPurchaseRequestMessage(

                        isSubmitFromEdit ? 'Saving changes and submitting purchase request...' : 'Saving purchase request changes...',

                        'info'

                    );

                    const response = await fetch(`/api/admin/procurement/purchase-requests/${prFormEditState.requestId}/edit`, {

                        method: 'PATCH',

                        headers: {

                            'Content-Type': 'application/json',

                        },

                        body: JSON.stringify(editPayload),

                    });

                    const data = await readProcurementJson(response);

                    if (!response.ok || !data.success) {

                        throw new Error(data.error || `Request failed with HTTP ${response.status}`);

                    }

                    const editSuccessRequestNo = isSubmitFromEdit

                        ? String((prFormEditState && prFormEditState.requestNumber) || document.getElementById('pr-request-number').value || '').trim()

                        : '';

                    prFormEditState = null;

                    initPurchaseRequestForm();

                    goToViewPrStatus('AWAITING');

                    if (isSubmitFromEdit) {

                        showPurchaseRequestSuccessModal(

                            'Purchase request submitted',

                            'Your purchase request was submitted successfully.',

                            editSuccessRequestNo || null

                        );

                    } else {

                        showPurchaseRequestSuccessModal(

                            'Draft updated',

                            'Your draft was saved successfully.',

                            editSuccessRequestNo || null

                        );

                    }

                } catch (error) {

                    if (!isProcurementAuthExpired(error)) showPurchaseRequestMessage(error.message || 'Failed to update purchase request.', 'error');

                } finally {

                    btn.disabled = false;

                    if (draftBtn) {

                        draftBtn.disabled = false;

                    }

                    applyPurchaseRequestFormModeUI();

                }

                return;

            }

            const payload = buildPurchaseRequestPayload(status);

            const validationError = validatePurchaseRequestPayload(payload);

            if (validationError) {

                showPurchaseRequestMessage(validationError, 'error');

                return;

            }

            try {

                btn.disabled = true;

                if (draftBtn) draftBtn.disabled = true;

                const actionLabel = status === 'SUBMITTED' ? 'Submitting...' : 'Saving...';

                btn.textContent = actionLabel;

                const progressMsg = status === 'SUBMITTED'

                    ? 'Submitting purchase request...'

                    : 'Saving draft purchase request...';

                showPurchaseRequestMessage(progressMsg, 'info');

                const response = await fetch('/api/admin/procurement/purchase-requests', {

                    method: 'POST',

                    headers: {

                        'Content-Type': 'application/json',

                    },

                    body: JSON.stringify(payload),

                });

                const data = await readProcurementJson(response);

                if (!response.ok || !data.success) {

                    throw new Error(data.error || `Request failed with HTTP ${response.status}`);

                }

                const requestNumber = data.data && data.data.requestNumber ? data.data.requestNumber : 'N/A';

                if (String(status || '').toUpperCase() === 'SUBMITTED') {

                    document.getElementById('pr-request-number').value = requestNumber;

                    selectedSuppliers = [];

                    _renderChips();

                    initPurchaseRequestForm();

                    goToViewPrStatus('AWAITING');

                    try {

                        const url = new URL(window.location.href);

                        url.searchParams.set('tab', 'view');

                        history.replaceState({}, '', url);

                    } catch (e) { /* ignore */ }

                    loadStockCardRows();

                    showPurchaseRequestSuccessModal(

                        'Purchase request submitted',

                        'Your purchase request was submitted successfully.',

                        requestNumber !== 'N/A' ? requestNumber : null

                    );

                } else {

                    const msg = `Draft saved successfully. Request Number: ${requestNumber}`;

                    showPurchaseRequestMessage(msg, 'success');

                    document.getElementById('pr-request-number').value = requestNumber;

                    selectedSuppliers = [];

                    _renderChips();

                    loadStockCardRows();

                    loadViewPurchaseRequests(true);

                    loadNextPurchaseRequestNumber();

                }

            } catch (error) {

                if (!isProcurementAuthExpired(error)) showPurchaseRequestMessage(error.message || 'Failed to submit purchase request.', 'error');

            } finally {

                btn.disabled = false;

                if (draftBtn) draftBtn.disabled = false;

                applyPurchaseRequestFormModeUI();

            }

        }

        function saveDraftPurchaseRequest() {

            submitPurchaseRequestInternal('DRAFT');

        }

        function submitPurchaseRequest() {

            submitPurchaseRequestInternal('SUBMITTED');

        }

        let supplierList = [];

        let selectedSuppliers = []; // [{code, name, email}]

        let projectList = [];

        function loadProjects() {

            fetch('/api/admin/procurement/projects')

                .then((res) => readProcurementJson(res))

                .then((payload) => {

                    if (payload.success && Array.isArray(payload.data)) {

                        projectList = payload.data;

                    } else {

                        console.warn('[Projects] Failed to load:', payload.error || payload);

                        projectList = [];

                    }

                    renderProjectOptions();

                })

                .catch((err) => {

                    console.warn('[Projects] Fetch error:', err);

                    projectList = [];

                    renderProjectOptions();

                });

        }

        function getSelectedProjectCode() {

            const projectSelect = document.getElementById('pr-project-code');

            if (!projectSelect) return '';

            const current = String(projectSelect.value || '').trim();

            if (current) return current;

            const firstOption = projectSelect.options && projectSelect.options.length ? String(projectSelect.options[0].value || '').trim() : '';

            return firstOption || '';

        }

        function renderProjectOptions(selectedCode) {

            const projectSelect = document.getElementById('pr-project-code');

            if (!projectSelect) return;

            const chosen = String(selectedCode || projectSelect.value || '').trim();

            const rows = Array.isArray(projectList) && projectList.length

                ? projectList

                : [];

            const seen = new Set();

            const options = [];

            rows.forEach((row) => {

                const code = String((row && row.code) || '').trim();

                if (!code || seen.has(code)) return;

                seen.add(code);

                const description = String((row && row.description) || '').trim();

                options.push({

                    code,

                    label: code,

                });

            });

            if (!options.length) {

                projectSelect.innerHTML = '<option value="">No project found</option>';

                projectSelect.value = '';

                return;

            }

            projectSelect.innerHTML = options

                .map((opt) => `<option value="${escapeHtml(opt.code)}">${escapeHtml(opt.label)}</option>`)

                .join('');

            const valid = options.some((opt) => opt.code === chosen);

            projectSelect.value = valid ? chosen : options[0].code;

        }

        function loadSuppliers() {

            fetch('/api/admin/procurement/suppliers')

                .then((res) => readProcurementJson(res))

                .then((payload) => {

                    if (payload.success && Array.isArray(payload.data)) {

                        supplierList = payload.data;

                        console.log('[Suppliers] Loaded', supplierList.length, 'suppliers');
                        const errEl = document.getElementById('pr-supplier-load-error');
                        if (errEl) {
                            errEl.textContent = '';
                            errEl.style.display = 'none';
                        }

                    } else {

                        supplierList = [];
                        console.warn('[Suppliers] Failed to load:', payload.error || payload);
                        const errEl = document.getElementById('pr-supplier-load-error');
                        if (errEl) {
                            errEl.textContent = 'Supplier list could not be loaded. Check SQL API /supplier and refresh.';
                            errEl.style.display = 'block';
                        }

                    }

                    _initSupplierPicker();

                })

                .catch((err) => { console.warn('[Suppliers] Fetch error:', err); _initSupplierPicker(); });

        }

        function _initSupplierPicker() {

            const search = document.getElementById('pr-supplier-search');

            const dropdown = document.getElementById('pr-supplier-dropdown');

            if (!search || !dropdown) return;
            if (search.dataset.prSupplierPickerBound === '1') return;
            search.dataset.prSupplierPickerBound = '1';

            search.addEventListener('input', () => _renderDropdown(search.value.trim()));

            search.addEventListener('focus', () => _renderDropdown(search.value.trim()));

            search.addEventListener('keydown', (e) => { if (e.key === 'Escape') dropdown.style.display = 'none'; });

            document.addEventListener('click', (e) => {

                const addRow = document.querySelector('.pr-supplier-add-row');

                if (addRow && !addRow.contains(e.target)) dropdown.style.display = 'none';

            });

        }

        function _renderDropdown(query) {

            const dropdown = document.getElementById('pr-supplier-dropdown');

            const selectedCodes = new Set(selectedSuppliers.map((s) => s.code));

            const q = query.toLowerCase();

            const filtered = supplierList.filter((s) => {

                const name = (s.companyname || '').toLowerCase();

                const code = (s.code || '').toLowerCase();

                const email = String(s.udf_email || s.email || '').toLowerCase();

                return !q || name.includes(q) || code.includes(q) || email.includes(q);

            });

            if (!filtered.length) {

                dropdown.innerHTML = '<div class="supplier-dropdown-item" style="color:#aaa;pointer-events:none;">No suppliers found</div>';

                dropdown.style.display = 'block';

                return;

            }

            dropdown.innerHTML = filtered.map((s) => {

                const isSelected = selectedCodes.has(s.code);

                const email = s.udf_email || '';

                const safeName = (s.companyname || '').replace(/'/g, "\\'");

                const safeEmail = email.replace(/'/g, "\\'");

                const curRaw = s.currencycode || s.CURRENCYCODE || s.currency || '';

                const safeCur = String(curRaw).replace(/\\/g, '\\\\').replace(/'/g, "\\'");

                return `<div class="supplier-dropdown-item${isSelected ? ' already-selected' : ''}" onclick="_addSupplier('${s.code}','${safeName}','${safeEmail}','${safeCur}')">

                    <span style="font-weight:600;min-width:80px;">${s.code}</span>

                    <span style="flex:1;">${s.companyname || ''}</span>

                    <span style="color:#9ba7b6;font-size:12px;">${email}</span>

                    ${isSelected ? '<span style="color:#1a56db;margin-left:6px;">✓</span>' : ''}

                </div>`;

            }).join('');

            dropdown.style.display = 'block';

        }

        function _addSupplier(code, name, email, currency) {

            if (selectedSuppliers.find((s) => s.code === code)) return;

            selectedSuppliers.push({

                code,

                name,

                email,

                currency: String(currency || '').trim(),

            });

            _renderSupplierTable();

            const search = document.getElementById('pr-supplier-search');

            search.value = '';

            document.getElementById('pr-supplier-dropdown').style.display = 'none';

        }

        function _removeSupplier(code) {

            selectedSuppliers = selectedSuppliers.filter((s) => s.code !== code);

            _renderSupplierTable();

        }

        function _updateSupplierSelectedCounts() {
            const n = selectedSuppliers.length;
            const badge = document.getElementById('pr-supplier-selected-badge');
            const countEl = document.getElementById('pr-supplier-selected-count');
            const selectedBlock = document.querySelector('.pr-supplier-block--selected');
            if (badge) badge.textContent = n === 1 ? '1 selected' : `${n} selected`;
            if (countEl) countEl.textContent = String(n);
            if (selectedBlock) selectedBlock.dataset.count = String(n);
        }

        function _renderSupplierTable() {

            const tbody = document.getElementById('pr-supplier-tbody');

            if (!tbody) return;

            _updateSupplierSelectedCounts();

            if (!selectedSuppliers.length) {

                tbody.innerHTML = '<tr id="pr-supplier-empty-row"><td colspan="5" class="pr-supplier-empty">No suppliers selected</td></tr>';

                return;

            }

            tbody.innerHTML = selectedSuppliers.map((s, i) => `

                <tr>

                    <td>${i + 1}</td>

                    <td><strong>${s.code}</strong></td>

                    <td>${s.name || ''}</td>

                    <td class="pr-supplier-email-cell" title="${escapeHtml(s.email || '')}">${s.email ? escapeHtml(s.email) : '<span style="color:#bbb;">-</span>'}</td>

                    <td><button type="button" class="pr-supplier-remove-btn" onclick="_removeSupplier('${s.code}')" title="Remove supplier">×</button></td>

                </tr>`).join('');

        }

        // Keep legacy alias used by reset after submit

        function _renderChips() { _renderSupplierTable(); }

        async function loadNextPurchaseRequestNumber() {

            const requestNumberInput = document.getElementById('pr-request-number');

            if (!requestNumberInput) {

                return;

            }

            requestNumberInput.value = 'Loading...';

            try {

                const response = await fetch('/api/admin/procurement/purchase-requests/next-number');

                const data = await readProcurementJson(response);

                if (!response.ok || !data.success) {

                    throw new Error(data.error || `Failed to load request number (HTTP ${response.status})`);

                }

                requestNumberInput.value = String(data?.data?.requestNumber || '').trim() || 'Auto-generated on save';

            } catch (error) {

                requestNumberInput.value = 'Auto-generated on save';

                console.warn('[Purchase Request] Failed to preload request number:', error);

            }

        }

        function initPurchaseRequestForm() {

            prFormEditState = null;
            clearPurchaseRequestDraftItems();

            renderProjectOptions('');

            const today = prTodayIso();

            const defU = defaultPrStockQtyUom();

            const row = {

                itemCode: '',

                itemName: '',

                locationCode: getDefaultLineLocation(),

                description: '',

                uom: '',

                udfReason: '',

                project: getSelectedProjectCode(),

                qtySqty: defU === 'SQTY' ? 1 : 0,

                qtySuomqty: defU === 'SUOMQTY' ? 1 : 0,

                quantity: 1,

                unitPrice: 0,

                deliveryDate: today,

                stockQtyUom: defU,

            };

            syncPrLineQuantityDerived(row);

            window.purchaseRequestItems = [row];

            selectedSuppliers = [];

            _renderChips();

            const requestDateEl = document.getElementById('pr-request-date');

            if (requestDateEl) {

                requestDateEl.value = today;

            }

            loadNextPurchaseRequestNumber();

            bindPurchaseRequestDeliveryLocationSync();

            renderPurchaseRequestLineItems();

            applyPurchaseRequestFormModeUI();

        }

        document.addEventListener('DOMContentLoaded', function () {

                initStockDashboardLayout();

                loadStockCardRows();

                afterStockCardTableRender();

                bindPurchaseRequestDeliveryLocationSync();

                if (!tryRestorePurchaseRequestDraftItems()) {
                    initPurchaseRequestForm();
                }
                const prNoEl = document.getElementById('pr-request-number');
                if (prNoEl && !String(prNoEl.value || '').trim()) {
                    loadNextPurchaseRequestNumber();
                }

                window.addEventListener('resize', afterStockCardTableRender);

                document.addEventListener('visibilitychange', () => {

                    if (document.visibilityState !== 'visible') return;

                    const panel = document.getElementById('panel-report');

                    if (!panel || panel.style.display === 'none') return;

                    if (!reportLoaded) return;

                    if (stockCardVisibilityRefreshTimer) {

                        clearTimeout(stockCardVisibilityRefreshTimer);

                    }

                    stockCardVisibilityRefreshTimer = setTimeout(() => {

                        stockCardVisibilityRefreshTimer = null;

                        loadStockCardRows();

                    }, 400);

                });

                // Select initial view based on URL query param (e.g. ?tab=report|view|create)

                try {

                    const params = new URLSearchParams(window.location.search || '');

                    const tab = String(params.get('tab') || 'report').trim();

                    applyViewStatusFromUrl();

                    showTab(tab);

                } catch (e) {

                    showTab('report');

                }

        });

    
