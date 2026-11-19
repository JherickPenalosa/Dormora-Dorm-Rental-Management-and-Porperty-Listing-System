
"""Dormora File 104 -- password reuse protection for verified password changes.

CREATE: backend/app/services/password_change_service.py

Read-only preflight:
    python -m app.services.password_change_service --check
Explicit schema setup (ONLY for a missing table):
    python -m app.services.password_change_service --setup

This module is NOT a FastAPI route, and DOES NOT create a password-reset grant.
The trusted recovery/session workflow must validate the owner and authorization
before calling apply_verified_password_change() within its own DB transaction.
Never expose that function directly to unauthenticated requests or admin tools.

Enforces a rule against reusing the current and two preceding passwords.
Existing Argon2id hashes are verified without reading plaintext passwords from DB.
The history table is created only by explicit --setup. Import and --check are
read-only. No password is changed by either command.
"""

from __future__ import annotations

import argparse
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Identity, Index, MetaData,
    String, Table, func, inspect, insert, select, text, update,
)
from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import users_table


class PasswordHistoryUnavailable(RuntimeError):
    """Password-history data or service cannot be trusted; fail closed."""


class RecentPasswordRejected(ValueError):
    """New password matches a protected recent password."""


class PasswordPolicyRejected(ValueError):
    """New password does not meet the existing project policy."""


@dataclass(frozen=True)
class PasswordChangeOutcome:
    user_id: int
    revoked_sessions: int
    changed_at: datetime


# Match project's Argon2id hash type; PasswordHasher.verify() reads parameters
# from each stored encoded hash (not from this instance's defaults).
_HASHER = PasswordHasher()
_HISTORY_NAME = "password_history"
_HISTORY_ORDER_FIELDS = ("created_at", "changed_at", "recorded_at")
_HISTORY_PK_FIELDS = ("history_id", "id", "password_history_id")


def _check_password_shape(new_password: str, confirmation: str) -> None:
    if not isinstance(new_password, str) or not isinstance(confirmation, str):
        raise PasswordPolicyRejected("Invalid password.")
    if new_password != confirmation:
        raise PasswordPolicyRejected("Mismatch Password.")
    if not (10 <= len(new_password) <= 64):
        raise PasswordPolicyRejected("Use between 10 and 64 characters.")
    if not (any(c.islower() for c in new_password)
            and any(c.isupper() for c in new_password)
            and any(c.isdigit() for c in new_password)
            and any(not c.isalnum() for c in new_password)):
        raise PasswordPolicyRejected(
            "Use upper and lowercase letters, a number, and a special character."
        )
    if any(ord(c) < 32 or ord(c) == 127 for c in new_password):
        raise PasswordPolicyRejected("Control characters are not allowed.")


def _matches_hash(stored_hash: Any, submitted_password: str) -> bool:
    if not isinstance(stored_hash, str) or not stored_hash.startswith("$argon2id$"):
        raise PasswordHistoryUnavailable("Unexpected stored password format.")
    try:
        return bool(_HASHER.verify(stored_hash, submitted_password))
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError, ValueError, TypeError):
        raise PasswordHistoryUnavailable("Stored password cannot be verified.") from None


def _existing_history_table(connection: Any) -> Table | None:
    inspector = inspect(connection)
    if not inspector.has_table(_HISTORY_NAME, schema="public"):
        alternatives = [
            name for name in inspector.get_table_names(schema="public")
            if "password" in name.lower() and "histor" in name.lower()
        ]
        if alternatives:
            raise PasswordHistoryUnavailable(
                "Another password-history table already exists; review its schema "
                "before creating a new one."
            )
        return None
    table = Table(_HISTORY_NAME, MetaData(), schema="public", autoload_with=connection)
    required = {"user_id", "password_hash"}
    if not required.issubset(table.c.keys()):
        raise PasswordHistoryUnavailable(
            "Existing public.password_history is missing user_id/password_hash."
        )
    if not any(name in table.c for name in _HISTORY_ORDER_FIELDS):
        raise PasswordHistoryUnavailable(
            "Existing password history table lacks a timestamp column."
        )
    return table


