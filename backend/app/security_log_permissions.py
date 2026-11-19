
"""Dormora FullStack 3 - File 130: read-only security log permissions audit.

CREATE: backend/app/security_log_permissions.py
RUN:    python -m app.security_log_permissions --check

Examine the EFFECTIVE PostgreSQL privileges of Dormora's backend connection
for public.security_logs. This tool reads only PostgreSQL catalog metadata;
it does not revoke grants, create roles, change accounts, or inspect log rows.

Why: File 127 found that the application connection may DELETE audit records.
The target design is an application runtime role that can INSERT and SELECT
logs but cannot UPDATE, DELETE, TRUNCATE, or assume ownership of the table.

Do NOT use pgAdmin's postgres superuser to evaluate the application's access.
This script connects using the same SQLAlchemy engine as the FastAPI backend.
If the backend's role owns the table, changing GRANTs alone does not provide
reliable separation; a distinct runtime role and DBA-owned table are needed.

Run only from the local development environment against local dormora_db.
"""

from __future__ import annotations

import argparse
import ipaddress
from dataclasses import dataclass


@dataclass(frozen=True)
class PrivilegeReport:
    database: str
    effective_role: str
    login_role: str
    table_owner: str
    superuser: bool
    owner_inherited: bool
    owner_member: bool
    owner_settable: bool
    can_select: bool
    can_insert: bool
    can_update: bool
    can_delete: bool
    can_truncate: bool
    can_trigger: bool
    row_security: bool
    force_row_security: bool
    trigger_names: tuple[str, ...]


class SecurityLogPermissionError(RuntimeError):
    """Cannot safely determine effective permissions."""


def _is_loopback(host: str | None) -> bool:
    if not isinstance(host, str) or not host.strip():
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.casefold() == "localhost"


def _flag(condition: bool) -> str:
    return "YES" if condition else "NO"


def _assessment(report: PrivilegeReport) -> tuple[str, tuple[str, ...]]:
    """Interpret catalog privileges conservatively; do not equate ACLs with proof."""
    observations: list[str] = []

    if report.superuser:
        observations.append("Runtime role is SUPERUSER; it can bypass audit protections.")
    if report.effective_role == report.table_owner:
        observations.append("Runtime role OWNS security_logs; separate table ownership from app runtime.")
    elif report.owner_inherited or report.owner_settable:
        observations.append("Runtime role inherits owner privileges or can SET ROLE to the table owner.")
    if report.can_delete:
        observations.append("Runtime role has effective DELETE privilege on security_logs.")
    if report.can_update:
        observations.append("Runtime role has effective UPDATE privilege on security_logs.")
    if report.can_truncate:
        observations.append("Runtime role has effective TRUNCATE privilege on security_logs.")
    if report.can_trigger:
        observations.append("Runtime role has TRIGGER privilege; review whether it can affect audit integrity.")
    if not report.can_insert:
        observations.append("Runtime role cannot INSERT audit records: normal security logging may fail.")
    if not report.can_select:
        observations.append("Runtime role cannot SELECT audit records: monitoring queries may fail.")

    if observations:
        return "REVIEW REQUIRED", tuple(observations)
    return "PRIVILEGES RESTRICTED", (
        "No dangerous table DML privileges or ownership rights were detected.",
        "This alone does not prove append-only logs (review functions, triggers and DBA access).",
    )


