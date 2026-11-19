
"""Dormora File 128: password recovery audit logging update.

REPLACE: backend/app/api/routes/secure_password_recovery.py (previously File 123)

IMPORTANT: IMPORTING THIS MODULE DOES NOT EXPOSE ANY ENDPOINTS.
RECOVERY_ROUTES_ENABLED remains False and this router is NOT mounted until
File 124 supplies the same signed-CSRF middleware used by Dormora login.
Never mount it on an app lacking File 56's signed cookie/header CSRF verifier.

Endpoints after explicit integration:
  POST /api/auth/password-recovery/identify    Username + Google CAPTCHA
  POST /api/auth/password-recovery/answer      Confirm registered question answer
  POST /api/auth/password-recovery/resend-otp  Replace code after cooldown
  POST /api/auth/password-recovery/verify-otp  Issue one-time reset-only grant
  POST /api/auth/password-recovery/reset       Consume grant, update password

The browser never supplies or receives a user ID. Identifying a username
returns the same three public seed questions for all accounts, including
unknown accounts. A signed, expiring HttpOnly cookie binds that input to the
answer request; it is not an authenticated session. Invalid questions or
answers are audited through the existing File 122 shared-login lockout gate.
Identification after a validated CAPTCHA also records RESET_REQUESTED in the
existing security_logs table for both known and unknown usernames, with a
NULL user_id to avoid account-existence disclosure. Audit insertion must commit
with the question-bank read; on audit failure the route fails closed.
Only a verified security answer may cause File 120 OTP issuance. Only a
verified OTP may cause a File 120 one-time reset grant. File 104 enforces the
last-three password policy, revokes sessions and writes PASSWORD_CHANGED.

Every write request requires trusted Origin, signed-CSRF middleware and a
valid X-CSRF-Token header. IP blocks and database-backed per-IP request
limits run before security-sensitive steps. Responses never return account
IDs, addresses, passwords, answers, OTP values or reset grants.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import ipaddress
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert, select

from app.api.routes import secure_login
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.user import users_table
from app.services.login_service import security_logs_table
from app.services.password_change_alert_email import (
    PasswordChangedAlert,
    send_password_changed_alert_email,
)
from app.services.password_change_service import (
    PasswordHistoryUnavailable,
    PasswordPolicyRejected,
    RecentPasswordRejected,
)
from app.services.password_recovery_challenge_store import (
    RecoveryGrantInvalid,
    RecoveryRateLimited,
    RecoveryStoreUnavailable,
    cancel_recovery_challenge,
    consume_reset_grant_and_change_password,
    create_recovery_challenge,
    resend_recovery_otp,
    verify_recovery_otp,
)
from app.services.password_recovery_otp_email import (
    PasswordRecoveryOtpDelivery,
    send_password_recovery_otp_email,
)
from app.services.recovery_account_gate import (
    RecoveryAccountGateUnavailable,
    recovery_question_choices,
    resolve_recovery_username,
    verify_and_count_recovery_answer,
)

router = APIRouter(prefix="/api/auth/password-recovery", tags=["Password recovery"])
RECOVERY_ROUTES_ENABLED = False  # File 124 explicitly decides local activation.

_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_UNAVAILABLE = "Account recovery is temporarily unavailable."
_INVALID = "The recovery information could not be verified."
_TOO_MANY = "Too many attempts. Please try again later."
_RESTART = "Please restart password recovery."
_MAX_CAPTCHA = 8192
_IDENT_SECONDS = 600
_IDENT_NAME_DEV = "dormora-recovery-identity-dev"
_IDENT_NAME_PROD = "__Host-dormora-recovery-identity"
_OTP_NAME_DEV = "dormora-recovery-otp-dev"
_OTP_NAME_PROD = "__Host-dormora-recovery-otp"
_GRANT_NAME_DEV = "dormora-recovery-grant-dev"
_GRANT_NAME_PROD = "__Host-dormora-recovery-grant"
_ID_PATTERN = re.compile(r"v1\.([1-9][0-9]{0,11})\.([A-Za-z0-9_-]{1,400})\.([0-9a-f]{64})\Z", re.ASCII)
_ID_DOMAIN = b"dormora-password-recovery-identity-v1:"


class IdentifySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=255)
    captcha_token: str = Field(min_length=1, max_length=_MAX_CAPTCHA, repr=False, exclude=True)


class AnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: int
    answer: str = Field(min_length=1, max_length=100, repr=False, exclude=True)
    confirm_answer: str = Field(min_length=1, max_length=100, repr=False, exclude=True)


class OtpSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    otp: str = Field(pattern=r"^[0-9]{6}$", repr=False, exclude=True)


class ResetSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(min_length=1, max_length=512, repr=False, exclude=True)
    confirm_password: str = Field(min_length=1, max_length=512, repr=False, exclude=True)


class QuestionChoice(BaseModel):
    question_id: int
    question_text: str


class IdentifyAcknowledgment(BaseModel):
    message: str
    questions: list[QuestionChoice]


class RecoveryAcknowledgment(BaseModel):
    message: str


def _error(code: int, detail: str, retry: int = 0) -> HTTPException:
    headers = dict(_CACHE)
    if retry > 0:
        headers["Retry-After"] = str(max(1, min(86400, int(retry))))
    return HTTPException(status_code=code, detail=detail, headers=headers)


def _enabled() -> None:
    # Even accidental mounting cannot activate recovery in a normal app.
    if not RECOVERY_ROUTES_ENABLED or not secure_login.PUBLIC_LOGIN_ENABLED or not secure_login.LOGIN_SECURITY_COMPLETE:
        raise _error(404, "Not found.")


def _guards(request: Request) -> tuple[str, str | None]:
    """File 56 middleware MUST additionally verify signed CSRF token/cookie."""
    _enabled()
    if request.headers.get("origin") != settings.frontend_origin.rstrip("/"):
        raise _error(403, "Request origin not permitted.")
    if not request.headers.get("x-csrf-token"):
        raise _error(403, "CSRF token required.")
    try:
        settings.require_csrf_key()
    except (RuntimeError, ValueError):
        raise _error(503, _UNAVAILABLE) from None
    if request.client is None:
        raise _error(503, _UNAVAILABLE)
    try:
        address = ipaddress.ip_address(request.client.host)
        ip = str(getattr(address, "ipv4_mapped", None) or address)
    except (ValueError, TypeError):
        raise _error(503, _UNAVAILABLE) from None
    raw_agent = request.headers.get("user-agent")
    agent = "".join(c for c in raw_agent if c.isprintable())[:255] if isinstance(raw_agent, str) else None
    return ip, agent or None


def _abuse_gate(ip: str, agent: str | None, purpose: str) -> None:
    from app.services.login_ip_service import (
        LoginIpServiceUnavailable, check_login_ip,
    )
    from app.services.login_request_limit_service import (
        LoginRequestLimiterUnavailable, check_and_record_login_request,
    )
    try:
        block = check_login_ip(ip, user_agent=agent)
        if not block.allowed:
            raise _error(429, _TOO_MANY, block.retry_after_seconds)
        # Reuse existing persistent DB-backed quotas. No limiter/DB migration.
        quota = check_and_record_login_request(purpose, client_ip=ip, user_agent=agent)
        if not quota.allowed:
            raise _error(429, _TOO_MANY, quota.retry_after_seconds)
    except HTTPException:
        raise
    except (LoginIpServiceUnavailable, LoginRequestLimiterUnavailable, ValueError):
        raise _error(503, _UNAVAILABLE) from None


def _post_failure_ip_check(ip: str, agent: str | None) -> None:
    from app.services.login_ip_service import (
        LoginIpServiceUnavailable, check_login_ip,
    )
    try:
        block = check_login_ip(ip, user_agent=agent)
    except (LoginIpServiceUnavailable, ValueError):
        raise _error(503, _UNAVAILABLE) from None
    if not block.allowed:
        raise _error(429, _TOO_MANY, block.retry_after_seconds)


def _notify_lockout(event_id: int | None) -> None:
    if event_id is None:
        return
    from app.services.lockout_alert_workflow import dispatch_lockout_alert
    try:
        dispatch_lockout_alert(event_id)
    except Exception:
        # Audit and lockout committed. Mail failure does not grant recovery.
        pass


def _cookie_key(kind: str) -> str:
    production = settings.environment == "production"
    return {
        "identity": _IDENT_NAME_PROD if production else _IDENT_NAME_DEV,
        "otp": _OTP_NAME_PROD if production else _OTP_NAME_DEV,
        "grant": _GRANT_NAME_PROD if production else _GRANT_NAME_DEV,
    }[kind]


def _set_cookie(response: Response, kind: str, value: str, seconds: int) -> None:
    if not isinstance(value, str) or not value or not 0 < seconds <= 900:
        raise _error(503, _UNAVAILABLE)
    response.set_cookie(
        key=_cookie_key(kind), value=value, max_age=seconds,
        httponly=True, secure=settings.environment == "production",
        samesite="strict", path="/",
    )
    response.headers.update(_CACHE)


def _clear_cookie(response: Response, kind: str) -> None:
    response.delete_cookie(
        key=_cookie_key(kind), path="/", httponly=True,
        secure=settings.environment == "production", samesite="strict",
    )
    response.headers.update(_CACHE)


def _signature(body: str) -> str:
    return hmac.new(
        settings.require_csrf_key(), _ID_DOMAIN + body.encode("ascii"), hashlib.sha256
    ).hexdigest()


def _issue_identity_cookie(response: Response, username: str) -> None:
    # Sign even unknown usernames, so the identify response never reveals presence.
    raw = username.strip()
    if (not raw or len(raw) > 255 or not raw.isascii()
            or not raw[0].isalpha() or not raw.isalnum()):
        raise _error(400, "Enter a valid username.")
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    body = f"v1.{int(time.time())}.{encoded}"
    _set_cookie(response, "identity", f"{body}.{_signature(body)}", _IDENT_SECONDS)


def _read_identity_cookie(request: Request) -> str:
    token = request.cookies.get(_cookie_key("identity"))
    if not isinstance(token, str) or len(token) > 560:
        raise _error(401, _RESTART)
    match = _ID_PATTERN.fullmatch(token)
    if match is None:
        raise _error(401, _RESTART)
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_signature(body), sig):
        raise _error(401, _RESTART)
    age = int(time.time()) - int(match.group(1))
    if not 0 <= age < _IDENT_SECONDS:
        raise _error(401, _RESTART)
    packed = match.group(2)
    try:
        raw = base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4)).decode("utf-8")
    except (UnicodeError, ValueError):
        raise _error(401, _RESTART) from None
    if not raw or len(raw) > 255:
        raise _error(401, _RESTART)
    return raw


def _required_cookie(request: Request, kind: str) -> str:
    token = request.cookies.get(_cookie_key(kind))
    if not isinstance(token, str) or not 40 <= len(token) <= 128:
        raise _error(401, _RESTART)
    return token


def _smtp_delivery(issue: object, email: str) -> None:
    send_password_recovery_otp_email(PasswordRecoveryOtpDelivery(
        recipient_email=email, code=issue.code,
        issued_at=issue.issued_at, expires_at=issue.expires_at,
    ))


def _abort_failed_delivery(token: str) -> None:
    try:
        with SessionLocal.begin() as db:
            cancel_recovery_challenge(db, challenge_token=token)
    except Exception:
        # Never return a usable browser challenge when delivery is uncertain.
        pass


def _captcha_check(token: str, ip: str, agent: str | None) -> None:
    # Same reCAPTCHA v2 server-side verification as the functioning login route.
    acceptable = (isinstance(token, str) and 1 <= len(token) <= _MAX_CAPTCHA
                  and token.isascii() and all(33 <= ord(c) <= 126 for c in token))
    if not acceptable:
        _captcha_rejected(ip, agent)
    try:
        good = settings.build_recaptcha_v2_verifier(client_ip=ip)(token)
    except Exception:
        raise _error(503, _UNAVAILABLE) from None
    if good is not True:
        _captcha_rejected(ip, agent)


def _captcha_rejected(ip: str, agent: str | None) -> None:
    from app.services.security_log_service import record_security_event
    try:
        record_security_event(
            event_type="captcha_failed", outcome="failure", ip_address=ip,
            user_agent=agent, event_details={"channel": "password_recovery"},
        )
    except Exception:
        raise _error(503, _UNAVAILABLE) from None
    raise _error(400, "CAPTCHA verification failed. Try again.")


@router.post("/identify", response_model=IdentifyAcknowledgment)
def identify_recovery_account(
    payload: IdentifySubmission, request: Request, response: Response,
) -> IdentifyAcknowledgment:
    """CAPTCHA-gated identification; uniform choices and acknowledgment."""
    response.headers.update(_CACHE)
    ip, agent = _guards(request)
    _abuse_gate(ip, agent, "password")
    _captcha_check(payload.captcha_token, ip, agent)
    try:
        with SessionLocal.begin() as db:
            choices = recovery_question_choices(db)
            # Required handout event: a recovery request was started.
            # Log identically for known and unknown usernames. No account ID,
            # password, CAPTCHA token, recovery OTP, or reset grant is stored.
            # This audit insert is atomic with the question-bank read; if it
            # fails, return the generic 503 instead of silently losing the log.
            db.execute(insert(security_logs_table).values(
                user_id=None,
                event_type="RESET_REQUESTED",
                outcome="info",
                ip_address=ip,
                user_agent=agent,
                event_details={
                    "channel": "password_recovery",
                    "username_typed": payload.username,
                },
                created_at=datetime.now(timezone.utc),
            ))
    except Exception:
        raise _error(503, _UNAVAILABLE) from None
    _issue_identity_cookie(response, payload.username)
    _clear_cookie(response, "otp")
    _clear_cookie(response, "grant")
    return IdentifyAcknowledgment(
        message="Choose one of your registered questions, then enter your answer twice.",
        questions=[QuestionChoice(question_id=qid, question_text=txt) for qid, txt in choices],
    )


@router.post("/answer", response_model=RecoveryAcknowledgment)
def verify_recovery_question_step(
    payload: AnswerSubmission, request: Request, response: Response,
) -> RecoveryAcknowledgment:
    """Verify a registered answer and issue an OTP only after DB commit."""
    response.headers.update(_CACHE)
    ip, agent = _guards(request)
    _abuse_gate(ip, agent, "password")
    username = _read_identity_cookie(request)
    if payload.answer != payload.confirm_answer:
        raise _error(400, "The answers do not match.")

    issue = None
    recipient = None
    try:
        with SessionLocal.begin() as db:
            identity = resolve_recovery_username(db, typed_username=username)
            decision = verify_and_count_recovery_answer(
                db, identity=identity, question_id=payload.question_id,
                answer=payload.answer, confirmation=payload.confirm_answer,
                client_ip=ip, user_agent=agent,
            )
            if decision.status == "approved":
                issue = create_recovery_challenge(
                    db, verified_user_id=decision.trusted_user_id,
                )
                recipient = db.execute(
                    select(users_table.c.email).where(users_table.c.user_id == issue.user_id)
                ).scalar_one()
    except RecoveryRateLimited:
        # Do not distinguish a real account with an issuance cooldown from
        # a nonexistent account, even when a guessed answer is submitted.
        raise _error(401, _INVALID) from None
    except (RecoveryAccountGateUnavailable, RecoveryStoreUnavailable):
        raise _error(503, _UNAVAILABLE) from None
    except Exception:
        raise _error(503, _UNAVAILABLE) from None

    if issue is None:
        _notify_lockout(decision.lockout_event_id)
        if decision.status in {"invalid", "locked"}:
            _post_failure_ip_check(ip, agent)
        raise _error(401, _INVALID)

    # SMTP must occur after commit, NEVER while holding the account row lock.
    try:
        _smtp_delivery(issue, recipient)
    except Exception:
        _abort_failed_delivery(issue.challenge_token)
        raise _error(503, _UNAVAILABLE) from None
    _clear_cookie(response, "identity")
    _set_cookie(response, "otp", issue.challenge_token, 900)
    return RecoveryAcknowledgment(message="If recovery is eligible, a verification code was sent.")


@router.post("/resend-otp", response_model=RecoveryAcknowledgment)
def resend_password_recovery_code(
    request: Request, response: Response,
) -> RecoveryAcknowledgment:
    response.headers.update(_CACHE)
    ip, agent = _guards(request)
    _abuse_gate(ip, agent, "otp_resend")
    token = _required_cookie(request, "otp")
    try:
        with SessionLocal.begin() as db:
            issue = resend_recovery_otp(db, challenge_token=token)
            recipient = db.execute(
                select(users_table.c.email).where(users_table.c.user_id == issue.user_id)
            ).scalar_one()
    except RecoveryRateLimited as exc:
        raise _error(429, _TOO_MANY, exc.retry_after_seconds) from None
    except RecoveryGrantInvalid:
        raise _error(401, _RESTART) from None
    except Exception:
        raise _error(503, _UNAVAILABLE) from None
    try:
        _smtp_delivery(issue, recipient)
    except Exception:
        _abort_failed_delivery(issue.challenge_token)
        raise _error(503, _UNAVAILABLE) from None
    return RecoveryAcknowledgment(message="If recovery remains eligible, another code was sent.")


@router.post("/verify-otp", response_model=RecoveryAcknowledgment)
def verify_password_recovery_code(
    payload: OtpSubmission, request: Request, response: Response,
) -> RecoveryAcknowledgment:
    response.headers.update(_CACHE)
    ip, agent = _guards(request)
    _abuse_gate(ip, agent, "otp_verify")
    token = _required_cookie(request, "otp")
    try:
        with SessionLocal.begin() as db:
            grant = verify_recovery_otp(db, challenge_token=token, code=payload.otp)
    except Exception:
        raise _error(503, _UNAVAILABLE) from None
    if grant is None:
        raise _error(401, "Invalid or expired verification code.")
    _clear_cookie(response, "otp")
    remaining = int((grant.expires_at - datetime.now(timezone.utc)).total_seconds())
    _set_cookie(response, "grant", grant.token, max(1, min(600, remaining)))
    return RecoveryAcknowledgment(message="Code verified. You may now set a new password.")


@router.post("/reset", response_model=RecoveryAcknowledgment)
def reset_recovered_password(
    payload: ResetSubmission, request: Request, response: Response,
) -> RecoveryAcknowledgment:
    response.headers.update(_CACHE)
    ip, agent = _guards(request)
    _abuse_gate(ip, agent, "password")
    token = _required_cookie(request, "grant")
    try:
        with SessionLocal.begin() as db:
            result = consume_reset_grant_and_change_password(
                db, reset_grant_token=token,
                new_password=payload.new_password,
                password_confirmation=payload.confirm_password,
                client_ip=ip, user_agent=agent,
            )
            recipient = db.execute(
                select(users_table.c.email).where(users_table.c.user_id == result.user_id)
            ).scalar_one()
    except RecoveryGrantInvalid:
        raise _error(401, _RESTART) from None
    except (PasswordPolicyRejected, RecentPasswordRejected) as exc:
        # Explanations are safe here: OTP-verified reset grant is required.
        raise _error(400, str(exc)) from None
    except (PasswordHistoryUnavailable, RecoveryStoreUnavailable):
        raise _error(503, _UNAVAILABLE) from None
    except Exception:
        raise _error(503, _UNAVAILABLE) from None

    # Commit is complete. No email failure can roll back the new password.
    _clear_cookie(response, "grant")
    _clear_cookie(response, "identity")
    _clear_cookie(response, "otp")
    try:
        send_password_changed_alert_email(PasswordChangedAlert(
            email_address=recipient, changed_at=result.changed_at,
            client_ip=ip, user_agent=agent,
        ))
    except Exception:
        # Do not claim the password remained unchanged if mail failed.
        pass
    else:
        try:
            with SessionLocal.begin() as audit_db:
                audit_db.execute(insert(security_logs_table).values(
                    user_id=result.user_id, event_type="ALERT_EMAIL_SENT",
                    outcome="success", ip_address=ip, user_agent=agent,
                    event_details={"channel": "password_recovery"},
                    created_at=datetime.now(timezone.utc),
                ))
        except Exception:
            # Password and session revocation have already committed.
            pass
    return RecoveryAcknowledgment(message="Password updated. Sign in again with your new password.")


def _local_preflight() -> None:
    """Read-only readiness check. Never mounts or activates this router."""
    from app.db.database import engine
    if settings.environment != "development":
        raise RuntimeError("Only local development is permitted for File 128 checks.")
    if settings.frontend_origin.rstrip("/") != "http://localhost:5173":
        raise RuntimeError("Expected local React origin http://localhost:5173.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise RuntimeError("Expected Dormora local PostgreSQL target.")
    host = engine.url.host or ""
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.casefold() == "localhost"
    if not local:
        raise RuntimeError("Local PostgreSQL host is required.")
    settings.require_csrf_key()
    if RECOVERY_ROUTES_ENABLED is not False:
        raise RuntimeError("Staged recovery router must remain disabled.")
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        routes = {getattr(route, "path", "") for route in router.routes}
    else:
        routes = {context.path for context in iter_route_contexts(router.routes)}
    expected = {"/api/auth/password-recovery/" + name for name in (
        "identify", "answer", "resend-otp", "verify-otp", "reset",
    )}
    if not expected.issubset(routes):
        raise RuntimeError("A staged recovery endpoint was not registered.")
    print("DORMORA FILE 128 -- RECOVERY AUDIT LOGGING")
    print("Local configuration and route definitions: PASS")
    print("Recovery routes flag: DISABLED (not mounted by this module)")
    print("Five recovery endpoints: PREPARED")
    print("RESET_REQUESTED audit: WIRED after CAPTCHA (not emitted by --check)")
    print("Signed HttpOnly recovery cookies and File 56 CSRF required")
    print("No account, session, OTP, password or database row was changed.")
    print("File 128 check OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dormora staged recovery API")
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        _local_preflight()
    except Exception as exc:
        print("FILE 123 CHECK FAILED:", type(exc).__name__)
        print("Inspect local recovery dependencies and configuration.")
        raise SystemExit(1) from None
