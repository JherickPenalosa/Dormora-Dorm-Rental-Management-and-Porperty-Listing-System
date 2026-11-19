
"""Dormora Backend File 86 -- localhost login runner (ROUTE-CONTEXT FIX).

REPLACE: backend/app/local_login_runner.py

Run from backend/ with .venv active:
    python -m app.local_login_runner --check
    python -m app.local_login_runner --enable-local-login

Importing this file DOES NOT mount routes, set login flags, modify database
records, send email, or start a server. The --check mode performs configuration
checks and a simulated in-process signed-CSRF handshake.

FastAPI versions with wrapped routes need iter_route_contexts() to enumerate
mounted endpoints. A direct isinstance(route, APIRoute) check misses them.
File 63 already uses iter_route_contexts for the same reason. Fallback code
supports older FastAPI versions with direct APIRoute entries.

--enable-local-login is for manual localhost testing only. Normal
`uvicorn app.main:app` login flags remain disabled. Existing registration
switches remain disabled. Never expose this runner behind a public tunnel,
proxy, or on 0.0.0.0.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
from collections import Counter
from typing import Any

from fastapi.routing import APIRoute

_LOOPBACK_BIND = "127.0.0.1"
_PORT = 8000
_FRONTEND_ORIGIN = "http://localhost:5173"
_DATABASE_NAME = "dormora_db"

_LOGIN_ROUTES = frozenset({
    ("/api/auth/login", "POST"),
    ("/api/auth/login/verify-otp", "POST"),
    ("/api/auth/login/resend-otp", "POST"),
    ("/api/auth/session", "GET"),
    ("/api/auth/session/refresh", "POST"),
    ("/api/auth/logout", "POST"),
})

_REGISTRATION_ROUTES = frozenset({
    ("/api/auth/register", "POST"),
    ("/api/auth/registration/verify", "POST"),
    ("/api/auth/registration/resend", "POST"),
})


class LocalLoginSafetyError(RuntimeError):
    """A prerequisite for real local login testing was not met."""


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _route_counts(app: Any) -> Counter[tuple[str, str]]:
    """Count effective endpoint paths, including FastAPI's wrapped routes.

    FastAPI 0.137+ can place routes in wrappers; app.routes may then contain
    no direct APIRoute items even after include_router(). Earlier File 86's
    isinstance(APIRoute) filter incorrectly counted every route as missing.
    """
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        # Compatibility for earlier FastAPI versions with direct APIRoute.
        return Counter(
            (route.path, method)
            for route in app.routes
            if isinstance(route, APIRoute)
            for method in (route.methods or ())
        )

    return Counter(
        (context.path, method)
        for context in iter_route_contexts(app.routes)
        for method in (context.methods or ())
    )


def _all_login_flags_false(modules: tuple[Any, ...]) -> bool:
    password, verify, resend, session = modules
    return (
        password.PUBLIC_LOGIN_ENABLED is False
        and password.LOGIN_SECURITY_COMPLETE is False
        and verify.LOGIN_OTP_VERIFY_ENABLED is False
        and resend.LOGIN_OTP_RESEND_ENABLED is False
        and session.SESSION_ROUTES_ENABLED is False
    )


def _set_login_flags(modules: tuple[Any, ...], enabled: bool) -> None:
    password, verify, resend, session = modules
    password.PUBLIC_LOGIN_ENABLED = enabled
    password.LOGIN_SECURITY_COMPLETE = enabled
    verify.LOGIN_OTP_VERIFY_ENABLED = enabled
    resend.LOGIN_OTP_RESEND_ENABLED = enabled
    session.SESSION_ROUTES_ENABLED = enabled


def _check_environment_and_database() -> None:
    from sqlalchemy import inspect

    from app.core.config import settings
    from app.core.login_challenge import CHALLENGE_TTL_SECONDS
    from app.core.session_security import SESSION_IDLE_TIMEOUT_MINUTES
    from app.db.database import check_database_connection, engine
    from app.services.auth_session_store import auth_sessions_table
    from app.services.login_ip_service import IP_FAILURE_THRESHOLD
    from app.services.login_otp_service import (
        COOLDOWN,
        EXPIRY,
        MAX_ATTEMPTS,
        MAX_ISSUES_PER_WINDOW,
    )
    from app.services.login_request_limit_service import LOGIN_REQUEST_LIMITS

    if settings.environment != "development":
        raise LocalLoginSafetyError(
            "Only DORMORA_ENVIRONMENT=development is allowed."
        )

    if settings.frontend_origin.rstrip("/") != _FRONTEND_ORIGIN:
        raise LocalLoginSafetyError(
            "Expected frontend Origin http://localhost:5173."
        )

    if getattr(settings, "recaptcha_v2_expected_hostname", None) != "localhost":
        raise LocalLoginSafetyError(
            "reCAPTCHA expected hostname must be localhost."
        )

    if not _is_loopback(engine.url.host) or engine.url.database != _DATABASE_NAME:
        raise LocalLoginSafetyError(
            "A local dormora_db PostgreSQL target is required."
        )

    if check_database_connection() != _DATABASE_NAME:
        raise LocalLoginSafetyError(
            "Connected PostgreSQL database name is unexpected."
        )

    settings.require_csrf_key()
    settings.require_otp_hmac_key()
    settings.require_smtp_configuration()

    if settings.smtp_security not in {"ssl", "starttls"}:
        raise LocalLoginSafetyError("Encrypted SMTP is required.")

    settings.build_recaptcha_v2_verifier(client_ip=_LOOPBACK_BIND)

    if not (
        IP_FAILURE_THRESHOLD == 10
        and SESSION_IDLE_TIMEOUT_MINUTES == 15
        and CHALLENGE_TTL_SECONDS == 900
        and EXPIRY.total_seconds() == 300
        and COOLDOWN.total_seconds() == 60
        and MAX_ATTEMPTS == 3
        and MAX_ISSUES_PER_WINDOW == 4
        and LOGIN_REQUEST_LIMITS["password"].max_requests == 10
        and LOGIN_REQUEST_LIMITS["otp_verify"].max_requests == 8
        and LOGIN_REQUEST_LIMITS["otp_resend"].max_requests == 12
    ):
        raise LocalLoginSafetyError("Login security seed/policy mismatch.")

    expected_columns = set(auth_sessions_table.c.keys())
    actual_columns = {
        column["name"]
        for column in inspect(engine).get_columns("auth_sessions", schema="public")
    }
    if actual_columns != expected_columns:
        raise LocalLoginSafetyError(
            "File 78 auth_sessions schema is missing or changed."
        )


def _mount_routes_for_local_process() -> tuple[Any, tuple[Any, ...]]:
    from app.main import app
    from app.api.routes import registration_otp, secure_registration
    from app.api.routes import (
        secure_login,
        secure_login_otp,
        secure_login_resend,
        secure_session,
    )

    modules = (secure_login, secure_login_otp, secure_login_resend, secure_session)

    if not _all_login_flags_false(modules):
        raise LocalLoginSafetyError("All login switches must initially be False.")

    if (
        secure_registration.PUBLIC_REGISTRATION_ENABLED is not False
        or registration_otp.PUBLIC_REGISTRATION_OTP_ENABLED is not False
    ):
        raise LocalLoginSafetyError("Registration must remain disabled in this runner.")

    before = _route_counts(app)

    # Registration routes are optional in this LOGIN-ONLY runner, but duplicates
    # are not allowed. Never mount, unmount, or enable registration here.
    if any(before[route] > 1 for route in _REGISTRATION_ROUTES):
        raise LocalLoginSafetyError("Existing registration routes are duplicated.")

    if any(before[route] != 0 for route in _LOGIN_ROUTES):
        raise LocalLoginSafetyError("Existing login route would be duplicated.")

    for module in modules:
        app.include_router(module.router, include_in_schema=False)

    after = _route_counts(app)
    errors = [
        f"{method} {path} (found={after[(path, method)]})"
        for path, method in sorted(_LOGIN_ROUTES)
        if after[(path, method)] != 1
    ]
    if errors:
        raise LocalLoginSafetyError(
            "Login route count mismatch: " + "; ".join(errors)
        )

    if any(after[route] != before[route] for route in _REGISTRATION_ROUTES):
        raise LocalLoginSafetyError("Registration route mounts unexpectedly changed.")

    if not _all_login_flags_false(modules):
        raise LocalLoginSafetyError("Route mounting unexpectedly changed login flags.")

    return app, modules


async def _test_signed_csrf(app: Any, modules: tuple[Any, ...]) -> None:
    """Exercise File 56's signed CSRF middleware without real authentication."""
    try:
        from httpx import ASGITransport, AsyncClient
    except ImportError:
        raise LocalLoginSafetyError("Install httpx to run the CSRF preflight.") from None

    _set_login_flags(modules, True)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost:8000",
            follow_redirects=False,
            timeout=8.0,
        ) as client:
            csrf = await client.get(
                "/api/csrf", headers={"Origin": _FRONTEND_ORIGIN}
            )
            if csrf.status_code != 200:
                raise LocalLoginSafetyError(
                    "File 56 /api/csrf endpoint did not succeed."
                )

            token = csrf.json().get("csrf_token")
            if not isinstance(token, str) or not token:
                raise LocalLoginSafetyError("Signed CSRF token is missing.")
            if not client.cookies:
                raise LocalLoginSafetyError("Signed CSRF cookie is missing.")

            forged = await client.post(
                "/api/auth/logout",
                headers={"Origin": _FRONTEND_ORIGIN, "X-CSRF-Token": "forged"},
            )
            if forged.status_code != 403:
                raise LocalLoginSafetyError("Forged CSRF token was not rejected.")

            valid = await client.post(
                "/api/auth/logout",
                headers={"Origin": _FRONTEND_ORIGIN, "X-CSRF-Token": token},
            )
            if (
                valid.status_code != 200
                or valid.json().get("authenticated") is not False
            ):
                raise LocalLoginSafetyError(
                    "Valid CSRF token did not reach logout handler."
                )
    finally:
        _set_login_flags(modules, False)


