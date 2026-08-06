// Login Page — OTP + login_mode (customer | admin | supplier) for directory-specific email lookup

let currentEmail = '';
/** @type {'customer'|'admin'|'supplier'} */
let currentLoginMode = 'customer';
let otpExpiryTimerId = null;
let otpExpiresAtUnix = 0;
let otpExpired = false;
let resendCountdown = 0;
let resendTimerId = null;
const OTP_LIFETIME_DEFAULT = 120;
const RESEND_COOLDOWN_DEFAULT = 30;

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

    const controller = new AbortController();
    const clientOtpMs = 45000;
    const abortTimer = setTimeout(() => controller.abort(), clientOtpMs);

    fetch('/api/send_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: email, login_mode: currentLoginMode }),
        signal: controller.signal
    })
        .then((res) => {
            clearTimeout(abortTimer);
            return res.json();
        })
        .then((data) => {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue';

            if (data.success) {
                currentEmail = email;
                document.getElementById('email-display').textContent = email;
                showStep('otp-step');
                if (data.debug_otp) {
                    showError(document.getElementById('otp-error'), `DEBUG OTP: ${data.debug_otp}`, 'success');
                } else if (data.email_sent === false) {
                    showError(
                        document.getElementById('otp-error'),
                        data.message ||
                            'Email is not configured on the server (no SMTP). Check inbox only after fixing SMTP.',
                        'warning'
                    );
                } else {
                    showError(document.getElementById('otp-error'), data.message || 'OTP sent successfully', 'success');
                }
                startOtpExpiryTimer(data.expires_at_unix, data.otp_lifetime_seconds || data.expiry);
                startResendTimer(data.resend_cooldown_seconds);
            } else {
                showError(emailError, data.error || 'Failed to send OTP');
                if (data.cooldown_remaining_seconds > 0) {
                    startResendTimer(data.cooldown_remaining_seconds);
                }
            }
        })
        .catch((err) => {
            clearTimeout(abortTimer);
            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue';
            if (err && err.name === 'AbortError') {
                showError(
                    emailError,
                    'Request timed out (SMTP or network). Check server logs, SMTP_TIMEOUT, firewall, and port 587 vs 465.'
                );
            } else {
                showError(emailError, 'Network error. Please try again.');
            }
            console.error(err);
        });
}

function handleOtpSubmit(event) {
    event.preventDefault();
    if (otpExpired) {
        showError(document.getElementById('otp-error'), 'OTP expired. Please resend a new code.');
        return;
    }
    const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));
    const otp = otpInputs.map((input) => input.value).join('').trim();
    const otpError = document.getElementById('otp-error');
    const submitBtn = event.target.querySelector('.btn-submit');

    if (otpExpiresAtUnix && Math.floor(Date.now() / 1000) >= otpExpiresAtUnix) {
        setOtpExpiredState();
        return;
    }

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
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ data }) => {
            submitBtn.disabled = otpExpired;
            submitBtn.textContent = 'Verify';

            if (data.success) {
                const redirectUrl = data.redirect || '/create-quotation';
                console.log(`Redirecting ${data.user_type} to ${redirectUrl}`);
                window.location.href = redirectUrl;
            } else if (data.expired) {
                setOtpExpiredState();
                showError(otpError, data.error || 'OTP has expired. Request a new one.');
            } else {
                showError(otpError, data.error || 'Invalid OTP');
            }
        })
        .catch((err) => {
            submitBtn.disabled = otpExpired;
            submitBtn.textContent = 'Verify';
            showError(otpError, 'Network error. Please try again.');
            console.error(err);
        });
}

