function handleNewGuestSignIn(event) {
    event.preventDefault();

    const form = document.getElementById('new-guest-signin-form');
    const messageBox = document.getElementById('guest-message');
    const payloadPreview = document.getElementById('payload-preview');
    const submitBtn = form.querySelector('.btn-submit');

    const companyname = (document.getElementById('companyname').value || '').trim();

    const payload = { companyname };
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
