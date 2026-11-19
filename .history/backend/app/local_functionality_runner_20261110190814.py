
"""Dormora — System Functionality File 8.

CREATE: backend/app/local_functionality_runner.py

Starts the established localhost-only Dormora login/recovery application,
then activates the File 7 owner-property routes against the SAME session
and signed-CSRF middleware. Does not change app.main or auth modules.

From backend/:
    python -m app.local_functionality_runner
"""

from __future__ import annotations

from fastapi import HTTPException, Request


def verified_owner_id(request: Request) -> int:
    # File 88 validates the real PostgreSQL-backed session and owner role.
    # Never accept a user ID submitted by the browser.
    from app.api.routes.secure_session import require_authenticated_account

    account = require_authenticated_account(
        request,
        allowed_roles=frozenset({"property_owner"}),
    )

    return account.user_id


def signed_csrf_gate(request: Request) -> None:
    # File 56's existing middleware validates the signed CSRF token
    # and cookie before the request reaches this handler.
    # These additional checks do not replace that middleware.

    from app.core.config import settings

    if (
        request.method != "POST"
        or request.headers.get("origin")
        != settings.frontend_origin.rstrip("/")
        or not request.headers.get("x-csrf-token")
    ):
        raise HTTPException(
            status_code=403,
            detail="Request not permitted.",
        )


def main() -> None:
    from app.api.routes.owner_properties import (
        build_owner_properties_router,
    )
    from app.local_login_runner import _set_login_flags
    from app.local_password_recovery_runner import (
        CSRFAuditGate,
        _preflight,
    )
    from app.local_registration_runner import LoopbackGate

    import uvicorn

    # Reuse existing Dormora login, OTP, sessions,
    # password recovery, CSRF middleware, and admin dashboard.
    app, login_modules, recovery = _preflight()

    # Connect File 7 using the existing authenticated session.
    router = build_owner_properties_router(
        verified_session_user_id=verified_owner_id,
        verify_signed_csrf=signed_csrf_gate,
    )

    existing = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", ())
    }

    requested = {
        (route.path, method)
        for route in router.routes
        for method in getattr(route, "methods", ())
    }

    if existing & requested:
        raise RuntimeError(
            "Owner property API routes are already registered."
        )

    app.include_router(router)

    # Activate existing authentication and recovery routes.
    _set_login_flags(login_modules, True)
    recovery.RECOVERY_ROUTES_ENABLED = True

    print(
        "DORMORA SYSTEM FUNCTIONALITY FILE 8: OWNER ROUTES ACTIVE"
    )
    print("GET  /api/owner/properties")
    print("POST /api/owner/properties")
    print(
        "GET  /api/owner/properties/photos/{storage_key}"
    )
    print(
        "Existing login, recovery, admin and signed CSRF: PRESERVED"
    )
    print("Local development: http://localhost:8000")

    # Use the established localhost-only server protections.
    uvicorn.run(
        CSRFAuditGate(LoopbackGate(app)),
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
        proxy_headers=False,
        access_log=True,
    )


if __name__ == "__main__":
    main()
