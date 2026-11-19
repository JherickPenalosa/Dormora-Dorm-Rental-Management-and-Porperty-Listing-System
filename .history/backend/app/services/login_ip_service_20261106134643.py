"""Dormora File 72: persistent IP blocking from failed login audit events.

Create: backend/app/services/login_ip_service.py
Uses existing public.security_logs; no migration or background task.
Call before password/OTP processing and again after a failed attempt commits.
The future route must enforce the returned decision. Importing does not enable
this protection. Only trusted connection metadata may supply client_ip.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address

from sqlalchemy import MetaData, Table, func, insert, select, text

from app.db.database import SessionLocal, engine

# Dormora's confirmed seed: D1=9, D2=6. Handout threshold = 8 + D2.
STUDENT_D2 = 6
IP_FAILURE_THRESHOLD = 8 + STUDENT_D2
FAILURE_WINDOW_SECONDS = 600
IP_BLOCK_SECONDS = 600
_BLOCK_REASON = "seeded_login_ip_block"
# File 66 records LOGIN_FAILED for incorrect credentials, including unknown users.
# Recovery must use that same failure event when checking security answers.
_FAILURE_EVENTS = ("LOGIN_FAILED",)

security_logs_table = Table(
    "security_logs", MetaData(), schema="public", autoload_with=engine
)


class LoginIpServiceUnavailable(RuntimeError):
    """Storage failure: the route must refuse login with a generic 503."""


@dataclass(frozen=True)
class LoginIpDecision:
    allowed: bool
    retry_after_seconds: int = 0
    newly_blocked: bool = False


def _trusted_ip(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("A trusted client IP is required.")
    parsed = ip_address(value)
    # IPv4 and its IPv4-mapped IPv6 form must share one blocking identity.
    mapped = getattr(parsed, "ipv4_mapped", None)
    return str(mapped if mapped is not None else parsed)


def _ip_variants(canonical: str) -> tuple[str, ...]:
    parsed = ip_address(canonical)
    if parsed.version == 4:
        return canonical, str(ip_address("::ffff:" + canonical))
    return (canonical,)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Expected a timezone-aware database timestamp.")
    return value.astimezone(timezone.utc)


def _lock_key(canonical_ip: str) -> int:
    digest = hashlib.blake2b(
        ("dormora:login-ip-block:v1:" + canonical_ip).encode("ascii"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


def check_login_ip(client_ip: str, *, user_agent: str | None = None) -> LoginIpDecision:
    """Block after 14 LOGIN_FAILED events in 10 minutes across all accounts.

    A block lasts 10 minutes from its creation. Blocked requests do not extend
    it. Advisory locks prevent duplicate block events across backend workers.
    Failure events must be committed before the post-failure call. This method
    does not record LOGIN_FAILED itself or alter account lockout counters.
    """
    canonical = _trusted_ip(client_ip)
    variants = _ip_variants(canonical)
    agent = None
    if isinstance(user_agent, str):
        agent = "".join(ch for ch in user_agent if ch.isprintable())[:255] or None
    try:
        with SessionLocal.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _lock_key(canonical)},
            )
            # Read the clock after the lock; transaction-start time can be stale.
            now = _utc(session.execute(select(func.clock_timestamp())).scalar_one())
            blocked_at = session.execute(
                select(func.max(security_logs_table.c.created_at)).where(
                    security_logs_table.c.ip_address.in_(variants),
                    security_logs_table.c.event_type == "IP_BLOCKED",
                    security_logs_table.c.event_details["reason"].as_string() == _BLOCK_REASON,
                )
            ).scalar_one()
            if blocked_at is not None:
                remaining = (_utc(blocked_at) + timedelta(seconds=IP_BLOCK_SECONDS) - now).total_seconds()
                if remaining > 0:
                    return LoginIpDecision(False, math.ceil(remaining))
            failures = session.execute(
                select(func.count()).select_from(security_logs_table).where(
                    security_logs_table.c.ip_address.in_(variants),
                    security_logs_table.c.event_type.in_(_FAILURE_EVENTS),
                    security_logs_table.c.outcome == "failure",
                    security_logs_table.c.created_at > now - timedelta(seconds=FAILURE_WINDOW_SECONDS),
                    security_logs_table.c.created_at <= now,
                )
            ).scalar_one()
            if int(failures) < IP_FAILURE_THRESHOLD:
                return LoginIpDecision(True)
            session.execute(insert(security_logs_table).values(
                event_type="IP_BLOCKED", outcome="blocked", ip_address=canonical,
                user_agent=agent, created_at=now,
                event_details={
                    "channel": "login", "reason": _BLOCK_REASON,
                    "failure_count": int(failures),
                    "window_seconds": FAILURE_WINDOW_SECONDS,
                    "block_seconds": IP_BLOCK_SECONDS,
                },
            ))
            return LoginIpDecision(False, IP_BLOCK_SECONDS, True)
    except Exception:
        raise LoginIpServiceUnavailable("Login security is temporarily unavailable.") from None