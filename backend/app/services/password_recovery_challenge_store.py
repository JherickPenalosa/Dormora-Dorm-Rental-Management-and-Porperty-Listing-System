"""Dormora File 120 (corrected) -- transaction-scoped password-recovery OTP and reset grants.

CREATE: backend/app/services/password_recovery_challenge_store.py

This is an INTERNAL SERVICE, not an API route. It intentionally uses a separate
purpose-specific table rather than changing registration/login OTP storage.
The browser must never supply a user_id; only a backend that has validated
CAPTCHA AND a registered security-question answer may create a challenge.

The caller MUST use `with SessionLocal.begin() as db` for every operation.
The caller MUST send the File 119 OTP email only AFTER issuance commits, and
call cancel_recovery_challenge() if SMTP definitively fails. SMTP acceptance is
not the same as inbox delivery. The caller must enforce IP throttling, signed
CSRF, trusted Origin, generic anti-enumeration responses, and audit events.

A successful OTP creates a random, short-lived reset grant, NOT a login session.
Pass the grant ONLY in a secure HttpOnly cookie in a later API integration.
Password change and grant consumption occur in the SAME DB transaction, using
File 104's existing password history, audit logging, and session revocation.

Correction: Table objects cannot be used in boolean conditions in SQLAlchemy;
check explicitly for ``is not None`` when reporting schema status.

Local schema commands (no user or password changes):
    python -m app.services.password_recovery_challenge_store --check
    python -m app.services.password_recovery_challenge_store --setup
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    MetaData, String, Table, func, inspect, insert, select, text, update,
)
from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import users_table


class RecoveryStoreUnavailable(RuntimeError):
    """Storage integrity is not established. The API must fail closed."""


class RecoveryRateLimited(ValueError):
    """Account-scoped OTP issuance or resend rate limit was reached."""

    def __init__(self, retry_after_seconds: int):
        super().__init__("Recovery code request temporarily limited.")
        self.retry_after_seconds = max(1, min(int(retry_after_seconds), 900))


class RecoveryGrantInvalid(ValueError):
    """The reset grant is absent, expired, consumed, or otherwise invalid."""


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryOtpIssue:
    """Transient trusted issuance data. Never log, print or return through HTTP."""
    user_id: int
    challenge_token: str = field(repr=False)
    code: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryResetGrant:
    """Raw grant belongs only in a secure HttpOnly reset-grant cookie."""
    token: str = field(repr=False)
    expires_at: datetime


OTP_SECONDS = 300  # Five-minute instructor requirement
CHALLENGE_SECONDS = 900
RESEND_COOLDOWN_SECONDS = 60
MAX_RESENDS = 3
MAX_ISSUANCES_PER_15_MIN = 4  # First code plus at most three more
MAX_WRONG_ATTEMPTS = 3
RESET_GRANT_SECONDS = 600  # Short one-time password-reset authorization
_TABLE = "password_recovery_challenges"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{40,128}\Z", re.ASCII)
_CODE_PATTERN = re.compile(r"[0-9]{6}\Z", re.ASCII)
_HASHER = PasswordHasher()


def _schema_table() -> Table:
    table = Table(
        _TABLE, MetaData(),
        Column("challenge_digest", String(64), primary_key=True),
        Column("user_id", users_table.c.user_id.type,
               ForeignKey(users_table.c.user_id, ondelete="CASCADE"), nullable=False),
        Column("otp_hash", String(255), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("last_sent_at", DateTime(timezone=True), nullable=False),
        Column("otp_expires_at", DateTime(timezone=True), nullable=False),
        Column("failed_attempts", Integer, nullable=False, server_default="0"),
        Column("resend_count", Integer, nullable=False, server_default="0"),
        Column("verified_at", DateTime(timezone=True), nullable=True),
        Column("grant_digest", String(64), unique=True, nullable=True),
        Column("grant_expires_at", DateTime(timezone=True), nullable=True),
        Column("consumed_at", DateTime(timezone=True), nullable=True),
        Column("revoked_at", DateTime(timezone=True), nullable=True),
        CheckConstraint("failed_attempts BETWEEN 0 AND 3", name="ck_dormora_reset_attempts"),
        CheckConstraint("resend_count BETWEEN 0 AND 3", name="ck_dormora_reset_resends"),
        schema="public",
    )
    Index("ix_dormora_reset_user_recent", table.c.user_id, table.c.created_at)
    Index("ix_dormora_reset_code_expiry", table.c.otp_expires_at)
    return table


_REQUIRED_COLUMNS = frozenset(_schema_table().c.keys())


def _existing_table(connection: Any) -> Table | None:
    inspector = inspect(connection)
    if not inspector.has_table(_TABLE, schema="public"):
        return None
    table = Table(_TABLE, MetaData(), schema="public", autoload_with=connection)
    if set(table.c.keys()) != _REQUIRED_COLUMNS:
        raise RecoveryStoreUnavailable("Existing password-recovery table differs from File 120.")
    pk = inspector.get_pk_constraint(_TABLE, schema="public")
    if set(pk.get("constrained_columns") or []) != {"challenge_digest"}:
        raise RecoveryStoreUnavailable("Recovery challenge primary key is invalid.")
    fks = inspector.get_foreign_keys(_TABLE, schema="public")
    if not any(
        fk.get("constrained_columns") == ["user_id"]
        and fk.get("referred_table") == "users"
        and fk.get("referred_columns") == ["user_id"]
        for fk in fks
    ):
        raise RecoveryStoreUnavailable("Recovery challenge owner foreign key is invalid.")
    required_nonnull = _REQUIRED_COLUMNS - {
        "verified_at", "grant_digest", "grant_expires_at", "consumed_at", "revoked_at"
    }
    if any(table.c[name].nullable for name in required_nonnull):
        raise RecoveryStoreUnavailable("Recovery table allows NULL in required columns.")
    uniques = inspector.get_unique_constraints(_TABLE, schema="public")
    if not any(set(row.get("column_names") or []) == {"grant_digest"} for row in uniques):
        raise RecoveryStoreUnavailable("Reset grants must be unique.")
    return table


def _table(db: Session) -> Table:
    table = _existing_table(db.connection())
    if table is None:
        raise RecoveryStoreUnavailable("Run File 120 --setup first.")
    return table


def _require_transaction(db: Session) -> None:
    if not isinstance(db, Session) or not db.in_transaction():
        raise RecoveryStoreUnavailable("A caller-owned transaction is required.")


def _now(db: Session) -> datetime:
    result = db.execute(select(func.clock_timestamp())).scalar_one()
    if not isinstance(result, datetime) or result.tzinfo is None:
        raise RecoveryStoreUnavailable("PostgreSQL clock is unavailable.")
    return result.astimezone(timezone.utc)


def _digest_token(token: str) -> str | None:
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _require_user_lock(db: Session, user_id: int) -> None:
    """Serialize issuance/resends for an account using the parent user row."""
    if type(user_id) is not int or user_id <= 0:
        raise RecoveryStoreUnavailable("A trusted user identity is required.")
    row = db.execute(
        select(users_table.c.user_id, users_table.c.account_status,
               users_table.c.email_verified_at)
        .where(users_table.c.user_id == user_id)
        .with_for_update()
    ).one_or_none()
    if row is None or row.account_status != "active" or row.email_verified_at is None:
        raise RecoveryStoreUnavailable("Account is not eligible for password recovery.")


def _quota_check(db: Session, table: Table, user_id: int, now: datetime) -> None:
    """Per-account 15-minute quota survives fresh challenges/browser restarts."""
    since = now - timedelta(seconds=CHALLENGE_SECONDS)
    recent = db.execute(
        select(table.c.created_at, table.c.last_sent_at, table.c.resend_count)
        .where(table.c.user_id == user_id, table.c.created_at >= since)
    ).all()
    total = sum(1 + int(item.resend_count) for item in recent)
    if total >= MAX_ISSUANCES_PER_15_MIN:
        earliest = min(item.created_at for item in recent)
        retry = max(1, int((earliest + timedelta(seconds=CHALLENGE_SECONDS) - now).total_seconds()) + 1)
        raise RecoveryRateLimited(retry)
    latest = max((item.last_sent_at for item in recent), default=None)
    if latest is not None:
        elapsed = (now - latest).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            raise RecoveryRateLimited(int(RESEND_COOLDOWN_SECONDS - elapsed) + 1)


def create_recovery_challenge(db: Session, *, verified_user_id: int) -> RecoveryOtpIssue:
    """Issue only AFTER the server verifies CAPTCHA and a security answer.

    The caller MUST commit issuance before calling the File 119 email sender.
    Invalidating prior outstanding OTPs/grants for this user is transactional.
    """
    _require_transaction(db)
    _require_user_lock(db, verified_user_id)
    table = _table(db)
    now = _now(db)
    _quota_check(db, table, verified_user_id, now)
    db.execute(
        update(table).where(table.c.user_id == verified_user_id,
                            table.c.revoked_at.is_(None),
                            table.c.consumed_at.is_(None))
        .values(revoked_at=now)
    )
    token = _new_token()
    otp = _new_code()
    db.execute(insert(table).values(
        challenge_digest=_digest_token(token),
        user_id=verified_user_id,
        otp_hash=_HASHER.hash(otp),
        created_at=now,
        last_sent_at=now,
        otp_expires_at=now + timedelta(seconds=OTP_SECONDS),
        failed_attempts=0, resend_count=0,
    ))
    return RecoveryOtpIssue(verified_user_id, token, otp, now,
                            now + timedelta(seconds=OTP_SECONDS))


def _challenge_for_update(db: Session, table: Table, token: str):
    digest = _digest_token(token)
    if digest is None:
        return None
    # Resolve trusted user_id first, then lock user followed by challenge.
    # Lock ordering matches create() and reset() and avoids user/challenge deadlocks.
    row_user_id = db.execute(
        select(table.c.user_id).where(table.c.challenge_digest == digest)
    ).scalar_one_or_none()
    if row_user_id is None:
        return None
    _require_user_lock(db, row_user_id)
    return db.execute(
        select(table).where(table.c.challenge_digest == digest).with_for_update()
    ).mappings().one_or_none()


def resend_recovery_otp(db: Session, *, challenge_token: str) -> RecoveryOtpIssue:
    """Replace prior OTP after 60 seconds; 3 resends maximum per 15 minutes."""
    _require_transaction(db)
    table = _table(db)
    row = _challenge_for_update(db, table, challenge_token)
    now = _now(db)
    if (row is None or row["revoked_at"] is not None
            or row["verified_at"] is not None or row["consumed_at"] is not None
            or now >= row["created_at"] + timedelta(seconds=CHALLENGE_SECONDS)):
        raise RecoveryGrantInvalid("Recovery challenge unavailable.")
    if int(row["resend_count"]) >= MAX_RESENDS:
        raise RecoveryRateLimited(CHALLENGE_SECONDS)
    _quota_check(db, table, row["user_id"], now)
    otp = _new_code()
    db.execute(update(table).where(table.c.challenge_digest == row["challenge_digest"]).values(
        otp_hash=_HASHER.hash(otp), last_sent_at=now,
        otp_expires_at=now + timedelta(seconds=OTP_SECONDS),
        failed_attempts=0, resend_count=int(row["resend_count"]) + 1,
    ))
    return RecoveryOtpIssue(row["user_id"], challenge_token, otp, now,
                            now + timedelta(seconds=OTP_SECONDS))


def verify_recovery_otp(
    db: Session, *, challenge_token: str, code: str
) -> RecoveryResetGrant | None:
    """Exactly three bad entries cancel this code; valid OTP grants reset only.

    Return None on invalid/expired code. The caller MUST COMMIT this transaction
    even when None is returned, or failed attempts will not be persisted.
    """
    _require_transaction(db)
    table = _table(db)
    row = _challenge_for_update(db, table, challenge_token)
    now = _now(db)
    if (row is None or row["revoked_at"] is not None
            or row["verified_at"] is not None or row["consumed_at"] is not None
            or now >= row["otp_expires_at"]
            or now >= row["created_at"] + timedelta(seconds=CHALLENGE_SECONDS)
            or int(row["failed_attempts"]) >= MAX_WRONG_ATTEMPTS):
        return None
    good = False
    if isinstance(code, str) and _CODE_PATTERN.fullmatch(code) is not None:
        try:
            good = bool(_HASHER.verify(row["otp_hash"], code))
        except VerifyMismatchError:
            pass
        except (VerificationError, InvalidHashError, ValueError, TypeError):
            raise RecoveryStoreUnavailable("Stored OTP hash cannot be verified.") from None
    if not good:
        attempts = int(row["failed_attempts"]) + 1
        db.execute(update(table).where(table.c.challenge_digest == row["challenge_digest"]).values(
            failed_attempts=attempts,
            revoked_at=now if attempts >= MAX_WRONG_ATTEMPTS else None,
        ))
        return None
    token = _new_token()
    expiry = now + timedelta(seconds=RESET_GRANT_SECONDS)
    db.execute(update(table).where(table.c.challenge_digest == row["challenge_digest"]).values(
        verified_at=now, grant_digest=_digest_token(token), grant_expires_at=expiry,
    ))
    return RecoveryResetGrant(token=token, expires_at=expiry)


def cancel_recovery_challenge(db: Session, *, challenge_token: str) -> None:
    """Revoke a challenge after definite email failure; never delete audit rows."""
    _require_transaction(db)
    table = _table(db)
    row = _challenge_for_update(db, table, challenge_token)
    if row is None or row["revoked_at"] is not None:
        return
    db.execute(update(table).where(table.c.challenge_digest == row["challenge_digest"])
               .values(revoked_at=_now(db)))


def consume_reset_grant_and_change_password(
    db: Session, *, reset_grant_token: str, new_password: str,
    password_confirmation: str, client_ip: str, user_agent: str | None = None,
):
    """Consume verified grant and change password atomically using File 104.

    Caller MUST commit on success, roll back on ANY exception, send alert after
    commit, and expire the HttpOnly grant cookie. A grant cannot create a login
    session and cannot be used a second time or for another user's password.
    """
    _require_transaction(db)
    table = _table(db)
    digest = _digest_token(reset_grant_token)
    if digest is None:
        raise RecoveryGrantInvalid("Password-reset authorization unavailable.")
    user_id = db.execute(
        select(table.c.user_id).where(table.c.grant_digest == digest)
    ).scalar_one_or_none()
    if user_id is None:
        raise RecoveryGrantInvalid("Password-reset authorization unavailable.")
    _require_user_lock(db, user_id)
    row = db.execute(
        select(table).where(table.c.grant_digest == digest).with_for_update()
    ).mappings().one_or_none()
    now = _now(db)
    if (row is None or row["revoked_at"] is not None
            or row["verified_at"] is None or row["grant_expires_at"] is None
            or now >= row["grant_expires_at"] or row["consumed_at"] is not None):
        raise RecoveryGrantInvalid("Password-reset authorization unavailable.")
    db.execute(update(table).where(table.c.challenge_digest == row["challenge_digest"])
               .values(consumed_at=now))
    from app.services.password_change_service import apply_verified_password_change
    return apply_verified_password_change(
        db, verified_user_id=user_id, new_password=new_password,
        password_confirmation=password_confirmation,
        client_ip=client_ip, user_agent=user_agent,
    )


def _local_preflight(*, setup: bool) -> None:
    from app.core.config import settings
    if settings.environment != "development":
        raise RecoveryStoreUnavailable("Development environment required.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise RecoveryStoreUnavailable("Expected local PostgreSQL dormora_db.")
    host = engine.url.host or ""
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.casefold() == "localhost"
    if not local:
        raise RecoveryStoreUnavailable("Only loopback PostgreSQL is permitted.")
    for required in ("user_id", "account_status", "email_verified_at", "password_hash"):
        if required not in users_table.c:
            raise RecoveryStoreUnavailable("User model is missing required fields.")
    if setup:
        with engine.begin() as conn:
            table = _existing_table(conn)
            if table is None:
                _schema_table().create(bind=conn, checkfirst=False)
                table = _existing_table(conn)
    else:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                table = _existing_table(conn)
    print("DORMORA FILE 120 -- RECOVERY OTP AND RESET-GRANT STORAGE")
    print("Local development and PostgreSQL: PASS")
    print("OTP hashing: Argon2id | Expiry: 5 minutes | Wrong attempts: 3")
    print("Resends: 60-second cooldown | Max 3 within 15 minutes")
    print("One-time reset grants: 10-minute expiry; password history via File 104")
    print("Recovery storage table:", "PRESENT and compatible" if table is not None else "MISSING")
    print("No user account, password, session, or recovery code was changed.")
    print("File 120", "setup OK" if setup else "check OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora recovery OTP storage")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check", action="store_true", help="read-only local schema check")
    choice.add_argument("--setup", action="store_true", help="create only missing recovery table")
    args = parser.parse_args()
    try:
        _local_preflight(setup=args.setup)
    except RecoveryStoreUnavailable as exc:
        print("FILE 120 STOPPED:", str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("FILE 120 FAILED:", type(exc).__name__)
        print("Check local database permissions and recovery schema.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
