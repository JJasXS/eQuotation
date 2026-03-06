// Login Page JavaScript

let currentEmail = '';
let otpTimer = null;
let resendCountdown = 0;

function handleEmailSubmit(event) {
    event.preventDefault();
    const email = document.getElementById('email').value.trim();
    const emailError = document.getElementById('email-error');
    const submitBtn = event.target.querySelector('.btn-submit');
    
    if (!email) {
        showError(emailError, 'Email is required');
        return;
    }
    
    // ============================================
    // VALIDATION DISABLED FOR TESTING
    // Uncomment below to enable email format validation
    // ============================================
    // const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    // if (!emailRegex.test(email)) {
    //     showError(emailError, 'Please enter a valid email');
    //     return;
    // }
    
    // Clear previous errors
    emailError.textContent = '';
    emailError.classList.remove('show');
    
    // Disable button and show loading state
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending OTP...';
    
    // Call backend to send OTP
    fetch('/api/send_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: email })
    })
    .then(res => res.json())
    .then(data => {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Continue';
        
        if (data.success) {
            currentEmail = email;
            document.getElementById('email-display').textContent = email;
            showStep('otp-step');
            if (data.debug_otp) {
                showError(document.getElementById('otp-error'), `DEBUG OTP: ${data.debug_otp}`, 'success');
            }
            startResendTimer();
        } else {
            showError(emailError, data.error || 'Failed to send OTP');
        }
    })
    .catch(err => {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Continue';
        showError(emailError, 'Network error. Please try again.');
        console.error(err);
    });
}

function handleOtpSubmit(event) {
    event.preventDefault();
    const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));
    const otp = otpInputs.map(input => input.value).join('').trim();
    const otpError = document.getElementById('otp-error');
    const submitBtn = event.target.querySelector('.btn-submit');
    
    // ============================================
    // VALIDATION DISABLED FOR TESTING
    // Uncomment below to enable OTP format validation
    // ============================================
    // if (!otp || otp.length !== 6) {
    //     showError(otpError, 'Please enter a valid 6-digit OTP');
    //     return;
    // }
    // 
    // if (!/^[0-9]{6}$/.test(otp)) {
    //     showError(otpError, 'OTP must contain only numbers');
    //     return;
    // }
    
    // Clear previous errors
    otpError.textContent = '';
    otpError.classList.remove('show');
    
    // Disable button and show loading state
    submitBtn.disabled = true;
    submitBtn.textContent = 'Verifying...';
    
    // Call backend to verify OTP
    fetch('/api/verify_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            email: currentEmail,
            otp: otp 
        })
    })
    .then(res => res.json())
    .then(data => {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Verify';
        
        if (data.success) {
            // OTP verified - redirect to appropriate page based on user type
            const redirectUrl = data.redirect || '/chat';
            console.log(`Redirecting ${data.user_type} to ${redirectUrl}`);
            window.location.href = redirectUrl;
        } else {
            showError(otpError, data.error || 'Invalid OTP');
        }
    })
    .catch(err => {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Verify';
        showError(otpError, 'Network error. Please try again.');
        console.error(err);
    });
}

function resendOtp() {
    if (resendCountdown > 0) {
        return; // Still in cooldown
    }
    
    const resendBtn = document.querySelector('.btn-resend');
    resendBtn.disabled = true;
    
    fetch('/api/send_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: currentEmail })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            if (data.debug_otp) {
                showError(document.getElementById('otp-error'), `DEBUG OTP: ${data.debug_otp}`, 'success');
            } else {
                showError(document.getElementById('otp-error'), 'OTP resent successfully', 'success');
            }
            startResendTimer();
        } else {
            showError(document.getElementById('otp-error'), data.error || 'Failed to resend OTP');
        }
        resendBtn.disabled = false;
    })
    .catch(err => {
        console.error(err);
        resendBtn.disabled = false;
    });
}

