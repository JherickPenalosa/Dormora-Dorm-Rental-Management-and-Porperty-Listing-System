
"""Dormora Backend File 63: opt-in, loopback-only real registration test server.

DESTINATION: backend/app/local_registration_runner.py (NEW FILE).

This module NEVER enables public registration merely by being imported.
Only the explicit command below can enable the existing File 55/54 handlers
in this ONE Python process, bound to 127.0.0.1 (no reload or workers):

    python -m app.local_registration_runner --check
    python -m app.local_registration_runner --enable-local-registration

Run File 56 normally with `uvicorn app.main:app` to keep registration disabled.
The development runner uses the EXISTING File 56 middleware, so CSRF, CORS,
origin checks, Google reCAPTCHA, database rate limits, and Gmail delivery are
still mandatory. It never bypasses these protections and never stubs OTPs.

WARNING: A successful test registration changes local PostgreSQL and sends a
real email. Use fictional profile/ID/security-answer data and an email inbox
you control. Not for production, tunneling, remote access, or deployment.
"""

from __future__ import annotations

import argparse
import ipaddress
from collections import Counter
from typing import Any

_LOOPBACK_BIND = "127.0.0.1"
_PORT = 8000
_FRONTEND_ORIGIN = "http://localhost:5173"
_EXPECTED_DB_NAME = "dormora_db"
_ALLOWED_HTTP_HOSTS = frozenset({"127.0.0.1:8000", "localhost:8000"})


class LocalRunnerSafetyError(Exception):
    """Only static, non-sensitive local setup errors use this exception."""


_REQUIRED_ROUTES = frozenset({
    ("/api/auth/register", "POST"),
    ("/api/auth/registration/verify", "POST"),
    ("/api/auth/registration/resend", "POST"),
})


