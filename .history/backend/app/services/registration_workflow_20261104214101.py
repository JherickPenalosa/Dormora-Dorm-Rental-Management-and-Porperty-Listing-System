
"""Coordinate pending account registration with email OTP delivery.

Backend File 23 — install as backend/app/services/registration_workflow.py.

The public registration router is intentionally NOT mounted yet. CAPTCHA,
request throttling, security logging, and verification endpoints must be
integrated before public registration is enabled.

This service uses the existing registration, OTP, and SMTP services. It does
not create or modify database tables, and it never returns or logs OTP codes.
"""

from app.core.config import settings
from app.schemas.auth import RegisterRequest
from app.services.email_service import EmailDeliveryError, send_registration_otp_email
from app.services.otp_service import (
    issue_registration_otp,
    mark_otp_failed,
    mark_otp_sent,
)
from app.services.registration import RegistrationResult, register_user


class RegistrationEmailDeliveryError(Exception):
    """The account remains pending, but the verification email was not sent."""


class RegistrationDeliveryStateError(Exception):
    """The provider accepted the email, but its OTP status was not confirmed."""


def register_with_email_otp(payload: RegisterRequest) -> RegistrationResult:
    """Register an account and request delivery of its verification OTP.

    Order of operations:
      1. Check SMTP and HMAC configuration before creating an account.
      2. Register the user, profile and role-specific record atomically.
      3. Issue a protected registration OTP in PostgreSQL.
      4. Submit the OTP email to the configured SMTP provider.
      5. Mark the OTP sent only after provider acceptance.

    Returns a non-secret registration summary. Accounts remain in
    'pending_verification' until a separate OTP verification succeeds.

    Important: these operations span multiple transactions and an external
    SMTP call. If sending fails, the account intentionally remains pending;
    a later resend/recovery workflow is required. Never retry the entire
    registration operation automatically because the account now exists.
    """
    if not isinstance(payload, RegisterRequest):
        raise TypeError("A validated RegisterRequest is required.")

    # Fail before creating a pending account when key or SMTP settings are
    # clearly missing. These checks do not make a network connection.
    settings.require_otp_hmac_key()
    settings.require_smtp_configuration()

    registration = register_user(payload)
    issued_otp = issue_registration_otp(registration.user_id)

    try:
        send_registration_otp_email(issued_otp)
    except EmailDeliveryError:
        # Do not leave an undelivered OTP eligible for verification.
        mark_otp_failed(issued_otp.otp_id)
        raise RegistrationEmailDeliveryError(
            "The account was created, but the verification email could not be "
            "sent. Email verification remains pending."
        ) from None

    if not mark_otp_sent(issued_otp.otp_id):
        # The provider accepted the message, but the DB status could not be
        # confirmed. The OTP remains unusable until an explicit recovery step.
        raise RegistrationDeliveryStateError(
            "The email provider accepted the message, but the verification "
            "status could not be confirmed."
        )

    return registration
