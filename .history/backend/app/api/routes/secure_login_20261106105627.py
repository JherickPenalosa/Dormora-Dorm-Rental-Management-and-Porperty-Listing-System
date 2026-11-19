
"""Dormora Backend File 67 — protected login password-step API (DISABLED).

NEW FILE: backend/app/api/routes/secure_login.py

This endpoint is designed to be mounted ONLY in app.main alongside File 56's
signed CSRF-cookie middleware, CORS policy, and security headers. Merely
creating/importing this module does NOT mount or enable login.

When eventually enabled it will:
  1. Check trusted Origin and client IP (never trust X-Forwarded-For).
  2. Require the File 56 CSRF middleware and configured signing key.
  3. Enforce PostgreSQL-backed per-IP login request rate limits.
  4. Verify Google reCAPTCHA v2 with private, server-side credentials.
  5. Invoke File 66 for password verification and progressive lockouts.

IMPORTANT: No login session is created here. Login requires a separate,
email-based OTP challenge and a completed lockout-alert workflow, which have
NOT been integrated. PUBLIC_LOGIN_ENABLED and LOGIN_SECURITY_COMPLETE must
remain False. Do NOT change these switches or mount a legacy auth router.

Never log passwords, CAPTCHA tokens, OTP codes, or private settings.
"""

from __future__ import annotations

from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.core.config import settings


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Both must remain False until login OTP, safe session creation, IP controls,
# lockout alert emails, and end-to-end tests have been completed.
PUBLIC_LOGIN_ENABLED = False
LOGIN_SECURITY_COMPLETE = False

_CACHE_HEADERS = {"Cache-Control": "no-store"}
_MAX_CAPTCHA_TOKEN_LENGTH = 8192


