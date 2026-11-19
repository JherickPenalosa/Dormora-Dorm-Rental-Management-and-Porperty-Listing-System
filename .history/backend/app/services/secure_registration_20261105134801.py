
"""Secure-registration coordinator for Dormora (Backend File 39).

Destination: backend/app/services/secure_registration.py

This module is NOT an API route and must not be mounted by itself.
It composes the existing database-backed registration rate limiter,
server-side CAPTCHA verification (provider injected by a future approved
adapter), security logging, and registration-with-email-OTP workflow.

Before enabling a public registration route, Dormora must still add the
handout's complete registration validations, privacy consent persistence,
security questions, approved CAPTCHA integration, and browser-side form.

Do not pass secrets or personal information into security event details.
"""

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.auth import RegisterRequest
from app.services.rate_limit_service import check_and_record_rate_limit
from app.services.registration import RegistrationResult
from app.services.registration_workflow import register_with_email_otp
from app.services.security_log_service import record_security_event

# A future API adapter must implement this with an instructor-approved CAPTCHA
# provider. A missing verifier fails closed; there is no development bypass.
CaptchaVerifier = Callable[[str], bool]


@dataclass(frozen=True)
class RegistrationSecurityRejected(Exception):
    """Static, safe rejection information for the future HTTP route.

    No submitted values, provider errors, or exception strings are retained.
    """

    code: str
    http_status: int
    retry_after_seconds: int = 0

    def __str__(self) -> str:
        return self.code


def _trusted_ip_address(client_ip: str) -> str:
    """Validate an IP supplied by trusted server networking configuration.

    The route must use Request.client.host after configuring trusted proxies.
    Never pass a client-supplied body field or untrusted forwarding header.
    """
    if not isinstance(client_ip, str):
        raise ValueError("A trusted IP address is required.")
    try:
        return str(ipaddress.ip_address(client_ip))
    except ValueError:
        raise ValueError("A valid trusted IP address is required.") from None


def _safe_user_agent(user_agent: str | None) -> str | None:
    """Omit malformed browser information rather than storing unsafe data."""
    if user_agent is None:
        return None
    if not isinstance(user_agent, str):
        raise ValueError("user_agent must be a string or None.")
    if not 1 <= len(user_agent) <= 512:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in user_agent):
        return None
    return user_agent


def _captcha_token_shape_valid(token: str) -> bool:
    """Reject an empty or malformed opaque CAPTCHA token locally."""
    return (
        isinstance(token, str)
        and 1 <= len(token) <= 2048
        and token.isascii()
        and all(33 <= ord(char) <= 126 for char in token)
    )


def check_registration_security(
    *,
    client_ip: str,
    captcha_token: str,
    captcha_verifier: CaptchaVerifier | None,
    user_agent: str | None = None,
) -> None:
    """Enforce rate limit and CAPTCHA before any registration database write.

    The rate limiter itself adds an audit event to public.security_logs.
    This method adds separate CAPTCHA success/failure audit events and fails
    closed if the configured CAPTCHA provider or security logger fails.

    NOTE: 'check' here is not read-only: successful and rejected attempts
    can add rows to public.security_logs, but no user account is created.
    """
    ip_address = _trusted_ip_address(client_ip)
    agent = _safe_user_agent(user_agent)

    if captcha_verifier is None or not callable(captcha_verifier):
        raise RegistrationSecurityRejected("captcha_unavailable", 503)

    try:
        decision = check_and_record_rate_limit(
            "registration", client_ip=ip_address
        )
    except Exception:
        # If PostgreSQL or security logging is unavailable, never bypass the
        # registration limiter. Do not disclose database exception details.
        raise RegistrationSecurityRejected("security_unavailable", 503) from None

    if not decision.allowed:
        raise RegistrationSecurityRejected(
            "rate_limited", 429, max(1, decision.retry_after_seconds)
        )

    if not _captcha_token_shape_valid(captcha_token):
        try:
            record_security_event(
                event_type="captcha_failed",
                outcome="failure",
                ip_address=ip_address,
                user_agent=agent,
                event_details={"reason": "captcha_failed", "channel": "web"},
            )
        except Exception:
            raise RegistrationSecurityRejected("security_unavailable", 503) from None
        raise RegistrationSecurityRejected("captcha_invalid", 400)

    try:
        # The future adapter must do actual server-to-provider verification,
        # including checking the fixed expected hostname/action where available.
        passed = captcha_verifier(captcha_token)
    except Exception:
        try:
            record_security_event(
                event_type="captcha_unavailable",
                outcome="failure",
                ip_address=ip_address,
                user_agent=agent,
                event_details={"reason": "service_unavailable", "channel": "web"},
            )
        except Exception:
            pass
        raise RegistrationSecurityRejected("captcha_unavailable", 503) from None

    if passed is not True:
        try:
            record_security_event(
                event_type="captcha_failed",
                outcome="failure",
                ip_address=ip_address,
                user_agent=agent,
                event_details={"reason": "captcha_failed", "channel": "web"},
            )
        except Exception:
            raise RegistrationSecurityRejected("security_unavailable", 503) from None
        raise RegistrationSecurityRejected("captcha_invalid", 400)

    try:
        record_security_event(
            event_type="registration.security_passed",
            outcome="info",
            ip_address=ip_address,
            user_agent=agent,
            event_details={"channel": "web"},
        )
    except Exception:
        raise RegistrationSecurityRejected("security_unavailable", 503) from None


def register_pending_account_securely(
    payload: RegisterRequest,
    *,
    client_ip: str,
    captcha_token: str,
    captcha_verifier: CaptchaVerifier | None,
    user_agent: str | None = None,
) -> RegistrationResult:
    """Check security controls, then use the existing registration + OTP flow.

    This is an INTERNAL coordinator, not yet safe to expose publicly:
    privacy consent, three question hashes, instructor-seeded registration
    rules, and an approved CAPTCHA adapter must first be implemented.
    The caller must separately enforce CSRF at the HTTP middleware layer.

    Registration and security logging use separate transactions. Later
    integration must handle partial progress without blindly retrying a
    registration if email delivery or a post-creation audit write fails.
    """
    if not isinstance(payload, RegisterRequest):
        raise TypeError("A validated RegisterRequest is required.")

    check_registration_security(
        client_ip=client_ip,
        captcha_token=captcha_token,
        captcha_verifier=captcha_verifier,
        user_agent=user_agent,
    )

    # Uses File 23: atomic user/profile creation, 6-digit OTP issuance,
    # SMTP delivery, and update of OTP delivery status. Account stays pending.
    return register_with_email_otp(payload)
