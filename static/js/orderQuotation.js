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
    document.querySelectorAll('#quotation-items-list .order-item').forEach(item => {
        const productElement = item.querySelector('.item-product');
        const product = productElement.tagName === 'SELECT' ?
            productElement.options[productElement.selectedIndex]?.value.trim() :
            productElement.value.trim();
        const qty = parseFloat(item.querySelector('.item-qty').value) || 0;
        const price = parseFloat(item.querySelector('.item-price').value) || 0;
        const discount = parseFloat(item.querySelector('.item-discount')?.value) || 0;
        const deliveryDate = item.querySelector('.item-delivery-date')?.value || null;

        if (product && qty > 0 && price >= 0) {
            items.push({ product, qty, price, discount, deliveryDate });
        }
    });

    return {
        description: 'Quotation',
        validUntil: document.getElementById('quotation-validity').value,
        companyName: document.getElementById('quotation-company').value.trim(),
        address1: document.getElementById('quotation-address1').value.trim(),
        address2: document.getElementById('quotation-address2').value.trim(),
        phone1: document.getElementById('quotation-phone').value.trim(),
        items: items
    };
}

// Add Quotation Item
function addQuotationItem() {
    const container = document.getElementById('quotation-items-list');
    const today = new Date().toISOString().split('T')[0];
    const newItem = document.createElement('div');
    newItem.className = 'order-item';
    newItem.innerHTML = `
        <div class="item-row">
            <select class="item-product" onchange="fetchProductPrice(this)">
                <option value="">Select product...</option>
            </select>
            <input type="number" class="item-qty" placeholder="Qty" min="1" value="1" onchange="calculateQuotationTotal()">
            <input type="number" class="item-discount" placeholder="Discount" step="0.01" min="0" value="0" onchange="calculateQuotationTotal()">
            <input type="number" class="item-suggested-price" placeholder="Suggested Price" step="0.01" min="0" readonly>
            <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" onchange="calculateQuotationTotal()">
            <input type="date" class="item-delivery-date" value="${today}">
            <button type="button" class="btn-remove" onclick="removeQuotationItem(this)">✕</button>
        </div>
    `;
    container.appendChild(newItem);
    
    // Populate the new select with products
    const select = newItem.querySelector('.item-product');
    populateProductSelect(select);
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
        const container = document.getElementById('quotation-items-list');
        container.innerHTML = `
            <div class="order-item">
                <div class="item-row">
                    <select class="item-product" onchange="fetchProductPrice(this)">
                        <option value="">Select product...</option>
                    </select>
                    <input type="number" class="item-qty" placeholder="Qty" min="1" value="1" onchange="calculateQuotationTotal()">
                    <input type="number" class="item-discount" placeholder="Discount" step="0.01" min="0" value="0" onchange="calculateQuotationTotal()">
                    <input type="number" class="item-suggested-price" placeholder="Suggested Price" step="0.01" min="0" readonly>
                    <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" onchange="calculateQuotationTotal()">
                    <button type="button" class="btn-remove" onclick="removeQuotationItem(this)">✕</button>
                </div>
            </div>
        `;
        // Populate the select with products
        const select = container.querySelector('.item-product');
        populateProductSelect(select);
        calculateQuotationTotal();
    }
}

