// Delete Quotations Page - Handle checkbox selection and bulk delete

let allQuotations = [];
let selectedQuotations = new Set();

document.addEventListener('DOMContentLoaded', () => {
    loadQuotations();
    
    // Event listeners
    document.getElementById('select-all-checkbox').addEventListener('change', toggleSelectAll);
    document.getElementById('bulk-delete-btn').addEventListener('click', showDeleteConfirmation);
    document.getElementById('confirm-delete-btn').addEventListener('click', performBulkDelete);
    document.getElementById('cancel-delete-btn').addEventListener('click', closeDeleteModal);
});

async function loadQuotations() {
    const container = document.getElementById('quotations-container');
    
    try {
        console.log('[DEBUG] Fetching quotations from /api/admin/get_all_quotations...');
        const response = await fetch('/api/admin/get_all_quotations');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('[DEBUG] Response received:', data);
        
        if (data.success && data.data && Array.isArray(data.data)) {
            console.log(`[DEBUG] Found ${data.data.length} quotations`);
            allQuotations = data.data;
            renderQuotationsList();
        } else if (!data.success) {
            console.error('[DEBUG] API returned success=false:', data.error);
            throw new Error(data.error || 'API returned error');
        } else {
            console.error('[DEBUG] No quotations in response:', data);
            throw new Error('No quotations found in response. Expected "data" property.');
        }
    } catch (error) {
        console.error('[ERROR] Error loading quotations:', error);
        container.innerHTML = `<div class="error-loading">⚠️ Error loading quotations: ${error.message}</div>`;
        showError('Error loading quotations: ' + error.message);
    }
}

function renderQuotationsList() {
    const container = document.getElementById('quotations-container');
    
    if (!container) {
        console.error('[ERROR] quotations-container not found in DOM');
        return;
    }
    
    console.log(`[DEBUG] Rendering ${allQuotations.length} quotations`);
    
    if (allQuotations.length === 0) {
        container.innerHTML = '<div class="empty-message">No quotations found</div>';
        return;
    }
    
    // Clear container and render quotations
    container.innerHTML = allQuotations.map((quotation, index) => `
        <div class="quotation-item">
            <div class="checkbox-container">
                <input 
                    type="checkbox" 
                    class="quotation-checkbox"
                    data-dockey="${quotation.DOCKEY}"
                    data-docno="${quotation.DOCNO}"
                    onchange="handleCheckboxChange(${index})"
                >
            </div>
            <div class="quotation-content">
                <div class="quotation-header">
                    <div class="quotation-number">
                        <strong>${escapeHtml(quotation.DOCNO)}</strong>
                    </div>
                    <div class="quotation-date">
                        ${formatDate(quotation.DOCDATE)}
                    </div>
                    <div class="quotation-amount">
                        ${formatCurrency(quotation.DOCAMT)} ${quotation.CURRENCYCODE || ''}
                    </div>
                </div>
                <div class="quotation-details">
                    <span class="customer-info">
                        <strong>Customer:</strong> ${escapeHtml(quotation.COMPANYNAME || 'N/A')}
                    </span>
                    <span class="status-badge" data-status="${quotation.CANCELLED ? 'cancelled' : 'active'}">
                        ${quotation.CANCELLED ? 'Cancelled' : 'Active'}
                    </span>
                    <span class="validity-info">
                        <strong>Valid Until:</strong> ${quotation.VALIDITY || 'N/A'}
                    </span>
                </div>
            </div>
        </div>
    `).join('');
    
    updateControlsState();
}

function handleCheckboxChange(index) {
    const checkbox = document.querySelectorAll('.quotation-checkbox')[index];
    const dockey = checkbox.dataset.dockey;
    
    if (checkbox.checked) {
        selectedQuotations.add(parseInt(dockey));
    } else {
        selectedQuotations.delete(parseInt(dockey));
    }
    
    updateControlsState();
}

function toggleSelectAll(event) {
    const isChecked = event.target.checked;
    const checkboxes = document.querySelectorAll('.quotation-checkbox');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
        const dockey = parseInt(checkbox.dataset.dockey);
        if (isChecked) {
            selectedQuotations.add(dockey);
        } else {
            selectedQuotations.delete(dockey);
        }
    });
    
    updateControlsState();
}

function updateControlsState() {
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
    const countSpan = document.querySelector('.selected-count');
    
    const count = selectedQuotations.size;
    countSpan.textContent = `${count} selected`;
    
    // Update Select All checkbox state
    const allCheckboxes = document.querySelectorAll('.quotation-checkbox');
    const allChecked = allCheckboxes.length > 0 && 
                       Array.from(allCheckboxes).every(cb => cb.checked);
    const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
    
    selectAllCheckbox.checked = allChecked;
    selectAllCheckbox.indeterminate = someChecked && !allChecked;
    
    // Enable/disable delete button
    bulkDeleteBtn.disabled = count === 0;
}

function showDeleteConfirmation() {
    if (selectedQuotations.size === 0) {
        showError('Please select at least one quotation');
        return;
    }
    
    document.getElementById('delete-count').textContent = selectedQuotations.size;
    document.getElementById('delete-modal').classList.add('open');
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('open');
}

async function performBulkDelete() {
    const dockeyArray = Array.from(selectedQuotations);
    
    if (dockeyArray.length === 0) {
        showError('No quotations selected');
        return;
    }
    
    try {
        // Perform bulk delete via API
        const response = await fetch('/api/admin/bulk_cancel_quotations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                dockeyList: dockeyArray
            })
        });
        
        const result = await response.json();
        
        closeDeleteModal();
        
        if (result.success) {
            showSuccess(`${result.deleted_count || dockeyArray.length} quotation(s) deleted successfully`);
            selectedQuotations.clear();
            await loadQuotations();
            updateControlsState();
        } else {
            showError(result.error || 'Failed to delete quotations');
        }
    } catch (error) {
        console.error('Error deleting quotations:', error);
        closeDeleteModal();
        showError('Error deleting quotations: ' + error.message);
    }
}

// Utility Functions
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
    } catch (e) {
        return dateStr;
    }
}

function formatCurrency(amount) {
    if (!amount) return '0.00';
    return parseFloat(amount).toFixed(2);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    const messageEl = document.getElementById('success-message');
    messageEl.querySelector('span').textContent = '✓ ' + message;
    messageEl.classList.add('show');
    setTimeout(() => {
        messageEl.classList.remove('show');
    }, 4000);
}

function showError(message) {
    const messageEl = document.getElementById('error-message');
    messageEl.querySelector('span').textContent = message;
    messageEl.classList.add('show');
    setTimeout(() => {
        messageEl.classList.remove('show');
    }, 4000);
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    const modal = document.getElementById('delete-modal');
    if (e.target === modal) {
        closeDeleteModal();
    }
});
