"""Dormora FastAPI entry point — File 17 normal-startup CSRF audit integration.

Destination: backend/app/main.py (complete replacement of File 37).
Preserves File 37 CSRF, CORS, security headers, safe errors, private logging,
CSRF cookie/token issuing, and /api/health + /api/health/db endpoints intact.

Adds the File 55 secure registration router and File 54 registration OTP router
for HTTP-level testing. Both remain disabled via their own False flags; the
startup safety lock rejects accidental activation and duplicate/legacy routes.
The new routes are hidden from public OpenAPI documentation for now.

No registration attempts, account creation, email or DB writes are performed
as a result of mounting; only the existing module imports occur at startup.

File 17 adds CSRF_REJECTED auditing when normal startup rejects an unsafe
request with HTTP 403. It leaves the HTTP result and all safety locks intact.
"""

import asyncio
import hashlib
import ipaddress
import hmac
import logging
import re
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.csrf_security import (
    CSRF_TOKEN_TTL_SECONDS,
    generate_csrf_binding,
    issue_csrf_token,
    verify_csrf_token,
)
from app.db.database import check_database_connection


app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend API for the Dormora rental management and "
        "property listing system."
    ),
    version=settings.app_version,
)

_ALLOWED_ORIGIN = settings.frontend_origin.rstrip("/")
_PRODUCTION = settings.environment == "production"
_CSRF_COOKIE_NAME = (
    "__Host-dormora-csrf" if _PRODUCTION else "dormora-csrf-dev"
)
_BINDING_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_PATTERN = re.compile(r"[1-9][0-9]{0,15}\Z")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# The location is outside the backend/frontend repositories and web roots.
# Do not include raw exception messages, SQL, submitted form values, cookies,
# tokens, query strings, or request bodies in diagnostic log records.
_PRIVATE_LOG_PATH = Path.home() / ".dormora" / "logs" / "api_errors.log"
_PRIVATE_LOG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
_error_logger = logging.getLogger("dormora.private_api_errors")
_error_logger.setLevel(logging.ERROR)
_error_logger.propagate = False
if not _error_logger.handlers:
    _handler = RotatingFileHandler(
        _PRIVATE_LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    _handler.setFormatter(logging.Formatter("%(asctime)sZ %(levelname)s %(message)s"))
    _handler.formatter.converter = time.gmtime
    _error_logger.addHandler(_handler)

# File 17: record genuine CSRF denials in the normal FastAPI application.
# This helper receives trusted ASGI connection metadata, never a request body,
# cookies, authorization headers, CSRF tokens, or query strings.
_csrf_audit_logger = logging.getLogger("dormora.csrf_audit")


def _csrf_audit_managed_by_local_runner() -> bool:
    """Avoid duplicate events and DB writes during File 129 read-only preflight.

    The supported localhost runner is invoked with
    `python -m app.local_password_recovery_runner`; it installs its own
    CSRFAuditGate and owns logging in that process. Normal app.main startup
    always uses this module's logger instead.
    """
    spec = getattr(sys.modules.get("__main__"), "__spec__", None)
    return getattr(spec, "name", None) == "app.local_password_recovery_runner"


def _write_csrf_rejected(scope: dict) -> None:
    """Persist one audit event for a rejected unsafe request.

    Call from a worker thread so synchronous PostgreSQL I/O does not block
    FastAPI's event loop. An audit failure must never permit the request.
    """
    from datetime import datetime, timezone

    from sqlalchemy import insert
    from app.db.database import SessionLocal
    from app.services.login_service import security_logs_table

    peer = scope.get("client")
    if not isinstance(peer, (tuple, list)) or not peer or not isinstance(peer[0], str):
        raise ValueError("Trusted client address is unavailable.")
    ip = ipaddress.ip_address(peer[0])
    client_ip = str(getattr(ip, "ipv4_mapped", None) or ip)

    method = scope.get("method")
    if method in _SAFE_METHODS or not isinstance(method, str):
        raise ValueError("CSRF audit must originate from an unsafe method.")
    path = scope.get("path")
    if not isinstance(path, str):
        raise ValueError("CSRF audit path unavailable.")
    safe_path = "".join(ch for ch in path if ch.isprintable())[:180]

    agent = None
    for key, value in scope.get("headers", ()):
        if key.lower() == b"user-agent":
            agent = "".join(ch for ch in value.decode("latin-1") if ch.isprintable())[:255] or None
            break

    with SessionLocal.begin() as session:
        session.execute(insert(security_logs_table).values(
            user_id=None,
            event_type="CSRF_REJECTED",
            outcome="failure",
            ip_address=client_ip,
            user_agent=agent,
            event_details={
                "channel": "csrf_middleware",
                "method": method,
                "path": safe_path,
            },
            created_at=datetime.now(timezone.utc),
        ))


# Known registration fields receive static, human-readable validation messages.
# Never put Pydantic's error['input'] or arbitrary error['msg'] in a response.
_FIELD_ERRORS = {
    "username": "Please enter a valid username.",
    "email": "Please enter a valid email address.",
    "password": "Password does not meet the required format or length.",
    "role": "Please select a valid account role.",
    "id_number": "ID Number must follow the format xxxx-xxxx.",
    "first_name": "Please enter a valid First Name.",
    "middle_name": "Please enter a valid Middle Name.",
    "family_name": "Please enter a valid Family Name.",
    "birthdate": "Please enter a valid Birthdate.",
    "name_extension": "Please select a valid Name Extension.",
    "other_extension": "Please enter a valid Name Extension value.",
    "street": "Please enter a valid Purok or Street.",
    "barangay": "Please enter a valid Barangay.",
    "city": "Please enter a valid Municipality or City.",
    "province": "Please enter a valid Province.",
    "country": "Please enter a valid Country.",
    "zip_code": "ZIP Code must contain exactly four digits.",
    # Dormora File 65 compatibility: allowlisted labels for *all* registration
    # fields, including aliases received from React. Never return the submitted
    # value or raw Pydantic message in an HTTP validation response.
    "confirm_password": "Password confirmation is invalid or does not match.",
    "privacy_consent": "Please read and accept the Privacy Notice.",
    "security_answer_1": "Security answer 1 must be 2–50 letters with single spaces only.",
    "security_answer_2": "Security answer 2 must be 2–50 letters with single spaces only.",
    "security_answer_3": "Security answer 3 must be 2–50 letters with single spaces only.",
    "captcha_token": "Please complete reCAPTCHA again.",
    "captchaToken": "Please complete reCAPTCHA again.",
    "preferred_rental_type": "Select a valid preferred rental type.",
    "preferredRentalType": "Select a valid preferred rental type.",
    "preferred_rental_area": "Preferred rental area needs 3–100 valid characters.",
    "preferredRentalArea": "Preferred rental area needs 3–100 valid characters.",
    "maximum_monthly_budget": "Monthly budget must be a positive number with up to two decimals.",
    "monthlyBudget": "Monthly budget must be a positive number with up to two decimals.",
    "target_move_in_date": "Move-in date must be a valid date, not in the past.",
    "targetMoveInDate": "Move-in date must be a valid date, not in the past.",
    "primary_property_type": "Select a valid primary property type.",
    "primaryPropertyType": "Select a valid primary property type.",
    "primary_property_area": "Primary property area needs 3–100 valid characters.",
    "primaryPropertyArea": "Primary property area needs 3–100 valid characters.",
    "expected_monthly_rent": "Expected monthly rent must be positive, with up to two decimals.",
    "expectedRent": "Expected monthly rent must be positive, with up to two decimals.",
    "expected_availability_date": "Availability date must be valid and not in the past.",
    "expectedAvailableDate": "Availability date must be valid and not in the past.",
}



def _safe_log_unexpected_error(request: Request, exc: Exception) -> str:
    """Log an incident without exception messages, request data, or secret values.

    Traceback *locations* allow developers to find the failed operation while
    avoiding the potentially sensitive exception string and source-code lines.
    """
    reference = uuid4().hex
    route = request.scope.get("route")
    endpoint = getattr(route, "path", "<unmatched>")
    frames = traceback.extract_tb(exc.__traceback__)[-12:]
    locations = [
        f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in frames
    ]
    try:
        _error_logger.error(
            "reference=%s method=%s route=%s exception=%s locations=%r",
            reference, request.method, endpoint,
            type(exc).__name__, locations,
        )
    except Exception:
        # Failure of the diagnostic logger must not disclose an error to clients.
        pass
    return reference


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    """Report field-level errors without echoing untrusted input or credentials."""
    problems = []
    seen = set()
    for error in exc.errors():
        location = error.get("loc", ())
        if "website" in location:
            # Honeypot submissions must not identify the trap to the caller.
            return JSONResponse(
                status_code=400,
                content={"detail": "Registration could not be completed."},
            )
        # Prefer an allowlisted field; no attacker-supplied key names are echoed.
        field = next((part for part in location if part in _FIELD_ERRORS), None)
        if field and field not in seen:
            problems.append({"field": field, "message": _FIELD_ERRORS[field]})
            seen.add(field)
        elif not field and "__form__" not in seen:
            # Model-level errors (e.g. matching passwords or forbidden role
            # combinations) do not have a named field. Unknown/extra fields
            # also land here. Provide a fixed, non-secret suggestion rather
            # than the unhelpful 'Invalid request data' placeholder.
            problems.append({
                "field": "__form__",
                "message": (
                    "Check password confirmation, name extension, role-specific "
                    "details, and unexpected form fields."
                ),
            })
            seen.add("__form__")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Please correct the highlighted fields.",
            "errors": problems or [{"message": "Invalid request data."}],
        },
    )


