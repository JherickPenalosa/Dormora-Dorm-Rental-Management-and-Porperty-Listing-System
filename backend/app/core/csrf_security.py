
"""Dormora CSRF token primitives (Backend File 33).

Destination: backend/app/core/csrf_security.py

This module ONLY generates and verifies signed, time-limited CSRF tokens.
It does not install middleware, issue cookies, create sessions, or change the DB.

Intended future integration:
- On a safe GET request, generate an unpredictable browser binding and store
  it in a host-only, HttpOnly cookie (Secure and __Host- prefixed on HTTPS).
- Return the CSRF token in a JSON response to the trusted React origin.
- For each state-changing request, read the binding from the server-set cookie
  and the token from an explicit X-CSRF-Token header (or a form field).
- Reject requests without a valid token before performing any action.
- Rotate the binding on login/logout and bind it to the new authenticated
  session. Never reuse a pre-login session as an authenticated session.

Do not place the token in URLs or logs. Keep the HMAC key in a separate
DORMORA_CSRF_SECRET configuration value, not the OTP HMAC key.
"""

import hashlib
import hmac
import re
import secrets
import time


CSRF_TOKEN_TTL_SECONDS = 3600
_CLOCK_SKEW_SECONDS = 30
_BINDING_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN_NONCE_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_PATTERN = re.compile(r"[1-9][0-9]{0,15}\Z")


def generate_csrf_binding() -> str:
    """Return an unpredictable 32-byte browser/session binding (64 hex chars).

    The future API must set this in a host-only, HttpOnly cookie; it should not
    take the binding from user-supplied JSON, a query string, or a form field.
    """
    return secrets.token_hex(32)


def _require_secret_key(secret_key: bytes) -> None:
    if not isinstance(secret_key, bytes) or len(secret_key) < 32:
        raise ValueError("CSRF HMAC key must be at least 32 random bytes.")


def _signature(
    *, browser_binding: str, timestamp: str, token_nonce: str, secret_key: bytes
) -> str:
    # Fixed-width components make the signed message unambiguous.
    message = (
        f"dormora-csrf-v1:{browser_binding}:{timestamp}:{token_nonce}"
    ).encode("ascii")
    return hmac.new(secret_key, message, hashlib.sha256).hexdigest()


def issue_csrf_token(browser_binding: str, *, secret_key: bytes) -> str:
    """Issue a signed token tied to a server-managed browser/session binding.

    The signing key must be stable across API restarts and stored privately.
    Tokens are reusable within their TTL; CSRF tokens are not OTPs.
    """
    _require_secret_key(secret_key)
    if not isinstance(browser_binding, str) or not _BINDING_PATTERN.fullmatch(
        browser_binding
    ):
        raise ValueError("CSRF browser binding must be 64 lowercase hex characters.")

    timestamp = str(int(time.time()))
    token_nonce = secrets.token_hex(16)
    signature = _signature(
        browser_binding=browser_binding,
        timestamp=timestamp,
        token_nonce=token_nonce,
        secret_key=secret_key,
    )
    return f"v1.{timestamp}.{token_nonce}.{signature}"


def verify_csrf_token(
    browser_binding: str | None,
    submitted_token: str | None,
    *,
    secret_key: bytes,
) -> bool:
    """Check token, expiry, and binding using constant-time HMAC comparison.

    Both browser_binding and submitted_token must come from different request
    locations (server-set cookie vs explicit header/form field), not both from
    automatically attached cookies. Missing/malformed/expired tokens fail.
    """
    _require_secret_key(secret_key)
    if not isinstance(browser_binding, str) or not _BINDING_PATTERN.fullmatch(
        browser_binding
    ):
        return False
    if not isinstance(submitted_token, str) or len(submitted_token) > 150:
        return False

    parts = submitted_token.split(".")
    if len(parts) != 4:
        return False
    version, timestamp, token_nonce, supplied_signature = parts
    if (
        version != "v1"
        or not _TIMESTAMP_PATTERN.fullmatch(timestamp)
        or not _TOKEN_NONCE_PATTERN.fullmatch(token_nonce)
        or not _SIGNATURE_PATTERN.fullmatch(supplied_signature)
    ):
        return False

    issued_at = int(timestamp)
    now = int(time.time())
    if issued_at > now + _CLOCK_SKEW_SECONDS:
        return False
    if now - issued_at > CSRF_TOKEN_TTL_SECONDS:
        return False

    expected_signature = _signature(
        browser_binding=browser_binding,
        timestamp=timestamp,
        token_nonce=token_nonce,
        secret_key=secret_key,
    )
    return hmac.compare_digest(supplied_signature, expected_signature)
