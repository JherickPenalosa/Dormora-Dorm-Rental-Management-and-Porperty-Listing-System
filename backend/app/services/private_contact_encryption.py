"""Dormora File 109: AES-256-GCM at-rest encryption of a private contact number.

CREATE: backend/app/services/private_contact_encryption.py

Commands (from backend/ with .venv active):
    python -m app.services.private_contact_encryption --check   # no writes
    python -m app.services.private_contact_encryption --setup   # creates one table

This module is NOT a FastAPI route. File 110 will authorize an existing
PostgreSQL-backed user session, then call save_private_contact() and
read_private_contact() with the authenticated user ID from the SERVER.
NEVER accept the user_id from the browser for these service calls.

Data stored: public.user_private_contacts (one OPTIONAL contact number per user).
Only random 12-byte nonce + AES-256-GCM ciphertext/tag are stored, NOT plaintext.
The authenticated user's immutable ID is additional authenticated data (AAD),
so moving an encrypted value to another user fails authentication.

Configuration: DORMORA_PRIVATE_CONTACT_AES256_KEY is a base64 encoding of
exactly 32 RANDOM bytes, supplied by process environment or backend/.env.
Keep the key stable and NEVER commit it. Without the key, ciphertext cannot
be decrypted. No fallback or hard-coded key exists.

CLI does not save real contact data, print secret key or change user accounts.
Table creation is an explicit local-development action only.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import os
import re
import secrets
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, LargeBinary, MetaData, String, Table,
    delete, func, inspect, select, text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import users_table

_TABLE = "user_private_contacts"
_KEY_NAME = "DORMORA_PRIVATE_CONTACT_AES256_KEY"
_ALGORITHM = "AES-256-GCM-v1"
_AAD_PREFIX = b"Dormora:private-contact:v1:\x00"
_PHONE = re.compile(r"\+?[0-9][0-9() .-]{5,24}\Z")
_REQUIRED_COLS = frozenset({
    "user_id", "nonce", "ciphertext", "algorithm", "created_at", "updated_at"
})


class PrivateContactUnavailable(RuntimeError):
    """Missing key, incompatible schema or authentication failure: fail closed."""


class PrivateContactRejected(ValueError):
    """A private contact number does not meet input requirements."""


def _trusted_id(value: int) -> int:
    if type(value) is not int or value < 1:
        raise PrivateContactUnavailable("A verified session user ID is required.")
    return value


def _configured_key() -> bytes:
    """Read one stable external secret; do not print, log or cache it."""
    secret = os.environ.get(_KEY_NAME)
    if not secret:
        # Other project settings read backend/.env; this NEW key need not be
        # added to Pydantic's existing, potentially strict Settings schema.
        try:
            from dotenv import dotenv_values
            env_path = Path(__file__).resolve().parents[2] / ".env"
            secret = dotenv_values(env_path).get(_KEY_NAME) if env_path.is_file() else None
        except ImportError:
            secret = None
    if not isinstance(secret, str):
        raise PrivateContactUnavailable("AES-256 contact encryption key is not configured.")
    try:
        key = base64.b64decode(secret.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise PrivateContactUnavailable("AES-256 contact encryption key is invalid.") from None
    if len(key) != 32:
        raise PrivateContactUnavailable("AES-256 contact encryption key must be 32 bytes.")
    return key


def _aad(user_id: int) -> bytes:
    _trusted_id(user_id)
    return _AAD_PREFIX + str(user_id).encode("ascii")


def _normalize_phone(raw: str) -> str:
    if not isinstance(raw, str):
        raise PrivateContactRejected("Enter a valid private contact number.")
    value = raw.strip()
    if len(value) > 26 or not _PHONE.fullmatch(value):
        raise PrivateContactRejected("Enter a valid private contact number.")
    digits = "".join(c for c in value if c.isdigit())
    if not 7 <= len(digits) <= 15:
        raise PrivateContactRejected("Enter a valid private contact number.")
    return ("+" if value.startswith("+") else "") + digits


def _encrypt(value: str, user_id: int, key: bytes) -> tuple[bytes, bytes]:
    if not isinstance(key, bytes) or len(key) != 32:
        raise PrivateContactUnavailable("Valid AES-256 key required.")
    nonce = secrets.token_bytes(12)  # Unique random nonce for every write
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), _aad(user_id))
    return nonce, ciphertext  # ciphertext contains the 16-byte authentication tag


def _decrypt(nonce: bytes, ciphertext: bytes, user_id: int, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) != 32:
        raise PrivateContactUnavailable("Valid AES-256 key required.")
    if not isinstance(nonce, bytes) or len(nonce) != 12:
        raise PrivateContactUnavailable("Stored contact encryption nonce is invalid.")
    if not isinstance(ciphertext, bytes) or len(ciphertext) < 17:
        raise PrivateContactUnavailable("Stored contact ciphertext is invalid.")
    try:
        decoded = AESGCM(key).decrypt(nonce, ciphertext, _aad(user_id))
        return decoded.decode("utf-8", errors="strict")
    except (InvalidTag, UnicodeError):
        raise PrivateContactUnavailable("Private contact could not be decrypted.") from None


def _table_definition() -> Table:
    metadata = MetaData()
    return Table(
        _TABLE, metadata,
        Column("user_id", users_table.c.user_id.type,
               ForeignKey(users_table.c.user_id, ondelete="CASCADE"),
               primary_key=True),
        Column("nonce", LargeBinary, nullable=False),
        Column("ciphertext", LargeBinary, nullable=False),
        Column("algorithm", String(32), nullable=False),
        Column("created_at", DateTime(timezone=True),
               server_default=func.clock_timestamp(), nullable=False),
        Column("updated_at", DateTime(timezone=True),
               server_default=func.clock_timestamp(), nullable=False),
        CheckConstraint("octet_length(nonce) = 12", name="ck_private_contact_nonce_length"),
        CheckConstraint("octet_length(ciphertext) > 16", name="ck_private_contact_ciphertext_length"),
        schema="public",
    )


def _existing_table(connection: Any) -> Table | None:
    inspector = inspect(connection)
    if not inspector.has_table(_TABLE, schema="public"):
        return None
    columns = {c["name"]: c for c in inspector.get_columns(_TABLE, schema="public")}
    if not _REQUIRED_COLS.issubset(columns):
        raise PrivateContactUnavailable("Private-contact schema is incompatible.")
    for column_name in ("nonce", "ciphertext"):
        if not isinstance(columns[column_name]["type"], LargeBinary):
            raise PrivateContactUnavailable("Private-contact encrypted columns must be BYTEA.")
        if columns[column_name]["nullable"]:
            raise PrivateContactUnavailable("Encrypted contact columns cannot be nullable.")
    pk = inspector.get_pk_constraint(_TABLE, schema="public")
    if set(pk.get("constrained_columns") or ()) != {"user_id"}:
        raise PrivateContactUnavailable("Private-contact user ID must be unique.")
    fks = inspector.get_foreign_keys(_TABLE, schema="public")
    if not any(
        fk.get("referred_table") == "users"
        and fk.get("referred_schema") in (None, "public")
        and fk.get("constrained_columns") == ["user_id"]
        and fk.get("referred_columns") == ["user_id"]
        for fk in fks
    ):
        raise PrivateContactUnavailable("Private-contact owner foreign key is missing.")
    return Table(_TABLE, MetaData(), schema="public", autoload_with=connection)


def _require_active_owner(db: Session, user_id: int, *, lock: bool) -> None:
    _trusted_id(user_id)
    for name in ("user_id", "account_status", "email_verified_at"):
        if name not in users_table.c:
            raise PrivateContactUnavailable("Account schema is incompatible.")
    statement = select(users_table.c.user_id).where(
        users_table.c.user_id == user_id,
        users_table.c.account_status == "active",
        users_table.c.email_verified_at.is_not(None),
    )
    if lock:
        statement = statement.with_for_update()
    if db.execute(statement).scalar_one_or_none() != user_id:
        raise PrivateContactUnavailable("Active verified account required.")


def _caller_transaction(db: Session) -> None:
    if not isinstance(db, Session) or not db.in_transaction():
        raise PrivateContactUnavailable("A caller-owned database transaction is required.")


def save_private_contact(db: Session, *, verified_session_user_id: int,
                         contact_number: str) -> None:
    """Encrypt and upsert for SESSION OWNER ONLY; caller commits/rolls back.

    The route MUST obtain verified_session_user_id from its server-validated
    PostgreSQL session, not from the submitted JSON or a URL parameter.
    """
    _caller_transaction(db)
    user_id = _trusted_id(verified_session_user_id)
    value = _normalize_phone(contact_number)
    key = _configured_key()  # fail closed before any data-changing query
    _require_active_owner(db, user_id, lock=True)
    table = _existing_table(db.connection())
    if table is None:
        raise PrivateContactUnavailable("Run File 109 --setup first.")
    nonce, ciphertext = _encrypt(value, user_id, key)
    statement = pg_insert(table).values(
        user_id=user_id, nonce=nonce, ciphertext=ciphertext, algorithm=_ALGORITHM,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.user_id],
        set_={"nonce": nonce, "ciphertext": ciphertext,
              "algorithm": _ALGORITHM, "updated_at": func.clock_timestamp()},
    )
    db.execute(statement)


def read_private_contact(db: Session, *, verified_session_user_id: int) -> str | None:
    """Decrypt ONLY for the authenticated session user; never for arbitrary IDs."""
    _caller_transaction(db)
    user_id = _trusted_id(verified_session_user_id)
    key = _configured_key()
    _require_active_owner(db, user_id, lock=False)
    table = _existing_table(db.connection())
    if table is None:
        raise PrivateContactUnavailable("Run File 109 --setup first.")
    row = db.execute(select(table.c.nonce, table.c.ciphertext, table.c.algorithm)
                     .where(table.c.user_id == user_id)).one_or_none()
    if row is None:
        return None
    if row.algorithm != _ALGORITHM:
        raise PrivateContactUnavailable("Unsupported contact encryption version.")
    return _decrypt(bytes(row.nonce), bytes(row.ciphertext), user_id, key)


def delete_private_contact(db: Session, *, verified_session_user_id: int) -> None:
    """Delete only the authenticated owner's optional contact record."""
    _caller_transaction(db)
    user_id = _trusted_id(verified_session_user_id)
    _require_active_owner(db, user_id, lock=True)
    table = _existing_table(db.connection())
    if table is None:
        raise PrivateContactUnavailable("Run File 109 --setup first.")
    db.execute(delete(table).where(table.c.user_id == user_id))


