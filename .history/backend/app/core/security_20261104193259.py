
"""Password hashing helpers for Dormora.

Backend File 10: backend/app/core/security.py

Uses Argon2id with a unique random salt for every password. This module
never stores passwords or interacts with the database.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type


# Fixed parameters keep hashing behavior predictable across library upgrades.
# memory_cost is measured in KiB (65,536 KiB = 64 MiB).
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Return a salted Argon2id hash for a validated plaintext password.

    Registration validation happens in app.schemas.auth.RegisterRequest.
    Never log the input password or the returned hash.
    """
    if not isinstance(password, str):
        raise TypeError("Password must be a string.")
    if not password:
        raise ValueError("Password must not be empty.")

    return _password_hasher.hash(password)


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Return True only when the password matches a valid stored hash.

    A wrong password or malformed hash safely returns False. The login
    endpoint will later handle rate limiting and failed-attempt tracking.
    """
    if not isinstance(plain_password, str) or not isinstance(stored_hash, str):
        return False

    try:
        return _password_hasher.verify(stored_hash, plain_password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    """Check whether a valid hash uses outdated Argon2 parameters.

    Use after a successful login to decide whether to replace an old hash.
    Invalid hashes are treated as needing replacement; never accept them.
    """
    if not isinstance(stored_hash, str):
        return True

    try:
        return _password_hasher.check_needs_rehash(stored_hash)
    except (VerificationError, InvalidHashError):
        return True
