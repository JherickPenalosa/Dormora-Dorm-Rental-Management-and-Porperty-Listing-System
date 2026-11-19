
"""Internal email-verification workflow for Dormora registration.

Backend File 25 -- destination: backend/app/services/verification_workflow.py

File 19 owns OTP expiration, delivery status, attempt counting, one-time use,
and atomic account activation. This module turns its result into a safe,
consistent response. It does not send email or expose any public API route.

Never log submitted OTP codes. Add API-level rate limiting, audit logging, and
other required controls before mounting a verification endpoint.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from app.services.otp_service import verify_registration_otp


class RegistrationVerificationUnavailableError(Exception):
    """Verification cannot be completed because a backend operation failed."""


@dataclass(frozen=True)
class RegistrationVerificationResult:
    """Non-sensitive result of an email-verification attempt."""

    verified: bool
    account_status: Literal["active"] | None
    message: str


def verify_registration_email(
    user_id: int, submitted_code: str
) -> RegistrationVerificationResult:
    """Check a registration OTP and report whether activation succeeded.

    File 19 performs all database checks and, on success, consumes the OTP and
    activates the user in a single transaction. Incorrect code attempts are
    counted there. We deliberately do not reject malformed *string* codes
    here, so those attempts also reach File 19's attempt counter.

    This function is internal until a protected public verification route is
    ready. It never returns an OTP, digest, HMAC secret, or database detail.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")
    if not isinstance(submitted_code, str):
        raise TypeError("submitted_code must be a string.")

    try:
        verified = verify_registration_otp(user_id, submitted_code)
    except (SQLAlchemyError, RuntimeError):
        raise RegistrationVerificationUnavailableError(
            "Email verification is temporarily unavailable."
        ) from None

    if not verified:
        return RegistrationVerificationResult(
            verified=False,
            account_status=None,
            message="Verification failed. Check your code or request a new one.",
        )

    return RegistrationVerificationResult(
        verified=True,
        account_status="active",
        message="Email verified successfully. You can now log in.",
    )
