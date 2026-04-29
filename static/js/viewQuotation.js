let activeQuotationsCache = [];
let cancelledQuotationsCache = [];
let draftQuotationsCache = [];
let pendingQuotationsCache = [];
let slQtDraftCache = [];
let slQtDraftLoaded = false;
let currentListTab = 'active';

function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function isPendingQuotation(qt) {
    const cancelledUnset = qt.CANCELLED === null || qt.CANCELLED === undefined;
    const updateCountUnset = qt.UPDATECOUNT === null || qt.UPDATECOUNT === undefined;
    return cancelledUnset || updateCountUnset;
}

async function fetchSavedDraftQuotations(forceReload = false) {
    if (slQtDraftLoaded && !forceReload) {
        return slQtDraftCache;
    }

    const res = await fetch('/api/get_my_draft_quotations');
    const data = await res.json();
    if (!data.success) {
        throw new Error(data.error || 'Failed to load drafts');
    }

    slQtDraftCache = data.data || [];
    slQtDraftLoaded = true;
    draftQuotationsCache = slQtDraftCache;
    return slQtDraftCache;
}

function shellHtml() {
    return `
    <div class="view-quotation-page">
        <div class="view-quotation-tabs" role="tablist">
            <button type="button" id="tab-drafts" data-tab="drafts" onclick="setQuotationTab('drafts')">
                📋 Drafts (${draftQuotationsCache.length})
            </button>
            <button type="button" id="tab-pending" data-tab="pending" onclick="setQuotationTab('pending')">
                ⏳ Pending (${pendingQuotationsCache.length})
            </button>
            <button type="button" id="tab-active" data-tab="active" onclick="setQuotationTab('active')">
                Active (${activeQuotationsCache.length})
            </button>
            <button type="button" id="tab-cancelled" data-tab="cancelled" onclick="setQuotationTab('cancelled')">
                Cancelled (${cancelledQuotationsCache.length})
            </button>
        </div>
        <div class="view-quotation-split">
            <aside class="view-quotation-list-pane" aria-label="Quotation list">
                <div id="view-quotation-list" class="view-quotation-list-scroll"></div>
            </aside>
            <section class="view-quotation-detail-pane" aria-label="Quotation details">
                <div id="view-quotation-detail-body" class="view-quotation-detail-scroll"></div>
            </section>
        </div>
    </div>
    `;
}

function showDetailEmpty(message) {
    const el = document.getElementById('view-quotation-detail-body');
    if (!el) return;
    el.innerHTML = `<div class="view-quotation-detail-empty">${escapeHtml(message)}</div>`;
}

function setTabButtonStyles(tabName) {
    const map = {
        drafts: { id: 'tab-drafts', cls: 'tab--drafts' },
        pending: { id: 'tab-pending', cls: 'tab--pending' },
        active: { id: 'tab-active', cls: 'tab--active' },
        cancelled: { id: 'tab-cancelled', cls: 'tab--cancelled' },
    };
    ['tab-drafts', 'tab-pending', 'tab-active', 'tab-cancelled'].forEach((tid) => {
        const b = document.getElementById(tid);
        if (b) {
            b.classList.remove('is-active');
        }
    });
    const m = map[tabName] || map.active;
    const btn = document.getElementById(m.id);
    if (btn) {
        btn.classList.add('is-active');
    }
    const controlsDiv = document.querySelector('.active-tab-controls');
    if (controlsDiv) {
        controlsDiv.classList.remove('show');
    }
}

function parseDisc(item) {
    const raw = item.DISC;
    if (raw == null) {
        return 0;
    }
    if (typeof raw === 'number') {
        return raw;
    }
    const t = String(raw).replace(/,/g, '');
    const n = parseFloat(t);
    return Number.isFinite(n) ? n : 0;
}

