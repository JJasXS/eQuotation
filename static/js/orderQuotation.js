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

// Add Quotation Item
function addQuotationItem() {
    const container = document.getElementById('quotation-items-list');
    const newItem = document.createElement('div');
    newItem.className = 'order-item';
    newItem.innerHTML = `
        <div class="item-row">
            <select class="item-product" onchange="fetchProductPrice(this)">
                <option value="">Select product...</option>
            </select>
            <input type="number" class="item-qty" placeholder="Qty" min="1" value="1" onchange="calculateQuotationTotal()">
            <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" onchange="calculateQuotationTotal()">
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
        const price = parseFloat(item.querySelector('.item-price').value) || 0;
        total += qty * price;
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
    
    const priceInput = input.closest('.item-row').querySelector('.item-price');
    
    try {
        const response = await fetch(`/api/get_product_price?description=${encodeURIComponent(productName)}`);
        const data = await response.json();
        
        if (data.success && data.price !== undefined && data.price !== null) {
            priceInput.value = data.price.toFixed(2);
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
            
            if (product && qty > 0 && price >= 0) {
                items.push({ product, qty, price });
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
    quotationForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const items = [];
        document.querySelectorAll('#quotation-items-list .order-item').forEach(item => {
            const productElement = item.querySelector('.item-product');
            const product = productElement.tagName === 'SELECT' ? 
                productElement.options[productElement.selectedIndex]?.value.trim() : 
                productElement.value.trim();
            const qty = parseFloat(item.querySelector('.item-qty').value) || 0;
            const price = parseFloat(item.querySelector('.item-price').value) || 0;
            
            if (product && qty > 0 && price >= 0) {
                items.push({ product, qty, price });
            }
        });
        
        if (items.length === 0) {
            alert('Please add at least one valid item');
            return;
        }
        
        const dockey = quotationForm.dataset.dockey;
        const quotationData = {
            description: 'Quotation',
            validUntil: document.getElementById('quotation-validity').value,
            companyName: document.getElementById('quotation-company').value.trim(),
            address1: document.getElementById('quotation-address1').value.trim(),
            address2: document.getElementById('quotation-address2').value.trim(),
            phone1: document.getElementById('quotation-phone').value.trim(),
            items: items
        };
        
        // DEBUG: Log the data being sent
        console.log('Quotation Data being sent:', quotationData);
        
        // Include dockey if editing existing quotation
        if (dockey) {
            quotationData.dockey = dockey;
        }
        
        try {
            const response = await fetch('/api/create_quotation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(quotationData)
            });
            
            const result = await response.json();
            
            // DEBUG: Log the API response
            console.log('API Response:', result);
            
            if (result.success) {
                const displayDocNo = result.docno || result.quotationid || result.dockey;
                const message = dockey ? 
                    `Quotation ${displayDocNo} updated successfully!` : 
                    `Quotation ${displayDocNo} created successfully!`;
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
                            <input type="number" class="item-price" placeholder="Unit Price" step="0.01" min="0" value="${item.UNITPRICE || 0}" onchange="calculateQuotationTotal()">
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadProducts();
    
    // Check if editing a draft quotation
    const quotationForm = document.getElementById('quotation-form');
    const dockey = quotationForm ? quotationForm.dataset.dockey : null;
    
    if (dockey) {
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

// Chat Popup Functions
function toggleChatPopup() {
    const chatPopup = document.getElementById('chat-popup');
    chatPopup.classList.toggle('hidden');
}

function closeChatPopup() {
    const chatPopup = document.getElementById('chat-popup');
    chatPopup.classList.add('hidden');
}

function sendChatMessage() {
    const textarea = document.getElementById('chat-popup-textarea');
    const messagesContainer = document.getElementById('chat-popup-messages');
    const message = textarea.value.trim();
    
    if (!message) return;
    
    // Add user message to chat
    const userMsgDiv = document.createElement('div');
    userMsgDiv.className = 'chat-message user-message';
    userMsgDiv.innerHTML = `<div class="message-content">${message}</div>`;
    messagesContainer.appendChild(userMsgDiv);
    
    // Clear input
    textarea.value = '';
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    // Simulate bot response
    setTimeout(() => {
        const botMsgDiv = document.createElement('div');
        botMsgDiv.className = 'chat-message bot-message';
        const botResponse = getBotResponse(message);
        botMsgDiv.innerHTML = `<div class="message-content">${botResponse}</div>`;
        messagesContainer.appendChild(botMsgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }, 500);
}

function getBotResponse(message) {
    const lowerMessage = message.toLowerCase();
    
    if (lowerMessage.includes('help') || lowerMessage.includes('how')) {
        return 'I can help you with creating quotations! Fill in the form above and I can assist with any questions. ??';
    } else if (lowerMessage.includes('price') || lowerMessage.includes('cost')) {
        return 'You can search for products and their prices will be automatically filled in when you select them. ??';
    } else if (lowerMessage.includes('submit') || lowerMessage.includes('save')) {
        return 'Once you\'re done filling the form, click the "Submit Quotation" button to save your quotation. ?';
    } else if (lowerMessage.includes('product')) {
        return 'Use the product dropdown to select items. The system will fetch the price automatically! ??';
    } else if (lowerMessage.includes('date') || lowerMessage.includes('valid')) {
        return 'You can set the validity date (when the quotation expires) in the "Valid Until" field. ??';
    } else {
        return 'Thanks for asking! I\'m here to help with your quotation. Is there anything specific you\'d like to know? ??';
    }
}

// Handle Enter key in chat textarea
document.addEventListener('DOMContentLoaded', function() {
    const textarea = document.getElementById('chat-popup-textarea');
    if (textarea) {
        textarea.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }
});
