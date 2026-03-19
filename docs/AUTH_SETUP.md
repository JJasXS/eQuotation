# Authentication Setup Guide

## Overview
The login system now includes email-based OTP (One-Time Password) authentication. This guide explains how to configure the email service for OTP delivery.

## Features Implemented
✅ Login page with two-step verification (email → OTP)
✅ 6-digit OTP code generation
✅ 10-minute OTP expiry
✅ Session management
✅ Protected routes (required authentication)
✅ Logout functionality

## Configuration Steps

### 1. Generate Flask Secret Key
Update your `.env` file with a secure secret key:

```env
FLASK_SECRET_KEY=generate-a-secure-random-key-here
```

To generate a secure key in Python:
```python
import secrets
print(secrets.token_urlsafe(32))
```

### 2. Choose Email Service

#### Option A: Gmail (Recommended for Development)

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Factor Authentication
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Select "Mail" and "Windows Computer"
5. Copy the generated 16-character app password
6. Update `.env`:

```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
```

#### Option B: Outlook/Office365

```env
SMTP_SERVER=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_EMAIL=your-email@outlook.com
SMTP_PASSWORD=your-outlook-password
```

#### Option C: SendGrid (Best for Production)

1. Sign up at [SendGrid](https://sendgrid.com)
2. Create an API key
3. Update main.py to use SendGrid instead of SMTP:

```env
SENDGRID_API_KEY=your-sendgrid-api-key
SMTP_EMAIL=noreply@yourdomain.com
```

Update the `send_email()` function in main.py to use SendGrid API.

#### Option D: Mailgun (Alternative)

1. Sign up at [Mailgun](https://www.mailgun.com)
2. Create an API key
3. Update `.env`:

```env
MAILGUN_API_KEY=your-mailgun-api-key
MAILGUN_DOMAIN=your-domain.mailgun.org
SMTP_EMAIL=noreply@your-domain.mailgun.org
```

## API Endpoints

### POST /api/send_otp
**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "OTP sent to user@example.com",
  "expiry": 600
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Invalid email format"
}
```

### POST /api/verify_otp
**Request:**
```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Login successful",
  "redirect": "/chat"
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Invalid OTP"
}
```

## Routes

### Public Routes
- `GET /login` - Login page
- `POST /api/send_otp` - Send OTP to email
- `POST /api/verify_otp` - Verify OTP and create session

### Protected Routes (Requires Authentication)
- `GET /` - Redirects to /chat if authenticated, /login if not
- `GET /chat` - Chat interface
- `POST /chat` - Send message
- `GET /get_chats` - List all chats
- `GET /get_chat_details` - Get chat history
- `POST /api/insert_chat` - Create new chat
- `GET /api/get_active_order` - Get active order
- `POST /api/check_draft_order` - Check for draft orders
- `GET /logout` - Logout and clear session

## Security Features

✅ Session-based authentication with secure cookies
✅ OTP expiry validation (10 minutes)
✅ Email validation regex
✅ HTTPONLY cookies (no JavaScript access)
✅ SAMESITE=Lax for CSRF protection
✅ Temporary OTP storage (automatically cleaned up)

## Testing

### Test with Gmail (Development)
1. Set up Gmail app password (see Option A above)
2. Update `.env` with your credentials
3. Start the Flask app: `python main.py`
4. Visit `http://localhost:5000/login`
5. Enter your email
6. Check your Gmail inbox for OTP
7. Enter the 6-digit code

### Console Logging (If No Email Service Configured)
If `SMTP_EMAIL` and `SMTP_PASSWORD` are not set, the system will print OTPs to console for debugging:

```
WARNING: SMTP_EMAIL or SMTP_PASSWORD not configured. Using console output for debugging.
Email would be sent to: user@example.com
Subject: Your Login OTP Code
Body: ...
```

## Troubleshooting

### "SMTP error: 535"
Gmail rejected your password. Make sure you:
1. Have 2FA enabled
2. Used an App Password (not your regular password)
3. Have the correct 16-character app password

### "Connection refused"
1. Check SMTP_SERVER and SMTP_PORT are correct
2. Verify your firewall allows outbound SMTP
3. Try port 465 instead of 587 (requires SSL)

### "OTP sent but not receiving emails"
1. Check email address is valid
2. Check spam/junk folder
3. Verify SMTP credentials in `.env`
4. Check Flask console for error messages

## Environment Variables Reference

```env
# Flask Session Security
FLASK_SECRET_KEY=your-secure-random-key

# SMTP Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your-email@domain.com
SMTP_PASSWORD=your-app-specific-password
```

## Session Configuration

- **Session Duration:** 7 days (configurable in main.py)
- **Cookie Secure:** Disabled for development (enable for HTTPS in production)
- **Cookie HttpOnly:** Enabled (JavaScript cannot access)
- **Cookie SameSite:** Lax (basic CSRF protection)

## Production Checklist

Before deploying to production:

- [ ] Generate new `FLASK_SECRET_KEY`
- [ ] Set `SESSION_COOKIE_SECURE = True` (requires HTTPS)
- [ ] Use production email service (SendGrid/Mailgun recommended)
- [ ] Set `FLASK_ENV=production`
- [ ] Set `FLASK_DEBUG=False`
- [ ] Test email delivery
- [ ] Set up logs for authentication events
- [ ] Configure HTTPS/SSL certificate
- [ ] Test logout functionality
- [ ] Verify session timeout

## OTP Storage

Currently, OTPs are stored in-memory (`OTP_STORAGE` dict). For production with multiple workers:

**Option A: Database Storage** (Recommended)
```sql
CREATE TABLE AUTH_CODES (
  ID INT PRIMARY KEY AUTO_INCREMENT,
  EMAIL VARCHAR(255),
  OTP VARCHAR(10),
  EXPIRY TIMESTAMP,
  CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Option B: Redis**
```python
import redis
r = redis.Redis()
r.setex(f"otp:{email}", 600, otp)  # Expires in 10 minutes
```

**Option C: Memcached**
```python
import memcache
mc = memcache.Client()
mc.set(f"otp:{email}", otp, time=600)
```

## User Management

Current implementation doesn't require a user table. Any email can proceed in the current flow-testing setup.

## Support

For issues or questions:
1. Check Flask console output for error messages
2. Verify `.env` configuration
3. Test email manually with Python's smtplib
4. Check firewall/network connectivity