function renderLineItemsTable(items) {
    if (!items || items.length === 0) {
        return '<p class="view-qt-detail-error">No line items.</p>';
    }
    let total = 0;
    let rows = '';
    items.forEach((item) => {
        const qty = Number(item.QTY || 0);
        const price = Number(item.UNITPRICE || 0);
        const disc = parseDisc(item);
        const amount = Math.max(0, qty * price - disc);
        total += amount;
        const code = escapeHtml(item.ITEMCODE || '');
        const desc = escapeHtml(item.DESCRIPTION || '');
        const deliv = item.DELIVERYDATE
            ? `<span class="view-qt-line-desc">Deliv. ${escapeHtml(String(item.DELIVERYDATE))}</span>`
            : '';
        rows += '<tr>';
        rows += `<td><div>${code}</div><span class="view-qt-line-desc">${desc}</span>${deliv}</td>`;
        rows += `<td class="num">RM ${price.toFixed(2)}</td>`;
        rows += `<td class="num">${qty.toFixed(2)}</td>`;
        rows += `<td class="num">RM ${disc.toFixed(2)}</td>`;
        rows += `<td class="num">RM ${amount.toFixed(2)}</td>`;
        rows += '</tr>';
    });
    return `
    <table class="view-quotation-items-table">
        <thead>
            <tr>
                <th>Item</th>
                <th class="num">Unit</th>
                <th class="num">Qty</th>
                <th class="num">Discount</th>
                <th class="num">Subtotal</th>
            </tr>
        </thead>
        <tbody>${rows}
            <tr class="view-quotation-items-total">
                <td colspan="4" class="num">Total</td>
                <td class="num">RM ${total.toFixed(2)}</td>
            </tr>
        </tbody>
    </table>`;
}

function listTypeLabel(listType) {
    if (listType === 'draft' || listType === 'drafts') {
        return 'Draft (saved)';
    }
    if (listType === 'pending') {
        return 'Pending';
    }
    if (listType === 'cancelled') {
        return 'Cancelled';
    }
    return 'Active';
}

function renderDetailPanel(data, listType) {
    const d = data || {};
    const items = Array.isArray(d.items) ? d.items : [];
    const statusLabel = listTypeLabel(listType);
    const docno = d.DOCNO != null ? String(d.DOCNO) : (d.DOCKEY != null ? `DOCKEY #${d.DOCKEY}` : '—');
    const meta = [];
    meta.push(['<dt>Status</dt>', `<dd>${escapeHtml(statusLabel)}</dd>`]);
    if (d.COMPANYNAME) {
        meta.push(['<dt>Customer</dt>', `<dd>${escapeHtml(d.COMPANYNAME)}</dd>`]);
    }
    if (d.DOCDATE) {
        meta.push(['<dt>Date</dt>', `<dd>${escapeHtml(d.DOCDATE)}</dd>`]);
    }
    if (d.VALIDITY) {
        meta.push(['<dt>Valid until</dt>', `<dd>${escapeHtml(d.VALIDITY)}</dd>`]);
    }
    const credit = d.CREDITTERM != null && d.CREDITTERM !== '' ? d.CREDITTERM : d.TERMS;
    if (credit != null && String(credit) !== '') {
        meta.push(['<dt>Terms</dt>', `<dd>${escapeHtml(String(credit))}</dd>`]);
    }
    if (d.CURRENCYCODE) {
        meta.push(['<dt>Currency</dt>', `<dd>${escapeHtml(d.CURRENCYCODE)}</dd>`]);
    }
    if (d.STATUS && listType === 'active') {
        meta.push(['<dt>Record status</dt>', `<dd>${escapeHtml(d.STATUS)}</dd>`]);
    }
    if (d.PHONE1) {
        meta.push(['<dt>Phone</dt>', `<dd>${escapeHtml(d.PHONE1)}</dd>`]);
    }
    if (d.ADDRESS1) {
        meta.push(['<dt>Address</dt>', `<dd>${[d.ADDRESS1, d.ADDRESS2, d.ADDRESS3, d.ADDRESS4].filter(Boolean).map(escapeHtml).join(', ')}</dd>`]);
    }
    if (d.DESCRIPTION) {
        meta.push(['<dt>Description</dt>', `<dd>${escapeHtml(d.DESCRIPTION)}</dd>`]);
    }
    if (d.DOCAMT != null) {
        meta.push(['<dt>Document amount</dt>', `<dd>RM ${Number(d.DOCAMT).toFixed(2)}</dd>`]);
    }

    return `
        <h3 class="view-quotation-detail-title">${escapeHtml(docno)}</h3>
        <p class="view-quotation-detail-status">${escapeHtml(statusLabel)}</p>
        <dl class="view-quotation-detail-meta">${meta.map((m) => m[0] + m[1]).join('')}</dl>
        ${renderLineItemsTable(items)}
    `;
}

