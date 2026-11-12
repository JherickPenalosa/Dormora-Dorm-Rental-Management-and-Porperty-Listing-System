
"""Secure email OTP primitives for Dormora.

Backend File 16 — destination: backend/app/core/otp_security.py

Generates six-digit codes, 32-character hexadecimal nonces, and keyed
HMAC-SHA256 digests. This module does not read secrets from configuration,
store OTPs in PostgreSQL, send emails, or enforce expiry/attempt limits.
Those behaviors belong to later files.
"""

import hashlib
import hmac
import json
import re
import secrets


_CODE_RE = re.compile(r"[0-9]{6}")
_NONCE_RE = re.compile(r"[0-9a-f]{32}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_ALLOWED_PURPOSES = frozenset({"registration", "login", "password_reset"})


def generate_otp_code() -> str:
    """Generate an unpredictable six-digit code, including leading zeros."""
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_otp_nonce() -> str:
    """Generate a random 16-byte nonce as 32 lowercase hex characters."""
    return secrets.token_hex(16)


def decode_otp_secret(secret_hex: str) -> bytes:
    """Decode a privately configured 32-byte secret encoded as 64 hex chars."""
    if not isinstance(secret_hex, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", secret_hex
    ):
        raise ValueError("OTP HMAC secret must be 64 hexadecimal characters.")
    return bytes.fromhex(secret_hex)


def calculate_otp_digest(
    code: str,
    *,
    nonce: str,
    secret_key: bytes,
    user_id: int,
    email_address: str,
    purpose: str,
) -> str:
    """Return a 64-character HMAC-SHA256 digest bound to this OTP context.

    A single application secret must be stored privately and remain stable
    across server restarts while outstanding OTPs need verification.
    Never use the six-digit OTP itself as the HMAC secret.
    """
    if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
        raise ValueError("OTP code must be exactly six ASCII digits.")
    if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
        raise ValueError("OTP nonce must be 32 lowercase hex characters.")
    if not isinstance(secret_key, bytes) or len(secret_key) < 32:
        raise ValueError("OTP HMAC secret must contain at least 32 bytes.")
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("OTP user_id must be a positive integer.")
    if not isinstance(email_address, str) or not email_address.strip():
        raise ValueError("OTP email address must not be blank.")
    if purpose not in _ALLOWED_PURPOSES:
        raise ValueError("Unsupported OTP purpose.")

    # JSON makes the message unambiguous even if a field contains punctuation.
    message = json.dumps(
        [
            "dormora-otp-v1",
            user_id,
            email_address.strip().casefold(),
            purpose,
            nonce,
            code,
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(secret_key, message, hashlib.sha256).hexdigest()


def verify_otp_code(
    submitted_code: str,
    *,
    stored_digest: str,
    nonce: str,
    secret_key: bytes,
    user_id: int,
    email_address: str,
    purpose: str,
) -> bool:
    """Check an OTP digest using constant-time comparison.

    This only verifies the cryptographic digest. Callers must separately
    enforce delivery status, expiration, attempt limits, one-time use,
    and database transaction safety before accepting an OTP.
    """
    if not isinstance(stored_digest, str) or not _DIGEST_RE.fullmatch(stored_digest):
        return False
    try:
        candidate = calculate_otp_digest(
            submitted_code,
            nonce=nonce,
            secret_key=secret_key,
            user_id=user_id,
            email_address=email_address,
            purpose=purpose,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(candidate, stored_digest)
