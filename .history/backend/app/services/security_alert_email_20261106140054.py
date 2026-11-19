"""Dormora File 73: build and send lockout security-alert emails.

Create: backend/app/services/security_alert_email.py
Use trusted account/audit data, never a browser-supplied recipient or URL.
The integration layer must send once per newly reached lockout tier and record
ALERT_EMAIL_SENT after SMTP acceptance. This module does not do database writes,
retry delivery, enable routes, or implement password-change alerts yet.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import EmailStr, TypeAdapter

from app.core.config import settings
from app.services.email_service import EmailDeliveryError

_EMAIL = TypeAdapter(EmailStr)
_PHT = timezone(timedelta(hours=8), name="PHT")
_TIER_FAILURES = {1: 3, 2: 6, 3: 9}


@dataclass(frozen=True)
class LockoutAlert:
    """Internal data from the actual lockout event; do not serialize to HTTP."""
    email_address: str = field(repr=False)
    tier: int
    occurred_at: datetime
    client_ip: str = field(repr=False)
    user_agent: str | None = field(default=None, repr=False)


def _recovery_url(frontend_origin: str) -> str:
    """Use only the configured frontend origin and the existing recovery route."""
    if not isinstance(frontend_origin, str) or any(ch.isspace() for ch in frontend_origin):
        raise ValueError("Invalid frontend origin.")
    parsed = urlsplit(frontend_origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Invalid frontend origin.")
    # Validate the port too; urlsplit otherwise defers this check.
    parsed.port
    if parsed.scheme == "http" and (
        settings.environment == "production"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("HTTPS is required outside local development.")
    return frontend_origin.rstrip("/") + "/forgot-password"


def build_lockout_alert_email(
    alert: LockoutAlert, *, sender_email: str,
    frontend_origin: str, sender_name: str = "Dormora",
) -> EmailMessage:
    """Build a plain-text message without network or database operations."""
    if type(alert.tier) is not int or alert.tier not in _TIER_FAILURES:
        raise ValueError("Invalid lockout tier.")
    if (not isinstance(alert.occurred_at, datetime)
            or alert.occurred_at.tzinfo is None
            or alert.occurred_at.utcoffset() is None):
        raise ValueError("Lockout time must be timezone-aware.")
    if (not isinstance(sender_name, str) or not sender_name.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in sender_name)):
        raise ValueError("Invalid sender name.")
    if not isinstance(alert.client_ip, str):
        raise ValueError("A trusted IP address is required.")
    client_ip = str(ip_address(alert.client_ip))
    recipient = str(_EMAIL.validate_python(alert.email_address))
    sender = str(_EMAIL.validate_python(sender_email))
    recovery_url = _recovery_url(frontend_origin)
    # User-Agent is untrusted descriptive text, not a verified device identity.
    agent = "Not provided"
    if isinstance(alert.user_agent, str):
        agent = "".join(ch for ch in alert.user_agent if ch.isprintable())[:255] or agent
    occurred = alert.occurred_at.astimezone(_PHT).strftime("%d %B %Y, %I:%M:%S %p PHT")
    message = EmailMessage()
    message["From"] = Address(display_name=sender_name.strip(), addr_spec=sender)
    message["To"] = recipient
    message["Subject"] = "Failed sign-in attempts on your Dormora account"
    message.set_content(
        "Dormora security alert\n\n"
        "Your account reached a temporary sign-in lockout.\n"
        f"Consecutive failed attempts: {_TIER_FAILURES[alert.tier]}\n"
        f"Lockout tier: {alert.tier}\n"
        f"Date and time: {occurred}\n"
        f"IP address: {client_ip}\n"
        f"Browser/device (reported User-Agent): {agent}\n\n"
        "If this was not you, reset your password now:\n"
        f"{recovery_url}\n\n"
        "If these attempts were yours, wait for the lockout countdown to finish "
        "before trying again.\n"
        "Dormora will never ask you to reply with your password or OTP.\n"
    )
    return message


def send_lockout_alert_email(alert: LockoutAlert) -> None:
    """SMTP acceptance only; caller handles once-per-tier dispatch and audit.

    Never reveal delivery success/failure on the login page. Do not automatically
    retry uncertain SMTP failures, which could send the same alert twice.
    """
    settings.require_smtp_configuration()
    if settings.smtp_security not in {"ssl", "starttls"}:
        raise RuntimeError("Encrypted SMTP is required.")
    message = build_lockout_alert_email(
        alert, sender_email=str(settings.smtp_from_email),
        sender_name=settings.smtp_from_name, frontend_origin=settings.frontend_origin,
    )
    sender = str(_EMAIL.validate_python(str(settings.smtp_from_email)))
    recipient = str(_EMAIL.validate_python(alert.email_address))
    password = settings.smtp_password.get_secret_value()
    context = ssl.create_default_context()
    accepted = False
    try:
        if settings.smtp_security == "ssl":
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port,
                timeout=settings.smtp_timeout_seconds, context=context,
            ) as client:
                client.login(settings.smtp_username, password)
                refused = client.send_message(message, from_addr=sender, to_addrs=[recipient])
                if refused:
                    raise EmailDeliveryError("Security alert email could not be sent.")
                accepted = True
        else:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as client:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
                client.login(settings.smtp_username, password)
                refused = client.send_message(message, from_addr=sender, to_addrs=[recipient])
                if refused:
                    raise EmailDeliveryError("Security alert email could not be sent.")
                accepted = True
    except (smtplib.SMTPException, OSError):
        if not accepted:
            raise EmailDeliveryError("Security alert email could not be sent.") from None