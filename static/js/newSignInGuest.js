function handleNewGuestSignIn(event) {
    event.preventDefault();

    const form = document.getElementById('new-guest-signin-form');
    const messageBox = document.getElementById('guest-message');
    const payloadPreview = document.getElementById('payload-preview');
    const submitBtn = form.querySelector('.btn-submit');

    const companyname = (document.getElementById('companyname').value || '').trim();
    const area = (document.getElementById('area').value || '').trim();
    const currencycode = (document.getElementById('currencycode').value || '').trim();
    const tin = (document.getElementById('tin').value || '').trim();
    const brn = (document.getElementById('brn').value || '').trim();
    const brn2 = (document.getElementById('brn2').value || '').trim();
    const salestaxno = (document.getElementById('salestaxno').value || '').trim();
    const servicetaxno = (document.getElementById('servicetaxno').value || '').trim();
    const taxexemptno = (document.getElementById('taxexemptno').value || '').trim();
    const taxexpdate = (document.getElementById('taxexpdate').value || '').trim();
    const attention = (document.getElementById('attention').value || '').trim();
    const phone1 = (document.getElementById('phone1').value || '').trim();
    const email = (document.getElementById('email').value || '').trim();
    const address1 = (document.getElementById('address1').value || '').trim();
    const address2 = (document.getElementById('address2').value || '').trim();
    const address3 = (document.getElementById('address3').value || '').trim();
    const address4 = (document.getElementById('address4').value || '').trim();
    const postcode = (document.getElementById('postcode').value || '').trim();
    const city = (document.getElementById('city').value || '').trim();
    const state = (document.getElementById('state').value || '').trim();
    const country = (document.getElementById('country').value || '').trim();

    const payload = { companyname, area, currencycode, tin, brn, brn2, salestaxno, servicetaxno, taxexemptno, taxexpdate, attention, phone1, email, address1, address2, address3, address4, postcode, city, state, country };
    payloadPreview.textContent = `Request:\n${JSON.stringify(payload, null, 2)}`;
    payloadPreview.classList.add('show');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    fetch('/api/create_signin_user_minimal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then((res) => res.json().then((data) => ({ status: res.status, data })))
        .then(({ status, data }) => {
            payloadPreview.textContent = `Response (${status}):\n${JSON.stringify(data, null, 2)}`;
            payloadPreview.classList.add('show');
            if (status >= 200 && status < 300 && data.success) {
                messageBox.textContent = `Guest user created successfully. Customer Code: ${data.customerCode}`;
                messageBox.className = 'guest-message show success';
            } else {
                messageBox.textContent = data.error || 'Failed to create customer.';
                messageBox.className = 'guest-message show error';
            }
        })
        .catch((error) => {
            console.error('create_signin_user_minimal error:', error);
            messageBox.textContent = 'Network error while creating customer.';
            messageBox.className = 'guest-message show error';
        })
        .finally(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create Customer';
        });
}

async function loadCurrencySymbols() {
    const currencySelect = document.getElementById('currencycode');
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

        if (currencySelect.options.length > 0) {
            currencySelect.selectedIndex = 0;
        }
    } catch (error) {
        console.error('Error loading currency symbols:', error);
        currencySelect.innerHTML = '<option value="">No currency available</option>';
    }
}

async function loadAreaCodes() {
    const areaSelect = document.getElementById('area');
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

        if (areaSelect.options.length > 0) {
            areaSelect.selectedIndex = 0;
        }
    } catch (error) {
        console.error('Error loading area codes:', error);
        areaSelect.innerHTML = '<option value="">No area available</option>';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCurrencySymbols();
    loadAreaCodes();
    initPostcodeAutofill();
});

function normalizePostcode(value) {
    return String(value || '').trim();
}

function initPostcodeAutofill() {
    const postcodeEl = document.getElementById('postcode');
    const cityEl = document.getElementById('city');
    const stateEl = document.getElementById('state');

    if (!postcodeEl || !cityEl || !stateEl) {
        return;
    }

    let timer = null;

    async function runLookup() {
        const postcode = normalizePostcode(postcodeEl.value);

        if (!postcode || postcode.length < 5) {
            cityEl.value = '';
            stateEl.value = '';
            return;
        }

        try {
            const res = await fetch(`/api/lookup_postcode?postcode=${encodeURIComponent(postcode)}`);
            const data = await res.json();

            if (!data || !data.success || !data.found || !data.data) {
                cityEl.value = '';
                stateEl.value = '';
                return;
            }

            cityEl.value = data.data.city || '';
            stateEl.value = data.data.state || '';
        } catch (error) {
            console.error('postcode lookup failed:', error);
            cityEl.value = '';
            stateEl.value = '';
        }
    }

    function scheduleLookup() {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(runLookup, 250);
    }

    postcodeEl.addEventListener('input', scheduleLookup);
    postcodeEl.addEventListener('change', runLookup);
    postcodeEl.addEventListener('blur', runLookup);
}
