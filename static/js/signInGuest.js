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
                form.reset();
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