async function loadQuotationDetailIntoPanel(dockey, isDraftSource, listType) {
    const detailRoot = document.getElementById('view-quotation-detail-body');
    if (!detailRoot) {
        return;
    }
    detailRoot.innerHTML = '<div class="view-qt-detail-loading">Loading details…</div>';
    const endpoint = isDraftSource
        ? `/api/get_draft_quotation_details?dockey=${encodeURIComponent(dockey)}`
        : `/api/get_quotation_details?dockey=${encodeURIComponent(dockey)}`;

    try {
        const response = await fetch(endpoint);
        const payload = await response.json();
        const dataBlock = payload && payload.data && typeof payload.data === 'object' ? payload.data : payload;
        if (!payload.success) {
            const err = dataBlock && (dataBlock.error != null) ? dataBlock.error : (payload.error || 'Failed to load');
            detailRoot.innerHTML = `<div class="view-qt-detail-error">${escapeHtml(String(err))}</div>`;
            return;
        }
        detailRoot.innerHTML = renderDetailPanel(dataBlock, isDraftSource ? 'draft' : listType);
    } catch (err) {
        console.error('loadQuotationDetailIntoPanel', err);
        detailRoot.innerHTML = '<div class="view-qt-detail-error">Error loading details.</div>';
    }
}

function getListTypeFromCurrentTab() {
    return currentListTab;
}

function selectListCard(card) {
    if (!card) {
        return;
    }
    document.querySelectorAll('.view-qt-list-card').forEach((c) => c.classList.remove('is-selected'));
    card.classList.add('is-selected');
    const dockey = card.dataset.dockey;
    const source = (card.dataset.source || '').trim();
    const isDraft = source === 'slqtdraft';
    const listType = card.dataset.listType || getListTypeFromCurrentTab();
    loadQuotationDetailIntoPanel(dockey, isDraft, listType);
}

function hasAnyQuotations() {
    return (
        (activeQuotationsCache && activeQuotationsCache.length > 0) ||
        (cancelledQuotationsCache && cancelledQuotationsCache.length > 0) ||
        (pendingQuotationsCache && pendingQuotationsCache.length > 0) ||
        (draftQuotationsCache && draftQuotationsCache.length > 0)
    );
}

function trySelectFirstListCard() {
    const first = document.querySelector('#view-quotation-list .view-qt-list-card');
    if (first) {
        selectListCard(first);
    } else {
        const noneAnywhere = !hasAnyQuotations();
        let msg;
        if (currentListTab === 'drafts') {
            msg = 'No saved drafts in this list.';
        } else if (noneAnywhere) {
            msg = 'No quotations found. New quotations from your workflow will appear in the list on the left when available.';
        } else {
            msg = 'No quotations in this tab. Try another filter above.';
        }
        showDetailEmpty(msg);
    }
}

function ensureListClickDelegation() {
    const content = document.getElementById('quotation-content');
    if (!content || content.dataset.viewQtDelegation) {
        return;
    }
    content.dataset.viewQtDelegation = '1';
    content.addEventListener('click', (e) => {
        if (e.target.closest('button') || e.target.closest('a')) {
            return;
        }
        const card = e.target.closest('.view-qt-list-card');
        if (card) {
            selectListCard(card);
        }
    });
}