def _canonical_history_table() -> Table:
    table = Table(
        _HISTORY_NAME, MetaData(),
        Column("history_id", BigInteger, Identity(), primary_key=True),
        Column("user_id", users_table.c.user_id.type,
               ForeignKey(users_table.c.user_id, ondelete="CASCADE"), nullable=False),
        Column("password_hash", String(255), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.clock_timestamp(),
               nullable=False),
        schema="public",
    )
    Index("ix_dormora_password_history_user_time", table.c.user_id, table.c.created_at)
    return table


def _order_columns(history: Table) -> list[Any]:
    time_name = next(name for name in _HISTORY_ORDER_FIELDS if name in history.c)
    columns = [history.c[time_name].desc()]
    pk = next((name for name in _HISTORY_PK_FIELDS if name in history.c), None)
    if pk:
        columns.append(history.c[pk].desc())
    return columns


def _recent_previous_hashes(db: Session, history: Table, user_id: int,
                            current_hash: str) -> list[str]:
    """Return the latest 2 distinct prior encodings (current is separately checked).

    The table may already include the current hash from registration. Avoid
    counting that duplicate as a previous password. Old records are not deleted.
    """
    result = db.execute(
        select(history.c.password_hash)
        .where(history.c.user_id == user_id)
        .order_by(*_order_columns(history))
        .limit(256)
    ).scalars()
    seen: set[str] = {current_hash}
    previous: list[str] = []
    for digest in result:
        if not isinstance(digest, str) or not digest.startswith("$argon2id$"):
            raise PasswordHistoryUnavailable("Invalid password-history hash.")
        if digest not in seen:
            seen.add(digest)
            previous.append(digest)
        if len(previous) >= 2:
            break
    return previous


def reject_recent_password(new_password: str, current_hash: str,
                           previous_hashes: list[str]) -> None:
    """Pure recent-password check; password and hashes are never printed/logged."""
    if _matches_hash(current_hash, new_password):
        raise RecentPasswordRejected("You cannot reuse a recent password.")
    for digest in previous_hashes[:2]:
        if _matches_hash(digest, new_password):
            raise RecentPasswordRejected("You cannot reuse a recent password.")


