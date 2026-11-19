
"""Dormora Backend File 57 — READ-ONLY registration readiness audit.

DESTINATION: backend/app/db/registration_readiness_audit.py (NEW FILE).
RUN FROM backend: python -m app.db.registration_readiness_audit

Checks installed source, the 12-table PostgreSQL schema, seeded security
questions, required backend configuration, and the mounted HTTP protection.
This diagnostic NEVER submits registration, generates OTPs, emails anyone,
changes accounts, or enables public routes. PostgreSQL is queried in a
READ ONLY transaction. No secrets or personal database records are printed.

PASS   = the specific check was observed to pass.
BLOCK  = a concrete defect or missing prerequisite was detected.
REVIEW = a human review or a live end-to-end test is still required.

A PASS for a code/schema contract is NOT proof of production security.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[2]
PROJECT = BACKEND.parent
CHECKS: list[tuple[str, str, str]] = []

PYTHON_FILES = (
    "app/main.py",
    "app/core/config.py",
    "app/core/csrf_security.py",
    "app/core/otp_policy.py",
    "app/core/otp_security.py",
    "app/schemas/auth.py",
    "app/services/registration.py",
    "app/services/registration_workflow.py",
    "app/services/secure_registration.py",
    "app/services/otp_service.py",
    "app/services/email_service.py",
    "app/api/routes/secure_registration.py",
    "app/api/routes/registration_otp.py",
)

REQUIRED_DB_COLUMNS = {
    "users": {"user_id", "username", "email", "password_hash", "role",
              "account_status", "email_verified_at", "updated_at"},
    "user_profiles": {"user_id", "id_number", "first_name", "family_name",
                      "birthdate", "street", "barangay", "city", "province",
                      "country", "zip_code"},
    "renter_preferences": {"user_id", "preferred_rental_type",
                           "preferred_rental_area", "maximum_monthly_budget",
                           "target_move_in_date"},
    "property_owner_details": {"user_id", "primary_property_type",
                               "primary_property_area", "expected_monthly_rent",
                               "expected_availability_date"},
    "security_questions": {"question_id", "question_text", "is_active"},
    "user_security_answers": {"user_id", "question_id", "answer_hash"},
    "security_logs": {"user_id", "event_type", "outcome", "event_details",
                      "created_at", "ip_address", "user_agent"},
    "email_otps": {"otp_id", "user_id", "email_address", "purpose",
                   "code_nonce", "code_digest", "delivery_status",
                   "attempt_count", "max_attempts", "created_at", "expires_at",
                   "sent_at", "consumed_at", "invalidated_at"},
}

REQUIRED_ROUTES = {
    ("/api/auth/register", "POST"),
    ("/api/auth/registration/verify", "POST"),
    ("/api/auth/registration/resend", "POST"),
}


def report(status: str, name: str, detail: str = "") -> None:
    CHECKS.append((status, name, detail))
    print(f"[{status:6}] {name}" + (f" — {detail}" if detail else ""))


def normalize_question(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def read_ast(relative_path: str) -> ast.Module:
    path = BACKEND / relative_path
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def assignment_literal(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == name):
            return ast.literal_eval(node.value)
    raise ValueError(f"Assignment {name} not found")


def audit_source() -> None:
    print("\n1. SOURCE CODE AND SAFETY SWITCHES")
    missing = [name for name in PYTHON_FILES if not (BACKEND / name).is_file()]
    if missing:
        report("BLOCK", "Required Python files present", ", ".join(missing))
        return
    report("PASS", "Required Python files present", f"{len(PYTHON_FILES)} files")

    errors = []
    for filename in PYTHON_FILES:
        try:
            read_ast(filename)
        except (SyntaxError, UnicodeError, OSError) as exc:
            errors.append(f"{filename}: {type(exc).__name__}")
    if errors:
        report("BLOCK", "Python source syntax", "; ".join(errors))
        return
    report("PASS", "Python source syntax", "AST parsed without execution")

    for path, flag in (
        ("app/api/routes/secure_registration.py", "PUBLIC_REGISTRATION_ENABLED"),
        ("app/api/routes/registration_otp.py", "PUBLIC_REGISTRATION_OTP_ENABLED"),
    ):
        try:
            value = assignment_literal(read_ast(path), flag)
            report("PASS" if value is False else "BLOCK", flag,
                   "disabled" if value is False else "MUST remain False")
        except (ValueError, TypeError):
            report("BLOCK", flag, "Cannot verify literal False flag")

    main = read_ast("app/main.py")
    mounted = set()
    for node in ast.walk(main):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "app" and node.args
                and isinstance(node.args[0], ast.Name)):
            mounted.add(node.args[0].id)
    expected = {"_file56_registration_router", "_file56_otp_router"}
    report("PASS" if expected.issubset(mounted) else "BLOCK",
           "File 56 router mounts", "both found" if expected.issubset(mounted)
           else "Expected disabled router mounts are missing")

    try:
        questions = assignment_literal(read_ast("app/services/registration.py"),
                                       "ASSIGNED_QUESTIONS")
        valid = (isinstance(questions, (tuple, list)) and len(questions) == 3
                 and {q[0] for q in questions} == {"Q7", "Q2", "Q4"}
                 and all(len(q) == 3 for q in questions))
        report("PASS" if valid else "BLOCK", "Seed-assigned questions in File 52",
               "Q7/Q2/Q4" if valid else "Wrong assigned questions")
    except (ValueError, TypeError, IndexError):
        report("BLOCK", "Seed-assigned questions in File 52",
               "Could not inspect question mapping")

    try:
        from app.core import otp_policy as policy
        actual = (
            policy.OTP_EXPIRY_MINUTES,
            policy.OTP_MAX_FAILED_ATTEMPTS,
            policy.OTP_RESEND_COOLDOWN_SECONDS,
            policy.OTP_MAX_RESENDS,
            policy.OTP_RESEND_WINDOW_MINUTES,
        )
        expected_values = (3, 3, 60, 3, 15)
        report("PASS" if actual == expected_values else "BLOCK", "File 49 OTP policy",
               "expiry 3m / attempts 3 / cooldown 60s / resends 3 per 15m"
               if actual == expected_values else "Policy values differ from the student seed")
    except Exception as exc:
        report("BLOCK", "File 49 OTP policy", type(exc).__name__)


def audit_database() -> None:
    print("\n2. POSTGRESQL READ-ONLY SCHEMA AUDIT")
    try:
        from app.db.database import engine
        with engine.connect() as conn:
            if conn.dialect.name != "postgresql":
                report("BLOCK", "Database engine", "PostgreSQL required")
                return
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            rows = conn.execute(text("""
                SELECT table_name, column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
            """)).all()
            columns: dict[str, set[str]] = {}
            for table_name, column_name in rows:
                columns.setdefault(table_name, set()).add(column_name)

            for table, expected in REQUIRED_DB_COLUMNS.items():
                missing = sorted(expected - columns.get(table, set()))
                report("BLOCK" if missing else "PASS", f"public.{table} columns",
                       "missing: " + ", ".join(missing) if missing else
                       f"{len(expected)} required columns present")

            constraints = conn.execute(text("""
                SELECT pg_get_constraintdef(c.oid)
                  FROM pg_constraint AS c
                  JOIN pg_class AS t ON t.oid = c.conrelid
                  JOIN pg_namespace AS n ON n.oid = t.relnamespace
                 WHERE n.nspname = 'public'
                   AND t.relname = 'users' AND c.contype = 'c'
            """)).scalars().all()
            account_checks = [str(definition).lower() for definition in constraints
                              if "account_status" in str(definition).lower()]
            if not account_checks:
                report("REVIEW", "users.account_status constraint",
                       "No explicit CHECK constraint found; review permitted statuses")
            elif any("pending_verification" in check for check in account_checks):
                report("PASS", "users.account_status constraint",
                       "pending_verification appears in an account-status CHECK")
            else:
                report("BLOCK", "users.account_status constraint",
                       "pending_verification absent from existing CHECK")

            try:
                questions = assignment_literal(
                    read_ast("app/services/registration.py"), "ASSIGNED_QUESTIONS"
                )
                catalog = conn.execute(text("""
                    SELECT question_text, is_active
                      FROM public.security_questions
                """)).all()
                active = [normalize_question(str(q)) for q, enabled in catalog
                          if enabled is True]
                for label, _answer_field, canonical_text in questions:
                    count = active.count(normalize_question(canonical_text))
                    report("PASS" if count == 1 else "BLOCK",
                           f"Security question {label}",
                           "unique and active" if count == 1 else
                           f"expected one active match, found {count}")
            except Exception as exc:
                report("BLOCK", "Security question catalog", type(exc).__name__)
    except Exception as exc:
        report("BLOCK", "Read-only PostgreSQL connection", type(exc).__name__)
        print("  Check that PostgreSQL is running and backend/.env is configured.")


def audit_http() -> None:
    print("\n3. IN-PROCESS HTTP SECURITY (NO SIGNUPS)")
    try:
        from fastapi.testclient import TestClient
        from app.core.config import settings
        from app.main import app
        from app.api.routes import secure_registration, registration_otp

        routes = Counter(
            (route.path, method)
            for route in app.routes
            for method in (getattr(route, "methods", None) or ())
        )
        duplicates = [path for path in sorted(REQUIRED_ROUTES)
                      if routes[path] != 1]
        report("BLOCK" if duplicates else "PASS", "Protected route uniqueness",
               "missing or duplicate: " + repr(duplicates) if duplicates else
               "three routes mounted exactly once")

        if (secure_registration.PUBLIC_REGISTRATION_ENABLED is not False or
                registration_otp.PUBLIC_REGISTRATION_OTP_ENABLED is not False):
            report("BLOCK", "Runtime public registration flags", "must remain False")
            return
        report("PASS", "Runtime public registration flags", "both disabled")

        origin = settings.frontend_origin.rstrip("/")
        with TestClient(app) as client:
            health = client.get("/api/health")
            report("PASS" if health.status_code == 200 else "BLOCK",
                   "Health endpoint", f"HTTP {health.status_code}")
            csrf = client.get("/api/csrf", headers={"Origin": origin})
            token = csrf.json().get("csrf_token") if csrf.status_code == 200 else None
            report("PASS" if isinstance(token, str) and bool(token) else "BLOCK",
                   "CSRF token issuing", f"HTTP {csrf.status_code}")
            if not token:
                return

            endpoint = "/api/auth/registration/resend"
            no_token = client.post(endpoint, headers={"Origin": origin})
            report("PASS" if no_token.status_code == 403 else "BLOCK",
                   "Missing CSRF token rejected", f"HTTP {no_token.status_code}")

            foreign = client.post(endpoint, headers={
                "Origin": "https://invalid.example", "X-CSRF-Token": token,
            })
            report("PASS" if foreign.status_code == 403 else "BLOCK",
                   "Wrong origin rejected", f"HTTP {foreign.status_code}")

            allowed = client.post(endpoint, headers={
                "Origin": origin, "X-CSRF-Token": token,
            })
            report("PASS" if allowed.status_code == 404 else "BLOCK",
                   "Valid CSRF reaches disabled resend handler",
                   f"HTTP {allowed.status_code} (expect 404)")
            headers_ok = (
                health.headers.get("x-frame-options") == "DENY" and
                health.headers.get("x-content-type-options") == "nosniff"
            )
            report("PASS" if headers_ok else "BLOCK", "Security headers",
                   "DENY and nosniff" if headers_ok else "missing required headers")
    except Exception as exc:
        report("BLOCK", "In-process HTTP test", type(exc).__name__)
        print("  Ensure app imports and FastAPI TestClient are working.")


def audit_manual_gates() -> None:
    print("\n4. REQUIRED HUMAN / LIVE-TRANSACTION REVIEW")
    try:
        from app.core.config import settings
        settings.require_smtp_configuration()
        report("PASS", "SMTP configuration", "server settings available; no email sent")
    except Exception as exc:
        report("BLOCK", "SMTP configuration", type(exc).__name__)

    try:
        from app.core.config import settings
        settings.build_recaptcha_v2_verifier(client_ip="127.0.0.1")
        report("PASS", "Google reCAPTCHA v2 configuration",
               "verifier configured; no external request sent")
    except Exception as exc:
        report("BLOCK", "Google reCAPTCHA v2 configuration", type(exc).__name__)

    frontend_app = PROJECT / "frontend/src/App.jsx"
    frontend_register = PROJECT / "frontend/src/pages/RegisterPage.jsx"
    if not frontend_app.is_file() or not frontend_register.is_file():
        report("REVIEW", "React Privacy Notice integration",
               "Cannot inspect expected React App/RegisterPage paths")
    else:
        app_text = frontend_app.read_text(encoding="utf-8-sig")
        register_text = frontend_register.read_text(encoding="utf-8-sig")
        has_privacy_route = "/privacy" in app_text
        has_privacy_link = "/privacy" in register_text
        if has_privacy_route and has_privacy_link:
            report("REVIEW", "React Privacy Notice integration",
                   "Route and link found; verify actual notice content and consent")
        else:
            missing = []
            if not has_privacy_route:
                missing.append("/privacy route")
            if not has_privacy_link:
                missing.append("register-page Privacy Notice link")
            report("BLOCK", "React Privacy Notice integration",
                   "missing: " + ", ".join(missing))

    report("REVIEW", "Approved Dormora-specific registration fields",
           "Compare optional/required rules with signed instructor proposal")
    report("REVIEW", "File 48 → File 55 return-value contract",
           "Confirm real successful workflow returns user_id and pending_verification")
    report("REVIEW", "PostgreSQL registration + OTP live transaction",
           "Test pending user, rollback, delivery, verification and replays")
    report("REVIEW", "OTP email wording and recovery",
           "Confirm 3-minute expiry and safe recovery from delivery failures")
    report("REVIEW", "Instructor ID-number primary key requirement",
           "Current schema uses users.user_id; document/obtain approval")


def main() -> None:
    print("=" * 67)
    print("DORMORA FILE 57 — REGISTRATION READINESS AUDIT (READ ONLY)")
    print("=" * 67)
    audit_source()
    audit_database()
    audit_http()
    audit_manual_gates()
    counts = Counter(status for status, _name, _detail in CHECKS)
    print("\n" + "=" * 67)
    print(f"SUMMARY: PASS={counts['PASS']}  BLOCK={counts['BLOCK']}  "
          f"REVIEW={counts['REVIEW']}")
    print("READY_FOR_PUBLIC_REGISTRATION: NO")
    print("Registration and OTP APIs remain disabled and unmounted changes are NOT made.")
    print("No account created, OTP issued, email sent, or database rows changed.")
    print("Copy the report output to review any BLOCK or REVIEW items.")
    print("=" * 67)


if __name__ == "__main__":
    main()
