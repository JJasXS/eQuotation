// Authentication check - Redirect to login if unauthorized
async function authenticatedFetch(url, options = {}) {
    const res = await fetch(url, options);
    
    // Check if unauthorized
    if (res.status === 401) {
        console.warn('Unauthorized - redirecting to login');
        window.location.href = '/login';
        return null;
    }
    
    return res;
}

let selectedChatId = null;
let currentOrderId = null;
const chatActionClickedLock = {};
const chatBackendOrderLock = {};

function updateCreateActionsVisibilityForSelectedChat() {
    const quickCreateOrder = document.getElementById('quick-create-order');
    const quickRequestQuotation = document.getElementById('quick-request-quotation');
    const menuCreateOrder = document.getElementById('menu-create-order');
    const menuCreateQuotation = document.getElementById('menu-create-quotation');

    const chatKey = String(selectedChatId || '');
    const isLocked = !!(chatKey && (chatActionClickedLock[chatKey] || chatBackendOrderLock[chatKey]));

    const displayValue = isLocked ? 'none' : '';

    // Only hide/show quick action buttons in chat interface
    // Keep hamburger menu items always visible
    if (quickCreateOrder) quickCreateOrder.style.display = displayValue;
    if (quickRequestQuotation) quickRequestQuotation.style.display = 'none'; // Always hidden
    
    // Hamburger menu items should always be visible (except Request Quotation which is hidden)
    if (menuCreateOrder) menuCreateOrder.style.display = '';
    if (menuCreateQuotation) menuCreateQuotation.style.display = ''; // Always hidden
}

function showChatArea() {
    const chatArea = document.querySelector('.main-chat');
    const approvalsArea = document.getElementById('main-approvals');
    
    if (chatArea) chatArea.style.display = 'flex';
    if (approvalsArea) approvalsArea.style.display = 'none';
}

function formatTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
}

function selectChat(chat) {
    selectedChatId = chat.CHATID;
    currentOrderId = null; // Reset order ID when switching chats
    
    // Show chat area when selecting a chat
    showChatArea();
    
    // Update header
    document.querySelector('.header-title').textContent = chat.CHATNAME;

    // Apply per-chat create action visibility immediately
    updateCreateActionsVisibilityForSelectedChat();
    
    // Check for active order
    checkForActiveOrder();
    
    // Check for draft order and update menu availability
    checkDraftOrderAndUpdateMenu();

    const userInput = document.getElementById('user-input');
    if (userInput) {
        userInput.focus();
    }
    
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = '<div style="color:#888; text-align:center; margin-top:20px;">Loading chat details...</div>';
    fetch(`/get_chat_details?chatid=${chat.CHATID}`)
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return; // Redirected to login
            chatBox.innerHTML = '';
            if (data.success && data.details && data.details.length > 0) {
                data.details.forEach(msg => {
                    const msgDiv = document.createElement('div');
                    const sender = msg.SENDER.toLowerCase();
                    msgDiv.className = 'message ' + sender;
                    
                    const msgContent = document.createElement('div');
                    msgContent.className = 'message-content';
                    
                    const bubble = document.createElement('div');
                    bubble.className = 'bubble';
                    bubble.innerHTML = (msg.MESSAGETEXT || '').replace(/\n/g, '<br>');
                    
                    const time = document.createElement('div');
                    time.className = 'message-time';
                    time.textContent = formatTime(msg.SENTAT);
                    
                    msgContent.appendChild(bubble);
                    msgContent.appendChild(time);
                    msgDiv.appendChild(msgContent);
                    chatBox.appendChild(msgDiv);
                });
                chatBox.scrollTop = chatBox.scrollHeight;
            } else {
                chatBox.innerHTML = '<div style="color:#888; text-align:center; margin-top:20px;">No messages yet. Start chatting!</div>';
            }
        })
        .catch((err) => {
            console.error(err);
            chatBox.innerHTML = '<div style="color:#888; text-align:center; margin-top:20px;">Failed to load chat details.</div>';
        });
}

function checkDraftOrderAndUpdateMenu() {
    if (!selectedChatId) {
        return;
    }
    
    fetch(`/api/check_draft_order?chatid=${selectedChatId}`)
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return;

            const chatKey = String(selectedChatId);
            if (data.success && data.hasDraft) {
                chatBackendOrderLock[chatKey] = true;
            } else if (data.success) {
                chatBackendOrderLock[chatKey] = false;
            }

            updateCreateActionsVisibilityForSelectedChat();
        })
        .catch(err => {
            console.error('Error checking draft order:', err);
        });
}

function checkUserDraftOrdersOnLoad() {
    fetch('/api/check_user_has_draft')
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return;

            if (data.success && data.hasDraft) {
                updateCreateActionsVisibilityForSelectedChat();
            }
        })
        .catch(err => {
            console.error('Error checking user draft orders:', err);
        });
}

