(function() {
    let previewTimer = null;
    let quotationChatId = null;

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function replaceLoadingWithError(loadingEl, messagesContainer, text) {
        if (!loadingEl || !messagesContainer) {
            return;
        }
        const errMsgDiv = document.createElement('div');
        errMsgDiv.className = 'quotation-chat-message bot-message';
        errMsgDiv.innerHTML = `<div class="quotation-chat-popup-message-content">${escapeHtml(text)}</div>`;
        loadingEl.replaceWith(errMsgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    async function ensureQuotationChatSession() {
        if (quotationChatId) {
            return quotationChatId;
        }
        const response = await fetch('/api/insert_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chatname: 'Quotation Assistant Chat' })
        });
        if (response.status === 401) {
            window.location.href = '/login';
            return null;
        }
        let data = {};
        try {
            data = await response.json();
        } catch (e) {
            throw new Error('Invalid response from server when starting chat');
        }
        if (!response.ok) {
            throw new Error((data && (data.error || data.message)) || `Could not start chat (${response.status})`);
        }
        const cid = data && data.chat && (data.chat.CHATID != null ? data.chat.CHATID : data.chat.chatid);
        if (cid != null) {
            quotationChatId = cid;
            return quotationChatId;
        }
        throw new Error((data && data.error) || 'Failed to initialize quotation chat');
    }

    /** Used by orderQuotation.js sendQuickChatMessage (pagination) — must match this session. */
    window.getQuotationPopupChatId = function() {
        return quotationChatId;
    };

    function renderQuotationChatReplyHtml(reply) {
        const text = String(reply ?? '');
        if (typeof window.buildChatReplyHtml === 'function') {
            return window
                .buildChatReplyHtml(text)
                .replace(
                    'class="chat-popup-message-content rich-message-content"',
                    'class="quotation-chat-popup-message-content rich-message-content"'
                );
        }
        return `<div class="quotation-chat-popup-message-content">${escapeHtml(text).replace(/\n/g, '<br>')}</div>`;
    }

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

        // Pre-create chat session so first send is reliable (edit-quotation pages load heavy JS in parallel).
        ensureQuotationChatSession().catch(function(err) {
            console.warn('[quotation chat] Session warmup failed:', err);
        });

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
        ensureQuotationChatSession().catch(function(err) {
            console.warn('[quotation chat] Session warmup failed:', err);
        });
        setTimeout(() => {
            if (textarea) {
                textarea.focus();
            }
        }, 0);
    };
    // Send message
    window.sendQuotationChatMessage = async function() {
        const textarea = document.getElementById('quotation-chat-popup-textarea');
        const messagesContainer = document.getElementById('quotation-chat-popup-messages');
        if (!textarea || !messagesContainer) {
            return;
        }
        const message = textarea.value.trim();
        if (!message) return;
        // Add user message
        const userMsgDiv = document.createElement('div');
        userMsgDiv.className = 'quotation-chat-message user-message';
        userMsgDiv.innerHTML = `<div class="quotation-chat-popup-message-content">${escapeHtml(message)}</div>`;
        messagesContainer.appendChild(userMsgDiv);
        textarea.value = '';
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Loading placeholder while waiting for backend response
        const loadingMsgDiv = document.createElement('div');
        loadingMsgDiv.className = 'quotation-chat-message bot-message';
        loadingMsgDiv.innerHTML = '<div class="quotation-chat-popup-message-content">Typing...</div>';
        messagesContainer.appendChild(loadingMsgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        try {
            const chatId = await ensureQuotationChatSession();
            if (!chatId) {
                replaceLoadingWithError(
                    loadingMsgDiv,
                    messagesContainer,
                    'Please sign in again to use chat.'
                );
                return;
            }
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, chatid: chatId })
            });
            if (response.status === 401) {
                window.location.href = '/login';
                replaceLoadingWithError(loadingMsgDiv, messagesContainer, 'Session expired. Redirecting to sign in…');
                return;
            }
            let data = {};
            try {
                data = await response.json();
            } catch (e) {
                data = {};
            }
            if (!response.ok) {
                const errText =
                    (data && (data.error || data.message)) ||
                    (response.status === 403
                        ? 'Chat access denied (try refreshing the page).'
                        : `Chat request failed (${response.status}).`);
                replaceLoadingWithError(loadingMsgDiv, messagesContainer, errText);
                return;
            }
            const reply = (data && data.reply) ? String(data.reply) : 'Sorry, I could not generate a reply.';
            const botMsgDiv = document.createElement('div');
            botMsgDiv.className = 'quotation-chat-message bot-message';
            botMsgDiv.innerHTML = renderQuotationChatReplyHtml(reply);
            loadingMsgDiv.replaceWith(botMsgDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        } catch (err) {
            console.error('Quotation popup chat error:', err);
            const msg =
                err && err.message
                    ? String(err.message)
                    : 'Sorry, I encountered an error. Please try again.';
            replaceLoadingWithError(loadingMsgDiv, messagesContainer, msg);
        }
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