class SecureLoginSubmission(BaseModel):
    """Flat JSON request. Do not serialize password or CAPTCHA token to logs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=512, repr=False, exclude=True)
    captcha_token: str = Field(
        min_length=1,
        max_length=_MAX_CAPTCHA_TOKEN_LENGTH,
        repr=False,
        exclude=True,
        validation_alias=AliasChoices("captchaToken", "captcha_token"),
    )


class LoginPasswordStepAcknowledgment(BaseModel):
    """No user ID, password, OTP, email, or session credential in JSON."""

    message: str
    verification_required: bool


def _http_error(code: int, detail: str, *, retry_after: int = 0) -> HTTPException:
    headers = dict(_CACHE_HEADERS)
    if retry_after > 0:
        headers["Retry-After"] = str(min(max(retry_after, 1), 86400))
    return HTTPException(status_code=code, detail=detail, headers=headers)


def _trusted_ip(request: Request) -> str:
    """Use only ASGI connection metadata, not forwarded headers or JSON."""
    if request.client is None:
        raise _http_error(503, "Login security is temporarily unavailable.")
    try:
        return str(ip_address(request.client.host))
    except (ValueError, TypeError):
        raise _http_error(503, "Login security is temporarily unavailable.") from None


def _captcha_token_shape_valid(token: str) -> bool:
    """Syntax/size guard only. Google Siteverify is the authority."""
    return (
        isinstance(token, str)
        and 1 <= len(token) <= _MAX_CAPTCHA_TOKEN_LENGTH
        and token.isascii()
        and all(33 <= ord(char) <= 126 for char in token)
    )


def _audit_security_event(
    event_type: str,
    outcome: str,
    *,
    client_ip: str,
    user_agent: str | None,
    reason: str,
) -> None:
    """Use the existing allowlisted audit service. Fail closed on log errors."""
    from app.services.security_log_service import record_security_event

    record_security_event(
        event_type=event_type,
        outcome=outcome,
        ip_address=client_ip,
        user_agent=user_agent,
        event_details={"channel": "login", "reason": reason},
    )


def _reject_with_audit(
    code: int,
    message: str,
    *,
    client_ip: str,
    user_agent: str | None,
    event_type: str,
    reason: str,
) -> None:
    try:
        _audit_security_event(
            event_type,
            "failure" if code != 429 else "blocked",
            client_ip=client_ip,
            user_agent=user_agent,
            reason=reason,
        )
    except Exception:
        raise _http_error(503, "Login security is temporarily unavailable.") from None
    raise _http_error(code, message)


@router.post(
    "/login",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LoginPasswordStepAcknowledgment,
    summary="Two-step login password phase (disabled pending OTP integration)",
    responses={
        400: {"description": "Invalid CAPTCHA."},
        401: {"description": "Invalid credentials."},
        403: {"description": "Origin or signed CSRF rejected."},
        404: {"description": "Login not enabled."},
        422: {"description": "Invalid request fields."},
        429: {"description": "IP rate limit or account lockout."},
        503: {"description": "Login security or OTP handoff unavailable."},
    },
)
def submit_login_password_step(
    payload: SecureLoginSubmission,
    request: Request,
    response: Response,
) -> LoginPasswordStepAcknowledgment:
    """Validate the password step only; never issue authentication cookies.

    Future activation requires mounting this router through app.main and
    connecting the login-OTP handoff BEFORE changing either safety switch.
    The File 56 middleware must validate the signed CSRF cookie/header.
    """
    response.headers["Cache-Control"] = "no-store"

    # Prevent premature login, even if somebody mounts this router manually.
    if not PUBLIC_LOGIN_ENABLED or not LOGIN_SECURITY_COMPLETE:
        raise _http_error(404, "Not found.")

    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise _http_error(403, "Request origin is not permitted.")

    # A signed CSRF check must already have run in File 56's middleware.
    # This guard is not itself a CSRF verifier.
    if not request.headers.get("x-csrf-token"):
        raise _http_error(403, "CSRF token required.")
    try:
        settings.require_csrf_key()
    except (RuntimeError, ValueError):
        raise _http_error(503, "Login security is temporarily unavailable.") from None

    client_ip = _trusted_ip(request)
    agent = request.headers.get("user-agent")
    if agent is not None and (len(agent) > 512 or not agent.isprintable()):
        agent = None

    # Use the SAME PostgreSQL-backed limiter pattern as File 48 registration.
    # The limiter must explicitly support the "login" purpose before enabling.
    try:
        from app.services.rate_limit_service import check_and_record_rate_limit

        limit = check_and_record_rate_limit("login", client_ip=client_ip)
    except Exception:
        raise _http_error(503, "Login security is temporarily unavailable.") from None
    if not limit.allowed:
        try:
            _audit_security_event(
                "IP_BLOCKED",
                "blocked",
                client_ip=client_ip,
                user_agent=agent,
                reason="login_rate_limit",
            )
        except Exception:
            raise _http_error(503, "Login security is temporarily unavailable.") from None
        raise _http_error(
            429,
            "Too many attempts. Please try again later.",
            retry_after=max(1, int(limit.retry_after_seconds)),
        )

    if not _captcha_token_shape_valid(payload.captcha_token):
        _reject_with_audit(
            400,
            "CAPTCHA verification failed. Please try again.",
            client_ip=client_ip,
            user_agent=agent,
            event_type="CAPTCHA_FAILED",
            reason="invalid_token_shape",
        )

    try:
        verifier = settings.build_recaptcha_v2_verifier(client_ip=client_ip)
        captcha_ok = verifier(payload.captcha_token)
    except Exception:
        raise _http_error(503, "Login security is temporarily unavailable.") from None
    if captcha_ok is not True:
        _reject_with_audit(
            400,
            "CAPTCHA verification failed. Please try again.",
            client_ip=client_ip,
            user_agent=agent,
            event_type="CAPTCHA_FAILED",
            reason="siteverify_rejected",
        )

    # File 66 writes failed counters, lockout tiers, and audits atomically.
    # This is NOT a successful login. No session is issued at this stage.
    from app.services.login_service import (
        LoginServiceUnavailable,
        authenticate_password_step,
    )

    try:
        decision = authenticate_password_step(
            payload.identifier,
            payload.password,
            client_ip=client_ip,
            user_agent=agent,
        )
    except LoginServiceUnavailable:
        raise _http_error(503, "Login is temporarily unavailable.") from None

    if decision.status == "locked":
        raise _http_error(
            429,
            "Too many attempts. Please try again later.",
            retry_after=max(1, int(decision.retry_after_seconds)),
        )
    if decision.status != "otp_required":
        # Identical response for bad password, nonexistent or inactive users.
        raise _http_error(401, "Invalid username or password.")

    # Even a correct password MUST NOT create a session or produce a 202 until
    # an email OTP has been securely issued and bound to a temporary cookie.
    # Replace this fail-closed branch only after the full OTP flow is ready.
    raise _http_error(503, "Login verification is not available yet.")
