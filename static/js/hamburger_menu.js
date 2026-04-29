// Hamburger menu (shared: customer, supplier, admin)
var HAMBURGER_EXPANDED_KEY = 'hamburgerExpandedSubmenus';
var HAMBURGER_EXPANDED_KEY_LEGACY = 'adminHamburgerExpandedSubmenus';

function toggleHamburgerMenu() {
    const dropdown = document.getElementById('hamburger-dropdown');
    const overlay = document.getElementById('hamburger-overlay');
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
    if (overlay) {
        overlay.classList.toggle('active');
    }
}

function toggleSubmenu(event, submenuId) {
    event.preventDefault();
    event.stopPropagation();

    const submenu = document.getElementById(submenuId);
    const parentLink = event.currentTarget;

    if (submenu && parentLink) {
        submenu.classList.toggle('active');
        parentLink.classList.toggle('active');

        try {
            if (window.localStorage) {
                const raw = localStorage.getItem(HAMBURGER_EXPANDED_KEY);
                const current = raw ? JSON.parse(raw) : {};
                current[submenuId] = submenu.classList.contains('active');
                localStorage.setItem(HAMBURGER_EXPANDED_KEY, JSON.stringify(current));
            }
        } catch (e) {
            // ignore
        }
    }
}

function restoreHamburgerExpandedState() {
    try {
        if (!window.localStorage) {
            return;
        }
        let raw = localStorage.getItem(HAMBURGER_EXPANDED_KEY);
        if (!raw) {
            raw = localStorage.getItem(HAMBURGER_EXPANDED_KEY_LEGACY);
            if (raw) {
                localStorage.setItem(HAMBURGER_EXPANDED_KEY, raw);
            }
        }
        if (!raw) {
            return;
        }
        const current = JSON.parse(raw);
        if (!current || typeof current !== 'object') {
            return;
        }

        Object.entries(current).forEach(function (entry) {
            const submenuId = entry[0];
            const isActive = entry[1];
            const submenu = document.getElementById(submenuId);
            if (!submenu) {
                return;
            }
            submenu.classList.toggle('active', Boolean(isActive));
            const parentLink = document.querySelector('[onclick*="' + submenuId + '"]');
            if (parentLink) {
                parentLink.classList.toggle('active', Boolean(isActive));
            }
        });
    } catch (e) {
        // ignore
    }
}

function hideCreateMenuItems() {
    const createOrder = document.getElementById('menu-create-order');
    if (createOrder) {
        createOrder.style.display = 'none';
        createOrder.dataset.manuallyHidden = 'true';
    }
}

function handleMenuAction(action) {
    const dropdown = document.getElementById('hamburger-dropdown');
    const overlay = document.getElementById('hamburger-overlay');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
    if (overlay) {
        overlay.classList.remove('active');
    }

    switch (action) {
        case 'chat':
            window.location.href = '/chat';
            break;
        case 'createOrder':
            window.location.href = '/create-order';
            break;
        case 'createQuotation':
            window.location.href = '/create-quotation';
            break;
        case 'viewQuotation':
            window.location.href = '/view-quotation';
            break;
        case 'supplierBidding':
            window.location.href = '/supplier/bidding';
            break;
        case 'viewOrderStatus':
            window.location.href = '/user/approvals';
            break;
        case 'logout':
            window.location.href = '/logout';
            break;
        default:
            console.log('Unknown action:', action);
    }
}

function showApprovalsPage() {
    const chatArea = document.querySelector('.main-chat');
    const approvalsArea = document.getElementById('main-approvals');
    if (chatArea) {
        chatArea.style.display = 'none';
    }
    if (approvalsArea) {
        approvalsArea.style.display = 'flex';
    }
}

