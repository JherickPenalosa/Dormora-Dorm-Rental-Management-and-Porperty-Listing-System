
"""Dormora Backend File 129 -- local CSRF rejection audit integration.

REPLACE: backend/app/local_password_recovery_runner.py (formerly File 124)

Run from backend/ with .venv active:
    python -m app.local_password_recovery_runner --check
    python -m app.local_password_recovery_runner --enable-local-recovery

Preserves the File 124 runner: File 86 login preflight, all original endpoints,
File 128 recovery routes, CSRF validation, and local-only startup. It also
records CSRF_REJECTED events when the installed CSRF middleware returns a
403 response whose body identifies CSRF as the failure reason.
Normal ``uvicorn app.main:app`` remains unaffected; neither login nor recovery
is enabled merely by importing this module.

The --check mode verifies existing schema, signed-CSRF response and the
audit-observer logic using in-memory events. It makes NO security log writes.
The --enable-local-recovery mode starts localhost-only login and recovery.
It writes one CSRF_REJECTED row for each qualifying failed unsafe request,
without recording CSRF tokens, cookies, passwords or request bodies.
Other 403 responses are NOT misclassified as CSRF failures.
Normal `uvicorn app.main:app` is unchanged; this audit integration is scoped
to this development runner until the main middleware is explicitly updated.

STOP the old File 86 server before starting this one (both use port 8000).
NEVER expose this runner via a tunnel, reverse proxy or 0.0.0.0.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
from datetime import datetime, timezone
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


# CSRF is validated by File 56's *existing* middleware. This observer only
# recognizes its failure response; it NEVER implements a parallel CSRF check.
_MAX_ERROR_BODY = 8192
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AUDIT_LOG = logging.getLogger("dormora.csrf_audit")


def _is_csrf_rejection(body: bytes) -> bool:
    """Require an explicit CSRF error marker: an unrelated 403 is not CSRF."""
    if not isinstance(body, bytes) or len(body) > _MAX_ERROR_BODY:
        return False
    try:
        parsed = json.loads(body)
    except (UnicodeError, ValueError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    detail = parsed.get("detail", parsed.get("message"))
    return isinstance(detail, str) and "csrf" in detail.casefold()


def _write_csrf_rejected(scope: dict[str, Any]) -> None:
    """Write one audit row. Do not read request bodies or trust proxy headers."""
    from sqlalchemy import insert
    from app.db.database import SessionLocal
    from app.services.login_service import security_logs_table

    peer = scope.get("client")
    address = None
    if isinstance(peer, (list, tuple)) and peer and isinstance(peer[0], str):
        try:
            ip = ipaddress.ip_address(peer[0])
            address = str(getattr(ip, "ipv4_mapped", None) or ip)
        except ValueError:
            pass
    if address is None:
        raise LocalRecoverySafetyError("Trusted request IP is unavailable.")

    agent = None
    for key, value in scope.get("headers", ()):
        if key.lower() == b"user-agent":
            agent = "".join(
                ch for ch in value.decode("latin-1") if ch.isprintable()
            )[:255] or None
            break

    method = scope.get("method")
    path = scope.get("path")
    if method not in _UNSAFE_METHODS or not isinstance(path, str):
        raise LocalRecoverySafetyError("Unexpected CSRF audit target.")
    safe_path = "".join(ch for ch in path if ch.isprintable())[:180]

    with SessionLocal.begin() as session:
        session.execute(insert(security_logs_table).values(
            user_id=None,
            event_type="CSRF_REJECTED",
            outcome="failure",
            ip_address=address,
            user_agent=agent,
            event_details={
                "channel": "csrf_middleware",
                "method": method,
                "path": safe_path,
            },
            created_at=datetime.now(timezone.utc),
        ))


class CSRFAuditGate:
    """Transparent ASGI observer for CSRF-specific HTTP 403 responses.

    Keeps original status, headers, and body identical. It buffers up to 8 KiB
    only for 403 responses on unsafe methods to distinguish CSRF validation
    rejection from authorization failures. It never examines request content.
    """

    def __init__(self, app: Any, *, writer: Any = None):
        self.app = app
        self.writer = writer if writer is not None else _write_csrf_rejected

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        buffered: list[dict[str, Any]] = []
        pending = False
        size = 0

        async def send_checked(message: dict[str, Any]) -> None:
            nonlocal buffered, pending, size
            if message["type"] == "http.response.start":
                if message.get("status") != 403:
                    await send(message)
                    return
                buffered = [message]
                pending = True
                size = 0
                return
            if not pending:
                await send(message)
                return
            buffered.append(message)
            if message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            complete = (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
            )
            if size > _MAX_ERROR_BODY or complete:
                if size <= _MAX_ERROR_BODY:
                    body = b"".join(
                        item.get("body", b"") for item in buffered
                        if item["type"] == "http.response.body"
                    )
                    if _is_csrf_rejection(body):
                        try:
                            await asyncio.to_thread(self.writer, scope)
                        except Exception:
                            _AUDIT_LOG.warning(
                                "CSRF rejection audit insert unavailable"
                            )
                queued, buffered = buffered, []
                pending = False
                for item in queued:
                    await send(item)

        await self.app(scope, receive, send_checked)


async def _test_csrf_audit_observer() -> None:
    """Synthetic in-memory tests: never connect to audit DB or write rows."""
    from httpx import ASGITransport, AsyncClient
    observed: list[str] = []

    def stub_write(scope: dict[str, Any]) -> None:
        observed.append(scope.get("path", ""))

    async def stub_app(scope: Any, receive: Any, send: Any) -> None:
        path = scope.get("path")
        if path == "/forged":
            status, detail = 403, "CSRF validation failed."
        elif path == "/denied":
            status, detail = 403, "Access denied."
        else:
            status, detail = 200, "OK"
        payload = json.dumps({"detail": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": payload,
        })

    async with AsyncClient(
        transport=ASGITransport(
            app=CSRFAuditGate(stub_app, writer=stub_write)
        ),
        base_url="http://localhost:8000",
        timeout=8.0,
    ) as client:
        forged = await client.post("/forged")
        denied = await client.post("/denied")
        allowed = await client.post("/allowed")

    if (
        forged.status_code,
        denied.status_code,
        allowed.status_code,
    ) != (403, 403, 200):
        raise LocalRecoverySafetyError(
            "CSRF observer modified status codes."
        )
    if observed != ["/forged"]:
        raise LocalRecoverySafetyError(
            "CSRF observer wrongly classified a response."
        )


def _route_counts(app: Any) -> Counter[tuple[str, str]]:
    from app.local_login_runner import (
        _route_counts as original_route_counts,
    )
    return original_route_counts(app)


def _require_recovery_prerequisites() -> None:
    """Read-only schema and settings checks; no account or OTP modifications."""
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.database import SessionLocal, engine
    from app.services.password_recovery_challenge_store import _existing_table
    from app.services.recovery_account_gate import recovery_question_choices

    if settings.environment != "development":
        raise LocalRecoverySafetyError(
            "Development environment is required."
        )
    if settings.frontend_origin.rstrip("/") != _FRONTEND_ORIGIN:
        raise LocalRecoverySafetyError(
            "Expected React Origin http://localhost:5173."
        )
    if (
        engine.dialect.name != "postgresql"
        or engine.url.database != "dormora_db"
    ):
        raise LocalRecoverySafetyError(
            "Expected the local dormora_db PostgreSQL database."
        )
    host = engine.url.host or ""
    try:
        is_local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_local = host.casefold() == "localhost"
    if not is_local:
        raise LocalRecoverySafetyError(
            "PostgreSQL must be on loopback."
        )

    with SessionLocal.begin() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        table = _existing_table(db.connection())
        if table is None:
            raise LocalRecoverySafetyError(
                "Recovery table missing: run File 120 --setup."
            )
        questions = recovery_question_choices(db)
        if len(questions) != 3 or len({
            qid for qid, _ in questions
        }) != 3:
            raise LocalRecoverySafetyError(
                "Assigned recovery question bank is incompatible."
            )


def _mount_staged_routes(app: Any) -> Any:
    from app.api.routes import secure_password_recovery

    if secure_password_recovery.RECOVERY_ROUTES_ENABLED is not False:
        raise LocalRecoverySafetyError(
            "Recovery flag must start disabled."
        )
    if not isinstance(secure_password_recovery.router, APIRouter):
        raise LocalRecoverySafetyError(
            "File 123 recovery router is missing."
        )

    before = _route_counts(app)
    if any(before[route] != 0 for route in _RECOVERY_ROUTES):
        raise LocalRecoverySafetyError(
            "Recovery routes were already mounted; refusing duplicates."
        )

    app.include_router(
        secure_password_recovery.router,
        include_in_schema=False,
    )
    after = _route_counts(app)
    errors = [
        f"{method} {path} (found={after[(path, method)]})"
        for path, method in sorted(_RECOVERY_ROUTES)
        if after[(path, method)] != 1
    ]
    if errors:
        raise LocalRecoverySafetyError(
            "Recovery route mount mismatch: " + "; ".join(errors)
        )
    if any(after[item] != before[item] for item in before):
        raise LocalRecoverySafetyError(
            "Mounting recovery changed an existing route count."
        )
    if secure_password_recovery.RECOVERY_ROUTES_ENABLED is not False:
        raise LocalRecoverySafetyError(
            "Mounting unexpectedly enabled recovery."
        )
    return secure_password_recovery


async def _check_recovery_csrf(app: Any) -> None:
    """Confirm forged/missing CSRF denial; valid token reaches disabled route."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost:8000",
        follow_redirects=False,
        timeout=8.0,
    ) as client:
        csrf = await client.get(
            "/api/csrf",
            headers={"Origin": _FRONTEND_ORIGIN},
        )
        if csrf.status_code != 200:
            raise LocalRecoverySafetyError(
                "CSRF handshake did not return HTTP 200."
            )
        token = csrf.json().get("csrf_token")
        if (
            not isinstance(token, str)
            or not token
            or not client.cookies
        ):
            raise LocalRecoverySafetyError(
                "Signed CSRF token/cookie was missing."
            )

        url = "/api/auth/password-recovery/resend-otp"

        forged = await client.post(url, headers={
            "Origin": _FRONTEND_ORIGIN,
            "X-CSRF-Token": "forged",
        })
        if forged.status_code != 403:
            raise LocalRecoverySafetyError(
                "Forged CSRF was not rejected by middleware."
            )
        if not _is_csrf_rejection(forged.content):
            raise LocalRecoverySafetyError(
                "Installed CSRF middleware 403 response is not identifiable; "
                "audit would miss it."
            )

        missing = await client.post(url, headers={
            "Origin": _FRONTEND_ORIGIN,
        })
        if (
            missing.status_code != 403
            or not _is_csrf_rejection(missing.content)
        ):
            raise LocalRecoverySafetyError(
                "Missing CSRF token was not rejected with identifiable "
                "CSRF response."
            )

        valid_but_disabled = await client.post(url, headers={
            "Origin": _FRONTEND_ORIGIN,
            "X-CSRF-Token": token,
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

    app, login_modules = login_preflight()
    if not _all_login_flags_false(login_modules):
        raise LocalRecoverySafetyError(
            "Login flags must be disabled after preflight."
        )

    _require_recovery_prerequisites()
    recovery = _mount_staged_routes(app)

    try:
        asyncio.run(_check_recovery_csrf(app))
    except LocalRecoverySafetyError:
        raise
    except Exception:
        raise LocalRecoverySafetyError(
            "Recovery CSRF preflight failed."
        ) from None

    try:
        asyncio.run(_test_csrf_audit_observer())
    except LocalRecoverySafetyError:
        raise
    except Exception:
        raise LocalRecoverySafetyError(
            "CSRF audit observer self-test failed."
        ) from None

    if (
        recovery.RECOVERY_ROUTES_ENABLED
        or not _all_login_flags_false(login_modules)
    ):
        raise LocalRecoverySafetyError(
            "A route became enabled during read-only preflight."
        )

    print("DORMORA FILE 124 -- LOCAL PASSWORD RECOVERY PREFLIGHT")
    print("File 86 login/session routes: 6/6 mounted once")
    print("File 123 recovery routes: 5/5 mounted once (disabled)")
    print("File 120 recovery table and File 121 question bank: VERIFIED")
    print("Signed CSRF: forged=403 | missing=403 | valid+disabled=404")
    print("No recovery route was activated; no email or reset was sent.")
    print("File 124 check OK")

    print("DORMORA FILE 129 -- CSRF REJECTION AUDIT PREFLIGHT")
    print("Installed CSRF failure response: IDENTIFIABLE")
    print("Observer: CSRF=403 logged | unrelated 403 not logged")
    print("Audit destination: public.security_logs / CSRF_REJECTED")
    print("No audit row was written during --check.")
    print("File 129 check OK")

    return app, login_modules, recovery


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dormora loopback-only recovery testing"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Read-only local preflight",
    )
    mode.add_argument(
        "--enable-local-recovery",
        action="store_true",
        help="Start login plus recovery routes ONLY on 127.0.0.1",
    )
    args = parser.parse_args()

    try:
        app, login_modules, recovery = _preflight()
    except LocalRecoverySafetyError as exc:
        print("FILE 129 PREFLIGHT FAILED:", str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("FILE 129 PREFLIGHT FAILED:", type(exc).__name__)
        print(
            "Inspect local File 86/128 configuration "
            "and CSRF audit prerequisites."
        )
        raise SystemExit(1) from None

    if args.check:
        print(
            "Read-only integration check passed. Recovery remains disabled."
        )
        return

    from app.local_login_runner import _set_login_flags

    _set_login_flags(login_modules, True)
    recovery.RECOVERY_ROUTES_ENABLED = True

    print("\nLOCAL PASSWORD RECOVERY TEST MODE ACTIVE (NOT FOR PRODUCTION)")
    print("FastAPI: http://localhost:8000 | React: http://localhost:5173")
    print(
        "Login, session and five recovery routes are enabled in THIS process."
    )
    print("CSRF_REJECTED audit is active for this localhost runner.")
    print(
        "WARNING: real requests may write security logs, "
        "change passwords and send email."
    )
    print(
        "STOP the original File 86 login runner first; port 8000 is shared."
    )
    print(
        "NEVER expose this app with tunnels, proxies or a non-loopback bind."
    )

    from app.local_registration_runner import LoopbackGate
    import uvicorn

    uvicorn.run(
        CSRFAuditGate(LoopbackGate(app)),
        host=_BIND_HOST,
        port=_PORT,
        reload=False,
        workers=1,
        proxy_headers=False,
        access_log=True,
    )


if __name__ == "__main__":
    main()
