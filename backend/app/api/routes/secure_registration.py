
"""Dormora Backend File 55 — connect successful registration to OTP cookie (NOT MOUNTED).

Destination: backend/app/api/routes/secure_registration.py (REPLACE File 53).

DO NOT mount this router in backend/app/main.py yet. The existing File 14
app/api/routes/auth.py router uses legacy registration and must also remain
UNMOUNTED. The explicit safety switch below stays False until the actual
Privacy Notice, approved system-specific fields, CSRF/CAPTCHA middleware,
email OTP/resend API, and end-to-end security tests are ready.

Once deliberately enabled and mounted under File 37's FastAPI application,
POST /api/auth/register receives the strict File 51 registration payload and a
Google reCAPTCHA v2 token, forwards trusted request context to File 48, and
returns a non-secret response. Only AFTER File 44 reports successful OTP
delivery does this route call File 54 to set an HttpOnly, signed, short-lived
pending-registration cookie. The cookie is NOT a login session.

A CSRF signing key is checked BEFORE registration creates database records,
so a missing key cannot cause an account to be created without a usable OTP
verification cookie. The future mounted FastAPI app must still run File 37's
CSRF middleware: this endpoint does not replace signed token verification.

No database connections, requests, account creation, or emails occur on import
beyond those already performed by the existing service module imports.
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

    except DuplicateRegistrationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An account with these registration details already exists."
            ),
            headers={"Cache-Control": "no-store"},
        ) from None

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
