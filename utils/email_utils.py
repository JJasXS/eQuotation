"""Email utility functions."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email configuration (will be set from main.py)
SMTP_SERVER = None
SMTP_PORT = None
SMTP_EMAIL = None
SMTP_PASSWORD = None


def set_email_config(smtp_server, smtp_port, smtp_email, smtp_password):
    """Set email configuration."""
    global SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD
    SMTP_SERVER = smtp_server
    SMTP_PORT = smtp_port
    SMTP_EMAIL = smtp_email
    SMTP_PASSWORD = smtp_password


def send_email(to_email, subject, body):
    """Send email using SMTP."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("WARNING: SMTP_EMAIL or SMTP_PASSWORD not configured. Using console output for debugging.")
        print(f"Email would be sent to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        return True
    
    # Gmail app passwords are often pasted with spaces; SMTP accepts the 16 chars without them.
    smtp_email = (SMTP_EMAIL or "").strip()
    smtp_password = (SMTP_PASSWORD or "").strip()
    if "gmail.com" in (SMTP_SERVER or "").lower():
        smtp_password = smtp_password.replace(" ", "")

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        err = str(e).lower()
        hint = ""
        if "534" in str(e) or "5.7.9" in err or "webloginrequired" in err:
            hint = (
                " Gmail (5.7.9 / 534): enable 2-Step Verification, create an App Password "
                "(Google Account → Security → App passwords), set SMTP_PASSWORD to that 16-character value "
                "(not your normal password). If it still fails, open "
                "https://accounts.google.com/DisplayUnlockCaptcha while signed in as the sender account."
            )
        print(f"Failed to send email: {e}{hint}")
        return False
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
