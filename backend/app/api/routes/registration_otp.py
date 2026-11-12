
"""Dormora Backend File 54 — pending-registration OTP verification/resend API.

Destination: backend/app/api/routes/registration_otp.py (NEW FILE).

IMPORTANT: This router is intentionally NOT MOUNTED and its feature guard is
False. Do not expose it until File 53 issues a signed pending-registration
cookie after successful registration, the Privacy Notice/approved fields are
complete, and the File 37 CSRF middleware is verified end to end.

The browser never supplies user_id. A short-lived, HMAC-signed, HttpOnly
pending-registration cookie identifies the user. It is NOT a login session.
The signing key uses the existing private CSRF key with an independent HMAC
message prefix (domain separation), and is never returned to the browser.

Registration OTP verification/activation uses File 50, as does resend limiting.
Gmail delivery uses File 44's existing email service interface. No route here
creates a logged-in session. No schema migrations or new dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.otp_policy import OTP_EXPIRY_MINUTES, OTP_RESEND_COOLDOWN_SECONDS
from app.services.email_service import send_registration_otp_email
from app.services.otp_service import (
    OtpAccountNotEligibleError,
    OtpResendNotAllowed,
    mark_otp_failed,
    mark_otp_sent,
    resend_registration_otp,
    verify_registration_otp,
)

router = APIRouter(prefix="/api/auth/registration", tags=["Registration verification"])

# Safeguard 1: stays False until the complete registration flow is reviewed.
PUBLIC_REGISTRATION_OTP_ENABLED = False

# Safeguard 2: do not mount this router until the main app's CSRF middleware,
# CORS origin enforcement, and secure error handling are in place and tested.
_PENDING_LIFETIME_SECONDS = 30 * 60
_CLOCK_SKEW_SECONDS = 30
_COOKIE_PATH = "/"
_COOKIE_NAME_DEV = "dormora-pending-dev"
_COOKIE_NAME_PROD = "__Host-dormora-pending"
_TOKEN_RE = re.compile(r"v1\.([0-9]{10,12})\.([1-9][0-9]{0,18})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")
_MAX_DATABASE_USER_ID = 2**63 - 1
_CONTEXT = b"dormora:pending-registration:v1|"


def _cookie_name() -> str:
    return _COOKIE_NAME_PROD if settings.environment == "production" else _COOKIE_NAME_DEV


def _epoch_now() -> int:
    return int(time.time())


def _signing_key() -> bytes:
    """Server-only existing CSRF key; HMAC input is domain-separated."""
    return settings.require_csrf_key()


def _signature(payload: str) -> str:
    return hmac.new(
        _signing_key(), _CONTEXT + payload.encode("ascii"), hashlib.sha256
    ).hexdigest()


def issue_pending_registration_cookie(response: Response, *, user_id: int) -> None:
    """Called ONLY by a future successful File 53 registration route.

    Sets a signed HttpOnly cookie after the registration workflow has actually
    returned a pending user. Never expose an HTTP endpoint for token minting.
    Do not call before the account exists or if the email workflow failed.
    """
    if type(user_id) is not int or not 1 <= user_id <= _MAX_DATABASE_USER_ID:
        raise ValueError("A valid registered user ID is required.")
    payload = f"v1.{_epoch_now()}.{user_id}.{secrets.token_hex(16)}"
    token = f"{payload}.{_signature(payload)}"
    response.set_cookie(
        key=_cookie_name(),
        value=token,
        max_age=_PENDING_LIFETIME_SECONDS,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path=_COOKIE_PATH,
    )
    response.headers["Cache-Control"] = "no-store"


def _validated_pending_user_id(token: str | None) -> int | None:
    """Reject tampered/expired proofs without revealing which check failed."""
    if not isinstance(token, str) or len(token) > 256:
        return None
    match = _TOKEN_RE.fullmatch(token)
    if match is None:
        return None
    issued_raw, user_id_raw, _nonce, supplied_signature = match.groups()
    issued_at = int(issued_raw)
    user_id = int(user_id_raw)
    now = _epoch_now()
    if (
        not 1 <= user_id <= _MAX_DATABASE_USER_ID
        or issued_at > now + _CLOCK_SKEW_SECONDS
        or now - issued_at >= _PENDING_LIFETIME_SECONDS
    ):
        return None
    payload = token.rsplit(".", 1)[0]
    if not hmac.compare_digest(supplied_signature, _signature(payload)):
        return None
    return user_id


def _require_enabled_context(request: Request) -> int:
    """Require feature enabled, expected browser origin, and signed cookie.

    This is defense-in-depth; a later mount MUST still use File 37's
    server-verified CSRF middleware. An Origin header alone is not CSRF.
    """
    if not PUBLIC_REGISTRATION_OTP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
            headers={"Cache-Control": "no-store"},
        )
    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification request is not permitted.",
            headers={"Cache-Control": "no-store"},
        )
    user_id = _validated_pending_user_id(request.cookies.get(_cookie_name()))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration verification has expired. Start again securely.",
            headers={"Cache-Control": "no-store"},
        )
    return user_id


class VerifyRegistrationOtpRequest(BaseModel):
    """No user ID, email address or OTP purpose is accepted from the browser."""

    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(repr=False, exclude=True)


class VerificationResult(BaseModel):
    message: str
    verified: bool


class ResendResult(BaseModel):
    message: str
    expires_in_minutes: int
    resend_cooldown_seconds: int


@router.post(
    "/verify",
    response_model=VerificationResult,
    summary="Verify registration email OTP (currently disabled)",
)
def verify_pending_registration(
    payload: VerifyRegistrationOtpRequest, request: Request, response: Response
) -> VerificationResult:
    """Activate a pending account only after File 50 consumes its valid OTP."""
    response.headers["Cache-Control"] = "no-store"
    user_id = _require_enabled_context(request)
    code = payload.code.get_secret_value()
    if len(code) > 64:
        raise HTTPException(status_code=400, detail="Invalid verification code.")
    try:
        accepted = verify_registration_otp(user_id, code, **_request_audit_metadata(request))
    except (SQLAlchemyError, RuntimeError):
        raise HTTPException(
            status_code=503,
            detail="Verification is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None
    if not accepted:
        raise HTTPException(
            status_code=400,
            detail="Invalid, expired, or already-used verification code.",
            headers={"Cache-Control": "no-store"},
        )
    # OTP verification does NOT create a session; login remains separate.
    response.delete_cookie(
        key=_cookie_name(), path=_COOKIE_PATH,
        secure=settings.environment == "production", httponly=True,
        samesite="lax",
    )
    return VerificationResult(
        message="Account verified. You may now log in.", verified=True
    )


def _ensure_mail_ready() -> None:
    """Check real server SMTP settings; easy to substitute during isolated tests."""
    settings.require_smtp_configuration()


def _request_audit_metadata(request: Request) -> dict[str, str | None]:
    """Get bounded metadata without trusting forwarded IP headers."""
    client_ip = request.client.host if request.client is not None else None
    user_agent = request.headers.get("user-agent") or None
    if user_agent is not None:
        user_agent = user_agent[:255]
    return {"client_ip": client_ip, "user_agent": user_agent}


def _invalidate_undelivered_otp(otp_id: int, request: Request | None = None) -> None:
    """Best-effort revoke a replacement after an email delivery failure."""
    try:
        mark_otp_failed(otp_id, **(_request_audit_metadata(request) if request is not None else {}))
    except Exception:
        # Return a generic 503; never imply that a code was actually delivered.
        pass


@router.post(
    "/resend",
    response_model=ResendResult,
    summary="Resend registration email OTP (currently disabled)",
)
def resend_pending_registration(
    request: Request, response: Response
) -> ResendResult:
    """Issue and email a replacement, respecting File 50's persisted limits."""
    response.headers["Cache-Control"] = "no-store"
    user_id = _require_enabled_context(request)

    # Check SMTP configuration before changing the OTP database state.
    try:
        _ensure_mail_ready()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Verification email is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None

    try:
        issued = resend_registration_otp(user_id, **_request_audit_metadata(request))
    except OtpResendNotAllowed as error:
        wait = max(1, min(int(error.retry_after_seconds), 900))
        raise HTTPException(
            status_code=429,
            detail="Please wait before requesting another code.",
            headers={"Retry-After": str(wait), "Cache-Control": "no-store"},
        ) from None
    except OtpAccountNotEligibleError:
        raise HTTPException(
            status_code=403,
            detail="Registration verification is not available.",
            headers={"Cache-Control": "no-store"},
        ) from None
    except (SQLAlchemyError, RuntimeError):
        raise HTTPException(
            status_code=503,
            detail="Verification email is temporarily unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None

    try:
        send_registration_otp_email(issued)
    except Exception:
        _invalidate_undelivered_otp(issued.otp_id, request=request)
        raise HTTPException(
            status_code=503,
            detail="The verification email could not be sent. Please try again later.",
            headers={"Cache-Control": "no-store"},
        ) from None

    try:
        delivery_confirmed = mark_otp_sent(issued.otp_id, **_request_audit_metadata(request))
    except Exception:
        delivery_confirmed = False
    if delivery_confirmed is not True:
        raise HTTPException(
            status_code=503,
            detail="Email delivery status could not be confirmed. Try again later.",
            headers={"Cache-Control": "no-store"},
        )

    return ResendResult(
        message="If your registration is pending, check your email for a new code.",
        expires_in_minutes=OTP_EXPIRY_MINUTES,
        resend_cooldown_seconds=OTP_RESEND_COOLDOWN_SECONDS,
    )
