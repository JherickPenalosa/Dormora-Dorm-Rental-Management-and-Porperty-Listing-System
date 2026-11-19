"""Dormora Backend File 75 — password verification with lockout-event handoff.

REPLACE: backend/app/services/login_service.py (previously File 66).

Purpose:
- Verify username OR email and password against the existing Argon2id hash.
- Enforce persistent progressive account lockouts after failed attempts
  3 / 6 / 9, using assigned D1=9: 24s / 48s / 96s.
- Record login failures and lockout events in existing security_logs.
- Return a trusted internal decision that a future CAPTCHA-protected
  login router can use to issue a LOGIN OTP.

Critical limitations (by design):
- This service does NOT expose an HTTP endpoint, issue OTPs, create sessions,
  reset failure counters, or mark any account logged in.
- Do not expose PasswordStepDecision.user_id or internal status in public JSON.
- A future login route MUST check CSRF, server-side CAPTCHA, per-IP rate limits,
  and safe Origin BEFORE calling authenticate_password_step.
- Failed-attempt counters should be reset only after the login OTP succeeds.
- lockout_event_id identifies the exact newly recorded tier event for File 74.
- Call dispatch_lockout_alert only AFTER this function returns successfully.
- The returned event ID is committed; no ID is returned on transaction failure.
- Alert dispatch and the login route still need integration before activation.

Keep this module out of production traffic until those protections are ready.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from ipaddress import ip_address
from typing import Literal

from sqlalchemy import MetaData, Table, func, insert, or_, select, update

from app.core.security import hash_password, verify_password
from app.db.database import SessionLocal, engine
from app.models.user import users_table


# Instructor handout: tiers at 3, 6, 9 consecutive failures.
# Dormora's assigned D1=9: 15+D1, 30+2*D1, 60+4*D1 seconds.
D1 = 9
FIRST_TIER = 3
SECOND_TIER = 6
THIRD_TIER = 9
FIRST_LOCK_SECONDS = 15 + D1         # 24
SECOND_LOCK_SECONDS = 30 + 2 * D1    # 48
THIRD_LOCK_SECONDS = 60 + 4 * D1     # 96

security_logs_table = Table(
    "security_logs", MetaData(), schema="public", autoload_with=engine
)

_DecisionStatus = Literal[
    "otp_required", "invalid_credentials", "locked", "account_not_eligible"
]


@dataclass(frozen=True)
class PasswordStepDecision:
    """Trusted backend-only result. NEVER return this directly to a browser.

    ``otp_required`` means *only the password* has been verified. It is not
    a completed login and cannot be used as proof of authentication.
    """

    status: _DecisionStatus
    user_id: int | None = None
    retry_after_seconds: int = 0
    lockout_tier_reached: int | None = None
    lockout_event_id: int | None = None

    @property
    def password_accepted(self) -> bool:
        return self.status == "otp_required"


class LoginServiceUnavailable(RuntimeError):
    """Unexpected storage/verification failure; fail closed at the HTTP layer."""


def lockout_for_failure_count(failed_count: int) -> tuple[int, int | None]:
    """Return (lock seconds, newly reached tier) for this failed attempt.

    Preserve the failed-attempt counter across expired lockouts. A successful
    *password step* does NOT reset it: that happens after successful login OTP.
    Attempts after tier 3 remain locked for 96 seconds each time.
    """
    if type(failed_count) is not int or failed_count < 0:
        raise ValueError("Failure count must be a nonnegative integer.")
    if failed_count >= THIRD_TIER:
        return THIRD_LOCK_SECONDS, (3 if failed_count == THIRD_TIER else None)
    if failed_count == SECOND_TIER:
        return SECOND_LOCK_SECONDS, 2
    if failed_count == FIRST_TIER:
        return FIRST_LOCK_SECONDS, 1
    return 0, None


def _as_utc(value: datetime) -> datetime:
    """Interpret PostgreSQL TIMESTAMPTZ correctly (aware datetimes expected)."""
    if not isinstance(value, datetime):
        raise ValueError("Invalid lockout timestamp.")
    if value.tzinfo is None or value.utcoffset() is None:
        # Defensive compatibility for legacy timestamps already stored as UTC.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_ip(value: str | None) -> str | None:
    """Only store a vetted IP supplied by the trusted HTTP request object."""
    if not value:
        return None
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def _safe_agent(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    # Remove control characters; cap stored data, not used for authentication.
    return "".join(ch for ch in value if ch.isprintable())[:255] or None


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Equal-cost Argon2id work when an entered username does not exist."""
    return hash_password("Dormora-nonexistent-account-dummy")


def _safe_verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bool(verify_password(password, stored_hash))
    except Exception:
        # Invalid or legacy hash must not log the hash or bypass login.
        return False


def _audit(
    session,
    *,
    user_id: int | None,
    username_typed: str,
    event_type: str,
    outcome: str,
    now: datetime,
    client_ip: str | None,
    user_agent: str | None,
    details: dict[str, object] | None = None,
) -> int:
    """Insert an audit row and return its ID within the caller transaction."""
    event_details: dict[str, object] = {
        "channel": "password",
        # The handout requires the identifier as entered; treat it as
        # UNTRUSTED when later displaying logs in the admin dashboard.
        "username_typed": username_typed,
    }
    if details:
        event_details.update(details)
    log_id = session.execute(
        insert(security_logs_table).values(
            user_id=user_id,
            event_type=event_type,
            outcome=outcome,
            ip_address=_safe_ip(client_ip),
            user_agent=_safe_agent(user_agent),
            event_details=event_details,
            created_at=now,
        ).returning(security_logs_table.c.log_id)
    ).scalar_one()
    return int(log_id)


