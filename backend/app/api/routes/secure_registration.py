
"""Dormora Requirement Validation File 11 - field-specific duplicate replies.

REPLACE: backend/app/api/routes/secure_registration.py.

Preserves the existing strict registration schema, signed-CSRF/origin guard,
server-side CAPTCHA, database rate limits, pending-account email OTP and
HttpOnly cookie. Only a protected registration attempt may return a duplicate
field, and only when File 10 verified a known PostgreSQL uniqueness constraint.
Unknown/ambiguous constraint violations keep the generic HTTP 409 response.

Importing this module does NOT activate the registration endpoint. The runner
retains responsibility for explicitly enabling the localhost registration
route and all mandatory middleware. Do not enable it through main.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.api.routes.registration_otp import issue_pending_registration_cookie
from app.schemas.auth import HandoutRegisterRequest
from app.services.otp_service import OtpAccountNotEligibleError
from app.services.registration import (
    DuplicateRegistrationError,
    RegistrationConfigurationError,
)
from app.services.registration_workflow import (
    RegistrationDeliveryStateError,
    RegistrationEmailDeliveryError,
)
from app.services.secure_registration import (
    RegistrationSecurityRejected,
    register_pending_account_securely,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Keep this False until the public registration requirements are complete.
PUBLIC_REGISTRATION_ENABLED = False


class SecureRegistrationSubmission(HandoutRegisterRequest):
    """Strict registration JSON request plus a Google CAPTCHA token.

    Existing React names such as preferredRentalType and captchaToken
    are supported. Unknown fields are rejected.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    captcha_token: str = Field(
        default="",
        max_length=8192,
        repr=False,
        exclude=True,
        validation_alias=AliasChoices("captchaToken", "captcha_token"),
    )

    def strict_registration(self) -> HandoutRegisterRequest:
        """Preserve SecretStr fields while removing the CAPTCHA field.

        model_dump() is inappropriate because sensitive fields are excluded
        from serialization by the base request model.
        """
        values = {
            field_name: getattr(self, field_name)
            for field_name in HandoutRegisterRequest.model_fields
        }
        return HandoutRegisterRequest.model_validate(values)


class RegistrationAcknowledgment(BaseModel):
    """Non-sensitive acknowledgment returned to the browser."""

    message: str
    verification_required: bool


def _safe_rejection(
    error: RegistrationSecurityRejected,
) -> HTTPException:
    """Map coordinator decisions to safe HTTP responses."""

    if error.code == "rate_limited":
        wait = max(
            1,
            min(int(error.retry_after_seconds), 86_400),
        )
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={
                "Retry-After": str(wait),
                "Cache-Control": "no-store",
            },
        )

    if error.code == "captcha_invalid":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "CAPTCHA verification failed. "
                "Please complete it again."
            ),
            headers={"Cache-Control": "no-store"},
        )

    if error.code == "registration_rejected":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration could not be completed.",
            headers={"Cache-Control": "no-store"},
        )

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Registration security is temporarily unavailable.",
        headers={"Cache-Control": "no-store"},
    )


# Field-specific error feedback is allowed ONLY after the existing protected
# registration request has passed the server-side CAPTCHA, IP rate limit,
# trusted Origin and signed-CSRF checks. There is no public availability API.
_DUPLICATE_DETAILS = {
    "username": "This username already exists.",
    "email": "This email is already used.",
    "id_number": "This ID number already exists.",
}