@app.exception_handler(Exception)
async def safe_unexpected_error(request: Request, exc: Exception):
    """Hide unexpected Python/SQL exceptions and return a support reference."""
    reference = _safe_log_unexpected_error(request, exc)
    headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    # The exception handler is run outside CORS middleware by Starlette's
    # ServerErrorMiddleware. Preserve allowed-origin CORS on HTTP 500 only.
    if request.headers.get("origin") == _ALLOWED_ORIGIN:
        headers.update({
            "Access-Control-Allow-Origin": _ALLOWED_ORIGIN,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        })
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "error_id": reference,
        },
        headers=headers,
    )


def _cookie_signature(binding: str, issued_at: str, key: bytes) -> str:
    """Sign the binding separately from CSRF tokens (domain separation)."""
    message = f"dormora-csrf-cookie-v1:{issued_at}:{binding}".encode("ascii")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _read_signed_binding(cookie: str | None, key: bytes) -> str | None:
    """Reject altered, malformed, future-dated, and expired cookies."""
    if not cookie or len(cookie) > 170:
        return None
    parts = cookie.split(".")
    if len(parts) != 4:
        return None
    version, issued_at, binding, supplied_signature = parts
    if (
        version != "v1"
        or not _TIMESTAMP_PATTERN.fullmatch(issued_at)
        or not _BINDING_PATTERN.fullmatch(binding)
        or not _SIGNATURE_PATTERN.fullmatch(supplied_signature)
    ):
        return None

    now = int(time.time())
    age = now - int(issued_at)
    if age < -30 or age > CSRF_TOKEN_TTL_SECONDS:
        return None

    expected = _cookie_signature(binding, issued_at, key)
    if not hmac.compare_digest(supplied_signature, expected):
        return None
    return binding


