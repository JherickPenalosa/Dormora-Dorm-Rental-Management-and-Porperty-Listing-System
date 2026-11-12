
"""PostgreSQL-backed rate limiting for Dormora's authentication entry points.

Backend File 28 -- install as backend/app/services/rate_limit_service.py.

Uses the EXISTING public.security_logs table. No schema changes are made.
Each allowed request records a non-secret security event; blocked requests
are also audited, but do not count toward the next allowance window.

PostgreSQL transaction advisory locks serialize concurrent checks for the
same IP/account, including across separate FastAPI workers. These functions
are NOT connected to public routes until subsequent integration files.

Caller responsibilities:
- Get the client IP from a trusted connection/proxy configuration, never
  directly from untrusted X-Forwarded-For or client-supplied JSON.
- For OTP actions, pass an EXISTING user_id (security_logs has a user FK).
- Call before starting registration, issuing an OTP, or checking a code.
- Handle denied requests as HTTP 429 and use retry_after_seconds.
- Provide CAPTCHA, OTP-attempt rules, and other independent protections.
"""

import hashlib
import ipaddress
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, insert, select, text

from app.db.database import SessionLocal
from app.services.security_log_service import security_logs_table


RateLimitAction = Literal["registration", "otp_verify", "otp_resend"]


@dataclass(frozen=True)
class RateLimitPolicy:
    """Limits within a rolling time window, per IP and optionally per user."""

    window_seconds: int
    per_ip: int
    per_user: int | None = None


POLICIES: dict[str, RateLimitPolicy] = {
    "registration": RateLimitPolicy(window_seconds=3600, per_ip=5),
    "otp_verify": RateLimitPolicy(window_seconds=600, per_ip=30, per_user=10),
    "otp_resend": RateLimitPolicy(window_seconds=3600, per_ip=5, per_user=3),
}


@dataclass(frozen=True)
class RateLimitDecision:
    """Result for a future FastAPI endpoint to enforce."""

    allowed: bool
    remaining: int
    retry_after_seconds: int


def _advisory_lock_id(key: str) -> int:
    """Stable signed 64-bit PostgreSQL advisory-lock identifier."""
    return int.from_bytes(
        hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )


def validate_rate_limit_request(
    action: RateLimitAction,
    *,
    client_ip: str,
    user_id: int | None = None,
) -> tuple[str, RateLimitPolicy]:
    """Validate identifiers without connecting to PostgreSQL.

    A known user_id is required for OTP actions so the user-level limit
    cannot be bypassed by simply omitting an identifier.
    """
    if not isinstance(action, str) or action not in POLICIES:
        raise ValueError("Unsupported rate-limit action.")
    if not isinstance(client_ip, str):
        raise ValueError("A trusted client IP address is required.")
    try:
        normalized_ip = str(ipaddress.ip_address(client_ip))
    except ValueError:
        raise ValueError("A valid client IPv4 or IPv6 address is required.") from None

    if action == "registration":
        if user_id is not None:
            raise ValueError("Registration rate limiting must not use a user_id.")
    elif type(user_id) is not int or user_id <= 0:
        raise ValueError("OTP rate limiting requires an existing positive user_id.")

    return normalized_ip, POLICIES[action]


def check_and_record_rate_limit(
    action: RateLimitAction,
    *,
    client_ip: str,
    user_id: int | None = None,
) -> RateLimitDecision:
    """Atomically check a rolling limit and record one security event.

    Each call is a security-relevant database write. Do not call it just to
    show a UI counter. If PostgreSQL is down, an exception propagates;
    authentication endpoints should fail closed instead of bypassing limits.
    """
    normalized_ip, policy = validate_rate_limit_request(
        action, client_ip=client_ip, user_id=user_id
    )
    event_type = f"rate_limit.{action}"

    # Acquire all locks in a deterministic order to avoid deadlocks. A
    # transaction-level lock is released automatically at commit/rollback.
    keys = [f"dormora:rl:v1:{action}:ip:{normalized_ip}"]
    if user_id is not None:
        keys.append(f"dormora:rl:v1:{action}:user:{user_id}")
    lock_ids = sorted({_advisory_lock_id(key) for key in keys})

    with SessionLocal.begin() as session:
        for lock_id in lock_ids:
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": lock_id},
            )

        now = session.execute(select(func.localtimestamp())).scalar_one()
        since = now - timedelta(seconds=policy.window_seconds)
        base = (
            select(
                func.count(security_logs_table.c.log_id),
                func.min(security_logs_table.c.created_at),
            )
            .where(
                security_logs_table.c.event_type == event_type,
                security_logs_table.c.outcome == "info",
                security_logs_table.c.created_at >= since,
            )
        )

        ip_count, ip_oldest = session.execute(
            base.where(security_logs_table.c.ip_address == normalized_ip)
        ).one()
        scopes = [(int(ip_count), ip_oldest, policy.per_ip)]

        if user_id is not None and policy.per_user is not None:
            user_count, user_oldest = session.execute(
                base.where(security_logs_table.c.user_id == user_id)
            ).one()
            scopes.append((int(user_count), user_oldest, policy.per_user))

        blocked_scopes = [
            (oldest, limit) for count, oldest, limit in scopes if count >= limit
        ]
        allowed = not blocked_scopes

        retry_after_seconds = 0
        if not allowed:
            retry_after_seconds = max(
                max(
                    1,
                    math.ceil(
                        (oldest + timedelta(seconds=policy.window_seconds) - now)
                        .total_seconds()
                    ),
                )
                for oldest, _limit in blocked_scopes
            )

        session.execute(
            insert(security_logs_table).values(
                user_id=user_id,
                event_type=event_type,
                outcome="info" if allowed else "blocked",
                ip_address=normalized_ip,
                event_details=(
                    {"channel": "web"}
                    if allowed
                    else {"channel": "web", "reason": "rate_limited"}
                ),
            )
        )

        remaining = (
            min(max(0, limit - count - 1) for count, _oldest, limit in scopes)
            if allowed
            else 0
        )

    return RateLimitDecision(
        allowed=allowed,
        remaining=remaining,
        retry_after_seconds=retry_after_seconds,
    )
