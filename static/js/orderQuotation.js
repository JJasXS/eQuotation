// Centered popup with slide in/out, replacing browser alert() dialogs.
function showAppPopup(message, type = 'info') {
    const styleId = 'app-popup-notice-style';
    if (!document.getElementById(styleId)) {
        const style = document.createElement('style');
        style.id = styleId;
        style.textContent = `
            .app-popup-notice {
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 99999;
                width: min(92vw, 440px);
                border-radius: 12px;
                padding: 14px 16px;
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.2);
                font-size: 14px;
                line-height: 1.45;
                display: flex;
                align-items: flex-start;
                gap: 10px;
                opacity: 0;
                animation: appPopupSlideIn 0.24s ease forwards;
            }

            .app-popup-notice.is-hiding {
                animation: appPopupSlideOut 0.2s ease forwards;
            }

            .app-popup-notice__text {
                flex: 1;
            }

            .app-popup-notice__close {
                border: none;
                background: transparent;
                color: inherit;
                cursor: pointer;
                font-size: 18px;
                line-height: 1;
                padding: 0 2px;
            }

            @keyframes appPopupSlideIn {
                from {
                    opacity: 0;
                    transform: translate(-50%, -14px);
                }
                to {
                    opacity: 1;
                    transform: translate(-50%, 0);
                }
            }

            @keyframes appPopupSlideOut {
                from {
                    opacity: 1;
                    transform: translate(-50%, 0);
                }
                to {
                    opacity: 0;
                    transform: translate(-50%, -14px);
                }
            }
        `;
        document.head.appendChild(style);
    }

    const existing = document.querySelector('.app-popup-notice');
    if (existing) {
        existing.remove();
    }

    const popup = document.createElement('div');
    popup.className = 'app-popup-notice';

    const bg = type === 'error' ? '#fde8e8' : type === 'success' ? '#e7f7ee' : '#eef5ff';
    const border = type === 'error' ? '#f2b8b5' : type === 'success' ? '#b7e3c7' : '#b9d3ff';
    const color = type === 'error' ? '#8a1f17' : type === 'success' ? '#14532d' : '#1e3a8a';

    popup.style.background = bg;
    popup.style.border = `1px solid ${border}`;
    popup.style.color = color;

    const text = document.createElement('div');
    text.className = 'app-popup-notice__text';
    text.textContent = String(message || '');

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'app-popup-notice__close';
    closeBtn.setAttribute('aria-label', 'Close notification');
    closeBtn.textContent = '×';

    let hideTimer = null;
    const hidePopup = () => {
        if (!popup.isConnected || popup.classList.contains('is-hiding')) {
            return;
        }
        popup.classList.add('is-hiding');
        window.setTimeout(() => {
            if (popup.isConnected) {
                popup.remove();
            }
        }, 210);
    };

    closeBtn.addEventListener('click', hidePopup);
    popup.appendChild(text);
    popup.appendChild(closeBtn);
    document.body.appendChild(popup);

    hideTimer = window.setTimeout(hidePopup, 3200);
    popup.addEventListener('mouseenter', () => {
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
    });
    popup.addEventListener('mouseleave', () => {
        if (!hideTimer) {
            hideTimer = window.setTimeout(hidePopup, 1400);
        }
    });
}

// Keep existing code unchanged: any alert(...) now uses custom popup.
window.alert = function(message) {
    showAppPopup(message, 'error');
};

// Tab Switching
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Add active class to clicked button
    event.target.classList.add('active');
}

// Add Order Item
function addOrderItem() {
    const container = document.getElementById('order-items-list');
    const newItem = document.createElement('div');
    newItem.className = 'order-item';
    newItem.innerHTML = `
        <div class="item-row">
            <input type="text" class="item-product" placeholder="Product name..." list="product-list" onchange="fetchProductPrice(this)">
            <input type="number" class="item-qty" placeholder="Qty" min="1" value="1" onchange="calculateOrderTotal()">
            <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" onchange="calculateOrderTotal()">
            <button type="button" class="btn-remove" onclick="removeOrderItem(this)">✕</button>
        </div>
    `;
    container.appendChild(newItem);
}

// Remove Order Item
function removeOrderItem(button) {
    const items = document.querySelectorAll('#order-items-list .order-item');
    if (items.length > 1) {
        button.closest('.order-item').remove();
        calculateOrderTotal();
    } else {
        alert('At least one item is required');
    }
}

function buildQuotationPayload() {
    const items = [];
    getQuotationLineRows().forEach(item => {
        const source = readQuotationLineSource(item);
        const product = source === 'custom'
            ? readQuotationLineField(item, '.item-product-custom')
            : readQuotationLineField(item, '.item-product');

        const qty = readQuotationLineNumber(item, '.item-qty');
        const price = readQuotationLineNumber(item, '.item-price');
        const discount = readQuotationLineNumber(item, '.item-discount');
        const deliveryDate = readQuotationLineField(item, '.item-delivery-date') || null;
        // SQL Accounting /salesquotation expects ST_ITEM.CODE on lines; description-only rows can be very slow upstream.
        let itemCode = '';
        if (source === 'catalog') {
            itemCode = resolveCatalogItemCodeFromDescription(product) || '';
        }

        if (product && qty > 0 && price >= 0) {
            items.push({ product, source, itemCode, qty, price, discount, deliveryDate });
        }
    });

    return {
        description: 'Quotation',
        validUntil: document.getElementById('quotation-validity').value,
        companyName: readCustomerScalar('companyname', 'companyName') || '',
        address1: readCustomerScalar('address1') || '',
        address2: readCustomerScalar('address2') || '',
        address3: readCustomerScalar('address3') || '',
        address4: readCustomerScalar('address4') || '',
        phone1: readCustomerScalar('phone1', 'phone') || '',
        remarks: document.getElementById('quotation-remarks')?.value.trim() || '',
        agent: readCustomerScalar('agent') || '',
        area: readCustomerScalar('area') || '',
        attention: readCustomerScalar('attention') || '',
        mobile: readCustomerScalar('mobile') || '',
        terms: readCustomerScalar('creditterm', 'terms') || '',
        currencyCode: readCustomerScalar('currencycode', 'currencyCode') || '',
        country: readCustomerScalar('country') || '',
        tin: readCustomerScalar('tin') || '',
        customerScalars: { ...quotationCustomerScalars },

        items: items
    };
}

function readQuotationCustomerField(id) {
    const el = document.getElementById(id);
    if (!el) return '';
    const tag = (el.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        return String(el.value || '').trim();
    }
    return String(el.textContent || '').trim();
}

function readCustomerScalar(...keys) {
    for (const key of keys) {
        const k = String(key || '').toLowerCase();
        const v = quotationCustomerScalars[k];
        if (v == null) continue;
        const s = String(v).trim();
        if (!s || s === '—' || s.toUpperCase() === 'N/A') {
            continue;
        }
        return s;
    }
    return '';
}

function formatCustomerDisplayValue(value) {
    const s = String(value == null ? '' : value).trim();
    if (!s || s === '—' || s.toUpperCase() === 'N/A') {
        return '';
    }
    return s;
}

function syncProminentCustomerFields() {
    writeQuotationCustomerField('quotation-agent', formatCustomerDisplayValue(readCustomerScalar('agent')));
    writeQuotationCustomerField('quotation-area', formatCustomerDisplayValue(readCustomerScalar('area')));
    writeQuotationCustomerField('quotation-company', formatCustomerDisplayValue(readCustomerScalar('companyname', 'companyName')));
    writeQuotationCustomerField('quotation-phone', formatCustomerDisplayValue(readCustomerScalar('phone1', 'phone')));
    writeQuotationCustomerField('quotation-terms', formatCustomerDisplayValue(readCustomerScalar('creditterm', 'terms')));
    writeQuotationCustomerField('quotation-address1', formatCustomerDisplayValue(readCustomerScalar('address1')));
    writeQuotationCustomerField('quotation-address2', formatCustomerDisplayValue(readCustomerScalar('address2')));
    writeQuotationCustomerField('quotation-address3', formatCustomerDisplayValue(readCustomerScalar('address3')));
    writeQuotationCustomerField('quotation-address4', formatCustomerDisplayValue(readCustomerScalar('address4')));
}

