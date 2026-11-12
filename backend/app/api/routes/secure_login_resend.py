
"""Dormora Backend File 85 -- rate-limited login OTP resend API (DISABLED).

CREATE: backend/app/api/routes/secure_login_resend.py

Provides POST /api/auth/login/resend-otp for an existing, signed pending
login challenge. It connects:
- File 70: read/replace signed HttpOnly pre-auth cookie without extending age.
- File 72: seeded IP blocking across failed password attempts.
- File 82: 12 resend requests per 15 minutes per trusted client IP.
- Files 68/71: account-specific 60-second cooldown, three resends per
  15 minutes, OTP invalidation, SMTP delivery, and send failure handling.

This route never creates authenticated sessions, accepts user/OTP IDs from
request JSON, or returns the OTP in its response. File 70's cookie remains
PRE-AUTHENTICATION ONLY. Importing this module does not mount or activate it.

All login safety gates remain disabled until File 56's signed CSRF middleware,
router mounting, session lifecycle, and full end-to-end tests are complete.
An x-csrf-token header by itself is NOT sufficient CSRF verification.
"""

from __future__ import annotations

from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.routes import secure_login, secure_login_otp
from app.core.config import settings


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Independent safety switch: do not activate independently of Files 83/84.
LOGIN_OTP_RESEND_ENABLED = False

_CACHE_HEADERS = {"Cache-Control": "no-store"}
_UNAVAILABLE = "Login verification is temporarily unavailable."
_RESTART = "Login verification must be restarted."
_RATE_LIMITED = "Too many attempts. Please try again later."


class LoginOtpResendAcknowledgment(BaseModel):
    """No user ID, OTP, email address, or bearer credential in JSON."""

    message: str
    verification_required: bool


def _http_error(code: int, detail: str, *, retry_after: int = 0) -> HTTPException:
    headers = dict(_CACHE_HEADERS)
    if retry_after > 0:
        headers["Retry-After"] = str(min(max(int(retry_after), 1), 86400))
    return HTTPException(status_code=code, detail=detail, headers=headers)


def _trusted_ip(request: Request) -> str:
    """Read the ASGI peer address, never browser-provided forwarded headers."""
    if request.client is None:
        raise _http_error(503, _UNAVAILABLE)
    try:
        parsed = ip_address(request.client.host)
        mapped = getattr(parsed, "ipv4_mapped", None)
        return str(mapped if mapped is not None else parsed)
    except (TypeError, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None


def _safe_agent(request: Request) -> str | None:
    agent = request.headers.get("user-agent")
    if not isinstance(agent, str):
        return None
    return "".join(char for char in agent if char.isprintable())[:255] or None


def _check_ip_block(*, client_ip: str, user_agent: str | None) -> None:
    from app.services.login_ip_service import (
        LoginIpServiceUnavailable,
        check_login_ip,
    )

    try:
        decision = check_login_ip(client_ip, user_agent=user_agent)
    except (LoginIpServiceUnavailable, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None
    if not decision.allowed:
        raise _http_error(
            429,
            _RATE_LIMITED,
            retry_after=max(1, int(decision.retry_after_seconds)),
        )


def _check_resend_request_limit(*, client_ip: str, user_agent: str | None) -> None:
    """File 82 protects the endpoint independently of per-account cooldowns."""
    from app.services.login_request_limit_service import (
        LoginRequestLimiterUnavailable,
        check_and_record_login_request,
    )

    try:
        decision = check_and_record_login_request(
            "otp_resend", client_ip=client_ip, user_agent=user_agent
        )
    except (LoginRequestLimiterUnavailable, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None
    if not decision.allowed:
        raise _http_error(
            429,
            _RATE_LIMITED,
            retry_after=max(1, int(decision.retry_after_seconds)),
        )


@router.post(
    "/login/resend-otp",
    status_code=status.HTTP_200_OK,
    response_model=LoginOtpResendAcknowledgment,
    summary="Resend a pending login OTP (disabled pending full integration)",
    responses={
        401: {"description": "Missing, expired or invalid login challenge."},
        403: {"description": "Origin or signed CSRF rejected."},
        404: {"description": "Public login remains disabled."},
        429: {"description": "Client IP blocked, quota reached, or OTP cooldown."},
        503: {"description": "Login security or email delivery unavailable."},
    },
)
def resend_login_otp_endpoint(
    request: Request,
    response: Response,
) -> LoginOtpResendAcknowledgment:
    """Resend only for the browser's VALID signed pre-login challenge.

    HTTP protection checks and per-IP request limiting occur before reading
    the challenge or contacting SMTP. Files 68/71 validate the account, old
    OTP ID, resend cooldown and window, invalidate the old OTP, and send a new
    code. File 70 replaces the pending cookie WITHOUT resetting its original
    15-minute deadline. No authenticated session is created by this route.
    """
    response.headers["Cache-Control"] = "no-store"

    # Defense in depth: even accidental mounting cannot expose incomplete auth.
    if (
        not LOGIN_OTP_RESEND_ENABLED
        or not secure_login.PUBLIC_LOGIN_ENABLED
        or not secure_login.LOGIN_SECURITY_COMPLETE
        or not secure_login_otp.LOGIN_OTP_VERIFY_ENABLED
    ):
        raise _http_error(404, "Not found.")

    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise _http_error(403, "Request origin is not permitted.")
    if not request.headers.get("x-csrf-token"):
        raise _http_error(403, "CSRF token required.")
    try:
        settings.require_csrf_key()
    except (RuntimeError, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None

    # File 56 must have ALREADY validated the signed CSRF cookie/header pair.
    client_ip = _trusted_ip(request)
    agent = _safe_agent(request)
    _check_ip_block(client_ip=client_ip, user_agent=agent)
    _check_resend_request_limit(client_ip=client_ip, user_agent=agent)

    from app.core.login_challenge import (
        InvalidLoginChallenge,
        read_login_challenge,
        replace_login_challenge_cookie,
    )
    from app.services.login_otp_service import LoginOtpNotEligible, LoginOtpRateLimited
    from app.services.login_otp_workflow import (
        LoginOtpWorkflowUnavailable,
        resend_login_otp,
    )

    try:
        challenge = read_login_challenge(request)
    except InvalidLoginChallenge:
        raise _http_error(401, _RESTART) from None
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    try:
        delivery = resend_login_otp(challenge)
    except LoginOtpRateLimited as exc:
        # File 68 enforces 60-second cooldown and max 3 resends/15 minutes.
        raise _http_error(
            429,
            "Please wait before requesting another login code.",
            retry_after=exc.retry_after_seconds,
        ) from None
    except LoginOtpNotEligible:
        raise _http_error(401, _RESTART) from None
    except LoginOtpWorkflowUnavailable:
        raise _http_error(503, _UNAVAILABLE) from None

    if (
        type(delivery.user_id) is not int
        or delivery.user_id != challenge.user_id
        or type(delivery.otp_id) is not int
        or delivery.otp_id <= 0
    ):
        raise _http_error(503, _UNAVAILABLE)

    try:
        # File 70 rechecks the signed cookie and preserves its original start.
        # A challenge that expired during SMTP delivery cannot be extended.
        replace_login_challenge_cookie(
            request, response, new_otp_id=delivery.otp_id
        )
    except InvalidLoginChallenge:
        raise _http_error(401, _RESTART) from None
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    return LoginOtpResendAcknowledgment(
        message="A new verification code has been sent.",
        verification_required=True,
    )
