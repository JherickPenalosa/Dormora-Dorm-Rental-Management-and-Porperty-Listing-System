"""Dormora File 71: coordinate login OTP storage and email delivery.

Create: backend/app/services/login_otp_workflow.py
Called by protected routes only. No routes, cookies or sessions are created.
After success, the route binds the returned IDs with File 70's cookie helper.
Do not enable File 67 until the remaining login protections are integrated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.core.login_challenge import CHALLENGE_TTL_SECONDS, LoginChallenge
from app.services.login_email_service import send_login_otp_email
from app.services.login_otp_service import (
    LoginOtpNotEligible,
    LoginOtpRateLimited,
    issue_login_otp,
    mark_login_otp_failed,
    mark_login_otp_sent,
)
from app.services.login_service import PasswordStepDecision


class LoginOtpWorkflowUnavailable(RuntimeError):
    """Generic failure; the HTTP layer must not expose underlying exceptions."""


@dataclass(frozen=True)
class LoginOtpDelivery:
    """Internal result for cookie creation; no plaintext OTP or email address."""
    user_id: int
    otp_id: int
    expires_at: datetime


def _preflight() -> None:
    """Check configuration before creating a code or attempting delivery."""
    settings.require_smtp_configuration()
    settings.require_otp_hmac_key()
    settings.require_csrf_key()
    if settings.smtp_security not in {"ssl", "starttls"}:
        raise RuntimeError("Encrypted SMTP is required.")


def _revoke_pending(otp_id: int) -> None:
    """Try to invalidate an undelivered code without masking the main error.

    If storage is unavailable, pending codes still cannot pass File 68's
    verification. A later database failure after marking sent may leave a
    sent code until expiry; this workflow still returns no successful result.
    """
    try:
        mark_login_otp_failed(otp_id)
    except Exception:
        pass


def _deliver(user_id: int, *, previous_otp_id: int | None = None,
             challenge_deadline: int | None = None) -> LoginOtpDelivery:
    issued = None
    try:
        _preflight()
        issued = issue_login_otp(user_id, previous_otp_id=previous_otp_id)
        send_login_otp_email(issued)
        # SMTP acceptance may take time. Never acknowledge an expired code
        # or extend an expired browser challenge after a slow email operation.
        if issued.expires_at <= datetime.now(timezone.utc):
            raise LoginOtpWorkflowUnavailable("Login verification is temporarily unavailable.")
        if challenge_deadline is not None and time.time() >= challenge_deadline:
            raise LoginOtpNotEligible("Login verification must be restarted.")
        if mark_login_otp_sent(issued.otp_id) is not True:
            raise LoginOtpWorkflowUnavailable("Login verification is temporarily unavailable.")
        return LoginOtpDelivery(user_id, issued.otp_id, issued.expires_at)
    except (LoginOtpNotEligible, LoginOtpRateLimited):
        if issued is not None:
            _revoke_pending(issued.otp_id)
        raise
    except Exception:
        if issued is not None:
            _revoke_pending(issued.otp_id)
        # No automatic retry: SMTP failures can have uncertain delivery.
        raise LoginOtpWorkflowUnavailable(
            "Login verification is temporarily unavailable."
        ) from None


def begin_login_otp(decision: PasswordStepDecision) -> LoginOtpDelivery:
    """Call with File 66's successful result, after all HTTP checks pass.

    Never construct this decision from browser input. A Python dataclass is
    not an authorization credential; the protected route must actually run
    password verification before calling this function.
    """
    if (not isinstance(decision, PasswordStepDecision)
            or decision.status != "otp_required"
            or type(decision.user_id) is not int or decision.user_id <= 0):
        raise LoginOtpNotEligible("Login verification is unavailable.")
    return _deliver(decision.user_id)


def resend_login_otp(challenge: LoginChallenge) -> LoginOtpDelivery:
    """Use only a challenge verified by File 70 from the current request.

    File 68 checks the exact previous OTP and enforces resend limits.
    After success, replace the cookie using File 70's replacement helper,
    preserving its original start time. Failed resends return no new IDs.
    """
    if (not isinstance(challenge, LoginChallenge)
            or type(challenge.user_id) is not int or challenge.user_id <= 0
            or type(challenge.otp_id) is not int or challenge.otp_id <= 0
            or type(challenge.started_at) is not int):
        raise LoginOtpNotEligible("Login verification must be restarted.")
    age = time.time() - challenge.started_at
    if not 0 <= age < CHALLENGE_TTL_SECONDS:
        raise LoginOtpNotEligible("Login verification must be restarted.")
    return _deliver(
        challenge.user_id, previous_otp_id=challenge.otp_id,
        challenge_deadline=challenge.started_at + CHALLENGE_TTL_SECONDS,
    )