
"""Security event logging for Dormora's existing PostgreSQL security_logs table.

Backend File 27 -- install as backend/app/services/security_log_service.py.

Only structured, allowlisted event details are accepted. Never pass passwords,
OTP codes, tokens, credentials, request bodies, or raw exception messages.

The prepare_security_event() function is read-only and suitable for tests.
record_security_event() inserts ONE event in its own database transaction.
No database tables are created or altered by this module.
"""

import ipaddress
import re
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from sqlalchemy import Table, insert

from app.db.database import SessionLocal, engine
from app.models.user import users_table


SecurityOutcome = Literal["success", "failure", "blocked", "info"]

security_logs_table = Table(
    "security_logs",
    users_table.metadata,
    schema="public",
    autoload_with=engine,
)

_OUTCOMES = frozenset({"success", "failure", "blocked", "info"})
_EVENT_TYPE_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z")

# Log only controlled metadata, never arbitrary client input or request data.
_DETAIL_KEYS = frozenset(
    {"reason", "role", "channel", "http_status", "attempt_count"}
)
_REASONS = frozenset(
    {
        "registration_pending",
        "duplicate_account",
        "invalid_input",
        "email_delivery_failed",
        "invalid_otp",
        "expired_otp",
        "email_verified",
        "invalid_credentials",
        "account_locked",
        "rate_limited",
        "captcha_failed",
        "service_unavailable",
    }
)
_ROLES = frozenset({"renter", "property_owner", "admin"})
_CHANNELS = frozenset({"web", "email", "system"})


def _validated_details(details: Mapping[str, object] | None) -> dict[str, object]:
    """Allow only a small set of non-secret, typed security event fields."""
    if details is None:
        return {}
    if not isinstance(details, Mapping):
        raise ValueError("event_details must be a mapping of approved fields.")

    unknown = set(details) - _DETAIL_KEYS
    if unknown:
        raise ValueError("event_details contains an unsupported field.")

    cleaned: dict[str, object] = {}
    for key, value in details.items():
        if key == "reason":
            if not isinstance(value, str) or value not in _REASONS:
                raise ValueError("Invalid security event reason.")
        elif key == "role":
            if not isinstance(value, str) or value not in _ROLES:
                raise ValueError("Invalid security event role.")
        elif key == "channel":
            if not isinstance(value, str) or value not in _CHANNELS:
                raise ValueError("Invalid security event channel.")
        elif key == "http_status":
            if type(value) is not int or not 100 <= value <= 599:
                raise ValueError("http_status must be a valid HTTP status code.")
        elif key == "attempt_count":
            if type(value) is not int or not 0 <= value <= 10_000:
                raise ValueError("attempt_count must be between 0 and 10000.")
        cleaned[key] = value
    return cleaned


def prepare_security_event(
    *,
    event_type: str,
    outcome: SecurityOutcome,
    user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: UUID | str | None = None,
    event_details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate a security event without contacting or writing to PostgreSQL.

    event_type is a fixed application-defined label (e.g. registration_attempt).
    Do not build it from a username, email, token, or arbitrary user input.
    Pass an IP only after a trusted request-IP policy is established.
    """
    if not isinstance(event_type, str) or not _EVENT_TYPE_PATTERN.fullmatch(
        event_type
    ):
        raise ValueError("event_type must be 1-80 lowercase label characters.")
    if outcome not in _OUTCOMES:
        raise ValueError("Invalid security event outcome.")
    if user_id is not None and (type(user_id) is not int or user_id <= 0):
        raise ValueError("user_id must be a positive integer or None.")

    normalized_ip: str | None = None
    if ip_address is not None:
        if not isinstance(ip_address, str):
            raise ValueError("ip_address must be a string or None.")
        try:
            normalized_ip = str(ipaddress.ip_address(ip_address))
        except ValueError:
            raise ValueError("Invalid IPv4 or IPv6 address.") from None

    normalized_agent: str | None = None
    if user_agent is not None:
        if not isinstance(user_agent, str) or not 1 <= len(user_agent) <= 512:
            raise ValueError("user_agent must contain 1-512 characters.")
        if any(ord(char) < 32 or ord(char) == 127 for char in user_agent):
            raise ValueError("user_agent contains forbidden control characters.")
        normalized_agent = user_agent

    normalized_request_id: UUID | None = None
    if request_id is not None:
        try:
            normalized_request_id = (
                request_id if isinstance(request_id, UUID) else UUID(str(request_id))
            )
        except (TypeError, ValueError, AttributeError):
            raise ValueError("request_id must be a valid UUID.") from None

    return {
        "user_id": user_id,
        "event_type": event_type,
        "outcome": outcome,
        "ip_address": normalized_ip,
        "user_agent": normalized_agent,
        "request_id": normalized_request_id,
        "event_details": _validated_details(event_details),
    }


def record_security_event(
    *,
    event_type: str,
    outcome: SecurityOutcome,
    user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: UUID | str | None = None,
    event_details: Mapping[str, object] | None = None,
) -> int:
    """Insert a validated event in its own transaction; return its log_id.

    Using an independent transaction lets a failed registration transaction
    still be audited. Database errors propagate to the calling service;
    callers must choose a safe policy for failures in security-critical logs.
    """
    values = prepare_security_event(
        event_type=event_type,
        outcome=outcome,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        event_details=event_details,
    )
    with SessionLocal.begin() as session:
        log_id = session.execute(
            insert(security_logs_table)
            .values(**values)
            .returning(security_logs_table.c.log_id)
        ).scalar_one()
    return int(log_id)
