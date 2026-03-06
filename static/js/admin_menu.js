// Admin Hamburger Menu Functions
function toggleAdminHamburgerMenu() {
    const dropdown = document.getElementById('admin-hamburger-dropdown');
    const overlay = document.getElementById('admin-hamburger-overlay');
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
    if (overlay) {
        overlay.classList.toggle('active');
    }
}

function handleAdminMenuAction(action) {
    const dropdown = document.getElementById('admin-hamburger-dropdown');
    const overlay = document.getElementById('admin-hamburger-overlay');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
    if (overlay) {
        overlay.classList.remove('active');
    }

    switch(action) {
        case 'pending-approvals':
            showPendingApprovals();
            break;
        case 'logout':
            window.location.href = '/logout';
            break;
        default:
            console.log('Unknown action:', action);
    }
}

function showWelcome() {
    const welcomeSection = document.getElementById('admin-welcome');
    const approvalsSection = document.getElementById('admin-approvals');
    
    if (welcomeSection) welcomeSection.style.display = 'flex';
    if (approvalsSection) approvalsSection.style.display = 'none';
}

function showPendingApprovals() {
    const welcomeSection = document.getElementById('admin-welcome');
    const approvalsSection = document.getElementById('admin-approvals');
    
    if (welcomeSection) welcomeSection.style.display = 'none';
    if (approvalsSection) approvalsSection.style.display = 'flex';
    
    // Load pending approvals
    loadApprovalsByStatus('PENDING');
}

let currentApprovalStatus = 'PENDING';
let ordersCache = {}; // Cache to store order data

function switchApprovalTab(status, event) {
    currentApprovalStatus = status;

    const tabs = document.querySelectorAll('.approval-tab');
    tabs.forEach(tab => tab.classList.remove('active'));
    if (event && event.target) {
        event.target.classList.add('active');
    }

    loadApprovalsByStatus(status);
}

function loadApprovalsByStatus(status) {
    const content = document.getElementById('approvals-content');
    if (!content) {
        return;
    }
    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';
    
    // Server-side handles email filtering automatically based on user type and session
    let url = `/php/getOrdersByStatus.php?status=${status}`;
    
    fetch(url)
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data && data.data.length > 0) {
                let html = '';
                
                // Sort orders: those with change requests come first if status is PENDING
                let orders = data.data;
                if (status === 'PENDING') {
                    orders = orders.sort((a, b) => {
                        if (a.HAS_CHANGE_REQUEST && !b.HAS_CHANGE_REQUEST) return -1;
                        if (!a.HAS_CHANGE_REQUEST && b.HAS_CHANGE_REQUEST) return 1;
                        return 0;
                    });
                }
                
                let lastHadChangeRequest = null;
                orders.forEach((order, index) => {
                    // Add separator when transitioning from with-requests to without-requests
                    if (status === 'PENDING' && lastHadChangeRequest === true && order.HAS_CHANGE_REQUEST === false) {
                        html += `
                            <div style="border-top: 3px solid #f5b301; margin: 20px 0; padding: 10px 0;">
                                <div style="text-align: center; color: #888; font-size: 12px;">Other Pending Orders</div>
                            </div>
                        `;
                    }
                    lastHadChangeRequest = order.HAS_CHANGE_REQUEST;
                    
                    // Set status badge color
                    let statusColor = '#f5b301'; // PENDING
                    let statusClass = 'status-pending';
                    if (order.STATUS === 'COMPLETED') {
                        statusColor = '#17a2b8';
                        statusClass = 'status-completed';
                    } else if (order.STATUS === 'CANCELLED') {
                        statusColor = '#dc3545';
                        statusClass = 'status-cancelled';
                    }

                    const showAcceptButton = order.STATUS !== 'COMPLETED';
                    const showCancelledButton = order.STATUS !== 'CANCELLED' && order.STATUS !== 'COMPLETED';
                    const showPrintButton = order.STATUS === 'COMPLETED';
                    const showRequestChangeButton = order.STATUS === 'CANCELLED';
                    
                    // Check if current user is admin
                    const isAdmin = window.currentUserType === 'admin';
                    
                    const acceptButtonHtml = (showAcceptButton && isAdmin)
                        ? `<button class="approval-btn approval-btn-accept" onclick="updateApprovalStatus(${order.ORDERID}, 'COMPLETED')">Accept</button>`
                        : '';
                    const cancelledButtonHtml = (showCancelledButton && isAdmin)
                        ? `<button class="approval-btn approval-btn-cancel" onclick="updateApprovalStatus(${order.ORDERID}, 'CANCELLED')">Cancelled</button>`
                        : '';
                    const editButtonHtml = (isAdmin && order.STATUS === 'PENDING')
                        ? `<button class="approval-btn approval-btn-edit" onclick="editApproval(${order.ORDERID})">Edit</button>`
                        : '';
                    // Print button available for all users on completed orders
                    const printButtonHtml = showPrintButton
                        ? `<button class="approval-btn approval-btn-print" onclick="printOrderProof(${order.ORDERID})">Print Receipt</button>`
                        : '';
                    // Request Change button for users on cancelled orders
                    const requestChangeButtonHtml = (showRequestChangeButton && !isAdmin)
                        ? `<button class="approval-btn approval-btn-accept" onclick="openRequestChangeModal(${order.ORDERID})">Request Change</button>`
                        : '';
                    
                    // Store order data in cache
                    ordersCache[order.ORDERID] = order;
                    
                    // Add exclamation mark for orders with change requests
                    const changeRequestIndicator = order.HAS_CHANGE_REQUEST ? ' <span style="color: #f50101; font-weight: bold; font-size: 18px;" title="Has change request history">!</span>' : '';
                    
                    html += `
                        <div class="order-card">
                            <div class="order-header">
                                <span class="order-id">Order #${order.ORDERID}${changeRequestIndicator}</span>
                                <span class="status-badge ${statusClass}" style="background: ${statusColor};">${order.STATUS}</span>
                            </div>
                            <div class="order-meta">
                                Chat: ${order.CHATID} | Date: ${new Date(order.CREATEDAT).toLocaleString()}
                                ${order.OWNEREMAIL ? `<br>Owner: ${order.OWNEREMAIL}` : ''}
                            </div>
                            <div class="approval-actions">
                                <button class="approval-btn approval-btn-view" onclick="viewOrderDetails(${order.ORDERID})">View</button>
                                ${editButtonHtml}
                                ${acceptButtonHtml}
                                ${cancelledButtonHtml}
                                ${requestChangeButtonHtml}
                                ${printButtonHtml}
                            </div>
                        </div>
                    `;
                });
                
                content.innerHTML = html;
            } else {
                content.innerHTML = `
                    <div style="padding: 20px; text-align: center; color: #888;">
                        <h3>No ${status} Orders</h3>
                        <p>There are no ${status.toLowerCase()} orders to display</p>
                    </div>
                `;
            }
        })
        .catch(err => {
            console.error('Error fetching pending approvals:', err);
            content.innerHTML = `
                <div style="padding: 20px; text-align: center; color: #ff6b6b;">
                    <p>Error loading ${status.toLowerCase()} approvals</p>
                    <p style="font-size: 12px; color: #888;">${err.message}</p>
                </div>
            `;
        });
}

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('approvals-content')) {
        loadApprovalsByStatus(currentApprovalStatus);
    }
});