function checkForActiveOrder() {
    if (!selectedChatId) {
        updateOrderBubble(null);
        return;
    }
    
    fetch(`/api/get_active_order?chatid=${selectedChatId}`)
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return;
            if (data.success && data.orderid) {
                currentOrderId = data.orderid;
                chatBackendOrderLock[String(selectedChatId)] = true;
                updateOrderBubble(data.orderid);
            } else {
                chatBackendOrderLock[String(selectedChatId)] = false;
                updateOrderBubble(null);
            }
            updateCreateActionsVisibilityForSelectedChat();
        })
        .catch(err => {
            console.error('Error checking for active order:', err);
            chatBackendOrderLock[String(selectedChatId)] = false;
            updateCreateActionsVisibilityForSelectedChat();
            updateOrderBubble(null);
        });
}

function updateOrderBubble(orderid) {
    const bubble = document.getElementById('order-bubble');
    const bubbleText = document.getElementById('order-bubble-text');
    
    if (orderid) {
        bubble.style.display = 'flex';
        bubbleText.textContent = `#${orderid}`;
        bubble.style.background = '#f5b301';
        bubble.style.color = '#1e2228';
    } else {
        bubble.style.display = 'none';
    }
}

function viewCurrentOrder() {
    if (!currentOrderId) {
        alert('Order not created yet');
        return;
    }
    
    // Fetch order details
    fetch(`/php/getOrderDetails.php?orderid=${currentOrderId}`)
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return;
            
            console.log('Order data received:', data);
            
            if (data.success && data.data) {
                console.log('Order items:', data.data.items);
                displayOrderModal(data.data);
            } else {
                alert('Order not found');
            }
        })
        .catch(err => {
            console.error('Error fetching order:', err);
            alert('Failed to fetch order details');
        });
}