function resendOtp() {
    if (resendCountdown > 0) {
        return;
    }

    const resendBtn = document.getElementById('btn-resend') || document.querySelector('.btn-resend');
    if (resendBtn) resendBtn.disabled = true;

    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), 45000);

    fetch('/api/send_otp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: currentEmail, login_mode: currentLoginMode }),
        signal: controller.signal
    })
        .then((res) => {
            clearTimeout(abortTimer);
            return res.json().then((data) => ({ status: res.status, data }));
        })
        .then(({ data }) => {
            if (data.success) {
                if (data.debug_otp) {
                    showError(document.getElementById('otp-error'), `DEBUG OTP: ${data.debug_otp}`, 'success');
                } else if (data.email_sent === false) {
                    showError(
                        document.getElementById('otp-error'),
                        data.message || 'OTP regenerated but email was not sent (SMTP not configured).',
                        'warning'
                    );
                } else {
                    showError(document.getElementById('otp-error'), 'OTP sent successfully', 'success');
                }
                // Unlock + clear for new code
                setOtpInputsEnabled(true);
                document.querySelectorAll('.otp-digit').forEach((input) => {
                    input.value = '';
                    input.classList.remove('otp-digit--filled');
                });
                const first = document.querySelector('.otp-digit');
                if (first) first.focus();
                startOtpExpiryTimer(data.expires_at_unix, data.otp_lifetime_seconds || data.expiry);
                startResendTimer(data.resend_cooldown_seconds);
            } else {
                showError(document.getElementById('otp-error'), data.error || 'Failed to resend OTP');
                if (data.cooldown_remaining_seconds > 0) {
                    startResendTimer(data.cooldown_remaining_seconds);
                } else if (resendBtn) {
                    resendBtn.disabled = false;
                }
            }
        })
        .catch((err) => {
            clearTimeout(abortTimer);
            console.error(err);
            if (resendBtn) resendBtn.disabled = false;
            if (err && err.name === 'AbortError') {
                showError(
                    document.getElementById('otp-error'),
                    'Resend timed out. Check SMTP / server logs and try again.',
                    'warning'
                );
            }
        });
}

function setOtpInputsEnabled(enabled) {
    document.querySelectorAll('.otp-digit').forEach((input) => {
        input.disabled = !enabled;
        input.readOnly = !enabled;
        if (!enabled) input.blur();
    });
    const boxes = document.getElementById('otp-boxes');
    if (boxes) boxes.classList.toggle('is-locked', !enabled);
    const verifyBtn = document.getElementById('otp-verify-btn') || document.querySelector('#otp-form .btn-submit');
    if (verifyBtn) verifyBtn.disabled = !enabled;
}

function stopOtpExpiryTimer() {
    if (otpExpiryTimerId) {
        clearInterval(otpExpiryTimerId);
        otpExpiryTimerId = null;
    }
}

function setOtpExpiredState() {
    otpExpired = true;
    stopOtpExpiryTimer();
    document.querySelectorAll('.otp-digit').forEach((input) => {
        input.value = '';
        input.classList.remove('otp-digit--filled');
    });
    setOtpInputsEnabled(false);
    const timer = document.getElementById('otp-timer');
    if (timer) {
        timer.classList.add('is-expired');
        timer.innerHTML = 'OTP expired. Request a new code below.';
    }
    showError(document.getElementById('otp-error'), 'OTP expired. Please resend a new code.');
}

function startOtpExpiryTimer(expiresAtUnix, lifetimeSeconds) {
    stopOtpExpiryTimer();
    otpExpired = false;
    const life = lifetimeSeconds || OTP_LIFETIME_DEFAULT;
    otpExpiresAtUnix = expiresAtUnix || (Math.floor(Date.now() / 1000) + life);
    setOtpInputsEnabled(true);
    const timer = document.getElementById('otp-timer');
    if (timer) {
        timer.classList.remove('is-expired');
        timer.innerHTML = 'OTP expires in <span id="otp-countdown">' + life + '</span>s';
    }
    const tick = () => {
        const el = document.getElementById('otp-countdown');
        const now = Math.floor(Date.now() / 1000);
        const remaining = Math.max(0, otpExpiresAtUnix - now);
        if (el) el.textContent = String(remaining);
        if (remaining <= 0) {
            setOtpExpiredState();
        }
    };
    tick();
    otpExpiryTimerId = setInterval(tick, 1000);
}

function startResendTimer(seconds) {
    if (resendTimerId) {
        clearInterval(resendTimerId);
        resendTimerId = null;
    }
    resendCountdown = seconds || RESEND_COOLDOWN_DEFAULT;
    const resendBtn = document.getElementById('btn-resend') || document.querySelector('.btn-resend');
    if (!resendBtn) return;
    resendBtn.textContent = `Resend (${resendCountdown}s)`;
    resendBtn.disabled = true;

    resendTimerId = setInterval(() => {
        resendCountdown--;
        if (resendCountdown > 0) {
            resendBtn.textContent = `Resend (${resendCountdown}s)`;
        } else {
            resendBtn.textContent = 'Resend';
            resendBtn.disabled = false;
            clearInterval(resendTimerId);
            resendTimerId = null;
        }
    }, 1000);
}

function syncOtpDigitFilledClasses() {
    document.querySelectorAll('.otp-digit').forEach((input) => {
        input.classList.toggle('otp-digit--filled', input.value.length > 0);
    });
}

