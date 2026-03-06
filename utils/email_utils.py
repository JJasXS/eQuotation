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
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
