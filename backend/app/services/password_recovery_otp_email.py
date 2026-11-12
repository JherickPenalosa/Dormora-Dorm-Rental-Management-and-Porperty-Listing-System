
"""Dormora File 119 -- password-recovery OTP email delivery.

CREATE: backend/app/services/password_recovery_otp_email.py

This is an internal service, NOT an exposed FastAPI route. Its caller MUST:
  1. Verify CAPTCHA and the account's registered security-question answer.
  2. Apply lockout, throttling and anti-enumeration controls on the server.
  3. Create a six-digit cryptographically random OTP and store ONLY its hash,
     purpose='reset', expiry and attempt limits in PostgreSQL.
  4. Derive recipient_email from the verified user record (not request JSON).
  5. Call send_password_recovery_otp_email() exactly once per valid issuance.
  6. Mark delivery accepted / cancel the OTP on a definite SMTP failure.

This file ONLY validates and delivers the email. It does NOT authenticate a
user, create a session or reset a password. It never logs or prints an OTP.
It uses the same TLS-only Gmail/SMTP configuration as File 107.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage

from pydantic import EmailStr, TypeAdapter

from app.core.config import settings
from app.services.email_service import EmailDeliveryError


_EMAIL = TypeAdapter(EmailStr)
_PHT = timezone(timedelta(hours=8), name="PHT")
_CODE_RE = re.compile(r"[0-9]{6}\Z", flags=re.ASCII)
_SEEDED_MAX_LIFETIME_SECONDS = 180  # Dormora: three-minute OTP expiry.


class PasswordRecoveryEmailRejected(ValueError):
    """Trusted delivery arguments are invalid; do not expose to the browser."""


@dataclass(frozen=True, slots=True, repr=False)
class PasswordRecoveryOtpDelivery:
    """Trusted, transient email details from an already-authorized backend flow.

    Code must be stored only as a hash by the caller, not in any log, database
    plaintext column, cookie, browser response or instance representation.
    """

    recipient_email: str = field(repr=False)
    code: str = field(repr=False)
    issued_at: datetime = field(repr=False)
    expires_at: datetime = field(repr=False)


def _validate_delivery(delivery: PasswordRecoveryOtpDelivery) -> str:
    if not isinstance(delivery, PasswordRecoveryOtpDelivery):
        raise PasswordRecoveryEmailRejected("Invalid reset email request.")
    if not isinstance(delivery.code, str) or _CODE_RE.fullmatch(delivery.code) is None:
        raise PasswordRecoveryEmailRejected("Invalid reset OTP format.")
    issued = delivery.issued_at
    expires = delivery.expires_at
    if not isinstance(issued, datetime) or not isinstance(expires, datetime):
        raise PasswordRecoveryEmailRejected("Invalid reset OTP lifetime.")
    if issued.tzinfo is None or expires.tzinfo is None:
        raise PasswordRecoveryEmailRejected("OTP timestamps must be timezone-aware.")
    try:
        lifetime = (expires.astimezone(timezone.utc) - issued.astimezone(timezone.utc)).total_seconds()
    except (OverflowError, ValueError, TypeError):
        raise PasswordRecoveryEmailRejected("Invalid reset OTP lifetime.") from None
    if not 0 < lifetime <= _SEEDED_MAX_LIFETIME_SECONDS:
        raise PasswordRecoveryEmailRejected("Reset OTP must expire within three minutes.")
    if expires.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise PasswordRecoveryEmailRejected("Reset OTP is already expired.")
    try:
        return str(_EMAIL.validate_python(delivery.recipient_email))
    except (TypeError, ValueError):
        raise PasswordRecoveryEmailRejected("Invalid trusted recipient address.") from None


def build_password_recovery_otp_email(
    delivery: PasswordRecoveryOtpDelivery,
    *,
    sender_email: str,
    sender_name: str = "Dormora",
) -> EmailMessage:
    """Build a text-only message; this function does NOT send an email.

    Only the recipient's inbox receives the code. Do not return this message
    through a route or print its content in test output.
    """
    recipient = _validate_delivery(delivery)
    if (
        not isinstance(sender_name, str)
        or not sender_name.strip()
        or len(sender_name) > 80
        or any(ord(char) < 32 or ord(char) == 127 for char in sender_name)
    ):
        raise PasswordRecoveryEmailRejected("Invalid email sender name.")
    try:
        sender = str(_EMAIL.validate_python(sender_email))
    except (TypeError, ValueError):
        raise PasswordRecoveryEmailRejected("Invalid email sender address.") from None

    expiry = delivery.expires_at.astimezone(_PHT).strftime(
        "%d %B %Y at %I:%M:%S %p PHT"
    )
    message = EmailMessage()
    message["From"] = Address(display_name=sender_name.strip(), addr_spec=sender)
    message["To"] = recipient
    message["Subject"] = "Your Dormora password reset code"
    message.set_content(
        "Dormora account recovery\n\n"
        "A password reset was requested for your Dormora account.\n\n"
        f"Your six-digit password reset code is: {delivery.code}\n"
        f"Expires: {expiry} (valid for no more than 3 minutes).\n\n"
        "Enter this code only on Dormora's password recovery page.\n"
        "The code can be used once. Three incorrect attempts cancel it.\n"
        "Requesting a replacement code cancels the previous code.\n\n"
        "If you did not request this code, ignore this email and consider "
        "changing your password.\n\n"
        "Dormora will never ask you to send your password or code in a reply.\n"
    )
    return message


def send_password_recovery_otp_email(delivery: PasswordRecoveryOtpDelivery) -> None:
    """Send one reset-code email through encrypted SMTP.

    Raise on SMTP refusal or transport failure. A caller must not claim
    successful delivery or reveal account existence to the requestor.
    An SMTP success means provider *acceptance*, not inbox arrival.
    """
    recipient = _validate_delivery(delivery)
    try:
        settings.require_smtp_configuration()
        if settings.smtp_security not in {"ssl", "starttls"}:
            raise PasswordRecoveryEmailRejected("Encrypted SMTP is required.")
        sender = str(_EMAIL.validate_python(str(settings.smtp_from_email)))
        message = build_password_recovery_otp_email(
            delivery,
            sender_email=sender,
            sender_name=settings.smtp_from_name,
        )
    except PasswordRecoveryEmailRejected:
        raise
    except (RuntimeError, ValueError, TypeError):
        raise PasswordRecoveryEmailRejected("Reset email configuration unavailable.") from None

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
            raise EmailDeliveryError("Password recovery OTP was not accepted.")
    except (smtplib.SMTPException, OSError):
        raise EmailDeliveryError("Password recovery OTP delivery failed.") from None
