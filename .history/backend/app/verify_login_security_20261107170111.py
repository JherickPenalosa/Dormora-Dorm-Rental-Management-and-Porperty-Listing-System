
"""Dormora Backend File 92 -- READ-ONLY login security verification.

CREATE: backend/app/verify_login_security.py
RUN:    python -m app.verify_login_security --check

Checks the configured login lockout and IP-blocking policies, then reviews
recent aggregated PostgreSQL audit events and current lockout counts.

SAFETY:
- Never submits passwords or OTPs, contacts Gmail, or calls check_login_ip().
- Never changes users, security_logs, sessions, settings, or lockout counters.
- Database audit runs with a PostgreSQL READ ONLY transaction.
- Prints aggregated counts only: no account names, emails, IPs, user IDs,
  CAPTCHA tokens, OTPs, session tokens, or security event_details.
- Policy calculations and existing audit events are NOT a substitute for
  separately controlled end-to-end threshold, alert-email and expiry tests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address


class LoginSecurityVerificationError(RuntimeError):
    """A required local security policy or read-only check did not pass."""


AUDIT_EVENTS = (
    "LOGIN_FAILED",
    "LOGIN_LOCKED",
    "LOCKOUT_TIER_1",
    "LOCKOUT_TIER_2",
    "LOCKOUT_TIER_3",
    "IP_BLOCKED",
    "LOGIN_REQUEST",
    "LOGIN_REQUEST_LIMITED",
    "LOGIN_PASSWORD_VERIFIED",
    "LOGIN_SUCCESS",
)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise LoginSecurityVerificationError(reason)


def _local_database_only() -> None:
    from app.core.config import settings
    from app.db.database import engine

    host = engine.url.host or ""
    try:
        local_host = ip_address(host).is_loopback
    except ValueError:
        local_host = host.lower() == "localhost"

    _require(settings.environment == "development", "Development environment required.")
    _require(local_host, "Local PostgreSQL server required.")
    _require(engine.url.database == "dormora_db", "Expected dormora_db database.")
    _require(engine.dialect.name == "postgresql", "PostgreSQL required.")


def _check_policies() -> None:
    from app.services.login_service import (
        D1, FIRST_TIER, SECOND_TIER, THIRD_TIER,
        FIRST_LOCK_SECONDS, SECOND_LOCK_SECONDS, THIRD_LOCK_SECONDS,
        lockout_for_failure_count,
    )
    from app.services.login_ip_service import (
        STUDENT_D2, IP_FAILURE_THRESHOLD,
        FAILURE_WINDOW_SECONDS, IP_BLOCK_SECONDS,
    )
    from app.services.login_request_limit_service import LOGIN_REQUEST_LIMITS

    _require(
        (D1, FIRST_TIER, SECOND_TIER, THIRD_TIER) == (9, 3, 6, 9),
        "Progressive lockout threshold mismatch.",
    )
    _require(
        (FIRST_LOCK_SECONDS, SECOND_LOCK_SECONDS, THIRD_LOCK_SECONDS)
        == (24, 48, 96),
        "Progressive lockout duration mismatch.",
    )

    # Exercise the actual pure decision function, not a duplicate formula.
    expected_decisions = {
        0: (0, None), 1: (0, None), 2: (0, None),
        3: (24, 1), 4: (0, None), 5: (0, None),
        6: (48, 2), 7: (0, None), 8: (0, None),
        9: (96, 3), 10: (96, None), 14: (96, None),
    }
    for failed_count, expected in expected_decisions.items():
        _require(
            lockout_for_failure_count(failed_count) == expected,
            f"Lockout decision does not match assigned seed at count {failed_count}.",
        )
    for bad in (-1, 2.5, True):
        try:
            lockout_for_failure_count(bad)
        except ValueError:
            pass
        else:
            raise LoginSecurityVerificationError("Invalid failure count was accepted.")

    _require(
        (STUDENT_D2, IP_FAILURE_THRESHOLD, FAILURE_WINDOW_SECONDS, IP_BLOCK_SECONDS)
        == (6, 14, 600, 600),
        "Seeded IP-blocking policy mismatch.",
    )
    expected_request_limits = {
        "password": (10, 60),
        "otp_verify": (8, 60),
        "otp_resend": (12, 900),
    }
    _require(
        set(LOGIN_REQUEST_LIMITS) == set(expected_request_limits),
        "Login request limiter action mismatch.",
    )
    for action, (maximum, window) in expected_request_limits.items():
        policy = LOGIN_REQUEST_LIMITS[action]
        _require(
            (policy.max_requests, policy.window_seconds) == (maximum, window),
            f"Login request limit mismatch for {action}.",
        )

    print("Policy decisions: PASS")
    print("  Account lockout tiers: 3/6/9 failures -> 24/48/96 seconds")
    print("  IP block threshold: 14 LOGIN_FAILED events / 10 minutes -> 10-minute block")
    print("  Request quotas: password 10/min; OTP verify 8/min; resend 12/15min")


def _read_only_audit() -> None:
    from sqlalchemy import func, select, text
    from app.db.database import engine
    from app.models.user import users_table
    from app.services.login_ip_service import security_logs_table

    required_logs = {"event_type", "created_at", "outcome"}
    required_users = {"failed_login_attempts", "locked_until"}
    _require(required_logs.issubset(security_logs_table.c.keys()),
             "security_logs is missing a required audit column.")
    _require(required_users.issubset(users_table.c.keys()),
             "users is missing a required lockout column.")

    # PostgreSQL rejects INSERT/UPDATE/DELETE within this transaction.
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            now = connection.execute(select(func.clock_timestamp())).scalar_one()
            _require(
                isinstance(now, datetime)
                and now.tzinfo is not None
                and now.utcoffset() is not None,
                "Database returned an invalid timestamp.",
            )
            now = now.astimezone(timezone.utc)
            since = now - timedelta(hours=24)

            rows = connection.execute(
                select(
                    security_logs_table.c.event_type,
                    func.count().label("total"),
                )
                .where(
                    security_logs_table.c.created_at >= since,
                    security_logs_table.c.created_at <= now,
                    security_logs_table.c.event_type.in_(AUDIT_EVENTS),
                )
                .group_by(security_logs_table.c.event_type)
            ).all()
            counts = {str(event): int(total) for event, total in rows}

            active_lockouts = int(connection.execute(
                select(func.count()).select_from(users_table).where(
                    users_table.c.locked_until > now,
                )
            ).scalar_one())
            accounts_with_failures = int(connection.execute(
                select(func.count()).select_from(users_table).where(
                    users_table.c.failed_login_attempts > 0,
                )
            ).scalar_one())

    print("PostgreSQL read-only audit: PASS")
    print("  Window: previous 24 hours, counted using the database clock")
    for event in AUDIT_EVENTS:
        print(f"  {event}: {counts.get(event, 0)}")
    print(f"  Currently locked accounts: {active_lockouts}")
    print(f"  Accounts with a nonzero failed-login counter: {accounts_with_failures}")

    if counts.get("LOGIN_FAILED", 0) == 0:
        print("  Note: no failed-password event observed in this 24-hour window.")
    if not any(counts.get(f"LOCKOUT_TIER_{tier}", 0) for tier in (1, 2, 3)):
        print("  Note: tier-trigger events NOT yet observed; live lockout unverified.")
    if counts.get("IP_BLOCKED", 0) == 0:
        print("  Note: IP_BLOCKED event NOT yet observed; live IP blocking unverified.")
    print("  This audit does not generate any failed requests or test SMTP alerts.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Dormora login-security audit")
    parser.add_argument("--check", required=True, action="store_true",
                        help="Verify policies and read aggregated audit counts")
    parser.parse_args()

    try:
        _local_database_only()
        print("DORMORA FILE 92 - READ-ONLY LOGIN SECURITY VERIFICATION")
        _check_policies()
        _read_only_audit()
    except LoginSecurityVerificationError as error:
        print(f"VERIFICATION FAILED: {error}")
        raise SystemExit(1) from None
    except Exception as error:
        # Avoid leaking database credentials, usernames, or security-log content.
        print(f"VERIFICATION FAILED: {type(error).__name__}")
        print("Check local .env, PostgreSQL connectivity, and prior backend files.")
        raise SystemExit(1) from None

    print("File 92 verification OK | Policies passed | Audit read-only")
    print("NEXT: separate controlled end-to-end tests are still required for thresholds.")


if __name__ == "__main__":
    main()
