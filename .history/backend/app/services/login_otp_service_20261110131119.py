"""Dormora File 68: internal login OTP storage; no routes or email sending.

Call issuance only after File 66 accepts the password and HTTP protections pass.
Bind user_id AND otp_id to a short-lived, signed HttpOnly login challenge.
Never accept those IDs directly from browser JSON or serialize IssuedLoginOtp.
Verification uses the caller's transaction: commit False results so failed
attempts persist; on True create the session/reset counters/audit in that SAME
transaction. Do not enable File 67 until that integration is complete.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import MetaData, Table, insert, select, update

from app.core.config import settings
from app.core.otp_security import (
    calculate_otp_digest, generate_otp_code, generate_otp_nonce, verify_otp_code,
)
from app.db.database import SessionLocal, engine
from app.models.user import users_table

email_otps_table = Table("email_otps", MetaData(), schema="public", autoload_with=engine)
security_logs_table = Table("security_logs", MetaData(), schema="public", autoload_with=engine)
PURPOSE = "login"
EXPIRY = timedelta(minutes=3)
WINDOW = timedelta(minutes=15)
COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 3
MAX_ISSUES_PER_WINDOW = 4  # Initial code plus three replacements.
_CODE = re.compile(r"[0-9]{6}\Z")


class LoginOtpNotEligible(ValueError):
    """Account/challenge cannot be used; return a generic HTTP response."""


class LoginOtpRateLimited(ValueError):
    def __init__(self, seconds: float):
        super().__init__("Please wait before requesting another login code.")
        self.retry_after_seconds = max(1, math.ceil(seconds))


@dataclass(frozen=True)
class IssuedLoginOtp:
    """Email-delivery payload only; never return as HTTP JSON or log it."""
    otp_id: int
    expires_at: datetime
    code: str = field(repr=False)
    email_address: str = field(repr=False)


def _id(value: object) -> bool:
    return type(value) is int and value > 0


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Expected a timezone-aware database timestamp.")
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _account(session, user_id: int):
    row = session.execute(
        select(users_table).where(users_table.c.user_id == user_id).with_for_update()
    ).mappings().first()
    now = _now()  # Evaluate after acquiring the row lock.
    if (row is None or row["account_status"] != "active"
            or row["email_verified_at"] is None
            or (row["locked_until"] is not None and _utc(row["locked_until"]) > now)):
        raise LoginOtpNotEligible("Login verification is unavailable.")
    if not isinstance(row["email"], str) or not row["email"].strip():
        raise LoginOtpNotEligible("Login verification is unavailable.")
    return row


def _latest(session, user_id: int):
    return session.execute(
        select(email_otps_table).where(
            email_otps_table.c.user_id == user_id,
            email_otps_table.c.purpose == PURPOSE,
        ).order_by(email_otps_table.c.created_at.desc(), email_otps_table.c.otp_id.desc())
        .limit(1).with_for_update()
    ).mappings().first()


def _audit(
    session,
    user_id: int,
    event: str,
    outcome: str,
    now: datetime,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
):
    session.execute(insert(security_logs_table).values(
        user_id=user_id, event_type=event, outcome=outcome,
        ip_address=client_ip, user_agent=user_agent,
        event_details={"channel": "email", "purpose": PURPOSE}, created_at=now,
    ))


def issue_login_otp(user_id: int, *, previous_otp_id: int | None = None) -> IssuedLoginOtp:
    """Trusted password-step issuance, or resend bound to the previous OTP ID.

    A fresh password submission also counts toward account-wide delivery limits.
    Failed SMTP deliveries count too. Resends cannot revive consumed challenges.
    The future router must additionally enforce challenge expiry and IP limits.
    """
    if not _id(user_id) or (previous_otp_id is not None and not _id(previous_otp_id)):
        raise LoginOtpNotEligible("Invalid login challenge.")
    key = settings.require_otp_hmac_key()
    with SessionLocal.begin() as session:
        account = _account(session, user_id)
        previous = _latest(session, user_id)
        if previous_otp_id is not None and (
            previous is None or previous["otp_id"] != previous_otp_id
            or previous["consumed_at"] is not None
        ):
            raise LoginOtpNotEligible("Invalid login challenge.")
        now = _now()
        recent = session.execute(select(email_otps_table.c.created_at).where(
            email_otps_table.c.user_id == user_id,
            email_otps_table.c.purpose == PURPOSE,
            email_otps_table.c.created_at > now - WINDOW,
        ).order_by(email_otps_table.c.created_at)).scalars().all()
        waits = [0.0]
        if previous is not None:
            waits.append((_utc(previous["created_at"]) + COOLDOWN - now).total_seconds())
        if len(recent) >= MAX_ISSUES_PER_WINDOW:
            waits.append((_utc(recent[-MAX_ISSUES_PER_WINDOW]) + WINDOW - now).total_seconds())
        if max(waits) > 0:
            raise LoginOtpRateLimited(max(waits))
        session.execute(update(email_otps_table).where(
            email_otps_table.c.user_id == user_id,
            email_otps_table.c.purpose == PURPOSE,
            email_otps_table.c.consumed_at.is_(None),
            email_otps_table.c.invalidated_at.is_(None),
        ).values(invalidated_at=now))
        email = account["email"].strip().lower()
        code, nonce = generate_otp_code(), generate_otp_nonce()
        digest = calculate_otp_digest(code, nonce=nonce, secret_key=key,
                                      user_id=user_id, email_address=email, purpose=PURPOSE)
        expiry = now + EXPIRY
        otp_id = session.execute(insert(email_otps_table).values(
            user_id=user_id, email_address=email, purpose=PURPOSE,
            code_nonce=nonce, code_digest=digest, delivery_status="pending",
            attempt_count=0, max_attempts=MAX_ATTEMPTS, created_at=now, expires_at=expiry,
        ).returning(email_otps_table.c.otp_id)).scalar_one()
        return IssuedLoginOtp(int(otp_id), expiry, code, email)


def _mark_delivery(
    otp_id: int,
    sent: bool,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    if not _id(otp_id):
        return False
    with SessionLocal.begin() as session:
        row = session.execute(select(email_otps_table).where(
            email_otps_table.c.otp_id == otp_id, email_otps_table.c.purpose == PURPOSE,
        ).with_for_update()).mappings().first()
        now = _now()
        if (row is None or row["delivery_status"] != "pending"
                or row["consumed_at"] is not None or row["invalidated_at"] is not None):
            return False
        if sent and now >= min(_utc(row["expires_at"]), _utc(row["created_at"]) + EXPIRY):
            return False
        values = {"delivery_status": "sent", "sent_at": now} if sent else {
            "delivery_status": "failed", "invalidated_at": now,
        }
        session.execute(update(email_otps_table).where(
            email_otps_table.c.otp_id == otp_id,
        ).values(**values))
        _audit(session, int(row["user_id"]), "OTP_SENT" if sent else "OTP_FAILED",
               "success" if sent else "failure", now,
               client_ip=client_ip, user_agent=user_agent)
        return True


def mark_login_otp_sent(
    otp_id: int,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Call only after SMTP accepts the message."""
    return _mark_delivery(
        otp_id, True, client_ip=client_ip, user_agent=user_agent
    )


