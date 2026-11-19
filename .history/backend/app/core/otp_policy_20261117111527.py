"""Dormora — email OTP policy.

Install as: backend/app/core/otp_policy.py (REPLACE EXISTING FILE)

Current uniform instructor setting:
    - OTP expires after 5 minutes, with a strict expiration boundary.

Existing security policy retained:
    - 6 cryptographically random digits (generation remains in otp_security.py)
    - 3 incorrect attempts exhaust the code, including a later correct entry
    - a new code revokes the old one; a successful code is single use
    - resend cooldown 60 seconds, maximum 3 resends per 15 minutes

This is a PURE POLICY module: actual enforcement belongs to the OTP service
and its database transactions. Legacy STUDENT_D1 and STUDENT_D2 values remain
for compatibility but no longer determine OTP expiration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Literal, Sequence


STUDENT_D1 = 9
STUDENT_D2 = 6
OTP_DIGITS = 6
OTP_EXPIRY_MINUTES = 5
OTP_MAX_FAILED_ATTEMPTS = 3
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_RESENDS = 3
OTP_RESEND_WINDOW_MINUTES = 15
OTP_PURPOSES = frozenset({"registration", "login", "password_reset"})

OtpStateReason = Literal[
    "ready", "not_sent", "expired", "already_used", "invalidated",
    "attempts_exhausted",
]
ResendReason = Literal["allowed", "cooldown", "resend_limit"]


@dataclass(frozen=True)
class OtpStateDecision:
    allowed: bool
    reason: OtpStateReason


@dataclass(frozen=True)
class OtpFailureDecision:
    failed_attempts: int
    invalidate: bool


@dataclass(frozen=True)
class OtpResendDecision:
    allowed: bool
    reason: ResendReason
    retry_after_seconds: int = 0


def utc_now() -> datetime:
    """Use aware UTC times for policy calculations; never local naive time."""
    return datetime.now(timezone.utc)


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime.")
    if value.utcoffset() is None:
        raise ValueError(f"{name} must have a valid UTC offset.")
    return value.astimezone(timezone.utc)


def check_purpose(purpose: str) -> str:
    """Validate which authentication flow may use this policy."""
    if purpose not in OTP_PURPOSES:
        raise ValueError("Unsupported OTP purpose.")
    return purpose


def expires_at_for(issued_at: datetime) -> datetime:
    """Return the precise OTP expiry time in UTC."""
    return _utc(issued_at, "issued_at") + timedelta(minutes=OTP_EXPIRY_MINUTES)


def check_otp_state(
    *,
    expires_at: datetime,
    failed_attempts: int,
    delivery_status: str,
    consumed: bool,
    invalidated: bool,
    now: datetime,
) -> OtpStateDecision:
    """Check DB-derived OTP state *before* comparing the HMAC digest.

    Callers must lock/re-read the OTP row inside a transaction. Never trust
    these attributes from a form. Successful verification must atomically
    consume this code, while incorrect verification must record a failure.
    """
    expiry = _utc(expires_at, "expires_at")
    current = _utc(now, "now")
    if type(failed_attempts) is not int or failed_attempts < 0:
        raise ValueError("failed_attempts must be a nonnegative integer.")
    if type(consumed) is not bool or type(invalidated) is not bool:
        raise ValueError("OTP usage flags must be booleans.")
    if not isinstance(delivery_status, str):
        raise ValueError("OTP delivery status must be a string.")

    # An older or replaced code is invalid even if the displayed code matches.
    if invalidated:
        return OtpStateDecision(False, "invalidated")
    if consumed:
        return OtpStateDecision(False, "already_used")
    if failed_attempts >= OTP_MAX_FAILED_ATTEMPTS:
        return OtpStateDecision(False, "attempts_exhausted")
    if current >= expiry:
        return OtpStateDecision(False, "expired")
    if delivery_status != "sent":
        return OtpStateDecision(False, "not_sent")
    return OtpStateDecision(True, "ready")


def after_failed_code(failed_attempts: int) -> OtpFailureDecision:
    """Compute next failed-attempt count; third wrong code invalidates OTP.

    Persist BOTH fields atomically with verification, not as a separate write.
    """
    if type(failed_attempts) is not int or failed_attempts < 0:
        raise ValueError("failed_attempts must be a nonnegative integer.")
    count = min(failed_attempts + 1, OTP_MAX_FAILED_ATTEMPTS)
    return OtpFailureDecision(
        failed_attempts=count,
        invalidate=count >= OTP_MAX_FAILED_ATTEMPTS,
    )


def check_resend(
    *,
    latest_issue_at: datetime,
    previous_resend_times: Sequence[datetime],
    now: datetime,
) -> OtpResendDecision:
    """Check rolling resend limits for one account and OTP purpose.

    latest_issue_at is the most recent INITIAL issue or resend timestamp.
    previous_resend_times contains only RESEND timestamps, not initial issue.
    The caller must read/lock and record these attempts atomically in the DB.
    3 resends per rolling 15 minutes does not mean 3 total OTP sends.
    """
    current = _utc(now, "now")
    latest = _utc(latest_issue_at, "latest_issue_at")
    if latest > current:
        raise ValueError("latest_issue_at cannot be in the future.")
    if isinstance(previous_resend_times, (str, bytes)):
        raise ValueError("previous_resend_times must be datetimes.")
    try:
        resends = [_utc(t, "previous_resend_time") for t in previous_resend_times]
    except TypeError:
        raise ValueError("previous_resend_times must be a sequence.") from None
    if any(t > current for t in resends):
        raise ValueError("Resend timestamps cannot be in the future.")

    cooldown_remaining = max(
        0,
        ceil((latest + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS) - current).total_seconds()),
    )
    window_start = current - timedelta(minutes=OTP_RESEND_WINDOW_MINUTES)
    recent_resends = sorted(t for t in resends if t > window_start)
    if len(recent_resends) >= OTP_MAX_RESENDS:
        # The earliest relevant resend must fall outside the rolling window.
        # Combine with cooldown so the returned delay satisfies both checks.
        rate_remaining = ceil(
            (recent_resends[-OTP_MAX_RESENDS] + timedelta(minutes=OTP_RESEND_WINDOW_MINUTES) - current).total_seconds()
        )
        return OtpResendDecision(
            False, "resend_limit", max(1, cooldown_remaining, rate_remaining)
        )
    if cooldown_remaining > 0:
        return OtpResendDecision(False, "cooldown", cooldown_remaining)
    return OtpResendDecision(True, "allowed", 0)