function renderCustomerAllFields(displayFields) {
    const container = document.getElementById('quotation-customer-all-fields');
    if (!container) {
        return;
    }
    container.innerHTML = '';
    const rows = Array.isArray(displayFields) ? displayFields : [];
    if (!rows.length) {
        container.innerHTML = '<div class="customer-detail-row"><span class="customer-detail-value">No customer fields returned.</span></div>';
        return;
    }
    rows.forEach((row) => {
        const label = String(row.label || row.key || '').trim();
        const value = row.value != null ? String(row.value).trim() : '—';
        const key = String(row.key || '').trim();
        const div = document.createElement('div');
        div.className = 'customer-detail-row';
        div.dataset.fieldKey = key;
        div.innerHTML = `<span class="customer-detail-label">${escapeHtml(label)}</span><span class="customer-detail-value">${escapeHtml(value || '—')}</span>`;
        container.appendChild(div);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function ingestCustomerApiPayload(source) {
    quotationCustomerScalars = {};
    if (!source || typeof source !== 'object') {
        return;
    }
    if (source.customerScalars && typeof source.customerScalars === 'object') {
        quotationCustomerScalars = { ...source.customerScalars };
    }
    Object.keys(source).forEach((k) => {
        if (k === 'displayFields' || k.startsWith('_')) {
            return;
        }
        const v = source[k];
        if (v != null && typeof v !== 'object') {
            const key = String(k).toLowerCase();
            const s = String(v).trim();
            if (s.toUpperCase() === 'N/A') {
                quotationCustomerScalars[key] = '';
            } else {
                quotationCustomerScalars[key] = s;
            }
        }
    });
    // Normalize blank placeholders from legacy uppercase keys.
    ['address1', 'address2', 'address3', 'address4'].forEach((k) => {
        const v = quotationCustomerScalars[k];
        if (v && (v === '—' || v.toUpperCase() === 'N/A')) {
            quotationCustomerScalars[k] = '';
        }
    });
}

function writeQuotationCustomerField(id, displayText) {
    const el = document.getElementById(id);
    if (!el) return;
    const tag = (el.tagName || '').toUpperCase();
    const text = displayText == null ? '' : String(displayText);
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        el.value = text;
        return;
    }
    el.textContent = text.trim();
}

function getQuotationLineItemsBody() {
    return document.getElementById('quotation-line-items')
        || document.querySelector('table.quotation-lines-table tbody#quotation-items-list');
}

function getQuotationLineRows() {
    const tbody = getQuotationLineItemsBody();
    if (!tbody) {
        return [];
    }
    return tbody.querySelectorAll('tr.quotation-line-row');
}

function ensureDefaultQuotationLineRow() {
    const tbody = getQuotationLineItemsBody();
    if (!tbody) {
        return;
    }
    if (!tbody.querySelector('tr.quotation-line-row')) {
        appendQuotationLineRow(tbody);
    }
}

const CREATE_QUOTATION_LINES_TABLE_HTML = `
<table class="quotation-lines-table" border="1" cellpadding="4" cellspacing="0">
    <thead>
        <tr>
            <th>Source</th>
            <th>Product</th>
            <th>MOQ</th>
            <th>Lead</th>
            <th>Bundle</th>
            <th>Thick</th>
            <th>Width</th>
            <th>Length</th>
            <th>Qty</th>
            <th>Discount</th>
            <th>Ref. price</th>
            <th>Unit price</th>
            <th>Delivery</th>
            <th></th>
        </tr>
    </thead>
    <tbody id="quotation-line-items"></tbody>
</table>`;

/** Fix cached/old markup: hidden flex grid or missing table left only the dashed Add Item box. */
function repairCreateQuotationLinesUi() {
    if (!document.body.classList.contains('create-quotation-page')
        || document.body.classList.contains('update-quotation-page')) {
        return;
    }

    const section = document.querySelector('.create-quotation-section--lines');
    if (!section) {
        return;
    }

    section.querySelectorAll('.create-quotation-lines-grid, .quotation-item-row-header').forEach((el) => {
        el.remove();
    });

    const orphanItemsList = section.querySelector('#quotation-items-list');
    if (orphanItemsList && String(orphanItemsList.tagName).toUpperCase() !== 'TBODY') {
        orphanItemsList.remove();
    }

    let wrap = section.querySelector('#create-quotation-lines-wrap');
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.id = 'create-quotation-lines-wrap';
        wrap.className = 'create-quotation-lines-wrap';
        const addBtn = section.querySelector('.btn-add-item');
        if (addBtn) {
            section.insertBefore(wrap, addBtn);
        } else {
            section.appendChild(wrap);
        }
    }

    let table = wrap.querySelector('table.quotation-lines-table');
    if (!table) {
        const looseTable = section.querySelector('table.quotation-lines-table');
        if (looseTable) {
            wrap.appendChild(looseTable);
            table = looseTable;
        } else {
            wrap.innerHTML = CREATE_QUOTATION_LINES_TABLE_HTML;
            table = wrap.querySelector('table.quotation-lines-table');
        }
    }

    const tbody = table ? table.querySelector('#quotation-line-items, #quotation-items-list') : null;
    if (tbody && tbody.id !== 'quotation-line-items') {
        tbody.id = 'quotation-line-items';
    }

    const mini = section.querySelector('#quotation-mini-item-codes');
    if (mini && mini.nextElementSibling !== wrap) {
        section.insertBefore(mini, wrap);
    }

    ensureDefaultQuotationLineRow();

    const today = new Date().toISOString().split('T')[0];
    getQuotationLineRows().forEach((row) => {
        const deliveryInput = row.querySelector('.item-delivery-date');
        if (deliveryInput && !deliveryInput.value) {
            deliveryInput.value = today;
        }
    });
}

function getQuotationLineRowFrom(el) {
    return el ? el.closest('tr.quotation-line-row') : null;
}

function formatQuotationCellDisplay(value, useDash = true) {
    if (value == null || String(value).trim() === '') {
        return useDash ? '—' : '';
    }
    return String(value).trim();
}

function readQuotationLineField(row, selector) {
    const el = row ? row.querySelector(selector) : null;
    if (!el) {
        return '';
    }
    const tag = (el.tagName || '').toUpperCase();
    const raw = (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA')
        ? String(el.value || '').trim()
        : String(el.textContent || '').trim();
    return raw === '—' ? '' : raw;
}

function writeQuotationLineField(row, selector, value) {
    const el = row ? row.querySelector(selector) : null;
    if (!el) {
        return;
    }
    const tag = (el.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
        if (el.type === 'number') {
            const n = parseFloat(value);
            el.value = Number.isFinite(n) ? String(n) : '0';
            return;
        }
        if (el.type === 'date') {
            el.value = value == null || String(value).trim() === '' ? '' : String(value).trim().split(' ')[0];
            return;
        }
        el.value = value == null ? '' : String(value).trim();
        return;
    }
    el.textContent = formatQuotationCellDisplay(value, true);
}

const QUOTATION_SOURCE_LABELS = {
    catalog: 'From catalog',
    custom: 'Custom order',
};

function readQuotationLineSource(row) {
    const el = row ? row.querySelector('td.item-source') : null;
    if (!el) {
        return 'catalog';
    }
    const fromData = (el.getAttribute('data-source') || '').toLowerCase();
    if (fromData === 'custom' || fromData === 'catalog') {
        return fromData;
    }
    const text = String(el.textContent || '').toLowerCase();
    return text.includes('custom') ? 'custom' : 'catalog';
}

function writeQuotationLineSource(row, source) {
    const el = row ? row.querySelector('td.item-source') : null;
    if (!el) {
        return;
    }
    const key = source === 'custom' ? 'custom' : 'catalog';
    el.setAttribute('data-source', key);
    el.textContent = QUOTATION_SOURCE_LABELS[key];
}

function readQuotationLineNumber(row, selector) {
    const raw = readQuotationLineField(row, selector);
    if (!raw) {
        return 0;
    }
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : 0;
}

function onQuotationLineCellBlur(cell) {
    const row = getQuotationLineRowFrom(cell);
    if (!row) {
        return;
    }
    if (cell.classList.contains('item-product') || cell.classList.contains('item-product-custom')) {
        fetchProductPrice(cell);
        return;
    }
    if (cell.classList.contains('item-qty') || cell.classList.contains('item-discount')) {
        calculateQuotationTotal();
    }
}

function escapeQuotationHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;');
}

function quotationLineStItemExtraCellsHtml() {
    return `
        <td class="item-udf-moq">—</td>
        <td class="item-udf-dleadtime">—</td>
        <td class="item-udf-bundle">—</td>
        <td class="item-udf-thickness">—</td>
        <td class="item-udf-width">—</td>
        <td class="item-udf-length">—</td>`;
}

function buildQuotationLineRowInnerHtml(options = {}) {
    const today = options.deliveryDate || new Date().toISOString().split('T')[0];
    const isCustom = Boolean(options.isCustom);
    const description = options.description != null ? String(options.description) : '';
    const sourceKey = isCustom ? 'custom' : 'catalog';
    const qty = options.qty != null ? options.qty : 1;
    const disc = options.disc != null ? options.disc : 0;
    const refPrice = options.refPrice != null ? options.refPrice : 0;
    const unitPrice = options.unitPrice != null ? options.unitPrice : 0;

    const productClass = isCustom ? 'item-product-custom' : 'item-product';
    const productValue = isCustom ? escapeQuotationHtml(description) : '';
    const refDisplay = refPrice ? Number(refPrice).toFixed(2) : '—';
    const unitDisplay = unitPrice ? Number(unitPrice).toFixed(2) : '—';

    return `
        <td class="item-source" data-source="${sourceKey}">${QUOTATION_SOURCE_LABELS[sourceKey]}</td>
        <td class="cq-product-cell"><input type="text" class="${productClass}" placeholder="Search or pick product…" value="${productValue}" autocomplete="off" spellcheck="false"></td>
        ${quotationLineStItemExtraCellsHtml()}
        <td><input type="number" class="item-qty" min="0" step="any" value="${qty}"></td>
        <td><input type="number" class="item-discount" min="0" step="any" value="${disc}"></td>
        <td class="item-suggested-price">${refDisplay}</td>
        <td class="item-price">${unitDisplay}</td>
        <td><input type="date" class="item-delivery-date" value="${today}"></td>
        <td class="item-remove">Remove</td>`;
}

function appendQuotationLineRow(container, options = {}) {
    const tr = document.createElement('tr');
    tr.className = 'quotation-line-row';
    tr.innerHTML = buildQuotationLineRowInnerHtml(options);
    container.appendChild(tr);
    const deliveryCell = tr.querySelector('.item-delivery-date');
    if (deliveryCell && !readQuotationLineField(tr, '.item-delivery-date')) {
        writeQuotationLineField(
            tr,
            '.item-delivery-date',
            new Date().toISOString().split('T')[0],
        );
    }
    const productInput = tr.querySelector('input.item-product:not(.item-product-custom)');
    if (productInput) {
        bindCatalogProductInput(productInput);
    }
    return tr;
}

// Add Quotation Item
function addQuotationItem() {
    const container = getQuotationLineItemsBody();
    if (!container) {
        return;
    }
    appendQuotationLineRow(container);
    syncProductDatalist();
    refreshQuotationMiniItemCodes();
}

function setQuotationLineSourceMode(row, source) {
    const productInput = row.querySelector('input.item-product, input.item-product-custom');
    if (!productInput) {
        return;
    }
    writeQuotationLineSource(row, source);
    if (source === 'custom') {
        productInput.classList.remove('item-product');
        productInput.classList.add('item-product-custom');
    } else {
        productInput.classList.remove('item-product-custom');
        productInput.classList.add('item-product');
    }
    writeQuotationLineField(row, 'input.item-product, input.item-product-custom', '');
    writeQuotationLineField(row, '.item-suggested-price', '');
    writeQuotationLineField(row, '.item-price', '');
    clearQuotationLineStItemExtras(row);
    refreshQuotationMiniItemCodes();
    hideCatalogProductPicker();
    if (source === 'catalog') {
        bindCatalogProductInput(productInput);
    }
}

function toggleQuotationLineSource(sourceCell) {
    const row = getQuotationLineRowFrom(sourceCell);
    if (!row) {
        return;
    }
    const next = readQuotationLineSource(row) === 'custom' ? 'catalog' : 'custom';
    setQuotationLineSourceMode(row, next);
}

function initQuotationLineTableEvents() {
    const table = document.querySelector('#quotation-form table.quotation-lines-table');
    if (!table || table.dataset.lineEventsBound === '1') {
        return;
    }
    table.dataset.lineEventsBound = '1';
    table.addEventListener('click', (e) => {
        const td = e.target.closest('td');
        if (!td || !table.contains(td)) {
            return;
        }
        if (td.classList.contains('item-source')) {
            toggleQuotationLineSource(td);
        } else if (td.classList.contains('item-remove')) {
            removeQuotationItem(td);
        }
    });
    table.addEventListener('change', (e) => {
        const el = e.target;
        if (!el || !table.contains(el)) {
            return;
        }
        if (el.matches('.item-product, .item-product-custom, .item-qty, .item-discount, .item-delivery-date')) {
            onQuotationLineCellBlur(el);
        }
    });
    table.addEventListener(
        'blur',
        (e) => {
            const el = e.target;
            if (!el || !table.contains(el)) {
                return;
            }
            if (el.matches('.item-product, .item-product-custom, .item-qty, .item-discount')) {
                onQuotationLineCellBlur(el);
            }
        },
        true,
    );
}

// Remove Quotation Item
function removeQuotationItem(button) {
    const items = getQuotationLineRows();
    if (items.length > 1) {
        getQuotationLineRowFrom(button)?.remove();
        calculateQuotationTotal();
        refreshQuotationMiniItemCodes();
    } else {
        alert('At least one item is required');
    }
}

// Calculate Order Total
function calculateOrderTotal() {
    const items = document.querySelectorAll('#order-items-list .order-item');
    let total = 0;
    
    items.forEach(item => {
        const qty = parseFloat(item.querySelector('.item-qty').value) || 0;
        const price = parseFloat(item.querySelector('.item-price').value) || 0;
        total += qty * price;
    });
    
    document.getElementById('order-total').textContent = `RM ${total.toFixed(2)}`;
}

// Calculate Quotation Total
function calculateQuotationTotal() {
    const items = getQuotationLineRows();
    let total = 0;
    
    items.forEach(item => {
        const qty = readQuotationLineNumber(item, '.item-qty');
        const unitPrice = readQuotationLineNumber(item, '.item-price');
        const discount = readQuotationLineNumber(item, '.item-discount');
        const lineSubtotal = qty * unitPrice;
        const discountAmount = discount > 0 ? discount : 0;
        total += Math.max(0, lineSubtotal - discountAmount);
    });
    
    document.getElementById('quotation-total').textContent = `RM ${total.toFixed(2)}`;
}

function clearQuotationLineStItemExtras(row) {
    if (!row) {
        return;
    }
    [
        '.item-udf-moq',
        '.item-udf-dleadtime',
        '.item-udf-bundle',
        '.item-udf-thickness',
        '.item-udf-width',
        '.item-udf-length',
    ].forEach((sel) => writeQuotationLineField(row, sel, ''));
}

function applyQuotationLineStItemExtras(row, data) {
    if (!row) {
        return;
    }
    const src = data || {};
    const pick = (key) => {
        const v = src[key];
        if (v == null) {
            return '';
        }
        return String(v).trim();
    };
    const fields = [
        ['.item-udf-moq', 'udfMoq'],
        ['.item-udf-dleadtime', 'udfDleadtime'],
        ['.item-udf-bundle', 'udfBundle'],
        ['.item-udf-thickness', 'udfThickness'],
        ['.item-udf-width', 'udfWidth'],
        ['.item-udf-length', 'udfLength'],
    ];
    fields.forEach(([sel, key]) => writeQuotationLineField(row, sel, pick(key)));
}

function applyQuotationLineStItemExtrasFromProduct(row, product) {
    if (!row) {
        return;
    }
    if (!product) {
        clearQuotationLineStItemExtras(row);
        return;
    }
    applyQuotationLineStItemExtras(row, {
        udfMoq: stockItemUdfDisplayValue(product, 'UDF_MOQ', 'udf_moq'),
        udfDleadtime: stockItemUdfDisplayValue(product, 'UDF_DLEADTIME', 'udf_dleadtime'),
        udfBundle: stockItemUdfDisplayValue(product, 'UDF_BUNDLE', 'udf_bundle'),
        udfThickness: stockItemUdfDisplayValue(product, 'UDF_THICKNESS', 'udf_thickness'),
        udfWidth: stockItemUdfDisplayValue(product, 'UDF_WIDTH', 'udf_width'),
        udfLength: stockItemUdfDisplayValue(product, 'UDF_LENGTH', 'udf_length'),
    });
}

function stockItemUdfDisplayValue(product, ...keys) {
    if (!product || typeof product !== 'object') {
        return '';
    }
    const lower = {};
    Object.keys(product).forEach((k) => {
        lower[String(k).toLowerCase()] = product[k];
    });
    for (const key of keys) {
        let v = product[key];
        if (v == null) {
            v = lower[String(key).toLowerCase()];
        }
        if (v != null && String(v).trim() !== '') {
            return String(v).trim();
        }
    }
    return '';
}

function findCatalogProductByDescription(description) {
    const d = String(description || '').trim();
    if (!d || !availableProducts.length) {
        return null;
    }
    const code = resolveCatalogItemCodeFromDescription(d);
    const norm = (s) => String(s || '').trim().replace(/\s+/g, ' ');
    const dNorm = norm(d);
    const codeNorm = norm(code);
    return (
        availableProducts.find((p) => {
            const c = norm(p.CODE ?? p.code ?? '');
            const desc = norm(p.DESCRIPTION ?? p.description ?? '');
            if (codeNorm && c && c.toUpperCase() === codeNorm.toUpperCase()) {
                return true;
            }
            if (dNorm && desc && desc.toUpperCase() === dNorm.toUpperCase()) {
                return true;
            }
            if (dNorm && c && c.toUpperCase() === dNorm.toUpperCase()) {
                return true;
            }
            return false;
        }) || null
    );
}

// Clear Order Form
function clearOrderForm() {
    if (confirm('Are you sure you want to clear the form?')) {
        document.getElementById('order-form').reset();
        const container = document.getElementById('order-items-list');
        container.innerHTML = `
            <div class="order-item">
                <div class="item-row">
                    <input type="text" class="item-product" placeholder="Product name..." list="product-list">
                    <input type="number" class="item-qty" placeholder="Qty" min="1" value="1" onchange="calculateOrderTotal()">
                    <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" onchange="calculateOrderTotal()">
                    <button type="button" class="btn-remove" onclick="removeOrderItem(this)">✕</button>
                </div>
            </div>
        `;
        calculateOrderTotal();
    }
}

// Clear Quotation Form
function clearQuotationForm() {
    if (confirm('Are you sure you want to clear the form?')) {
        document.getElementById('quotation-form').reset();
        const quotationDescription = document.getElementById('quotation-description');
        if (quotationDescription) {
            quotationDescription.value = 'Quotation';
        }
        const container = document.getElementById('quotation-line-items');
        container.innerHTML = '';
        appendQuotationLineRow(container);
        syncProductDatalist();
        calculateQuotationTotal();
        loadUserInfo();
        refreshQuotationMiniItemCodes();
    }
}

// Fetch product price when a product is selected
async function fetchProductPrice(input) {
    if (input.classList && input.classList.contains('item-product-custom')) {
        return;
    }

    const row = getQuotationLineRowFrom(input) || input.closest('.item-row');
    const inQuotationTable = Boolean(input.closest && input.closest('#quotation-line-items'));
    const productName = inQuotationTable && row
        ? (
            readQuotationLineField(row, '.item-product')
            || readQuotationLineField(row, '.item-product-custom')
            || String(input.value || '').trim()
        )
        : String(input.value || '').trim();
    if (!productName) {
        if (row && inQuotationTable) {
            clearQuotationLineStItemExtras(row);
        }
        return;
    }

    if (row && inQuotationTable) {
        applyQuotationLineStItemExtrasFromProduct(row, findCatalogProductByDescription(productName));
    }

    const quotationLine = getQuotationLineRowFrom(input);
    if (quotationLine) {
        quotationLine.dataset.productDescription = productName;
    }
    const orderItem = input.closest('.order-item');
    if (orderItem) {
        orderItem.dataset.productDescription = productName;
    }
    
    try {
        const response = await fetch(`/api/get_product_price?description=${encodeURIComponent(productName)}`);
        const data = await response.json();
        
        if (data.success && data.price !== undefined && data.price !== null) {
            if (row && inQuotationTable) {
                if (data.suggestedPrice !== undefined && data.suggestedPrice !== null) {
                    writeQuotationLineField(row, '.item-suggested-price', Number(data.suggestedPrice).toFixed(2));
                } else {
                    writeQuotationLineField(row, '.item-suggested-price', '');
                    if (data.suggestedReason) {
                        console.log('Suggested price unavailable:', data.suggestedReason, '| source:', data.source, '| rule:', data.matchedRuleCode);
                    }
                }
                const stItemPrice = Number(data.stItemPrice);
                if (Number.isFinite(stItemPrice)) {
                    writeQuotationLineField(row, '.item-price', stItemPrice.toFixed(2));
                } else {
                    writeQuotationLineField(row, '.item-price', data.price.toFixed(2));
                }
            } else if (row) {
                const suggestedPriceInput = row.querySelector('.item-suggested-price');
                const unitPriceInput = row.querySelector('.item-price');
                if (suggestedPriceInput) {
                    if (data.suggestedPrice !== undefined && data.suggestedPrice !== null) {
                        suggestedPriceInput.value = Number(data.suggestedPrice).toFixed(2);
                    } else {
                        suggestedPriceInput.value = '';
                    }
                }
                if (unitPriceInput) {
                    const stItemPrice = Number(data.stItemPrice);
                    unitPriceInput.value = Number.isFinite(stItemPrice)
                        ? stItemPrice.toFixed(2)
                        : data.price.toFixed(2);
                }
            }
            // Trigger total recalculation
            const isOrder = input.closest && input.closest('#order-items-list') !== null;
            if (isOrder) {
                calculateOrderTotal();
            } else {
                calculateQuotationTotal();
            }
            if (row && inQuotationTable) {
                applyQuotationLineStItemExtras(row, {
                    udfMoq: data.udfMoq,
                    udfDleadtime: data.udfDleadtime,
                    udfBundle: data.udfBundle,
                    udfThickness: data.udfThickness,
                    udfWidth: data.udfWidth,
                    udfLength: data.udfLength,
                });
            }
        } else if (row && inQuotationTable) {
            clearQuotationLineStItemExtras(row);
        }
    } catch (error) {
        console.error('Failed to fetch product price:', error);
        if (row && inQuotationTable) {
            clearQuotationLineStItemExtras(row);
        }
    }
    if (inQuotationTable) {
        refreshQuotationMiniItemCodes();
    }
}

// Store products globally
let availableProducts = [];

/** Scalar map from GET /api/get_user_info (SQL API → salesquotation). */
let quotationCustomerScalars = {};

// Load Products for Autocomplete
async function loadProducts() {
    try {
        const response = await fetch('/api/get_stock_items');
        const data = await response.json();
        
        if (data.success && data.items) {
            availableProducts = data.items;
            syncProductDatalist();

            // Legacy rows may still use <select>; create-quotation uses searchable <input list="product-list">.
            document.querySelectorAll('.item-product').forEach((el) => {
                if (el.tagName === 'SELECT') {
                    populateProductSelect(el);
                }
            });
            refreshQuotationMiniItemCodes();
        }
    } catch (error) {
        console.error('Failed to load products:', error);
    }
}

function syncProductDatalist() {
    const datalist = document.getElementById('product-list');
    if (!datalist) {
        initQuotationCatalogProductPickers();
        return;
    }
    datalist.innerHTML = '';
    availableProducts.forEach((item) => {
        const rawCode = item.CODE ?? item.code ?? item.StockCode ?? item.stockCode ?? '';
        const code = rawCode != null ? String(rawCode).trim() : '';
        const rawDesc = item.DESCRIPTION ?? item.description ?? item.Description ?? '';
        const desc = rawDesc != null ? String(rawDesc).trim() : '';
        const value = desc || code;
        if (!value) {
            return;
        }
        const option = document.createElement('option');
        option.value = value;
        if (code && desc) {
            option.label = `${desc} (${code})`;
        }
        datalist.appendChild(option);
    });
    initQuotationCatalogProductPickers();
}

let cqProductPickerActiveInput = null;
let cqProductPickerCloseTimer = null;

function normalizeProductSearchText(value) {
    return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function getCatalogProductPickerOptions() {
    const options = [];
    const seen = new Set();
    (availableProducts || []).forEach((item) => {
        const code = String(item.CODE ?? item.code ?? item.StockCode ?? item.stockCode ?? '').trim();
        const desc = String(item.DESCRIPTION ?? item.description ?? item.Description ?? '').trim();
        const value = desc || code;
        if (!value) {
            return;
        }
        const key = normalizeProductSearchText(value);
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        options.push({
            value,
            code,
            label: code && desc ? `${desc} (${code})` : value,
        });
    });
    options.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
    return options;
}

function ensureCatalogProductPicker() {
    let picker = document.getElementById('cq-product-picker');
    if (picker) {
        return picker;
    }
    picker = document.createElement('div');
    picker.id = 'cq-product-picker';
    picker.className = 'cq-product-picker';
    picker.hidden = true;
    picker.innerHTML = `
        <div class="cq-product-picker-header">Choose product</div>
        <input type="text" class="cq-product-picker-search" placeholder="Type to filter…" autocomplete="off" />
        <ul class="cq-product-picker-list" role="listbox"></ul>`;
    document.body.appendChild(picker);

    const search = picker.querySelector('.cq-product-picker-search');
    search.addEventListener('input', () => {
        if (cqProductPickerActiveInput) {
            renderCatalogProductPickerList(cqProductPickerActiveInput, search.value);
        }
    });
    search.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            hideCatalogProductPicker();
        }
    });
    document.addEventListener('mousedown', (event) => {
        if (picker.hidden) {
            return;
        }
        if (picker.contains(event.target)) {
            return;
        }
        if (event.target === cqProductPickerActiveInput) {
            return;
        }
        hideCatalogProductPicker();
    });
    return picker;
}

