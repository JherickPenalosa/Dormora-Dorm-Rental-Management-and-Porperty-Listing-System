
"""Dormora System Functionality File 17 -- unified localhost development runner.

REPLACE: backend/app/local_functionality_runner.py

Run from backend/ with the virtual environment active:
    python -m app.local_functionality_runner

Reuses the established login/recovery and registration safety preflights,
then enables all authentication, registration + email OTP, password recovery,
and existing Dormora feature routes in ONE localhost-only process.

This runner is for local development ONLY. It does NOT change app.main,
weaken CSRF/reCAPTCHA/rate limits, or enable public registration merely by
being imported. Real registration requests can write PostgreSQL records and
send Gmail OTP messages. Never use a tunnel, proxy, or non-loopback bind.
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


def _registration_readiness(app):
    """Read-only File 63-equivalent checks using File 86's route counter.

    The older registration runner uses a FastAPI-private route helper that is
    not present in all installed versions. The login preflight already uses
    the compatible route counter, so reuse that here without touching File 63.
    No account write, email send, or public flag change occurs in this check.
    """
    import ipaddress

    from app.core.config import settings
    from app.db.database import engine, check_database_connection
    from app.local_login_runner import _route_counts
    from app.main import app as base_app
    from app.api.routes import secure_registration, registration_otp

    if app is not base_app:
        raise RuntimeError("Registration must use the existing FastAPI application.")
    if settings.environment != "development":
        raise RuntimeError("Unified runner requires development environment.")
    if settings.frontend_origin.rstrip("/") != "http://localhost:5173":
        raise RuntimeError("Unified runner requires localhost React origin.")
    if getattr(settings, "recaptcha_v2_expected_hostname", None) != "localhost":
        raise RuntimeError("Local reCAPTCHA hostname must be localhost.")

    # Require the real production-style security checks; never stub services.
    settings.require_csrf_key()
    settings.require_otp_hmac_key()
    settings.require_smtp_configuration()
    settings.build_recaptcha_v2_verifier(client_ip="127.0.0.1")

    host = engine.url.host or ""
    try:
        local_db = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local_db = host.casefold() == "localhost"
    if (
        engine.dialect.name != "postgresql"
        or not local_db
        or engine.url.database != "dormora_db"
        or check_database_connection() != "dormora_db"
    ):
        raise RuntimeError("Registration requires local PostgreSQL dormora_db.")

    if (
        secure_registration.PUBLIC_REGISTRATION_ENABLED is not False
        or registration_otp.PUBLIC_REGISTRATION_OTP_ENABLED is not False
    ):
        raise RuntimeError("Registration must begin disabled.")

    expected = (
        ("/api/auth/register", "POST"),
        ("/api/auth/registration/verify", "POST"),
        ("/api/auth/registration/resend", "POST"),
    )
    counts = _route_counts(app)
    if any(counts[route] != 1 for route in expected):
        raise RuntimeError("Registration route missing or mounted multiple times.")

    print("DORMORA UNIFIED RUNNER -- REGISTRATION PREFLIGHT")
    print("Environment, localhost origin, database and keys: VERIFIED")
    print("reCAPTCHA, CSRF, SMTP and OTP configuration: VERIFIED")
    print("Existing registration routes: 3/3 mounted once (disabled)")
    return secure_registration, registration_otp


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

    # Reuse the existing localhost login/session/password recovery, signed
    # CSRF middleware, CAPTCHA checks, and admin dashboard preflight.
    # This does not enable any public authentication handler.
    app, login_modules, recovery = _preflight()

    # Validate all three registration endpoints and security settings before
    # changing any flags. Reuse the same app and version-compatible route count.
    registration, registration_otp = _registration_readiness(app)

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

    # FILE 16: Authenticated renter discovery routes.
    from app.api.routes.renter_discovery import (
        build_renter_discovery_router,
    )
    from app.api.routes.secure_session import (
        require_authenticated_account as _require_renter_account,
    )

    def verified_renter_id(request):
        account = _require_renter_account(
            request,
            allowed_roles=frozenset({"renter"}),
        )
        return account.user_id

    app.include_router(
        build_renter_discovery_router(
            verified_session_user_id=verified_renter_id,
        )
    )

    # FILE 22: Rental Inquiry API.
    from app.api.routes.rental_inquiries import (
        build_rental_inquiries_router,
    )
    from app.api.routes.secure_session import (
        require_authenticated_account as _require_inquiry_account,
    )

    def verified_inquiry_user_id(request):
        account = _require_inquiry_account(
            request,
            allowed_roles=frozenset({"renter", "property_owner"}),
        )
        return account.user_id

    app.include_router(
        build_rental_inquiries_router(
            verified_session_user_id=verified_inquiry_user_id,
            verify_signed_csrf=signed_csrf_gate,
        )
    )

    # FILE 31: Private inquiry messaging (same session and CSRF as File 22).
    from app.api.routes.inquiry_messages import build_inquiry_messages_router
    app.include_router(
        build_inquiry_messages_router(
            verified_session_user_id=verified_inquiry_user_id,
            verify_signed_csrf=signed_csrf_gate,
        )
    )

    # FILE 37: Tenant Management routes.
    from app.api.routes.tenancies import build_tenancies_router
    app.include_router(
        build_tenancies_router(
            verified_session_user_id=verified_inquiry_user_id,
            verify_signed_csrf=signed_csrf_gate,
        )
    )

    # FILE 45: Rent Management routes.
    from app.api.routes.rent_management import build_rent_management_router
    app.include_router(
        build_rent_management_router(
            verified_session_user_id=verified_inquiry_user_id,
            verify_signed_csrf=signed_csrf_gate,
        )
    )

    # FILE 53: Read-only dashboard summary API (existing verified session).
    from app.api.routes.dashboard_summary import build_dashboard_summary_router
    app.include_router(
        build_dashboard_summary_router(
            verified_session_user_id=verified_inquiry_user_id,
        )
    )

    # FILE 62: Read-only Admin User Directory (admin-only session resolver).
    def verified_admin_directory_user_id(request):
        account = _require_inquiry_account(
            request, allowed_roles=frozenset({"admin"})
        )
        return account.user_id

    from app.api.routes.admin_user_directory import build_admin_user_directory_router
    app.include_router(
        build_admin_user_directory_router(
            verified_session_user_id=verified_admin_directory_user_id,
        )
    )

    # FILE 66: Read-only Admin Property Directory; same admin session.
    from app.api.routes.admin_property_directory import build_admin_property_directory_router
    app.include_router(
        build_admin_property_directory_router(
            verified_session_user_id=verified_admin_directory_user_id,
        )
    )

    # Activate only AFTER every preflight and route inclusion has succeeded.
    # These flags are scoped to this process. Ordinary app.main remains disabled.
    _set_login_flags(login_modules, True)
    recovery.RECOVERY_ROUTES_ENABLED = True
    registration.PUBLIC_REGISTRATION_ENABLED = True
    registration_otp.PUBLIC_REGISTRATION_OTP_ENABLED = True

    print("DORMORA SYSTEM FUNCTIONALITY FILE 17: UNIFIED LOCAL DEVELOPMENT")
    print("Registration + email OTP: ACTIVE (localhost only)")
    print("Login + email OTP + sessions: ACTIVE")
    print("Password recovery: ACTIVE")
    print("GET  /api/owner/properties")
    print("POST /api/owner/properties")
    print("GET  /api/owner/properties/photos/{storage_key}")
    print("Renter discovery, inquiries, messages, tenancies, rent: PRESERVED")
    print("Admin read-only APIs and signed CSRF: PRESERVED")
    print("CSRF_REJECTED audit observer: ACTIVE")
    print("Local development: http://localhost:8000")
    print("WARNING: Valid registration requests WRITE local DB rows and SEND real email OTPs.")
    print("Use only fictional test data and an inbox you control.")
    print("Never expose this development server through a tunnel or proxy.")

    # Preserve the existing loopback gate; use the already-tested CSRF
    # rejection audit observer from the recovery runner as the outer wrapper.
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
cd