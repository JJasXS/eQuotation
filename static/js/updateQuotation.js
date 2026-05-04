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

// Add Quotation Item (same column layout as create quotation)
function addQuotationItem() {
    const container = document.getElementById('quotation-items-list');
    const today = new Date().toISOString().split('T')[0];
    const newItem = document.createElement('div');
    newItem.className = 'order-item';
    newItem.innerHTML = `
        <div class="item-row">
            <select class="item-source" onchange="onProductSourceChange(this)">
                <option value="catalog">From catalog</option>
                <option value="custom">Custom order</option>
            </select>
            <select class="item-product" onchange="fetchProductPrice(this)">
                <option value="">Select product...</option>
            </select>
            <input type="text" class="item-product-custom" placeholder="Custom product" style="display:none;" onchange="fetchProductPrice(this)">
            <input type="number" class="item-qty" placeholder="Qty" min="1" value="1" onchange="calculateQuotationTotal()">
            <input type="number" class="item-discount" placeholder="Discount (RM)" step="0.01" min="0" value="0" onchange="calculateQuotationTotal()">
            <input type="number" class="item-suggested-price" placeholder="Reference price" step="0.01" min="0" readonly>
            <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" onchange="calculateQuotationTotal()">
            <input type="date" class="item-delivery-date" value="${today}">
            <button type="button" class="btn-remove" onclick="removeQuotationItem(this)">✕</button>
        </div>
    `;
    container.appendChild(newItem);
    const select = newItem.querySelector('.item-product');
    populateProductSelect(select);
    onProductSourceChange(newItem.querySelector('.item-source'));
}

// Remove Quotation Item
function removeQuotationItem(button) {
    const items = document.querySelectorAll('#quotation-items-list .order-item');
    if (items.length > 1) {
        button.closest('.order-item').remove();
        calculateQuotationTotal();
    } else {
        alert('At least one item is required');
    }
}

// Calculate Quotation Total (fixed RM discount per line — same as create quotation)
function calculateQuotationTotal() {
    const items = document.querySelectorAll('#quotation-items-list .order-item');
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
    const row = selectElement.closest('.item-row');
    const catalogSelect = row.querySelector('.item-product');
    const customInput = row.querySelector('.item-product-custom');
    const suggestedPriceInput = row.querySelector('.item-suggested-price');
    const priceInput = row.querySelector('.item-price');

    if (selectElement.value === 'custom') {
        catalogSelect.style.display = 'none';
        customInput.style.display = 'inline-block';
        catalogSelect.value = '';
        if (suggestedPriceInput) suggestedPriceInput.value = '';
        priceInput.readOnly = false;
    } else {
        catalogSelect.style.display = 'inline-block';
        customInput.style.display = 'none';
        customInput.value = '';
        priceInput.readOnly = true;
    }
}