function positionCatalogProductPicker(input, picker) {
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

function renderCatalogProductPickerList(input, filterText) {
    const picker = ensureCatalogProductPicker();
    const list = picker.querySelector('.cq-product-picker-list');
    const query = normalizeProductSearchText(filterText);
    const row = getQuotationLineRowFrom(input);
    const current = normalizeProductSearchText(
        row ? readQuotationLineField(row, '.item-product') : input.value,
    );
    const matches = getCatalogProductPickerOptions().filter((opt) => {
        if (!query) {
            return true;
        }
        const blob = normalizeProductSearchText(`${opt.label} ${opt.code} ${opt.value}`);
        return blob.includes(query);
    });

    list.innerHTML = '';
    if (!matches.length) {
        const empty = document.createElement('li');
        empty.className = 'cq-product-picker-empty';
        empty.textContent = 'No products match';
        list.appendChild(empty);
        return;
    }

    const limit = 150;
    matches.slice(0, limit).forEach((opt) => {
        const item = document.createElement('li');
        item.className = 'cq-product-picker-option';
        item.setAttribute('role', 'option');
        item.textContent = opt.label;
        if (normalizeProductSearchText(opt.value) === current) {
            item.classList.add('is-current');
        }
        item.addEventListener('mousedown', (event) => {
            event.preventDefault();
            applyCatalogProductSelection(input, opt.value);
        });
        list.appendChild(item);
    });
    if (matches.length > limit) {
        const more = document.createElement('li');
        more.className = 'cq-product-picker-more';
        more.textContent = `Showing ${limit} of ${matches.length} — type to narrow`;
        list.appendChild(more);
    }
}

function applyCatalogProductSelection(input, value) {
    const row = getQuotationLineRowFrom(input);
    if (!row || !input) {
        return;
    }
    writeQuotationLineField(row, '.item-product', value);
    hideCatalogProductPicker();
    fetchProductPrice(input);
}

function showCatalogProductPicker(input) {
    if (!input || input.classList.contains('item-product-custom')) {
        return;
    }
    if (!document.body.classList.contains('create-quotation-page')) {
        return;
    }
    clearTimeout(cqProductPickerCloseTimer);
    const picker = ensureCatalogProductPicker();
    cqProductPickerActiveInput = input;
    positionCatalogProductPicker(input, picker);
    const search = picker.querySelector('.cq-product-picker-search');
    search.value = '';
    renderCatalogProductPickerList(input, '');
    picker.hidden = false;
    requestAnimationFrame(() => search.focus());
}

function hideCatalogProductPicker() {
    const picker = document.getElementById('cq-product-picker');
    if (picker) {
        picker.hidden = true;
    }
    cqProductPickerActiveInput = null;
}

function bindCatalogProductInput(input) {
    if (!input || input.dataset.cqProductPickerBound === '1') {
        return;
    }
    if (!input.classList.contains('item-product') || input.classList.contains('item-product-custom')) {
        return;
    }
    input.dataset.cqProductPickerBound = '1';
    input.removeAttribute('list');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');
    if (!input.placeholder || input.placeholder === 'Product') {
        input.placeholder = 'Search or pick product…';
    }

    const openPicker = () => showCatalogProductPicker(input);
    input.addEventListener('focus', openPicker);
    input.addEventListener('click', openPicker);
    input.addEventListener('input', () => {
        if (cqProductPickerActiveInput !== input) {
            return;
        }
        const picker = document.getElementById('cq-product-picker');
        const search = picker ? picker.querySelector('.cq-product-picker-search') : null;
        if (search) {
            search.value = input.value;
            renderCatalogProductPickerList(input, input.value);
        }
    });
    input.addEventListener('blur', () => {
        cqProductPickerCloseTimer = setTimeout(hideCatalogProductPicker, 200);
    });

    const cell = input.closest('td');
    if (cell) {
        cell.classList.add('cq-product-cell');
    }
}

function initQuotationCatalogProductPickers() {
    if (!document.body.classList.contains('create-quotation-page')) {
        return;
    }
    document.querySelectorAll('#quotation-line-items input.item-product:not(.item-product-custom)').forEach((input) => {
        bindCatalogProductInput(input);
    });
}

// Populate a product select element
function populateProductSelect(selectElement) {
    const currentValue = selectElement.value;
    selectElement.innerHTML = '<option value="">Select product...</option>';
    
    availableProducts.forEach(item => {
        const option = document.createElement('option');
        const rawCode = item.CODE ?? item.code ?? item.StockCode ?? item.stockCode ?? '';
        const code = rawCode != null ? String(rawCode).trim() : '';
        const rawDesc = item.DESCRIPTION ?? item.description ?? item.Description ?? '';
        const desc = rawDesc != null ? String(rawDesc).trim() : '';
        option.value = desc || code;
        option.textContent = desc ? (code ? `${desc} (${code})` : desc) : code;
        if (code) {
            option.setAttribute('data-stock-code', code);
        }
        selectElement.appendChild(option);
    });
    
    // Restore previous value if it exists
    if (currentValue) {
        selectElement.value = currentValue;
    }
}

function resolveCatalogItemCodeFromDescription(description) {
    const d = String(description || '').trim().replace(/\s+/g, ' ');
    if (!d || !availableProducts.length) {
        return '';
    }
    const norm = (s) => String(s || '').trim().replace(/\s+/g, ' ');
    const codeOf = (p) => {
        const c = p.CODE ?? p.code ?? p.StockCode ?? p.stockCode;
        return c != null ? String(c).trim() : '';
    };
    const descOf = (p) => {
        const x = p.DESCRIPTION ?? p.description ?? p.Description;
        return x != null ? String(x).trim() : '';
    };
    const hit = availableProducts.find(
        (p) =>
            (descOf(p) && norm(descOf(p)) === d) ||
            (codeOf(p) && norm(codeOf(p)) === d)
    );
    const resolved = hit ? codeOf(hit) : '';
    if (resolved) {
        return resolved;
    }
    return '';
}

function refreshQuotationMiniItemCodes() {
    const el = document.getElementById('quotation-mini-item-codes');
    if (!el) {
        return;
    }
    const parts = [];
    getQuotationLineRows().forEach((row) => {
        const source = readQuotationLineSource(row);
        if (source === 'custom') {
            return;
        }
        const desc = readQuotationLineField(row, '.item-product');
        if (!desc) {
            return;
        }
        const code = resolveCatalogItemCodeFromDescription(desc);
        if (code) {
            parts.push(code);
        }
    });
    /* Hyphen separators (not middle dots) so codes read clearly next to slashes, e.g. ISCT - CCE/Grey-Chair - … */
    el.textContent = parts.length ? parts.join(' - ') : '';
}

const orderForm = document.getElementById('order-form');
if (orderForm) {
    orderForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const items = [];
        document.querySelectorAll('#order-items-list .order-item').forEach(item => {
            const product = item.querySelector('.item-product').value.trim();
            const qty = parseFloat(item.querySelector('.item-qty').value) || 0;
            const price = parseFloat(item.querySelector('.item-price').value) || 0;
            const discount = parseFloat(item.querySelector('.item-discount')?.value) || 0;
            
            if (product && qty > 0 && price >= 0) {
                items.push({ product, qty, price, discount });
            }
        });
        
        if (items.length === 0) {
            alert('Please add at least one valid item');
            return;
        }
        
        const orderData = {
            description: document.getElementById('order-description').value.trim(),
            items: items
        };
        
        try {
            const response = await fetch('/api/create_order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(orderData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert(`Order #${result.orderid} created successfully!`);
                clearOrderForm();
            } else {
                alert('Failed to create order: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating order:', error);
            alert('Failed to create order. Please try again.');
        }
    });
}

