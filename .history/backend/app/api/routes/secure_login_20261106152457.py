
"""Dormora Backend File 83 -- enforce request limits on the login password phase.

REPLACE: backend/app/api/routes/secure_login.py (previously File 76).

This route connects File 75's password decision to File 72 IP blocking,
File 74 lockout alert delivery, File 71 login OTP email, File 70's
signed, temporary login challenge cookie, and File 82's per-IP request limiter.

SAFETY GATE: The route remains DISABLED. Neither flag below may be enabled
until the login OTP verification route, authenticated session lifecycle,
OTP verification request limits, router mounting, and end-to-end security
tests are complete. The pending cookie is NOT an authenticated session.

File 56's signed CSRF middleware, trusted Origin and CORS configuration,
and security response headers must protect this route when mounted.
Never log passwords, CAPTCHA tokens, OTP codes, or secret keys.
"""

from __future__ import annotations

from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.core.config import settings


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Do not change these until the ENTIRE login flow is security-tested.
PUBLIC_LOGIN_ENABLED = False
LOGIN_SECURITY_COMPLETE = False

_CACHE_HEADERS = {"Cache-Control": "no-store"}
_MAX_CAPTCHA_TOKEN_LENGTH = 8192
_INVALID_LOGIN = "Invalid username or password."
_TEMPORARY_ERROR = "Login security is temporarily unavailable."
_TOO_MANY_ATTEMPTS = "Too many attempts. Please try again later."


class SecureLoginSubmission(BaseModel):
    """Accept only expected fields. Secrets must not appear in model repr."""

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
    """The API never returns an account ID, OTP, or authentication token."""

    message: str
    verification_required: bool


def _http_error(code: int, detail: str, *, retry_after: int = 0) -> HTTPException:
    headers = dict(_CACHE_HEADERS)
    if retry_after > 0:
        headers["Retry-After"] = str(min(max(int(retry_after), 1), 86400))
    return HTTPException(status_code=code, detail=detail, headers=headers)


def _trusted_ip(request: Request) -> str:
    """Use ASGI connection metadata, never untrusted forwarded headers."""
    if request.client is None:
        raise _http_error(503, _TEMPORARY_ERROR)
    try:
        parsed = ip_address(request.client.host)
        mapped = getattr(parsed, "ipv4_mapped", None)
        return str(mapped if mapped is not None else parsed)
    except (ValueError, TypeError):
        raise _http_error(503, _TEMPORARY_ERROR) from None


def _safe_user_agent(request: Request) -> str | None:
    raw = request.headers.get("user-agent")
    if raw is None:
        return None
    return "".join(char for char in raw if char.isprintable())[:255] or None


def _captcha_token_shape_valid(token: str) -> bool:
    """A syntax guard, not a replacement for Google's server-side Siteverify."""
    return (
        isinstance(token, str)
        and 1 <= len(token) <= _MAX_CAPTCHA_TOKEN_LENGTH
        and token.isascii()
        and all(33 <= ord(char) <= 126 for char in token)
    )


def _record_captcha_failure(*, client_ip: str, user_agent: str | None,
                            reason: str) -> None:
    """File 27 accepts lower-case audit labels; do not expose audit errors."""
    from app.services.security_log_service import record_security_event

    try:
        record_security_event(
            event_type="captcha_failed",
            outcome="failure",
            ip_address=client_ip,
            user_agent=user_agent,
            event_details={"channel": "login", "reason": reason},
        )
    except Exception:
        raise _http_error(503, _TEMPORARY_ERROR) from None
    raise _http_error(400, "CAPTCHA verification failed. Please try again.")


def _check_ip_block(*, client_ip: str, user_agent: str | None) -> None:
    """File 72 enforces 14 failed logins per 10 minutes, blocked for 10."""
    from app.services.login_ip_service import (
        LoginIpServiceUnavailable,
        check_login_ip,
    )

    try:
        decision = check_login_ip(client_ip, user_agent=user_agent)
    except (LoginIpServiceUnavailable, ValueError):
        raise _http_error(503, _TEMPORARY_ERROR) from None
    if not decision.allowed:
        raise _http_error(
            429,
            _TOO_MANY_ATTEMPTS,
            retry_after=max(1, int(decision.retry_after_seconds)),
        )


def _check_password_request_limit(*, client_ip: str, user_agent: str | None) -> None:
    """File 82: count a password request before CAPTCHA and password hashing.

    This request-volume limit is independent of File 72's seeded 14-failure
    IP-block threshold; it never replaces account lockouts or CAPTCHA.
    """
    from app.services.login_request_limit_service import (
        LoginRequestLimiterUnavailable,
        check_and_record_login_request,
    )

    try:
        decision = check_and_record_login_request(
            "password", client_ip=client_ip, user_agent=user_agent
        )
    except (LoginRequestLimiterUnavailable, ValueError):
        # If PostgreSQL cannot enforce the limit, never allow login through.
        raise _http_error(503, _TEMPORARY_ERROR) from None
    if not decision.allowed:
        raise _http_error(
            429,
            _TOO_MANY_ATTEMPTS,
            retry_after=max(1, int(decision.retry_after_seconds)),
        )