def _load_report() -> PrivilegeReport:
    """Read only PostgreSQL catalog state using the *backend* database role."""
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.database import SessionLocal, engine

    if settings.environment != "development":
        raise SecurityLogPermissionError("Development environment is required.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise SecurityLogPermissionError("Expected local PostgreSQL dormora_db.")
    if not _is_loopback(engine.url.host):
        raise SecurityLogPermissionError("Database host must be local loopback.")

    # The two-argument pg_has_role variants refer to current_user. The audit
    # must measure privileges of the app's active role, not the pgAdmin role.
    metadata_sql = text("""
        SELECT
            current_database() AS database_name,
            current_user AS effective_role,
            session_user AS login_role,
            owner.rolname AS table_owner,
            current_role_info.rolsuper AS superuser,
            pg_has_role(owner.oid, 'USAGE') AS owner_inherited,
            pg_has_role(owner.oid, 'MEMBER') AS owner_member,
            pg_has_role(owner.oid, 'SET') AS owner_settable,
            has_table_privilege(c.oid, 'SELECT') AS can_select,
            has_table_privilege(c.oid, 'INSERT') AS can_insert,
            has_table_privilege(c.oid, 'UPDATE') AS can_update,
            has_table_privilege(c.oid, 'DELETE') AS can_delete,
            has_table_privilege(c.oid, 'TRUNCATE') AS can_truncate,
            has_table_privilege(c.oid, 'TRIGGER') AS can_trigger,
            c.relrowsecurity AS row_security,
            c.relforcerowsecurity AS force_row_security
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = c.relnamespace
        JOIN pg_catalog.pg_roles AS owner ON owner.oid = c.relowner
        JOIN pg_catalog.pg_roles AS current_role_info
          ON current_role_info.rolname = current_user
        WHERE namespace.nspname = 'public'
          AND c.relname = 'security_logs'
          AND c.relkind IN ('r', 'p')
    """)
    triggers_sql = text("""
        SELECT tgname
        FROM pg_catalog.pg_trigger AS t
        JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = c.relnamespace
        WHERE namespace.nspname = 'public'
          AND c.relname = 'security_logs'
          AND NOT t.tgisinternal
        ORDER BY tgname
    """)

    with SessionLocal.begin() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        row = db.execute(metadata_sql).mappings().one_or_none()
        if row is None:
            raise SecurityLogPermissionError("public.security_logs is not a base/partitioned table.")
        trigger_names = tuple(str(name) for name in db.execute(triggers_sql).scalars().all())

    mandatory = (
        "superuser", "owner_inherited", "owner_member", "owner_settable", "can_select",
        "can_insert", "can_update", "can_delete", "can_truncate",
        "can_trigger", "row_security", "force_row_security",
    )
    if any(type(row[name]) is not bool for name in mandatory):
        raise SecurityLogPermissionError("A required PostgreSQL privilege was unavailable.")

    return PrivilegeReport(
        database=str(row["database_name"]),
        effective_role=str(row["effective_role"]),
        login_role=str(row["login_role"]),
        table_owner=str(row["table_owner"]),
        superuser=row["superuser"],
        owner_inherited=row["owner_inherited"],
        owner_member=row["owner_member"],
        owner_settable=row["owner_settable"],
        can_select=row["can_select"],
        can_insert=row["can_insert"],
        can_update=row["can_update"],
        can_delete=row["can_delete"],
        can_truncate=row["can_truncate"],
        can_trigger=row["can_trigger"],
        row_security=row["row_security"],
        force_row_security=row["force_row_security"],
        trigger_names=trigger_names,
    )


def _show_report(report: PrivilegeReport) -> None:
    status, observations = _assessment(report)
    print("DORMORA FILE 130 -- SECURITY LOG DATABASE PERMISSIONS")
    print("Mode: READ-ONLY PostgreSQL catalog audit")
    print("Database:", report.database)
    print("Backend effective role:", report.effective_role)
    print("Backend login role:", report.login_role)
    print("security_logs table owner:", report.table_owner)
    print("Superuser:", _flag(report.superuser))
    print("Owner role inherited:", _flag(report.owner_inherited))
    print("Owner role membership:", _flag(report.owner_member))
    print("Can SET ROLE to owner:", _flag(report.owner_settable))
    print("Effective SELECT:", _flag(report.can_select))
    print("Effective INSERT:", _flag(report.can_insert))
    print("Effective UPDATE:", _flag(report.can_update))
    print("Effective DELETE:", _flag(report.can_delete))
    print("Effective TRUNCATE:", _flag(report.can_truncate))
    print("Effective TRIGGER:", _flag(report.can_trigger))
    print("Row-level security enabled:", _flag(report.row_security))
    print("Row-level security forced:", _flag(report.force_row_security))
    print("Custom trigger names:", ", ".join(report.trigger_names) or "None")
    print("Append-only permission assessment:", status)
    for note in observations:
        print("REVIEW:", note)
    print("No schema, grants, roles, sessions, log events or accounts were modified.")
    print("File 130 check OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Dormora runtime-role security-log permission review",
    )
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        report = _load_report()
        _show_report(report)
    except SecurityLogPermissionError as error:
        print("FILE 130 STOPPED:", str(error))
        raise SystemExit(1) from None
    except Exception as error:
        # Never expose DB credentials or connection strings from an exception.
        print("FILE 130 FAILED:", type(error).__name__)
        print("Inspect the local application database role and PostgreSQL catalog access.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
