
"""Dormora Backend File 124 -- localhost-only login + password-recovery runner.

CREATE: backend/app/local_password_recovery_runner.py

Run from backend/ with .venv active:
    python -m app.local_password_recovery_runner --check
    python -m app.local_password_recovery_runner --enable-local-recovery

This separate runner REUSES the existing File 86 local-login preflight and
mounts File 123's five staged recovery routes ONCE, in the same FastAPI app.
Normal ``uvicorn app.main:app`` remains unaffected; neither login nor recovery
is enabled merely by importing this module.

The --check mode verifies the current DB schema and the live signed-CSRF
middleware. It does not submit passwords, answers, OTPs, CAPTCHA, or emails.
The --enable-local-recovery mode starts actual localhost-only login and
recovery endpoints; those requests can write audit/recovery rows and send email.

STOP the old File 86 server before starting this one (both use port 8000).
NEVER expose this runner via a tunnel, reverse proxy or 0.0.0.0.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
from collections import Counter
from typing import Any

from fastapi import APIRouter

_RECOVERY_ROUTES = frozenset({
    ("/api/auth/password-recovery/identify", "POST"),
    ("/api/auth/password-recovery/answer", "POST"),
    ("/api/auth/password-recovery/resend-otp", "POST"),
    ("/api/auth/password-recovery/verify-otp", "POST"),
    ("/api/auth/password-recovery/reset", "POST"),
})
_FRONTEND_ORIGIN = "http://localhost:5173"
_BIND_HOST = "127.0.0.1"
_PORT = 8000


class LocalRecoverySafetyError(RuntimeError):
    """Local safety prerequisites failed; do not run recovery."""


def _route_counts(app: Any) -> Counter[tuple[str, str]]:
    # Reuse File 86's FastAPI version-compatible route-context enumeration.
    from app.local_login_runner import _route_counts as original_route_counts

    return original_route_counts(app)


def _require_recovery_prerequisites() -> None:
    """Read-only schema and settings checks; no account or OTP modifications."""
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.database import SessionLocal, engine
    from app.services.password_recovery_challenge_store import _existing_table
    from app.services.recovery_account_gate import recovery_question_choices

    if settings.environment != "development":
        raise LocalRecoverySafetyError("Development environment is required.")
    if settings.frontend_origin.rstrip("/") != _FRONTEND_ORIGIN:
        raise LocalRecoverySafetyError("Expected React Origin http://localhost:5173.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise LocalRecoverySafetyError("Expected the local dormora_db PostgreSQL database.")
    host = engine.url.host or ""
    try:
        is_local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_local = host.casefold() == "localhost"
    if not is_local:
        raise LocalRecoverySafetyError("PostgreSQL must be on loopback.")

    with SessionLocal.begin() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        table = _existing_table(db.connection())
        if table is None:
            raise LocalRecoverySafetyError("Recovery table missing: run File 120 --setup.")
        questions = recovery_question_choices(db)
        if len(questions) != 3 or len({qid for qid, _ in questions}) != 3:
            raise LocalRecoverySafetyError("Assigned recovery question bank is incompatible.")


def _mount_staged_routes(app: Any) -> Any:
    from app.api.routes import secure_password_recovery

    if secure_password_recovery.RECOVERY_ROUTES_ENABLED is not False:
        raise LocalRecoverySafetyError("Recovery flag must start disabled.")
    if not isinstance(secure_password_recovery.router, APIRouter):
        raise LocalRecoverySafetyError("File 123 recovery router is missing.")

    before = _route_counts(app)
    if any(before[route] != 0 for route in _RECOVERY_ROUTES):
        raise LocalRecoverySafetyError("Recovery routes were already mounted; refusing duplicates.")

    # Mount only in this process, not app.main's normal startup.
    app.include_router(secure_password_recovery.router, include_in_schema=False)
    after = _route_counts(app)
    errors = [
        f"{method} {path} (found={after[(path, method)]})"
        for path, method in sorted(_RECOVERY_ROUTES)
        if after[(path, method)] != 1
    ]
    if errors:
        raise LocalRecoverySafetyError("Recovery route mount mismatch: " + "; ".join(errors))
    if any(after[item] != before[item] for item in before):
        raise LocalRecoverySafetyError("Mounting recovery changed an existing route count.")
    if secure_password_recovery.RECOVERY_ROUTES_ENABLED is not False:
        raise LocalRecoverySafetyError("Mounting unexpectedly enabled recovery.")
    return secure_password_recovery


async def _check_recovery_csrf(app: Any) -> None:
    """Verify forged CSRF is rejected; valid CSRF reaches the disabled route.

    Both requests run with File 123's flag OFF: they cannot reach recovery
    database operations, issue an OTP, or send an email.
    """
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost:8000",
        follow_redirects=False,
        timeout=8.0,
    ) as client:
        csrf = await client.get("/api/csrf", headers={"Origin": _FRONTEND_ORIGIN})
        if csrf.status_code != 200:
            raise LocalRecoverySafetyError("CSRF handshake did not return HTTP 200.")
        token = csrf.json().get("csrf_token")
        if not isinstance(token, str) or not token or not client.cookies:
            raise LocalRecoverySafetyError("Signed CSRF token/cookie was missing.")

        url = "/api/auth/password-recovery/resend-otp"
        forged = await client.post(url, headers={
            "Origin": _FRONTEND_ORIGIN, "X-CSRF-Token": "forged",
        })
        if forged.status_code != 403:
            raise LocalRecoverySafetyError("Forged CSRF was not rejected by middleware.")

        valid_but_disabled = await client.post(url, headers={
            "Origin": _FRONTEND_ORIGIN, "X-CSRF-Token": token,
        })
        if valid_but_disabled.status_code != 404:
            raise LocalRecoverySafetyError(
                "Signed CSRF did not reach the safely disabled recovery route."
            )


def _preflight() -> tuple[Any, tuple[Any, ...], Any]:
    from app.local_login_runner import (
        _all_login_flags_false,
        _preflight as login_preflight,
    )

    # File 86 already verifies development-only origin, PostgreSQL, SMTP,
    # reCAPTCHA, session policy, signed CSRF and six active login route mounts.
    app, login_modules = login_preflight()
    if not _all_login_flags_false(login_modules):
        raise LocalRecoverySafetyError("Login flags must be disabled after preflight.")

    _require_recovery_prerequisites()
    recovery = _mount_staged_routes(app)
    try:
        asyncio.run(_check_recovery_csrf(app))
    except LocalRecoverySafetyError:
        raise
    except Exception:
        raise LocalRecoverySafetyError("Recovery CSRF preflight failed.") from None

    if recovery.RECOVERY_ROUTES_ENABLED or not _all_login_flags_false(login_modules):
        raise LocalRecoverySafetyError("A route became enabled during read-only preflight.")

    print("DORMORA FILE 124 -- LOCAL PASSWORD RECOVERY PREFLIGHT")
    print("File 86 login/session routes: 6/6 mounted once")
    print("File 123 recovery routes: 5/5 mounted once (disabled)")
    print("File 120 recovery table and File 121 question bank: VERIFIED")
    print("Signed CSRF: forged=403 | valid+disabled=404")
    print("No recovery route was activated; no email or reset was sent.")
    print("File 124 check OK")
    return app, login_modules, recovery


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora loopback-only recovery testing")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only local preflight")
    mode.add_argument(
        "--enable-local-recovery", action="store_true",
        help="Start login plus recovery routes ONLY on 127.0.0.1",
    )
    args = parser.parse_args()

    try:
        app, login_modules, recovery = _preflight()
    except LocalRecoverySafetyError as exc:
        print("FILE 124 PREFLIGHT FAILED:", str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        # Never print exception values that may contain credentials/DB URLs.
        print("FILE 124 PREFLIGHT FAILED:", type(exc).__name__)
        print("Inspect local File 86/123 configuration and recovery schema.")
        raise SystemExit(1) from None

    if args.check:
        print("Read-only integration check passed. Recovery remains disabled.")
        return

    # Flags change only inside this explicit local test process. They are not
    # configuration changes, DB writes, or changes to the normal FastAPI app.
    from app.local_login_runner import _set_login_flags

    _set_login_flags(login_modules, True)
    recovery.RECOVERY_ROUTES_ENABLED = True

    print("\nLOCAL PASSWORD RECOVERY TEST MODE ACTIVE (NOT FOR PRODUCTION)")
    print("FastAPI: http://localhost:8000 | React: http://localhost:5173")
    print("Login, session and five recovery routes are enabled in THIS process.")
    print("WARNING: real requests may write security logs, change passwords and send email.")
    print("STOP the original File 86 login runner first; port 8000 is shared.")
    print("NEVER expose this app with tunnels, proxies or a non-loopback bind.")

    from app.local_registration_runner import LoopbackGate
    import uvicorn

    uvicorn.run(
        LoopbackGate(app), host=_BIND_HOST, port=_PORT, reload=False,
        workers=1, proxy_headers=False, access_log=True,
    )


if __name__ == "__main__":
    main()