def _make_signed_cookie(binding: str, key: bytes) -> str:
    issued_at = str(int(time.time()))
    signature = _cookie_signature(binding, issued_at, key)
    return f"v1.{issued_at}.{binding}.{signature}"


@app.middleware("http")
async def enforce_csrf(request: Request, call_next):
    """Protect every state-changing HTTP method.

    Requests without a trustworthy CSRF token fail BEFORE route handlers run.
    If the CSRF secret is absent, unsafe methods fail closed with HTTP 503.
    OPTIONS preflights remain available to the CORS middleware.
    """
    response = None
    csrf_rejected = False
    if request.method not in _SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin != _ALLOWED_ORIGIN:
            response = JSONResponse(
                status_code=403, content={"detail": "CSRF validation failed."}
            )
            csrf_rejected = True
        else:
            try:
                csrf_key = settings.require_csrf_key()
            except RuntimeError:
                response = JSONResponse(
                    status_code=503,
                    content={"detail": "Security protection unavailable."},
                )
            else:
                binding = _read_signed_binding(
                    request.cookies.get(_CSRF_COOKIE_NAME), csrf_key
                )
                token = request.headers.get("X-CSRF-Token")
                if binding is None or not verify_csrf_token(
                    binding, token, secret_key=csrf_key
                ):
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF validation failed."},
                    )
                    csrf_rejected = True

    if csrf_rejected and not _csrf_audit_managed_by_local_runner():
        try:
            await asyncio.to_thread(_write_csrf_rejected, request.scope)
        except Exception:
            # Never reveal database exceptions, tokens or other sensitive data.
            # Even when the audit store is unavailable, the CSRF request is denied.
            _csrf_audit_logger.warning("CSRF rejection audit insert unavailable")
    if response is None:
        response = await call_next(request)
    return response


