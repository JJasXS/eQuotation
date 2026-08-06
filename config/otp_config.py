# OTP Configuration
import random
import string

# OTP Settings
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 120  # 2 minutes — inputs lock on client when this hits 0
OTP_RESEND_COOLDOWN_SECONDS = 30  # resend button cooldown
OTP_CHARS = string.digits  # Only numeric

def generate_otp(length=OTP_LENGTH):
    """Generate a random OTP"""
    return ''.join(random.choice(OTP_CHARS) for _ in range(length))
