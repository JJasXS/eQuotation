// Login Page — OTP + login_mode (customer | admin | supplier) for directory-specific email lookup

let currentEmail = '';
/** @type {'customer'|'admin'|'supplier'} */
let currentLoginMode = 'customer';
let otpTimer = null;
let resendCountdown = 0;

/** Real slides count (no clones). Extended track = [clone last] + reals + [clone first]. */
let realSlideCount = 0;
/** Index in extended track (0 = clone of last real, 1..n = reals, n+1 = clone of first). */
let extendedIndex = 1;
let carouselTransitioning = false;

function getCarouselTrack() {
    return document.getElementById('login-carousel-track');
}

/** All slide nodes in DOM order (includes clones after init). */
function getExtendedSlides() {
    const track = getCarouselTrack();
    return track ? Array.from(track.querySelectorAll('.login-carousel-slide')) : [];
}

function logicalIndexFromExtended(ext, n) {
    if (n <= 1) {
        return 0;
    }
    if (ext === 0) {
        return n - 1;
    }
    if (ext === n + 1) {
        return 0;
    }
    return ext - 1;
}

function extendedIndexFromLogical(logical, n) {
    return logical + 1;
}

function getViewportSlideWidth() {
    const viewport = document.getElementById('login-carousel-viewport');
    return viewport ? viewport.getBoundingClientRect().width : 0;
}

/** Apply transform + active slide + dots + currentLoginMode. */
function applyCarouselPosition(instant) {
    const viewport = document.getElementById('login-carousel-viewport');
    const track = getCarouselTrack();
    const slides = getExtendedSlides();
    if (!viewport || !track || !slides.length || realSlideCount < 1) {
        return;
    }
    const w = getViewportSlideWidth();
    if (w <= 0) {
        return;
    }

    if (instant) {
        track.style.transition = 'none';
    } else if (track.style.transition === 'none') {
        track.style.transition = '';
    }

    track.style.transform = `translateX(-${extendedIndex * w}px)`;

    if (instant) {
        void track.offsetHeight;
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                track.style.transition = '';
            });
        });
    }

    slides.forEach((el, i) => {
        const active = i === extendedIndex;
        el.classList.toggle('is-active', active);
        el.setAttribute('tabindex', active ? '0' : '-1');
        el.setAttribute('aria-selected', active ? 'true' : 'false');
        if (active) {
            currentLoginMode = el.getAttribute('data-mode') || 'customer';
        }
    });

    const logical = logicalIndexFromExtended(extendedIndex, realSlideCount);
    document.querySelectorAll('.login-carousel-dot').forEach((dot, i) => {
        dot.setAttribute('aria-current', i === logical ? 'true' : 'false');
    });
}

/** Measure viewport so one full slide shows; keep current extendedIndex. */
function layoutLoginCarousel() {
    const viewport = document.getElementById('login-carousel-viewport');
    const track = getCarouselTrack();
    const slides = getExtendedSlides();
    if (!viewport || !track || !slides.length) {
        return;
    }
    const w = getViewportSlideWidth();
    slides.forEach((slide) => {
        slide.style.flex = `0 0 ${w}px`;
        slide.style.width = `${w}px`;
        slide.style.maxWidth = `${w}px`;
    });
    track.style.width = `${w * slides.length}px`;
    applyCarouselPosition(true);
    carouselTransitioning = false;
}

function jumpCarouselAfterCloneEdge() {
    const n = realSlideCount;
    if (n < 2) {
        return;
    }
    if (extendedIndex === n + 1) {
        extendedIndex = 1;
        applyCarouselPosition(true);
    } else if (extendedIndex === 0) {
        extendedIndex = n;
        applyCarouselPosition(true);
    }
}

function goCarouselNext() {
    const slides = getExtendedSlides();
    if (carouselTransitioning || slides.length < 2) {
        return;
    }
    carouselTransitioning = true;
    extendedIndex = Math.min(extendedIndex + 1, slides.length - 1);
    applyCarouselPosition(false);
}

function goCarouselPrev() {
    if (carouselTransitioning || getExtendedSlides().length < 2) {
        return;
    }
    carouselTransitioning = true;
    extendedIndex = Math.max(extendedIndex - 1, 0);
    applyCarouselPosition(false);
}

/** Go to logical slide index 0..n-1 with animation when possible. */
function goCarouselLogical(logical) {
    const n = realSlideCount;
    if (n < 1 || logical < 0 || logical >= n) {
        return;
    }
    if (carouselTransitioning) {
        return;
    }
    const targetExt = extendedIndexFromLogical(logical, n);
    if (targetExt === extendedIndex) {
        return;
    }
    carouselTransitioning = true;
    extendedIndex = targetExt;
    applyCarouselPosition(false);
}

