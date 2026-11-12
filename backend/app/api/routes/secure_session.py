"""Dormora Backend File 110 -- Authenticated AES-256-GCM private contact endpoints.

Preserves File 101 admin-only filterable security event history.

Preserves File 99 FIX and adds a separate GET /admin/security/events endpoint.

REPLACE: backend/app/api/routes/secure_session.py (previously File 105)

Uses File 77 browser-token cookies and File 78 PostgreSQL session storage.

The nine routes are NOT enabled or mounted by importing this module:
  GET  /api/auth/session          Check DB-backed authentication (no renewal).
  GET  /api/auth/me               Server-verified username and account role.
  POST /api/auth/session/refresh  Renew idle timeout after CSRF validation.
  POST /api/auth/logout           Revoke the session and expire cookies.
  GET  /api/auth/admin/security   Admin-only security overview; append-only access audit.
  GET  /api/auth/admin/security/events  Admin-only latest 50 audited events with filters.
  POST /api/auth/password/change  Change own password with current password.
  GET  /api/auth/private-contact  Read own decrypted optional contact.
  POST /api/auth/private-contact  Save own contact encrypted with AES-256-GCM.

File 105 requires a valid OTP-established server-side session, current
password re-verification, signed CSRF cookie + header, and File 104 history
checks. A successful update revokes all user sessions and appends an audit
event in the SAME DB transaction. Five failed current-password attempts
within fifteen minutes temporarily block this endpoint. This is NOT the
Forgot Password reset flow; that separate OTP/grant integration remains to be
done. File 108 sends the change-notification email only AFTER the transaction commits.
SMTP acceptance triggers a separate append-only ALERT_EMAIL_SENT audit event.
Mail failure cannot undo or misrepresent a successful password change.


File 110 adds two account-owner endpoints. They read the verified session
in the same DB transaction as their File 109 service operation. No
user ID, target email, nonce, ciphertext or encryption key is accepted
from or returned to the browser. Admin role cannot access contact data.
Only the POST request changes account data; existing signed CSRF
middleware remains mandatory. These endpoints do not log contact data.

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
File 90 login and File 98 React routing remain unchanged.

The security overview returns the existing sanitized summary and events,
PLUS 24 hourly failed-login buckets, the five highest-failure IPs with active
block status, and recent monitoring-script flags (if File 96 has created its
table). IPs and flag targets are intentionally ADMIN-ONLY; raw event_details,
user agents, passwords, OTPs, session tokens and per-user IDs are never returned.
File 98 accepts added JSON fields but will not render them until File 100.
Every authorized dashboard API fetch appends ADMIN_VIEWED_DASHBOARD, and every
authenticated non-admin request appends ADMIN_ACCESS_DENIED. Audit failure fails
closed; SELECTs do not renew idle expiry. Normal app.main login remains disabled.
This endpoint does not modify security_flags or existing audit log records.
File 101 adds an independently authorized history endpoint; the overview JSON
shape and File 100 React remain unchanged. History exposes bounded log metadata
only to verified admins. It never returns event_details, passwords, OTP codes,
CSRF tokens, session cookies or user IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address, ip_interface
import re
import logging
from contextlib import nullcontext
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, case, cast, func, insert, inspect, or_, select, text

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
from app.services.password_change_alert_email import (
    PasswordChangedAlert,
    send_password_changed_alert_email,
)
from app.services.private_contact_encryption import (
    PrivateContactRejected,
    PrivateContactUnavailable,
    save_private_contact,
    read_private_contact,
)
from app.services.password_change_service import (
    PasswordHistoryUnavailable,
    PasswordPolicyRejected,
    RecentPasswordRejected,
    _matches_hash,
    apply_verified_password_change,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Additional gate; File 76 and File 80 must ALSO be enabled at final activation.
SESSION_ROUTES_ENABLED = False

_CACHE_HEADERS = {"Cache-Control": "no-store"}
_UNAVAILABLE = "Authentication is temporarily unavailable."
_NOT_AUTHENTICATED = "Authentication required."
_MONITOR_LOGGER = logging.getLogger("dormora.admin_monitoring")
_PASSWORD_ALERT_LOGGER = logging.getLogger("dormora.password_alert")


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
        return  # GET may append security audit events, never change account data.
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
# FILE 110: OPTIONAL AES-256-GCM PRIVATE CONTACT -- SESSION OWNER ONLY
# ---------------------------------------------------------------------------
# File 109 stores only nonce + ciphertext in public.user_private_contacts.
# GET discloses the decrypted value solely to the verified current renter/owner.
# POST updates the current user's own encrypted record after signed CSRF check.
# There is intentionally NO user_id/email/username parameter in either route.
# The admin security-monitor role is read-only and cannot use these endpoints.

_PRIVATE_CONTACT_ROLES = frozenset({"renter", "property_owner"})


class PrivateContactSubmission(BaseModel):
    """Never accept a target account ID or an encryption key from the browser."""

    model_config = ConfigDict(extra="forbid")
    contact_number: str = Field(min_length=7, max_length=26, repr=False)


class PrivateContactSnapshot(BaseModel):
    """Decrypted data is returned only to the account that owns this session."""

    has_contact: bool
    contact_number: str | None


class PrivateContactSaveAcknowledgment(BaseModel):
    message: str
    has_contact: bool


def _private_contact_owner(db, session_token: str) -> AuthenticatedAccount:
    """Reverify the real DB session and current role in the SAME transaction."""
    account = _verified_account_in_transaction(db, session_token)
    if account is None:
        raise _http_error(401, _NOT_AUTHENTICATED)
    if account.role not in _PRIVATE_CONTACT_ROLES:
        raise _http_error(403, "Access denied.")
    return account


@router.get(
    "/private-contact",
    status_code=status.HTTP_200_OK,
    response_model=PrivateContactSnapshot,
    summary="Read only your own AES-256 encrypted private contact",
    responses={
        401: {"description": "No active authenticated session."},
        403: {"description": "Account role is not permitted."},
        404: {"description": "Local login routes disabled."},
        503: {"description": "Encrypted contact storage is unavailable."},
    },
)
def current_private_contact(
    request: Request,
    response: Response,
) -> PrivateContactSnapshot:
    """Decrypt only for the session's owner; never renew the idle timeout."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)
    try:
        with SessionLocal.begin() as db:
            owner = _private_contact_owner(db, token)
            # Rechecks active/verified account and owner binding before decrypt.
            contact = read_private_contact(
                db, verified_session_user_id=owner.user_id
            )
    except HTTPException:
        raise
    except Exception:
        # Never expose encrypted material, key status, schema details or IPs.
        raise _http_error(503, "Private contact is temporarily unavailable.") from None
    return PrivateContactSnapshot(
        has_contact=contact is not None,
        contact_number=contact,
    )


