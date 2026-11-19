
"""Dormora Backend File 93 -- authenticated sessions and admin-only security overview.

REPLACE: backend/app/api/routes/secure_session.py (previously File 88)

Uses File 77 browser-token cookies and File 78 PostgreSQL session storage.

The five routes are NOT enabled or mounted by importing this module:
  GET  /api/auth/session          Check DB-backed authentication (no renewal).
  GET  /api/auth/me               Server-verified username and account role.
  POST /api/auth/session/refresh  Renew idle timeout after CSRF validation.
  POST /api/auth/logout           Revoke the session and expire cookies.
  GET  /api/auth/admin/security   Admin-only, read-only audit overview.

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
File 90 login and File 91 React routing remain unchanged.

The security overview exposes ONLY allowlisted event names, outcomes and
timestamps plus aggregate counts. It never returns usernames, emails, IPs,
user IDs, tokens, user agents or event_details. It performs SELECT queries
only, uses the existing File 88 authenticated-session validation and does
NOT renew the idle timeout. Normal app.main login remains disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
        return  # Safe GET; the database is not updated by that endpoint.
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
    responses={401: {"description": "No valid session."},
               404: {"description": "Session routes disabled."},
               503: {"description": "Session storage unavailable."}},
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



def _verified_account_in_transaction(db, token: str) -> AuthenticatedAccount | None:
    """Resolve identity only from a still-active DB session and the users row.

    The validated session supplies the ONLY user_id used in the user lookup.
    This GET does not renew the nine-minute idle deadline. Protected writes
    must recheck permissions independently in their own server transaction.
    """
    active = validate_auth_session(db, token, renew_idle=False)
    if active is None:
        return None

    username_column = users_table.c.get("username")
    role_column = users_table.c.get("role")
    status_column = users_table.c.get("account_status")
    verified_column = users_table.c.get("email_verified_at")
    if any(column is None for column in (
        username_column, role_column, status_column, verified_column,
    )):
        raise AccountIdentityUnavailable("Account role schema is unavailable.")

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
    # Support SQLAlchemy Enum values without accepting arbitrary user input.
    raw_role = getattr(role_value, "value", role_value)
    if (
        not isinstance(username, str)
        or not username.strip()
        or len(username) > 255
        or not isinstance(raw_role, str)
        or raw_role not in _ALLOWED_ROLES
    ):
        raise AccountIdentityUnavailable("Account role is unavailable.")

    return AuthenticatedAccount(
        user_id=active.user_id,
        username=username,
        role=raw_role,
        expires_at=active.expires_at,
    )


def require_authenticated_account(
    request: Request, *, allowed_roles: frozenset[str] | None = None,
) -> AuthenticatedAccount:
    """Server-side guard for future renter/owner/admin protected endpoints.

    Future endpoints must call this or an equivalent DB-backed dependency on
    EVERY request. React route guards alone cannot authorize backend actions.
    allowed_roles is hard-coded in the server route, NEVER read from JSON.
    """
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)
    if allowed_roles is not None and (
        not allowed_roles or not allowed_roles.issubset(_ALLOWED_ROLES)
    ):
        raise ValueError("Server role permission is misconfigured.")

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
    request: Request, response: Response,
) -> AuthenticatedAccountAcknowledgment:
    """Read account role from PostgreSQL; do not trust client-selected roles."""
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
    responses={401: {"description": "No valid session."},
               403: {"description": "Origin or CSRF rejected."},
               404: {"description": "Session routes disabled."},
               503: {"description": "Session storage unavailable."}},
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
    responses={403: {"description": "Origin or CSRF rejected."},
               404: {"description": "Session routes disabled."},
               503: {"description": "Session storage unavailable."}},
)
def logout_auth_session(
    request: Request,
    response: Response,
) -> LogoutAcknowledgment:
    """Revoke the authenticated DB session before returning a logout success.

    Logout is idempotent: a missing, stale, or already-revoked cookie can be
    cleared safely. A database error is NOT reported as a completed logout.
    """
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_post_csrf_prerequisites(request)
    token = read_session_cookie(request)

    if token is not None:
        # Resolve before transaction so missing client metadata cannot turn
        # a successfully committed DB revocation into an HTTP 503.
        ip = _trusted_ip(request)
        agent = _safe_agent(request)
        try:
            with SessionLocal.begin() as db:
                active = validate_auth_session(db, token, renew_idle=False)
                revoked = revoke_auth_session(db, token)
                if active is not None and revoked:
                    db.execute(
                        insert(security_logs_table).values(
                            user_id=active.user_id,
                            event_type="LOGOUT",
                            outcome="success",
                            ip_address=ip,
                            user_agent=agent,
                            event_details={"channel": "authentication"},
                            created_at=func.clock_timestamp(),
                        )
                    )
        except Exception:
            raise _http_error(503, _UNAVAILABLE) from None

    # Clearing cookies alone is not logout. DB revocation committed first.
    clear_session_cookie(response)
    clear_login_challenge_cookie(response)
    return LogoutAcknowledgment(message="Signed out.", authenticated=False)


# ---------------------------------------------------------------------------
# FILE 93: ADMIN-ONLY READ-ONLY SECURITY MONITORING DATA
# ---------------------------------------------------------------------------
# Bounded audit data: no pagination or user-supplied time range in this first
# endpoint. Account activity, IP addresses and untrusted event_details never
# leave the API. A later admin UI may visualize these sanitized results.
_SECURITY_WINDOW_HOURS = 24
_RECENT_SECURITY_EVENTS_LIMIT = 20
_IP_BLOCK_DURATION_SECONDS = 600   # File 72 policy, not a changeable client input.
_SEEDED_IP_BLOCK_REASON = "seeded_login_ip_block"

_MONITORED_SECURITY_EVENTS = (
    "LOGIN_REQUEST",
    "LOGIN_REQUEST_LIMITED",
    "LOGIN_FAILED",
    "LOGIN_LOCKED",
    "LOCKOUT_TIER_1",
    "LOCKOUT_TIER_2",
    "LOCKOUT_TIER_3",
    "IP_BLOCKED",
    "LOGIN_PASSWORD_VERIFIED",
    "LOGIN_SUCCESS",
    "LOGIN_NOT_ELIGIBLE",
    "OTP_SENT",
    "OTP_FAILED",
    "LOGOUT",
)
_SAFE_EVENT_OUTCOMES = frozenset({"success", "failure", "info", "blocked"})


class SecurityEventCount(BaseModel):
    event_type: str
    count: int


class SecurityRecentEvent(BaseModel):
    event_type: str
    outcome: str
    occurred_at: datetime


class SecurityOverviewSummary(BaseModel):
    failed_logins: int
    successful_logins: int
    lockout_tier_events: int
    blocked_login_attempts: int
    ip_block_events: int
    active_ip_blocks: int
    limited_requests: int
    currently_locked_accounts: int
    accounts_with_failed_login_counter: int


class AdminSecurityOverview(BaseModel):
    window_hours: int
    generated_at: datetime
    window_start: datetime
    summary: SecurityOverviewSummary
    event_counts: list[SecurityEventCount]
    recent_events: list[SecurityRecentEvent]


@router.get(
    "/admin/security",
    status_code=status.HTTP_200_OK,
    response_model=AdminSecurityOverview,
    summary="Read sanitized security-monitoring data (admin only)",
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "Administrator role required or Origin rejected."},
        404: {"description": "Local login routes not enabled."},
        503: {"description": "Security audit storage unavailable."},
    },
)
def admin_security_overview(
    request: Request,
    response: Response,
) -> AdminSecurityOverview:
    """Return safe aggregates and the latest 20 events from the last 24 hours.

    Access check and audit SELECT queries share one database transaction.
    File 78 validation uses a PostgreSQL row lock but renew_idle=False, so
    this GET does not change session or audit data. No user-controlled role,
    user ID, time range, query fragment or table name is accepted.
    """
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)

    try:
        with SessionLocal.begin() as db:
            account = _verified_account_in_transaction(db, token)
            if account is None:
                raise _http_error(401, _NOT_AUTHENTICATED)
            if account.role != "admin":
                raise _http_error(403, "Access denied.")

            db_now = db.execute(select(func.clock_timestamp())).scalar_one()
            if not isinstance(db_now, datetime) or db_now.tzinfo is None:
                raise RuntimeError("Unexpected PostgreSQL clock value.")
            now = db_now.astimezone(timezone.utc)
            window_start = now - timedelta(hours=_SECURITY_WINDOW_HOURS)

            rows = db.execute(
                select(
                    security_logs_table.c.event_type,
                    func.count().label("event_count"),
                )
                .where(
                    security_logs_table.c.event_type.in_(
                        _MONITORED_SECURITY_EVENTS
                    ),
                    security_logs_table.c.created_at >= window_start,
                    security_logs_table.c.created_at <= now,
                )
                .group_by(security_logs_table.c.event_type)
            ).all()
            counts = {str(name): int(count) for name, count in rows}

            recent_rows = db.execute(
                select(
                    security_logs_table.c.event_type,
                    security_logs_table.c.outcome,
                    security_logs_table.c.created_at,
                )
                .where(
                    security_logs_table.c.event_type.in_(
                        _MONITORED_SECURITY_EVENTS
                    ),
                    security_logs_table.c.created_at >= window_start,
                    security_logs_table.c.created_at <= now,
                )
                .order_by(
                    security_logs_table.c.created_at.desc(),
                    security_logs_table.c.log_id.desc(),
                )
                .limit(_RECENT_SECURITY_EVENTS_LIMIT)
            ).all()

            currently_locked = int(
                db.execute(
                    select(func.count())
                    .select_from(users_table)
                    .where(users_table.c.locked_until > now)
                ).scalar_one()
            )
            accounts_with_failures = int(
                db.execute(
                    select(func.count())
                    .select_from(users_table)
                    .where(users_table.c.failed_login_attempts > 0)
                ).scalar_one()
            )
            # No IPs are returned. File 72 stores one IP_BLOCKED event per
            # effective block and uses the fixed reason below.
            active_ip_blocks = int(
                db.execute(
                    select(func.count(func.distinct(
                        security_logs_table.c.ip_address
                    )))
                    .where(
                        security_logs_table.c.event_type == "IP_BLOCKED",
                        security_logs_table.c.event_details["reason"].as_string()
                        == _SEEDED_IP_BLOCK_REASON,
                        security_logs_table.c.created_at
                        > now - timedelta(seconds=_IP_BLOCK_DURATION_SECONDS),
                        security_logs_table.c.created_at <= now,
                    )
                ).scalar_one()
            )

    except HTTPException:
        # 401 and 403 must not be disguised as 503 errors.
        raise
    except Exception:
        # Do not leak DB details, arbitrary audit content or account metadata.
        raise _http_error(503, "Security monitoring is temporarily unavailable.") from None

    recent: list[SecurityRecentEvent] = []
    for event_name, outcome, happened_at in recent_rows:
        # Whitelist outcomes, because event records could contain untrusted text.
        safe_outcome = (
            str(outcome) if outcome in _SAFE_EVENT_OUTCOMES else "other"
        )
        recent.append(SecurityRecentEvent(
            event_type=str(event_name),
            outcome=safe_outcome,
            occurred_at=happened_at,
        ))

    return AdminSecurityOverview(
        window_hours=_SECURITY_WINDOW_HOURS,
        generated_at=now,
        window_start=window_start,
        summary=SecurityOverviewSummary(
            failed_logins=counts.get("LOGIN_FAILED", 0),
            successful_logins=counts.get("LOGIN_SUCCESS", 0),
            lockout_tier_events=sum(
                counts.get(f"LOCKOUT_TIER_{tier}", 0) for tier in (1, 2, 3)
            ),
            blocked_login_attempts=counts.get("LOGIN_LOCKED", 0),
            ip_block_events=counts.get("IP_BLOCKED", 0),
            active_ip_blocks=active_ip_blocks,
            limited_requests=counts.get("LOGIN_REQUEST_LIMITED", 0),
            currently_locked_accounts=currently_locked,
            accounts_with_failed_login_counter=accounts_with_failures,
        ),
        event_counts=[
            SecurityEventCount(event_type=name, count=counts.get(name, 0))
            for name in _MONITORED_SECURITY_EVENTS
        ],
        recent_events=recent,
    )