def apply_verified_password_change(
    db: Session,
    *,
    verified_user_id: int,
    new_password: str,
    password_confirmation: str,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> PasswordChangeOutcome:
    """Change password only INSIDE an already authorized, active transaction.

    CALLER SECURITY CONTRACT:
      1. Verify the authenticated current-password flow OR validate a short-lived
         one-time password-recovery OTP grant for this exact user, in the backend.
      2. Lock/consume the grant in this same transaction before calling here.
      3. Do not commit until this operation and grant consumption succeed.
      4. Send the change-notification email AFTER the commit; a future integration
         file must implement that notification and HTTP route.

    This internal function does not validate CAPTCHA/CSRF/OTP by itself and must
    NEVER be registered as a route or called with a browser-chosen user_id.
    """
    _check_password_shape(new_password, password_confirmation)
    if not isinstance(db, Session) or not db.in_transaction():
        raise PasswordHistoryUnavailable("An active caller-owned DB transaction is required.")
    if type(verified_user_id) is not int or verified_user_id < 1:
        raise PasswordHistoryUnavailable("A trusted user id is required.")

    history = _existing_history_table(db.connection())
    if history is None:
        raise PasswordHistoryUnavailable("Run File 104 --setup before password changes.")

    user = db.execute(
        select(users_table)
        .where(users_table.c.user_id == verified_user_id)
        .with_for_update()
    ).mappings().one_or_none()
    if user is None:
        raise PasswordHistoryUnavailable("Account unavailable.")
    current_hash = user["password_hash"]
    previous = _recent_previous_hashes(db, history, verified_user_id, current_hash)
    reject_recent_password(new_password, current_hash, previous)

    # Use Argon2id for the new password; the caller controls commit/rollback.
    new_hash = _HASHER.hash(new_password)
    now = db.execute(select(func.clock_timestamp())).scalar_one()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise PasswordHistoryUnavailable("Database clock is invalid.")

    # Save the former current digest, unless registration/history already has it.
    previous_row = db.execute(
        select(history.c.password_hash)
        .where(history.c.user_id == verified_user_id)
        .order_by(*_order_columns(history))
        .limit(1)
    ).scalar_one_or_none()
    if previous_row != current_hash:
        to_insert: dict[str, Any] = {
            "user_id": verified_user_id, "password_hash": current_hash,
        }
        time_name = next(name for name in _HISTORY_ORDER_FIELDS if name in history.c)
        to_insert[time_name] = now
        db.execute(insert(history).values(**to_insert))

    updated = db.execute(
        update(users_table)
        .where(users_table.c.user_id == verified_user_id)
        .values(password_hash=new_hash, updated_at=now)
    )
    if updated.rowcount != 1:
        raise PasswordHistoryUnavailable("Password update was not confirmed.")

    # Revocation and security audit are part of the same caller transaction.
    from app.services.auth_session_store import revoke_user_sessions
    from app.services.login_otp_service import security_logs_table
    revoked = revoke_user_sessions(db, user_id=verified_user_id)
    if not isinstance(client_ip, str) or not client_ip.strip():
        raise PasswordHistoryUnavailable("A server-observed client IP is required.")
    try:
        ip_value = str(ipaddress.ip_address(client_ip.strip()))
    except ValueError:
        raise PasswordHistoryUnavailable("Invalid trusted client IP.") from None
    agent = ("".join(c for c in user_agent if c.isprintable())[:255]
             if isinstance(user_agent, str) else None)
    db.execute(insert(security_logs_table).values(
        user_id=verified_user_id,
        event_type="PASSWORD_CHANGED",
        outcome="success",
        ip_address=ip_value,
        user_agent=agent,
        event_details={"channel": "verified_password_change"},
        created_at=now,
    ))
    return PasswordChangeOutcome(verified_user_id, revoked, now.astimezone(timezone.utc))


def _local_preflight(*, setup: bool) -> None:
    """Deliberate localhost-only schema action; NO user/password changes."""
    from app.core.config import settings
    if settings.environment != "development":
        raise PasswordHistoryUnavailable("Development environment required.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise PasswordHistoryUnavailable("Expected PostgreSQL dormora_db.")
    host = engine.url.host or ""
    try:
        is_local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_local = host.casefold() == "localhost"
    if not is_local:
        raise PasswordHistoryUnavailable("Only local PostgreSQL is permitted.")

    if not {"user_id", "password_hash", "updated_at"}.issubset(users_table.c.keys()):
        raise PasswordHistoryUnavailable("Current user model is incompatible.")

    if setup:
        with engine.begin() as conn:
            history = _existing_history_table(conn)
            if history is None:
                _canonical_history_table().create(bind=conn, checkfirst=False)
                history = _existing_history_table(conn)
            if history is None:
                raise PasswordHistoryUnavailable("Password history setup failed.")
    else:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                history = _existing_history_table(conn)

    print("DORMORA FILE 104 - PASSWORD HISTORY")
    print("Local development and database: PASS")
    print("User password-hash schema: PASS")
    if history is None:
        print("History table: MISSING")
        print("Next: run --setup to create public.password_history (no user changes).")
    else:
        print("History table: PRESENT and compatible")
        print("Recent-password policy: current + two preceding passwords")
    print("No user password, session, or audit record was changed.")
    print("File 104", "setup OK" if setup else "check OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora password-history service")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only schema check")
    mode.add_argument("--setup", action="store_true", help="explicit local history schema setup")
    args = parser.parse_args()
    try:
        _local_preflight(setup=args.setup)
    except PasswordHistoryUnavailable as error:
        print("FILE 104 STOPPED:", str(error))
        raise SystemExit(1) from None
    except Exception as error:
        print("FILE 104 FAILED:", type(error).__name__)
        print("Check local DB permissions and the existing password-history schema.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
