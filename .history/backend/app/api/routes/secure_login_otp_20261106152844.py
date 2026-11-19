
"""Dormora Backend File 84 -- rate-limited login OTP verification API (DISABLED).

REPLACE: backend/app/api/routes/secure_login_otp.py (previously File 80).

This route connects:
- File 70: signed, HttpOnly PENDING login challenge cookie.
- File 72: PostgreSQL-backed IP block check.
- File 82: per-IP OTP verification request limit (8 per minute).
- File 79: OTP consumption + auth-session creation in ONE transaction.
- File 77: authenticated-session cookie, set ONLY after commit.

PUBLIC SAFETY GATES:
- Importing this router does not mount it or enable login.
- LOGIN_OTP_VERIFY_ENABLED stays False until the complete login flow is
  mounted, CSRF-verified, and end-to-end tested.
- File 76's two public-login switches must also remain False until then.
- File 56's signed CSRF middleware MUST validate cookie + request header.
  Checking header presence here is NOT CSRF verification by itself.
- File 82 limits OTP verification request volume; File 68 independently
  limits wrong attempts per issued code to three. Neither replaces CSRF.
- File 82 also defines an OTP resend request limit for a future resend API.

No raw OTP, account ID, session bearer, or challenge ID is sent in JSON.
Do not log secrets or assume that importing this file enables the endpoint.
"""

from __future__ import annotations

from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.api.routes import secure_login
from app.core.config import settings


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# An independent explicit gate, in addition to File 76's two switches.
LOGIN_OTP_VERIFY_ENABLED = False

_CACHE_HEADERS = {"Cache-Control": "no-store"}
_UNAVAILABLE = "Login verification is temporarily unavailable."
_RESTART = "Login verification must be restarted."


class LoginOtpVerificationSubmission(BaseModel):
    """The OTP is the only browser-supplied identifier for this endpoint.

    user_id and otp_id MUST come exclusively from File 70's signed cookie.
    A malformed code still reaches File 68, which records an unsuccessful
    entry against the three-attempt limit (unless over the input size bound).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    code: str = Field(
        min_length=1,
        max_length=64,
        repr=False,
        exclude=True,
        validation_alias=AliasChoices("code", "otpCode", "otp_code"),
    )


class LoginOtpVerificationAcknowledgment(BaseModel):
    """Public success response with no account/session secrets."""

    message: str
    authenticated: bool


def _http_error(code: int, detail: str, *, retry_after: int = 0) -> HTTPException:
    headers = dict(_CACHE_HEADERS)
    if retry_after > 0:
        headers["Retry-After"] = str(min(max(int(retry_after), 1), 86400))
    return HTTPException(status_code=code, detail=detail, headers=headers)


def _trusted_ip(request: Request) -> str:
    """Never trust X-Forwarded-For or an IP supplied in request JSON."""
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
    return "".join(ch for ch in agent if ch.isprintable())[:255] or None


def _check_otp_verify_request_limit(*, client_ip: str, user_agent: str | None) -> None:
    """File 82: count attempts before reading the challenge or checking OTP.

    Limit: eight OTP verification requests per 60 seconds per trusted IP,
    independent of File 68's three wrong-code attempts per OTP.
    """
    from app.services.login_request_limit_service import (
        LoginRequestLimiterUnavailable,
        check_and_record_login_request,
    )

    try:
        decision = check_and_record_login_request(
            "otp_verify", client_ip=client_ip, user_agent=user_agent
        )
    except (LoginRequestLimiterUnavailable, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None

    if not decision.allowed:
        raise _http_error(
            429,
            "Too many attempts. Please try again later.",
            retry_after=max(1, int(decision.retry_after_seconds)),
        )


@router.post(
    "/login/verify-otp",
    status_code=status.HTTP_200_OK,
    response_model=LoginOtpVerificationAcknowledgment,
    summary="Rate-limited two-step email login (disabled pending full integration)",
    responses={
        401: {"description": "Invalid, expired, or consumed OTP/challenge."},
        403: {"description": "Origin or signed CSRF rejected."},
        404: {"description": "Public login not enabled."},
        422: {"description": "Invalid request fields."},
        429: {"description": "Client IP blocked or OTP request quota reached."},
        503: {"description": "Verification or session storage unavailable."},
    },
)
def verify_login_otp_endpoint(
    payload: LoginOtpVerificationSubmission,
    request: Request,
    response: Response,
) -> LoginOtpVerificationAcknowledgment:
    """Only a committed successful OTP can issue an authenticated cookie.

    File 79 commits the OTP + session + login audit atomically. This endpoint
    MUST NOT set the authenticated cookie until that service has returned.
    """
    response.headers["Cache-Control"] = "no-store"

    # Defense in depth if the router is accidentally mounted during development.
    if (
        not LOGIN_OTP_VERIFY_ENABLED
        or not secure_login.PUBLIC_LOGIN_ENABLED
        or not secure_login.LOGIN_SECURITY_COMPLETE
    ):
        raise _http_error(404, "Not found.")

    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise _http_error(403, "Request origin is not permitted.")
    if not request.headers.get("x-csrf-token"):
        raise _http_error(403, "CSRF token required.")
    try:
        settings.require_csrf_key()
    except (ValueError, RuntimeError):
        raise _http_error(503, _UNAVAILABLE) from None

    # File 56 MUST additionally validate the signed CSRF cookie/header pair.
    client_ip = _trusted_ip(request)
    agent = _safe_agent(request)

    from app.services.login_ip_service import (
        LoginIpServiceUnavailable,
        check_login_ip,
    )

    try:
        ip_state = check_login_ip(client_ip, user_agent=agent)
    except (LoginIpServiceUnavailable, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None
    if not ip_state.allowed:
        raise _http_error(
            429,
            "Too many attempts. Please try again later.",
            retry_after=max(1, int(ip_state.retry_after_seconds)),
        )

    # Count the request before parsing any signed login challenge or checking
    # the OTP. A blocked IP does not consume an additional request quota slot.
    _check_otp_verify_request_limit(client_ip=client_ip, user_agent=agent)

    from app.core.login_challenge import (
        InvalidLoginChallenge,
        clear_login_challenge_cookie,
        read_login_challenge,
    )

    try:
        challenge = read_login_challenge(request)
    except InvalidLoginChallenge:
        raise _http_error(401, _RESTART) from None
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    from app.services.login_completion_service import (
        LoginCompletionRejected,
        LoginCompletionUnavailable,
        complete_login_otp,
    )

    try:
        completed = complete_login_otp(
            challenge,
            payload.code,
            client_ip=client_ip,
            user_agent=agent,
        )
    except LoginCompletionRejected:
        raise _http_error(401, _RESTART) from None
    except LoginCompletionUnavailable:
        raise _http_error(503, _UNAVAILABLE) from None

    if completed is None:
        # File 68 has persisted this wrong OTP attempt before returning False.
        # A wrong OTP, consumed OTP, or expired OTP NEVER creates a session.
        raise _http_error(401, "Invalid or expired verification code.")

    from app.core.session_security import set_session_cookie

    try:
        # The database transaction already COMMITTED in File 79.
        set_session_cookie(response, token=completed.session_token)
        clear_login_challenge_cookie(response)
    except Exception:
        # An orphaned DB session cannot authenticate without its raw token.
        # FastAPI will send the error response, not this response's cookies.
        raise _http_error(503, _UNAVAILABLE) from None

    return LoginOtpVerificationAcknowledgment(
        message="Login successful.",
        authenticated=True,
    )
