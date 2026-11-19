
"""Dormora Backend File 45: secure registration coordinator refinement.

Destination: backend/app/services/secure_registration.py (REPLACE File 39).

Connects File 28 (database-backed registration rate limit), File 27 (safe
security-event logging), and File 44 (strict account + email-OTP workflow).
No routes are mounted, and no tables or existing records are changed by
importing this module. The functions DO write if called with real services.

Do not enable the public registration endpoint until the approved CAPTCHA,
privacy notice, system-specific field requirements, and seeded OTP rules are
integrated and tested. A future route must enforce CSRF (File 37) and supply
an instructor-approved, genuinely server-side CAPTCHA verifier.
"""

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.auth import HandoutRegisterRequest
from app.services.rate_limit_service import check_and_record_rate_limit
from app.services.registration import RegistrationResult
from app.services.registration_workflow import register_with_email_otp
from app.services.security_log_service import record_security_event


# The future HTTP adapter must bind its trusted provider, hostname, and action.
# Do not use an always-True lambda or a client-reported CAPTCHA success value.
CaptchaVerifier = Callable[[str], bool]


@dataclass(frozen=True)
class RegistrationSecurityRejected(Exception):
    """Safe machine-readable failure for a later API route; no user input."""

    code: str
    http_status: int
    retry_after_seconds: int = 0

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class RegistrationSecurityContext:
    """Validated request metadata to carry into File 44 / File 42."""

    client_ip: str
    user_agent: str | None


def _trusted_ip_address(value: str) -> str:
    """Normalize a server-resolved IP, never a user-controlled forwarded IP."""
    if not isinstance(value, str):
        raise ValueError("A trusted client IP address is required.")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise ValueError("A valid trusted IPv4 or IPv6 address is required.") from None


def _safe_user_agent(value: str | None) -> str | None:
    """Drop missing/malformed browser metadata instead of persisting it."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("User agent must be a string or None.")
    if not 1 <= len(value) <= 512:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return value


def _captcha_token_shape_valid(value: str) -> bool:
    """Validate opaque token format locally; only the provider checks validity."""
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 2048
        and value.isascii()
        and all(33 <= ord(char) <= 126 for char in value)
    )


def _audit_captcha_event(
    *,
    event_type: str,
    outcome: str,
    context: RegistrationSecurityContext,
    reason: str | None = None,
) -> None:
    """Use File 27's allowlisted fields; never record tokens or exceptions."""
    details = {"channel": "web"}
    if reason is not None:
        details["reason"] = reason
    record_security_event(
        event_type=event_type,
        outcome=outcome,
        ip_address=context.client_ip,
        user_agent=context.user_agent,
        event_details=details,
    )


def check_registration_security(
    *,
    client_ip: str,
    captcha_token: str,
    captcha_verifier: CaptchaVerifier | None,
    user_agent: str | None = None,
) -> RegistrationSecurityContext:
    """Enforce registration rate limit, then a real server-side CAPTCHA.

    Returns sanitized metadata for downstream registration audit events.
    Consumes one registration rate-limit attempt even for invalid CAPTCHA.
    Stops on database, audit, or CAPTCHA provider failures (fail-closed).

    This function performs security-log writes with real backend services;
    the unit test mocks those writers and changes no database records.
    """
    context = RegistrationSecurityContext(
        client_ip=_trusted_ip_address(client_ip),
        user_agent=_safe_user_agent(user_agent),
    )

    if captcha_verifier is None or not callable(captcha_verifier):
        raise RegistrationSecurityRejected("captcha_unavailable", 503)

    try:
        decision = check_and_record_rate_limit(
            "registration", client_ip=context.client_ip
        )
    except Exception:
        raise RegistrationSecurityRejected("security_unavailable", 503) from None

    if not decision.allowed:
        raise RegistrationSecurityRejected(
            "rate_limited", 429, max(1, decision.retry_after_seconds)
        )

    if not _captcha_token_shape_valid(captcha_token):
        try:
            _audit_captcha_event(
                event_type="captcha_failed",
                outcome="failure",
                context=context,
                reason="captcha_failed",
            )
        except Exception:
            raise RegistrationSecurityRejected("security_unavailable", 503) from None
        raise RegistrationSecurityRejected("captcha_invalid", 400)

    try:
        # Only a trusted provider adapter may supply this verdict. In
        # particular, do not interpret a frontend boolean as verification.
        accepted = captcha_verifier(captcha_token)
    except Exception:
        try:
            _audit_captcha_event(
                event_type="captcha_unavailable",
                outcome="failure",
                context=context,
                reason="service_unavailable",
            )
        except Exception:
            raise RegistrationSecurityRejected("security_unavailable", 503) from None
        raise RegistrationSecurityRejected("captcha_unavailable", 503) from None

    if accepted is not True:
        try:
            _audit_captcha_event(
                event_type="captcha_failed",
                outcome="failure",
                context=context,
                reason="captcha_failed",
            )
        except Exception:
            raise RegistrationSecurityRejected("security_unavailable", 503) from None
        raise RegistrationSecurityRejected("captcha_invalid", 400)

    try:
        _audit_captcha_event(
            event_type="registration.security_passed",
            outcome="info",
            context=context,
        )
    except Exception:
        raise RegistrationSecurityRejected("security_unavailable", 503) from None

    return context


def register_pending_account_securely(
    payload: HandoutRegisterRequest,
    *,
    client_ip: str,
    captcha_token: str,
    captcha_verifier: CaptchaVerifier | None,
    user_agent: str | None = None,
) -> RegistrationResult:
    """Validate registration prerequisites, then delegate to File 44.

    The real File 42 persistence service accepts only HandoutRegisterRequest;
    this coordinator checks the same rule before touching security logs.
    Once File 44 commits a pending account, an OTP/email failure must NOT
    trigger automatic re-registration; an OTP resend flow is required.

    This coordinator is INTERNAL ONLY. The future public route must also
    provide CSRF, the approved CAPTCHA adapter, safe error mappings,
    privacy notice, and required role-specific registration fields.
    """
    if not isinstance(payload, HandoutRegisterRequest):
        raise TypeError("HandoutRegisterRequest is required for registration.")
    if payload.privacy_consent is not True or payload.website != "":
        raise RegistrationSecurityRejected("registration_rejected", 400)

    context = check_registration_security(
        client_ip=client_ip,
        captcha_token=captcha_token,
        captcha_verifier=captcha_verifier,
        user_agent=user_agent,
    )

    return register_with_email_otp(
        payload,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )
