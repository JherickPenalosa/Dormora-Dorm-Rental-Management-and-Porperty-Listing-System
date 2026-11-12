"""Dormora File 69: login OTP email delivery using existing SMTP settings.

Create: backend/app/services/login_email_service.py
No database writes, routes, sessions, or registration-email changes.
The caller must mark the OTP sent only after this sender succeeds, and
mark it failed on delivery failure. Never log the message or OTP payload.
"""
from __future__ import annotations

import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage
from typing import TYPE_CHECKING

from pydantic import EmailStr, TypeAdapter

from app.core.config import settings
from app.services.email_service import EmailDeliveryError

if TYPE_CHECKING:
    from app.services.login_otp_service import IssuedLoginOtp

_EMAIL = TypeAdapter(EmailStr)
_CODE = re.compile(r"[0-9]{6}\Z")
_PHT = timezone(timedelta(hours=8), name="PHT")


def build_login_otp_email(
    issued: IssuedLoginOtp,
    *,
    sender_email: str,
    sender_name: str = "Dormora",
) -> EmailMessage:
    """Build an email without SMTP or database access; contains a secret code."""
    if not isinstance(issued.code, str) or not _CODE.fullmatch(issued.code):
        raise ValueError("Login OTP must contain exactly six digits.")
    expiry = issued.expires_at
    if (not isinstance(expiry, datetime) or expiry.tzinfo is None
            or expiry.utcoffset() is None):
        raise ValueError("OTP expiry must be timezone-aware.")
    if expiry <= datetime.now(timezone.utc):
        raise ValueError("Cannot send an expired login code.")
    if (not isinstance(sender_name, str) or not sender_name.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in sender_name)):
        raise ValueError("Invalid sender name.")
    recipient = str(_EMAIL.validate_python(issued.email_address))
    sender = str(_EMAIL.validate_python(sender_email))
    expiry_text = expiry.astimezone(_PHT).strftime("%d %B %Y, %I:%M:%S %p PHT")
    message = EmailMessage()
    message["From"] = Address(display_name=sender_name.strip(), addr_spec=sender)
    message["To"] = recipient
    message["Subject"] = "Your Dormora log-in code"
    message.set_content(
        "Your Dormora log-in code is:\n\n"
        f"{issued.code}\n\n"
        f"Expires: {expiry_text} (Philippine time).\n"
        "This code can be used only once. Use the latest code you requested.\n"
        "Do not share this code with anyone.\n\n"
        "If you did not request this code, ignore this email and consider "
        "changing your password.\n"
    )
    return message


def send_login_otp_email(issued: IssuedLoginOtp) -> None:
    """Send using authenticated TLS; success means SMTP acceptance only.

    Configuration/payload errors raise RuntimeError or ValueError. SMTP/network
    errors raise EmailDeliveryError with a generic message. The future workflow
    must handle failures and persist delivery status; this function does not.
    """
    settings.require_smtp_configuration()
    if settings.smtp_security not in {"ssl", "starttls"}:
        raise RuntimeError("Encrypted SMTP is required.")
    message = build_login_otp_email(
        issued,
        sender_email=str(settings.smtp_from_email),
        sender_name=settings.smtp_from_name,
    )
    sender = str(_EMAIL.validate_python(str(settings.smtp_from_email)))
    recipient = str(_EMAIL.validate_python(issued.email_address))
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
                    raise EmailDeliveryError("Login verification email could not be sent.")
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
                    raise EmailDeliveryError("Login verification email could not be sent.")
                accepted = True
    except (smtplib.SMTPException, OSError):
        # A failure during QUIT after acceptance must not trigger a resend.
        # An uncertain send failure is not automatically retried here.
        if not accepted:
            raise EmailDeliveryError("Login verification email could not be sent.") from None