const quotationForm = document.getElementById('quotation-form');
if (quotationForm) {
    const saveDraftButton = document.getElementById('save-draft-btn');

    if (saveDraftButton) {
        saveDraftButton.addEventListener('click', async function() {
            const quotationData = buildQuotationPayload();
            const draftDockey = quotationForm.dataset.draftDockey;

            if (draftDockey) {
                quotationData.dockey = draftDockey;
            }

            try {
                saveDraftButton.disabled = true;
                const response = await fetch('/api/save_draft_quotation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(quotationData)
                });

                if (response.status === 401) {
                    alert('Your session has expired. Please log in again.');
                    window.location.href = '/login';
                    return;
                }

                const result = await response.json();
                if (result.success) {
                    if (result.dockey) {
                        quotationForm.dataset.draftDockey = result.dockey;
                    }
                    window.location.href = '/view-quotation?tab=drafts';
                    return;
                } else {
                    alert('Failed to save draft: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error saving draft quotation:', error);
                alert('Failed to save draft. Please try again.');
            } finally {
                saveDraftButton.disabled = false;
            }
        });
    }

    quotationForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const quotationData = buildQuotationPayload();
        if (quotationData.items.length === 0) {
            alert('Please add at least one valid item');
            return;
        }

        const missingStockCodes = quotationData.items.filter(
            (it) => it.source === 'catalog' && !it.itemCode
        );
        if (missingStockCodes.length) {
            const ok = window.confirm(
                'Some catalog lines have no stock item code (try reloading the page so products load, then pick again from the dropdown). ' +
                    'Submitting without codes may be very slow or fail. Continue anyway?'
            );
            if (!ok) {
                return;
            }
        }

        const items = quotationData.items;
        const dockey = quotationForm.dataset.dockey;
        const draftDockey = quotationForm.dataset.draftDockey;
        
        // DEBUG: Log the data being sent
        console.log('Quotation Data being sent:', quotationData);
        
        // Include dockey if editing existing SL_QT quotation
        if (dockey) {
            quotationData.dockey = dockey;
        }
        // Pass draftDockey so server can delete the draft after successful submission
        if (draftDockey) {
            quotationData.draftDockey = draftDockey;
        }
        
        try {
            const response = await fetch('/api/create_quotation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(quotationData)
            });

            if (response.status === 401) {
                alert('Your session has expired. Please log in again.');
                window.location.href = '/login';
                return;
            }
            
            const result = await response.json();
            
            // DEBUG: Log the API response
            console.log('API Response:', result);
            
            if (result.success) {
                const displayDocNo = result.docno || result.quotationid || result.dockey;
                const message = dockey ?
                    `Quotation ${displayDocNo} updated successfully!` :
                    `Quotation ${displayDocNo} created and is awaiting approval.`;

                // Send quotation pending approval email
                try {
                    // Calculate total amount (accounting for discount)
                    let totalAmount = 0;
                    items.forEach(item => {
                        const unitPrice = item.price || 0;
                        const lineSubtotal = item.qty * unitPrice;
                        const discountAmount = item.discount > 0 ? item.discount : 0;
                        totalAmount += Math.max(0, lineSubtotal - discountAmount);
                    });
                    
                    const emailData = {
                        docno: displayDocNo,
                        dockey: result.dockey,
                        totalAmount: totalAmount,
                        items: items,
                        companyName: quotationData.companyName
                    };
                    
                    fetch('/api/send_quotation_email', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(emailData)
                    }).then(emailResponse => emailResponse.json())
                      .then(emailResult => {
                          if (emailResult.success) {
                              console.log('Email sent successfully:', emailResult.message);
                          } else {
                              console.warn('Email sending failed:', emailResult.error);
                          }
                      }).catch(emailError => {
                          console.error('Error sending email:', emailError);
                      });
                } catch (emailError) {
                    console.error('Failed to send quotation email:', emailError);
                }
                
                alert(message);

                // Redirect to view quotations — Pending tab (newly submitted / UDF_STATUS PENDING)
                window.location.href = '/view-quotation?tab=pending';
            } else {
                const err = result.error || 'Unknown error';
                if (result.errorCode === 'SQL_API_TIMEOUT') {
                    alert(
                        err + '\n\n(HTTP 504: accounting service did not answer in time. ' +
                        'Check SQL Accounting for a duplicate before trying again.)'
                    );
                } else {
                    alert('Failed to save quotation: ' + err);
                }
            }
        } catch (error) {
            console.error('Error saving quotation:', error);
            alert('Failed to save quotation. Please try again.');
        }
    });
}

