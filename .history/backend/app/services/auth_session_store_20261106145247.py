
"""Dormora Backend File 78 -- PostgreSQL-backed authenticated sessions.

CREATE: backend/app/services/auth_session_store.py

This module defines a dedicated public.auth_sessions table and provides
transaction-scoped operations for the browser token from File 77.

IMPORTANT:
- Importing this module NEVER creates a table, an authentication session,
  a cookie, or an API route.
- Run initialize_auth_session_schema() explicitly ONCE after checking the
  database, as a deliberate schema-setup step. It creates ONLY this table.
- insert_auth_session() must be called ONLY AFTER a successful login OTP
  check, in the SAME caller-owned transaction as OTP consumption, resetting
  failed-login counters, and recording LOGIN_SUCCESS (implemented later).
- Send the File 77 cookie ONLY after the transaction commits successfully.
- Every protected request must validate the session in PostgreSQL and honor
  the nine-minute idle expiry, regardless of browser cookie expiration.
- Logout/password reset must revoke the DB record, not merely clear a cookie.

No application startup code calls the schema initializer or enables login.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    func,
    inspect,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Session

from app.core.session_security import (
    InvalidSessionToken,
    SESSION_IDLE_TIMEOUT_SECONDS,
    session_token_digest,
)
from app.db.database import engine
from app.models.user import users_table


# Use the SAME metadata and exact user-id SQL type as Dormora's existing model.
# The table is not reflected and does not query PostgreSQL at module import.
auth_sessions_table = Table(
    "auth_sessions",
    users_table.metadata,
    Column("token_digest", String(64), primary_key=True),
    Column(
        "user_id",
        users_table.c.user_id.type,
        ForeignKey(users_table.c.user_id, ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("client_ip", String(45), nullable=True),
    Column("user_agent", String(255), nullable=True),
    CheckConstraint(
        "expires_at > last_seen_at",
        name="ck_dormora_auth_session_expiry",
    ),
    schema="public",
)

Index("ix_dormora_auth_sessions_user", auth_sessions_table.c.user_id)
Index("ix_dormora_auth_sessions_expiry", auth_sessions_table.c.expires_at)


class AuthSessionStoreUnavailable(RuntimeError):
    """Storage or schema is unavailable; HTTP routes must fail closed."""


@dataclass(frozen=True)
class ActiveAuthSession:
    """A DB-validated session; contains NO raw bearer token or digest."""

    user_id: int
    expires_at: datetime


def initialize_auth_session_schema() -> None:
    """EXPLICIT admin/setup operation: create the auth_sessions table only.

    Does not alter public.users or any existing table. An existing table with
    missing expected columns is rejected rather than silently modified.
    Never invoke this function on import or automatically at app startup.
    """
    expected = {
        "token_digest",
        "user_id",
        "created_at",
        "last_seen_at",
        "expires_at",
        "revoked_at",
        "client_ip",
        "user_agent",
    }

    try:
        with engine.begin() as connection:
            inspector = inspect(connection)

            if not inspector.has_table("auth_sessions", schema="public"):
                auth_sessions_table.create(
                    bind=connection,
                    checkfirst=False,
                )

            actual = {
                col["name"]
                for col in inspect(connection).get_columns(
                    "auth_sessions",
                    schema="public",
                )
            }

            if actual != expected:
                raise AuthSessionStoreUnavailable(
                    "Existing auth_sessions schema differs from File 78."
                )

    except AuthSessionStoreUnavailable:
        raise
    except Exception:
        raise AuthSessionStoreUnavailable(
            "Authentication-session schema setup failed."
        ) from None


def _require_transaction(session: Session) -> None:
    """Require the caller to control commit/rollback with SessionLocal.begin()."""
    if not isinstance(session, Session) or not session.in_transaction():
        raise ValueError("A caller-owned database transaction is required.")


def _db_now(session: Session) -> datetime:
    """Read current PostgreSQL clock after obtaining any required locks."""
    value = session.execute(
        select(func.clock_timestamp())
    ).scalar_one()

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AuthSessionStoreUnavailable(
            "Invalid database session clock."
        )

    return value.astimezone(timezone.utc)


def _sanitized_ip(value: str | None) -> str | None:
    if value is None:
        return None

    try:
        parsed = ip_address(value)
        mapped = getattr(parsed, "ipv4_mapped", None)
        return str(mapped if mapped is not None else parsed)
    except (ValueError, TypeError):
        raise ValueError("A trusted client IP is required.") from None


def _sanitized_agent(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    return "".join(
        ch for ch in value if ch.isprintable()
    )[:255] or None


def insert_auth_session(
    session: Session,
    *,
    user_id: int,
    token: str,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert a hashed session bearer token without committing.

    SECURITY PRECONDITION: The caller has verified this user's login OTP in
    this SAME transaction and locked/validated the account. This function is
    storage only; it is NOT a login authorization check by itself.

    Generate the random token using File 77 before the transaction. Do NOT
    send a Set-Cookie header until the transaction commits successfully.
    """
    _require_transaction(session)

    if type(user_id) is not int or user_id <= 0:
        raise ValueError("Invalid user ID.")

    digest = session_token_digest(token)
    vetted_ip = _sanitized_ip(client_ip)
    agent = _sanitized_agent(user_agent)
    now = _db_now(session)

    session.execute(
        insert(auth_sessions_table).values(
            token_digest=digest,
            user_id=user_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(
                seconds=SESSION_IDLE_TIMEOUT_SECONDS
            ),
            revoked_at=None,
            client_ip=vetted_ip,
            user_agent=agent,
        )
    )