def authenticate_password_step(
    identifier: str,
    password: str,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> PasswordStepDecision:
    """Verify credentials and account lockout atomically, NOT a full login.

    Call only *after* CSRF, Origin, server-side reCAPTCHA and IP rate-limit
    validation. Unknown identifiers receive a dummy Argon2id verification.
    All account-state updates and audit events share one transaction.

    Do not serialize the returned ``user_id`` to the frontend. A future login
    endpoint should use a signed, HttpOnly pre-OTP cookie or server-side state
    to bind the next step, then issue login OTP; no session at this stage.
    """
    if not isinstance(identifier, str) or not isinstance(password, str):
        return PasswordStepDecision("invalid_credentials")

    typed_identifier = identifier[:255]  # Preserve exactly what the user typed for audit.
    raw_identifier = identifier.strip()
    if (
        not raw_identifier
        or len(raw_identifier) > 255
        or not password
        or len(password) > 512
    ):
        return PasswordStepDecision("invalid_credentials")

    now = datetime.now(timezone.utc)
    try:
        with SessionLocal.begin() as session:
            # Lock the user row so two wrong attempts cannot overwrite the
            # same failed_login_attempts value concurrently.
            row = session.execute(
                select(
                    users_table.c.user_id,
                    users_table.c.password_hash,
                    users_table.c.account_status,
                    users_table.c.email_verified_at,
                    users_table.c.failed_login_attempts,
                    users_table.c.locked_until,
                )
                .where(
                    or_(
                        func.lower(users_table.c.username) == raw_identifier.lower(),
                        func.lower(users_table.c.email) == raw_identifier.lower(),
                    )
                )
                .with_for_update()
            ).mappings().first()

            if row is None:
                _safe_verify_password(password, _dummy_password_hash())
                _audit(
                    session,
                    user_id=None,
                    username_typed=typed_identifier,
                    event_type="LOGIN_FAILED",
                    outcome="failure",
                    now=now,
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
                return PasswordStepDecision("invalid_credentials")

            user_id = int(row["user_id"])
            until = row["locked_until"]
            if until is not None and _as_utc(until) > now:
                retry = max(1, math.ceil((_as_utc(until) - now).total_seconds()))
                _audit(
                    session,
                    user_id=user_id,
                    username_typed=typed_identifier,
                    event_type="LOGIN_LOCKED",
                    outcome="blocked",
                    now=now,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    details={"retry_after_seconds": retry},
                )
                return PasswordStepDecision("locked", retry_after_seconds=retry)

            if not _safe_verify_password(password, str(row["password_hash"])):
                failures = min(2_147_483_647, int(row["failed_login_attempts"] or 0) + 1)
                lock_seconds, tier = lockout_for_failure_count(failures)
                lock_until = (now + timedelta(seconds=lock_seconds)) if lock_seconds else None
                session.execute(
                    update(users_table)
                    .where(users_table.c.user_id == user_id)
                    .values(
                        failed_login_attempts=failures,
                        locked_until=lock_until,
                        updated_at=now,
                    )
                )
                _audit(
                    session,
                    user_id=user_id,
                    username_typed=typed_identifier,
                    event_type="LOGIN_FAILED",
                    outcome="failure",
                    now=now,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    details={"failure_count": failures},
                )
                lockout_event_id = None
                if tier is not None:
                    lockout_event_id = _audit(
                        session,
                        user_id=user_id,
                        username_typed=typed_identifier,
                        event_type=f"LOCKOUT_TIER_{tier}",
                        outcome="blocked",
                        now=now,
                        client_ip=client_ip,
                        user_agent=user_agent,
                        details={"failure_count": failures, "lock_seconds": lock_seconds},
                    )
                return PasswordStepDecision(
                    "locked" if lock_seconds else "invalid_credentials",
                    retry_after_seconds=lock_seconds,
                    lockout_tier_reached=tier,
                    lockout_event_id=lockout_event_id,
                )

            # A correct password alone is NOT a successful login.
            # Keep failed_login_attempts until the login OTP is verified.
            if row["account_status"] != "active" or row["email_verified_at"] is None:
                _audit(
                    session,
                    user_id=user_id,
                    username_typed=typed_identifier,
                    event_type="LOGIN_NOT_ELIGIBLE",
                    outcome="blocked",
                    now=now,
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
                return PasswordStepDecision("account_not_eligible")

            _audit(
                session,
                user_id=user_id,
                username_typed=typed_identifier,
                event_type="LOGIN_PASSWORD_VERIFIED",
                outcome="info",
                now=now,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            return PasswordStepDecision("otp_required", user_id=user_id)
    except Exception as exc:
        # No authentication result when DB transactions or security logging fail.
        # A future route maps this to generic 503 without exposing exceptions.
        raise LoginServiceUnavailable("Login validation is temporarily unavailable.") from exc