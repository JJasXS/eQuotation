# OTP Configuration
import random
import string

# OTP Settings
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 60  # 1 minute
OTP_CHARS = string.digits  # Only numeric

def generate_otp(length=OTP_LENGTH):
    """Generate a random OTP"""
    return ''.join(random.choice(OTP_CHARS) for _ in range(length))
