
"""Dormora Backend File 48: bind Google reCAPTCHA v2 to secure registration.

Destination: backend/app/services/secure_registration.py (REPLACE File 45).

This INTERNAL coordinator checks the PostgreSQL-backed registration limiter,
verifies Google reCAPTCHA v2 server-side, audits outcomes, and delegates to
File 44's strict registration + email OTP workflow. A trusted verifier is
constructed exclusively from private File 47 settings (which uses File 46).
Callers cannot inject an always-True CAPTCHA verifier.

This module adds no FastAPI routes and changes no tables. Importing it does not
create users, send email, or verify any token. Actual calls do write security
logs; an accepted registration eventually creates a pending account.

Do NOT mount public registration yet: the real Privacy Notice, instructor-
approved system-specific registration fields, seeded OTP expiry/attempt rules,
and end-to-end CSRF/browser testing remain outstanding.
"""

import ipaddress
from dataclasses import dataclass

from app.core.config import settings
from app.schemas.auth import HandoutRegisterRequest
from app.services.rate_limit_service import check_and_record_rate_limit
from app.services.registration import RegistrationResult
from app.services.registration_workflow import register_with_email_otp
from app.services.security_log_service import record_security_event


@dataclass(frozen=True)
class RegistrationSecurityRejected(Exception):
    """Safe, static error information for a future HTTP route."""

    code: str
    http_status: int
    retry_after_seconds: int = 0

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class RegistrationSecurityContext:
    """Validated request metadata forwarded into Files 44 and 42."""

    client_ip: str
    user_agent: str | None


def _trusted_ip_address(value: str) -> str:
    """Normalize a server-resolved IP, never an untrusted forwarding header."""
    if not isinstance(value, str):
        raise ValueError("A trusted client IP address is required.")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise ValueError("A valid trusted IPv4 or IPv6 address is required.") from None


def _safe_user_agent(value: str | None) -> str | None:
    """Omit malformed user-agent metadata rather than logging unsafe text."""
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
    """Check token syntax only; ONLY Google's Siteverify decides validity."""
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 8192
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
    """Log only File 27 allowlisted metadata; never record a CAPTCHA token."""
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


def _record_failure_or_stop(
    *,
    event_type: str,
    context: RegistrationSecurityContext,
    reason: str,
    reject_code: str,
    http_status: int,
) -> None:
    """Audit a rejected attempt; fail closed if its required log cannot be stored."""
    try:
        _audit_captcha_event(
            event_type=event_type,
            outcome="failure",
            context=context,
            reason=reason,
        )
    except Exception:
        raise RegistrationSecurityRejected("security_unavailable", 503) from None
    raise RegistrationSecurityRejected(reject_code, http_status)


def check_registration_security(
    *,
    client_ip: str,
    captcha_token: str,
    user_agent: str | None = None,
) -> RegistrationSecurityContext:
    """Verify rate limit and configured Google reCAPTCHA before registration.

    A CAPTCHA verifier is ALWAYS built internally from private settings, with
    a validated server-resolved client IP. Callers cannot supply a fake verifier.
    Each real call consumes a registration rate-limit attempt in PostgreSQL.
    Token failures, provider outages and successes are separately audited.
    """
    context = RegistrationSecurityContext(
        client_ip=_trusted_ip_address(client_ip),
        user_agent=_safe_user_agent(user_agent),
    )

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
        _record_failure_or_stop(
            event_type="captcha_failed",
            context=context,
            reason="captcha_failed",
            reject_code="captcha_invalid",
            http_status=400,
        )

    try:
        # File 47 checks that a real private key and fixed hostname exist.
        # File 46 contacts Google's HTTPS Siteverify API when invoked.
        verifier = settings.build_recaptcha_v2_verifier(
            client_ip=context.client_ip
        )
    except Exception:
        _record_failure_or_stop(
            event_type="captcha_unavailable",
            context=context,
            reason="service_unavailable",
            reject_code="captcha_unavailable",
            http_status=503,
        )

    try:
        verified = verifier(captcha_token)
    except Exception:
        # Never expose the provider's response, secret, or exception text.
        _record_failure_or_stop(
            event_type="captcha_unavailable",
            context=context,
            reason="service_unavailable",
            reject_code="captcha_unavailable",
            http_status=503,
        )

    if verified is not True:
        _record_failure_or_stop(
            event_type="captcha_failed",
            context=context,
            reason="captcha_failed",
            reject_code="captcha_invalid",
            http_status=400,
        )

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
    user_agent: str | None = None,
) -> RegistrationResult:
    """Delegate a strictly validated, CAPTCHA-approved registration to File 44.

    INTERNAL SERVICE ONLY. The future FastAPI route must also require CSRF,
    enforce system-specific fields and privacy notice, and map errors safely.
    Never retry registration automatically after a partial OTP/SMTP failure.
    """
    if not isinstance(payload, HandoutRegisterRequest):
        raise TypeError("HandoutRegisterRequest is required for registration.")
    if payload.privacy_consent is not True or payload.website != "":
        raise RegistrationSecurityRejected("registration_rejected", 400)

    context = check_registration_security(
        client_ip=client_ip,
        captcha_token=captcha_token,
        user_agent=user_agent,
    )

    return register_with_email_otp(
        payload,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
    )