def mark_login_otp_failed(
    otp_id: int,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Revoke a pending code when sending fails."""
    return _mark_delivery(
        otp_id, False, client_ip=client_ip, user_agent=user_agent
    )


def verify_login_otp(
    session,
    user_id: int,
    otp_id: int,
    submitted_code: str,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """Consume once inside a caller-owned transaction; never commit here.

    IDs must come from a validated password-step challenge, not browser input.
    On False, exit the transaction normally BEFORE raising an HTTP error, so
    failed-attempt writes commit. On True, create the session, reset password
    counters and record login success atomically before committing. A session
    creation failure must roll everything back. Do not send cookies until commit.
    """
    if not session.in_transaction():
        raise RuntimeError("An explicit caller-owned transaction is required.")
    if not _id(user_id) or not _id(otp_id):
        return False
    key = settings.require_otp_hmac_key()
    try:
        account = _account(session, user_id)
    except LoginOtpNotEligible:
        return False
    row = _latest(session, user_id)
    now = _now()
    if (row is None or row["otp_id"] != otp_id
            or row["email_address"] != account["email"].strip().lower()
            or row["delivery_status"] != "sent" or row["consumed_at"] is not None
            or row["invalidated_at"] is not None
            or now >= min(_utc(row["expires_at"]), _utc(row["created_at"]) + EXPIRY)
            or int(row["attempt_count"]) >= min(MAX_ATTEMPTS, int(row["max_attempts"]))):
        return False
    valid = (isinstance(submitted_code, str) and _CODE.fullmatch(submitted_code) is not None
             and verify_otp_code(submitted_code, stored_digest=row["code_digest"],
                                 nonce=row["code_nonce"], secret_key=key, user_id=user_id,
                                 email_address=row["email_address"], purpose=PURPOSE))
    if valid:
        values = {"consumed_at": now}
    else:
        attempts = int(row["attempt_count"]) + 1
        values = {"attempt_count": attempts}
        if attempts >= min(MAX_ATTEMPTS, int(row["max_attempts"])):
            values["invalidated_at"] = now
        _audit(session, user_id, "OTP_FAILED", "failure", now,
               client_ip=client_ip, user_agent=user_agent)
    session.execute(update(email_otps_table).where(
        email_otps_table.c.otp_id == otp_id,
    ).values(**values))
    return bool(valid)