// Load user info (customer info including company, address, phone, and credit term) for quotation form
async function loadUserInfo() {
    try {
        const response = await fetch('/api/get_user_info');
        if (!response.ok) {
            console.warn('Customer info lookup failed with status:', response.status);
            setDefaultCustomerInfo();
            return;
        }

        const data = await response.json();

        if (data.success && data.data) {
            const source = data.data || {};
            ingestCustomerApiPayload(source);
            renderCustomerAllFields(source.displayFields);
            syncProminentCustomerFields();

            const pickFrom = (obj, keys) => {
                if (!obj || typeof obj !== 'object') return '';
                for (const key of keys) {
                    const raw = obj[key];
                    if (raw === undefined || raw === null) continue;
                    const value = String(raw).trim();
                    if (value) return value;
                }
                return '';
            };

            const dept = pickFrom(source, ['DEPARTMENT', 'department']) || '';
            const deptRow = document.getElementById('quotation-department-row');
            const deptEl = document.getElementById('quotation-department');
            if (deptRow && deptEl) {
                if (dept) {
                    deptEl.textContent = dept;
                    deptRow.style.display = '';
                } else {
                    deptRow.style.display = 'none';
                    deptEl.textContent = '';
                }
            }

            // Customer email: keep server-rendered session login email (#quotation-customer). Do not replace
            // with AR_CUSTOMER master UDF_EMAIL/EMAIL — users may log in via UDF_EMAIL2/3… (jason.choo…).
        } else {
            // Set default N/A values if data not found
            console.warn('Customer data not found:', data.error);
            setDefaultCustomerInfo();
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        setDefaultCustomerInfo();
    }
}

// Helper function to set all customer fields to N/A
function setDefaultCustomerInfo() {
    quotationCustomerScalars = {};
    renderCustomerAllFields([]);
    syncProminentCustomerFields();
    const deptRow = document.getElementById('quotation-department-row');
    const deptEl = document.getElementById('quotation-department');
    if (deptRow && deptEl) {
        deptRow.style.display = 'none';
        deptEl.textContent = '';
    }
}

// Load draft quotation data if dockey is present
async function loadDraftQuotation(dockey) {
    if (!dockey) return;
    
    try {
        const response = await fetch(`/api/get_quotation_details?dockey=${dockey}`);
        const data = await response.json();
        
        if (data.success && data.data) {
            const quotation = data.data;
            
            // Populate form fields
            const descriptionField = document.getElementById('quotation-description');
            if (descriptionField && quotation.DESCRIPTION) {
                descriptionField.value = quotation.DESCRIPTION;
            }
            
            const validityField = document.getElementById('quotation-validity');
            if (validityField && quotation.VALIDITY) {
                // Convert Firebird date format to HTML date input format (YYYY-MM-DD)
                const validityDate = quotation.VALIDITY.split(' ')[0];
                validityField.value = validityDate;
            }
            
            await loadUserInfo();

            // Populate items
            if (quotation.items && quotation.items.length > 0) {
                const container = getQuotationLineItemsBody();
                if (!container) {
                    ensureDefaultQuotationLineRow();
                    return;
                }
                container.innerHTML = ''; // Clear default item

                quotation.items.forEach(item => {
                    const explicitSource = (item.SOURCE || '').toString().toLowerCase();
                    const description = (item.DESCRIPTION || '').toString();
                    const hasCatalogMatch = !description || !availableProducts.length || availableProducts.some(product => {
                        const candidate = (product.DESCRIPTION || product.CODE || '').toString();
                        return candidate === description;
                    });
                    const source = explicitSource || (hasCatalogMatch ? 'catalog' : 'custom');
                    const isCustom = source !== 'catalog';
                    const newItem = appendQuotationLineRow(container, {
                        isCustom,
                        description,
                        qty: item.QTY || 1,
                        disc: item.DISC || 0,
                        refPrice: item.UDF_STDPRICE || 0,
                        unitPrice: item.UNITPRICE || 0,
                        deliveryDate: item.DELIVERYDATE || new Date().toISOString().split('T')[0],
                    });
                    syncProductDatalist();

                    const productField = newItem.querySelector('.item-product');
                    if (!isCustom && item.DESCRIPTION && productField) {
                        writeQuotationLineField(newItem, '.item-product', item.DESCRIPTION);
                        fetchProductPrice(productField);
                    }
                });
                
                calculateQuotationTotal();
                refreshQuotationMiniItemCodes();
            }
            
            // Update page title to indicate editing
            const pageTitle = document.querySelector('.header-title');
            if (pageTitle) {
                pageTitle.textContent = 'Edit Quotation';
            }
            
            const formTitle = document.querySelector('#quotation-form').previousElementSibling;
            if (formTitle && formTitle.tagName === 'H3') {
                formTitle.textContent = `Edit Quotation - ${quotation.DOCNO || ''}`;
            }
        } else {
            console.error('Failed to load draft quotation:', data.error);
        }
        ensureDefaultQuotationLineRow();
    } catch (error) {
        console.error('Error loading draft quotation:', error);
        ensureDefaultQuotationLineRow();
    }
}

// Load a SL_QTDRAFT draft into the quotation form for editing
async function loadSlQtDraftForEdit(draftDockey) {
    if (!draftDockey) return;
    try {
        const response = await fetch(`/api/get_draft_quotation_details?dockey=${draftDockey}`);
        const data = await response.json();
        if (!data.success || !data.data) {
            console.error('Failed to load SL_QTDRAFT draft:', data.error);
            return;
        }
        const draft = data.data;
        const fillField = (id, val) => {
            const el = document.getElementById(id);
            if (!el || val == null) return;
            const tag = (el.tagName || '').toUpperCase();
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
                el.value = val;
            } else {
                el.textContent = String(val).trim();
            }
        };
        fillField('quotation-description', draft.DESCRIPTION);
        if (draft.VALIDITY) {
            fillField('quotation-validity', draft.VALIDITY.split(' ')[0]);
        }
        await loadUserInfo();

        if (draft.items && draft.items.length > 0) {
            const container = getQuotationLineItemsBody();
            if (!container) {
                ensureDefaultQuotationLineRow();
                return;
            }
            container.innerHTML = '';
            draft.items.forEach(item => {
                const explicitSource = (item.SOURCE || '').toString().toLowerCase();
                const description = (item.DESCRIPTION || '').toString();
                const hasCatalogMatch = !description || !availableProducts.length || availableProducts.some(product => {
                    const candidate = (product.DESCRIPTION || product.CODE || '').toString();
                    return candidate === description;
                });
                const source = explicitSource || (hasCatalogMatch ? 'catalog' : 'custom');
                const isCustom = source !== 'catalog';
                const newItem = appendQuotationLineRow(container, {
                    isCustom,
                    description,
                    qty: item.QTY || 1,
                    disc: item.DISC || 0,
                    refPrice: item.UDF_STDPRICE || 0,
                    unitPrice: item.UNITPRICE || 0,
                    deliveryDate: item.DELIVERYDATE || new Date().toISOString().split('T')[0],
                });
                syncProductDatalist();

                const productField = newItem.querySelector('.item-product');
                const savedCode = (item.ITEMCODE != null && String(item.ITEMCODE).trim())
                    ? String(item.ITEMCODE).trim()
                    : '';
                if (!isCustom && item.DESCRIPTION && productField) {
                    let rowLabel = String(item.DESCRIPTION).trim();
                    if (savedCode && availableProducts && availableProducts.length) {
                        const byCode = availableProducts.find(
                            (p) => String(p.CODE || '').trim() === savedCode
                        );
                        if (byCode) {
                            rowLabel = String(byCode.DESCRIPTION || byCode.CODE || rowLabel).trim();
                        }
                    }
                    writeQuotationLineField(newItem, '.item-product', rowLabel);
                    fetchProductPrice(productField);
                }
            });
            calculateQuotationTotal();
            refreshQuotationMiniItemCodes();
        }

        const quotationForm = document.getElementById('quotation-form');
        if (quotationForm) quotationForm.dataset.draftDockey = draftDockey;

        const pageTitle = document.querySelector('.header-title');
        if (pageTitle) pageTitle.textContent = 'Edit Draft Quotation';
        const formTitle = document.querySelector('#quotation-form').previousElementSibling;
        if (formTitle && formTitle.tagName === 'H3') formTitle.textContent = `Edit Draft - ${draft.DOCNO || ''}`;
        ensureDefaultQuotationLineRow();
    } catch (error) {
        console.error('Error loading SL_QTDRAFT draft:', error);
        ensureDefaultQuotationLineRow();
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async function() {
    repairCreateQuotationLinesUi();

    const quotationForm = document.getElementById('quotation-form');
    const urlParams = new URLSearchParams(window.location.search);
    const draftDockey = urlParams.get('draftDockey');
    const dockey = quotationForm ? quotationForm.dataset.dockey : null;

    if (draftDockey) {
        await loadProducts();
        await loadSlQtDraftForEdit(draftDockey);
    } else if (dockey) {
        await loadProducts();
        await loadDraftQuotation(dockey);
    } else {
        await Promise.all([loadProducts(), loadUserInfo()]);
        const quotationDescription = document.getElementById('quotation-description');
        if (quotationDescription) {
            quotationDescription.value = 'Quotation';
        }
    }

    // Add change listeners to calculate totals
    document.querySelectorAll('#order-items-list .item-qty, #order-items-list .item-price').forEach(input => {
        input.addEventListener('change', calculateOrderTotal);
    });

    initQuotationLineTableEvents();
    repairCreateQuotationLinesUi();
    ensureDefaultQuotationLineRow();
    initQuotationCatalogProductPickers();
});

// AUTO-FILL FROM CHATBOT
// Auto-add product from chatbot to quotation form
function updateChatSuggestionButtonState(button, label, stateClass) {
    if (!button) {
        return;
    }

    if (!button.dataset.originalLabel) {
        button.dataset.originalLabel = button.textContent;
    }

    button.textContent = label;
    button.classList.remove('is-added', 'is-updated');
    if (stateClass) {
        button.classList.add(stateClass);
    }

    if (button._resetStateTimeout) {
        clearTimeout(button._resetStateTimeout);
    }

    button._resetStateTimeout = setTimeout(() => {
        button.textContent = button.dataset.originalLabel || button.textContent;
        button.classList.remove('is-added', 'is-updated');
    }, 1600);
}

function escapeChatHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeInlineJsString(value) {
    return String(value ?? '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'");
}

function sendQuickChatMessage(message, sourceButton = null) {
    const popupMessagesEl = document.getElementById('quotation-chat-popup-messages');
    const legacyMessagesEl = document.getElementById('chat-popup-messages');
    const messagesContainer = popupMessagesEl || legacyMessagesEl;
    const useQuotationPopup = Boolean(popupMessagesEl && messagesContainer === popupMessagesEl);

    let activeChatId = null;
    if (typeof window.getQuotationPopupChatId === 'function') {
        activeChatId = window.getQuotationPopupChatId();
    }
    if (activeChatId == null || activeChatId === '') {
        activeChatId = quotationChatId;
    }

    if (!messagesContainer || activeChatId == null || activeChatId === '' || !message) {
        return;
    }

    const targetBotMessage = sourceButton
        ? sourceButton.closest('.quotation-chat-message.bot-message, .chat-message.bot-message')
        : null;

    if (sourceButton) {
        sourceButton.disabled = true;
    }

    fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message, chatid: activeChatId })
    })
    .then(res => {
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return res.json();
    })
    .then(data => {
        if (!data) return;
        const reply =
            typeof data.reply === 'string'
                ? data.reply
                : (data.error && String(data.error)) || 'Sorry, that request did not return a reply.';
        let renderedHtml = buildChatReplyHtml(reply);
        if (useQuotationPopup) {
            renderedHtml = renderedHtml.replace(
                'class="chat-popup-message-content rich-message-content"',
                'class="quotation-chat-popup-message-content rich-message-content"'
            );
        }

        if (targetBotMessage) {
            targetBotMessage.innerHTML = renderedHtml;
            /* scrollIntoView on nodes inside position:fixed can scroll the document and move the popup off-screen */
            if (useQuotationPopup && messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            } else {
                targetBotMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        } else {
            const botMsgDiv = document.createElement('div');
            botMsgDiv.className = useQuotationPopup
                ? 'quotation-chat-message bot-message'
                : 'chat-message bot-message';
            botMsgDiv.innerHTML = renderedHtml;
            messagesContainer.appendChild(botMsgDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    })
    .catch(error => {
        console.error('Error requesting catalog page:', error);
        if (targetBotMessage) {
            const existingContent = targetBotMessage.querySelector(
                '.chat-popup-message-content, .quotation-chat-popup-message-content'
            );
            if (existingContent) {
                existingContent.insertAdjacentHTML('beforeend', '<div class="chat-reply-line">Unable to load that page right now. Please try again.</div>');
            }
        }
    })
    .finally(() => {
        if (sourceButton && sourceButton.isConnected) {
            sourceButton.disabled = false;
        }
    });
}

const CHAT_PRODUCT_TAG_RE = /\[PRODUCT:\s*([^|\]]+?)\s*\|\s*qty:\s*(\d+)\s*\]/gi;
const CHAT_PAGE_TAG_RE = /\[PAGE:\s*(\d+)\s*\|\s*label:\s*([^\]]+)\]/gi;
const CHAT_LIST_LINE_RE = /^(?:\d+[\.\)]\s+|[-*•]\s+)(.+)$/;
const CHAT_CATALOG_META_LINE_RE =
    /^(Showing\s+\d|That is the end|Use the arrows|Let me know|Here are the matching|Here are more matching|No item found|Try one of these)/i;