def validate_auth_session(
    session: Session,
    token: str | None,
    *,
    renew_idle: bool = True,
) -> ActiveAuthSession | None:
    """Authorize against active DB state; optionally extend nine-minute idle.

    Call on EVERY protected request using a transaction. With row-level locks,
    concurrent logout/renewal cannot revive a revoked session. The caller must
    reissue File 77's cookie after a successful renewal and DB commit.
    """
    _require_transaction(session)

    try:
        digest = session_token_digest(token)  # type: ignore[arg-type]
    except InvalidSessionToken:
        return None

    stmt = (
        select(
            auth_sessions_table.c.user_id,
            auth_sessions_table.c.expires_at,
            auth_sessions_table.c.revoked_at,
            users_table.c.account_status,
            users_table.c.email_verified_at,
        )
        .select_from(
            auth_sessions_table.join(
                users_table,
                auth_sessions_table.c.user_id == users_table.c.user_id,
            )
        )
        .where(auth_sessions_table.c.token_digest == digest)
        .with_for_update(of=auth_sessions_table)
    )

    row = session.execute(stmt).mappings().first()
    now = _db_now(session)

    if row is None:
        return None

    expiry = row["expires_at"]

    if (
        row["revoked_at"] is not None
        or not isinstance(expiry, datetime)
        or expiry.tzinfo is None
        or expiry.astimezone(timezone.utc) <= now
        or row["account_status"] != "active"
        or row["email_verified_at"] is None
    ):
        return None

    if renew_idle:
        expiry = now + timedelta(
            seconds=SESSION_IDLE_TIMEOUT_SECONDS
        )
        session.execute(
            update(auth_sessions_table)
            .where(auth_sessions_table.c.token_digest == digest)
            .values(
                last_seen_at=now,
                expires_at=expiry,
            )
        )

    return ActiveAuthSession(
        user_id=int(row["user_id"]),
        expires_at=expiry,
    )


def revoke_auth_session(
    session: Session,
    token: str | None,
) -> bool:
    """Revoke one browser's DB session. No cookie or commit is performed here."""
    _require_transaction(session)

    try:
        digest = session_token_digest(token)  # type: ignore[arg-type]
    except InvalidSessionToken:
        return False

    row = session.execute(
        select(auth_sessions_table.c.revoked_at)
        .where(auth_sessions_table.c.token_digest == digest)
        .with_for_update()
    ).first()

    if row is None or row[0] is not None:
        return False

    now = _db_now(session)

    session.execute(
        update(auth_sessions_table)
        .where(auth_sessions_table.c.token_digest == digest)
        .values(revoked_at=now)
    )

    return True


def revoke_user_sessions(
    session: Session,
    *,
    user_id: int,
) -> int:
    """Invalidate all active sessions after a password reset/account removal.

    Must be invoked within the caller's account-locked transaction to prevent
    a concurrent login from racing a password-change revocation.
    """
    _require_transaction(session)

    if type(user_id) is not int or user_id <= 0:
        raise ValueError("Invalid user ID.")

    now = _db_now(session)

    result = session.execute(
        update(auth_sessions_table)
        .where(
            auth_sessions_table.c.user_id == user_id,
            auth_sessions_table.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    return int(result.rowcount or 0)
