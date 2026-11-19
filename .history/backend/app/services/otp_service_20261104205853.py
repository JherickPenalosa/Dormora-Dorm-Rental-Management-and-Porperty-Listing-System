
"""Registration email OTP lifecycle for Dormora's existing PostgreSQL schema.

Backend File 19 -- install as backend/app/services/otp_service.py.

This module prepares a registration OTP, records the email sender's result,
and verifies a delivered code. Verification consumes the OTP and activates
its pending user in ONE database transaction. It never creates or alters tables.

Do not expose these functions through public routes until email delivery,
request throttling, CAPTCHA, and relevant security logging are integrated.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Table, func, insert, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.otp_security import (
    calculate_otp_digest,
    generate_otp_code,
    generate_otp_nonce,
    verify_otp_code,
)
from app.db.database import SessionLocal, engine
from app.models.user import users_table


# Reflect the table already present in public schema; do not recreate it.
email_otps_table = Table(
    "email_otps",
    users_table.metadata,
    schema="public",
    autoload_with=engine,
)


class OtpAccountNotEligibleError(Exception):
    """The account is missing or is not pending registration verification."""


@dataclass(frozen=True)
class IssuedRegistrationOtp:
    """One code awaiting email delivery; keep code and address out of logs."""

    otp_id: int
    expires_at: datetime
    code: str = field(repr=False)
    email_address: str = field(repr=False)


def _get_pending_user_email(session: Session, user_id: int) -> str | None:
    """Lock the user row to serialize issue/verify operations for this user."""
    user = session.execute(
        select(users_table.c.email, users_table.c.account_status)
        .where(users_table.c.user_id == user_id)
        .with_for_update()
    ).one_or_none()

    if user is None or user.account_status != "pending_verification":
        return None
    return str(user.email).strip().casefold()


def issue_registration_otp(user_id: int) -> IssuedRegistrationOtp:
    """Create a pending OTP, invalidating older unconsumed registration OTPs.

    The code is returned only in memory for a future trusted email sender.
    The database stores only its random nonce and keyed digest.
    PostgreSQL supplies the 10-minute expiry and five-attempt default.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    secret_key = settings.require_otp_hmac_key()

    with SessionLocal.begin() as session:
        email_address = _get_pending_user_email(session, user_id)
        if not email_address:
            raise OtpAccountNotEligibleError(
                "Account is not eligible for registration verification."
            )

        # User-row lock prevents concurrent issuance/verification from
        # accidentally leaving an earlier code active.
        session.execute(
            update(email_otps_table)
            .where(
                email_otps_table.c.user_id == user_id,
                email_otps_table.c.purpose == "registration",
                email_otps_table.c.consumed_at.is_(None),
                email_otps_table.c.invalidated_at.is_(None),
            )
            .values(invalidated_at=func.localtimestamp())
        )

        code = generate_otp_code()
        nonce = generate_otp_nonce()
        digest = calculate_otp_digest(
            code,
            nonce=nonce,
            secret_key=secret_key,
            user_id=user_id,
            email_address=email_address,
            purpose="registration",
        )

        otp_id, expires_at = session.execute(
            insert(email_otps_table)
            .values(
                user_id=user_id,
                email_address=email_address,
                purpose="registration",
                code_nonce=nonce,
                code_digest=digest,
                delivery_status="pending",
            )
            .returning(email_otps_table.c.otp_id, email_otps_table.c.expires_at)
        ).one()

    return IssuedRegistrationOtp(
        otp_id=int(otp_id),
        expires_at=expires_at,
        code=code,
        email_address=email_address,
    )


def mark_otp_sent(otp_id: int) -> bool:
    """Mark a pending, unexpired OTP sent AFTER email-provider acceptance."""
    if type(otp_id) is not int or otp_id <= 0:
        return False

    with SessionLocal.begin() as session:
        updated_id = session.execute(
            update(email_otps_table)
            .where(
                email_otps_table.c.otp_id == otp_id,
                email_otps_table.c.delivery_status == "pending",
                email_otps_table.c.consumed_at.is_(None),
                email_otps_table.c.invalidated_at.is_(None),
                email_otps_table.c.expires_at > func.localtimestamp(),
            )
            .values(delivery_status="sent", sent_at=func.localtimestamp())
            .returning(email_otps_table.c.otp_id)
        ).scalar_one_or_none()
    return updated_id is not None