@router.post(
    "/private-contact",
    status_code=status.HTTP_200_OK,
    response_model=PrivateContactSaveAcknowledgment,
    summary="Encrypt and store your own optional private contact number",
    responses={
        400: {"description": "Contact number rejected by validation."},
        401: {"description": "No active authenticated session."},
        403: {"description": "Origin, CSRF or account role rejected."},
        404: {"description": "Local login routes disabled."},
        503: {"description": "Encrypted contact storage is unavailable."},
    },
)
def save_current_private_contact(
    payload: PrivateContactSubmission,
    request: Request,
    response: Response,
) -> PrivateContactSaveAcknowledgment:
    """Store ciphertext for the current user after File 56 signed CSRF check.

    As with other state-changing routes, _require_post_csrf_prerequisites()
    checks Origin/header/config, and the existing outer middleware validates
    the signed CSRF cookie+header. Do not call these routes outside that app.
    A failure rolls back the transaction; no plaintext is written to audit logs.
    """
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_post_csrf_prerequisites(request)
    token = _require_session_token(request)
    try:
        with SessionLocal.begin() as db:
            owner = _private_contact_owner(db, token)
            save_private_contact(
                db,
                verified_session_user_id=owner.user_id,
                contact_number=payload.contact_number,
            )
    except HTTPException:
        raise
    except PrivateContactRejected:
        raise _http_error(400, "Enter a valid private contact number.") from None
    except Exception:
        # Wrong key / locked DB / tamper / schema errors must fail closed.
        raise _http_error(503, "Private contact is temporarily unavailable.") from None
    return PrivateContactSaveAcknowledgment(
        message="Private contact saved securely.", has_contact=True,
    )


# ---------------------------------------------------------------------------
# FILE 105: ACCOUNT-OWNED PASSWORD CHANGE (REQUIRES OTP-ESTABLISHED SESSION)
# ---------------------------------------------------------------------------
# This is not a recovery grant and does not give an unauthenticated user
# permission to change a password. File 104 owns the history, password UPDATE,
# session revocation and PASSWORD_CHANGED audit. This route owns session+CSRF
# authorization, current-password re-verification and brute-force throttling.
_PASSWORD_CHANGE_FAILURE_LIMIT = 5
_PASSWORD_CHANGE_FAILURE_WINDOW = timedelta(minutes=15)


class AuthenticatedPasswordChangeSubmission(BaseModel):
    """No user_id, role, or token is accepted from the caller."""

    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=512, repr=False, exclude=True)
    new_password: str = Field(min_length=1, max_length=512, repr=False, exclude=True)
    confirm_password: str = Field(min_length=1, max_length=512, repr=False, exclude=True)


class PasswordChangeAcknowledgment(BaseModel):
    message: str
    authenticated: bool


