
"""Dormora Backend File 79 -- atomic login OTP and authenticated-session handoff.

CREATE: backend/app/services/login_completion_service.py

After File 70's signed pre-login cookie has been validated by an HTTP route,
complete_login_otp() uses one PostgreSQL transaction to:
  1. Verify/consume File 68's single-use login OTP.
  2. Insert a hashed session token through File 78.
  3. Reset File 75's consecutive password failures and lockout timestamp.
  4. Write an auditable LOGIN_SUCCESS event.

An incorrect OTP returns None AFTER committing File 68's failed-attempt count.
Any failure after a successful OTP check rolls the transaction back, so an OTP
cannot be consumed without also creating its matching DB session.

IMPORTANT: This module never sets cookies, exposes routes, or enables login.
The future route must call read_login_challenge(request), enforce Origin,
CSRF and IP/rate limits, then call this service. ONLY after the service
returns should the route set File 77's auth cookie and clear File 70's
pending challenge cookie. Never serialize a CompletedLogin object to JSON.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ipaddress import ip_address

from sqlalchemy import insert, update

from app.core.login_challenge import CHALLENGE_TTL_SECONDS, LoginChallenge
from app.core.session_security import generate_session_token
from app.db.database import SessionLocal
from app.models.user import users_table
from app.services.auth_session_store import insert_auth_session
from app.services.login_otp_service import security_logs_table, verify_login_otp


class LoginCompletionRejected(ValueError):
    """No valid pre-OTP browser challenge is available; restart login."""


class LoginCompletionUnavailable(RuntimeError):
    """Database or security-log failure: HTTP must fail closed with generic 503."""


@dataclass(frozen=True)
class CompletedLogin:
    """Private handoff to the route after a committed login transaction.

    session_token is a bearer secret: never log it or send it in response JSON.
    """

    user_id: int
    session_token: str = field(repr=False)


def _validate_challenge(challenge: LoginChallenge) -> None:
    """Defense in depth; callers MUST first verify File 70's signed cookie."""
    if (
        not isinstance(challenge, LoginChallenge)
        or type(challenge.user_id) is not int
        or challenge.user_id <= 0
        or type(challenge.otp_id) is not int
        or challenge.otp_id <= 0
        or type(challenge.started_at) is not int
    ):
        raise LoginCompletionRejected("Login verification must be restarted.")
    age = int(time.time()) - challenge.started_at
    if not 0 <= age < CHALLENGE_TTL_SECONDS:
        raise LoginCompletionRejected("Login verification must be restarted.")


def _validated_ip(value: str) -> str:
    """Input must come from request.client, not forwarded headers or browser JSON."""
    if not isinstance(value, str):
        raise LoginCompletionUnavailable("Login verification is unavailable.")
    try:
        parsed = ip_address(value)
    except ValueError:
        raise LoginCompletionUnavailable("Login verification is unavailable.") from None
    mapped = getattr(parsed, "ipv4_mapped", None)
    return str(mapped if mapped is not None else parsed)


def _safe_agent(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return "".join(ch for ch in value if ch.isprintable())[:255] or None


def complete_login_otp(
    challenge: LoginChallenge,
    submitted_code: str,
    *,
    client_ip: str,
    user_agent: str | None = None,
) -> CompletedLogin | None:
    """Complete a fully verified login atomically; return None on OTP failure.

    The caller MUST obtain challenge through read_login_challenge(request),
    which validates File 70's signature and expiry. A Python dataclass by
    itself is NOT proof that the password step was completed.

    Do not issue cookies or redirect based on this result until PostgreSQL
    commit succeeds. OTP failure writes are committed by leaving the context
    manager normally; do not raise an HTTPException inside the transaction.
    """
    _validate_challenge(challenge)
    if not isinstance(submitted_code, str):
        raise LoginCompletionRejected("Invalid verification code.")
    ip = _validated_ip(client_ip)
    agent = _safe_agent(user_agent)

    token: str | None = None
    verified = False
    try:
        with SessionLocal.begin() as session:
            # File 68 locks the active user and latest OTP row. Its unsuccessful
            # verification records and commits the attempt count in this txn.
            verified = verify_login_otp(
                session, challenge.user_id, challenge.otp_id, submitted_code
            )
            if verified:
                # Fresh random bearer token per full two-factor login; File 78
                # stores only its digest and enforces the 9-minute idle policy.
                token = generate_session_token()
                insert_auth_session(
                    session,
                    user_id=challenge.user_id,
                    token=token,
                    client_ip=ip,
                    user_agent=agent,
                )
                now = datetime.now(timezone.utc)

                changed = session.execute(
                    update(users_table)
                    .where(users_table.c.user_id == challenge.user_id)
                    .values(
                        failed_login_attempts=0,
                        locked_until=None,
                        updated_at=now,
                    )
                )
                if changed.rowcount != 1:
                    raise ValueError("Account state could not be updated.")

                session.execute(
                    insert(security_logs_table).values(
                        user_id=challenge.user_id,
                        event_type="LOGIN_SUCCESS",
                        outcome="success",
                        ip_address=ip,
                        user_agent=agent,
                        created_at=now,
                        event_details={
                            "channel": "login",
                            "method": "password_and_email_otp",
                        },
                    )
                )
        # Transaction successfully COMMITTED here. The HTTP route may now set
        # the auth cookie; it must NOT place this token in response JSON/logs.
    except Exception:
        raise LoginCompletionUnavailable(
            "Login verification is temporarily unavailable."
        ) from None

    if not verified:
        return None
    if token is None:
        # Defensive invariant: this branch cannot normally be reached.
        raise LoginCompletionUnavailable("Login verification is temporarily unavailable.")
    return CompletedLogin(user_id=challenge.user_id, session_token=token)
