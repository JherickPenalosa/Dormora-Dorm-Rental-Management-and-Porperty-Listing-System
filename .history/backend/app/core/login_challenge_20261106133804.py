"""Dormora File 70: signed, temporary password-to-OTP browser binding.

Create: backend/app/core/login_challenge.py
This cookie is NOT an authenticated session. Create it only after password
verification and successful OTP delivery. Routes still need Origin, CSRF,
rate limits and File 68's database checks before accepting an OTP.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import Request, Response

CHALLENGE_TTL_SECONDS = 15 * 60
_DOMAIN = b"dormora-login-challenge-v1:"
_TOKEN = re.compile(r"v1\.([1-9][0-9]{0,18})\.([1-9][0-9]{0,18})\.([1-9][0-9]{0,15})\.([0-9a-f]{64})\Z")


@dataclass(frozen=True)
class LoginChallenge:
    """Internal verified claims; never treat these as proof of a full login."""
    user_id: int
    otp_id: int
    started_at: int


class InvalidLoginChallenge(ValueError):
    """Missing, malformed, altered or expired password-step cookie."""


def _cookie_name() -> str:
    return "__Host-dormora-login-pending" if settings.environment == "production" else "dormora-login-pending-dev"


def _signature(body: str) -> str:
    # Separate message domain from registration cookies and CSRF tokens.
    return hmac.new(settings.require_csrf_key(), _DOMAIN + body.encode("ascii"), hashlib.sha256).hexdigest()


def _valid_id(value: object) -> bool:
    return type(value) is int and 0 < value <= 9_223_372_036_854_775_807


def _encode(challenge: LoginChallenge) -> str:
    if not _valid_id(challenge.user_id) or not _valid_id(challenge.otp_id):
        raise ValueError("Positive database IDs are required.")
    if type(challenge.started_at) is not int or challenge.started_at <= 0:
        raise ValueError("Invalid challenge timestamp.")
    body = f"v1.{challenge.user_id}.{challenge.otp_id}.{challenge.started_at}"
    return f"{body}.{_signature(body)}"


def verify_login_challenge(token: str | None) -> LoginChallenge:
    """Verify signature and age. Does not query the account or OTP database."""
    if not isinstance(token, str) or len(token) > 160:
        raise InvalidLoginChallenge("Login verification must be restarted.")
    match = _TOKEN.fullmatch(token)
    if match is None:
        raise InvalidLoginChallenge("Login verification must be restarted.")
    body, supplied = token.rsplit(".", 1)
    if not hmac.compare_digest(_signature(body), supplied):
        raise InvalidLoginChallenge("Login verification must be restarted.")
    user_id, otp_id, started_at = map(int, match.groups()[:3])
    age = int(time.time()) - started_at
    if not _valid_id(user_id) or not _valid_id(otp_id) or not 0 <= age < CHALLENGE_TTL_SECONDS:
        raise InvalidLoginChallenge("Login verification must be restarted.")
    return LoginChallenge(user_id, otp_id, started_at)


def _set_cookie(response: Response, challenge: LoginChallenge) -> None:
    remaining = challenge.started_at + CHALLENGE_TTL_SECONDS - int(time.time())
    if not 0 < remaining <= CHALLENGE_TTL_SECONDS:
        raise InvalidLoginChallenge("Login verification must be restarted.")
    response.set_cookie(
        key=_cookie_name(), value=_encode(challenge), max_age=remaining,
        httponly=True, secure=settings.environment == "production",
        samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def issue_login_challenge_cookie(response: Response, *, user_id: int, otp_id: int) -> None:
    """Call only after accepted password AND successful login OTP delivery."""
    _set_cookie(response, LoginChallenge(user_id, otp_id, int(time.time())))


def read_login_challenge(request: Request) -> LoginChallenge:
    """Read trusted IDs from the signed cookie, never from browser JSON."""
    return verify_login_challenge(request.cookies.get(_cookie_name()))


def replace_login_challenge_cookie(
    request: Request, response: Response, *, new_otp_id: int,
) -> None:
    """After a successful resend, bind the new OTP without extending lifetime.

    The route must pass this cookie's old OTP ID to File 68 when resending,
    then call this only after the replacement code is delivered and marked sent.
    """
    previous = read_login_challenge(request)
    _set_cookie(response, LoginChallenge(previous.user_id, new_otp_id, previous.started_at))


def clear_login_challenge_cookie(response: Response) -> None:
    """Clear after completed login or cancellation; DB consumption blocks replay."""
    response.delete_cookie(
        key=_cookie_name(), path="/", httponly=True,
        secure=settings.environment == "production", samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"