@router.post(
    "/password/change",
    status_code=status.HTTP_200_OK,
    response_model=PasswordChangeAcknowledgment,
    summary="Change own password using the current password and active session",
    responses={
        400: {"description": "Current password incorrect or new password rejected."},
        401: {"description": "A valid authenticated session is required."},
        403: {"description": "Origin or signed CSRF token rejected."},
        404: {"description": "Login routes disabled."},
        429: {"description": "Too many incorrect current-password attempts."},
        503: {"description": "Password-change storage unavailable."},
    },
)
def change_authenticated_password(
    payload: AuthenticatedPasswordChangeSubmission,
    request: Request,
    response: Response,
) -> PasswordChangeAcknowledgment:
    """Update only the authenticated account, atomically with revocation.

    Security-critical ordering:
      1) Require File 56's signed CSRF middleware + exact Origin.
      2) Validate the *current* PostgreSQL session and current account state.
      3) Lock the account row and verify its Argon2id current password.
      4) Apply File 104's last-three-password rule in the SAME transaction.
      5) Commit password update, history, audit, and session revocation.
      6) Clear browser cookie and ask user to log in with the new password.

    The session was established using password + email OTP during login.
    This endpoint does not implement the separate forgot-password OTP grant.
    After the DB commit, send the File 107 notification to the verified account
    email from PostgreSQL. On SMTP acceptance, append ALERT_EMAIL_SENT in a
    new transaction. Neither failure can undo a committed password change.
    """
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_post_csrf_prerequisites(request)
    token = _require_session_token(request)
    client_ip = _trusted_ip(request)
    user_agent = _safe_agent(request)

    wrong_current = False
    rate_limited = False
    # Populated ONLY on the successful, verified password-change branch.
    # The email and user ID come from the same locked account row, not JSON.
    change_notice: PasswordChangedAlert | None = None
    changed_user_id: int | None = None
    try:
        with SessionLocal.begin() as db:
            account = _verified_account_in_transaction(db, token)
            if account is None:
                raise _http_error(401, _NOT_AUTHENTICATED)

            # The account belongs to the validated session, NEVER to a request
            # body. Lock it before verification, checking and updating hashes.
            row = db.execute(
                select(users_table.c.password_hash, users_table.c.email)
                .where(users_table.c.user_id == account.user_id)
                .with_for_update()
            ).first()
            if row is None:
                raise PasswordHistoryUnavailable("Account unavailable.")

            db_now = db.execute(select(func.clock_timestamp())).scalar_one()
            if not isinstance(db_now, datetime) or db_now.tzinfo is None:
                raise PasswordHistoryUnavailable("Database clock unavailable.")

            recent_failures = int(db.execute(
                select(func.count())
                .select_from(security_logs_table)
                .where(
                    security_logs_table.c.user_id == account.user_id,
                    security_logs_table.c.event_type == "PASSWORD_CHANGE_FAILED",
                    security_logs_table.c.created_at >=
                        db_now - _PASSWORD_CHANGE_FAILURE_WINDOW,
                    security_logs_table.c.created_at <= db_now,
                )
            ).scalar_one())
            if recent_failures >= _PASSWORD_CHANGE_FAILURE_LIMIT:
                rate_limited = True
            elif not _matches_hash(row[0], payload.current_password):
                # Commit the failure event before replying. Throwing an HTTP
                # exception *inside* the with block would roll it back.
                db.execute(insert(security_logs_table).values(
                    user_id=account.user_id,
                    event_type="PASSWORD_CHANGE_FAILED",
                    outcome="failure",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    event_details={"channel": "authenticated_password_change"},
                    created_at=db_now,
                ))
                wrong_current = True
            else:
                # Capture trusted metadata before commit. The password-change
                # service performs its own row lock, hash/history validation,
                # update, revocation and PASSWORD_CHANGED audit in this txn.
                changed = apply_verified_password_change(
                    db,
                    verified_user_id=account.user_id,
                    new_password=payload.new_password,
                    password_confirmation=payload.confirm_password,
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
                if not isinstance(row[1], str) or not row[1].strip():
                    raise PasswordHistoryUnavailable("Verified account email unavailable.")
                changed_user_id = account.user_id
                change_notice = PasswordChangedAlert(
                    email_address=row[1],
                    changed_at=changed.changed_at,
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
    except HTTPException:
        raise
    except (RecentPasswordRejected, PasswordPolicyRejected) as exc:
        # User is already fully authenticated and current password verified;
        # the policy explanation does not disclose whether an account exists.
        raise _http_error(400, str(exc)) from None
    except Exception:
        # No DB, SQL, hash, SMTP or secret details in browser responses.
        raise _http_error(503, "Password change is temporarily unavailable.") from None

    if rate_limited:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect password attempts. Try again later.",
            headers={**_CACHE_HEADERS, "Retry-After": "900"},
        )
    if wrong_current:
        raise _http_error(400, "Current password is incorrect.")

    # A successful change has already committed the new hash and session
    # revocation. Never return a 503 here: the frontend would incorrectly
    # assume that the password was unchanged and could retry the operation.
    # File 107 does not retry uncertain SMTP failures or contain passwords.
    # Clear cookies even if SMTP is unavailable.
    clear_session_cookie(response)
    clear_login_challenge_cookie(response)

    if change_notice is not None and changed_user_id is not None:
        accepted = False
        try:
            send_password_changed_alert_email(change_notice)
            accepted = True
        except Exception as exc:
            # Do not log the exception text: mail libraries may expose private
            # credentials or addresses. No automatic retry after uncertainty.
            _PASSWORD_ALERT_LOGGER.warning(
                "Password committed; change-notification SMTP not confirmed (%s)",
                type(exc).__name__,
            )
        if accepted:
            try:
                # Append-only event AFTER SMTP acceptance. This is deliberately
                # not in the password update transaction: SMTP is not atomic
                # with PostgreSQL. Failure here cannot revert the new password.
                with SessionLocal.begin() as audit_db:
                    audit_db.execute(insert(security_logs_table).values(
                        user_id=changed_user_id,
                        event_type="ALERT_EMAIL_SENT",
                        outcome="success",
                        ip_address=client_ip,
                        user_agent=user_agent,
                        event_details={"channel": "password_change"},
                        created_at=func.clock_timestamp(),
                    ))
            except Exception as exc:
                _PASSWORD_ALERT_LOGGER.warning(
                    "Password-change notification accepted; audit append failed (%s)",
                    type(exc).__name__,
                )

    return PasswordChangeAcknowledgment(
        message="Password changed successfully. Please sign in again.",
        authenticated=False,
    )


# ---------------------------------------------------------------------------
# FILE 93 + 97 + 99: ADMIN-ONLY MONITORING DATA AND ACCESS AUDIT
# ---------------------------------------------------------------------------
# Bounded, hard-coded reporting windows; no user-provided SQL or IP arguments.
# Administrator-only IP ranking and sanitized flag labels serve IT 107 Section 13.
# Raw audit details and identities are never included in the recent-events feed.
_SECURITY_WINDOW_HOURS = 24
_RECENT_SECURITY_EVENTS_LIMIT = 20
_IP_BLOCK_DURATION_SECONDS = 600   # File 72 policy, not a changeable client input.
_SEEDED_IP_BLOCK_REASON = "seeded_login_ip_block"
_PHT = timezone(timedelta(hours=8), name="PHT")
_HOURLY_BUCKET_COUNT = 24
_TOP_IP_LIMIT = 5
_RECENT_MONITOR_FLAGS_LIMIT = 20
_ALLOWED_FLAG_TYPES = frozenset({
    "IP_OVER_THRESHOLD", "ACCOUNT_TARGETED", "OTP_GUESSING", "OFF_HOURS_LOGIN",
})
_ALLOWED_FLAG_SEVERITIES = frozenset({"HIGH", "MED", "INFO"})

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
    "ADMIN_VIEWED_DASHBOARD",
    "ADMIN_ACCESS_DENIED",
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


class SecurityFailedLoginHour(BaseModel):
    hour_start: datetime  # Philippine time (+08:00), start of the hourly bucket.
    count: int


class SecurityTopFailingIp(BaseModel):
    ip_address: str  # Admin-only ranking: one canonical, validated IP address.
    failed_logins: int
    blocked: bool  # Whether File 72's ten-minute IP block is still active.


class SecurityMonitorFlag(BaseModel):
    flag_type: str
    severity: str
    target: str  # Sanitized flag target created by File 96; admin only.
    event_count: int
    description: str
    detected_at: datetime


class AdminSecurityOverview(BaseModel):
    window_hours: int
    generated_at: datetime
    window_start: datetime
    summary: SecurityOverviewSummary
    event_counts: list[SecurityEventCount]
    recent_events: list[SecurityRecentEvent]
    # File 99 additions. The File 98 UI ignores these until File 100.
    failed_logins_hourly: list[SecurityFailedLoginHour]
    top_failing_ips: list[SecurityTopFailingIp]
    monitoring_flags: list[SecurityMonitorFlag]
    monitoring_flags_available: bool
    # File 99 fix: never present unavailable supplementary data as zero events.
    report_warnings: list[str] = Field(default_factory=list)


def _canonical_report_ip(value: object) -> str | None:
    """Do not return malformed or attacker-manipulated IP text from audit data."""
    if value is None:
        return None
    # psycopg can return ipaddress objects for PostgreSQL INET.
    if not isinstance(value, str) and not hasattr(value, "compressed"):
        return None
    try:
        raw = str(value).strip()
        try:
            parsed = ip_address(raw)
        except ValueError:
            # psycopg INET values may render as 127.0.0.1/32 or ::1/128.
            interface = ip_interface(raw)
            if interface.network.prefixlen != interface.max_prefixlen:
                return None
            parsed = interface.ip
        return str(parsed.ipv4_mapped or parsed) if parsed.version == 6 else str(parsed)
    except ValueError:
        return None


def _safe_flag_label(value: object, *, limit: int) -> str:
    """Bound and filter text sourced from monitoring flags before JSON output."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Za-z0-9 _.@:+()/-]", "?", value)[:limit].strip()


def _hourly_login_failures(db, now: datetime) -> list[SecurityFailedLoginHour]:
    """Exactly 24 PHT clock-hour buckets, ending with the current hour.

    Other summary cards use a rolling 24-hour window; this graph covers the
    current partial hour and previous 23 clock hours. This difference is
    deliberate and keeps its x-axis readable and exactly 24 columns.
    """
    current_hour = now.astimezone(_PHT).replace(
        minute=0, second=0, microsecond=0
    )
    first_hour = current_hour - timedelta(hours=_HOURLY_BUCKET_COUNT - 1)
    hour_expr = func.date_trunc(
        "hour", func.timezone("Asia/Manila", security_logs_table.c.created_at)
    )
    rows = db.execute(
        select(hour_expr.label("pht_hour"), func.count().label("failure_count"))
        .where(
            security_logs_table.c.event_type == "LOGIN_FAILED",
            security_logs_table.c.outcome == "failure",
            security_logs_table.c.created_at >= first_hour.astimezone(timezone.utc),
            security_logs_table.c.created_at <= now,
        )
        .group_by(hour_expr)
    ).all()
    counts: dict[datetime, int] = {}
    for value, count in rows:
        if not isinstance(value, datetime):
            raise ValueError("Unexpected hourly audit timestamp.")
        hour = value.replace(tzinfo=_PHT) if value.tzinfo is None else value.astimezone(_PHT)
        counts[hour] = int(count)
    buckets: list[SecurityFailedLoginHour] = []
    for index in range(_HOURLY_BUCKET_COUNT):
        hour = first_hour + timedelta(hours=index)
        buckets.append(SecurityFailedLoginHour(
            hour_start=hour, count=counts.get(hour, 0)
        ))
    return buckets


def _top_failing_ips(db, start: datetime, now: datetime) -> list[SecurityTopFailingIp]:
    """Five largest sources of LOGIN_FAILED across all accounts, last 24h.

    Normalize IPv4-mapped IPv6 in SQL before grouping to match File 72's
    block identity. The returned ranking is accessible to admins only.
    """
    ip_column = security_logs_table.c.ip_address
    # File 99 FIX: PostgreSQL INET is not a text value. Both LIKE and
    # substr(INET, ...) error with SQLSTATE 42883. Cast before text
    # operations; PostgreSQL VARCHAR/TEXT columns also remain supported.
    ip_text = cast(ip_column, String)
    ip_group = case(
        (ip_text.like("::ffff:%"), func.substr(ip_text, 8)),
        else_=ip_text,
    )
    rankings = db.execute(
        select(ip_group.label("source_ip"), func.count().label("failure_count"))
        .where(
            security_logs_table.c.event_type == "LOGIN_FAILED",
            security_logs_table.c.outcome == "failure",
            ip_column.is_not(None),
            ip_text != "",
            security_logs_table.c.created_at >= start,
            security_logs_table.c.created_at <= now,
        )
        .group_by(ip_group)
        .order_by(func.count().desc(), ip_group.asc())
        .limit(_TOP_IP_LIMIT)
    ).all()
    blocked_rows = db.execute(
        select(ip_group.label("blocked_ip"))
        .where(
            security_logs_table.c.event_type == "IP_BLOCKED",
            security_logs_table.c.event_details["reason"].as_string()
            == _SEEDED_IP_BLOCK_REASON,
            security_logs_table.c.created_at > now - timedelta(seconds=_IP_BLOCK_DURATION_SECONDS),
            security_logs_table.c.created_at <= now,
        )
        .distinct()
    ).all()
    blocked_ips = {
        canonical for (raw,) in blocked_rows
        if (canonical := _canonical_report_ip(raw)) is not None
    }
    result: list[SecurityTopFailingIp] = []
    for raw, count in rankings:
        canonical = _canonical_report_ip(raw)
        if canonical is not None:
            result.append(SecurityTopFailingIp(
                ip_address=canonical,
                failed_logins=int(count),
                blocked=canonical in blocked_ips,
            ))
    return result


def _recent_monitoring_flags(
    db, start: datetime, now: datetime
) -> tuple[list[SecurityMonitorFlag], bool]:
    """Read File 96's flag table; never create/update it in an HTTP request."""
    if not inspect(db.connection()).has_table("security_flags", schema="public"):
        return [], False
    rows = db.execute(
        text("""
            SELECT flag_type, severity, target_display, event_count,
                   description, detected_at
              FROM public.security_flags
             WHERE detected_at >= :start AND detected_at <= :now
             ORDER BY detected_at DESC, flag_id DESC
             LIMIT :limit
        """),
        {"start": start, "now": now, "limit": _RECENT_MONITOR_FLAGS_LIMIT},
    ).mappings().all()
    flags: list[SecurityMonitorFlag] = []
    for row in rows:
        if (row["flag_type"] not in _ALLOWED_FLAG_TYPES
                or row["severity"] not in _ALLOWED_FLAG_SEVERITIES):
            continue
        flags.append(SecurityMonitorFlag(
            flag_type=row["flag_type"],
            severity=row["severity"],
            target=_safe_flag_label(row["target_display"], limit=100),
            event_count=max(0, int(row["event_count"])),
            description=_safe_flag_label(row["description"], limit=255),
            detected_at=row["detected_at"],
        ))
    return flags, True



def _optional_admin_section(db, section_name: str, callback, default):
    """Keep supplement failures from hiding the verified core security summary.

    A PostgreSQL error aborts its transaction unless rolled back to a
    savepoint. SQLAlchemy Session.begin_nested() supplies that savepoint.
    Only static section names and exception *types* go to server logs; never
    account identifiers, raw SQL errors, connection URLs or audit payloads.
    """
    try:
        # Test doubles may not implement savepoints. Real Session does.
        begin_nested = getattr(db, "begin_nested", None)
        with begin_nested() if callable(begin_nested) else nullcontext():
            return callback(), None
    except Exception as exc:
        _MONITOR_LOGGER.error(
            "Optional admin report section %s unavailable (%s)",
            section_name, type(exc).__name__,
        )
        return default, section_name


def _append_admin_access_audit(db, request: Request, account: AuthenticatedAccount, *, allowed: bool) -> None:
    """Append the dashboard-access event inside the caller's transaction.

    This is an INSERT only. It is intentionally mandatory: if audit storage
    fails, the request must not return security data or a false 403 success.
    Never persist a client-supplied role or a forwarded client IP header.
    """
    db.execute(
        insert(security_logs_table).values(
            user_id=account.user_id,
            event_type="ADMIN_VIEWED_DASHBOARD" if allowed else "ADMIN_ACCESS_DENIED",
            outcome="info" if allowed else "blocked",
            ip_address=_trusted_ip(request),
            user_agent=_safe_agent(request),
            event_details={
                "channel": "admin_security_api",
                "access": "granted" if allowed else "denied",
            },
            created_at=func.clock_timestamp(),
        )
    )


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
    """Return a sanitized overview and append access auditing atomically.

    The session check never renews idle expiry. Successful requests write an
    ADMIN_VIEWED_DASHBOARD event before querying recent activity. Authenticated
    non-admin requests commit ADMIN_ACCESS_DENIED before returning HTTP 403.
    No account/session data is updated. Audit logging failure returns 503.
    """
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)

    denied = False
    try:
        with SessionLocal.begin() as db:
            account = _verified_account_in_transaction(db, token)
            if account is None:
                raise _http_error(401, _NOT_AUTHENTICATED)

            denied = account.role != "admin"
            _append_admin_access_audit(db, request, account, allowed=not denied)
            # Do not raise HTTP 403 inside this transaction: raising here would
            # ROLLBACK the mandatory denied-access audit INSERT. Leave the
            # context cleanly, commit, and only then return 403 to the caller.
            if not denied:
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
                # Count distinct currently blocked IPs. File 72 stores one
                # IP_BLOCKED event per effective block with the reason below.
                # Only the separate admin-only ranking returns IP addresses.
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
                # File 99 FIX: optional sections are isolated in savepoints.
                # On failure, return explicit warnings rather than hiding the
                # working security overview or claiming that zero incidents exist.
                report_warnings: list[str] = []
                hourly_failures, warning = _optional_admin_section(
                    db, "failed_logins_hourly",
                    lambda: _hourly_login_failures(db, now), [],
                )
                if warning:
                    report_warnings.append(warning)
                top_ips, warning = _optional_admin_section(
                    db, "top_failing_ips",
                    lambda: _top_failing_ips(db, window_start, now), [],
                )
                if warning:
                    report_warnings.append(warning)
                flag_result, warning = _optional_admin_section(
                    db, "monitoring_flags",
                    lambda: _recent_monitoring_flags(db, window_start, now),
                    ([], False),
                )
                monitor_flags, flags_available = flag_result
                if warning:
                    report_warnings.append(warning)
    except HTTPException:
        # Preserve unauthenticated (401) and origin (403) failures.
        raise
    except Exception as exc:
        # Log only the error class, not SQL text/params or sensitive data.
        _MONITOR_LOGGER.error(
            "Core admin monitoring query failed (%s)", type(exc).__name__,
        )
        raise _http_error(503, "Security monitoring is temporarily unavailable.") from None

    if denied:
        # The audit transaction committed successfully. The client receives
        # no admin overview data and no account identifiers.
        raise _http_error(403, "Access denied.")

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
        failed_logins_hourly=hourly_failures,
        top_failing_ips=top_ips,
        monitoring_flags=monitor_flags,
        monitoring_flags_available=flags_available,
        report_warnings=report_warnings,
    )