function editApproval(orderId) {
    window.location.href = `/admin/pending-approvals/edit/${orderId}`;
}

function printOrderProof(orderId) {
    const receiptUrl = `/order/proof/${orderId}?autodownload=1`;
    window.location.href = receiptUrl;
}

function updateApprovalStatus(orderId, status) {
    fetch('/php/updateOrderStatus.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orderid: orderId, status: status })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            loadApprovalsByStatus(currentApprovalStatus);
        } else {
            alert(data.error || 'Failed to update order status');
        }
    })
    .catch(err => {
        console.error('Failed to update status:', err);
        alert('Failed to update order status');
    });
}

function viewOrderDetails(orderId) {
    const order = ordersCache[orderId];
    
    if (!order) {
        alert('Order details not found. Please try again.');
        return;
    }
    
    // Set modal content
    document.getElementById('modal-order-title').textContent = `Order #${orderId} - Details`;
    document.getElementById('modal-order-id').textContent = `#${orderId}`;
    document.getElementById('modal-chat-id').textContent = order.CHATID;
    document.getElementById('modal-owner-email').textContent = order.OWNEREMAIL || 'N/A';
    document.getElementById('modal-date').textContent = new Date(order.CREATEDAT).toLocaleString();
    document.getElementById('modal-status').textContent = order.STATUS;
    
    // Set status color
    let statusColor = '#f5b301';
    if (order.STATUS === 'COMPLETED') {
        statusColor = '#17a2b8';
    } else if (order.STATUS === 'CANCELLED') {
        statusColor = '#dc3545';
    }
    document.getElementById('modal-status').style.color = statusColor;
    
    // Set items
    let itemsHtml = '';
    if (order.items && order.items.length > 0) {
        itemsHtml += '<div class="modal-items-list">';
        order.items.forEach(item => {
            const itemTotal = (item.QTY * item.UNITPRICE - (item.DISCOUNT || 0)).toFixed(2);
            itemsHtml += `
                <div class="modal-item" style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                    <div style="flex: 1;">
                        <div class="item-main">
                            <span class="item-desc">${item.DESCRIPTION}</span>
                            <span class="item-price">RM${itemTotal}</span>
                        </div>
                        <div class="item-detail">
                            Qty: ${item.QTY} x RM${parseFloat(item.UNITPRICE).toFixed(2)}
                            ${item.DISCOUNT ? `<span class="item-discount"> - Discount: RM${item.DISCOUNT}</span>` : ''}
                        </div>
                    </div>
                    <button type="button" class="btn-remove-item" style="color: #fff; background: #e74c3c; border: none; border-radius: 50%; width: 22px; height: 22px; cursor: pointer; font-size: 14px; line-height: 18px; display: flex; align-items: center; justify-content: center;" onclick="removeModalOrderItem('${item.DESCRIPTION}', ${item.QTY}, ${item.UNITPRICE})">&times;</button>
                </div>
            `;
        // Remove item from modal order (to be implemented with actual logic)
        function removeModalOrderItem(description, qty, unitPrice) {
            if (!confirm(`Remove item: ${description} x${qty} @ RM${parseFloat(unitPrice).toFixed(2)}?`)) return;
            // TODO: Implement actual removal logic (e.g., update order.items, send request to backend, refresh UI)
            alert(`Item '${description}' removed (demo only). Implement backend logic here.`);
        }
        });
        itemsHtml += '</div>';
    } else {
        itemsHtml = '<p style="color: #666;">No items in this order</p>';
    }
    document.getElementById('modal-items-container').innerHTML = itemsHtml;
    
    // Load and display remarks if any
    fetch(`/php/getOrderRemarks.php?orderid=${orderId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data && data.data.length > 0) {
                let remarksHtml = '<div style="margin-top: 8px;">';
                data.data.forEach(remark => {
                    const remarkDate = new Date(remark.CREATEDAT).toLocaleString();
                    const remarkType = remark.REMARKTYPE || 'NOTE';
                    const typeColor = remarkType === 'CHANGE_REQUEST' ? '#f5b301' : '#4b6e9e';
                    
                    remarksHtml += `
                        <div style="background: #2d3440; padding: 12px; margin-bottom: 8px; border-radius: 6px; border-left: 3px solid ${typeColor};">
                            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 4px;">
                                <span style="font-size: 12px; color: ${typeColor}; font-weight: 600;">${remarkType.replace('_', ' ')}</span>
                                <span style="font-size: 11px; color: #666;">${remarkDate}</span>
                            </div>
                            <div style="color: #e4e9f1; margin-bottom: 4px;">${remark.REMARK}</div>
                            ${remark.REQUESTEDBY ? `<div style="font-size: 11px; color: #9ba7b6;">By: ${remark.REQUESTEDBY}</div>` : ''}
                        </div>
                    `;
                });
                remarksHtml += '</div>';
                document.getElementById('modal-remarks-container').innerHTML = remarksHtml;
                document.getElementById('modal-remarks-section').style.display = 'block';
            } else {
                document.getElementById('modal-remarks-section').style.display = 'none';
            }
        })
        .catch(err => {
            console.error('Error loading remarks:', err);
            document.getElementById('modal-remarks-section').style.display = 'none';
        });
    
    // Show modal
    document.getElementById('details-modal').style.display = 'flex';
}

function closeOrderDetails() {
    document.getElementById('details-modal').style.display = 'none';
}

// Close modal when clicking outside of it
document.addEventListener('click', function(event) {
    const modal = document.getElementById('details-modal');
    if (modal && event.target === modal) {
        closeOrderDetails();
    }
    const changeModal = document.getElementById('request-change-modal');
    if (changeModal && event.target === changeModal) {
        closeRequestChangeModal();
    }
});

// Request Change Functions
let currentRequestChangeOrderId = null;

function openRequestChangeModal(orderId) {
    currentRequestChangeOrderId = orderId;
    document.getElementById('change-request-remark').value = '';
    document.getElementById('request-change-modal').style.display = 'flex';
}

function closeRequestChangeModal() {
    currentRequestChangeOrderId = null;
    document.getElementById('request-change-modal').style.display = 'none';
}

function submitRequestChange() {
    const remark = document.getElementById('change-request-remark').value.trim();
    
    if (!remark) {
        alert('Please enter a reason for the change request.');
        return;
    }
    
    if (!currentRequestChangeOrderId) {
        alert('No order selected.');
        return;
    }
    
    const userEmail = window.currentUserEmail || 'Unknown';
    
    fetch('/php/requestOrderChange.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            orderid: currentRequestChangeOrderId,
            remark: remark,
            requestedby: userEmail
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert('Change request submitted successfully! The order has been sent back to admin for review.');
            closeRequestChangeModal();
            // Reload the current tab to show updated status
            loadApprovalsByStatus(currentApprovalStatus);
        } else {
            alert('Failed to submit change request: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error('Error submitting change request:', err);
        alert('Failed to submit change request. Please try again.');
    });
}

