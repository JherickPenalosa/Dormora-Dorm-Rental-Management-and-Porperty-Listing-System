
"""Atomic registration database service for Dormora.

Backend File 13: backend/app/services/registration.py

Uses the existing PostgreSQL tables without creating or altering their schema.
This service does NOT send an email or activate accounts; OTP verification is
implemented in a later file. Do not expose it through a public endpoint until
required registration security controls are added.
"""

from dataclasses import dataclass

from sqlalchemy import Table, insert
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.database import SessionLocal, engine
from app.models.user import users_table
from app.schemas.auth import RegisterRequest


# Reflect the existing registration-related tables into the metadata already
# used by the User mapping. All column types and constraints come from PostgreSQL.
user_profiles_table = Table(
    "user_profiles", users_table.metadata, schema="public", autoload_with=engine
)
renter_preferences_table = Table(
    "renter_preferences", users_table.metadata, schema="public", autoload_with=engine
)
property_owner_details_table = Table(
    "property_owner_details", users_table.metadata, schema="public", autoload_with=engine
)


class DuplicateRegistrationError(Exception):
    """A username, email, or ID number conflicts with an existing record."""


@dataclass(frozen=True)
class RegistrationResult:
    """Safe summary of a newly registered but unverified account."""

    user_id: int
    username: str
    email: str
    role: str
    account_status: str


def register_user(payload: RegisterRequest) -> RegistrationResult:
    """Create an account, profile, and matching role record atomically.

    A valid RegisterRequest is required. Password hashing happens before the
    transaction; no plaintext password is inserted into PostgreSQL.

    The SessionLocal.begin() context commits only after all three INSERTs
    succeed and rolls everything back if any INSERT fails.

    PostgreSQL unique indexes are the final authority for duplicates, including
    case-insensitive username/email uniqueness and unique profile ID numbers.
    """
    password_digest = hash_password(payload.password.get_secret_value())

    try:
        with SessionLocal.begin() as session:
            user_id = session.execute(
                insert(users_table)
                .values(
                    username=payload.username,
                    email=str(payload.email),
                    password_hash=password_digest,
                    role=payload.role,
                    account_status="pending_verification",
                )
                .returning(users_table.c.user_id)
            ).scalar_one()

            session.execute(
                insert(user_profiles_table).values(
                    user_id=user_id,
                    id_number=payload.id_number,
                    first_name=payload.first_name,
                    middle_name=payload.middle_name,
                    family_name=payload.family_name,
                    name_extension=payload.name_extension,
                    other_extension=payload.other_extension,
                    birthdate=payload.birthdate,
                    street=payload.street,
                    barangay=payload.barangay,
                    city=payload.city,
                    province=payload.province,
                    country=payload.country,
                    zip_code=payload.zip_code,
                )
            )

            # The role-specific fields are optional in the existing schema,
            # so a record with user_id alone is valid at this stage.
            role_table = (
                renter_preferences_table
                if payload.role == "renter"
                else property_owner_details_table
            )
            session.execute(insert(role_table).values(user_id=user_id))

    except IntegrityError as exc:
        # PostgreSQL's unique_violation SQLSTATE. Do not send raw SQL/database
        # exception text (which can include private input) to API clients.
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DuplicateRegistrationError(
                "Username, email, or ID number is already registered."
            ) from None
        raise

    return RegistrationResult(
        user_id=int(user_id),
        username=payload.username,
        email=str(payload.email),
        role=payload.role,
        account_status="pending_verification",
    )