def _preflight() -> tuple[Any, tuple[Any, ...]]:
    _check_environment_and_database()
    app, modules = _mount_routes_for_local_process()
    try:
        asyncio.run(_test_signed_csrf(app, modules))
    except LocalLoginSafetyError:
        raise
    except Exception:
        raise LocalLoginSafetyError("Signed CSRF middleware preflight failed.") from None

    if not _all_login_flags_false(modules):
        raise LocalLoginSafetyError("Login flags were not restored after CSRF check.")

    print("DORMORA FILE 86 - LOCAL LOGIN PREFLIGHT")
    print("Local development and database verified: True")
    print("Security seed, email, CAPTCHA and session schema ready: True")
    print("Six secure login/session routes mounted once: True")

    observed = _route_counts(app)
    registration_mounted = sum(observed[route] == 1 for route in _REGISTRATION_ROUTES)
    print(f"Existing registration routes unchanged: {registration_mounted}/3 mounted")
    print("Real signed CSRF rejection and acceptance verified: True")
    print("Registration and normal public-login switches still disabled: True")
    return app, modules


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dormora localhost-only login tests"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only preflight")
    mode.add_argument(
        "--enable-local-login",
        action="store_true",
        help="Start explicit localhost-only real login test server",
    )
    args = parser.parse_args()

    try:
        app, modules = _preflight()
    except LocalLoginSafetyError as exc:
        print(f"PREFLIGHT FAILED: {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        # Don't print underlying database/SMTP exceptions (might include secrets).
        print(f"PREFLIGHT FAILED: {type(exc).__name__}")
        raise SystemExit(1) from None

    if args.check:
        print("Preflight passed. No login enabled, database written, or email sent.")
        return

    _set_login_flags(modules, True)
    print("\nLOCAL LOGIN TEST MODE ACTIVE (NOT FOR PRODUCTION)")
    print("API: http://localhost:8000 | React: http://localhost:5173")
    print("Use localhost for BOTH URLs to preserve SameSite=Strict cookies.")
    print("WARNING: real logins write PostgreSQL data and send Gmail OTPs.")
    print("Registration remains disabled in this runner.")
    print("Press Ctrl+C to exit local test mode.")

    from app.local_registration_runner import LoopbackGate
    import uvicorn

    uvicorn.run(
        LoopbackGate(app),
        host=_LOOPBACK_BIND,
        port=_PORT,
        reload=False,
        workers=1,
        proxy_headers=False,
        access_log=True,
    )


if __name__ == "__main__":
    main()
