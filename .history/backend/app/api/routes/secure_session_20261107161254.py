
"""Dormora Backend File 88 -- session, logout and server-verified account roles.

REPLACE: backend/app/api/routes/secure_session.py (previously File 81)

Uses File 77 browser-token cookies and File 78 PostgreSQL session storage.

The four routes are NOT enabled or mounted by importing this module:
  GET  /api/auth/session          Check DB-backed authentication (no renewal).
  GET  /api/auth/me               Server-verified username and account role.
  POST /api/auth/session/refresh  Renew idle timeout after CSRF validation.
  POST /api/auth/logout           Revoke the session and expire cookies.

SECURITY REQUIREMENTS BEFORE ACTIVATION:
- File 56's middleware must validate signed CSRF cookies and headers for POST.
  The header-presence check in this file is NOT sufficient on its own.
- File 76's password route and File 80's OTP route must be completely tested.
- Use a trusted Origin and CORS policy; do not trust forwarded client IP headers.
- All additional protected endpoints must check File 78's server-side session
  AND the current role in PostgreSQL; frontend navigation is not authorization.
- SESSION_ROUTES_ENABLED must remain False until those integrations are ready.

A successful GET status request does NOT extend the session. Refresh is POST
because it changes server-side expiry; it requires Origin and signed CSRF.
No bearer session token, token digest, OTP, or user ID appears in JSON.
The account role is read from public.users for the validated session's user_id,
never from the browser. Only renter/property_owner/admin are recognized.
File 86's local runner already mounts this existing router. It still checks
its original six required routes; the new /me endpoint is an additional GET.
File 87's React login page is unchanged. Frontend role navigation comes later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, insert, select

from app.api.routes import secure_login, secure_login_otp
from app.core.config import settings
from app.core.login_challenge import clear_login_challenge_cookie
from app.core.session_security import (
    clear_session_cookie,
    read_session_cookie,
    set_session_cookie,
)
from app.db.database import SessionLocal
from app.models.user import users_table
from app.services.auth_session_store import (
    revoke_auth_session,
    validate_auth_session,
)
from app.services.login_otp_service import security_logs_table


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Additional gate; File 76 and File 80 must ALSO be enabled at final activation.
SESSION_ROUTES_ENABLED = False

_CACHE_HEADERS = {"Cache-Control": "no-store"}
_UNAVAILABLE = "Authentication is temporarily unavailable."
_NOT_AUTHENTICATED = "Authentication required."


class SessionStatusAcknowledgment(BaseModel):
    """Browser-readable result without any credential or user identifier."""

    authenticated: bool
    expires_at: datetime


class LogoutAcknowledgment(BaseModel):
    message: str
    authenticated: bool


AccountRole = Literal["renter", "property_owner", "admin"]
_ALLOWED_ROLES = frozenset({"renter", "property_owner", "admin"})


class AuthenticatedAccountAcknowledgment(BaseModel):
    """Non-secret, server-verified account information for protected navigation."""

    authenticated: bool
    username: str
    role: AccountRole
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedAccount:
    """Trusted backend-only identity; do not treat client JSON as this class."""

    user_id: int
    username: str
    role: AccountRole
    expires_at: datetime


class AccountIdentityUnavailable(RuntimeError):
    """Required account fields or role mapping are unavailable; fail closed."""


def _http_error(code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=code, detail=message, headers=dict(_CACHE_HEADERS)
    )


def _require_enabled() -> None:
    """Keep these endpoints dark until every login gate has been released."""
    if not (
        SESSION_ROUTES_ENABLED
        and secure_login.PUBLIC_LOGIN_ENABLED
        and secure_login.LOGIN_SECURITY_COMPLETE
        and secure_login_otp.LOGIN_OTP_VERIFY_ENABLED
    ):
        raise _http_error(404, "Not found.")


def _require_known_origin(request: Request, *, allow_absent: bool = False) -> None:
    origin = request.headers.get("origin")
    if origin is None and allow_absent:
        return
    if origin != settings.frontend_origin.rstrip("/"):
        raise _http_error(403, "Request origin is not permitted.")


def _require_post_csrf_prerequisites(request: Request) -> None:
    """Not a CSRF verifier; signed cookie/header check belongs to File 56."""
    _require_known_origin(request)
    if not request.headers.get("x-csrf-token"):
        raise _http_error(403, "CSRF token required.")
    try:
        settings.require_csrf_key()
    except (RuntimeError, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None


def _trusted_ip(request: Request) -> str:
    """Never use X-Forwarded-For supplied by a browser."""
    if request.client is None:
        raise _http_error(503, _UNAVAILABLE)
    try:
        parsed = ip_address(request.client.host)
        mapped = getattr(parsed, "ipv4_mapped", None)
        return str(mapped if mapped is not None else parsed)
    except (TypeError, ValueError):
        raise _http_error(503, _UNAVAILABLE) from None


def _safe_agent(request: Request) -> str | None:
    agent = request.headers.get("user-agent")
    if not isinstance(agent, str):
        return None
    return "".join(char for char in agent if char.isprintable())[:255] or None


def _require_session_token(request: Request) -> str:
    token = read_session_cookie(request)
    if token is None:
        raise _http_error(401, _NOT_AUTHENTICATED)
    return token


@router.get(
    "/session",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusAcknowledgment,
    summary="Check current database-backed session (not enabled)",
    responses={
        401: {"description": "No valid session."},
        404: {"description": "Session routes disabled."},
        503: {"description": "Session storage unavailable."},
    },
)
def current_auth_session(
    request: Request,
    response: Response,
) -> SessionStatusAcknowledgment:
    """Read-only check. Does NOT update PostgreSQL idle expiry or cookies."""
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)

    try:
        with SessionLocal.begin() as db:
            active = validate_auth_session(db, token, renew_idle=False)
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    if active is None:
        raise _http_error(401, _NOT_AUTHENTICATED)
    return SessionStatusAcknowledgment(
        authenticated=True,
        expires_at=active.expires_at,
    )


def _verified_account_in_transaction(
    db, token: str
) -> AuthenticatedAccount | None:
    """Resolve account identity from the validated DB session and users row."""
    active = validate_auth_session(db, token, renew_idle=False)
    if active is None:
        return None

    username_column = users_table.c.get("username")
    role_column = users_table.c.get("role")
    status_column = users_table.c.get("account_status")
    verified_column = users_table.c.get("email_verified_at")

    if any(
        column is None
        for column in (
            username_column,
            role_column,
            status_column,
            verified_column,
        )
    ):
        raise AccountIdentityUnavailable(
            "Account role schema is unavailable."
        )

    row = db.execute(
        select(
            username_column.label("username"),
            role_column.label("role"),
            status_column.label("account_status"),
            verified_column.label("email_verified_at"),
        ).where(users_table.c.user_id == active.user_id)
    ).mappings().first()

    if (
        row is None
        or row["account_status"] != "active"
        or row["email_verified_at"] is None
    ):
        return None

    username = row["username"]
    role_value = row["role"]
    raw_role = getattr(role_value, "value", role_value)

    if (
        not isinstance(username, str)
        or not username.strip()
        or len(username) > 255
        or not isinstance(raw_role, str)
        or raw_role not in _ALLOWED_ROLES
    ):
        raise AccountIdentityUnavailable(
            "Account role is unavailable."
        )

    return AuthenticatedAccount(
        user_id=active.user_id,
        username=username,
        role=raw_role,
        expires_at=active.expires_at,
    )


def require_authenticated_account(
    request: Request,
    *,
    allowed_roles: frozenset[str] | None = None,
) -> AuthenticatedAccount:
    """Server-side authorization helper for future protected endpoints.

    Future protected operations must check session and account role on the
    backend for every request. React navigation is not a security boundary.
    """
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)

    if allowed_roles is not None and (
        not allowed_roles or not allowed_roles.issubset(_ALLOWED_ROLES)
    ):
        raise ValueError(
            "Server role permission is misconfigured."
        )

    try:
        with SessionLocal.begin() as db:
            account = _verified_account_in_transaction(db, token)
    except AccountIdentityUnavailable:
        raise _http_error(503, _UNAVAILABLE) from None
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    if account is None:
        raise _http_error(401, _NOT_AUTHENTICATED)

    if allowed_roles is not None and account.role not in allowed_roles:
        raise _http_error(403, "Access denied.")

    return account


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=AuthenticatedAccountAcknowledgment,
    summary="Read server-verified account role for current session",
    responses={
        401: {"description": "No valid session."},
        403: {"description": "Request Origin rejected."},
        404: {"description": "Session routes disabled."},
        503: {"description": "Session or account role unavailable."},
    },
)
def current_authenticated_account(
    request: Request,
    response: Response,
) -> AuthenticatedAccountAcknowledgment:
    """Return account identity obtained from PostgreSQL, not browser input."""
    response.headers["Cache-Control"] = "no-store"
    account = require_authenticated_account(request)

    return AuthenticatedAccountAcknowledgment(
        authenticated=True,
        username=account.username,
        role=account.role,
        expires_at=account.expires_at,
    )


@router.post(
    "/session/refresh",
    status_code=status.HTTP_200_OK,
    response_model=SessionStatusAcknowledgment,
    summary="Refresh the server-side session idle timeout (not enabled)",
    responses={
        401: {"description": "No valid session."},
        403: {"description": "Origin or CSRF rejected."},
        404: {"description": "Session routes disabled."},
        503: {"description": "Session storage unavailable."},
    },
)
def refresh_auth_session(
    request: Request,
    response: Response,
) -> SessionStatusAcknowledgment:
    """Move the DB idle deadline forward only for a still-valid session."""
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_post_csrf_prerequisites(request)
    token = _require_session_token(request)

    try:
        with SessionLocal.begin() as db:
            active = validate_auth_session(db, token, renew_idle=True)
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    if active is None:
        raise _http_error(401, _NOT_AUTHENTICATED)

    # The transaction COMMITTED above before the browser cookie is refreshed.
    try:
        set_session_cookie(response, token=token)
    except Exception:
        raise _http_error(503, _UNAVAILABLE) from None

    return SessionStatusAcknowledgment(
        authenticated=True,
        expires_at=active.expires_at,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=LogoutAcknowledgment,
    summary="Revoke database session and clear browser cookies (not enabled)",
    responses={
        403: {"description": "Origin or CSRF rejected."},
        404: {"description": "Session routes disabled."},
        503: {"description": "Session storage unavailable."},
    },
)
def logout_auth_session(
    request: Request,
    response: Response,
) -> LogoutAcknowledgment:
    """Revoke the authenticated DB session before returning logout success."""
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_post_csrf_prerequisites(request)
    token = read_session_cookie(request)

    if token is not None:
        ip = _trusted_ip(request)
        agent = _safe_agent(request)

        try:
            with SessionLocal.begin() as db:
                active = validate_auth_session(
                    db, token, renew_idle=False
                )
                revoked = revoke_auth_session(db, token)

                if active is not None and revoked:
                    db.execute(
                        insert(security_logs_table).values(
                            user_id=active.user_id,
                            event_type="LOGOUT",
                            outcome="success",
                            ip_address=ip,
                            user_agent=agent,
                            event_details={
                                "channel": "authentication"
                            },
                            created_at=func.clock_timestamp(),
                        )
                    )
        except Exception:
            raise _http_error(503, _UNAVAILABLE) from None

    clear_session_cookie(response)
    clear_login_challenge_cookie(response)

    return LogoutAcknowledgment(
        message="Signed out.",
        authenticated=False,
    )
