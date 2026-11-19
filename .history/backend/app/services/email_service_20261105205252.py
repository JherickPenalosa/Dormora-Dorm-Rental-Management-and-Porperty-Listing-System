
"""Send Dormora registration OTP emails through authenticated, encrypted SMTP.

Backend File 62 -- REPLACE backend/app/services/email_service.py (File 21).

Uses File 49 OTP expiry setting; no hardcoded email-expiration claim.

This module does NOT generate/store OTPs, change delivery_status, or activate
accounts. The registration workflow must call mark_otp_sent(otp_id)
ONLY after this sender returns successfully, or mark_otp_failed(otp_id) when
sending fails. An SMTP success means the provider accepted the message, not
that it reached the recipient's inbox.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from typing import TYPE_CHECKING

from pydantic import EmailStr, TypeAdapter

from app.core.config import settings
from app.core.otp_policy import OTP_EXPIRY_MINUTES

if TYPE_CHECKING:
    from app.services.otp_service import IssuedRegistrationOtp


_EMAIL = TypeAdapter(EmailStr)
_OTP_PATTERN = re.compile(r"[0-9]{6}")


class EmailDeliveryError(Exception):
    """SMTP failed; expose a generic error instead of server details."""


def build_registration_otp_email(
    issued: IssuedRegistrationOtp,
    *,
    sender_email: str,
    sender_name: str = "Dormora",
) -> EmailMessage:
    """Build the plain-text registration email without connecting to SMTP.

    Do not print or log the returned message because its body contains
    the one-time code.
    """
    if not isinstance(issued.code, str) or not _OTP_PATTERN.fullmatch(issued.code):
        raise ValueError("Registration OTP must contain exactly six digits.")
    if not isinstance(sender_name, str) or not sender_name.strip():
        raise ValueError("Sender name must not be empty.")
    if any(character in sender_name for character in ("\r", "\n", "\x00")):
        raise ValueError("Sender name contains an invalid character.")

    recipient = str(_EMAIL.validate_python(issued.email_address))
    sender = str(_EMAIL.validate_python(sender_email))

    message = EmailMessage()
    message["From"] = Address(display_name=sender_name.strip(), addr_spec=sender)
    message["To"] = recipient
    message["Subject"] = "Your Dormora email verification code"
    message.set_content(
        "Your Dormora email verification code is:\n\n"
        f"{issued.code}\n\n"
        f"This code is valid for up to {OTP_EXPIRY_MINUTES} minutes after it was issued "
        "and can be used only once.\n\n"
        "If you did not create a Dormora account, you can ignore this email.\n"
    )
    return message


def send_registration_otp_email(issued: IssuedRegistrationOtp) -> None:
    """Submit an OTP email using SMTP with required TLS and authentication.

    Raises RuntimeError for missing SMTP configuration, EmailDeliveryError
    for network/SMTP errors. Never log the code, message or SMTP password.
    """
    settings.require_smtp_configuration()
    assert settings.smtp_host is not None
    assert settings.smtp_username is not None
    assert settings.smtp_password is not None
    assert settings.smtp_from_email is not None

    message = build_registration_otp_email(
        issued,
        sender_email=str(settings.smtp_from_email),
        sender_name=settings.smtp_from_name,
    )
    recipient = str(_EMAIL.validate_python(issued.email_address))
    sender = str(settings.smtp_from_email)
    password = settings.smtp_password.get_secret_value()
    tls_context = ssl.create_default_context()

    try:
        if settings.smtp_security == "ssl":
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=tls_context,
            ) as client:
                client.login(settings.smtp_username, password)
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
                client.login(settings.smtp_username, password)
                refused = client.send_message(
                    message, from_addr=sender, to_addrs=[recipient]
                )
        if refused:
            raise EmailDeliveryError("Verification email could not be sent.")
    except (smtplib.SMTPException, OSError):
        raise EmailDeliveryError("Verification email could not be sent.") from None
