"""Dormora File 103: read-only IT 107 thirteen-protection readiness review.

CREATE: backend/app/mandatory_security_review.py
RUN:    python -m app.mandatory_security_review --check

Purpose: identify implementation evidence and unfinished verification work,
not certify that any protection is attack-proof. Inspects local source files
and PostgreSQL metadata; never writes to the database, sends email, changes
sessions, or prints secrets/account data. No HTTP routes are registered.

The authoritative criteria are Section 12 of Security1_Student_Handout.pdf.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import inspect, text

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent


@dataclass(frozen=True)
class Check:
    number: int
    title: str
    evidence: str
    status: str  # EVIDENCE, VERIFY, GAP
    next_test: str


def _source(relative_path: str) -> str:
    """Read only application source, never .env or other secret files."""
    path = (PROJECT_DIR / relative_path).resolve()
    try:
        path.relative_to(PROJECT_DIR.resolve())
    except ValueError:
        return ""
    if path.suffix not in {".py", ".jsx", ".js", ".ts", ".tsx", ".txt"}:
        return ""
    try:
        if not path.is_file() or path.stat().st_size > 1_500_000:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _has(relative_path: str, *needles: str) -> bool:
    content = _source(relative_path).casefold()
    return bool(content) and all(token.casefold() in content for token in needles)


def _exists(*relative_paths: str) -> bool:
    return any((PROJECT_DIR / path).is_file() for path in relative_paths)


def _any_has(paths: Iterable[str], *needles: str) -> bool:
    return any(_has(path, *needles) for path in paths)


def _row(number: int, title: str, condition: bool, evidence: str,
         next_test: str, *, require_manual: bool = True) -> Check:
    # Even EVIDENCE is NOT a pass: the handout grades actual attacks.
    status = ("VERIFY" if require_manual else "EVIDENCE") if condition else "GAP"
    return Check(number, title,
                 evidence if condition else "Expected implementation evidence was not found.",
                 status, next_test)


def _read_schema() -> dict[str, set[str]]:
    """Read PostgreSQL catalog metadata in a read-only transaction."""
    from app.core.config import settings
    from app.db.database import engine

    if settings.environment != "development":
        raise RuntimeError("File 103 is restricted to the development environment.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise RuntimeError("Expected local PostgreSQL database dormora_db.")
    host = (engine.url.host or "").strip()
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.lower() == "localhost"
    if not local:
        raise RuntimeError("File 103 refuses non-local database connections.")

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            inspector = inspect(connection)
            names = set(inspector.get_table_names(schema="public"))
            return {
                table: {column["name"] for column in
                        inspector.get_columns(table, schema="public")}
                for table in sorted(names)
            }


def build_report(schema: dict[str, set[str]]) -> list[Check]:
    """Assemble conservative source/schema evidence for all 13 protections."""
    route = "backend/app/api/routes/"
    services = "backend/app/services/"
    main = "backend/app/main.py"
    appjsx = "frontend/src/App.jsx"
    registration_sources = [
        route + "secure_registration.py",
        services + "registration_service.py",
        route + "registration_otp.py",
    ]
    login_sources = [
        route + "secure_login.py",
        services + "login_service.py",
    ]
    recovery_sources = [
        route + "password_recovery.py",
        route + "secure_password_recovery.py",
        services + "password_recovery_service.py",
        services + "password_change_service.py",
    ]
    security_sources = [
        services + "registration_service.py",
        services + "contact_encryption.py",
        "backend/app/core/field_encryption.py",
        "backend/app/core/security.py",
        "backend/app/core/encryption.py",
    ]
    checks: list[Check] = []

    sql_evidence = (_any_has(login_sources, "select(") or
                    _any_has(login_sources, "sqlalchemy"))
    checks.append(_row(1, "SQL injection", sql_evidence,
        "SQLAlchemy query construction found in login source.",
        "Test an injection input against login, recovery and every data API; review dynamic text() queries."))

    react = _source(appjsx)
    no_raw_html = bool(react) and "dangerouslySetInnerHTML" not in react
    checks.append(_row(2, "Cross-site scripting", no_raw_html,
        "The current App.jsx does not use dangerouslySetInnerHTML.",
        "Try <script>alert(1)</script> in permitted fields and audit strings; inspect every React view."))

    csrf_evidence = (_has(main, "csrf") and
                     _any_has([route + "secure_session.py", main], "x-csrf-token"))
    checks.append(_row(3, "CSRF", csrf_evidence,
        "CSRF middleware reference and token-header gate found.",
        "Remove/alter the CSRF token on a POST and expect rejection; test actual signed-token validation."))

    enumeration_evidence = _any_has(login_sources, "Invalid username or password")
    checks.append(_row(4, "Username enumeration", enumeration_evidence,
        "Login uses a generic invalid-credentials message.",
        "Compare unknown username vs wrong password AND forgot-password responses/timing."))

    ip_service = services + "login_ip_service.py"
    ip_evidence = _has(ip_service, "IP_FAILURE_THRESHOLD", "IP_BLOCK_SECONDS")
    checks.append(_row(5, "IP blocking", ip_evidence,
        "Seeded persistent IP blocking service file found.",
        "Use controlled test accounts to confirm 14 failures/10min blocks IP for 10min."))

    sessions = services + "auth_session_store.py"
    session_policy = "backend/app/core/session_security.py"
    session_evidence = ("auth_sessions" in schema and
                        _exists(sessions) and _exists(session_policy))
    checks.append(_row(6, "Session hardening", session_evidence,
        "Session table and server-side store/cookie policy modules found.",
        "Check HttpOnly, SameSite, session rotation, 9-minute idle expiry, logout/back button."))

    history_tables = {name for name in schema if "password" in name and "histor" in name}
    history_logic = _any_has(recovery_sources, "password_history") or _any_has(
        recovery_sources, "last_three") or _any_has(recovery_sources, "recent password")
    checks.append(_row(7, "Password history", bool(history_tables and history_logic),
        "Password-history table and recovery/change logic reference found.",
        "Verify an OTP-authorized change rejects the current and previous two passwords; check reuse is transactional."))

    honeypot_source = _any_has(registration_sources, "website")
    honeypot_frontend = _any_has([
        "frontend/src/pages/RegisterPage.jsx", "frontend/src/pages/RegistrationPage.jsx"
    ], "website")
    checks.append(_row(8, "Registration honeypot", honeypot_source and honeypot_frontend,
        "Registration backend and frontend both reference the honeypot field.",
        "Fill the hidden field via DevTools and confirm silent rejection with no account created."))

    required_log_fields = {"event_type", "outcome", "created_at", "ip_address", "user_agent"}
    logging_evidence = required_log_fields.issubset(schema.get("security_logs", set()))
    checks.append(_row(9, "Activity logging", logging_evidence,
        "public.security_logs has event, outcome, IP, agent, and timestamp columns.",
        "Confirm every required handout event is appended and visible only to admins."))

    safe_error_source = _any_has(
        [main, route + "secure_login.py", route + "secure_session.py"],
        "temporarily unavailable",
    )
    checks.append(_row(10, "Safe error handling", safe_error_source,
        "Generic service-unavailable responses appear in API source.",
        "Trigger invalid requests and DB errors; confirm responses hide tracebacks, SQL, and secrets."))

    ignore_file = PROJECT_DIR / ".gitignore"
    try:
        ignore_text = ignore_file.read_text(encoding="utf-8", errors="replace") if ignore_file.is_file() else ""
    except OSError:
        ignore_text = ""
    ignored = any(
        line.strip() in {".env", ".env.*", "**/.env", "**/.env.*",
                         "backend/.env", "backend/.env.*", "*.env"}
        for line in ignore_text.splitlines()
        if not line.strip().startswith("#")
    )
    checks.append(_row(11, "Secrets management", ignored,
        "Project .gitignore has an environment-file exclusion rule.",
        "Review .gitignore coverage and scan Git history for real credentials WITHOUT printing any secrets."))

    headers_evidence = _has(main, "X-Frame-Options", "X-Content-Type-Options")
    checks.append(_row(12, "Security headers", headers_evidence,
        "FastAPI source sets both required security-header names.",
        "Check response headers on API AND served frontend pages: DENY and nosniff on every page."))

    encrypted_columns = [
        col for columns in schema.values() for col in columns
        if re.search(r"encrypt|cipher|nonce|_iv$", col, flags=re.I)
    ]
    encrypt_logic = _any_has(security_sources, "AESGCM") or _any_has(
        security_sources, "AES-256")
    checks.append(_row(13, "AES-256 encryption at rest", bool(encrypt_logic and encrypted_columns),
        "Encryption implementation reference and encrypted/IV database column names found.",
        "Verify a real encrypted stored field is unreadable in SQL and decrypts only for its owner."))

    return checks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dormora File 103: read-only 13 mandatory protections review")
    parser.add_argument("--check", action="store_true", required=True,
                        help="inspect source structure and read-only database metadata")
    parser.parse_args()

    try:
        schema = _read_schema()
        checks = build_report(schema)
    except Exception as exc:
        print("FILE 103 REVIEW STOPPED:", type(exc).__name__)
        print("Run only in the backend .venv, with local dormora_db available.")
        raise SystemExit(1) from None

    print("DORMORA FILE 103 -- IT 107 REQUIRED PROTECTIONS REVIEW")
    print("Mode: READ-ONLY | Source and database metadata only | 13 controls")
    print("Status meanings: VERIFY = implementation evidence, manual test needed;")
    print("                 GAP = expected evidence not found; NOT proof of absence.")
    print("-" * 75)
    for check in checks:
        print(f"{check.number:02d}. [{check.status:6}] {check.title}")
        print("    Evidence:", check.evidence)
        print("    Next:    ", check.next_test)
    print("-" * 75)
    print("Source evidence:", sum(c.status == "VERIFY" for c in checks), "/ 13")
    print("Requires investigation:", sum(c.status == "GAP" for c in checks), "/ 13")
    print("IMPORTANT: No requirement is marked PASSED by static/database inspection.")
    print("Do live attack tests and demonstrate change-password and encrypted fields.")
    print("File 103 review OK | Database unchanged")


if __name__ == "__main__":
    main()
