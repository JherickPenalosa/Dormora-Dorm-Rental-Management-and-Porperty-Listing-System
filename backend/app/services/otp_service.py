
"""Dormora Backend File 136 — registration OTP audit metadata support.

REPLACE: backend/app/services/otp_service.py (previously File 50).

Preserves OTP issuance, delivery confirmation, resend limits, verification,
row locks, and atomic transactions. All existing positional calls still work.

Optional client_ip and user_agent must be supplied by trusted HTTP routes or
workflow callers. Never trust arbitrary X-Forwarded-For headers. Without
these optional arguments, the original NULL metadata behavior is preserved.
The route/workflow forwarding updates are separate later files.

OTP codes and email addresses stay in trusted internal return values only.
This module does not send email, run schema migrations, or open HTTP routes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import MetaData, Table, insert, select, update

from app.core.config import settings
from app.core.otp_policy import (
    OTP_EXPIRY_MINUTES,
    OTP_MAX_FAILED_ATTEMPTS,
    OTP_RESEND_WINDOW_MINUTES,
    after_failed_code,
    check_otp_state,
    check_resend,
    expires_at_for,
    utc_now,
)
from app.core.otp_security import (
    calculate_otp_digest,
    generate_otp_code,
    generate_otp_nonce,
    verify_otp_code,
)
from app.db.database import SessionLocal, engine
from app.models.user import users_table

email_otps_table = Table(
    "email_otps", MetaData(), schema="public", autoload_with=engine
)

security_logs_table = Table(
    "security_logs", MetaData(), schema="public", autoload_with=engine
)

_CODE_RE = re.compile(r"[0-9]{6}\Z")
_PURPOSE = "registration"
_RESEND_EVENT = "otp_resend_issued"


class OtpAccountNotEligibleError(Exception):
    """Registration OTPs require a pending, unverified user account."""


class OtpResendNotAllowed(Exception):
    """The request is too early or exceeds the resend limit."""

    def __init__(self, *, retry_after_seconds: int, reason: str):
        super().__init__("OTP resend is temporarily unavailable.")
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        self.reason = reason


@dataclass(frozen=True)
class IssuedRegistrationOtp:
    """Trusted internal delivery payload; NEVER serialize into HTTP JSON."""

    otp_id: int
    expires_at: datetime
    code: str = field(repr=False)
    email_address: str = field(repr=False)


def _valid_id(value: object) -> bool:
    return type(value) is int and value > 0


def _db_timestamp(value: datetime) -> datetime:
    """Encode UTC in the existing PostgreSQL TIMESTAMP WITHOUT TIME ZONE."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required.")
    return value.astimezone(timezone.utc)


def _utc_timestamp(value: datetime) -> datetime:
    """Interpret SQL naive timestamps as UTC, not the local computer time."""
    if not isinstance(value, datetime):
        raise ValueError("Missing OTP timestamp.")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_pending_user_email(session, user_id: int) -> str:
    """Lock user row so issuing/verification/resend cannot race."""
    row = session.execute(
        select(
            users_table.c.email,
            users_table.c.account_status,
            users_table.c.email_verified_at,
        )
        .where(users_table.c.user_id == user_id)
        .with_for_update()
    ).mappings().first()

    if (
        row is None
        or row["account_status"] != "pending_verification"
        or row["email_verified_at"] is not None
    ):
        raise OtpAccountNotEligibleError(
            "Account is not awaiting verification."
        )

    email_address = str(row["email"]).strip().lower()
    if not email_address or len(email_address) > 255:
        raise OtpAccountNotEligibleError(
            "Verification email is unavailable."
        )
    return email_address


