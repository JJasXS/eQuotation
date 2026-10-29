# OTP Configuration
import secrets
import string

# OTP Settings
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 120  # 2 minutes — inputs lock on client when this hits 0
OTP_RESEND_COOLDOWN_SECONDS = 30  # resend button cooldown
OTP_MAX_VERIFY_ATTEMPTS = 5  # lock out after this many wrong codes within expiry
OTP_CHARS = string.digits  # Only numeric

def generate_otp(length=OTP_LENGTH):
    """Generate a cryptographically strong numeric OTP."""
    return ''.join(secrets.choice(OTP_CHARS) for _ in range(length))
