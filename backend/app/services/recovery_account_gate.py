
"""Dormora File 122 -- recovery identity and shared lockout gate.

CREATE: backend/app/services/recovery_account_gate.py

Internal service only: NO HTTP route or browser-visible account lookup.
This code connects File 121's verified security answers to the exact login
failure/lockout state already used by Dormora File 75. A wrong recovery answer
adds LOGIN_FAILED to public.security_logs, so File 72's cross-account IP
threshold also counts it. The existing 3/6/9 tiers stay at 24/48/96 seconds.

The future recovery router MUST:
  * run trusted-Origin + signed-CSRF, server-side reCAPTCHA, per-IP request
    throttling and IP-block checks BEFORE calling this service;
  * bind the username to a short-lived, integrity-protected HttpOnly recovery
    cookie; never accept a client-provided user_id as recovery authority;
  * show the same Q7/Q2/Q4 question choices for eligible, unknown, and locked
    accounts, and never expose internal decisions or real account IDs;
  * use a generic public error for unknown accounts, wrong answers and locked
    accounts (otherwise the response becomes a username-enumeration oracle);
  * dispatch a new lockout alert ONLY after a successful DB commit and only
    using the trusted internal lockout_event_id;
  * after 'approved', issue File 120's OTP in the SAME caller transaction,
    commit, then send File 119's email and set the challenge cookie;
  * preserve failed counters until a successful OTP-mediated recovery reset.

The service never accepts a user ID, logs a security answer, issues an OTP,
creates an authenticated session or changes a password.

Read-only local readiness check:
    python -m app.services.recovery_account_gate --check
"""

from __future__ import annotations

import argparse
import ipaddress
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, engine
from app.models.user import users_table
from app.services.login_service import lockout_for_failure_count, security_logs_table
from app.services.recovery_security_questions import (
    ASSIGNED_QUESTIONS,
    RecoveryQuestionsUnavailable,
    _answer_to_verify,
    _question_bank,
    _read_tables,
    verify_recovery_answer,
)


class RecoveryAccountGateUnavailable(RuntimeError):
    """Do not proceed if database identity, security answers or logs are uncertain."""


@dataclass(frozen=True, slots=True)
class RecoveryAccountIdentity:
    """Internal result of a username lookup, NEVER a browser response.

    The caller must store only the submitted identifier in an authenticated,
    expiring HttpOnly recovery cookie. This user_id must not enter browser JSON.
    """

    typed_username: str
    user_id: int | None


@dataclass(frozen=True, slots=True)
class RecoveryAnswerDecision:
    """Internal verdict, never serialized directly to the user."""

    status: Literal["approved", "invalid", "mismatch", "locked"]
    trusted_user_id: int | None = None
    lockout_event_id: int | None = None
    retry_after_seconds: int = 0


_MAX_USERNAME_LENGTH = 255
_MAX_ATTEMPTS = 2_147_483_647
_HASHER = PasswordHasher()
_DUMMY_ANSWER = "not-a-real-security-answer"


def _require_transaction(db: Session) -> None:
    if not isinstance(db, Session) or not db.in_transaction():
        raise RecoveryAccountGateUnavailable("An active caller-owned transaction is required.")


def _now(db: Session) -> datetime:
    result = db.execute(select(func.clock_timestamp())).scalar_one()
    if not isinstance(result, datetime) or result.tzinfo is None:
        raise RecoveryAccountGateUnavailable("PostgreSQL clock could not be verified.")
    return result.astimezone(timezone.utc)


