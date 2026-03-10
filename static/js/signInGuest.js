function handleGuestSignIn(event) {
    event.preventDefault();

    const form = document.getElementById('guest-signin-form');
    const messageBox = document.getElementById('guest-message');
    const payloadPreview = document.getElementById('payload-preview');

    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());

    // Keep visible mapping of frontend field keys for backend payload verification.
    payloadPreview.textContent = JSON.stringify(payload, null, 2);
    payloadPreview.classList.add('show');

    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    fetch('/api/create_signin_user', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
        .then((res) => res.json())
        .then((data) => {
            if (data.success) {
                messageBox.textContent = `Guest user created successfully. Customer Code: ${data.customerCode}`;
                messageBox.className = 'guest-message show success';
                const redirectUrl = data.redirect || '/login';
                setTimeout(() => {
                    window.location.href = redirectUrl;
                }, 600);
            } else {
                messageBox.textContent = data.error || 'Failed to create guest user.';
                messageBox.className = 'guest-message show error';
            }
        })
        .catch((error) => {
            console.error('create_signin_user error:', error);
            messageBox.textContent = 'Network error while creating guest user.';
            messageBox.className = 'guest-message show error';
        })
        .finally(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue as Guest';
        });
}

async function loadCurrencySymbols() {
    const currencySelect = document.getElementById('CURRENCYCODE');
    if (!currencySelect) {
        return;
    }

    try {
        const response = await fetch('/api/get_currency_symbols');
        const data = await response.json();

        if (!data.success || !Array.isArray(data.data)) {
            throw new Error(data.error || 'Failed to load currencies');
        }

        currencySelect.innerHTML = '';
        data.data.forEach((symbol) => {
            const option = document.createElement('option');
            option.value = symbol;
            option.textContent = symbol;
            currencySelect.appendChild(option);
        });

        // Auto-select the first currency returned by the API.
        if (currencySelect.options.length > 0) {
            currencySelect.selectedIndex = 0;
        } else {
            currencySelect.innerHTML = '<option value="MYR">MYR</option>';
            currencySelect.selectedIndex = 0;
        }
    } catch (error) {
        console.error('Error loading currency symbols:', error);
        currencySelect.innerHTML = '<option value="MYR">MYR</option>';
        currencySelect.selectedIndex = 0;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCurrencySymbols();
});