# ---------------------------------------------------------------------------
# FILE 101: ADMIN-ONLY FILTERABLE RECENT SECURITY EVENTS (SEPARATE API)
# ---------------------------------------------------------------------------
# IT 107 section 13.2: latest 50 events and filters by date range, event type,
# username, and IP. The existing /admin/security response and its 20-item
# summary feed remain unchanged to keep File 100 fully compatible.
#
# Query examples (URL-encode parameters in browsers / React):
#   /api/auth/admin/security/events
#   /api/auth/admin/security/events?event_type=LOGIN_FAILED
#   /api/auth/admin/security/events?username=sample
#   /api/auth/admin/security/events?ip_address=127.0.0.1
#   /api/auth/admin/security/events?start_at=2026-11-06T00:00:00%2B08:00
#                                     &end_at=2026-11-07T23:59:59%2B08:00
#
# Filter rules:
# - Default: 24-hour rolling window; optional explicit dates within last 30 days.
# - ISO-8601 timestamps MUST have timezone offsets. Maximum 30-day range.
# - Username: case-insensitive substring over logged typed name OR user name.
# - IP address: canonical, validated literal; no wildcard or partial match.
# - Event type: exact validated uppercase name; SQL parameters are bound.
# - Fixed limit 50 (+1 for has_more). No raw JSON details or sensitive tokens.
_HISTORY_LIMIT = 50
_HISTORY_MAX_DAYS = 30
_HISTORY_EVENT_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