def mark_otp_failed(otp_id: int) -> bool:
    """Record an unsuccessful send and invalidate the undelivered OTP."""
    if type(otp_id) is not int or otp_id <= 0:
        return False

    with SessionLocal.begin() as session:
        updated_id = session.execute(
            update(email_otps_table)
            .where(
                email_otps_table.c.otp_id == otp_id,
                email_otps_table.c.delivery_status == "pending",
                email_otps_table.c.consumed_at.is_(None),
                email_otps_table.c.invalidated_at.is_(None),
            )
            .values(delivery_status="failed", invalidated_at=func.localtimestamp())
            .returning(email_otps_table.c.otp_id)
        ).scalar_one_or_none()
    return updated_id is not None


def verify_registration_otp(user_id: int, submitted_code: str) -> bool:
    """Consume a valid delivered code AND activate its user atomically.

    Incorrect attempts are committed and the fifth failure invalidates the
    code. Expired, pending, failed, consumed, or invalidated codes never pass.
    The latest OTP takes precedence, so resending disables older codes.
    This is an internal service; public endpoints still need rate limiting,
    CAPTCHA where required, and safe error responses.
    """
    if type(user_id) is not int or user_id <= 0:
        return False

    secret_key = settings.require_otp_hmac_key()

    with SessionLocal.begin() as session:
        email_address = _get_pending_user_email(session, user_id)
        if not email_address:
            return False

        # Lock the latest code so concurrent attempts cannot bypass limits
        # or consume the same code twice.
        otp = session.execute(
            select(email_otps_table)
            .where(
                email_otps_table.c.user_id == user_id,
                email_otps_table.c.purpose == "registration",
            )
            .order_by(
                email_otps_table.c.created_at.desc(),
                email_otps_table.c.otp_id.desc(),
            )
            .limit(1)
            .with_for_update()
        ).mappings().first()

        if otp is None:
            return False
        if (
            otp["delivery_status"] != "sent"
            or otp["consumed_at"] is not None
            or otp["invalidated_at"] is not None
            or otp["attempt_count"] >= otp["max_attempts"]
            or str(otp["email_address"]).strip().casefold() != email_address
        ):
            return False

        # PostgreSQL columns are TIMESTAMP WITHOUT TIME ZONE, so compare
        # against the database's own local timestamp, not the PC clock.
        database_now = session.execute(select(func.localtimestamp())).scalar_one()
        if otp["expires_at"] <= database_now:
            session.execute(
                update(email_otps_table)
                .where(email_otps_table.c.otp_id == otp["otp_id"])
                .values(invalidated_at=func.localtimestamp())
            )
            return False

        is_correct = verify_otp_code(
            submitted_code,
            stored_digest=otp["code_digest"],
            nonce=otp["code_nonce"],
            secret_key=secret_key,
            user_id=user_id,
            email_address=email_address,
            purpose="registration",
        )

        if not is_correct:
            next_attempt = otp["attempt_count"] + 1
            changes = {"attempt_count": next_attempt}
            if next_attempt >= otp["max_attempts"]:
                changes["invalidated_at"] = func.localtimestamp()
            session.execute(
                update(email_otps_table)
                .where(email_otps_table.c.otp_id == otp["otp_id"])
                .values(**changes)
            )
            return False

        # Verification and account activation share one transaction.
        # If either update fails, BOTH are rolled back.
        session.execute(
            update(email_otps_table)
            .where(email_otps_table.c.otp_id == otp["otp_id"])
            .values(consumed_at=func.localtimestamp())
        )
        updated_user_id = session.execute(
            update(users_table)
            .where(
                users_table.c.user_id == user_id,
                users_table.c.account_status == "pending_verification",
            )
            .values(
                account_status="active",
                email_verified_at=func.localtimestamp(),
                updated_at=func.localtimestamp(),
            )
            .returning(users_table.c.user_id)
        ).scalar_one_or_none()
        if updated_user_id is None:
            raise RuntimeError("Registration activation could not be completed.")

    return True
