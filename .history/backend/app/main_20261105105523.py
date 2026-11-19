
"""Dormora FastAPI entry point: CSRF cookie and HTTP enforcement (File 36).

Destination: backend/app/main.py (replace File 31).
Requires File 33 (csrf_security.py), File 34 (config.py), and the
DORMORA_CSRF_SECRET installed locally by File 35.

No routes for registration or login are activated by this file.
All unsafe HTTP methods are CSRF-checked before a route executes.
The browser/session binding is issued only by the server in a signed,
HttpOnly, host-only cookie. The CSRF token is returned separately as JSON.

During development, use http://localhost:5173 for React and
http://localhost:8000 for FastAPI. Do not mix localhost with 127.0.0.1
inside the browser; they are different cookie sites.
"""

import hashlib
import hmac
import re
import time

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    if request.method not in _SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin != _ALLOWED_ORIGIN:
            response = JSONResponse(
                status_code=403, content={"detail": "CSRF validation failed."}
            )
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