def _duplicate_conflict(error: DuplicateRegistrationError) -> HTTPException:
    """Return the exact allowlisted field only if PostgreSQL identified it.

    File 08's React component recognizes detail.code='duplicate' and
    detail.field. Never serialize the original DB error or submitted value.
    """
    field = getattr(error, "field", None)
    if type(field) is str and field in _DUPLICATE_DETAILS:
        detail: str | dict[str, str] = {
            "code": "duplicate",
            "field": field,
            "message": _DUPLICATE_DETAILS[field],
        }
    else:
        detail = "An account with these registration details already exists."

    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegistrationAcknowledgment,
    summary="Secure registration with temporary OTP cookie (disabled)",
    responses={
        400: {
            "description": "Invalid CAPTCHA or rejected registration."
        },
        403: {
            "description": "Disallowed request origin or CSRF token."
        },
        404: {
            "description": "Public registration is not yet enabled."
        },
        409: {
            "description": "An account with these details already exists."
        },
        422: {
            "description": "Input validation failed."
        },
        429: {
            "description": "Registration rate limit reached."
        },
        503: {
            "description": "Registration, email, or cookie security unavailable."
        },
    },
)
def submit_registration(
    payload: SecureRegistrationSubmission,
    request: Request,
    response: Response,
) -> RegistrationAcknowledgment:
    """Link successful account registration to File 54's signed cookie.

    File 37's CSRF middleware is mandatory when mounted.
    This function does not replace that middleware.

    A failed SMTP step may leave a pending account. Never automatically
    retry registration after such a failure.

    No pending-registration cookie is issued when registration is rejected.
    """

    response.headers["Cache-Control"] = "no-store"

    # Public registration remains disabled.
    if not PUBLIC_REGISTRATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
            headers={"Cache-Control": "no-store"},
        )

    # Additional origin restriction.
    # This does NOT replace signed CSRF protection.
    if (
        request.headers.get("origin")
        != settings.frontend_origin.rstrip("/")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not permitted.",
            headers={"Cache-Control": "no-store"},
        )

    # Use server-resolved request information, never submitted user IDs
    # or untrusted X-Forwarded-For values.
    if request.client is None or not request.client.host:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration security is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        )

    # Check the cookie-signing key before creating an account.
    # This prevents avoidable post-registration configuration failures.
    try:
        settings.require_csrf_key()
    except (RuntimeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration security is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None

    # File 48 enforces rate limits, Google CAPTCHA, and auditing.
    # Files 44, 52, and 50 perform registration and email OTP issuance.
    try:
        registration = register_pending_account_securely(
            payload.strict_registration(),
            client_ip=request.client.host,
            user_agent=request.headers.get("user-agent"),
            captcha_token=payload.captcha_token,
        )

    except RegistrationSecurityRejected as error:
        raise _safe_rejection(error) from None

    except DuplicateRegistrationError as error:
        raise _duplicate_conflict(error) from None

    except RegistrationEmailDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Account creation completed, but the verification email "
                "could not be sent. Do not submit registration again."
            ),
            headers={"Cache-Control": "no-store"},
        ) from None

    except (
        RegistrationDeliveryStateError,
        OtpAccountNotEligibleError,
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Registration was saved, but email verification could not "
                "be confirmed. Do not submit registration again."
            ),
            headers={"Cache-Control": "no-store"},
        ) from None

    except (
        RegistrationConfigurationError,
        SQLAlchemyError,
        RuntimeError,
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None

    # Account and OTP delivery succeeded.
    # The browser must NEVER choose its own pending-registration user ID.
    user_id = getattr(registration, "user_id", None)
    account_status = getattr(
        registration,
        "account_status",
        None,
    )

    if (
        type(user_id) is not int
        or user_id <= 0
        or account_status != "pending_verification"
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Registration status could not be confirmed. "
                "Do not submit registration again."
            ),
            headers={"Cache-Control": "no-store"},
        )

    # File 54 signs the temporary pending-registration cookie.
    # It is HttpOnly, SameSite=Lax, short-lived, and NOT a login session.
    try:
        issue_pending_registration_cookie(
            response,
            user_id=user_id,
        )
    except (RuntimeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Registration was saved, but verification could not be "
                "started. Do not submit registration again."
            ),
            headers={"Cache-Control": "no-store"},
        ) from None

    # No user_id, OTP, password, or security answer is returned.
    return RegistrationAcknowledgment(
        message=(
            "Registration received. Check your email "
            "for a verification code."
        ),
        verification_required=True,
    )