function isCatalogProductListLine(trimmedLine) {
    const line = String(trimmedLine || '').trim();
    if (!line || CHAT_CATALOG_META_LINE_RE.test(line)) {
        return false;
    }
    return CHAT_LIST_LINE_RE.test(line);
}

function catalogLineProductName(label) {
    let name = stripChatProductTags(String(label || '').trim());
    name = name.replace(/\s*-\s*RM\s+[\d.,]+$/i, '').trim();
    return name || String(label || '').trim();
}

function stripChatProductTags(line) {
    return String(line || '')
        .replace(new RegExp(CHAT_PRODUCT_TAG_RE.source, 'gi'), '')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

function renderChatProductButton(productName, quantity, label) {
    const escapedProductName = escapeInlineJsString(productName);
    const escapedLabel = escapeChatHtml(label || productName);
    const qty = Number(quantity) || 1;
    return `<button type="button" class="chat-inline-product-action" onclick="addProductToQuotation('${escapedProductName}', ${qty}, this); return false;">${escapedLabel}</button>`;
}

function buildChatReplyHtml(reply) {
    const pageMatches = Array.from(reply.matchAll(new RegExp(CHAT_PAGE_TAG_RE.source, 'gi')));
    const bodyText = reply.replace(new RegExp(CHAT_PAGE_TAG_RE.source, 'gi'), '');
    const allProductTags = Array.from(bodyText.matchAll(new RegExp(CHAT_PRODUCT_TAG_RE.source, 'gi'))).map((match) => ({
        name: match[1].trim(),
        qty: Number(match[2]) || 1,
    }));

    const lines = bodyText.replace(/\r\n/g, '\n').split('\n');
    const renderedLines = [];
    let tagCursor = 0;

    lines.forEach((line) => {
        const trimmedLine = line.trim();

        if (!trimmedLine) {
            renderedLines.push('<div class="chat-reply-line is-empty"></div>');
            return;
        }

        const inlineTags = Array.from(line.matchAll(new RegExp(CHAT_PRODUCT_TAG_RE.source, 'gi')));
        if (inlineTags.length) {
            const visible = stripChatProductTags(line);
            inlineTags.forEach((match, index) => {
                tagCursor += 1;
                const productName = match[1].trim();
                const quantity = Number(match[2]) || 1;
                const label =
                    inlineTags.length === 1 && visible
                        ? visible
                        : productName;
                renderedLines.push(renderChatProductButton(productName, quantity, label));
            });
            return;
        }

        const listMatch = trimmedLine.match(CHAT_LIST_LINE_RE);
        if (listMatch && tagCursor < allProductTags.length) {
            const tag = allProductTags[tagCursor];
            tagCursor += 1;
            renderedLines.push(renderChatProductButton(tag.name, tag.qty, listMatch[1].trim()));
            return;
        }

        if (isCatalogProductListLine(trimmedLine)) {
            const label = listMatch ? listMatch[1].trim() : trimmedLine.replace(/^\d+[\.\)]\s+/, '').trim();
            const productName = catalogLineProductName(label);
            renderedLines.push(renderChatProductButton(productName, 1, label));
            return;
        }

        renderedLines.push(`<div class="chat-reply-line">${escapeChatHtml(line)}</div>`);
    });

    if (tagCursor < allProductTags.length) {
        const fallbackButtons = allProductTags.slice(tagCursor).map((tag) =>
            renderChatProductButton(tag.name, tag.qty, tag.name)
        );
        renderedLines.push(`<div class="chat-inline-product-list">${fallbackButtons.join('')}</div>`);
    }

    if (pageMatches.length) {
        const pageButtons = pageMatches.map((match) => {
            const pageNumber = Number(match[1]) || 1;
            const label = escapeChatHtml(match[2].trim());
            return `<button type="button" class="chat-page-nav-button" onclick="sendQuickChatMessage('page ${pageNumber}', this); return false;">${label}</button>`;
        });

        renderedLines.push(`<div class="chat-page-nav">${pageButtons.join('')}</div>`);
    }

    if (!renderedLines.length) {
        renderedLines.push('<div class="chat-reply-line"></div>');
    }

    return `<div class="chat-popup-message-content rich-message-content">${renderedLines.join('')}</div>`;
}


