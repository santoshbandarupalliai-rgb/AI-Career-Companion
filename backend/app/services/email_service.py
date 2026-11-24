"""Outgoing email (SMTP). Used for verification links.

With no SMTP_HOST configured nothing is sent: the message is written to the server log instead, so
development and demos work without an email account. Sending failures are logged and never raised
into a request.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(get_settings().smtp_host)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one email. Returns True if it was handed to the SMTP server, False otherwise."""
    s = get_settings()
    if not s.smtp_host:
        log.info("SMTP is not configured; email '%s' was not sent. Message body:\n%s", subject, text)
        return False
    sender = s.smtp_from or s.smtp_user
    if not sender:
        log.error("SMTP_FROM or SMTP_USER must be set to send email")
        return False
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        ctx = ssl.create_default_context()
        if s.smtp_ssl:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=ctx)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        with server:
            if not s.smtp_ssl and s.smtp_starttls:
                server.starttls(context=ctx)
            if s.smtp_user:
                server.login(s.smtp_user, s.smtp_password)
            server.send_message(msg)
        log.info("email sent subject=%r", subject)
        return True
    except Exception as exc:  # network, auth, refused recipient...
        detail = str(exc).replace(s.smtp_password, "***") if s.smtp_password else str(exc)
        log.error("sending email failed: %s: %s", type(exc).__name__, detail[:200])
        return False


def verification_link(token: str) -> str:
    s = get_settings()
    base = (s.app_base_url or s.frontend_origin).rstrip("/")
    return f"{base}/verify-email?token={token}"


def send_verification_email(to: str, full_name: str, token: str) -> bool:
    link = verification_link(token)
    hours = get_settings().verification_token_hours
    text = (
        f"Hi {full_name},\n\n"
        "Welcome to AI Career Companion. Please confirm your email address by opening this link:\n\n"
        f"{link}\n\n"
        f"The link works for {hours} hours. If you did not create an account, you can ignore this email.\n"
    )
    html = (
        f"<p>Hi {full_name},</p><p>Welcome to AI Career Companion. Please confirm your email address:</p>"
        f'<p><a href="{link}">Verify my email</a></p>'
        f"<p>The link works for {hours} hours. If you did not create an account, you can ignore this email.</p>"
    )
    return send_email(to, "Verify your email for AI Career Companion", text, html)
