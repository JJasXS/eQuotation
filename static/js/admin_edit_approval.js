let orderData = null;
let itemsData = [];

document.addEventListener('DOMContentLoaded', function () {
    const orderId = window.editOrderId;
    if (!orderId) {
        showError('No order ID provided.');
        return;
    }
    loadOrderData(orderId);
});

function loadOrderData(orderId) {
    fetch(`/php/getOrderDetails.php?orderid=${orderId}`)
        .then(res => res.json())
        .then(data => {
            if (!data.success || !data.data) {
                throw new Error(data.error || 'Order not found');
            }
            orderData = data.data;
            itemsData = Array.isArray(orderData.items) ? orderData.items : [];
            renderEditForm();
            document.getElementById('loading-state').style.display = 'none';
            document.getElementById('edit-content').style.display = 'block';
        })
        .catch(err => {
            console.error('Failed to load order details:', err);
            showError(err.message || 'Failed to load order details');
        });
}

function renderEditForm() {
    document.getElementById('orderid').value = orderData.ORDERID;
    document.getElementById('chatid').value = orderData.CHATID;
    document.getElementById('createdat').value = new Date(orderData.CREATEDAT).toLocaleString();
    document.getElementById('status').value = orderData.STATUS;
    document.getElementById('owneremail').value = orderData.OWNEREMAIL || 'N/A';
    renderItems();
    updateTotals();
}

function renderItems() {
    const container = document.getElementById('items-container');
    if (!itemsData.length) {
        container.innerHTML = '<div style="color:#9ba7b6; padding: 8px 4px;">No items. Add one.</div>';
        return;
    }

    container.innerHTML = itemsData.map((item, index) => {
        const orderDetailId = Number(item.ORDERDTLID) || 0;
        const qty = Number(item.QTY) || 0;
        const unitPrice = Number(item.UNITPRICE) || 0;
        const discount = Number(item.DISCOUNT) || 0;
        const total = (qty * unitPrice) - discount;
        return `
            <div class="item-row">
                <input type="text" value="${item.DESCRIPTION || ''}" oninput="updateItem(${index}, 'DESCRIPTION', this.value)">
                <input type="number" min="0" value="${qty}" oninput="updateItem(${index}, 'QTY', this.value)">
                <input type="number" min="0" step="0.01" value="${unitPrice}" oninput="updateItem(${index}, 'UNITPRICE', this.value)">
                <input type="number" min="0" step="0.01" value="${discount}" oninput="updateItem(${index}, 'DISCOUNT', this.value)">
                <span class="item-total">RM${total.toFixed(2)}</span>
                ${orderDetailId > 0
                    ? '<button type="button" class="remove-btn" disabled title="Existing items cannot be deleted for audit purposes">Locked</button>'
                    : `<button type="button" class="remove-btn" onclick="removeItem(${index})">Remove</button>`}
            </div>
        `;
    }).join('');
}

function updateItem(index, key, value) {
    itemsData[index][key] = value;
    renderItems();
    updateTotals();
}

function addNewItem() {
    itemsData.push({
        ORDERDTLID: 0,
        ORDERID: orderData.ORDERID,
        DESCRIPTION: '',
        QTY: 1,
        UNITPRICE: 0,
        DISCOUNT: 0
    });
    renderItems();
    updateTotals();
}

function removeItem(index) {
    const orderDetailId = Number(itemsData[index]?.ORDERDTLID) || 0;
    if (orderDetailId > 0) {
        alert('Existing items cannot be deleted for audit purposes.');
        return;
    }
    itemsData.splice(index, 1);
    renderItems();
    updateTotals();
}

function updateTotals() {
    let subtotal = 0;
    let totalDiscount = 0;

    itemsData.forEach(item => {
        const qty = Number(item.QTY) || 0;
        const unitPrice = Number(item.UNITPRICE) || 0;
        const discount = Number(item.DISCOUNT) || 0;
        subtotal += qty * unitPrice;
        totalDiscount += discount;
    });

    const grandTotal = subtotal - totalDiscount;
    document.getElementById('totals-container').innerHTML = `
        <div class="total-row"><span>Subtotal</span><span>RM${subtotal.toFixed(2)}</span></div>
        <div class="total-row"><span>Discount</span><span>-RM${totalDiscount.toFixed(2)}</span></div>
        <div class="total-row grand"><span>Grand Total</span><span>RM${grandTotal.toFixed(2)}</span></div>
    `;
}

function saveChanges() {
    if (itemsData.length === 0) {
        alert('Please add at least one item.');
        return;
    }

    const payload = {
        orderid: orderData.ORDERID,
        status: document.getElementById('status').value,
        items: itemsData.map(item => ({
            orderdtlid: Number(item.ORDERDTLID) || 0,
            orderid: item.ORDERID || orderData.ORDERID,
            description: item.DESCRIPTION || '',
            qty: Number(item.QTY) || 0,
            unitprice: Number(item.UNITPRICE) || 0,
            discount: Number(item.DISCOUNT) || 0
        }))
    };

    fetch('/admin/api/update-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                throw new Error(data.error || 'Failed to save changes');
            }
            alert('Order updated successfully.');
            window.location.href = '/admin/pending-approvals';
        })
        .catch(err => {
            console.error('Save failed:', err);
            alert(`Failed to save changes: ${err.message}`);
        });
}

function cancelEdit() {
    window.location.href = '/admin/pending-approvals';
}

function showError(message) {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('edit-content').style.display = 'none';
    document.getElementById('error-state').style.display = 'flex';
    document.getElementById('error-message').textContent = message;
}