async function loadQuotations() {
    const content = document.getElementById('quotation-content');
    if (!content) {
        return;
    }

    content.innerHTML = '<div class="view-quotation-detail-empty" style="padding:24px;">Loading…</div>';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);
        const response = await fetch('/api/get_my_quotations', { signal: controller.signal });
        clearTimeout(timeoutId);
        const data = await response.json();

        if (!data.success) {
            const err = escapeHtml(data.error || 'Failed to load quotations');
            pendingQuotationsCache = [];
            cancelledQuotationsCache = [];
            activeQuotationsCache = [];
            try {
                await fetchSavedDraftQuotations(true);
            } catch (e) {
                console.error('fetchSavedDraftQuotations after list error', e);
                if (!slQtDraftLoaded) {
                    slQtDraftCache = [];
                    draftQuotationsCache = [];
                }
            }
            content.innerHTML = shellHtml();
            ensureListClickDelegation();
            setQuotationTab('active');
            updateDraftCountDisplay();
            showDetailEmpty(err);
            return;
        }

        const quotations = data.data || [];
        try {
            await fetchSavedDraftQuotations(true);
        } catch (e) {
            console.error('fetchSavedDraftQuotations', e);
            if (!slQtDraftLoaded) {
                slQtDraftCache = [];
                draftQuotationsCache = [];
            }
        }

        pendingQuotationsCache = quotations.filter((qt) => isPendingQuotation(qt));
        cancelledQuotationsCache = quotations.filter(
            (qt) => !isPendingQuotation(qt) && qt.CANCELLED === true
        );
        activeQuotationsCache = quotations.filter(
            (qt) => !isPendingQuotation(qt) && qt.CANCELLED === false
        );

        content.innerHTML = shellHtml();
        ensureListClickDelegation();
        setQuotationTab('active');
        updateDraftCountDisplay();
    } catch (error) {
        const message =
            error && error.name === 'AbortError'
                ? 'Request timed out while loading quotations. Please refresh and try again.'
                : 'Failed to load quotations.';
        content.innerHTML = `<div class="view-quotation-detail-empty" style="color:#b42318;">${escapeHtml(message)}</div>`;
        console.error('Error loading quotations:', error);
    }
}

function setQuotationTab(tabName) {
    currentListTab = tabName;
    const listEl = document.getElementById('view-quotation-list');
    const activeBtn = document.getElementById('tab-active');
    const cancelledBtn = document.getElementById('tab-cancelled');
    const draftsBtn = document.getElementById('tab-drafts');
    const pendingBtn = document.getElementById('tab-pending');
    if (!listEl || !activeBtn || !cancelledBtn || !draftsBtn || !pendingBtn) {
        return;
    }

    if (tabName === 'cancelled') {
        listEl.innerHTML = renderQuotationList(cancelledQuotationsCache, 'cancelled');
        setTabButtonStyles('cancelled');
    } else if (tabName === 'drafts') {
        setTabButtonStyles('drafts');
        loadSlQtDraftTab(listEl);
        return;
    } else if (tabName === 'pending') {
        listEl.innerHTML = renderQuotationList(pendingQuotationsCache, 'pending');
        setTabButtonStyles('pending');
    } else {
        listEl.innerHTML = renderQuotationList(activeQuotationsCache, 'active');
        setTabButtonStyles('active');
    }

    trySelectFirstListCard();
}

function renderQuotationList(list, listType) {
    if (!list || list.length === 0) {
        return '<div class="view-quotation-list-empty">No quotations</div>';
    }

    let html = '';
    list.forEach((qt) => {
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = escapeHtml(qt.DOCDATE || '—');
        const validity = escapeHtml(qt.VALIDITY || '—');
        const companyName = escapeHtml(qt.COMPANYNAME || 'N/A');
        const docno = escapeHtml(qt.DOCNO || 'DOCKEY #' + qt.DOCKEY);
        const isCancelled = listType === 'cancelled';
        const isPending = listType === 'pending';
        const borderColor = isCancelled ? '#a65c5c' : isPending ? '#b0892f' : '#4b6e9e';
        const badgeColor = isCancelled ? '#a65c5c' : isPending ? '#b0892f' : '#4b6e9e';
        const lt = escapeHtml(listType);
        html += `
            <div class="view-qt-list-card" data-dockey="${qt.DOCKEY}" data-list-type="${lt}" data-source="" style="border-left-color:${borderColor}" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}">
                <div class="view-qt-list-card__row">
                    <span class="view-qt-list-card__docno">${docno}</span>
                    <span class="view-qt-list-card__amount" style="background:${badgeColor}">RM ${amount}</span>
                </div>
                <div class="view-qt-list-card__meta">${companyName}</div>
                <div class="view-qt-list-card__row2">Date: ${docDate} · Valid: ${validity}</div>
            </div>
        `;
    });

    return html;
}

