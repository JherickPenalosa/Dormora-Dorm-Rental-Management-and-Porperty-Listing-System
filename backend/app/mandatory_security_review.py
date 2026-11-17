
"""Dormora FullStack 3 - File 135: refreshed thirteen security protections.

REPLACE: backend/app/mandatory_security_review.py (previously File 127).
RUN:     python -m app.mandatory_security_review --check

Read-only evidence review based on Section 12 and the event list in Section
13.4 of Security1_Student_Handout.pdf. Updated for Files 128-134, verified registration honeypot, CSRF audit logs,
restricted database-role permissions and AES-256-GCM contact storage.

This is NOT a penetration test or a certificate of security. EVIDENCE means
supporting code/schema was located; REVIEW means something needs investigation.
Every protection STILL requires the instructor's live attack/demo test.

No database writes, HTTP requests, account lookups, password/OTP generation,
email delivery, session changes, or secret-file contents are performed.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import inspect, text

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent.parent


@dataclass(frozen=True)
class Control:
    number: int
    name: str
    evidence: bool
    reason: str
    live_test: str

    @property
    def status(self) -> str:
        return "EVIDENCE" if self.evidence else "REVIEW"


def _read_source(path: Path) -> str:
    """Read only application source, never .env, keys, dumps or Git objects."""
    if path.suffix.lower() not in {".py", ".jsx", ".js", ".ts", ".tsx"}:
        return ""
    try:
        path.resolve().relative_to(PROJECT_DIR.resolve())
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_500_000:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def _sources(folder: str, extensions: set[str]) -> dict[str, str]:
    root = PROJECT_DIR / folder
    if not root.is_dir():
        return {}
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in extensions:
            continue
        if any(item in {"node_modules", "dist", "__pycache__", ".git"}
               for item in path.parts):
            continue
        content = _read_source(path)
        if content:
            result[path.relative_to(PROJECT_DIR).as_posix()] = content
    return result


def _contains(files: dict[str, str], paths: Iterable[str], *words: str) -> bool:
    return any(
        all(word.casefold() in files.get(path, "").casefold() for word in words)
        for path in paths
    )


def _matches(files: dict[str, str], pattern: str, *, prefixes: tuple[str, ...]) -> bool:
    expression = re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
    return any(expression.search(source) for path, source in files.items()
               if path.startswith(prefixes))


def _schema() -> tuple[dict[str, set[str]], bool | None, frozenset[str]]:
    """Inspect PostgreSQL metadata in a read-only transaction."""
    from app.core.config import settings
    from app.db.database import engine

    if settings.environment != "development":
        raise RuntimeError("File 127 is restricted to development mode.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise RuntimeError("Expected local PostgreSQL dormora_db.")
    hostname = (engine.url.host or "").strip()
    try:
        local = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        local = hostname.casefold() == "localhost"
    if not local:
        raise RuntimeError("File 127 refuses non-local databases.")

    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            inspector = inspect(conn)
            tables = set(inspector.get_table_names(schema="public"))
            columns = {
                table: {column["name"] for column in inspector.get_columns(table, schema="public")}
                for table in sorted(tables)
            }
            can_delete_logs = None
            seen_events: frozenset[str] = frozenset()
            if "security_logs" in tables:
                can_delete_logs = bool(conn.execute(text(
                    "SELECT has_table_privilege(current_user, 'public.security_logs', 'DELETE')"
                )).scalar_one())
                # Read event TYPE only, never event_details, names, IPs, or accounts.
                seen_events = frozenset(str(row).upper() for row in conn.execute(text(
                    "SELECT DISTINCT event_type FROM public.security_logs "
                    "WHERE event_type IN ('CSRF_REJECTED', 'RESET_REQUESTED')"
                )).scalars())
            return columns, can_delete_logs, seen_events


def _git_has_secret_filename() -> bool | None:
    """Check Git history FILENAMES only. Never inspect or print secret contents."""
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_DIR), "log", "--all", "--name-only",
             "--pretty=format:"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        name = Path(line.strip().replace("\\", "/")).name.casefold()
        if name == ".env" or (name.startswith(".env.") and name not in {
            ".env.example", ".env.sample", ".env.template",
        }):
            return True
    return False


def _env_ignored() -> bool:
    """Check ignore RULES, not contents of environment files."""
    lines: list[str] = []
    for relative in (".gitignore", "backend/.gitignore", "frontend/.gitignore"):
        path = PROJECT_DIR / relative
        try:
            if path.is_file() and not path.is_symlink():
                lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    rules = {line.strip().replace("\\", "/") for line in lines
             if line.strip() and not line.lstrip().startswith("#")}
    return bool(rules & {
        ".env", ".env.*", ".env*", "*.env", "**/.env", "**/.env.*",
        "backend/.env", "backend/.env.*", "frontend/.env",
        "frontend/.env.*", "*.local",
    })


def build_report(files: dict[str, str], schema: dict[str, set[str]],
                 *, git_exposure: bool | None, ignore_ok: bool,
                 can_delete_logs: bool | None,
                 observed_events: frozenset[str] = frozenset(),
                 honeypot_verified: bool = False) -> tuple[list[Control], list[str]]:
    """Use structural indicators only; never mistake them for proven safety."""
    api = "backend/app/api/routes/"
    services = "backend/app/services/"
    front = "frontend/src/"
    login = [api + "secure_login.py", services + "login_service.py"]
    recovery = api + "secure_password_recovery.py"
    session = api + "secure_session.py"
    main = "backend/app/main.py"
    all_backend = {path: value for path, value in files.items()
                   if path.startswith((api, services, "backend/app/core/", "backend/app/middleware/"))
                   or path == "backend/app/local_password_recovery_runner.py"}
    frontend = {path: value for path, value in files.items() if path.startswith(front)}
    controls: list[Control] = []
    notes: list[str] = []

    def add(number: int, label: str, condition: bool, why: str, test: str) -> None:
        controls.append(Control(number, label, bool(condition), why, test))

    # 1. Prepared SQL is structural evidence, never a proof across EVERY query.
    query_evidence = _contains(files, login, "select(") and _contains(files, [recovery], "select(")
    raw_interpolation = _matches(all_backend, r"\b(?:text|execute)\s*\(\s*f[\"']", prefixes=(api, services))
    add(1, "SQL injection", query_evidence and not raw_interpolation,
        "SQLAlchemy query builders in login/recovery; flag raw f-string SQL for review.",
        "Test SQL injection at login and each data endpoint; inspect all dynamic SQL.")
    if raw_interpolation:
        notes.append("Potential interpolated SQL detected in routes/services; review before demo.")

    # 2. Look across MODULAR frontend, not File 103's obsolete App.jsx-only check.
    unsafe_html = _matches(frontend, r"dangerouslySetInnerHTML|\.innerHTML\b|document\.write\s*\(", prefixes=(front,))
    add(2, "Cross-site scripting", bool(frontend) and not unsafe_html,
        "Modular React source searched for raw HTML rendering and document.write.",
        "Enter script payload in fields; confirm log text is inert in admin history.")
    if unsafe_html:
        notes.append("Review raw-HTML rendering in frontend/src before testing XSS.")

    csrf = ("csrf" in files.get(main, "").casefold() and
            _contains(files, [session, recovery], "x-csrf-token") and
            _matches(frontend, "x-csrf-token", prefixes=(front,)))
    add(3, "CSRF", csrf,
        "Middleware reference plus protected POST headers in backend and React.",
        "Remove/forge X-CSRF-Token on a state-changing POST; expect HTTP 403.")

    generic_login = _contains(files, [api + "secure_login.py"], "invalid username or password")
    generic_recovery = _contains(files, [recovery], "_INVALID", "recovery")
    add(4, "Username enumeration", generic_login and generic_recovery,
        "Generic login and recovery failure handling found; timing not assessed.",
        "Compare unknown username versus bad credentials in login AND recovery.")

    ip_service = services + "login_ip_service.py"
    add(5, "IP blocking", _contains(files, [ip_service], "IP_FAILURE_THRESHOLD", "IP_BLOCK_SECONDS")
        and "security_logs" in schema,
        "IP service and persistent security-log storage found (10 failures/10min).",
        "Controlled 10 failures across usernames in 10min; verify 10min IP block.")

    add(6, "Session hardening", "auth_sessions" in schema
        and "backend/app/core/session_security.py" in files
        and services + "auth_session_store.py" in files
        and session in files,
        "Database-backed sessions, cookie policy, and authenticated routes found.",
        "Check new session ID, HttpOnly/SameSite, 15min idle, logout and browser Back.")

    history = services + "password_change_service.py"
    add(7, "Password history", "password_history" in schema and history in files
        and _contains(files, [history], "RecentPasswordRejected", "password_hash")
        and recovery in files,
        "Password-history table and reusable password-change service located.",
        "Try current and two earlier passwords after OTP-authorized recovery.")

    add(8, "Honeypot", honeypot_verified,
        "File 134 checks real React field, both Pydantic validators, and secure route binding.",
        "Run an authorized HTTP negative test; verify a filled website creates no account.")

    event_names = (
        "REGISTERED", "ACCOUNT_VERIFIED", "LOGIN_SUCCESS", "LOGIN_FAILED",
        "OTP_SENT", "OTP_FAILED", "LOCKOUT_TIER_1", "LOCKOUT_TIER_2",
        "LOCKOUT_TIER_3", "IP_BLOCKED", "ALERT_EMAIL_SENT",
        "RESET_REQUESTED", "PASSWORD_CHANGED", "CAPTCHA_FAILED",
        "CSRF_REJECTED", "ADMIN_VIEWED_DASHBOARD", "ADMIN_ACCESS_DENIED",
    )
    combined = "\n".join(all_backend.values()).casefold()
    # File 75 emits lockout tiers dynamically: f"LOCKOUT_TIER_{tier}".
    # Recognize that implementation instead of claiming all three names absent.
    dynamic_tiers = 'lockout_tier_{tier}' in combined
    missing_events = [item for item in event_names
                      if item.casefold() not in combined
                      and not (dynamic_tiers and item.startswith("LOCKOUT_TIER_"))]
    logs = schema.get("security_logs", set())
    event_columns = {"event_type", "user_id", "ip_address", "user_agent",
                     "event_details", "created_at"}
    required_events = {"CSRF_REJECTED", "RESET_REQUESTED"}
    event_rows_present = required_events.issubset(observed_events)
    protected_runtime = can_delete_logs is False
    add(9, "Activity logging", event_columns.issubset(logs)
        and not missing_events and event_rows_present and protected_runtime,
        "Event source references, observed CSRF/RESET audit rows, and no runtime DELETE right.",
        "Demonstrate fresh audit rows and admin-only access; verify other role privileges.")
    if missing_events:
        notes.append("Event names not found in runtime source (manual review): " + ", ".join(missing_events))
    if not event_rows_present:
        notes.append("No audit rows confirmed for: " + ", ".join(sorted(required_events - observed_events)))
    if can_delete_logs is True:
        notes.append("Runtime database role may DELETE security_logs; verify File 132 switch.")
    notes.append("CSRF_REJECTED logging currently verified in the local File 129 runner, not normal production startup.")

    add(10, "Safe error handling", _matches(all_backend, r"temporarily unavailable", prefixes=(api, services))
        and _matches(all_backend, r"except\s+", prefixes=(api, services)),
        "Generic unavailable responses and exception-handling branches found.",
        "Send malformed inputs and simulate a safe backend error; never expose SQL/tracebacks.")

    secrets_ok = ignore_ok and git_exposure is False
    add(11, "Secrets / Git history", secrets_ok,
        "Ignore rules and historical secret-file PATHS inspected (not file contents).",
        "Run a separate confidential Git-history secret scan; rotate any exposed key.")
    if git_exposure is True:
        notes.append("An environment-secret filename appears in Git history; do not show its contents.")
    elif git_exposure is None:
        notes.append("Git history could not be checked automatically; inspect it manually.")
    if not ignore_ok:
        notes.append("Review .gitignore coverage for backend/frontend .env and local secrets.")

    add(12, "Security headers", _contains(files, [main], "X-Frame-Options", "X-Content-Type-Options"),
        "API entry source contains both required header names.",
        "Check X-Frame-Options: DENY and X-Content-Type-Options: nosniff on API AND web pages.")

    encrypted = schema.get("user_private_contacts", set())
    aes_file = services + "private_contact_encryption.py"
    add(13, "AES-256 encryption at rest", {"user_id", "nonce", "ciphertext"}.issubset(encrypted)
        and _contains(files, [aes_file], "AESGCM", "encrypt(", "decrypt(")
        and _contains(files, [session], "/api/auth/private-contact"),
        "AES-GCM module, owner-facing endpoint, and nonce/ciphertext columns found.",
        "Save and read own contact; verify DB ciphertext and cross-account denial.")

    return controls, notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora File 135 - IT 107 security evidence review")
    parser.add_argument("--check", action="store_true", required=True,
                        help="read-only source, Git filename and DB metadata inspection")
    args = parser.parse_args()
    assert args.check

    try:
        files = _sources("backend/app", {".py"})
        files.update(_sources("frontend/src", {".js", ".jsx", ".ts", ".tsx"}))
        schema, can_delete_logs, observed_events = _schema()
        # Use the tested File 134 schema/route/frontend checker directly, so
        # a text-only "website" reference cannot inflate the honeypot result.
        from app.registration_honeypot_check import (
            _check_frontend, _check_route, _check_schema,
        )
        registration_model = _check_schema()
        _check_route(registration_model)
        _check_frontend()
        results, notes = build_report(
            files, schema, git_exposure=_git_has_secret_filename(),
            ignore_ok=_env_ignored(), can_delete_logs=can_delete_logs,
            observed_events=observed_events, honeypot_verified=True,
        )
    except Exception as exc:
        # Never print database connection strings, private content or exception text.
        print("FILE 135 STOPPED:", type(exc).__name__)
        print("Check development configuration and local dormora_db availability.")
        raise SystemExit(1) from None

    print("DORMORA FILE 135 -- IT 107 THIRTEEN PROTECTIONS REVIEW")
    print("Mode: READ-ONLY | Source + PostgreSQL metadata/events + Git filenames")
    print("EVIDENCE is NOT a security pass; REVIEW is NOT proof of absence.")
    print("-" * 72)
    for item in results:
        print(f"{item.number:02d}. [{item.status:8}] {item.name}")
        print("    Basis:", item.reason)
        print("    Live: ", item.live_test)
    print("-" * 72)
    print(f"Implementation evidence: {sum(x.evidence for x in results)}/13")
    print(f"Investigate: {sum(not x.evidence for x in results)}/13")
    for note in notes:
        print("FOLLOW-UP:", note)
    print("IMPORTANT: The handout grades live attack demonstrations, not this report.")
    print("No accounts, passwords, sessions, OTPs or DB rows were modified.")
    print("File 135 review OK")


if __name__ == "__main__":
    main()
