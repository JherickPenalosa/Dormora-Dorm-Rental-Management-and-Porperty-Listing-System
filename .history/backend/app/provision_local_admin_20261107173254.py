
"""Dormora File 94: local-only test administrator provisioning.

CREATE: backend/app/provision_local_admin.py

Read-only preflight:
    python -m app.provision_local_admin --check

Interactive promotion of a dedicated, already verified test account:
    python -m app.provision_local_admin --grant

Never run on production databases or deployed hosts.

Does not create users, passwords, or verification timestamps.
Register a dedicated test renter normally, verify its email OTP,
then grant the administrator role through this local command.

The account must still log in with password, CAPTCHA, and login OTP.
"""

from __future__ import annotations

import argparse
import hmac
from ipaddress import ip_address


class LocalAdminProvisioningError(RuntimeError):
    """Expected safe error without database secrets or personal data."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise LocalAdminProvisioningError(reason)


def _is_loopback(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _preflight() -> int:
    """Verify local safety conditions without modifying the database."""
    from sqlalchemy import func, inspect, select, text

    from app.core.config import settings
    from app.db.database import engine
    from app.models.user import users_table
    from app.services.auth_session_store import auth_sessions_table
    from app.services.login_otp_service import security_logs_table

    _require(
        settings.environment == "development",
        "Development environment required.",
    )
    _require(
        settings.frontend_origin.rstrip("/") == "http://localhost:5173",
        "Local React origin is required.",
    )
    _require(
        engine.dialect.name == "postgresql",
        "PostgreSQL is required.",
    )
    _require(
        _is_loopback(engine.url.host or ""),
        "Local PostgreSQL host is required.",
    )
    _require(
        engine.url.database == "dormora_db",
        "Unexpected database target.",
    )

    required_user_columns = {
        "user_id",
        "username",
        "email",
        "role",
        "password_hash",
        "account_status",
        "email_verified_at",
        "updated_at",
    }
    _require(
        required_user_columns.issubset(users_table.c.keys()),
        "User schema is incompatible.",
    )

    _require(
        {"user_id", "revoked_at"}.issubset(
            auth_sessions_table.c.keys()
        ),
        "Session schema is incompatible.",
    )

    required_audit_columns = {
        "user_id",
        "event_type",
        "outcome",
        "event_details",
        "created_at",
    }
    _require(
        required_audit_columns.issubset(
            security_logs_table.c.keys()
        ),
        "Audit schema is incompatible.",
    )

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text("SET TRANSACTION READ ONLY")
            )

            current_db = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            _require(
                current_db == "dormora_db",
                "Connected to unexpected database.",
            )

            _require(
                inspect(connection).has_table(
                    "auth_sessions",
                    schema="public",
                ),
                "File 78 auth_sessions table is missing.",
            )

            count = int(
                connection.execute(
                    select(func.count())
                    .select_from(users_table)
                    .where(users_table.c.role == "admin")
                ).scalar_one()
            )

    print("DORMORA FILE 94 - LOCAL ADMIN PREFLIGHT")
    print("Development environment and local dormora_db: PASS")
    print("User, session and audit schema: PASS")
    print(f"Existing administrator accounts: {count}")
    print(
        "Public registration remains renter/property_owner only."
    )

    return count


def _input_account() -> tuple[str, str]:
    print(
        "\nUse a DEDICATED TEST account registered "
        "through the normal OTP flow."
    )

    username = input(
        "Existing verified test username: "
    ).strip()

    email = input(
        "Matching registered email: "
    ).strip().lower()

    _require(
        3 <= len(username) <= 30
        and username.isascii()
        and all(
            character.isalnum() or character == "_"
            for character in username
        ),
        "Invalid target username.",
    )

    _require(
        3 <= len(email) <= 255
        and email.count("@") == 1
        and not any(character.isspace() for character in email),
        "Invalid target email.",
    )

    return username, email


def _grant_verified_test_account(
    username: str,
    email: str,
) -> int:
    """Promote, revoke sessions, and audit in one transaction."""
    from sqlalchemy import func, insert, select, text, update

    from app.db.database import SessionLocal
    from app.models.user import users_table
    from app.services.auth_session_store import revoke_user_sessions
    from app.services.login_otp_service import security_logs_table

    with SessionLocal.begin() as db:

        # Prevent two concurrent provisioning processes
        # from independently granting additional administrators.
        db.execute(
            text("SELECT pg_advisory_xact_lock(940094009400)")
        )

        existing_admins = int(
            db.execute(
                select(func.count())
                .select_from(users_table)
                .where(users_table.c.role == "admin")
            ).scalar_one()
        )

        _require(
            existing_admins == 0,
            "An administrator already exists; "
            "no additional admin granted.",
        )

        row = db.execute(
            select(users_table)
            .where(
                func.lower(users_table.c.username)
                == username.lower()
            )
            .with_for_update()
        ).mappings().first()

        _require(
            row is not None,
            "Test account not found.",
        )

        actual_email = str(
            row["email"] or ""
        ).strip().lower()

        _require(
            hmac.compare_digest(actual_email, email),
            "Username and registered email do not match.",
        )

        role = getattr(
            row["role"],
            "value",
            row["role"],
        )

        _require(
            role in {"renter", "property_owner"},
            "Only an existing renter/owner test account "
            "may be promoted.",
        )

        _require(
            row["account_status"] == "active"
            and row["email_verified_at"] is not None,
            "The account must have completed "
            "registration email verification.",
        )

        hashed = row["password_hash"]

        _require(
            isinstance(hashed, str)
            and hashed.startswith("$argon2id$"),
            "An existing Argon2id password hash is required.",
        )

        user_id = int(row["user_id"])

        now = db.execute(
            select(func.clock_timestamp())
        ).scalar_one()

        changed = db.execute(
            update(users_table)
            .where(users_table.c.user_id == user_id)
            .values(
                role="admin",
                updated_at=now,
            )
        )

        _require(
            changed.rowcount == 1,
            "Administrator role update was not confirmed.",
        )

        # Invalidate any sessions created under the old role.
        revoked = revoke_user_sessions(
            db,
            user_id=user_id,
        )

        # Persist an audit event without passwords,
        # email addresses, tokens, or personal details.
        db.execute(
            insert(security_logs_table).values(
                user_id=user_id,
                event_type="ADMIN_PROVISIONED",
                outcome="success",
                event_details={
                    "channel": "localhost_admin_provisioning",
                    "previous_role": role,
                    "method": "existing_verified_test_account",
                    "revoked_sessions": revoked,
                },
                created_at=now,
            )
        )

        # SessionLocal.begin() commits only after every
        # operation succeeds. Exceptions roll back changes.
        return revoked


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Provision one local Dormora test administrator "
            "from an email-verified account."
        )
    )

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--check",
        action="store_true",
        help="Read-only preflight",
    )

    mode.add_argument(
        "--grant",
        action="store_true",
        help="Interactive database role change",
    )

    args = parser.parse_args()

    try:
        existing_admins = _preflight()

        if args.check:
            print(
                "Preflight passed. No account, session, "
                "or audit record changed."
            )
            return

        _require(
            existing_admins == 0,
            "An administrator already exists; "
            "no additional admin granted.",
        )

        username, email = _input_account()

        print(
            "\nWARNING: This grants admin access "
            "in LOCAL dormora_db."
        )
        print(
            "All existing sessions for that account "
            "will be revoked."
        )

        confirmation = input(
            "Type GRANT LOCAL ADMIN to proceed: "
        ).strip()

        _require(
            confirmation == "GRANT LOCAL ADMIN",
            "Confirmation did not match.",
        )

        revoked = _grant_verified_test_account(
            username,
            email,
        )

    except (
        LocalAdminProvisioningError,
        EOFError,
        KeyboardInterrupt,
    ) as error:
        message = (
            str(error)
            if isinstance(error, LocalAdminProvisioningError)
            else "Cancelled."
        )

        print(
            f"PROVISIONING STOPPED: {message}"
        )
        raise SystemExit(1) from None

    except Exception as error:
        # Never expose raw SQL exceptions,
        # connection strings, or personal data.
        print(
            f"PROVISIONING FAILED: {type(error).__name__}"
        )
        print(
            "No role change should be assumed. "
            "Review database schema and constraints."
        )
        raise SystemExit(1) from None

    print(
        "\nFILE 94 SUCCESS: One verified local "
        "test account now has the admin role."
    )
    print(
        f"Old sessions revoked: {revoked}"
    )
    print(
        "Log in again through File 86 with "
        "password, CAPTCHA and Gmail OTP."
    )
    print(
        "Then GET /api/auth/admin/security "
        "should return HTTP 200."
    )


if __name__ == "__main__":
    main()
