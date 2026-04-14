(function() {
    let previewTimer = null;

    function getQuotationChatElements() {
        return {
            popup: document.getElementById('quotation-chat-popup'),
            preview: document.getElementById('quotation-chat-preview'),
            textarea: document.getElementById('quotation-chat-popup-textarea')
        };
    }

    function hideQuotationChatPreview() {
        const { preview } = getQuotationChatElements();
        if (!preview) {
            return;
        }

        preview.classList.add('quotation-chat-preview-hidden');
        if (previewTimer) {
            clearTimeout(previewTimer);
            previewTimer = null;
        }
    }

    function showQuotationChatPreview() {
        const { preview, popup } = getQuotationChatElements();
        if (!preview || !popup || !popup.classList.contains('quotation-chat-popup-hidden')) {
            return;
        }

        preview.classList.remove('quotation-chat-preview-hidden');
        if (previewTimer) {
            clearTimeout(previewTimer);
        }
        previewTimer = window.setTimeout(() => {
            preview.classList.add('quotation-chat-preview-hidden');
            previewTimer = null;
        }, 1500);
    }

    // Toggle popup
    window.toggleQuotationChatPopup = function() {
        const { popup, textarea } = getQuotationChatElements();
        if (!popup) {
            return;
        }

        hideQuotationChatPreview();

        // Always bring popup to front
        popup.style.zIndex = 10050;
        popup.classList.toggle('quotation-chat-popup-hidden');
        if (popup.classList.contains('quotation-chat-popup-hidden')) {
            return;
        }

        setTimeout(() => {
            if (textarea) {
                textarea.focus();
            }
        }, 0);
    };
    window.closeQuotationChatPopup = function() {
        const { popup } = getQuotationChatElements();
        if (!popup) {
            return;
        }
        popup.classList.add('quotation-chat-popup-hidden');
    };
    window.openQuotationChatFromPreview = function() {
        const { popup, textarea } = getQuotationChatElements();
        if (!popup) {
            return;
        }

        hideQuotationChatPreview();
        popup.style.zIndex = 10050;
        popup.classList.remove('quotation-chat-popup-hidden');
        setTimeout(() => {
            if (textarea) {
                textarea.focus();
            }
        }, 0);
    };
    // Send message
    window.sendQuotationChatMessage = function() {
        const textarea = document.getElementById('quotation-chat-popup-textarea');
        const messagesContainer = document.getElementById('quotation-chat-popup-messages');
        const message = textarea.value.trim();
        if (!message) return;
        // Add user message
        const userMsgDiv = document.createElement('div');
        userMsgDiv.className = 'quotation-chat-message user-message';
        userMsgDiv.innerHTML = `<div class="quotation-chat-popup-message-content">${message}</div>`;
        messagesContainer.appendChild(userMsgDiv);
        textarea.value = '';
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        // Simulate bot reply (replace with real API call if needed)
        setTimeout(() => {
            const botMsgDiv = document.createElement('div');
            botMsgDiv.className = 'quotation-chat-message bot-message';
            botMsgDiv.innerHTML = `<div class="quotation-chat-popup-message-content">Sorry, this is a demo. Integrate with backend as needed.</div>`;
            messagesContainer.appendChild(botMsgDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }, 600);
    };
    // Enter key to send
    document.addEventListener('DOMContentLoaded', function() {
        const { textarea } = getQuotationChatElements();
        if (textarea) {
            textarea.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendQuotationChatMessage();
                }
            });
        }

        window.setTimeout(showQuotationChatPreview, 500);
    });
})();