function backToEmail() {
    stopOtpExpiryTimer();
    if (resendTimerId) {
        clearInterval(resendTimerId);
        resendTimerId = null;
    }
    resendCountdown = 0;
    otpExpired = false;
    setOtpInputsEnabled(true);
    showStep('email-step');
    document.getElementById('email').focus();
}

function setCarouselLocked(locked) {
    const prev = document.getElementById('login-mode-prev');
    const next = document.getElementById('login-mode-next');
    const dots = document.querySelectorAll('.login-carousel-dot');
    const slides = document.querySelectorAll('.login-carousel-slide');
    const aside = document.querySelector('.login-aside');

    if (prev) { prev.disabled = locked; prev.setAttribute('aria-disabled', locked); }
    if (next) { next.disabled = locked; next.setAttribute('aria-disabled', locked); }
    dots.forEach(d => { d.disabled = locked; d.setAttribute('aria-disabled', locked); });
    slides.forEach(s => { s.style.pointerEvents = locked ? 'none' : ''; });
    if (aside) aside.classList.toggle('login-aside--locked', locked);
}

function showStep(stepId) {
    document.querySelectorAll('.login-step').forEach((step) => {
        step.classList.remove('active');
    });

    document.getElementById(stepId).classList.add('active');

    const loginPage = document.querySelector('.login-page');
    if (loginPage) {
        loginPage.classList.toggle('login-page--otp', stepId === 'otp-step');
    }

    const isOtp = stepId === 'otp-step';
    setCarouselLocked(isOtp);

    if (isOtp) {
        const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));
        otpInputs.forEach((input) => {
            input.value = '';
            input.classList.remove('otp-digit--filled');
        });
        if (otpInputs.length > 0) {
            otpInputs[0].focus();
        }
    }
}

function showError(errorElement, message, type = 'error') {
    errorElement.textContent = message;
    errorElement.classList.remove('error-message--success', 'error-message--warning');
    errorElement.classList.add('show');

    let autoHideMs = 0;
    if (type === 'success') {
        errorElement.classList.add('error-message--success');
        autoHideMs = 3000;
    } else if (type === 'warning') {
        errorElement.classList.add('error-message--warning');
        autoHideMs = 12000;
    }

    if (autoHideMs > 0) {
        setTimeout(() => {
            errorElement.classList.remove('show', 'error-message--success', 'error-message--warning');
        }, autoHideMs);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    initLoginCarousel();

    const otpInputs = Array.from(document.querySelectorAll('.otp-digit'));

    function checkAndAutoSubmitOtp() {
        if (otpExpired) return;
        const otpValues = otpInputs.map((input) => input.value).join('');
        if (otpValues.length === 6 && /^\d{6}$/.test(otpValues)) {
            setTimeout(() => {
                const otpForm = document.getElementById('otp-form');
                if (otpForm && !otpExpired) {
                    otpForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            }, 300);
        }
    }

    if (otpInputs.length > 0) {
        otpInputs.forEach((input, index) => {
            input.addEventListener('input', function () {
                if (otpExpired || this.disabled) {
                    this.value = '';
                    return;
                }
                this.value = this.value.replace(/[^0-9]/g, '').slice(0, 1);
                this.classList.toggle('otp-digit--filled', this.value.length > 0);
                if (this.value && index < otpInputs.length - 1) {
                    otpInputs[index + 1].focus();
                }
                checkAndAutoSubmitOtp();
            });

            input.addEventListener('keydown', function (event) {
                if (otpExpired || this.disabled) {
                    event.preventDefault();
                    return;
                }
                if (/^Numpad[0-9]$/.test(event.code)) {
                    const digit = event.code.replace('Numpad', '');
                    this.value = digit;
                    this.classList.toggle('otp-digit--filled', true);
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
                    this.classList.toggle('otp-digit--filled', true);
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
                if (otpExpired || this.disabled) {
                    event.preventDefault();
                    return;
                }
                event.preventDefault();
                const pasted = (event.clipboardData || window.clipboardData)
                    .getData('text')
                    .replace(/[^0-9]/g, '')
                    .slice(0, otpInputs.length);

                for (let i = 0; i < otpInputs.length; i++) {
                    otpInputs[i].value = pasted[i] || '';
                }
                syncOtpDigitFilledClasses();

                const focusIndex = Math.min(pasted.length, otpInputs.length - 1);
                otpInputs[focusIndex].focus();

                checkAndAutoSubmitOtp();
            });
        });
    }
});