def _notify_new_lockout(lockout_event_id: int | None) -> None:
    """Notify only for the exact tier event committed by File 75.

    A mail delivery error must not disclose whether an account exists or
    whether its owner received a notification. File 74 tracks claims and
    delivery outcomes for operational review.
    """
    if lockout_event_id is None:
        return
    from app.services.lockout_alert_workflow import (
        LockoutAlertUnavailable,
        dispatch_lockout_alert,
    )

    try:
        dispatch_lockout_alert(lockout_event_id)
    except LockoutAlertUnavailable:
        # A failed alert does not authorize login or reveal account state.
        # File 74's one-time claim guards against duplicate SMTP attempts.
        pass


@router.post(
    "/login",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LoginPasswordStepAcknowledgment,
    summary="Two-step login password phase (not publicly enabled)",
    responses={
        400: {"description": "Invalid CAPTCHA."},
        401: {"description": "Invalid credentials."},
        403: {"description": "Origin or CSRF rejected."},
        404: {"description": "Public login remains disabled."},
        422: {"description": "Invalid request fields."},
        429: {"description": "IP blocked, request limited, account locked, or OTP rate-limited."},
        503: {"description": "Required login security component unavailable."},
    },
)
def submit_login_password_step(
    payload: SecureLoginSubmission,
    request: Request,
    response: Response,
) -> LoginPasswordStepAcknowledgment:
    """Issue a PENDING OTP challenge, never an authenticated login session.

    Important: File 56 must validate the signed CSRF cookie/header BEFORE
    this handler executes. Header presence alone does not verify the token.
    """
    response.headers["Cache-Control"] = "no-store"

    # An accidentally mounted router must not expose an incomplete login.
    if not PUBLIC_LOGIN_ENABLED or not LOGIN_SECURITY_COMPLETE:
        raise _http_error(404, "Not found.")

    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise _http_error(403, "Request origin is not permitted.")
    if not request.headers.get("x-csrf-token"):
        raise _http_error(403, "CSRF token required.")
    try:
        settings.require_csrf_key()
    except (RuntimeError, ValueError):
        raise _http_error(503, _TEMPORARY_ERROR) from None

    client_ip = _trusted_ip(request)
    agent = _safe_user_agent(request)

    # Blocked IPs are rejected without consuming request-quota slots.
    _check_ip_block(client_ip=client_ip, user_agent=agent)

    # File 82 counts every eligible password submission, including failed
    # CAPTCHAs. Do not perform expensive reCAPTCHA/Argon2 work if denied.
    _check_password_request_limit(client_ip=client_ip, user_agent=agent)

    if not _captcha_token_shape_valid(payload.captcha_token):
        _record_captcha_failure(
            client_ip=client_ip, user_agent=agent, reason="invalid_token_shape"
        )
    try:
        verifier = settings.build_recaptcha_v2_verifier(client_ip=client_ip)
        captcha_ok = verifier(payload.captcha_token)
    except Exception:
        raise _http_error(503, _TEMPORARY_ERROR) from None
    if captcha_ok is not True:
        _record_captcha_failure(
            client_ip=client_ip, user_agent=agent, reason="siteverify_rejected"
        )

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

    # A newly reached 3/6/9 tier produces one committed, trusted event ID.
    # Never take an alert recipient or event ID from browser-supplied JSON.
    _notify_new_lockout(decision.lockout_event_id)

    if decision.status in {"invalid_credentials", "locked"}:
        # The failed attempt was committed by File 75. Recheck so the exact
        # 14th failure can trigger File 72's 10-minute block immediately.
        _check_ip_block(client_ip=client_ip, user_agent=agent)

    if decision.status == "locked":
        raise _http_error(
            429,
            _TOO_MANY_ATTEMPTS,
            retry_after=max(1, int(decision.retry_after_seconds)),
        )
    if decision.status != "otp_required":
        # Same credentials error for unknown, incorrect, and ineligible users.
        raise _http_error(401, _INVALID_LOGIN)

    # File 71 sends the email and returns only internal user/OTP IDs.
    # File 70 binds those IDs to a signed HttpOnly PRE-AUTH cookie.
    from app.core.login_challenge import issue_login_challenge_cookie
    from app.services.login_otp_service import LoginOtpNotEligible, LoginOtpRateLimited
    from app.services.login_otp_workflow import (
        LoginOtpWorkflowUnavailable,
        begin_login_otp,
    )

    try:
        delivery = begin_login_otp(decision)
    except LoginOtpRateLimited as exc:
        raise _http_error(429, _TOO_MANY_ATTEMPTS,
                          retry_after=exc.retry_after_seconds) from None
    except (LoginOtpNotEligible, LoginOtpWorkflowUnavailable):
        raise _http_error(503, "Login verification is temporarily unavailable.") from None

    try:
        issue_login_challenge_cookie(
            response, user_id=delivery.user_id, otp_id=delivery.otp_id
        )
    except Exception:
        # Never report success when the pending challenge cookie is missing.
        raise _http_error(503, "Login verification is temporarily unavailable.") from None

    return LoginPasswordStepAcknowledgment(
        message="Verification code sent. Check your email.",
        verification_required=True,
    )
