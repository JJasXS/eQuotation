// Update Quotation Page JavaScript

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

let availableProducts = [];
let quotationData = null;

function formatDateInput(value) {
    if (!value) return '';
    const s = String(value).trim();
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? '' : d.toISOString().split('T')[0];
}

function setDetailText(id, value, fallback) {
    const el = document.getElementById(id);
    if (!el) return;
    const text = value != null && String(value).trim() !== '' ? String(value).trim() : (fallback ?? '');
    el.textContent = text || '-';
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
    return hit ? codeOf(hit) : '';
}

function resolveLineItemCode(row, source, product) {
    if (source === 'custom') {
        const stored = row.dataset.itemCode ? String(row.dataset.itemCode).trim() : '';
        return stored || 'CUSTOM';
    }
    const sel = row.querySelector('.item-product');
    if (sel && sel.tagName === 'SELECT') {
        const opt = sel.selectedOptions[0];
        const fromAttr = opt && opt.getAttribute('data-stock-code');
        if (fromAttr && String(fromAttr).trim()) {
            return String(fromAttr).trim();
        }
    }
    const stored = row.dataset.itemCode ? String(row.dataset.itemCode).trim() : '';
    if (stored && stored.toUpperCase() !== 'CUSTOM') {
        return stored;
    }
    return resolveCatalogItemCodeFromDescription(product) || stored;
}

function buildUpdateQuotationPayload(dockey, updateForm) {
    const items = [];
    getQuotationLineRows().forEach((row) => {
        const source = row.querySelector('.item-source')?.value || 'catalog';
        let product = '';
        if (source === 'custom') {
            product = row.querySelector('.item-product-custom')?.value.trim() || '';
        } else {
            const productElement = row.querySelector('.item-product');
            if (productElement) {
                product = productElement.options[productElement.selectedIndex]?.value.trim() || '';
            }
        }
        const qty = parseFloat(row.querySelector('.item-qty').value) || 0;
        const price = parseFloat(row.querySelector('.item-price').value) || 0;
        const discount = parseFloat(row.querySelector('.item-discount')?.value) || 0;
        const deliveryDate = row.querySelector('.item-delivery-date')?.value || null;
        const itemCode = resolveLineItemCode(row, source, product);
        const dtlkeyRaw = row.dataset.dtlkey;
        const dtlkey = dtlkeyRaw && String(dtlkeyRaw).trim() !== '' ? parseInt(dtlkeyRaw, 10) : 0;

        if (product && qty > 0 && price >= 0) {
            const line = { product, source, itemCode, qty, price, discount, deliveryDate };
            if (dtlkey > 0) {
                line.dtlkey = dtlkey;
            }
            items.push(line);
        }
    });

    const payload = {
        dockey: dockey,
        description: 'Quotation',
        validUntil: document.getElementById('quotation-validity').value,
        companyName: readQuotationCustomerField('quotation-company'),
        address1: readQuotationCustomerField('quotation-address1'),
        address2: readQuotationCustomerField('quotation-address2'),
        address3: readQuotationCustomerField('quotation-address3'),
        address4: readQuotationCustomerField('quotation-address4'),
        phone1: readQuotationCustomerField('quotation-phone'),
        terms: readQuotationCustomerField('quotation-terms'),
        items: items
    };

    if (updateForm) {
        const uc = updateForm.dataset.updatecount;
        if (uc != null && String(uc).trim() !== '') {
            payload.updatecount = parseInt(uc, 10);
        }
    }

    return payload;
}

function getQuotationLineRows() {
    return document.querySelectorAll('#update-quotation-line-items tr.quotation-line-row');
}