// Fetch product price when a product is selected
async function fetchProductPrice(input) {
    const productName = input.value.trim();
    if (!productName) return;
    
    const row = input.closest('.item-row');
    const orderItem = input.closest('.order-item');
    if (orderItem) {
        orderItem.dataset.productDescription = productName;
    }
    const suggestedPriceInput = row.querySelector('.item-price');
    const priceInput = input.closest('.item-row').querySelector('.item-suggested-price');
    
    try {
        const response = await fetch(`/api/get_product_price?description=${encodeURIComponent(productName)}`);
        const data = await response.json();
        
        if (data.success && data.price !== undefined && data.price !== null) {
            if (suggestedPriceInput) {
                if (data.suggestedPrice !== undefined && data.suggestedPrice !== null) {
                    suggestedPriceInput.value = Number(data.suggestedPrice).toFixed(2);
                } else {
                    suggestedPriceInput.value = '';
                    if (data.suggestedReason) {
                        console.log('Suggested price unavailable:', data.suggestedReason, '| source:', data.source, '| rule:', data.matchedRuleCode);
                    }
                }
                const stItemPrice = Number(data.stItemPrice);
                if (Number.isFinite(stItemPrice)) {
                    priceInput.value = stItemPrice.toFixed(2);
                } else {
                    priceInput.value = data.price.toFixed(2);
                }
            } else {
                priceInput.value = data.price.toFixed(2);
            }
            // Trigger total recalculation
            const isOrder = input.closest('#order-items-list') !== null;
            if (isOrder) {
                calculateOrderTotal();
            } else {
                calculateQuotationTotal();
            }
        }
    } catch (error) {
        console.error('Failed to fetch product price:', error);
    }
}

// Store products globally
let availableProducts = [];

// Load Products for Autocomplete
async function loadProducts() {
    try {
        const response = await fetch('/api/get_stock_items');
        const data = await response.json();
        
        if (data.success && data.items) {
            availableProducts = data.items;
            
            // Populate all existing select elements
            document.querySelectorAll('.item-product').forEach(select => {
                if (select.tagName === 'SELECT') {
                    populateProductSelect(select);
                }
            });
        }
    } catch (error) {
        console.error('Failed to load products:', error);
    }
}

// Populate a product select element
function populateProductSelect(selectElement) {
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
    }
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
                    const draftNo = result.docno || result.dockey;
                    alert(`Draft ${draftNo} saved successfully.`);
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
                
                // Redirect to view quotations page
                window.location.href = '/view-quotation';
            } else {
                alert('Failed to save quotation: ' + (result.error || 'Unknown error'));
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
        const data = await response.json();
        
        if (data.success && data.data) {
            // Populate company name
            const companyInput = document.getElementById('quotation-company');
            if (companyInput) {
                companyInput.value = data.data.COMPANYNAME || 'N/A';
            }
            
            // Populate address 1
            const address1Input = document.getElementById('quotation-address1');
            if (address1Input) {
                address1Input.value = data.data.ADDRESS1 || 'N/A';
            }
            
            // Populate address 2
            const address2Input = document.getElementById('quotation-address2');
            if (address2Input) {
                address2Input.value = data.data.ADDRESS2 || 'N/A';
            }
            
            // Populate phone 1
            const phoneInput = document.getElementById('quotation-phone');
            if (phoneInput) {
                phoneInput.value = data.data.PHONE1 || 'N/A';
            }
            
            // Populate credit terms
            const termsInput = document.getElementById('quotation-terms');
            if (termsInput) {
                termsInput.value = data.data.CREDITTERM || 'N/A';
            }
        } else {
            // Set default N/A values if data not found
            setDefaultCustomerInfo();
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        setDefaultCustomerInfo();
    }
}