async function loadSlQtDraftTab(listEl) {
    listEl.innerHTML = '<div class="view-quotation-list-empty" style="padding:16px;">Loading drafts…</div>';
    try {
        await fetchSavedDraftQuotations();
        if (!slQtDraftCache || slQtDraftCache.length === 0) {
            listEl.innerHTML = '<div class="view-quotation-list-empty">No saved drafts</div>';
        } else {
            listEl.innerHTML = renderDraftList(slQtDraftCache);
        }
    } catch (e) {
        listEl.innerHTML = '<div class="view-quotation-list-empty" style="color:#b42318;">Error loading drafts</div>';
        console.error('loadSlQtDraftTab error:', e);
    }
    trySelectFirstListCard();
}

function renderDraftList(list) {
    if (!list || list.length === 0) {
        return '<div class="view-quotation-list-empty">No saved drafts</div>';
    }
    let html = '';
    list.forEach((qt) => {
        const amount = Number(qt.DOCAMT || 0).toFixed(2);
        const docDate = escapeHtml(qt.DOCDATE || '—');
        const validity = escapeHtml(qt.VALIDITY || '—');
        const companyName = escapeHtml(qt.COMPANYNAME || 'N/A');
        const docno = escapeHtml(qt.DOCNO || 'DOCKEY #' + qt.DOCKEY);
        html += `
            <div class="view-qt-list-card" data-dockey="${qt.DOCKEY}" data-list-type="draft" data-source="slqtdraft" style="border-left-color:#4b6e9e" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}">
                <div class="view-qt-list-card__row">
                    <span class="view-qt-list-card__docno">${docno}</span>
                    <span class="view-qt-list-card__amount" style="background:#4b6e9e">RM ${amount}</span>
                </div>
                <div class="view-qt-list-card__meta">${companyName}</div>
                <div class="view-qt-list-card__row2">Date: ${docDate} · Valid: ${validity}</div>
                <div class="view-qt-list-card__actions">
                    <button type="button" class="btn-edit-draft" onclick="event.stopPropagation(); editSlQtDraft(${qt.DOCKEY})">Edit draft</button>
                </div>
            </div>
        `;
    });
    return html;
}

function editSlQtDraft(dockey) {
    window.location.href = `/create-quotation?draftDockey=${dockey}`;
}

document.addEventListener('DOMContentLoaded', loadQuotations);

function updateDraftCountDisplay() {
    const draftDisplay = document.getElementById('draft-count-display');
    if (draftDisplay) {
        const count = draftQuotationsCache.length;
        draftDisplay.textContent = `📋 Drafts: ${count}`;
    }
    const td = document.getElementById('tab-drafts');
    if (td) {
        td.textContent = `📋 Drafts (${draftQuotationsCache.length})`;
    }
}

function editDraft(dockey) {
    window.location.href = `/create-quotation?dockey=${dockey}`;
}

function viewDrafts() {
    setQuotationTab('drafts');
    const qc = document.getElementById('quotation-content');
    if (qc) {
        qc.scrollIntoView({ behavior: 'smooth' });
    }
}

function showDraftNotification(docno) {
    const notification = document.getElementById('draft-notification');
    if (!notification) {
        return;
    }

    const messageEl = notification.querySelector('.draft-notification-message');
    if (messageEl) {
        messageEl.innerHTML = `✓ Draft saved successfully!<br><strong>DOCNO: ${escapeHtml(docno)}</strong>`;
    }

    notification.classList.remove('hidden');

    setTimeout(() => {
        notification.classList.add('hidden');
    }, 5000);
}