function addProductToQuotation(productDescription, quantity = 1, sourceButton = null) {
    if (!productDescription || !productDescription.trim()) {
        return false;
    }

    const normalizeProductName = (value) => (value || '').trim().replace(/\s+/g, ' ').toLowerCase();
    const normalizedProduct = normalizeProductName(productDescription);
    const parsedQuantity = Number(quantity) || 1;

    const existingItems = getQuotationLineRows();
    for (const item of existingItems) {
        const productCell = item.querySelector('.item-product');
        const existingProduct = normalizeProductName(
            item.dataset.productDescription || readQuotationLineField(item, '.item-product')
        );

        if (existingProduct && existingProduct === normalizedProduct && productCell) {
            const currentQty = readQuotationLineNumber(item, '.item-qty');
            writeQuotationLineField(item, '.item-qty', currentQty + parsedQuantity);
            item.dataset.productDescription = productDescription.trim();
            calculateQuotationTotal();
            fetchProductPrice(productCell);
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            updateChatSuggestionButtonState(sourceButton, `Qty updated (+${parsedQuantity})`, 'is-updated');
            return true;
        }
    }
    
    // Find the last empty item or add a new one
    let lastItem = null;
    const items = getQuotationLineRows();
    
    for (let i = items.length - 1; i >= 0; i--) {
        if (!readQuotationLineField(items[i], '.item-product')) {
            lastItem = items[i];
            break;
        }
    }
    
    // If no empty item found, add a new one
    if (!lastItem) {
        addQuotationItem();
        const rows = getQuotationLineRows();
        lastItem = rows[rows.length - 1];
    }
    
    const productCell = lastItem.querySelector('.item-product');
    lastItem.dataset.productDescription = productDescription.trim();
    writeQuotationLineField(lastItem, '.item-product', productDescription);
    writeQuotationLineField(lastItem, '.item-qty', parsedQuantity);
    
    fetchProductPrice(productCell);
    updateChatSuggestionButtonState(sourceButton, 'Added to quotation', 'is-added');
    
    // Scroll to the form
    document.querySelector('.form-container').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    return true;
}