function buildCarouselClones() {
    const track = getCarouselTrack();
    if (!track) {
        return;
    }
    track.querySelectorAll('.login-carousel-slide--clone').forEach((el) => el.remove());

    const reals = Array.from(track.querySelectorAll('.login-carousel-slide:not(.login-carousel-slide--clone)'));
    realSlideCount = reals.length;
    if (realSlideCount < 2) {
        extendedIndex = 0;
        return;
    }

    const first = reals[0];
    const last = reals[realSlideCount - 1];

    const cloneLast = last.cloneNode(true);
    cloneLast.classList.add('login-carousel-slide--clone');
    cloneLast.classList.remove('is-active');
    cloneLast.setAttribute('aria-hidden', 'true');

    const cloneFirst = first.cloneNode(true);
    cloneFirst.classList.add('login-carousel-slide--clone');
    cloneFirst.classList.remove('is-active');
    cloneFirst.setAttribute('aria-hidden', 'true');

    track.insertBefore(cloneLast, first);
    track.appendChild(cloneFirst);

    const logicalStart = reals.findIndex((s) => s.classList.contains('is-active'));
    const logical = logicalStart >= 0 ? logicalStart : 1;
    reals.forEach((s) => s.classList.remove('is-active'));
    extendedIndex = extendedIndexFromLogical(logical, realSlideCount);
}

function initLoginCarousel() {
    const dotsHost = document.getElementById('login-carousel-dots');
    const prev = document.getElementById('login-mode-prev');
    const next = document.getElementById('login-mode-next');
    const track = getCarouselTrack();

    buildCarouselClones();

    if (dotsHost && realSlideCount) {
        dotsHost.innerHTML = '';
        for (let i = 0; i < realSlideCount; i++) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'login-carousel-dot';
            b.setAttribute('aria-label', `Show login option ${i + 1}`);
            b.addEventListener('click', () => goCarouselLogical(i));
            dotsHost.appendChild(b);
        }
    }

    getExtendedSlides().forEach((slide, i) => {
        slide.addEventListener('click', () => {
            if (carouselTransitioning) {
                return;
            }
            if (i === extendedIndex) {
                return;
            }
            carouselTransitioning = true;
            extendedIndex = i;
            applyCarouselPosition(false);
        });
    });

    if (prev) {
        prev.addEventListener('click', goCarouselPrev);
    }
    if (next) {
        next.addEventListener('click', goCarouselNext);
    }

    if (track) {
        track.addEventListener('transitionend', (e) => {
            if (e.target !== track || e.propertyName !== 'transform') {
                return;
            }
            if (!carouselTransitioning) {
                return;
            }
            carouselTransitioning = false;
            jumpCarouselAfterCloneEdge();
        });
    }

    layoutLoginCarousel();
    window.addEventListener('resize', () => {
        layoutLoginCarousel();
    });
    const viewport = document.getElementById('login-carousel-viewport');
    if (viewport && typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(() => layoutLoginCarousel());
        ro.observe(viewport);
    }
}

function handleEmailSubmit(event) {
    event.preventDefault();
    const email = document.getElementById('email').value.trim();
    const emailError = document.getElementById('email-error');
    const submitBtn = event.target.querySelector('.btn-submit');

    if (!email) {
        showError(emailError, 'Email is required');
        return;
    }

    emailError.textContent = '';
    emailError.classList.remove('show');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending OTP...';

    fetch('/api/send_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: email, login_mode: currentLoginMode })
    })
        .then((res) => res.json())
        .then((data) => {
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
        .catch((err) => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue';
            showError(emailError, 'Network error. Please try again.');
            console.error(err);
        });
}

function handleOtpSubmit(event) {
    event.preventDefault();
    const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));
    const otp = otpInputs.map((input) => input.value).join('').trim();
    const otpError = document.getElementById('otp-error');
    const submitBtn = event.target.querySelector('.btn-submit');

    otpError.textContent = '';
    otpError.classList.remove('show');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Verifying...';

    fetch('/api/verify_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            email: currentEmail,
            otp: otp,
            login_mode: currentLoginMode
        })
    })
        .then((res) => res.json())
        .then((data) => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Verify';

            if (data.success) {
                const redirectUrl = data.redirect || '/chat';
                console.log(`Redirecting ${data.user_type} to ${redirectUrl}`);
                window.location.href = redirectUrl;
            } else {
                showError(otpError, data.error || 'Invalid OTP');
            }
        })
        .catch((err) => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Verify';
            showError(otpError, 'Network error. Please try again.');
            console.error(err);
        });
}

function resendOtp() {
    if (resendCountdown > 0) {
        return;
    }

    const resendBtn = document.querySelector('.btn-resend');
    resendBtn.disabled = true;

    fetch('/api/send_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: currentEmail, login_mode: currentLoginMode })
    })
        .then((res) => res.json())
        .then((data) => {
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
        .catch((err) => {
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
    document.querySelectorAll('.login-step').forEach((step) => {
        step.classList.remove('active');
    });

    document.getElementById(stepId).classList.add('active');

    if (stepId === 'otp-step') {
        const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));
        otpInputs.forEach((input) => {
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

document.addEventListener('DOMContentLoaded', function () {
    initLoginCarousel();

    const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));

    function checkAndAutoSubmitOtp() {
        const otpValues = otpInputs.map((input) => input.value).join('');
        if (otpValues.length === 6 && /^\d{6}$/.test(otpValues)) {
            setTimeout(() => {
                const otpForm = document.getElementById('otp-form');
                if (otpForm) {
                    otpForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            }, 300);
        }
    }

    if (otpInputs.length > 0) {
        otpInputs.forEach((input, index) => {
            input.addEventListener('input', function () {
                this.value = this.value.replace(/[^0-9]/g, '').slice(0, 1);
                if (this.value && index < otpInputs.length - 1) {
                    otpInputs[index + 1].focus();
                }
                checkAndAutoSubmitOtp();
            });

            input.addEventListener('keydown', function (event) {
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

            input.addEventListener('paste', function (event) {
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