def _latest_otp(session, user_id: int, *, lock: bool = True):
    stmt = (
        select(email_otps_table)
        .where(
            email_otps_table.c.user_id == user_id,
            email_otps_table.c.purpose == _PURPOSE,
        )
        .order_by(
            email_otps_table.c.created_at.desc(),
            email_otps_table.c.otp_id.desc(),
        )
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return session.execute(stmt).mappings().first()


def _audit(
    session,
    user_id: int,
    event_type: str,
    outcome: str,
    at: datetime,
    *,
    details: dict[str, object] | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Atomically record a no-secret event with optional trusted request data."""
    session.execute(
        insert(security_logs_table).values(
            user_id=user_id,
            event_type=event_type,
            outcome=outcome,
            ip_address=client_ip,
            user_agent=user_agent,
            event_details=details or {"channel": "email"},
            created_at=_db_timestamp(at),
        )
    )


def _new_code(
    session,
    *,
    user_id: int,
    email_address: str,
    now: datetime,
) -> IssuedRegistrationOtp:
    code = generate_otp_code()
    nonce = generate_otp_nonce()

    digest = calculate_otp_digest(
        code,
        nonce=nonce,
        secret_key=settings.require_otp_hmac_key(),
        user_id=user_id,
        email_address=email_address,
        purpose=_PURPOSE,
    )

    expiry = expires_at_for(now)

    otp_id = session.execute(
        insert(email_otps_table).values(
            user_id=user_id,
            email_address=email_address,
            purpose=_PURPOSE,
            code_nonce=nonce,
            code_digest=digest,
            delivery_status="pending",
            attempt_count=0,
            max_attempts=OTP_MAX_FAILED_ATTEMPTS,
            created_at=_db_timestamp(now),
            expires_at=_db_timestamp(expiry),
        ).returning(email_otps_table.c.otp_id)
    ).scalar_one()

    return IssuedRegistrationOtp(
        otp_id=int(otp_id),
        expires_at=expiry,
        code=code,
        email_address=email_address,
    )


def issue_registration_otp(user_id: int) -> IssuedRegistrationOtp:
    """Issue the first registration OTP, once per pending user.

    A repeat call cannot bypass cooldown/rate-limit rules: use
    resend_registration_otp instead. The previous File 44 calls this only
    immediately after creating the user's pending account.
    """
    if not _valid_id(user_id):
        raise ValueError("A positive user ID is required.")

    settings.require_otp_hmac_key()

    with SessionLocal.begin() as session:
        email_address = _get_pending_user_email(session, user_id)

        if _latest_otp(session, user_id) is not None:
            raise OtpAccountNotEligibleError(
                "An initial registration OTP already exists. Use the resend flow."
            )

        return _new_code(
            session,
            user_id=user_id,
            email_address=email_address,
            now=utc_now(),
        )


def resend_registration_otp(
    user_id: int,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> IssuedRegistrationOtp:
    """Issue a replacement OTP enforcing both resend limits atomically.

    Resend activity is counted in security_logs because existing email_otps
    has no is_resend column. A user-row lock serializes per-account requests;
    the resend event and replacement OTP are committed together. A future
    protected endpoint must call this, send the email, and mark it sent/failed.
    """
    if not _valid_id(user_id):
        raise ValueError("A positive user ID is required.")

    settings.require_otp_hmac_key()

    with SessionLocal.begin() as session:
        email_address = _get_pending_user_email(session, user_id)
        previous = _latest_otp(session, user_id)

        if previous is None:
            raise OtpAccountNotEligibleError(
                "No previous registration OTP. Initial issuance is required."
            )

        now = utc_now()
        window_start = _db_timestamp(
            now - timedelta(minutes=OTP_RESEND_WINDOW_MINUTES)
        )

        previous_resend_rows = session.execute(
            select(security_logs_table.c.created_at).where(
                security_logs_table.c.user_id == user_id,
                security_logs_table.c.event_type == _RESEND_EVENT,
                security_logs_table.c.created_at > window_start,
            )
        ).scalars().all()

        decision = check_resend(
            latest_issue_at=_utc_timestamp(previous["created_at"]),
            previous_resend_times=[
                _utc_timestamp(ts) for ts in previous_resend_rows
            ],
            now=now,
        )

        if not decision.allowed:
            raise OtpResendNotAllowed(
                retry_after_seconds=decision.retry_after_seconds,
                reason=decision.reason,
            )

        # Revoke the old code even if its email was delayed or it was expired.
        if (
            previous["consumed_at"] is None
            and previous["invalidated_at"] is None
        ):
            session.execute(
                update(email_otps_table)
                .where(email_otps_table.c.otp_id == previous["otp_id"])
                .values(invalidated_at=_db_timestamp(now))
            )

        issued = _new_code(
            session,
            user_id=user_id,
            email_address=email_address,
            now=now,
        )

        _audit(
            session, user_id, _RESEND_EVENT, "info", now,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return issued


def mark_otp_sent(
    otp_id: int,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Mark an SMTP-accepted OTP as sent; cannot resurrect revoked OTPs."""
    if not _valid_id(otp_id):
        return False

    with SessionLocal.begin() as session:
        row = session.execute(
            select(email_otps_table)
            .where(email_otps_table.c.otp_id == otp_id)
            .with_for_update()
        ).mappings().first()

        if row is None:
            return False

        now = utc_now()

        if (
            row["delivery_status"] != "pending"
            or row["consumed_at"] is not None
            or row["invalidated_at"] is not None
            or now >= _utc_timestamp(row["expires_at"])
        ):
            return False

        session.execute(
            update(email_otps_table)
            .where(email_otps_table.c.otp_id == otp_id)
            .values(
                delivery_status="sent",
                sent_at=_db_timestamp(now),
            )
        )

        _audit(
            session, int(row["user_id"]), "OTP_SENT", "success", now,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return True


def mark_otp_failed(
    otp_id: int,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Revoke an undelivered OTP after SMTP failure, preserving history."""
    if not _valid_id(otp_id):
        return False

    with SessionLocal.begin() as session:
        row = session.execute(
            select(email_otps_table)
            .where(email_otps_table.c.otp_id == otp_id)
            .with_for_update()
        ).mappings().first()

        if (
            row is None
            or row["delivery_status"] != "pending"
            or row["consumed_at"] is not None
            or row["invalidated_at"] is not None
        ):
            return False

        now = utc_now()

        session.execute(
            update(email_otps_table)
            .where(email_otps_table.c.otp_id == otp_id)
            .values(
                delivery_status="failed",
                invalidated_at=_db_timestamp(now),
            )
        )

        _audit(
            session, int(row["user_id"]), "OTP_FAILED", "failure", now,
            details={
                "channel": "email",
                "reason": "email_delivery_failed",
            },
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return True


def verify_registration_otp(
    user_id: int,
    submitted_code: str,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Verify registration code and activate account in ONE DB transaction.

    Failed code checks persist an attempt even if the input has bad syntax.
    Third failed attempt irrevocably invalidates the OTP. A verified code
    gets consumed_at and the user becomes active in the SAME transaction.
    Old 10-minute / 5-attempt OTPs are capped at the new 3-minute / 3-attempt
    limits, even if their older database row stored more permissive values.
    """
    if not _valid_id(user_id):
        return False

    secret_key = settings.require_otp_hmac_key()

    with SessionLocal.begin() as session:
        try:
            _get_pending_user_email(session, user_id)
        except OtpAccountNotEligibleError:
            return False

        row = _latest_otp(session, user_id)

        if row is None:
            return False

        now = utc_now()
        created = _utc_timestamp(row["created_at"])
        original_expiry = _utc_timestamp(row["expires_at"])
        effective_expiry = min(original_expiry, expires_at_for(created))

        decision = check_otp_state(
            expires_at=effective_expiry,
            failed_attempts=int(row["attempt_count"]),
            delivery_status=str(row["delivery_status"]),
            consumed=row["consumed_at"] is not None,
            invalidated=row["invalidated_at"] is not None,
            now=now,
        )

        if not decision.allowed:
            if (
                decision.reason == "attempts_exhausted"
                and row["invalidated_at"] is None
            ):
                session.execute(
                    update(email_otps_table)
                    .where(email_otps_table.c.otp_id == row["otp_id"])
                    .values(invalidated_at=_db_timestamp(now))
                )
            return False

        valid_code = (
            isinstance(submitted_code, str)
            and _CODE_RE.fullmatch(submitted_code) is not None
            and verify_otp_code(
                submitted_code,
                stored_digest=row["code_digest"],
                nonce=row["code_nonce"],
                secret_key=secret_key,
                user_id=user_id,
                email_address=row["email_address"],
                purpose=_PURPOSE,
            )
        )

        if not valid_code:
            failure = after_failed_code(int(row["attempt_count"]))

            updates: dict[str, object] = {
                "attempt_count": failure.failed_attempts,
            }

            if failure.invalidate:
                updates["invalidated_at"] = _db_timestamp(now)

            session.execute(
                update(email_otps_table)
                .where(email_otps_table.c.otp_id == row["otp_id"])
                .values(**updates)
            )

            _audit(
                session, user_id, "OTP_FAILED", "failure", now,
                details={
                    "channel": "web",
                    "attempt_count": failure.failed_attempts,
                },
                client_ip=client_ip,
                user_agent=user_agent,
            )
            return False

        session.execute(
            update(email_otps_table)
            .where(email_otps_table.c.otp_id == row["otp_id"])
            .values(consumed_at=_db_timestamp(now))
        )

        session.execute(
            update(users_table)
            .where(users_table.c.user_id == user_id)
            .values(
                account_status="active",
                email_verified_at=_db_timestamp(now),
                updated_at=_db_timestamp(now),
            )
        )

        _audit(
            session, user_id, "ACCOUNT_VERIFIED", "success", now,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return True
