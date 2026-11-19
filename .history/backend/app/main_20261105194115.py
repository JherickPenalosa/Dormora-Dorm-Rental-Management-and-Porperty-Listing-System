
"""Dormora FastAPI entry point — File 56 secure registration router mounting.

Destination: backend/app/main.py (complete replacement of File 37).
Preserves File 37 CSRF, CORS, security headers, safe errors, private logging,
CSRF cookie/token issuing, and /api/health + /api/health/db endpoints intact.

Adds the File 55 secure registration router and File 54 registration OTP router
for HTTP-level testing. Both remain disabled via their own False flags; the
startup safety lock rejects accidental activation and duplicate/legacy routes.
The new routes are hidden from public OpenAPI documentation for now.

No registration attempts, account creation, email or DB writes are performed
as a result of mounting; only the existing module imports occur at startup.
"""

import hashlib
import hmac
import logging
import re
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

# Keep private diagnostics outside the repository.
_PRIVATE_LOG_PATH = Path.home() / ".dormora" / "logs" / "api_errors.log"
_PRIVATE_LOG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

_error_logger = logging.getLogger("dormora.private_api_errors")
_error_logger.setLevel(logging.ERROR)
_error_logger.propagate = False

if not _error_logger.handlers:
    _handler = RotatingFileHandler(
        _PRIVATE_LOG_PATH,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    _handler.setFormatter(
        logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
    )
    _handler.formatter.converter = time.gmtime
    _error_logger.addHandler(_handler)

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
}


def _safe_log_unexpected_error(
    request: Request,
    exc: Exception,
) -> str:
    """Log incident locations without request data or exception text."""
    reference = uuid4().hex
    route = request.scope.get("route")
    endpoint = getattr(route, "path", "<unmatched>")
    frames = traceback.extract_tb(exc.__traceback__)[-12:]
    locations = [
        f"{frame.filename}:{frame.lineno}:{frame.name}"
        for frame in frames
    ]

    try:
        _error_logger.error(
            "reference=%s method=%s route=%s exception=%s locations=%r",
            reference,
            request.method,
            endpoint,
            type(exc).__name__,
            locations,
        )
    except Exception:
        pass

    return reference


@app.exception_handler(RequestValidationError)
async def safe_validation_error(
    request: Request,
    exc: RequestValidationError,
):
    """Return field-level errors without echoing submitted secrets."""
    problems = []
    seen = set()

    for error in exc.errors():
        location = error.get("loc", ())

        if "website" in location:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "Registration could not be completed."
                },
            )

        field = next(
            (part for part in location if part in _FIELD_ERRORS),
            None,
        )

        if field and field not in seen:
            problems.append({
                "field": field,
                "message": _FIELD_ERRORS[field],
            })
            seen.add(field)

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Please correct the highlighted fields.",
            "errors": problems or [
                {"message": "Invalid request data."}
            ],
        },
    )


@app.exception_handler(Exception)
async def safe_unexpected_error(
    request: Request,
    exc: Exception,
):
    """Hide internal exceptions and return a support reference."""
    reference = _safe_log_unexpected_error(request, exc)

    headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }

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


def _cookie_signature(
    binding: str,
    issued_at: str,
    key: bytes,
) -> str:
    """Sign the binding separately from CSRF tokens."""
    message = (
        f"dormora-csrf-cookie-v1:{issued_at}:{binding}"
    ).encode("ascii")

    return hmac.new(
        key,
        message,
        hashlib.sha256,
    ).hexdigest()


def _read_signed_binding(
    cookie: str | None,
    key: bytes,
) -> str | None:
    """Reject altered, malformed, future-dated and expired cookies."""
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

    expected = _cookie_signature(
        binding,
        issued_at,
        key,
    )

    if not hmac.compare_digest(
        supplied_signature,
        expected,
    ):
        return None

    return binding


def _make_signed_cookie(
    binding: str,
    key: bytes,
) -> str:
    issued_at = str(int(time.time()))
    signature = _cookie_signature(
        binding,
        issued_at,
        key,
    )

    return f"v1.{issued_at}.{binding}.{signature}"


@app.middleware("http")
async def enforce_csrf(
    request: Request,
    call_next,
):
    """Protect state-changing HTTP methods before route handlers run."""
    response = None

    if request.method not in _SAFE_METHODS:
        origin = request.headers.get("origin")

        if origin is not None and origin != _ALLOWED_ORIGIN:
            response = JSONResponse(
                status_code=403,
                content={"detail": "CSRF validation failed."},
            )
        else:
            try:
                csrf_key = settings.require_csrf_key()
            except RuntimeError:
                response = JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Security protection unavailable."
                    },
                )
            else:
                binding = _read_signed_binding(
                    request.cookies.get(_CSRF_COOKIE_NAME),
                    csrf_key,
                )
                token = request.headers.get("X-CSRF-Token")

                if binding is None or not verify_csrf_token(
                    binding,
                    token,
                    secret_key=csrf_key,
                ):
                    response = JSONResponse(
                        status_code=403,
                        content={
                            "detail": "CSRF validation failed."
                        },
                    )

    if response is None:
        response = await call_next(request)

    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[_ALLOWED_ORIGIN],
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-CSRF-Token",
    ],
)


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):
    """Apply security headers to all normal and rejected responses."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/csrf", tags=["Security"])
def get_csrf_token(
    request: Request,
    response: Response,
) -> dict[str, str]:
    """Issue React's CSRF token and separate HttpOnly binding cookie."""
    origin = request.headers.get("origin")

    if origin is not None and origin != _ALLOWED_ORIGIN:
        raise HTTPException(
            status_code=403,
            detail="Origin not allowed.",
        )

    try:
        csrf_key = settings.require_csrf_key()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Security protection unavailable.",
        ) from None

    binding = _read_signed_binding(
        request.cookies.get(_CSRF_COOKIE_NAME),
        csrf_key,
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

    return {
        "csrf_token": issue_csrf_token(
            binding,
            secret_key=csrf_key,
        )
    }


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Confirm FastAPI is running."""
    return {
        "status": "healthy",
        "service": "Dormora API",
    }


@app.get("/api/health/db", tags=["Health"])
def database_health_check() -> dict[str, str]:
    """Confirm PostgreSQL is reachable without exposing credentials."""
    try:
        database_name = check_database_connection()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable.",
        ) from None

    return {
        "status": "connected",
        "database": database_name,
    }


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
app.include_router(
    _file56_registration_router,
    include_in_schema=False,
)

app.include_router(
    _file56_otp_router,
    include_in_schema=False,
)
# --- DORMORA FILE 56 ROUTER MOUNTS: END ---
