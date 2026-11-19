
"""Dormora Backend File 44: registration -> email OTP workflow refinement.

Destination: backend/app/services/registration_workflow.py
REPLACES Backend File 23 (no new route, table, or database migration).

File 42 now persists a strictly validated registration, three hashed security
answers, and a privacy-consent log event in a single transaction. This file
passes trusted network metadata to that service, then issues and emails an OTP.

IMPORTANT:
- The public registration endpoint is STILL DISABLED. Do not mount it yet.
- In production, callers must supply a HandoutRegisterRequest and trusted
  client_ip/user_agent. The File 42 register_user() enforces the strict type.
- This workflow retains the old RegisterRequest guard so File 24's existing
  mocked tests remain compatible; unvalidated legacy registrations cannot
  pass File 42's real registration persistence check.
- File 39's coordinator still needs a later one-file update to forward the
  trusted network context to this workflow.
- Account creation, OTP issuance, SMTP and delivery-status updates are not one
  global transaction. A failed step can leave a pending account; never blindly
  re-run account registration. Use a dedicated OTP resend/recovery flow.
"""

from app.core.config import settings
from app.schemas.auth import HandoutRegisterRequest, RegisterRequest
from app.services.email_service import EmailDeliveryError, send_registration_otp_email
from app.services.otp_service import (
    issue_registration_otp,
    mark_otp_failed,
    mark_otp_sent,
)
from app.services.registration import RegistrationResult, register_user


class RegistrationEmailDeliveryError(Exception):
    """SMTP rejected the message. The registered account stays pending."""


class RegistrationDeliveryStateError(Exception):
    """OTP delivery status could not be confirmed; do not claim success."""


def register_with_email_otp(
    payload: HandoutRegisterRequest,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> RegistrationResult:
    """Create a pending account and send its single-use verification email.

    Sequence:
      1. Validate required OTP HMAC and SMTP configuration BEFORE inserting.
      2. File 42 creates user/profile/role, hashes security answers, and writes
         REGISTERED + PRIVACY_CONSENT_GRANTED in one database transaction.
      3. Issue registration OTP (separate database transaction).
      4. Send email over SMTP, never disclosing or logging the OTP.
      5. Mark OTP sent only after SMTP provider acceptance.

    A failure AFTER step 2 leaves an unverified account. A future resend
    endpoint must handle recovery; the caller must not automatically retry
    this function with the same account details.

    The real File 42 register_user() requires HandoutRegisterRequest. An old
    RegisterRequest works only with earlier mocked tests; it cannot create an
    account using the actual File 42 persistence function.
    """
    if not isinstance(payload, RegisterRequest):
        raise TypeError("A validated registration request is required.")

    # Validate settings first so no account is created when configuration is
    # clearly incomplete. These checks make no external network requests.
    settings.require_otp_hmac_key()
    settings.require_smtp_configuration()

    # File 42 accepts optional trusted IP and browser information, then
    # stores it with consent and registration audit events. Do not pass
    # untrusted X-Forwarded-For values or user-supplied form fields here.
    context = {}
    if client_ip is not None:
        context["client_ip"] = client_ip
    if user_agent is not None:
        context["user_agent"] = user_agent

    registration = register_user(payload, **context)
    issued_otp = issue_registration_otp(registration.user_id)

    try:
        send_registration_otp_email(issued_otp)
    except EmailDeliveryError:
        # An undelivered OTP must not remain valid. If the DB cannot confirm
        # failure, report an uncertain delivery state rather than success.
        try:
            failure_recorded = mark_otp_failed(issued_otp.otp_id)
        except Exception:
            raise RegistrationDeliveryStateError(
                "Email delivery failed and the OTP delivery state could not "
                "be confirmed. The account remains pending."
            ) from None
        if failure_recorded is False:
            raise RegistrationDeliveryStateError(
                "Email delivery failed and the OTP failure state could not "
                "be confirmed. The account remains pending."
            )
        raise RegistrationEmailDeliveryError(
            "The account was created, but the verification email could not "
            "be sent. Email verification remains pending."
        ) from None

    try:
        confirmed_sent = mark_otp_sent(issued_otp.otp_id)
    except Exception:
        raise RegistrationDeliveryStateError(
            "The email provider accepted the message, but the verification "
            "status could not be confirmed. The account remains pending."
        ) from None

    if not confirmed_sent:
        raise RegistrationDeliveryStateError(
            "The email provider accepted the message, but the verification "
            "status could not be confirmed. The account remains pending."
        )

    return registration