# This must wrap the CSRF middleware so that even rejected requests receive
# the expected CORS response headers for the configured React origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_ALLOWED_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Apply required headers to normal, rejected and CORS preflight responses."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/csrf", tags=["Security"])
def get_csrf_token(request: Request, response: Response) -> dict[str, str]:
    """Give React a CSRF token with a separate HttpOnly binding cookie.

    A valid binding cookie is reused, which avoids invalidating a different
    open tab whenever another tab requests a new CSRF token.
    """
    origin = request.headers.get("origin")
    if origin is not None and origin != _ALLOWED_ORIGIN:
        raise HTTPException(status_code=403, detail="Origin not allowed.")

    try:
        csrf_key = settings.require_csrf_key()
    except RuntimeError:
        raise HTTPException(
            status_code=503, detail="Security protection unavailable."
        ) from None

    binding = _read_signed_binding(
        request.cookies.get(_CSRF_COOKIE_NAME), csrf_key
    )
    if binding is None:
        binding = generate_csrf_binding()

    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=_make_signed_cookie(binding, csrf_key),
        httponly=True,
        secure=_PRODUCTION,
        samesite="lax",
        path="/",
        max_age=CSRF_TOKEN_TTL_SECONDS,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"csrf_token": issue_csrf_token(binding, secret_key=csrf_key)}


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Confirm the FastAPI application is running."""
    return {"status": "healthy", "service": "Dormora API"}


@app.get("/api/health/db", tags=["Health"])
def database_health_check() -> dict[str, str]:
    """Confirm PostgreSQL is reachable without exposing credentials."""
    try:
        database_name = check_database_connection()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503, detail="Database connection unavailable."
        ) from None
    return {"status": "connected", "database": database_name}


# --- DORMORA FILE 56 ROUTER MOUNTS: BEGIN ---
# File 56 mounts registration endpoints for protected HTTP testing only.
# BOTH public feature switches remain False. No account can be registered.
from app.api.routes.secure_registration import (
    PUBLIC_REGISTRATION_ENABLED as _file56_registration_enabled,
    router as _file56_registration_router,
)
from app.api.routes.registration_otp import (
    PUBLIC_REGISTRATION_OTP_ENABLED as _file56_otp_enabled,
    router as _file56_otp_router,
)

if _file56_registration_enabled is not False or _file56_otp_enabled is not False:
    raise RuntimeError(
        "Dormora File 56 safety lock: registration routers must stay disabled."
    )

_file56_restricted_paths = {
    ("/api/auth/register", "POST"),
    ("/api/auth/registration/verify", "POST"),
    ("/api/auth/registration/resend", "POST"),
}
_file56_conflicts = {
    (route.path, method)
    for route in app.routes
    for method in (getattr(route, "methods", None) or set())
    if (route.path, method) in _file56_restricted_paths
}
if _file56_conflicts:
    raise RuntimeError(
        "Dormora File 56 safety lock: an older or duplicate registration "
        "route is already mounted. Remove the legacy registration router "
        "before continuing."
    )

# Do not mount the legacy auth.py router. Route functions stay disabled.
# Existing CSRF, origin checks, and security headers in File 37 remain active.
app.include_router(_file56_registration_router, include_in_schema=False)
app.include_router(_file56_otp_router, include_in_schema=False)
# --- DORMORA FILE 56 ROUTER MOUNTS: END ---