class SecurityHistoryEvent(BaseModel):
    event_type: str
    outcome: str
    occurred_at: datetime
    username: str | None
    ip_address: str | None
    user_agent: str | None


class AdminSecurityHistory(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    limit: int
    has_more: bool
    events: list[SecurityHistoryEvent]


def _history_datetime(text_value: str | None, *, name: str) -> datetime | None:
    """Parse explicit-offset ISO dates, rejecting ambiguous local/naive times."""
    if text_value is None:
        return None
    if not isinstance(text_value, str) or len(text_value) > 48:
        raise _http_error(422, f"Invalid {name} date filter.")
    try:
        parsed = datetime.fromisoformat(text_value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise _http_error(422, f"Invalid {name} date filter.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _http_error(422, f"{name} must include a timezone offset.")
    return parsed.astimezone(timezone.utc)


def _history_filter_window(
    now: datetime, start_text: str | None, end_text: str | None,
) -> tuple[datetime, datetime]:
    """Limit queries to at most 30 days of recent audit history."""
    start = _history_datetime(start_text, name="start_at")
    end = _history_datetime(end_text, name="end_at") or now
    start = start or end - timedelta(hours=24)
    oldest = now - timedelta(days=_HISTORY_MAX_DAYS)
    if (
        start >= end
        or start < oldest
        or end > now + timedelta(minutes=1)
        or end - start > timedelta(days=_HISTORY_MAX_DAYS)
    ):
        raise _http_error(422, "Date range must be within the last 30 days.")
    return start, end


def _history_text(value: object, *, limit: int) -> str | None:
    """Keep printable audit text only; JSX must still HTML-escape rendering."""
    if not isinstance(value, str):
        return None
    clean = "".join(ch for ch in value if ch.isprintable())[:limit].strip()
    return clean or None


def _history_ip_candidates(value: str) -> tuple[str, ...]:
    """Exact string forms used by PostgreSQL INET, TEXT and mapped-IPv6 IPs."""
    try:
        parsed = ip_address(value.strip())
    except (ValueError, AttributeError):
        raise _http_error(422, "Invalid ip_address filter.") from None
    ipv4_mapped = getattr(parsed, "ipv4_mapped", None)
    if ipv4_mapped is not None:
        parsed = ipv4_mapped
    base = str(parsed)
    bits = 32 if parsed.version == 4 else 128
    choices = {base, f"{base}/{bits}"}
    if parsed.version == 4:
        mapped = f"::ffff:{base}"
        choices.update({mapped, f"{mapped}/128"})
    return tuple(sorted(choices))


def _select_filtered_history(
    db,
    *,
    start: datetime,
    end: datetime,
    event_type: str | None,
    username: str | None,
    ip_address: str | None,
):
    """SELECT event metadata, never raw event_details or user IDs.

    Only the username_typed JSON key is selected; full event_details may hold
    sensitive values and must not leave the server. The account username
    provides fallback for events where typed username isn't present.
    """
    typed_name = security_logs_table.c.event_details["username_typed"].as_string()
    account_name = users_table.c.username
    query = (
        select(
            security_logs_table.c.event_type.label("event_type"),
            security_logs_table.c.outcome.label("outcome"),
            security_logs_table.c.created_at.label("occurred_at"),
            func.coalesce(typed_name, account_name).label("username"),
            security_logs_table.c.ip_address.label("ip_address"),
            security_logs_table.c.user_agent.label("user_agent"),
        )
        .select_from(
            security_logs_table.outerjoin(
                users_table,
                security_logs_table.c.user_id == users_table.c.user_id,
            )
        )
        .where(
            security_logs_table.c.created_at >= start,
            security_logs_table.c.created_at <= end,
        )
    )
    if event_type:
        query = query.where(security_logs_table.c.event_type == event_type)
    if username:
        # SQLAlchemy's autoescape=True treats % and _ as data, not SQL wildcards.
        query = query.where(or_(
            typed_name.icontains(username, autoescape=True),
            account_name.icontains(username, autoescape=True),
        ))
    if ip_address:
        query = query.where(
            cast(security_logs_table.c.ip_address, String).in_(
                _history_ip_candidates(ip_address)
            )
        )
    return db.execute(
        query.order_by(
            security_logs_table.c.created_at.desc(),
            security_logs_table.c.log_id.desc(),
        ).limit(_HISTORY_LIMIT + 1)
    ).mappings().all()


@router.get(
    "/admin/security/events",
    status_code=status.HTTP_200_OK,
    response_model=AdminSecurityHistory,
    summary="Admin-only filtered audit history (latest 50)",
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "Administrator role required or Origin rejected."},
        404: {"description": "Local login routes not enabled."},
        422: {"description": "Invalid history filter."},
        503: {"description": "Security audit storage unavailable."},
    },
)
def admin_security_event_history(
    request: Request,
    response: Response,
    start_at: str | None = Query(default=None, max_length=48),
    end_at: str | None = Query(default=None, max_length=48),
    event_type: str | None = Query(default=None, max_length=80),
    username: str | None = Query(default=None, max_length=100),
    ip_address: str | None = Query(default=None, max_length=64),
) -> AdminSecurityHistory:
    """Server-side authorization and filtered event history, no session renewal.

    Every authorized fetch writes ADMIN_VIEWED_DASHBOARD. Authenticated
    non-admin requests commit ADMIN_ACCESS_DENIED before returning 403.
    No UPDATE/DELETE, and no HTTP access to the File 96 monitoring script.
    """
    response.headers["Cache-Control"] = "no-store"
    _require_enabled()
    _require_known_origin(request, allow_absent=True)
    token = _require_session_token(request)

    if event_type and not _HISTORY_EVENT_TYPE_PATTERN.fullmatch(event_type):
        raise _http_error(422, "Invalid event_type filter.")
    username_filter = username.strip() if username is not None else None
    if username is not None and not username_filter:
        username_filter = None
    ip_filter = ip_address.strip() if ip_address is not None else None
    if ip_address is not None and ip_filter:
        _history_ip_candidates(ip_filter)  # validate before database access
    if ip_address is not None and not ip_filter:
        ip_filter = None

    denied = False
    try:
        with SessionLocal.begin() as db:
            account = _verified_account_in_transaction(db, token)
            if account is None:
                raise _http_error(401, _NOT_AUTHENTICATED)
            denied = account.role != "admin"
            _append_admin_access_audit(db, request, account, allowed=not denied)
            if not denied:
                db_now = db.execute(select(func.clock_timestamp())).scalar_one()
                if not isinstance(db_now, datetime) or db_now.tzinfo is None:
                    raise RuntimeError("Unexpected PostgreSQL clock value.")
                now = db_now.astimezone(timezone.utc)
                start, end = _history_filter_window(now, start_at, end_at)
                rows = _select_filtered_history(
                    db,
                    start=start,
                    end=end,
                    event_type=event_type,
                    username=username_filter,
                    ip_address=ip_filter,
                )
    except HTTPException:
        raise
    except Exception as exc:
        _MONITOR_LOGGER.error(
            "Admin event-history query failed (%s)", type(exc).__name__,
        )
        raise _http_error(503, "Security monitoring is temporarily unavailable.") from None

    if denied:
        raise _http_error(403, "Access denied.")

    entries: list[SecurityHistoryEvent] = []
    for row in rows[:_HISTORY_LIMIT]:
        raw_ip = row["ip_address"]
        clean_ip = _canonical_report_ip(raw_ip)
        raw_event = row["event_type"]
        safe_event = _history_text(raw_event, limit=80)
        if safe_event is None or not _HISTORY_EVENT_TYPE_PATTERN.fullmatch(safe_event):
            safe_event = "UNRECOGNIZED_EVENT"
        raw_outcome = row["outcome"]
        safe_outcome = raw_outcome if raw_outcome in _SAFE_EVENT_OUTCOMES else "other"
        entries.append(SecurityHistoryEvent(
            event_type=safe_event,
            outcome=safe_outcome,
            occurred_at=row["occurred_at"],
            username=_history_text(row["username"], limit=100),
            ip_address=clean_ip,
            user_agent=_history_text(row["user_agent"], limit=255),
        ))

    return AdminSecurityHistory(
        generated_at=now,
        window_start=start,
        window_end=end,
        limit=_HISTORY_LIMIT,
        has_more=len(rows) > _HISTORY_LIMIT,
        events=entries,
    )
