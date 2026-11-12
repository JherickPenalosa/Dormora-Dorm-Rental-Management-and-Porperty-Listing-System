
"""Dormora Backend File 82 -- persistent login and OTP request rate limits.

CREATE: backend/app/services/login_request_limit_service.py

The service limits request volume BEFORE expensive CAPTCHA, password, OTP,
or email work. It is separate from File 72's seeded account-independent
14 LOGIN_FAILED events per 10 minutes and File 68's per-account OTP limits.

Actions (per trusted client IP, across all accounts):
  password:    10 requests per 60 seconds
  otp_verify:   8 requests per 60 seconds
  otp_resend:  12 requests per 15 minutes

All decisions are serialized per IP/action using a PostgreSQL advisory
transaction lock. Allowed requests are recorded in the EXISTING
public.security_logs table (no migration). Denials do not consume quota or
extend the wait; at most one rate-limit warning per action/window is logged.

This module does NOT provide routes, bypass CSRF, accept forwarded IP headers,
or enable login. The future HTTP routes MUST invoke this service with a
client IP from trusted request.client metadata and map storage failures to
HTTP 503 (fail closed) and denied decisions to HTTP 429 + Retry-After.
Never send passwords, OTPs, CAPTCHA values, identifiers, or session tokens.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Literal

from sqlalchemy import MetaData, Table, func, insert, select, text

from app.db.database import SessionLocal, engine


LoginRequestAction = Literal["password", "otp_verify", "otp_resend"]


@dataclass(frozen=True)
class LoginRequestPolicy:
    max_requests: int
    window_seconds: int


# These are additional anti-abuse limits, NOT the instructor's 14-failure IP
# block threshold. That seeded rule stays in File 72.
LOGIN_REQUEST_LIMITS: dict[str, LoginRequestPolicy] = {
    "password": LoginRequestPolicy(max_requests=10, window_seconds=60),
    "otp_verify": LoginRequestPolicy(max_requests=8, window_seconds=60),
    "otp_resend": LoginRequestPolicy(max_requests=12, window_seconds=900),
}

_REQUEST_EVENT = "LOGIN_REQUEST"
_LIMITED_EVENT = "LOGIN_REQUEST_LIMITED"

# Same existing audit table used by Files 68, 72, 74 and 79. Reflection does
# not create or alter it. This project's backend already requires PostgreSQL.
security_logs_table = Table(
    "security_logs", MetaData(), schema="public", autoload_with=engine
)


class LoginRequestLimiterUnavailable(RuntimeError):
    """An audit/DB failure prevents request authorization; return HTTP 503."""


@dataclass(frozen=True)
class LoginRequestLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    remaining_requests: int = 0


def _canonical_ip(value: str) -> str:
    """Accept only an IP from the ASGI connection; never proxy headers."""
    if not isinstance(value, str) or not value:
        raise ValueError("A trusted client IP is required.")
    parsed = ip_address(value)
    mapped = getattr(parsed, "ipv4_mapped", None)
    return str(mapped if mapped is not None else parsed)


def _safe_agent(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return "".join(ch for ch in value if ch.isprintable())[:255] or None


def _lock_key(client_ip: str, action: str) -> int:
    digest = hashlib.blake2b(
        f"dormora:login-request-limit:v1:{client_ip}:{action}".encode("ascii"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Invalid database timestamp.")
    return value.astimezone(timezone.utc)


def check_and_record_login_request(
    action: LoginRequestAction,
    *,
    client_ip: str,
    user_agent: str | None = None,
) -> LoginRequestLimitDecision:
    """Atomically count one protected request, or refuse it without counting.

    Invoke once per request, after trusted-Origin and CSRF validation but
    before CAPTCHA/password/OTP processing. This is the full rate-limit check:
    it is NOT a standalone authentication or permission decision.

    Allowed request event: LOGIN_REQUEST (outcome=info), with IP/action only.
    Limited event: LOGIN_REQUEST_LIMITED (outcome=blocked), at most one per
    IP/action/window so that floods cannot amplify audit-log writes.
    """
    if action not in LOGIN_REQUEST_LIMITS:
        raise ValueError("Unsupported login request action.")
    policy = LOGIN_REQUEST_LIMITS[action]
    canonical = _canonical_ip(client_ip)
    agent = _safe_agent(user_agent)

    try:
        with SessionLocal.begin() as session:
            # Cross-worker transaction lock: prevents parallel requests from
            # all reading the same quota and collectively exceeding it.
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": _lock_key(canonical, action)},
            )
            now = _aware_utc(
                session.execute(select(func.clock_timestamp())).scalar_one()
            )
            start = now - timedelta(seconds=policy.window_seconds)
            action_matches = (
                security_logs_table.c.event_details["action"].as_string()
                == action
            )
            recent = session.execute(
                select(security_logs_table.c.created_at)
                .where(
                    security_logs_table.c.ip_address == canonical,
                    security_logs_table.c.event_type == _REQUEST_EVENT,
                    security_logs_table.c.outcome == "info",
                    action_matches,
                    security_logs_table.c.created_at > start,
                    security_logs_table.c.created_at <= now,
                )
                .order_by(
                    security_logs_table.c.created_at.desc(),
                    security_logs_table.c.log_id.desc(),
                )
                .limit(policy.max_requests)
            ).scalars().all()

            if len(recent) >= policy.max_requests:
                oldest_relevant = _aware_utc(recent[-1])
                retry = max(
                    1,
                    math.ceil(
                        (
                            oldest_relevant
                            + timedelta(seconds=policy.window_seconds)
                            - now
                        ).total_seconds()
                    ),
                )
                # One warning per window; denied requests never extend quota
                # or flood the audit table with one log entry per retry.
                already_logged = session.execute(
                    select(security_logs_table.c.log_id)
                    .where(
                        security_logs_table.c.ip_address == canonical,
                        security_logs_table.c.event_type == _LIMITED_EVENT,
                        action_matches,
                        security_logs_table.c.created_at > start,
                        security_logs_table.c.created_at <= now,
                    )
                    .limit(1)
                ).first()
                if already_logged is None:
                    session.execute(
                        insert(security_logs_table).values(
                            event_type=_LIMITED_EVENT,
                            outcome="blocked",
                            ip_address=canonical,
                            user_agent=agent,
                            created_at=now,
                            event_details={
                                "channel": "login",
                                "action": action,
                                "max_requests": policy.max_requests,
                                "window_seconds": policy.window_seconds,
                            },
                        )
                    )
                return LoginRequestLimitDecision(
                    allowed=False, retry_after_seconds=retry
                )

            session.execute(
                insert(security_logs_table).values(
                    event_type=_REQUEST_EVENT,
                    outcome="info",
                    ip_address=canonical,
                    user_agent=agent,
                    created_at=now,
                    event_details={
                        "channel": "login",
                        "action": action,
                    },
                )
            )
            return LoginRequestLimitDecision(
                allowed=True,
                remaining_requests=policy.max_requests - len(recent) - 1,
            )
    except Exception:
        # Never fall back to allowing a login if quota/audit storage failed.
        raise LoginRequestLimiterUnavailable(
            "Login request rate limiting is temporarily unavailable."
        ) from None
