"""Email utility functions."""
import os
import smtplib
import ssl
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


def _smtp_socket_timeout_seconds() -> float:
    """Upper bound for connect/read so OTP HTTP requests do not hang indefinitely (env ``SMTP_TIMEOUT``, default 25)."""
    raw = (os.getenv("SMTP_TIMEOUT") or "25").strip()
    try:
        v = float(raw)
    except ValueError:
        v = 25.0
    return max(5.0, min(v, 120.0))


def _coerce_smtp_port(port) -> int:
    try:
        p = int(port)
        return p if p > 0 else 587
    except (TypeError, ValueError):
        return 587


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

        port = _coerce_smtp_port(SMTP_PORT)
        tmo = _smtp_socket_timeout_seconds()
        host = (SMTP_SERVER or "").strip()
        print(f"[EMAIL] SMTP {host!r} port={port} timeout={tmo}s (implicit TLS on 465, STARTTLS on 587)", flush=True)

        # Port 465 expects implicit TLS (same as MailKit SslOnConnect / ApprovalPO); STARTTLS on 465 can hang or fail.
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=tmo, context=ctx) as server:
                server.login(smtp_email, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=tmo) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(smtp_email, smtp_password)
                server.send_message(msg)
        print(f"Email sent successfully to {to_email}", flush=True)
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
    except (TimeoutError, OSError) as e:
        low = str(e).lower()
        if "timed out" in low or isinstance(e, TimeoutError):
            print(
                f"[EMAIL] SMTP timed out (limit {_smtp_socket_timeout_seconds()}s) connecting to "
                f"{SMTP_SERVER!r}:{_coerce_smtp_port(SMTP_PORT)} — check firewall, host, port (587 vs 465), "
                f"or set SMTP_TIMEOUT in the environment.",
                flush=True,
            )
        else:
            print(f"[EMAIL] SMTP network error: {e}", flush=True)
        return False
    except Exception as e:
        print(f"Failed to send email: {e}", flush=True)
        return False