function switchApprovalTab(tabName) {
    // Update active tab button
    const tabs = document.querySelectorAll('.approval-tab');
    tabs.forEach((tab) => {
        tab.classList.remove('active');
    });
    event.target.classList.add('active');

    // Map tab names to status values
    const statusMap = {
        'pending': 'PENDING',
        'completed': 'COMPLETED',
        'cancelled': 'CANCELLED',
    };

    const status = statusMap[tabName.toLowerCase()];

    // Fetch orders by status
    const content = document.getElementById('approvals-content');
    content.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">Loading...</div>';

    fetch(`/php/getOrdersByStatus.php?status=${status}`)
        .then((res) => res.json())
        .then((data) => {
            if (data.success && data.data && data.data.length > 0) {
                let html = '<div style="padding: 16px;">';

                data.data.forEach((order) => {
                    // Set status badge color
                    let statusColor = '#4b6e9e'; // default blue
                    if (order.STATUS === 'PENDING') {
                        statusColor = '#f5b301'; // yellow
                    } else if (order.STATUS === 'COMPLETED') {
                        statusColor = '#17a2b8'; // cyan
                    } else if (order.STATUS === 'CANCELLED') {
                        statusColor = '#dc3545'; // red
                    }

                    html += `
                        <div style="background: #2d3440; padding: 12px; margin-bottom: 12px; border-radius: 8px; border-left: 3px solid #4b6e9e;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-weight: 600; color: #e4e9f1;">Order #${order.ORDERID}</span>
                                <span style="background: ${statusColor}; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${order.STATUS}</span>
                            </div>
                            <div style="color: #9ba7b6; font-size: 12px; margin-bottom: 8px;">
                                Chat: ${order.CHATID} | Date: ${new Date(order.CREATEDAT).toLocaleString()}
                            </div>
                            <div style="font-size: 12px; color: #9ba7b6;">
                                <strong>Items:</strong>
                    `;

                    if (order.items && order.items.length > 0) {
                        html += '<ul style="margin: 4px 0; padding-left: 20px;">';
                        order.items.forEach((item) => {
                            const itemTotal = (item.QTY * item.UNITPRICE - (item.DISCOUNT || 0)).toFixed(2);
                            html += `<li style="display: flex; align-items: center; justify-content: space-between;">
                                <span>${item.DESCRIPTION} x${item.QTY} @ RM${parseFloat(item.UNITPRICE).toFixed(2)} = RM${itemTotal}</span>
                                <button type="button" class="btn-remove-item" style="margin-left: 8px; color: #fff; background: #e74c3c; border: none; border-radius: 50%; width: 22px; height: 22px; cursor: pointer; font-size: 14px; line-height: 18px; display: flex; align-items: center; justify-content: center;" onclick="removeItemFromOrder('${item.DESCRIPTION}', ${item.QTY}, ${item.UNITPRICE})">&times;</button>
                            </li>`;
                            function removeItemFromOrder(description, qty, unitPrice) {
                                if (!confirm(`Remove item: ${description} x${qty} @ RM${parseFloat(unitPrice).toFixed(2)}?`)) return;
                                alert(`Item '${description}' removed (demo only). Implement backend logic here.`);
                            }
                        });
                        html += '</ul>';
                    } else {
                        html += '<span style="color: #666;">No items</span>';
                    }

                    html += `
                            </div>
                        </div>
                    `;
                });

                html += '</div>';
                content.innerHTML = html;
            } else {
                content.innerHTML = `
                    <div style="padding: 20px; text-align: center; color: #888;">
                        <h3>${tabName.charAt(0).toUpperCase() + tabName.slice(1)} approvals</h3>
                        <p>No ${tabName} orders to display</p>
                    </div>
                `;
            }
        })
        .catch((err) => {
            console.error('Error fetching approvals:', err);
            content.innerHTML = `
                <div style="padding: 20px; text-align: center; color: #ff6b6b;">
                    <p>Error loading ${tabName} approvals</p>
                </div>
            `;
        });
}

document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.getElementById('hamburger-overlay');
    if (overlay) {
        overlay.addEventListener('click', function () {
            const dropdown = document.getElementById('hamburger-dropdown');
            if (dropdown) {
                dropdown.classList.remove('active');
            }
            overlay.classList.remove('active');
        });
    }
    restoreHamburgerExpandedState();
});