// Chat Session Management
let quotationChatId = null;

// Initialize chat session for quotation form
async function initializeQuotationChat() {
    try {
        const response = await fetch('/api/insert_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chatname: 'Quotation Assistant Chat' })
        });
        
        const data = await response.json();
        if (data.success && data.chat) {
            quotationChatId = data.chat.CHATID;
            console.log('Quotation chat session created:', quotationChatId);
        }
    } catch (error) {
        console.error('Failed to initialize quotation chat:', error);
    }
}

// Chat Popup Functions
function toggleChatPopup() {
    const chatPopup = document.getElementById('chat-popup');
    const textarea = document.getElementById('chat-popup-textarea');
    chatPopup.classList.toggle('hidden');
    
    // Initialize chat if not already initialized (lazy initialization)
    if (!quotationChatId && !chatPopup.classList.contains('hidden')) {
        initializeQuotationChat();
    }

    if (!chatPopup.classList.contains('hidden') && textarea) {
        window.setTimeout(() => {
            textarea.focus();
            const length = textarea.value.length;
            textarea.setSelectionRange(length, length);
        }, 0);
    }
}

function closeChatPopup() {
    const chatPopup = document.getElementById('chat-popup');
    chatPopup.classList.add('hidden');
}

function sendChatMessage(messageOverride = null) {
    const textarea = document.getElementById('chat-popup-textarea');
    const messagesContainer = document.getElementById('chat-popup-messages');
    const message = (messageOverride ?? textarea.value).trim();
    
    if (!message || !quotationChatId) return;
    
    // Add user message to chat
    const userMsgDiv = document.createElement('div');
    userMsgDiv.className = 'chat-message user-message';
    userMsgDiv.innerHTML = `<div class="chat-popup-message-content">${message}</div>`;
    messagesContainer.appendChild(userMsgDiv);
    
    // Clear input
    textarea.value = '';
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    // Send message to API
    fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message, chatid: quotationChatId })
    })
    .then(res => {
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return res.json();
    })
    .then(data => {
        if (!data) return;
        const reply = data.reply;

        // Add bot response to chat
        const botMsgDiv = document.createElement('div');
        botMsgDiv.className = 'chat-message bot-message';

        botMsgDiv.innerHTML = buildChatReplyHtml(reply);
        messagesContainer.appendChild(botMsgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    })
    .catch(error => {
        console.error('Error sending message:', error);
        const errorMsgDiv = document.createElement('div');
        errorMsgDiv.className = 'chat-message bot-message';
        errorMsgDiv.innerHTML = `<div class="chat-popup-message-content">Sorry, I encountered an error. Please try again.</div>`;
        messagesContainer.appendChild(errorMsgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    });
}

// Handle Enter key in chat textarea
document.addEventListener('DOMContentLoaded', function() {
    // Initialize quotation chat session
    // initializeQuotationChat(); // DISABLED: Chat functionality disabled for create quotation page
    
    const textarea = document.getElementById('chat-popup-textarea');
    if (textarea) {
        textarea.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }
    
    // Make chat popup draggable
    makeChatPopupDraggable();
    makeChatPopupResizable();
});

// Draggable functionality for chat popup
function makeChatPopupDraggable() {
    const chatPopup = document.getElementById('chat-popup');
    const chatHeader = document.querySelector('.chat-popup-header');
    
    if (!chatPopup || !chatHeader) return;
    
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let translateX = 0;
    let translateY = 0;
    
    chatHeader.addEventListener('mousedown', function(e) {
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        chatHeader.style.cursor = 'grabbing';
        chatPopup.style.transition = 'none';
    });
    
    document.addEventListener('mousemove', function(e) {
        if (!isDragging) return;
        
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;
        
        translateX += deltaX;
        translateY += deltaY;
        
        chatPopup.style.transform = `translate(${translateX}px, ${translateY}px)`;
        
        startX = e.clientX;
        startY = e.clientY;
    });
    
    document.addEventListener('mouseup', function() {
        isDragging = false;
        chatHeader.style.cursor = 'grab';
        chatPopup.style.transition = 'all 0.3s ease';
    });
    
    chatHeader.addEventListener('mouseenter', function() {
        if (!isDragging) {
            chatHeader.style.cursor = 'grab';
        }
    });
    
    chatHeader.addEventListener('mouseleave', function() {
        if (!isDragging) {
            chatHeader.style.cursor = 'default';
        }
    });
}

function makeChatPopupResizable() {
    const chatPopup = document.getElementById('chat-popup');
    const resizeHandles = document.querySelectorAll('.resize-handle');
    
    if (!chatPopup || !resizeHandles.length) return;
    
    let isResizing = false;
    let startX = 0;
    let startY = 0;
    let startWidth = 0;
    let startHeight = 0;
    let resizeEdge = null;
    
    resizeHandles.forEach(handle => {
        handle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            isResizing = true;
            startX = e.clientX;
            startY = e.clientY;
            startWidth = chatPopup.offsetWidth;
            startHeight = chatPopup.offsetHeight;
            resizeEdge = handle.getAttribute('data-edge');
            chatPopup.style.transition = 'none';
        });
    });
    
    document.addEventListener('mousemove', function(e) {
        if (!isResizing) return;
        
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;
        
        if (resizeEdge === 'right') {
            // Resize width only
            const newWidth = Math.max(300, startWidth + deltaX);
            chatPopup.style.width = newWidth + 'px';
        }
        
        if (resizeEdge === 'bottom') {
            // Resize height only
            const newHeight = Math.max(250, startHeight + deltaY);
            chatPopup.style.height = newHeight + 'px';
        }
    });
    
    document.addEventListener('mouseup', function() {
        isResizing = false;
        resizeEdge = null;
        chatPopup.style.transition = 'all 0.3s ease';
    });
}