def _ip(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise RecoveryAccountGateUnavailable("A server-observed IP address is required.")
    try:
        parsed = ipaddress.ip_address(value)
        return str(getattr(parsed, "ipv4_mapped", None) or parsed)
    except ValueError:
        raise RecoveryAccountGateUnavailable("Invalid trusted client IP.") from None


def _agent(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return "".join(char for char in value if char.isprintable())[:255] or None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Use comparable Argon2id work on unknown identifiers."""
    return _HASHER.hash(_DUMMY_ANSWER)


def _dummy_verify(answer: str) -> None:
    try:
        _HASHER.verify(_dummy_hash(), answer if isinstance(answer, str) else "")
    except (VerifyMismatchError, InvalidHashError, VerificationError, TypeError, ValueError):
        pass


def _record_event(
    db: Session,
    *,
    identity: RecoveryAccountIdentity,
    user_id: int | None,
    event: str,
    outcome: str,
    now: datetime,
    client_ip: str,
    user_agent: str | None,
    failure_count: int | None = None,
    lock_seconds: int | None = None,
) -> int:
    details: dict[str, object] = {
        "channel": "password_recovery",
        "username_typed": identity.typed_username,
    }
    if failure_count is not None:
        details["failure_count"] = failure_count
    if lock_seconds is not None:
        details["lock_seconds"] = lock_seconds
    log_id = db.execute(
        insert(security_logs_table).values(
            user_id=user_id,
            event_type=event,
            outcome=outcome,
            ip_address=client_ip,
            user_agent=user_agent,
            event_details=details,
            created_at=now,
        ).returning(security_logs_table.c.log_id)
    ).scalar_one()
    return int(log_id)


def recovery_question_choices(db: Session) -> tuple[tuple[int, str], ...]:
    """Return the SAME three seeded public questions for every username.

    The returned IDs are database question IDs, *not* account IDs.
    Only the future CAPTCHA-protected, rate-limited endpoint should expose it.
    """
    _require_transaction(db)
    questions, _ = _read_tables(db)
    bank = _question_bank(db, questions)
    return tuple((item.question_id, item.question_text) for item in bank)


def resolve_recovery_username(
    db: Session, *, typed_username: str,
) -> RecoveryAccountIdentity:
    """Internal username-only lookup. No account existence in public responses.

    This function must not be callable without the future route's CAPTCHA,
    signed-CSRF and IP limits; the route must not display user_id or presence.
    """
    _require_transaction(db)
    if not isinstance(typed_username, str):
        return RecoveryAccountIdentity("", None)
    logged_username = typed_username[:_MAX_USERNAME_LENGTH]
    identifier = typed_username.strip()
    if not identifier or len(identifier) > _MAX_USERNAME_LENGTH:
        return RecoveryAccountIdentity(logged_username, None)
    if not identifier[0].isalpha() or not identifier.isascii() or not identifier.isalnum():
        return RecoveryAccountIdentity(logged_username, None)
    try:
        row = db.execute(
            select(
                users_table.c.user_id,
                users_table.c.account_status,
                users_table.c.email_verified_at,
            ).where(func.lower(users_table.c.username) == identifier.casefold())
        ).mappings().one_or_none()
    except Exception as exc:
        raise RecoveryAccountGateUnavailable("Recovery account lookup failed.") from exc
    if row is None or row["account_status"] != "active" or row["email_verified_at"] is None:
        return RecoveryAccountIdentity(logged_username, None)
    if type(row["user_id"]) is not int or row["user_id"] <= 0:
        raise RecoveryAccountGateUnavailable("User identity schema mismatch.")
    return RecoveryAccountIdentity(logged_username, row["user_id"])


def verify_and_count_recovery_answer(
    db: Session,
    *,
    identity: RecoveryAccountIdentity,
    question_id: int,
    answer: str,
    confirmation: str,
    client_ip: str,
    user_agent: str | None = None,
) -> RecoveryAnswerDecision:
    """Verify a trusted recovery identity and apply login-shared lockouts.

    Requires a caller-owned transaction; even on failure, caller MUST commit
    to persist the failed-login audit/counter. On success, File 120's issuance
    must happen before the same transaction commits. No OTP is sent here.
    """
    _require_transaction(db)
    if not isinstance(identity, RecoveryAccountIdentity):
        raise RecoveryAccountGateUnavailable("Trusted recovery identity required.")
    ip = _ip(client_ip)
    agent = _agent(user_agent)

    # The handout requires confirmation equality BEFORE checking an answer.
    normalized = _answer_to_verify(answer)
    normalized_confirmation = _answer_to_verify(confirmation)
    if normalized is not None and normalized_confirmation is not None and normalized != normalized_confirmation:
        return RecoveryAnswerDecision("mismatch")

    now = _now(db)
    if identity.user_id is None:
        _dummy_verify(normalized or "")
        _record_event(
            db, identity=identity, user_id=None, event="LOGIN_FAILED",
            outcome="failure", now=now, client_ip=ip, user_agent=agent,
        )
        return RecoveryAnswerDecision("invalid")

    # Use the same locked user row/columns as File 75's login service.
    row = db.execute(
        select(
            users_table.c.user_id,
            users_table.c.account_status,
            users_table.c.email_verified_at,
            users_table.c.failed_login_attempts,
            users_table.c.locked_until,
        ).where(users_table.c.user_id == identity.user_id).with_for_update()
    ).mappings().one_or_none()
    if row is None or row["account_status"] != "active" or row["email_verified_at"] is None:
        _dummy_verify(normalized or "")
        _record_event(
            db, identity=identity, user_id=None, event="LOGIN_FAILED",
            outcome="failure", now=now, client_ip=ip, user_agent=agent,
        )
        return RecoveryAnswerDecision("invalid")

    if row["locked_until"] is not None and _utc(row["locked_until"]) > now:
        retry = max(1, math.ceil((_utc(row["locked_until"]) - now).total_seconds()))
        _record_event(
            db, identity=identity, user_id=identity.user_id, event="LOGIN_LOCKED",
            outcome="blocked", now=now, client_ip=ip, user_agent=agent,
        )
        return RecoveryAnswerDecision("locked", retry_after_seconds=retry)

    # File 121 validates the three assigned answers and Argon2id hashes.
    try:
        approved = verify_recovery_answer(
            db, trusted_user_id=identity.user_id,
            question_id=question_id, answer=answer, answer_confirmation=confirmation,
        )
    except RecoveryQuestionsUnavailable as exc:
        raise RecoveryAccountGateUnavailable("Registered security questions unavailable.") from exc

    if approved:
        # Do not clear failures here: only a verified reset/login-OTP may do so.
        return RecoveryAnswerDecision("approved", trusted_user_id=identity.user_id)

    failures = min(_MAX_ATTEMPTS, int(row["failed_login_attempts"] or 0) + 1)
    lock_seconds, tier = lockout_for_failure_count(failures)
    db.execute(
        update(users_table).where(users_table.c.user_id == identity.user_id).values(
            failed_login_attempts=failures,
            locked_until=now + timedelta(seconds=lock_seconds) if lock_seconds else None,
            updated_at=now,
        )
    )
    _record_event(
        db, identity=identity, user_id=identity.user_id, event="LOGIN_FAILED",
        outcome="failure", now=now, client_ip=ip, user_agent=agent,
        failure_count=failures,
    )
    lock_event_id = None
    if tier is not None:
        lock_event_id = _record_event(
            db, identity=identity, user_id=identity.user_id,
            event=f"LOCKOUT_TIER_{tier}", outcome="blocked",
            now=now, client_ip=ip, user_agent=agent,
            failure_count=failures, lock_seconds=lock_seconds,
        )
    if lock_seconds:
        return RecoveryAnswerDecision(
            "locked", lockout_event_id=lock_event_id,
            retry_after_seconds=lock_seconds,
        )
    return RecoveryAnswerDecision("invalid")


def _local_preflight() -> None:
    from app.core.config import settings
    if settings.environment != "development":
        raise RecoveryAccountGateUnavailable("Development environment required.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise RecoveryAccountGateUnavailable("Expected local PostgreSQL dormora_db.")
    try:
        loopback = ipaddress.ip_address(engine.url.host or "").is_loopback
    except ValueError:
        loopback = (engine.url.host or "").lower() == "localhost"
    if not loopback:
        raise RecoveryAccountGateUnavailable("Only local PostgreSQL is permitted.")

    for required in (
        "user_id", "username", "account_status", "email_verified_at",
        "failed_login_attempts", "locked_until", "updated_at",
    ):
        if required not in users_table.c:
            raise RecoveryAccountGateUnavailable("Login account model is incompatible.")
    for required in (
        "log_id", "user_id", "event_type", "outcome", "ip_address",
        "user_agent", "event_details", "created_at",
    ):
        if required not in security_logs_table.c:
            raise RecoveryAccountGateUnavailable("Login audit model is incompatible.")

    with SessionLocal.begin() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        choices = recovery_question_choices(db)
        if len(choices) != 3 or len({code for code, _ in choices}) != 3:
            raise RecoveryAccountGateUnavailable("Recovery question choices are invalid.")
        _ = db.execute(select(func.count()).select_from(security_logs_table)).scalar_one()

    first, tier = lockout_for_failure_count(3)
    second, second_tier = lockout_for_failure_count(6)
    third, third_tier = lockout_for_failure_count(9)
    if (first, second, third, tier, second_tier, third_tier) != (24, 48, 96, 1, 2, 3):
        raise RecoveryAccountGateUnavailable("Login lockout policy changed.")
    if not _HASHER.verify(_HASHER.hash("sample answer"), "sample answer"):
        raise RecoveryAccountGateUnavailable("Argon2id self-check failed.")
    print("DORMORA FILE 122 -- SHARED RECOVERY / LOGIN LOCKOUT GATE")
    print("Local development and PostgreSQL: PASS")
    print("Recovery questions: Q7, Q2, Q4 | Uniform choices: READY")
    print("Shared login lockout tiers: 3/6/9 -> 24/48/96 seconds")
    print("Failed recovery answers: LOGIN_FAILED audit + existing IP threshold")
    print("No account, security answer, session, password or OTP was modified.")
    print("File 122 check OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora recovery identity / lockout readiness")
    parser.add_argument("--check", action="store_true", required=True,
                        help="read-only schema and policy verification")
    parser.parse_args()
    try:
        _local_preflight()
    except RecoveryAccountGateUnavailable as exc:
        print("FILE 122 STOPPED:", str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("FILE 122 FAILED:", type(exc).__name__)
        print("Inspect local question, account and security audit schema.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
