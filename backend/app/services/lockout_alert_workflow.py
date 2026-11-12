"""Dormora File 74: send one alert attempt per recorded lockout event.

Create: backend/app/services/lockout_alert_workflow.py
Input is a trusted security_logs.log_id, never a browser-supplied recipient.
A committed claim prevents duplicate sends across workers/repeated calls.
No automatic retries: SMTP acceptance and a database commit cannot be atomic.
A crash after claiming can leave an unsent/uncertain alert requiring review.
Routes and File 66 still need integration; importing sends nothing.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import MetaData, Table, func, insert, select, text

from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.models.user import users_table
from app.services.security_alert_email import (
    LockoutAlert, build_lockout_alert_email, send_lockout_alert_email,
)

security_logs_table = Table(
    "security_logs", MetaData(), schema="public", autoload_with=engine
)
_TIERS = {"LOCKOUT_TIER_1": 1, "LOCKOUT_TIER_2": 2, "LOCKOUT_TIER_3": 3}
_CLAIM_EVENT = "ALERT_EMAIL_ATTEMPTED"


class LockoutAlertUnavailable(RuntimeError):
    """Internal failure; never disclose alert delivery state on the login page."""


@dataclass(frozen=True)
class LockoutAlertResult:
    status: Literal["sent", "failed", "already_attempted", "not_eligible"]


@dataclass(frozen=True)
class _Claim:
    user_id: int
    alert: LockoutAlert


def _lock_key(log_id: int) -> int:
    digest = hashlib.blake2b(
        f"dormora:lockout-alert:v1:{log_id}".encode("ascii"), digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


def _record(session, source_log_id: int, claim: _Claim,
            event_type: str, outcome: str) -> None:
    session.execute(insert(security_logs_table).values(
        user_id=claim.user_id, event_type=event_type, outcome=outcome,
        ip_address=claim.alert.client_ip, user_agent=claim.alert.user_agent,
        created_at=func.clock_timestamp(),
        event_details={
            "channel": "email", "purpose": "lockout_alert",
            "source_log_id": source_log_id, "tier": claim.alert.tier,
        },
    ))


def _claim(source_log_id: int) -> _Claim | LockoutAlertResult:
    with SessionLocal.begin() as session:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _lock_key(source_log_id)},
        )
        previous = session.execute(select(security_logs_table.c.log_id).where(
            security_logs_table.c.event_type.in_((_CLAIM_EVENT, "ALERT_EMAIL_SENT")),
            security_logs_table.c.event_details["source_log_id"].as_string() == str(source_log_id),
        ).limit(1)).first()
        if previous is not None:
            return LockoutAlertResult("already_attempted")
        event = session.execute(select(security_logs_table).where(
            security_logs_table.c.log_id == source_log_id,
            security_logs_table.c.event_type.in_(tuple(_TIERS)),
            security_logs_table.c.outcome == "blocked",
        )).mappings().first()
        if event is None or event["user_id"] is None:
            return LockoutAlertResult("not_eligible")
        account = session.execute(select(
            users_table.c.email, users_table.c.email_verified_at,
            users_table.c.account_status,
        ).where(users_table.c.user_id == event["user_id"])).mappings().first()
        if (account is None or account["email_verified_at"] is None
                or account["account_status"] != "active"):
            return LockoutAlertResult("not_eligible")
        occurred = event["created_at"]
        if (not isinstance(occurred, datetime) or occurred.tzinfo is None
                or occurred.utcoffset() is None):
            raise ValueError("Invalid lockout timestamp.")
        agent = event["user_agent"]
        agent = "".join(ch for ch in agent if ch.isprintable())[:255] if isinstance(agent, str) else None
        alert = LockoutAlert(
            email_address=str(account["email"]), tier=_TIERS[event["event_type"]],
            occurred_at=occurred.astimezone(timezone.utc),
            client_ip=str(event["ip_address"]), user_agent=agent,
        )
        # Validate configuration/message before permanently reserving a send.
        settings.require_smtp_configuration()
        if settings.smtp_security not in {"ssl", "starttls"}:
            raise RuntimeError("Encrypted SMTP is required.")
        build_lockout_alert_email(
            alert, sender_email=str(settings.smtp_from_email),
            sender_name=settings.smtp_from_name, frontend_origin=settings.frontend_origin,
        )
        claim = _Claim(int(event["user_id"]), alert)
        _record(session, source_log_id, claim, _CLAIM_EVENT, "info")
        return claim


def dispatch_lockout_alert(source_log_id: int) -> LockoutAlertResult:
    """Dispatch from the exact committed LOCKOUT_TIER event, once per event.

    The caller must get the event ID from trusted backend processing. Do not
    guess the latest event or take an ID from browser JSON. The claim commits
    before SMTP; repeated calls never resend an already attempted event.
    Return values are internal only and must not change the login response.
    """
    if type(source_log_id) is not int or not 0 < source_log_id <= 9_223_372_036_854_775_807:
        raise ValueError("A positive lockout event ID is required.")
    try:
        claim = _claim(source_log_id)
        if isinstance(claim, LockoutAlertResult):
            return claim
        try:
            send_lockout_alert_email(claim.alert)
        except Exception:
            with SessionLocal.begin() as session:
                _record(session, source_log_id, claim, "ALERT_EMAIL_FAILED", "failure")
            return LockoutAlertResult("failed")
        with SessionLocal.begin() as session:
            _record(session, source_log_id, claim, "ALERT_EMAIL_SENT", "success")
        return LockoutAlertResult("sent")
    except Exception:
        # A persisted claim remains after uncertain SMTP/audit failures.
        # Never remove it or retry automatically, as this could duplicate mail.
        raise LockoutAlertUnavailable("Security alert processing is unavailable.") from None