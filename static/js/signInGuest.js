function handleGuestSignIn(event) {
    event.preventDefault();

    const form = document.getElementById('guest-signin-form');
    const messageBox = document.getElementById('guest-message');
    const payloadPreview = document.getElementById('payload-preview');

    const formData = new FormData(form);

    // For preview, convert FormData to object (excluding files)
    const previewData = {};
    for (let [key, value] of formData.entries()) {
        if (value instanceof File) {
            previewData[key] = `${value.name} (${(value.size / 1024).toFixed(2)} KB)`;
        } else {
            previewData[key] = value;
        }
    }
    payloadPreview.textContent = JSON.stringify(previewData, null, 2);
    payloadPreview.classList.add('show');

    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    fetch('/api/create_signin_user', {
        method: 'POST',
        body: formData
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

async function loadAreaCodes() {
    const areaSelect = document.getElementById('AREA');
    if (!areaSelect) {
        return;
    }

    try {
        const response = await fetch('/api/get_area_codes');
        const data = await response.json();

        if (!data.success || !Array.isArray(data.data)) {
            throw new Error(data.error || 'Failed to load areas');
        }

        areaSelect.innerHTML = '';
        data.data.forEach((code) => {
            const option = document.createElement('option');
            option.value = code;
            option.textContent = code;
            areaSelect.appendChild(option);
        });

        // Auto-select the first area returned by the API.
        if (areaSelect.options.length > 0) {
            areaSelect.selectedIndex = 0;
        } else {
            areaSelect.innerHTML = '<option value="">No area available</option>';
            areaSelect.selectedIndex = 0;
        }
    } catch (error) {
        console.error('Error loading area codes:', error);
        areaSelect.innerHTML = '<option value="">No area available</option>';
        areaSelect.selectedIndex = 0;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCurrencySymbols();
    loadAreaCodes();
    initPostcodeAutofill();
    initBrn2NumericOnly();
});

function normalizePostcode(value) {
    return String(value || '').trim();
}

function initPostcodeAutofill() {
    const postcodeEl = document.getElementById('POSTCODE');
    const cityEl = document.getElementById('CITY');
    const stateEl = document.getElementById('STATE');

    if (!postcodeEl || !cityEl || !stateEl) return;

    let timer = null;

    async function runLookup() {
        const postcode = normalizePostcode(postcodeEl.value);

        // Clear auto fields if postcode not usable yet
        if (!postcode || postcode.length < 5) {
            cityEl.value = '';
            stateEl.value = '';
            return;
        }

        try {
            const res = await fetch(`/api/lookup_postcode?postcode=${encodeURIComponent(postcode)}`);
            const data = await res.json();

            if (!data || !data.success) {
                cityEl.value = '';
                stateEl.value = '';
                return;
            }

            if (data.found && data.data) {
                cityEl.value = data.data.city || '';
                stateEl.value = data.data.state || '';
            } else {
                cityEl.value = '';
                stateEl.value = '';
            }
        } catch (e) {
            console.error('postcode lookup failed:', e);
            cityEl.value = '';
            stateEl.value = '';
        }
    }

    function scheduleLookup() {
        if (timer) clearTimeout(timer);
        timer = setTimeout(runLookup, 250);
    }

    postcodeEl.addEventListener('input', scheduleLookup);
    postcodeEl.addEventListener('change', runLookup);
    postcodeEl.addEventListener('blur', runLookup);
}

function initBrn2NumericOnly() {
    const el = document.getElementById('BRN2');
    if (!el) return;

    el.addEventListener('input', () => {
        const digitsOnly = String(el.value || '').replace(/\D+/g, '').slice(0, 12);
        if (el.value !== digitsOnly) el.value = digitsOnly;
    });
}