function displayOrderModal(order) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('order-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'order-modal';
        modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000;';
        modal.onclick = function(e) {
            if (e.target === this) {
                this.style.display = 'none';
            }
        };
        document.body.appendChild(modal);
    }
    
    let content = `
        <div style="background: #2d3440; border-radius: 8px; padding: 24px; max-width: 600px; max-height: 80vh; overflow-y: auto; color: #e4e9f1;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px;">
                <h2 style="margin: 0; color: #f5b301;">Order #${order.ORDERID}</h2>
                <button onclick="document.getElementById('order-modal').style.display='none'" style="background: none; border: none; color: #9ba7b6; font-size: 24px; cursor: pointer;">&times;</button>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #3a424e;">
                <div>
                    <div style="font-size: 12px; color: #9ba7b6; margin-bottom: 4px;">Chat ID</div>
                    <div style="font-size: 14px;">${order.CHATID}</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #9ba7b6; margin-bottom: 4px;">Status</div>
                    <div style="font-size: 14px; color: #f5b301; font-weight: bold;">${order.STATUS}</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #9ba7b6; margin-bottom: 4px;">Owner</div>
                    <div style="font-size: 14px;">${order.OWNEREMAIL || 'N/A'}</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #9ba7b6; margin-bottom: 4px;">Created</div>
                    <div style="font-size: 14px;">${new Date(order.CREATEDAT).toLocaleString()}</div>
                </div>
            </div>
            
            <div style="margin-bottom: 20px;">
                <h3 style="margin: 0 0 12px 0; font-size: 14px; color: #9ba7b6;">ORDER ITEMS</h3>
                <div style="display: flex; flex-direction: column; gap: 8px;">
    `;
    
    if (order.items && order.items.length > 0) {
        order.items.forEach(item => {
            const total = (item.QTY * item.UNITPRICE - (item.DISCOUNT || 0)).toFixed(2);
            content += `
                <div style="background: #3a424e; padding: 12px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                    <div>
                        <div style=\"font-weight: bold;\">${item.DESCRIPTION}</div>
                        <div style=\"font-size: 12px; color: #9ba7b6; margin-top: 4px;\">Qty: ${item.QTY} × RM${parseFloat(item.UNITPRICE).toFixed(2)}</div>
                        ${item.DISCOUNT ? `<div style=\\\"font-size: 12px; color: #9ba7b6;\\\">Discount: -RM${item.DISCOUNT}</div>` : ''}
                    </div>
                    <div style=\"display: flex; align-items: center; gap: 8px;\">
                        <span style=\"text-align: right; font-weight: bold; color: #f5b301;\">RM${total}</span>
                        <button type=\"button\" class=\"btn-remove-item minimalist-x\" onclick=\"removeChatOrderItem(${item.ORDER_DTLID}, this)\">&times;</button>
                    </div>
                </div>
            `;
        // Minimalist X button style for chat area
        if (!document.getElementById('minimalist-x-style')) {
            const minimalistXStyle = document.createElement('style');
            minimalistXStyle.id = 'minimalist-x-style';
            minimalistXStyle.innerHTML = `
        .minimalist-x {
            background: none !important;
            border: none !important;
            color: #ffffff !important;
            font-size: 18px !important;
            width: 24px !important;
            height: 24px !important;
            border-radius: 50% !important;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            transition: background 0.2s, color 0.2s;
        }
        .minimalist-x:hover {
            background: #ececec !important;
            color: #e74c3c !important;
        }
        `;
            document.head.appendChild(minimalistXStyle);
        }
        // Remove item from chat order and backend
        async function removeChatOrderItem(orderdtlid, btn) {
            if (!confirm('Remove this item from the order?')) return;
            try {
                const res = await fetch('/php/deleteOrderDetail.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ orderdtlid })
                });
                const data = await res.json();
                if (data.success) {
                    // Remove the item visually from the modal
                    const itemDiv = btn.closest('div[style*="background: #3a424e"]');
                    if (itemDiv) itemDiv.remove();
                    // Optionally, show a toast or refresh the order modal
                } else {
                    alert(data.error || 'Failed to remove item.');
                }
            } catch (err) {
                alert('Failed to remove item.');
            }
        }
        });
    } else {
        content += '<div style="color: #9ba7b6;">No items in this order</div>';
    }
    
    content += `
                </div>
            </div>
            
            <div style="text-align: right; padding-top: 16px; border-top: 1px solid #3a424e;">
                <button onclick="document.getElementById('order-modal').style.display='none'" style="padding: 8px 16px; border-radius: 6px; border: 1px solid #3a424e; background: #2d3440; color: #e4e9f1; cursor: pointer;">
                    Close
                </button>
            </div>
        </div>
    `;
    
    modal.innerHTML = content;
    modal.style.display = 'flex';
}

function appendMessage(sender, text) {
    const chatBox = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message ' + sender.toLowerCase();
    
    const msgContent = document.createElement('div');
    msgContent.className = 'message-content';
    
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.innerHTML = text.replace(/\n/g, '<br>');
    
    const time = document.createElement('div');
    time.className = 'message-time';
    const now = new Date();
    time.textContent = formatTime(now.toISOString());
    
    msgContent.appendChild(bubble);
    msgContent.appendChild(time);
    msgDiv.appendChild(msgContent);
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function quickAction(action) {
    if (!selectedChatId) {
        alert('Please select a chat first.');
        return;
    }

    if (action === 'Create Order') {
        chatActionClickedLock[String(selectedChatId)] = true;
        updateCreateActionsVisibilityForSelectedChat();
        
        const input = document.getElementById('user-input');
        input.value = action;
        sendMessage();
    } else if (action === 'Request Quotation') {
        // Create draft quotation first, then navigate to form
        chatActionClickedLock[String(selectedChatId)] = true;
        updateCreateActionsVisibilityForSelectedChat();
        
        createDraftQuotation();
    } else {
        const input = document.getElementById('user-input');
        input.value = action;
        sendMessage();
    }
}

async function createDraftQuotation() {
    try {
        // Get customer code from session (should be available globally)
        const response = await fetch('/api/get_user_info');
        const userData = await response.json();
        
        if (!userData.success || !userData.data || !userData.data.CODE) {
            alert('Failed to get customer information');
            return;
        }
        
        const customerCode = userData.data.CODE;
        
        // Create draft quotation
        const createResponse = await fetch('/php/insertDraftQuotation.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                customerCode: customerCode,
                chatId: selectedChatId
            })
        });
        
        const createData = await createResponse.json();
        
        if (createData.success) {
            // Navigate to quotation form with dockey
            window.location.href = `/create-quotation?dockey=${createData.dockey}`;
        } else {
            alert('Failed to create draft quotation: ' + (createData.error || 'Unknown error'));
            chatActionClickedLock[String(selectedChatId)] = false;
            updateCreateActionsVisibilityForSelectedChat();
        }
    } catch (error) {
        console.error('Error creating draft quotation:', error);
        alert('Failed to create draft quotation');
        chatActionClickedLock[String(selectedChatId)] = false;
        updateCreateActionsVisibilityForSelectedChat();
    }
}

function sendMessage() {
    const input = document.getElementById('user-input');
    const text = input.value.trim();
    if (!text || !selectedChatId) {
        alert('Please select a chat first.');
        return;
    }
    
    appendMessage('user', text);
    input.value = '';
    input.style.height = 'auto'; // Reset textarea height after sending
    
    fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, chatid: selectedChatId })
    })
    .then(res => {
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return res.json();
    })
    .then(data => {
        if (!data) return; // Redirected to login
        appendMessage('system', data.reply);
        loadChatList();
        // Check for active order after chat response
        setTimeout(checkForActiveOrder, 500);
    })
    .catch((err) => {
        console.error(err);
        appendMessage('system', 'Error: Could not reach server.');
        // Still check for active order even if there's an error
        setTimeout(checkForActiveOrder, 500);
    });
}

function createNewChat() {
    const input = document.getElementById('new-chat-name');
    const chatName = input.value.trim();

    if (!chatName) {
        alert('Please enter a chat name.');
        return;
    }

    fetch('/api/insert_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatname: chatName })
    })
    .then(res => {
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return res.json();
    })
    .then(data => {
        if (!data) return; // Redirected to login
        if (data.success && data.chat) {
            input.value = '';
            // Select the newly created chat using the returned chat object
            selectChat(data.chat);
            // Reload the chat list to show the new chat
            loadChatList();
            // Focus the message input so user can start typing immediately
            const messageInput = document.getElementById('user-input');
            if (messageInput) {
                messageInput.focus();
            }
        } else {
            alert('Failed to create chat.');
        }
    })
    .catch(err => {
        console.error(err);
        alert('Error creating chat.');
    });
}

function loadChatList(searchQuery = '') {
    const previewMaxLength = 45;

    fetch('/get_chats')
    .then(res => {
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return res.json();
    })
    .then(data => {
        if (!data) return; // Redirected to login
        const chatTabs = document.getElementById('chat-tabs');
        chatTabs.innerHTML = '';
        if (data.success && data.chats && data.chats.length > 0) {
            const filteredChats = data.chats.filter(chat => 
                chat.CHATNAME.toLowerCase().includes(searchQuery.toLowerCase())
            );
            
            if (filteredChats.length > 0) {
                filteredChats.forEach(chat => {
                    const tab = document.createElement('button');
                    const isSelected = selectedChatId === chat.CHATID;
                    tab.className = isSelected ? 'chat-tab selected' : 'chat-tab';
                    
                    const content = document.createElement('div');
                    content.className = 'chat-tab-content';
                    
                    // Name header with badge
                    const nameHeader = document.createElement('div');
                    nameHeader.className = 'chat-tab-name-header';
                    
                    const name = document.createElement('div');
                    name.className = 'chat-tab-name';
                    name.textContent = chat.CHATNAME;
                    
                    nameHeader.appendChild(name);

                    const preview = document.createElement('div');
                    preview.className = 'chat-tab-preview';
                    const rawLastMessage = (chat.LASTMESSAGE || '').trim();
                    const shortLastMessage = rawLastMessage.length > previewMaxLength
                        ? `${rawLastMessage.slice(0, previewMaxLength)}...`
                        : rawLastMessage;
                    preview.textContent = shortLastMessage || 'No messages yet';
                    
                    content.appendChild(nameHeader);
                    content.appendChild(preview);
                    tab.appendChild(content);
                    
                    // Check for DRAFT orders and add badge
                    fetch(`/api/check_draft_order?chatid=${chat.CHATID}`)
                    .then(res => {
                        if (res.status === 401) {
                            window.location.href = '/login';
                            return null;
                        }
                        return res.json();
                    })
                    .then(orderData => {
                        if (!orderData) return; // Redirected to login
                        if (orderData.success && orderData.hasDraft) {
                            const badge = document.createElement('span');
                            badge.className = 'draft-badge';
                            badge.textContent = 'DRAFT';
                            nameHeader.appendChild(badge);
                        }
                    })
                    .catch(err => console.log('Order check error:', err));
                    
                    tab.onclick = function() { selectChat(chat); loadChatList(searchQuery); };
                    chatTabs.appendChild(tab);
                });
            } else {
                chatTabs.innerHTML = '<div style="padding:16px; color:#888; text-align:center;">No chats matching search.</div>';
            }
        } else {
            chatTabs.innerHTML = '<div style="padding:16px; color:#888; text-align:center;">No chats found.</div>';
        }
    })
    .catch((err) => {
        console.error(err);
        document.getElementById('chat-tabs').innerHTML = '<div style="padding:16px; color:#888; text-align:center;">Failed to load chats.</div>';
    });
}

document.addEventListener('DOMContentLoaded', function() {
        // Check if user has any draft orders and hide menu items accordingly
        checkUserDraftOrdersOnLoad();
    
    // Search functionality
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            loadChatList(e.target.value);
        });
    }

    const newChatInput = document.getElementById('new-chat-name');
    if (newChatInput) {
        newChatInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') createNewChat();
        });
    }
    
    // Message input - send on Enter (but allow Shift+Enter for new line)
    const userInput = document.getElementById('user-input');
    userInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Auto-resize textarea as user types
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });

    loadChatList();
    fetch('/get_chats')
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return; // Redirected to login
            if (data.success && data.chats && data.chats.length > 0) {
                selectChat(data.chats[0]);
            }
        });
});
