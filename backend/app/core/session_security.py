
"""Dormora Backend File 77 -- authenticated-session token and cookie security.

CREATE: backend/app/core/session_security.py

This file provides ONLY authenticated-session cookie primitives. It does not
validate an OTP, create a PostgreSQL session row, authenticate a user, or mount
an API endpoint. Until later integration files are complete, public login
must remain disabled in File 76.

The caller MUST:
  1. Verify the login OTP and create a server-side session in one transaction.
  2. Store ONLY session_token_digest(token), never the raw browser token.
  3. Set the auth cookie ONLY AFTER that transaction commits successfully.
  4. Enforce a seeded 9-minute idle timeout on the server for every request.
  5. Revoke the server-side session during logout and password reset.
  6. Rotate the session token on each newly completed authentication.

The temporary pre-OTP cookie in File 70 is separate from this auth cookie.
Never return or log the raw session token or the OTP code.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets

from fastapi import Request, Response

from app.core.config import settings


# Instructor's seed: D1 = 9; idle timeout is 5 + (D1 mod 5) minutes.
STUDENT_D1 = 9
SESSION_IDLE_TIMEOUT_MINUTES = 15  # Presentation idle timeout
SESSION_IDLE_TIMEOUT_SECONDS = SESSION_IDLE_TIMEOUT_MINUTES * 60

_SESSION_ENTROPY_BYTES = 32  # 256 bits from the OS CSPRNG.
_TOKEN_LENGTH = 43  # Unpadded URL-safe base64 encoding of 32 bytes.
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_DIGEST_DOMAIN = b"dormora-auth-session-token-v1:\x00"

_PRODUCTION_COOKIE_NAME = "__Host-dormora-auth-session"
_DEVELOPMENT_COOKIE_NAME = "dormora-auth-session-dev"


class InvalidSessionToken(ValueError):
    """The value cannot be accepted as a Dormora authenticated-session token."""


def session_cookie_name() -> str:
    """Production uses a host-only, Secure, Path=/ cookie with __Host- prefix."""
    return (
        _PRODUCTION_COOKIE_NAME
        if settings.environment == "production"
        else _DEVELOPMENT_COOKIE_NAME
    )


def _decode_session_token(token: object) -> bytes:
    """Reject malformed and noncanonical base64url values before DB access."""
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise InvalidSessionToken("Invalid session token.")

    try:
        decoded = base64.b64decode(token + "=", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise InvalidSessionToken("Invalid session token.") from None

    if len(decoded) != _SESSION_ENTROPY_BYTES:
        raise InvalidSessionToken("Invalid session token.")

    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if not hmac.compare_digest(token, canonical):
        raise InvalidSessionToken("Invalid session token.")
    return decoded


def is_valid_session_token(token: object) -> bool:
    """A shape check only; it does NOT prove the session exists or is active."""
    try:
        _decode_session_token(token)
    except InvalidSessionToken:
        return False
    return True


def generate_session_token() -> str:
    """Generate a fresh, unpredictable browser bearer token after login OTP."""
    token = secrets.token_urlsafe(_SESSION_ENTROPY_BYTES)
    if not is_valid_session_token(token):  # Defensive invariant.
        raise RuntimeError("Session-token generation failed.")
    return token


def session_token_digest(token: str) -> str:
    """Hash the bearer token for storage/lookup in PostgreSQL.

    This is safe without a separate hashing key because the random token has
    256 bits of entropy. The domain prefix separates it from other SHA-256 uses.
    Never place the raw token, or a digest, in application audit messages.
    """
    _decode_session_token(token)
    return hashlib.sha256(_DIGEST_DOMAIN + token.encode("ascii")).hexdigest()


def read_session_cookie(request: Request) -> str | None:
    """Return a well-formed token only; DB validity MUST be checked separately.

    Treat the result as untrusted bearer material. Do not authorize a request
    using this function alone: the session record must be active, unexpired,
    and associated with an eligible account in the database.
    """
    token = request.cookies.get(session_cookie_name())
    return token if is_valid_session_token(token) else None


def set_session_cookie(response: Response, *, token: str) -> None:
    """Call ONLY after successful OTP + committed, server-side session setup.

    The cookie's nine-minute browser age is a second layer of protection, not
    a substitute for the seeded server-side inactivity timeout. Later handlers
    may reissue it on authenticated activity after server-side idle renewal.
    """
    _decode_session_token(token)
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        max_age=SESSION_IDLE_TIMEOUT_SECONDS,
        httponly=True,
        secure=settings.environment == "production",
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_session_cookie(response: Response) -> None:
    """Expire the browser cookie; logout MUST also revoke the DB session."""
    response.delete_cookie(
        key=session_cookie_name(),
        httponly=True,
        secure=settings.environment == "production",
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