function buildQuotationLineRowHtml(opts = {}) {
    const today = opts.delivery || new Date().toISOString().split('T')[0];
    const qty = opts.qty ?? 1;
    const discount = opts.discount ?? 0;
    const suggested = opts.suggestedPrice != null ? Number(opts.suggestedPrice).toFixed(2) : '';
    const price = opts.price != null && opts.price !== '' ? Number(opts.price).toFixed(2) : '';
    const customValue = opts.customProduct ? String(opts.customProduct).replace(/"/g, '&quot;') : '';

    return `
        <td class="col-source">
            <select class="item-source" onchange="onProductSourceChange(this)">
                <option value="catalog">From catalog</option>
                <option value="custom">Custom order</option>
            </select>
        </td>
        <td class="col-product">
            <select class="item-product" onchange="fetchProductPrice(this)">
                <option value="">Select product...</option>
            </select>
            <input type="text" class="item-product-custom" placeholder="Custom product" style="display:none;" value="${customValue}" onchange="fetchProductPrice(this)">
        </td>
        <td class="col-numeric">
            <input type="number" class="item-qty" placeholder="Qty" min="1" value="${qty}" onchange="calculateQuotationTotal()">
        </td>
        <td class="col-numeric">
            <input type="number" class="item-discount" placeholder="Disc." step="0.01" min="0" value="${discount}" onchange="calculateQuotationTotal()">
        </td>
        <td class="col-numeric">
            <input type="number" class="item-suggested-price" placeholder="Ref." step="0.01" min="0" readonly value="${suggested}">
        </td>
        <td class="col-numeric">
            <input type="number" class="item-price" placeholder="Unit" step="0.01" min="0" value="${price}" title="Unit price (editable)" onchange="calculateQuotationTotal()">
        </td>
        <td class="col-delivery">
            <input type="date" class="item-delivery-date" value="${today}">
        </td>
        <td class="col-actions">
            <button type="button" class="btn-remove" onclick="removeQuotationItem(this)" aria-label="Remove line">✕</button>
        </td>
    `;
}

function createQuotationLineRow(opts = {}) {
    const row = document.createElement('tr');
    row.className = 'quotation-line-row';
    row.innerHTML = buildQuotationLineRowHtml(opts);
    return row;
}

function refreshQuotationMiniItemCodes() {
    const el = document.getElementById('quotation-mini-item-codes');
    if (!el) return;
    const codes = [];
    getQuotationLineRows().forEach((row) => {
        const source = row.querySelector('.item-source')?.value;
        const catalog = row.querySelector('.item-product')?.value?.trim();
        const custom = row.querySelector('.item-product-custom')?.value?.trim();
        const label = source === 'custom' ? custom : catalog;
        if (label) codes.push(label);
    });
    el.textContent = codes.length ? codes.join(' | ') : '';
}

function addQuotationItem() {
    const container = document.getElementById('update-quotation-line-items');
    const newItem = createQuotationLineRow();
    container.appendChild(newItem);
    populateProductSelect(newItem.querySelector('.item-product'));
    onProductSourceChange(newItem.querySelector('.item-source'));
    refreshQuotationMiniItemCodes();
}

// Remove Quotation Item
function removeQuotationItem(button) {
    const items = getQuotationLineRows();
    if (items.length > 1) {
        button.closest('tr.quotation-line-row').remove();
        calculateQuotationTotal();
        refreshQuotationMiniItemCodes();
    } else {
        alert('At least one item is required');
    }
}

// Calculate Quotation Total (fixed RM discount per line — same as create quotation)
function calculateQuotationTotal() {
    const items = getQuotationLineRows();
    let total = 0;

    items.forEach(item => {
        const qty = parseFloat(item.querySelector('.item-qty').value) || 0;
        const unitPrice = parseFloat(item.querySelector('.item-price')?.value) || 0;
        const discount = parseFloat(item.querySelector('.item-discount')?.value) || 0;
        const lineSubtotal = qty * unitPrice;
        const discountAmount = discount > 0 ? discount : 0;
        total += Math.max(0, lineSubtotal - discountAmount);
    });

    document.getElementById('quotation-total').textContent = `RM ${total.toFixed(2)}`;
}

function onProductSourceChange(selectElement) {
    const row = selectElement.closest('tr.quotation-line-row');
    if (!row) return;
    const catalogSelect = row.querySelector('.item-product');
    const customInput = row.querySelector('.item-product-custom');
    const suggestedPriceInput = row.querySelector('.item-suggested-price');
    const priceInput = row.querySelector('.item-price');

    if (selectElement.value === 'custom') {
        catalogSelect.style.display = 'none';
        customInput.style.display = 'block';
        catalogSelect.value = '';
        if (suggestedPriceInput) suggestedPriceInput.value = '';
    } else {
        catalogSelect.style.display = 'block';
        customInput.style.display = 'none';
        customInput.value = '';
    }
    if (priceInput) {
        priceInput.readOnly = false;
        priceInput.removeAttribute('readonly');
        priceInput.title = 'Unit price (editable on update)';
    }
}

// Same pricing behaviour as create quotation (orderQuotation.js)
async function fetchProductPrice(input) {
    if (input.classList.contains('item-product-custom')) {
        return;
    }

    const productName = input.value.trim();
    if (!productName) return;

    const row = input.closest('tr.quotation-line-row');
    if (!row) return;
    row.dataset.productDescription = productName;
    const suggestedPriceInput = row.querySelector('.item-suggested-price');
    const priceInput = row.querySelector('.item-price');

    try {
        const response = await fetch(`/api/get_product_price?description=${encodeURIComponent(productName)}`);
        const data = await response.json();

        if (data.success && data.price !== undefined && data.price !== null) {
            if (suggestedPriceInput) {
                if (data.suggestedPrice !== undefined && data.suggestedPrice !== null) {
                    suggestedPriceInput.value = Number(data.suggestedPrice).toFixed(2);
                } else {
                    suggestedPriceInput.value = '';
                }
                const stItemPrice = Number(data.stItemPrice);
                if (Number.isFinite(stItemPrice)) {
                    priceInput.value = stItemPrice.toFixed(2);
                } else {
                    priceInput.value = data.price.toFixed(2);
                }
            } else if (priceInput) {
                priceInput.value = data.price.toFixed(2);
            }
            calculateQuotationTotal();
        }
    } catch (error) {
        console.error('Failed to fetch product price:', error);
    }
}

// Load Products for Autocomplete
async function loadProducts() {
    try {
        console.log('🔄 Loading products...');
        const response = await fetch('/api/get_stock_items');
        const data = await response.json();
        
        console.log('📦 Products response:', data);
        
        if (data.success && data.items) {
            availableProducts = data.items;
            console.log('✅ Loaded', availableProducts.length, 'products');
        } else {
            console.warn('⚠️ No items in response');
        }
    } catch (error) {
        console.error('❌ Failed to load products:', error);
    }
}

function populateProductSelect(selectElement) {
    const currentValue = selectElement.value;
    selectElement.innerHTML = '<option value="">Select product...</option>';

    availableProducts.forEach((item) => {
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

    if (currentValue) {
        selectElement.value = currentValue;
    }
}

// Load Quotation Data
async function loadQuotationData(dockey) {
    try {
        console.log('🔄 Loading quotation data for dockey:', dockey);
        
        // Fetch quotation details
        const response = await fetch(`/api/admin/get_quotation_detail?dockey=${dockey}`);
        console.log('📡 API Response status:', response.status);
        
        const data = await response.json();
        console.log('📦 API Response data:', data);
        
        if (!data.success) {
            alert('Failed to load quotation: ' + (data.error || 'Unknown error'));
            window.location.href = '/admin/view-quotations';
            return;
        }
        
        const quotation = data.quotation;
        const items = data.items || [];
        quotationData = quotation;

        const updateForm = document.getElementById('update-quotation-form');
        if (updateForm) {
            if (quotation.UPDATECOUNT != null && quotation.UPDATECOUNT !== '') {
                updateForm.dataset.updatecount = String(quotation.UPDATECOUNT);
            }
            if (quotation.CODE) {
                updateForm.dataset.customerCode = String(quotation.CODE).trim();
            }
        }

        console.log('✅ Quotation loaded:', quotation);
        console.log('✅ Items loaded:', items);

        document.getElementById('quotation-docno').textContent = quotation.DOCNO || dockey;
        
        setDetailText('quotation-customer', quotation.CODE, 'N/A');
        setDetailText('quotation-company', quotation.COMPANYNAME, 'N/A');
        setDetailText('quotation-phone', quotation.PHONE1, 'N/A');
        setDetailText('quotation-address1', quotation.ADDRESS1, 'N/A');
        setDetailText('quotation-address2', quotation.ADDRESS2, 'N/A');
        setDetailText('quotation-address3', quotation.ADDRESS3, '');
        setDetailText('quotation-address4', quotation.ADDRESS4, '');
        setDetailText('quotation-terms', quotation.CREDITTERM, 'N/A');
        
        console.log('📝 Form fields populated');
        
        // Format dates
        if (quotation.VALIDITY) {
            const validityDate = new Date(quotation.VALIDITY);
            document.getElementById('quotation-validity').value = validityDate.toISOString().split('T')[0];
        }
        
        if (quotation.DOCDATE) {
            const docDate = formatDateInput(quotation.DOCDATE);
            setDetailText('quotation-docdate', docDate, '-');
        } else {
            setDetailText('quotation-docdate', '', '-');
        }
        
        // Populate items
        const container = document.getElementById('update-quotation-line-items');
        container.innerHTML = '';
        
        console.log('🛒 Loading', items.length, 'items');
        
        if (items.length === 0) {
            console.log('⚠️ No items, adding empty item');
            addQuotationItem();
        } else {
            const today = new Date().toISOString().split('T')[0];
            items.forEach((item, index) => {
                console.log(`📦 Item ${index}:`, item);

                const isCustom = String(item.ITEMCODE || '').trim().toUpperCase() === 'CUSTOM';
                const sourceVal = isCustom ? 'custom' : 'catalog';
                const delivery = formatDateInput(item.DELIVERYDATE) || today;

                const newItemDiv = createQuotationLineRow({
                    qty: item.QTY || 1,
                    discount: item.DISC || 0,
                    suggestedPrice: item.UDF_STDPRICE || 0,
                    price: item.UNITPRICE || 0,
                    delivery,
                    customProduct: isCustom ? (item.DESCRIPTION || '') : ''
                });
                container.appendChild(newItemDiv);

                if (item.DTLKEY != null && item.DTLKEY !== '') {
                    newItemDiv.dataset.dtlkey = String(item.DTLKEY);
                }
                if (item.ITEMCODE != null && String(item.ITEMCODE).trim() !== '') {
                    newItemDiv.dataset.itemCode = String(item.ITEMCODE).trim();
                }

                const sourceSel = newItemDiv.querySelector('.item-source');
                const select = newItemDiv.querySelector('.item-product');
                const customIn = newItemDiv.querySelector('.item-product-custom');

                sourceSel.value = sourceVal;
                populateProductSelect(select);

                if (!isCustom && item.DESCRIPTION) {
                    const d = String(item.DESCRIPTION);
                    const ic = item.ITEMCODE ? String(item.ITEMCODE).trim() : '';
                    const found = Array.from(select.options).some((o) => o.value === d);
                    if (!found) {
                        const opt = document.createElement('option');
                        opt.value = d;
                        opt.textContent = d;
                        if (ic) {
                            opt.setAttribute('data-stock-code', ic);
                        }
                        select.appendChild(opt);
                    }
                    select.value = d;
                }
                if (isCustom) {
                    customIn.value = item.DESCRIPTION || '';
                }

                onProductSourceChange(sourceSel);
            });
        }
        
        // Calculate total
        setTimeout(() => {
            console.log('Calculating total');
            calculateQuotationTotal();
            refreshQuotationMiniItemCodes();
        }, 200);
        
    } catch (error) {
        console.error('❌ Error loading quotation data:', error);
        alert('Failed to load quotation. Please try again.');
        window.location.href = '/admin/view-quotations';
    }
}



// Initialize page
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Page loading - DOM content loaded');
    
    const updateForm = document.getElementById('update-quotation-form');
    console.log('📋 Update form element:', updateForm);
    
    const dockey = updateForm?.dataset.dockey;
    console.log('🔑 dockey from dataset:', dockey);
    
    if (!dockey) {
        console.error('❌ No dockey found!');
        alert('No quotation specified');
        window.location.href = '/admin/view-quotations';
        return;
    }
    
    console.log('⏳ Loading products first...');
    // Load products first, then load quotation data
    await loadProducts();
    console.log('⏳ Loading quotation data...');
    await loadQuotationData(dockey);
    console.log('✅ Page initialization complete');
    
    // Setup form submission handler
    console.log('🔗 Setting up form submit handler');
    if (updateForm) {
        updateForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('📤 Form submitted');

            const updateData = buildUpdateQuotationPayload(dockey, updateForm);

            if (!updateData.items || updateData.items.length === 0) {
                alert('Please add at least one valid item');
                return;
            }

            console.log('📦 Updating quotation with data:', updateData);
            
            try {
                const response = await fetch('/api/admin/update_quotation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateData)
                });
                
                if (response.status === 401) {
                    alert('Your session has expired. Please log in again.');
                    window.location.href = '/login';
                    return;
                }
                
                const result = await response.json();
                console.log('✅ Update response:', result);
                
                if (result.success) {
                    alert('Quotation updated successfully!');
                    window.location.href = '/admin/view-quotations';
                } else {
                    alert('Failed to update quotation: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('❌ Error updating quotation:', error);
                alert('Failed to update quotation. Please try again.');
            }
        });
    } else {
        console.error('❌ Form not found!');
    }
});
