# Complete Login System - Testing Guide

## System Overview

Your chatbot now has a complete authentication system with:
- ✅ Email + OTP two-step login
- ✅ Session-based authentication
- ✅ Protected routes (requires login)
- ✅ Logout functionality
- ✅ In-memory OTP storage with expiry

## Quick Start Testing

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Gmail (SMTP)
Before testing, set up Gmail app password:

1. Go to [Google Account](https://myaccount.google.com/security)
2. Enable 2-Factor Authentication (if not already enabled)
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Select "Mail" and "Windows Computer"
5. Copy the 16-character app password

### 3. Update .env File
```env
FLASK_SECRET_KEY=your-super-secret-key-12345

# Gmail SMTP Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
```

### 4. Run Flask Application
```bash
python main.py
```

You should see:
```
Starting Flask web server at http://localhost:5000 ...
```

### 5. Test Login Flow

#### Step 1: Access Login Page
- Open browser: `http://localhost:5000`
- You should see the login page (if not authenticated)
- No redirect should occur

#### Step 2: Send OTP
- Enter your email (e.g., `your-email@gmail.com`)
- Click "Continue"
- Expected: "Sending OTP..." button state
- Check email inbox for OTP code

#### Step 3: Verify OTP
- Copy the 6-digit code from email
- Enter in the OTP field (auto-formats)
- Click "Verify"
- Expected: Redirected to `/chat` page

#### Step 4: Use Chat
- You should see the chat interface
- All chat, order, and message features should work
- Session is active for 7 days

#### Step 5: Logout
- Click hamburger menu (top-left)
- Look for "Logout" or reload and click logout
- You should be redirected to login page

## Testing Scenarios

### Scenario 1: Invalid Email
**Input:** `invalid-email`
**Expected:** Error message: "Please enter a valid email"
**Status:** ✅

### Scenario 2: Email Not Found (First Time)
**Input:** `newemail@example.com`
**Expected:** OTP sent, user receives email
**Duration:** 10 minutes to use OTP
**Status:** ✅

### Scenario 3: Wrong OTP
**Input:** Correct email, wrong 6-digit code
**Expected:** Error message: "Invalid OTP. Please try again."
**Status:** ✅

### Scenario 4: Expired OTP
**Input:** Valid email, wait 11 minutes, use same OTP
**Expected:** Error message: "OTP has expired. Request a new one."
**Status:** ✅

### Scenario 5: Resend OTP
**Input:** Click "Resend OTP" before 30-second cooldown
**Expected:** Button disabled, countdown displayed
**Status:** ✅

**Input:** Click "Resend OTP" after 30 seconds
**Expected:** OTP resent, countdown resets
**Status:** ✅

### Scenario 6: Unauthorized Access
**URL:** `http://localhost:5000/chat` (without authentication)
**Expected:** Redirect to `/login`
**Status:** ✅

**API:** `GET /get_chats` (without session)
**Expected:** Returns `{success: false, error: 'Unauthorized'}` with 401 status
**Status:** ✅

### Scenario 7: Session Persistence
**Steps:**
1. Login successfully
2. Reload browser page
3. Perform chat action
**Expected:** Session persists, all features work
**Status:** ✅

## Console Testing (No Email Configured)

If you don't configure SMTP, the system will print OTPs to console:

```
WARNING: SMTP_EMAIL or SMTP_PASSWORD not configured. Using console output for debugging.
Email would be sent to: user@example.com
Subject: Your Login OTP Code
Body:
...
```

**To test:**
1. Remove or comment out `SMTP_EMAIL` and `SMTP_PASSWORD` in `.env`
2. Run Flask app `python main.py`
3. Try to send OTP
4. Check Flask console for printed OTP
5. Use that OTP to verify login

## API Testing with curl/Postman

### Test /api/send_otp
```bash
curl -X POST http://localhost:5000/api/send_otp \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com"}'
```

**Expected Response:**
```json
{
  "success": true,
  "message": "OTP sent to user@example.com",
  "expiry": 600
}
```

### Test /api/verify_otp
```bash
curl -X POST http://localhost:5000/api/verify_otp \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","otp":"123456"}'
```

**Expected Response (Success):**
```json
{
  "success": true,
  "message": "Login successful",
  "redirect": "/chat"
}
```

**Expected Response (Invalid OTP):**
```json
{
  "success": false,
  "error": "Invalid OTP. Please try again."
}
```

### Test Protected Route (Without Session)
```bash
curl -X GET http://localhost:5000/get_chats
```

**Expected Response:**
```json
{
  "success": false,
  "error": "Unauthorized"
}
```

HTTP Status: `401`

### Test Protected Route (With Session)
First, login via browser to create session cookie, then:

```bash
curl -X GET http://localhost:5000/get_chats \
  -H "Cookie: session=your-session-cookie"
```

**Expected Response:**
```json
{
  "success": true,
  "chats": [...]
}
```

## Browser DevTools Testing

### Check Session Cookie
1. Open Chrome/Firefox DevTools (F12)
2. Go to Application → Cookies → http://localhost:5000
3. Look for `session` cookie
4. Verify properties:
   - ✅ HttpOnly: Yes (not accessible via JavaScript)
   - ✅ Secure: No (set to Yes in production with HTTPS)
   - ✅ SameSite: Lax

### Check Network Requests
1. Open DevTools Network tab
2. Login successfully
3. Perform chat action
4. Inspect `/chat` POST request:
   - Request Headers should include session cookie
   - Response should return 200 (not 401)

### Check Console for Redirects
1. Open DevTools Console
2. Try accessing `/get_chat_details` without authentication (simulate)
3. Should see console message: "Unauthorized - redirecting to login"

## Troubleshooting

### Issue: "SMTP error: 535"
**Cause:** Gmail rejected credentials
**Solution:**
1. Verify you enabled 2FA on Gmail
2. Delete previous app password, create new one
3. Copy exact 16-character password (no spaces)
4. Restart Flask app

### Issue: Email not received
**Cause:** SMTP configuration issue
**Solution:**
1. Check Flask console for error messages
2. Verify SMTP_EMAIL and SMTP_PASSWORD in .env
3. Test SMTP with Python directly:
   ```python
   import smtplib
   server = smtplib.SMTP('smtp.gmail.com', 587)
   server.starttls()
   server.login('your-email@gmail.com', 'app-password')
   print("SMTP Connection OK")
   ```

### Issue: OTP keeps saying "Invalid OTP"
**Cause:** OTP expired or wrong code
**Solution:**
1. Resend OTP
2. Use immediately (600 seconds = 10 minutes)
3. Check Flask console output if SMTP not configured

### Issue: Can't access /chat after login
**Cause:** Session not created
**Solution:**
1. Check that `/api/verify_otp` returns `redirect: /chat`
2. Verify browser cookies are enabled
3. Check Flask console for errors
4. Restart Flask app and try again

### Issue: "FLASK_SECRET_KEY environment variable is not set"
**Cause:** Missing FLASK_SECRET_KEY in .env
**Solution:**
```env
FLASK_SECRET_KEY=generate-a-random-string-here
```

Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Performance Testing

### Load Test OTP Generation
```python
# test_otp_generation.py
from config.otp_config import generate_otp
import time

start = time.time()
for i in range(10000):
    otp = generate_otp(6)
end = time.time()
print(f"Generated 10000 OTPs in {end-start:.2f} seconds")
```

Expected: < 0.1 seconds

### Session Memory Usage
```python
# Test OTP_STORAGE size with 1000 concurrent OTPs
len(OTP_STORAGE)  # Should be manageable in memory
```

For production with >1000 concurrent users, migrate to database or Redis.

## Security Testing

### Test Session Timeout
1. Login successfully
2. Wait for 7+ days (or modify in code to 10 seconds for testing)
3. Try to send message
4. Expected: Redirect to login

### Test CSRF Protection
With `SESSION_COOKIE_SAMESITE = 'Lax'`, cross-site form submissions are blocked.

### Test Cookie Stealing
1. Login and get session cookie
2. Verify `HttpOnly` flag is set
3. JavaScript `document.cookie` should NOT show session cookie
4. Only server can access it (protection against XSS)

## Migration Checklist

Before deploying to production:

- [ ] Generate new `FLASK_SECRET_KEY`
- [ ] Set `SESSION_COOKIE_SECURE = True` (requires HTTPS)
- [ ] Use production email service (SendGrid/Mailgun)
- [ ] Migrate OTP storage from in-memory to database
- [ ] Set `FLASK_ENV=production`
- [ ] Set `FLASK_DEBUG=False`
- [ ] Configure HTTPS/SSL certificate
- [ ] Test email delivery in production
- [ ] Set up logging for auth events
- [ ] Test logout functionality
- [ ] Verify session timeout settings

## Next Steps

### Optional Enhancements

1. **Rate Limiting** - Prevent brute force OTP attempts
   ```python
   from flask_limiter import Limiter
   limiter = Limiter(app, key_func=lambda: request.remote_addr)
   ```

2. **Password Reset** - Add forgot password flow
   ```python
   @app.route('/forgot_password', methods=['POST'])
   def forgot_password():
       # Send password reset link
       pass
   ```

3. **Multi-device Sessions** - Allow logout from all devices
4. **Login Audit Log** - Track all login attempts
5. **2FA Method Options** - SMS, authenticator app, etc.

## Contact & Support

For issues or questions, check:
1. Flask console for error messages
2. Browser DevTools Network tab for HTTP status codes
3. Browser DevTools Application tab for session cookie
4. .env file for correct configuration

