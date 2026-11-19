
"""Dormora Backend File 53 — secured registration HTTP contract (NOT MOUNTED).

Destination: backend/app/api/routes/secure_registration.py (NEW FILE).

DO NOT mount this router in backend/app/main.py yet. The existing File 14
app/api/routes/auth.py router uses legacy registration and must also remain
UNMOUNTED. The explicit safety switch below stays False until the actual
Privacy Notice, approved system-specific fields, CSRF/CAPTCHA middleware,
email OTP/resend API, and end-to-end security tests are ready.

Once deliberately enabled and mounted under File 37's FastAPI application,
POST /api/auth/register receives a strict File 51 registration payload and a
Google reCAPTCHA v2 token, passes server-resolved IP/browser information to
File 48, and returns a non-secret response. File 48 checks PostgreSQL-backed
rate limits + Google Siteverify before File 44 starts account creation/OTP.

No database connections, requests, account creation, or emails occur on import
beyond those already performed by the existing service module imports.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
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

# Leave False even during development. Only a later, deliberate activation
# should switch this on after the remaining public-registration prerequisites.
# This extra guard prevents accidental exposure if someone includes the router.
PUBLIC_REGISTRATION_ENABLED = False


class SecureRegistrationSubmission(HandoutRegisterRequest):
    """Flat JSON contract compatible with existing React form field names.

    Includes every File 51 validation and one opaque Google CAPTCHA token.
    Example JSON keys: username, email, password, confirm_password,
    privacy_consent, security_answer_1/2/3, preferredRentalType, captchaToken.
    Unknown keys are rejected; CAPTCHA token is excluded from model dumps.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    captcha_token: str = Field(
        default="",
        max_length=2048,
        repr=False,
        exclude=True,
        validation_alias=AliasChoices("captchaToken", "captcha_token"),
    )

    def strict_registration(self) -> HandoutRegisterRequest:
        """Preserve excluded secrets while removing only the CAPTCHA field.

        model_dump() is NOT appropriate here: File 51 deliberately excludes
        the password confirmation and security answers from serialization.
        Read only declared File 51 attributes and revalidate them instead.
        """
        values = {
            field_name: getattr(self, field_name)
            for field_name in HandoutRegisterRequest.model_fields
        }
        return HandoutRegisterRequest.model_validate(values)


class RegistrationAcknowledgment(BaseModel):
    """No user_id, email, passwords, answers, CAPTCHA token, or OTP in JSON."""

    message: str
    verification_required: bool


def _safe_rejection(error: RegistrationSecurityRejected) -> HTTPException:
    """Translate only known static coordinator codes; never expose raw errors."""
    if error.code == "rate_limited":
        # The service computes this from database rate-limiting state.
        wait = max(1, min(int(error.retry_after_seconds), 86_400))
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(wait), "Cache-Control": "no-store"},
        )
    if error.code == "captcha_invalid":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification failed. Please complete it again.",
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
    summary="Secure account registration (disabled until activation)",
    responses={
        400: {"description": "Invalid CAPTCHA or rejected registration."},
        403: {"description": "Disallowed request origin or CSRF token."},
        404: {"description": "Pualic registration is not yet enabled."},
        409: {"description": "An account with these details already exists."},
        422: {"description": "Input validation failed."},
        429: {"description": "Registration rate limit reached."},
        503: {"description": "Registration or email service unavailable."},
    },
)
def submit_registration(
    payload: SecureRegistrationSubmission,
    request: Request,
    response: Response,
) -> RegistrationAcknowledgment:
    """Prepare the public route, but refuse traffic until explicitly enabled.

    File 37 main.py MUST be the eventual mounting application: its middleware
    checks signed CSRF cookie + X-CSRF-Token for every unsafe HTTP method,
    and installs CORS/security headers. This module alone does not replace
    that middleware. NEVER mount the insecure legacy File 14 auth router.

    A failed SMTP step may have already created a pending account; do not
    automatically re-register. OTP resend will be a separate protected route.
    """
    response.headers["Cache-Control"] = "no-store"
    if not PUBLIC_REGISTRATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
            headers={"Cache-Control": "no-store"},
        )

    # Normal browser form submissions include Origin. This is an additional
    # check, NOT a replacement for the signed-CSRF middleware in File 37.
    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not permitted.",
            headers={"Cache-Control": "no-store"},
        )

    # Never derive this from request JSON or untrusted X-Forwarded-For headers.
    if request.client is None or not request.client.host:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration security is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        )

    # File 48 normalizes user agents and IP addresses, constructs the Google
    # verifier internally, and refuses to continue on rate-limit/log failures.
    try:
        register_pending_account_securely(
            payload.strict_registration(),
            client_ip=request.client.host,
            user_agent=request.headers.get("user-agent"),
            captcha_token=payload.captcha_token,
        )
    except RegistrationSecurityRejected as error:
        raise _safe_rejection(error) from None
    except DuplicateRegistrationError:
        # Field-specific uniqueness mapping requires a later verified DB test.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with these registration details already exists.",
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
    except (RegistrationDeliveryStateError, OtpAccountNotEligibleError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Registration was saved, but email verification could not "
                "be confirmed. Do not submit registration again."
            ),
            headers={"Cache-Control": "no-store"},
        ) from None
    except (RegistrationConfigurationError, SQLAlchemyError, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None

    return RegistrationAcknowledgment(
        message="Registration received. Check your email for a verification code.",
        verification_required=True,
    )
