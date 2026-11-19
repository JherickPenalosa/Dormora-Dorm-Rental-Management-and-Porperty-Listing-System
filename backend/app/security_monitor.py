
"""Dormora File 96 -- Section 14 security monitoring (command line only).

CREATE: backend/app/security_monitor.py

    python -m app.security_monitor --check  # read-only preview
    python -m app.security_monitor --run    # creates security_flags if missing;
                                            # adds unique daily findings

Four required patterns, based on last 24 hours of public.security_logs:
  1. A single IP with >= seeded failed-login threshold (14).
  2. One typed username attacked from >=3 distinct IPs.
  3. One user's >=5 OTP_FAILED events inside any 10-minute interval.
  4. LOGIN_SUCCESS between midnight and 05:00 Philippine time.

Do not register this script as a FastAPI route or put it in frontend/public.
The script does not attempt logins, call the OTP service, or change users.
Only --run writes to security_flags. Runs on local development DB only.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

PHT = timezone(timedelta(hours=8), name="PHT")
WINDOW = timedelta(hours=24)
OTP_WINDOW = timedelta(minutes=10)
FLAG_TYPES = (
    "IP_OVER_THRESHOLD",
    "ACCOUNT_TARGETED",
    "OTP_GUESSING",
    "OFF_HOURS_LOGIN",
)


class MonitorError(RuntimeError):
    """Safe, expected configuration or schema error."""


@dataclass(frozen=True)
class Finding:
    flag_type: str
    severity: str
    target: str
    count: int
    description: str


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise MonitorError(message)


def _canonical_ip(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = ipaddress.ip_address(value.strip())
        return str(parsed.ipv4_mapped or parsed) if parsed.version == 6 else str(parsed)
    except ValueError:
        return None


def _username(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip().casefold()
    return name[:255] if name else None


def _safe_print(value: str) -> str:
    # Attacker-supplied usernames may be in logs. Never pass raw control
    # characters/ANSI escape sequences into a terminal or later HTML.
    return re.sub(r"[^a-zA-Z0-9_.@:+-]", "?", value)[:100]


def _utc(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MonitorError("Audit timestamp is not timezone-aware.")
    return value.astimezone(timezone.utc)


def _check_environment() -> None:
    from app.core.config import settings
    from app.db.database import engine
    _require(settings.environment == "development", "Development environment required.")
    _require(engine.dialect.name == "postgresql", "PostgreSQL is required.")
    _require(engine.url.database == "dormora_db", "Expected dormora_db database.")
    _require(_canonical_ip(engine.url.host or "") in {"127.0.0.1", "::1"}
             or (engine.url.host or "").lower() == "localhost",
             "The PostgreSQL server must be local.")


def detect_findings(
    events: list[dict[str, Any]],
    usernames_by_id: dict[int, str],
    threshold: int,
) -> list[Finding]:
    """Pure pattern analysis: accepts already queried audit records.

    No database access, side effects, or credentials. Useful for isolated tests.
    Events must have event_type, outcome, ip_address, user_id,
    event_details and created_at. Any untrusted usernames are bounded.
    """
    failures_per_ip: dict[str, int] = defaultdict(int)
    ips_per_username: dict[str, set[str]] = defaultdict(set)
    otp_by_user: dict[int, list[datetime]] = defaultdict(list)
    offhours_by_user: dict[int, int] = defaultdict(int)

    for event in events:
        kind = event["event_type"]
        outcome = event["outcome"]
        ip = _canonical_ip(event["ip_address"])
        occurred = _utc(event["created_at"])
        user_id = event["user_id"]
        details = event.get("event_details")

        if kind == "LOGIN_FAILED" and outcome == "failure":
            if ip is not None:
                failures_per_ip[ip] += 1
                typed = details.get("username_typed") if isinstance(details, dict) else None
                name = _username(typed)
                if name is not None:
                    ips_per_username[name].add(ip)
        elif kind == "OTP_FAILED" and outcome == "failure":
            if type(user_id) is int and user_id > 0:
                otp_by_user[user_id].append(occurred)
        elif kind == "LOGIN_SUCCESS" and outcome == "success":
            if type(user_id) is int and user_id > 0:
                if occurred.astimezone(PHT).hour < 5:
                    offhours_by_user[user_id] += 1

    findings: list[Finding] = []
    for ip, failures in sorted(failures_per_ip.items()):
        if failures >= threshold:
            findings.append(Finding(
                "IP_OVER_THRESHOLD", "HIGH", ip, failures,
                f"{failures} failed logins from one IP in the last 24 hours",
            ))

    for username, ips in sorted(ips_per_username.items()):
        if len(ips) >= 3:
            findings.append(Finding(
                "ACCOUNT_TARGETED", "MED", username, len(ips),
                f"Username attacked from {len(ips)} different IP addresses",
            ))

    for uid, times in sorted(otp_by_user.items()):
        times.sort()
        interval: deque[datetime] = deque()
        largest = 0
        for at in times:
            while interval and at - interval[0] > OTP_WINDOW:
                interval.popleft()
            interval.append(at)
            largest = max(largest, len(interval))
        if largest >= 5:
            target = _username(usernames_by_id.get(uid)) or f"account-{uid}"
            findings.append(Finding(
                "OTP_GUESSING", "HIGH", target, largest,
                f"{largest} failed OTP entries within a ten-minute window",
            ))

    for uid, count in sorted(offhours_by_user.items()):
        target = _username(usernames_by_id.get(uid)) or f"account-{uid}"
        findings.append(Finding(
            "OFF_HOURS_LOGIN", "INFO", target, count,
            f"{count} successful login(s) between 00:00 and 05:00 PHT",
        ))

    return findings


def _fetch_events() -> tuple[datetime, int, list[dict[str, Any]], dict[int, str]]:
    from sqlalchemy import func, select, text
    from app.db.database import engine
    from app.models.user import users_table
    from app.services.login_otp_service import security_logs_table
    from app.services.login_ip_service import IP_FAILURE_THRESHOLD

    required = {"event_type", "outcome", "ip_address", "user_id", "event_details", "created_at"}
    _require(required.issubset(security_logs_table.c.keys()),
             "Security audit table is missing required columns.")
    _require({"user_id", "username"}.issubset(users_table.c.keys()),
             "User table is missing required columns.")
    _require(IP_FAILURE_THRESHOLD == 14, "Unexpected seeded IP threshold.")

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            now = _utc(connection.execute(select(func.clock_timestamp())).scalar_one())
            rows = connection.execute(
                select(
                    security_logs_table.c.event_type,
                    security_logs_table.c.outcome,
                    security_logs_table.c.ip_address,
                    security_logs_table.c.user_id,
                    security_logs_table.c.event_details,
                    security_logs_table.c.created_at,
                )
                .where(
                    security_logs_table.c.created_at > now - WINDOW,
                    security_logs_table.c.created_at <= now,
                    security_logs_table.c.event_type.in_((
                        "LOGIN_FAILED", "OTP_FAILED", "LOGIN_SUCCESS",
                    )),
                )
                .order_by(security_logs_table.c.created_at)
            ).mappings().all()
            ids = sorted({int(row["user_id"]) for row in rows
                          if type(row["user_id"]) is int and row["user_id"] > 0})
            usernames = {}
            if ids:
                for uid, username in connection.execute(
                    select(users_table.c.user_id, users_table.c.username)
                    .where(users_table.c.user_id.in_(ids))
                ).all():
                    usernames[int(uid)] = str(username)

    return now, IP_FAILURE_THRESHOLD, [dict(row) for row in rows], usernames


_CREATE_FLAGS_SQL = """
CREATE TABLE IF NOT EXISTS public.security_flags (
    flag_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    flag_date DATE NOT NULL,
    flag_type VARCHAR(48) NOT NULL,
    target_key CHAR(64) NOT NULL,
    target_display VARCHAR(255) NOT NULL,
    severity VARCHAR(8) NOT NULL,
    event_count INTEGER NOT NULL,
    description VARCHAR(255) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT security_flags_daily_unique
        UNIQUE (flag_date, flag_type, target_key)
)
"""

_INSERT_FLAG_SQL = """
INSERT INTO public.security_flags (
    flag_date, flag_type, target_key, target_display,
    severity, event_count, description
) VALUES (
    :flag_date, :flag_type, :target_key, :target_display,
    :severity, :event_count, :description
)
ON CONFLICT (flag_date, flag_type, target_key) DO NOTHING
"""


def _write_flags(run_at: datetime, findings: list[Finding]) -> tuple[int, int]:
    from sqlalchemy import inspect, text
    from app.db.database import engine

    created = 0
    duplicate = 0
    today = run_at.astimezone(PHT).date()
    with engine.begin() as connection:
        connection.execute(text(_CREATE_FLAGS_SQL))
        cols = {item["name"] for item in inspect(connection).get_columns(
            "security_flags", schema="public"
        )}
        needed = {"flag_id", "flag_date", "flag_type", "target_key",
                  "target_display", "severity", "event_count", "description", "detected_at"}
        _require(needed.issubset(cols), "Existing security_flags table is incompatible.")

        for finding in findings:
            _require(finding.flag_type in FLAG_TYPES, "Unexpected monitoring flag type.")
            key = hashlib.sha256(
                (finding.flag_type + "\x00" + finding.target).encode("utf-8")
            ).hexdigest()
            result = connection.execute(text(_INSERT_FLAG_SQL), {
                "flag_date": today,
                "flag_type": finding.flag_type,
                "target_key": key,
                "target_display": _safe_print(finding.target),
                "severity": finding.severity,
                "event_count": finding.count,
                "description": finding.description,
            })
            if result.rowcount == 1:
                created += 1
            else:
                duplicate += 1
    return created, duplicate


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora security monitoring script")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only monitor preview")
    mode.add_argument("--run", action="store_true", help="store daily flags in PostgreSQL")
    args = parser.parse_args()

    try:
        _check_environment()
        now, threshold, events, usernames = _fetch_events()
        findings = detect_findings(events, usernames, threshold)
        print("DORMORA FILE 96 - IT 107 MONITORING REPORT")
        print("Generated:", now.astimezone(PHT).strftime("%Y-%m-%d %I:%M %p PHT"))
        print("Scanned:", len(events), "relevant events (last 24 hours)")
        for finding in findings:
            print(f"[{finding.severity:4}] {finding.flag_type:<20} "
                  f"{_safe_print(finding.target):<22} {finding.description}")
        if not findings:
            print("No monitored attack patterns detected in the last 24 hours.")

        if args.check:
            print(f"Read-only preview: {len(findings)} finding(s); no flags written.")
            print("File 96 check OK")
            return

        created, duplicate = _write_flags(now, findings)
        print(f"New flags written: {created} | Already flagged today: {duplicate}")
        print("File 96 monitoring run OK")
    except MonitorError as error:
        print("MONITORING STOPPED:", error)
        raise SystemExit(1) from None
    except Exception as error:
        print("MONITORING FAILED:", type(error).__name__)
        print("Check local PostgreSQL access, audit schema and existing flag table.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