function startResendTimer() {
    resendCountdown = 30;
    const resendBtn = document.querySelector('.btn-resend');
    resendBtn.textContent = `Resend (${resendCountdown}s)`;
    resendBtn.disabled = true;
    
    const interval = setInterval(() => {
        resendCountdown--;
        if (resendCountdown > 0) {
            resendBtn.textContent = `Resend (${resendCountdown}s)`;
        } else {
            resendBtn.textContent = 'Resend';
            resendBtn.disabled = false;
            clearInterval(interval);
        }
    }, 1000);
}

function backToEmail() {
    showStep('email-step');
    document.getElementById('email').focus();
}

function showStep(stepId) {
    // Hide all steps
    document.querySelectorAll('.login-step').forEach(step => {
        step.classList.remove('active');
    });
    
    // Show selected step
    document.getElementById(stepId).classList.add('active');
    
    // Clear OTP input
    if (stepId === 'otp-step') {
        const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));
        otpInputs.forEach(input => {
            input.value = '';
        });
        if (otpInputs.length > 0) {
            otpInputs[0].focus();
        }
    }
}

function showError(errorElement, message, type = 'error') {
    errorElement.textContent = message;
    errorElement.classList.add('show');
    
    if (type === 'success') {
        errorElement.style.background = 'rgba(75, 110, 158, 0.1)';
        errorElement.style.color = '#4b6e9e';
        setTimeout(() => {
            errorElement.classList.remove('show');
            errorElement.style.background = '';
            errorElement.style.color = '';
        }, 3000);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));

    function checkAndAutoSubmitOtp() {
        const otpValues = otpInputs.map(input => input.value).join('');
        if (otpValues.length === 6 && /^\d{6}$/.test(otpValues)) {
            // Wait a moment for visual feedback, then auto-submit
            setTimeout(() => {
                const otpForm = document.querySelector('form[name="otp-form"]') || 
                               document.querySelector('.otp-form') || 
                               otpInputs[0].closest('form');
                if (otpForm) {
                    otpForm.dispatchEvent(new Event('submit'));
                }
            }, 300);
        }
    }

    if (otpInputs.length > 0) {
        otpInputs.forEach((input, index) => {
            input.addEventListener('input', function() {
                this.value = this.value.replace(/[^0-9]/g, '').slice(0, 1);
                if (this.value && index < otpInputs.length - 1) {
                    otpInputs[index + 1].focus();
                }
                checkAndAutoSubmitOtp();
            });

            input.addEventListener('keydown', function(event) {
                // Handle numpad digits explicitly (works even if NumLock state is odd)
                if (/^Numpad[0-9]$/.test(event.code)) {
                    const digit = event.code.replace('Numpad', '');
                    this.value = digit;
                    if (index < otpInputs.length - 1) {
                        otpInputs[index + 1].focus();
                    } else {
                        checkAndAutoSubmitOtp();
                    }
                    event.preventDefault();
                    return;
                }

                // Handle top-row digits explicitly
                if (/^[0-9]$/.test(event.key)) {
                    this.value = event.key;
                    if (index < otpInputs.length - 1) {
                        otpInputs[index + 1].focus();
                    } else {
                        checkAndAutoSubmitOtp();
                    }
                    event.preventDefault();
                    return;
                }

                if (event.key === 'Backspace' && !this.value && index > 0) {
                    otpInputs[index - 1].focus();
                }
            });

            input.addEventListener('paste', function(event) {
                event.preventDefault();
                const pasted = (event.clipboardData || window.clipboardData)
                    .getData('text')
                    .replace(/[^0-9]/g, '')
                    .slice(0, otpInputs.length);

                for (let i = 0; i < otpInputs.length; i++) {
                    otpInputs[i].value = pasted[i] || '';
                }

                const focusIndex = Math.min(pasted.length, otpInputs.length - 1);
                otpInputs[focusIndex].focus();
                
                checkAndAutoSubmitOtp();
            });
        });
    }
});