def _loopback_address(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LoopbackGate:
    """ASGI outer guard: block non-local peers and unapproved Host/Origin.

    This is defense-in-depth; Uvicorn ALSO binds exclusively to 127.0.0.1,
    disables proxy-header address substitution, and uses one worker.
    """

    def __init__(self, inner_app: Any) -> None:
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.inner_app(scope, receive, send)
            return

        from starlette.responses import JSONResponse

        client = scope.get("client")
        client_address = client[0] if client else None
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        supplied_host = headers.get(b"host", b"").decode("ascii", "ignore").lower()

        if (not _loopback_address(client_address)
                or supplied_host not in _ALLOWED_HTTP_HOSTS):
            response = JSONResponse(
                {"detail": "Local development access only."}, status_code=403
            )
            await response(scope, receive, send)
            return

        # Every unsafe registration HTTP request must come from our local
        # React development server. This is NOT a replacement for File 56's
        # signed CSRF token and cookie validation.
        if (scope.get("path", "").startswith("/api/auth/")
                and scope.get("method") not in {"GET", "HEAD", "OPTIONS"}):
            origin = headers.get(b"origin", b"").decode("ascii", "ignore")
            if origin != _FRONTEND_ORIGIN:
                response = JSONResponse(
                    {"detail": "Local registration origin is required."},
                    status_code=403,
                )
                await response(scope, receive, send)
                return

        await self.inner_app(scope, receive, send)


def _preflight() -> tuple[Any, Any, Any]:
    """Fail closed BEFORE allowing one live signup; no DB mutations here."""
    from fastapi.routing import iter_route_contexts
    from app.core.config import settings

    if settings.environment != "development":
        raise LocalRunnerSafetyError(
            "File 63 runs only with DORMORA_ENVIRONMENT=development."
        )
    if settings.frontend_origin.rstrip("/") != _FRONTEND_ORIGIN:
        raise LocalRunnerSafetyError(
            "File 63 requires DORMORA_FRONTEND_ORIGIN=http://localhost:5173."
        )
    if getattr(settings, "recaptcha_v2_expected_hostname", None) != "localhost":
        raise LocalRunnerSafetyError(
            "File 63 requires reCAPTCHA expected hostname 'localhost'."
        )

    # Check secret presence without revealing them. These functions do not
    # connect to Google/Gmail or generate a real OTP.
    settings.require_csrf_key()
    settings.require_otp_hmac_key()
    settings.require_smtp_configuration()
    settings.build_recaptcha_v2_verifier(client_ip=_LOOPBACK_BIND)

    from app.db.database import engine, check_database_connection

    if not _loopback_address(engine.url.host) and engine.url.host != "localhost":
        raise LocalRunnerSafetyError("File 63 requires a LOCAL PostgreSQL host.")
    if engine.url.database != _EXPECTED_DB_NAME:
        raise LocalRunnerSafetyError(
            "File 63 refuses to write to a database other than dormora_db."
        )
    database_name = check_database_connection()
    if database_name != _EXPECTED_DB_NAME:
        raise LocalRunnerSafetyError("PostgreSQL connected to an unexpected database.")

    # Import app.main first. File 56 has a startup safety lock and mounts the
    # original route objects only while their public switches are False.
    from app.main import app
    from app.api.routes import secure_registration as registration
    from app.api.routes import registration_otp as otp

    if (registration.PUBLIC_REGISTRATION_ENABLED is not False
            or otp.PUBLIC_REGISTRATION_OTP_ENABLED is not False):
        raise LocalRunnerSafetyError("Registration switches must initially be False.")

    observed = Counter(
        (context.path, method)
        for context in iter_route_contexts(app.routes)
        for method in (context.methods or ())
    )
    incorrect = [key for key in sorted(_REQUIRED_ROUTES) if observed[key] != 1]
    if incorrect:
        raise LocalRunnerSafetyError("Missing or duplicated secure registration routes.")

    print("DORMORA FILE 63 - LOCAL REGISTRATION PREFLIGHT")
    print("Development-only environment: True")
    print("React origin is localhost:5173: True")
    print("PostgreSQL target is local dormora_db: True")
    print("CSRF/OTP/SMTP/reCAPTCHA configuration ready: True")
    print("Three secure registration routes mounted once: True")
    print("Normal FastAPI public-registration switches still disabled: True")
    return app, registration, otp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Dormora's real registration endpoints for localhost tests ONLY."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only preflight")
    mode.add_argument(
        "--enable-local-registration", action="store_true",
        help="explicitly allow real signup/SMTP in this localhost-only process",
    )
    args = parser.parse_args()

    try:
        app, registration, otp = _preflight()
    except LocalRunnerSafetyError as error:
        print(f"PREFLIGHT FAILED: {error}")
        raise SystemExit(1) from None
    except Exception as error:
        # Never print exception values that could contain SMTP/database secrets.
        print(f"PREFLIGHT FAILED: {type(error).__name__}")
        print("Check local .env, database, File 56 routers and server settings.")
        raise SystemExit(1) from None

    if args.check:
        print("Preflight passed. No user created, email sent, or flag changed.")
        return

    # Enable ONLY these two module variables in this Python process. Neither
    # file is edited and File 56's ordinary startup mode stays disabled.
    registration.PUBLIC_REGISTRATION_ENABLED = True
    otp.PUBLIC_REGISTRATION_OTP_ENABLED = True

    print("\nLOCAL-ONLY TEST MODE ACTIVE")
    print("Browser API URL: http://localhost:8000 (bound to 127.0.0.1)")
    print("Use localhost on BOTH frontend and API: SameSite=Lax cookies need matching sites.")
    print("Allowed frontend: http://localhost:5173")
    print("WARNING: valid signup requests will WRITE local DB rows and SEND Gmail OTPs.")
    print("Use fictional profile information and your own test email inbox.")
    print("Press Ctrl+C to stop and restore the ordinary disabled-server mode.")

    import uvicorn

    # One process, no reload, no proxy-header trust, and loopback-only bind.
    # Never change host to 0.0.0.0 or deploy this runner behind a tunnel.
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
