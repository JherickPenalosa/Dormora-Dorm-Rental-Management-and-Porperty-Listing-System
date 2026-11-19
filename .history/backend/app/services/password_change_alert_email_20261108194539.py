
"""Dormora File 107: email notification for an ALREADY committed password change.

CREATE: backend/app/services/password_change_alert_email.py

This is a mail-construction/delivery service, not a FastAPI route. Only a
trusted post-commit password-change workflow may call the sender with the
verified account's database email. Never accept a recipient from browser JSON.

- Use existing encrypted SMTP settings; no credentials are hard-coded.
- Include event time in Philippine time, server-observed IP, and User-Agent.
- Never include the password, its hash, or a session/OTP token in the email.
- SMTP success means provider acceptance, not inbox delivery.
- Do not silently retry uncertain SMTP failures: duplicates can result.
- The integration layer must write ALERT_EMAIL_SENT only AFTER SMTP acceptance.
- This module alone does not send an email or complete the instructor criterion.
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


@dataclass(frozen=True, slots=True)
class PasswordChangedAlert:
    """Trusted event data supplied after a committed password change."""

    email_address: str = field(repr=False)
    changed_at: datetime
    client_ip: str = field(repr=False)
    user_agent: str | None = field(default=None, repr=False)


def _recovery_url(frontend_origin: str) -> str:
    """Construct a fixed recovery link from trusted application config only."""
    if not isinstance(frontend_origin, str) or any(
        ch.isspace() or ord(ch) < 32 for ch in frontend_origin
    ):
        raise ValueError("Invalid frontend origin.")
    parsed = urlsplit(frontend_origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid frontend origin.")
    # Force validation of the port field; urlsplit can defer some failures.
    parsed.port
    if parsed.scheme == "http" and (
        settings.environment != "development"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("HTTPS required outside local development.")
    return frontend_origin.rstrip("/") + "/forgot-password"


def build_password_changed_email(
    alert: PasswordChangedAlert,
    *,
    sender_email: str,
    frontend_origin: str,
    sender_name: str = "Dormora",
) -> EmailMessage:
    """Build a safe, text-only email; no SMTP call or database write."""
    if not isinstance(alert, PasswordChangedAlert):
        raise TypeError("A trusted password-change event is required.")
    if (
        not isinstance(alert.changed_at, datetime)
        or alert.changed_at.tzinfo is None
        or alert.changed_at.utcoffset() is None
    ):
        raise ValueError("Change time must include a timezone.")
    if (
        not isinstance(sender_name, str)
        or not sender_name.strip()
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in sender_name)
    ):
        raise ValueError("Invalid sender name.")
    # These are supplied by trusted server configuration and verified DB rows.
    sender = str(_EMAIL.validate_python(sender_email))
    recipient = str(_EMAIL.validate_python(alert.email_address))
    server_ip = str(ip_address(alert.client_ip))
    recovery_url = _recovery_url(frontend_origin)
    agent = "Not provided"
    if isinstance(alert.user_agent, str):
        agent = "".join(ch for ch in alert.user_agent if ch.isprintable())[:255] or agent
    changed = alert.changed_at.astimezone(_PHT).strftime(
        "%d %B %Y, %I:%M:%S %p PHT"
    )

    message = EmailMessage()
    message["From"] = Address(display_name=sender_name.strip(), addr_spec=sender)
    message["To"] = recipient
    message["Subject"] = "Your Dormora password was changed"
    message.set_content(
        "Dormora account security notice\n\n"
        "The password for your Dormora account was changed successfully.\n\n"
        f"Date and time: {changed}\n"
        f"IP address: {server_ip}\n"
        f"Browser/device (reported User-Agent): {agent}\n\n"
        "If you made this change, no action is needed.\n"
        "If this was not you, reset your password immediately:\n"
        f"{recovery_url}\n\n"
        "All existing Dormora sessions were signed out during the change.\n"
        "Dormora will never ask you to reply with a password or OTP.\n"
    )
    return message


def send_password_changed_alert_email(alert: PasswordChangedAlert) -> None:
    """Deliver the alert via TLS-protected SMTP; raise on non-acceptance.

    Call only AFTER the password-change transaction commits. A notification
    failure must not roll back or misrepresent a password update that committed.
    Caller records ALERT_EMAIL_SENT only after this method returns normally.
    """
    settings.require_smtp_configuration()
    if settings.smtp_security not in {"ssl", "starttls"}:
        raise RuntimeError("Encrypted SMTP is required.")

    message = build_password_changed_email(
        alert,
        sender_email=str(settings.smtp_from_email),
        sender_name=settings.smtp_from_name,
        frontend_origin=settings.frontend_origin,
    )
    sender = str(_EMAIL.validate_python(str(settings.smtp_from_email)))
    recipient = str(_EMAIL.validate_python(alert.email_address))
    smtp_password = settings.smtp_password.get_secret_value()
    tls_context = ssl.create_default_context()
    try:
        if settings.smtp_security == "ssl":
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=tls_context,
            ) as client:
                client.login(settings.smtp_username, smtp_password)
                refused = client.send_message(
                    message, from_addr=sender, to_addrs=[recipient]
                )
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as client:
                client.ehlo()
                client.starttls(context=tls_context)
                client.ehlo()
                client.login(settings.smtp_username, smtp_password)
                refused = client.send_message(
                    message, from_addr=sender, to_addrs=[recipient]
                )
        if refused:
            raise EmailDeliveryError("Security notification email was not accepted.")
    except (smtplib.SMTPException, OSError):
        raise EmailDeliveryError("Security notification email delivery failed.") from None