// Same pricing behaviour as create quotation (orderQuotation.js)
async function fetchProductPrice(input) {
    if (input.classList.contains('item-product-custom')) {
        return;
    }

    const productName = input.value.trim();
    if (!productName) return;

    const row = input.closest('.item-row');
    const orderItem = input.closest('.order-item');
    if (orderItem) {
        orderItem.dataset.productDescription = productName;
    }
    const suggestedPriceInput = row.querySelector('.item-price');
    const priceInput = row.querySelector('.item-suggested-price');

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

// Populate a product select element
function populateProductSelect(selectElement) {
    console.log('📝 Populating select with', availableProducts.length, 'products');
    const currentValue = selectElement.value;
    selectElement.innerHTML = '<option value="">Select product...</option>';
    
    availableProducts.forEach(item => {
        const option = document.createElement('option');
        option.value = item.DESCRIPTION || item.CODE;
        option.textContent = item.DESCRIPTION || item.CODE;
        selectElement.appendChild(option);
    });
    
    // Restore previous value if it exists
    if (currentValue) {
        selectElement.value = currentValue;
        console.log('✓ Select value set to:', currentValue);
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
        
        console.log('✅ Quotation loaded:', quotation);
        console.log('✅ Items loaded:', items);
        
        // Populate header
        document.getElementById('quotation-docno').textContent = quotation.DOCNO || dockey;
        
        // Populate form fields
        document.getElementById('quotation-customer').value = quotation.CODE || 'N/A';
        document.getElementById('quotation-company').value = quotation.COMPANYNAME || 'N/A';
        document.getElementById('quotation-phone').value = quotation.PHONE1 || 'N/A';
        document.getElementById('quotation-address1').value = quotation.ADDRESS1 || 'N/A';
        document.getElementById('quotation-address2').value = quotation.ADDRESS2 || 'N/A';
        const a3 = document.getElementById('quotation-address3');
        const a4 = document.getElementById('quotation-address4');
        if (a3) a3.value = quotation.ADDRESS3 || '';
        if (a4) a4.value = quotation.ADDRESS4 || '';
        document.getElementById('quotation-terms').value = quotation.CREDITTERM || 'N/A';
        
        console.log('📝 Form fields populated');
        
        // Format dates
        if (quotation.VALIDITY) {
            const validityDate = new Date(quotation.VALIDITY);
            document.getElementById('quotation-validity').value = validityDate.toISOString().split('T')[0];
        }
        
        if (quotation.DOCDATE) {
            const docDate = new Date(quotation.DOCDATE);
            document.getElementById('quotation-docdate').value = docDate.toISOString().split('T')[0];
        }
        
        // Populate items
        const container = document.getElementById('quotation-items-list');
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

                const newItemDiv = document.createElement('div');
                newItemDiv.className = 'order-item';
                newItemDiv.innerHTML = `
                    <div class="item-row">
                        <select class="item-source" onchange="onProductSourceChange(this)">
                            <option value="catalog">From catalog</option>
                            <option value="custom">Custom order</option>
                        </select>
                        <select class="item-product" onchange="fetchProductPrice(this)">
                            <option value="">Select product...</option>
                        </select>
                        <input type="text" class="item-product-custom" placeholder="Custom product" style="display:none;" value="" onchange="fetchProductPrice(this)">
                        <input type="number" class="item-qty" placeholder="Qty" min="1" value="${item.QTY || 1}" onchange="calculateQuotationTotal()">
                        <input type="number" class="item-discount" placeholder="Discount (RM)" step="0.01" min="0" value="${item.DISC || 0}" onchange="calculateQuotationTotal()">
                        <input type="number" class="item-suggested-price" placeholder="Reference price" step="0.01" min="0" readonly value="${Number(item.UDF_STDPRICE || 0).toFixed(2)}">
                        <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" value="${Number(item.UNITPRICE || 0).toFixed(2)}" onchange="calculateQuotationTotal()">
                        <input type="date" class="item-delivery-date" value="${delivery}">
                        <button type="button" class="btn-remove" onclick="removeQuotationItem(this)">✕</button>
                    </div>
                `;
                container.appendChild(newItemDiv);

                const sourceSel = newItemDiv.querySelector('.item-source');
                const select = newItemDiv.querySelector('.item-product');
                const customIn = newItemDiv.querySelector('.item-product-custom');

                sourceSel.value = sourceVal;
                populateProductSelect(select);

                if (!isCustom && item.DESCRIPTION) {
                    const d = String(item.DESCRIPTION);
                    const found = Array.from(select.options).some(o => o.value === d);
                    if (!found) {
                        const opt = document.createElement('option');
                        opt.value = d;
                        opt.textContent = d;
                        select.appendChild(opt);
                    }
                    select.value = d;
                }
                if (isCustom) {
                    customIn.value = item.DESCRIPTION || '';
                }

                onProductSourceChange(sourceSel);
                if (isCustom) {
                    newItemDiv.querySelector('.item-price').readOnly = false;
                }
            });
        }
        
        // Calculate total
        setTimeout(() => {
            console.log('💰 Calculating total');
            calculateQuotationTotal();
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
            
            const items = [];
            document.querySelectorAll('#quotation-items-list .order-item').forEach(item => {
                const source = item.querySelector('.item-source')?.value || 'catalog';
                let product = '';
                if (source === 'custom') {
                    product = item.querySelector('.item-product-custom')?.value.trim() || '';
                } else {
                    const productElement = item.querySelector('.item-product');
                    if (productElement) {
                        product = productElement.options[productElement.selectedIndex]?.value.trim() || '';
                    }
                }
                const qty = parseFloat(item.querySelector('.item-qty').value) || 0;
                const price = parseFloat(item.querySelector('.item-price').value) || 0;
                const discount = parseFloat(item.querySelector('.item-discount')?.value) || 0;
                const deliveryDate = item.querySelector('.item-delivery-date')?.value || null;

                if (product && qty > 0 && price >= 0) {
                    items.push({ product, source, qty, price, discount, deliveryDate });
                }
            });

            if (items.length === 0) {
                alert('Please add at least one valid item');
                return;
            }

            const updateData = {
                dockey: dockey,
                description: 'Quotation',
                validUntil: document.getElementById('quotation-validity').value,
                companyName: document.getElementById('quotation-company').value.trim(),
                address1: document.getElementById('quotation-address1').value.trim(),
                address2: document.getElementById('quotation-address2').value.trim(),
                address3: document.getElementById('quotation-address3')?.value.trim() || '',
                address4: document.getElementById('quotation-address4')?.value.trim() || '',
                phone1: document.getElementById('quotation-phone').value.trim(),
                items: items
            };
            
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
