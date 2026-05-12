"""Email utility functions."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _smtp_auth_failure_console_fallback_allowed() -> bool:
    """When True, SMTP auth errors fall back to console logging and return success (local dev)."""
    if (os.getenv("SMTP_AUTH_FAILURE_NO_FALLBACK") or "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if (os.getenv("SMTP_AUTH_FAILURE_CONSOLE_OK") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    env = (os.getenv("FLASK_ENV") or os.getenv("FLASK_DEBUG") or "").strip().lower()
    return env in ("development", "dev", "local", "1", "true")


def _log_email_console(to_email: str, subject: str, body: str, *, label: str) -> None:
    print(f"[EMAIL {label}] (not sent via SMTP) to={to_email}", flush=True)
    print(f"[EMAIL {label}] subject={subject}", flush=True)
    print(f"[EMAIL {label}] body:\n{body}", flush=True)


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
        print(
            "WARNING: SMTP_EMAIL or SMTP_PASSWORD not configured. Using console output for debugging.",
            flush=True,
        )
        _log_email_console(to_email, subject, body, label="DRY_RUN")
        return True
    
    # Gmail app passwords are often pasted with spaces; SMTP accepts the 16 chars without them.
    smtp_email = (SMTP_EMAIL or "").strip()
    smtp_password = (SMTP_PASSWORD or "").strip()
    if "gmail.com" in (SMTP_SERVER or "").lower():
        smtp_password = smtp_password.replace(" ", "")

    try:
        msg = MIMEMultipart()
        sender_name = (
            (os.getenv("SMTP_SENDER_NAME") or os.getenv("EmailSettings__SenderName") or "").strip()
        )
        if sender_name:
            msg["From"] = f"{sender_name} <{smtp_email}>"
        else:
            msg["From"] = smtp_email
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
        elif "535" in str(e) or "5.7.8" in err or "badcredentials" in err:
            hint = (
                " Gmail (5.7.8 / 535): wrong SMTP user or password — use an App Password for the same "
                "account as EmailSettings:SmtpUser (or SMTP_EMAIL), not your normal login password."
            )
        if _smtp_auth_failure_console_fallback_allowed():
            print(
                f"[EMAIL] SMTP login rejected.{hint} "
                "Console fallback is enabled (development / SMTP_AUTH_FAILURE_CONSOLE_OK): "
                "logging the message here and returning success so OTP flow continues.",
                flush=True,
            )
            _log_email_console(to_email, subject, body, label="AUTH_FAIL_FALLBACK")
            return True
        print(f"Failed to send email: {e}{hint}", flush=True)
        return False
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