def _check_local_db() -> None:
    from app.core.config import settings
    if settings.environment != "development":
        raise PrivateContactUnavailable("Local development mode required.")
    if engine.dialect.name != "postgresql" or engine.url.database != "dormora_db":
        raise PrivateContactUnavailable("Expected PostgreSQL dormora_db.")
    host = engine.url.host or ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.casefold() == "localhost"
    if not loopback:
        raise PrivateContactUnavailable("Local PostgreSQL only.")
    if "user_id" not in users_table.c:
        raise PrivateContactUnavailable("User table needs an immutable user_id.")


def _crypto_self_check() -> None:
    """Use an EPHEMERAL key. Never print/commit a real encryption key."""
    demo_key = secrets.token_bytes(32)
    sample = "+639171234567"
    nonce1, encrypted1 = _encrypt(sample, 101, demo_key)
    nonce2, encrypted2 = _encrypt(sample, 101, demo_key)
    if (nonce1 == nonce2 or encrypted1 == encrypted2 or sample.encode() in encrypted1
            or _decrypt(nonce1, encrypted1, 101, demo_key) != sample):
        raise PrivateContactUnavailable("AES-256-GCM self-test failed.")
    for nonce, ciphertext, wrong_user in (
        (nonce1, encrypted1, 202),
        (nonce1, encrypted1[:-1] + bytes([encrypted1[-1] ^ 1]), 101),
    ):
        try:
            _decrypt(nonce, ciphertext, wrong_user, demo_key)
        except PrivateContactUnavailable:
            continue
        raise PrivateContactUnavailable("Encryption owner-binding/tamper test failed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dormora File 109 encrypted private contact")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only readiness check")
    mode.add_argument("--setup", action="store_true", help="create optional encrypted field table")
    args = parser.parse_args()
    try:
        _check_local_db()
        _crypto_self_check()
        if args.setup:
            _configured_key()  # never set up storage with a missing/bad secret
            with engine.begin() as conn:
                table = _existing_table(conn)
                if table is None:
                    _table_definition().create(bind=conn, checkfirst=False)
                    table = _existing_table(conn)
                if table is None:
                    raise PrivateContactUnavailable("Contact table creation not confirmed.")
        else:
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                    table = _existing_table(conn)
        try:
            _configured_key()
            key_ready = True
        except PrivateContactUnavailable:
            key_ready = False
        print("DORMORA FILE 109 -- AES-256-GCM ENCRYPTION AT REST")
        print("Crypto round-trip, random nonce, owner-binding and tamper: PASS")
        print("Storage table:", "PRESENT" if table is not None else "MISSING")
        print("Stable AES-256 key:", "CONFIGURED" if key_ready else "MISSING OR INVALID")
        print("No account or private contact was changed by this command.")
        print("File 109", "setup OK" if args.setup else "check OK")
    except PrivateContactUnavailable as error:
        print("FILE 109 STOPPED:", error)
        raise SystemExit(1) from None
    except Exception as error:
        print("FILE 109 FAILED:", type(error).__name__)
        print("Check the local PostgreSQL schema and encryption configuration.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