// Helper function to set all customer fields to N/A
function setDefaultCustomerInfo() {
    const fields = ['quotation-company', 'quotation-address1', 'quotation-address2', 'quotation-phone', 'quotation-terms'];
    fields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.value = 'N/A';
        }
    });
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
            
            // Populate credit terms
            const termsInput = document.getElementById('quotation-terms');
            if (termsInput && quotation.TERMS) {
                termsInput.value = quotation.TERMS;
            }
            
            // Populate customer info fields
            const companyInput = document.getElementById('quotation-company');
            if (companyInput && quotation.COMPANYNAME) {
                companyInput.value = quotation.COMPANYNAME;
            }
            
            const address1Input = document.getElementById('quotation-address1');
            if (address1Input && quotation.ADDRESS1) {
                address1Input.value = quotation.ADDRESS1;
            }
            
            const address2Input = document.getElementById('quotation-address2');
            if (address2Input && quotation.ADDRESS2) {
                address2Input.value = quotation.ADDRESS2;
            }
            
            const phoneInput = document.getElementById('quotation-phone');
            if (phoneInput && quotation.PHONE1) {
                phoneInput.value = quotation.PHONE1;
            }
            
            // Populate items
            if (quotation.items && quotation.items.length > 0) {
                const container = document.getElementById('quotation-items-list');
                container.innerHTML = ''; // Clear default item
                
                quotation.items.forEach(item => {
                    const newItem = document.createElement('div');
                    newItem.className = 'order-item';
                    newItem.innerHTML = `
                        <div class="item-row">
                            <input type="text" class="item-product" placeholder="Product name..." list="product-list" value="${item.DESCRIPTION || ''}" onchange="fetchProductPrice(this)">
                            <input type="number" class="item-qty" placeholder="Qty" min="1" value="${item.QTY || 1}" onchange="calculateQuotationTotal()">
                            <input type="number" class="item-discount" placeholder="Discount" step="0.01" min="0" value="${item.DISC || 0}" onchange="calculateQuotationTotal()">
                            <input type="number" class="item-suggested-price" placeholder="Suggested Price" step="0.01" min="0" value="${item.UDF_STDPRICE || 0}" readonly>
                            <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" value="${item.UNITPRICE || 0}" onchange="calculateQuotationTotal()">
                            <input type="date" class="item-delivery-date" value="${item.DELIVERYDATE || new Date().toISOString().split('T')[0]}">
                            <button type="button" class="btn-remove" onclick="removeQuotationItem(this)">✕</button>
                        </div>
                    `;
                    container.appendChild(newItem);
                });
                
                calculateQuotationTotal();
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
    } catch (error) {
        console.error('Error loading draft quotation:', error);
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
        const fillField = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
        fillField('quotation-description', draft.DESCRIPTION);
        if (draft.VALIDITY) {
            fillField('quotation-validity', draft.VALIDITY.split(' ')[0]);
        }
        fillField('quotation-terms', draft.TERMS);
        fillField('quotation-company', draft.COMPANYNAME);
        fillField('quotation-address1', draft.ADDRESS1);
        fillField('quotation-address2', draft.ADDRESS2);
        fillField('quotation-phone', draft.PHONE1);

        if (draft.items && draft.items.length > 0) {
            const container = document.getElementById('quotation-items-list');
            container.innerHTML = '';
            draft.items.forEach(item => {
                const newItem = document.createElement('div');
                newItem.className = 'order-item';
                newItem.innerHTML = `
                    <div class="item-row">
                        <input type="text" class="item-product" placeholder="Product name..." list="product-list" value="${item.DESCRIPTION || ''}" onchange="fetchProductPrice(this)">
                        <input type="number" class="item-qty" placeholder="Qty" min="1" value="${item.QTY || 1}" onchange="calculateQuotationTotal()">
                        <input type="number" class="item-discount" placeholder="Discount" step="0.01" min="0" value="${item.DISC || 0}" onchange="calculateQuotationTotal()">
                        <input type="number" class="item-suggested-price" placeholder="Suggested Price" step="0.01" min="0" value="${item.UDF_STDPRICE || 0}" readonly>
                        <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" value="${item.UNITPRICE || 0}" onchange="calculateQuotationTotal()">
                        <input type="date" class="item-delivery-date" value="${item.DELIVERYDATE || new Date().toISOString().split('T')[0]}">
                        <button type="button" class="btn-remove" onclick="removeQuotationItem(this)">✕</button>
                    </div>
                `;
                container.appendChild(newItem);
            });
            calculateQuotationTotal();
        }

        const quotationForm = document.getElementById('quotation-form');
        if (quotationForm) quotationForm.dataset.draftDockey = draftDockey;

        const pageTitle = document.querySelector('.header-title');
        if (pageTitle) pageTitle.textContent = 'Edit Draft Quotation';
        const formTitle = document.querySelector('#quotation-form').previousElementSibling;
        if (formTitle && formTitle.tagName === 'H3') formTitle.textContent = `Edit Draft - ${draft.DOCNO || ''}`;
    } catch (error) {
        console.error('Error loading SL_QTDRAFT draft:', error);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadProducts();

    const quotationForm = document.getElementById('quotation-form');
    const urlParams = new URLSearchParams(window.location.search);
    const draftDockey = urlParams.get('draftDockey');
    const dockey = quotationForm ? quotationForm.dataset.dockey : null;

    if (draftDockey) {
        // Load from SL_QTDRAFT
        loadSlQtDraftForEdit(draftDockey);
    } else if (dockey) {
        // Load draft quotation data
        loadDraftQuotation(dockey);
    } else {
        // Load user info only for new quotations
        loadUserInfo();
        const quotationDescription = document.getElementById('quotation-description');
        if (quotationDescription) {
            quotationDescription.value = 'Quotation';
        }
    }
    
    // Add change listeners to calculate totals
    document.querySelectorAll('#order-items-list .item-qty, #order-items-list .item-price').forEach(input => {
        input.addEventListener('change', calculateOrderTotal);
    });
    
    document.querySelectorAll('#quotation-items-list .item-qty, #quotation-items-list .item-price').forEach(input => {
        input.addEventListener('change', calculateQuotationTotal);
    });
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
    const messagesContainer = document.getElementById('chat-popup-messages');
    if (!messagesContainer || !quotationChatId || !message) {
        return;
    }

    const targetBotMessage = sourceButton
        ? sourceButton.closest('.chat-message.bot-message')
        : null;

    if (sourceButton) {
        sourceButton.disabled = true;
    }

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
        const renderedHtml = buildChatReplyHtml(reply);

        if (targetBotMessage) {
            targetBotMessage.innerHTML = renderedHtml;
            targetBotMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            const botMsgDiv = document.createElement('div');
            botMsgDiv.className = 'chat-message bot-message';
            botMsgDiv.innerHTML = renderedHtml;
            messagesContainer.appendChild(botMsgDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    })
    .catch(error => {
        console.error('Error requesting catalog page:', error);
        if (targetBotMessage) {
            const existingContent = targetBotMessage.querySelector('.message-content');
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

function buildChatReplyHtml(reply) {
    const matches = Array.from(reply.matchAll(/\[PRODUCT:\s*([^\|]+)\s*\|\s*qty:\s*(\d+)\s*\]/gi));
    const pageMatches = Array.from(reply.matchAll(/\[PAGE:\s*(\d+)\s*\|\s*label:\s*([^\]]+)\]/gi));
    const cleanedReply = reply
        .replace(/\[PRODUCT:[^\]]+\]/gi, '')
        .replace(/\[PAGE:[^\]]+\]/gi, '')
        .replace(/\r\n/g, '\n')
        .trim();
    const lines = cleanedReply.length ? cleanedReply.split('\n') : [];
    const renderedLines = [];
    let matchIndex = 0;

    lines.forEach(line => {
        const trimmedLine = line.trim();

        if (!trimmedLine) {
            renderedLines.push('<div class="chat-reply-line is-empty"></div>');
            return;
        }

        const numberedLineMatch = trimmedLine.match(/^\d+\.\s+(.+)$/);
        if (numberedLineMatch && matchIndex < matches.length) {
            const productName = matches[matchIndex][1].trim();
            const quantity = Number(matches[matchIndex][2]) || 1;
            const escapedProductName = escapeInlineJsString(productName);
            const escapedLabel = escapeChatHtml(trimmedLine);
            matchIndex += 1;

            renderedLines.push(
                `<button type="button" class="chat-inline-product-action" onclick="addProductToQuotation('${escapedProductName}', ${quantity}, this); return false;">${escapedLabel}</button>`
            );
            return;
        }

        renderedLines.push(`<div class="chat-reply-line">${escapeChatHtml(line)}</div>`);
    });

    if (matchIndex < matches.length) {
        const fallbackButtons = matches.slice(matchIndex).map(match => {
            const productName = match[1].trim();
            const quantity = Number(match[2]) || 1;
            const escapedProductName = escapeInlineJsString(productName);
            const escapedLabel = escapeChatHtml(productName);
            return `<button type="button" class="chat-inline-product-action" onclick="addProductToQuotation('${escapedProductName}', ${quantity}, this); return false;">${escapedLabel}</button>`;
        });

        renderedLines.push(`<div class="chat-inline-product-list">${fallbackButtons.join('')}</div>`);
    }

    if (pageMatches.length) {
        const pageButtons = pageMatches.map(match => {
            const pageNumber = Number(match[1]) || 1;
            const label = escapeChatHtml(match[2].trim());
            return `<button type="button" class="chat-page-nav-button" onclick="sendQuickChatMessage('page ${pageNumber}', this); return false;">${label}</button>`;
        });

        renderedLines.push(`<div class="chat-page-nav">${pageButtons.join('')}</div>`);
    }

    if (!renderedLines.length) {
        renderedLines.push('<div class="chat-reply-line"></div>');
    }

    return `<div class="message-content rich-message-content">${renderedLines.join('')}</div>`;
}


function addProductToQuotation(productDescription, quantity = 1, sourceButton = null) {
    if (!productDescription || !productDescription.trim()) {
        return false;
    }

    const normalizeProductName = (value) => (value || '').trim().replace(/\s+/g, ' ').toLowerCase();
    const normalizedProduct = normalizeProductName(productDescription);
    const parsedQuantity = Number(quantity) || 1;

    const existingItems = document.querySelectorAll('#quotation-items-list .order-item');
    for (const item of existingItems) {
        const select = item.querySelector('.item-product');
        const qtyInput = item.querySelector('.item-qty');
        const existingProduct = normalizeProductName(
            item.dataset.productDescription || select?.value || select?.options?.[select.selectedIndex]?.text || ''
        );

        if (existingProduct && existingProduct === normalizedProduct && qtyInput) {
            const currentQty = Number(qtyInput.value) || 0;
            qtyInput.value = currentQty + parsedQuantity;
            item.dataset.productDescription = productDescription.trim();
            calculateQuotationTotal();
            fetchProductPrice(select);
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            updateChatSuggestionButtonState(sourceButton, `Qty updated (+${parsedQuantity})`, 'is-updated');
            return true;
        }
    }
    
    // Find the last empty item or add a new one
    let lastItem = null;
    const items = document.querySelectorAll('#quotation-items-list .order-item');
    
    for (let i = items.length - 1; i >= 0; i--) {
        const select = items[i].querySelector('.item-product');
        if (!select.value) {
            lastItem = items[i];
            break;
        }
    }
    
    // If no empty item found, add a new one
    if (!lastItem) {
        addQuotationItem();
        lastItem = document.querySelectorAll('#quotation-items-list .order-item')[
            document.querySelectorAll('#quotation-items-list .order-item').length - 1
        ];
    }
    
    // Fill in the product and quantity
    const select = lastItem.querySelector('.item-product');
    const qtyInput = lastItem.querySelector('.item-qty');
    
    lastItem.dataset.productDescription = productDescription.trim();
    select.value = productDescription;
    qtyInput.value = parsedQuantity;
    
    // Trigger price fetch
    fetchProductPrice(select);
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
    userMsgDiv.innerHTML = `<div class="message-content">${message}</div>`;
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
        errorMsgDiv.innerHTML = `<div class="message-content">Sorry, I encountered an error. Please try again.</div>`;
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




