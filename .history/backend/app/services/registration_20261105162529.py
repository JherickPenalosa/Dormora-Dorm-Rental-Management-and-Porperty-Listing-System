
"""Atomic, role-aware registration persistence for Dormora (Backend File 52).

Destination: backend/app/services/registration.py (REPLACE Backend File 42).

Uses existing public.users, user_profiles, renter_preferences,
property_owner_details, security_questions, user_security_answers and
security_logs. No migrations, new tables, OTP delivery or public routes.

This function is intentionally FAIL-CLOSED: the legacy RegisterRequest is no
longer accepted for database inserts. Only HandoutRegisterRequest, containing
valid privacy consent and three required security answers, is accepted.

One transaction creates the pending account/profile/role row, saves exactly
four validated role-specific fields in the correct existing role table, stores
three salted Argon2id answer hashes, and records the consent time as the
database-generated created_at of a PRIVACY_CONSENT_GRANTED log event.

The security question catalog must contain the student's three assigned
questions (Q7, Q2, Q4), with is_active = TRUE. No question rows are invented.
Before public activation: confirm these provisional four-field rules against
the signed proposal, publish the actual Privacy Notice, integrate the approved
CAPTCHA/CSRF checks, and ensure registration logs contain trusted IP and user
agent. Account creation here does not issue or deliver OTP.

The earlier schema design uses user_id as the users primary key and keeps
id_number unique in user_profiles. Confirm instructor approval of this
difference from the handout's ID-as-primary-key instruction.
"""

import ipaddress
import re
from dataclasses import dataclass

from sqlalchemy import Table, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.database import SessionLocal, engine
from app.models.user import users_table
from app.schemas.auth import HandoutRegisterRequest


# Reflect existing tables; let PostgreSQL's actual types/constraints govern.
user_profiles_table = Table(
    "user_profiles", users_table.metadata, schema="public", autoload_with=engine
)
renter_preferences_table = Table(
    "renter_preferences", users_table.metadata, schema="public", autoload_with=engine
)
property_owner_details_table = Table(
    "property_owner_details", users_table.metadata, schema="public", autoload_with=engine
)
security_questions_table = Table(
    "security_questions", users_table.metadata, schema="public", autoload_with=engine
)
user_security_answers_table = Table(
    "user_security_answers", users_table.metadata, schema="public", autoload_with=engine
)
security_logs_table = Table(
    "security_logs", users_table.metadata, schema="public", autoload_with=engine
)

# Actual question IDs are database-generated; never assume Q7 has question_id=7.
# Match against the seeded question text, then use the REAL question_id.
ASSIGNED_QUESTIONS = (
    ("Q7", "security_answer_1", "What was the name of your elementary school?"),
    ("Q2", "security_answer_2", "Who was your best friend in elementary school?"),
    ("Q4", "security_answer_3", "What is your mother's maiden first name?"),
)


# Explicit allowlist. No browser-supplied column/table name is ever used.
_ROLE_SPECIFIC_FIELDS = {
    "renter": frozenset({
        "preferred_rental_type", "preferred_rental_area",
        "maximum_monthly_budget", "target_move_in_date",
    }),
    "property_owner": frozenset({
        "primary_property_type", "primary_property_area",
        "expected_monthly_rent", "expected_availability_date",
    }),
}


class DuplicateRegistrationError(Exception):
    """A username, email, or profile ID number is already registered."""


class RegistrationConfigurationError(Exception):
    """A required seeded security question is missing or ambiguous."""


@dataclass(frozen=True)
class RegistrationResult:
    """Non-secret account summary, pending email verification."""

    user_id: int
    username: str
    email: str
    role: str
    account_status: str


def _normalize_question_text(value: str) -> str:
    """Match smart/straight apostrophes and punctuation-free text safely."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _assigned_question_ids(session) -> dict[str, int]:
    """Resolve Q7, Q2, Q4 to real active question IDs; raise if unavailable."""
    candidates = session.execute(
        select(
            security_questions_table.c.question_id,
            security_questions_table.c.question_text,
        ).where(security_questions_table.c.is_active.is_(True))
    ).all()
    lookup: dict[str, list[int]] = {}
    for question_id, text_value in candidates:
        normalized = _normalize_question_text(str(text_value))
        lookup.setdefault(normalized, []).append(int(question_id))

    result: dict[str, int] = {}
    for label, answer_attribute, question_text in ASSIGNED_QUESTIONS:
        matches = lookup.get(_normalize_question_text(question_text), [])
        if len(matches) != 1:
            raise RegistrationConfigurationError(
                f"Required active authentication question {label} "
                "is missing or duplicated. Seed or review security_questions "
                "before enabling public registration."
            )
        result[answer_attribute] = matches[0]
    return result


def inspect_assigned_question_readiness() -> dict[str, bool]:
    """Read-only check for Q7/Q2/Q4. No account or answer rows are read."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                security_questions_table.c.question_text,
                security_questions_table.c.is_active,
            )
        ).all()
    active_texts = [
        _normalize_question_text(str(question_text))
        for question_text, active in rows
        if active
    ]
    return {
        label: active_texts.count(_normalize_question_text(question_text)) == 1
        for label, _attribute, question_text in ASSIGNED_QUESTIONS
    }


def _role_insert_values(payload: HandoutRegisterRequest) -> tuple[Table, dict]:
    """Build a safe role-row INSERT from File 51's validated fields.

    The table choice and column allowlist are fixed by server code. Any
    unexpected schema/mapping mismatch fails BEFORE creating the user.
    """
    if payload.role == "renter":
        table = renter_preferences_table
    elif payload.role == "property_owner":
        table = property_owner_details_table
    else:
        raise RegistrationConfigurationError("Unsupported registration role.")

    values = payload.role_specific_db_values()
    expected = _ROLE_SPECIFIC_FIELDS[payload.role]
    if (
        payload.target_table != table.name
        or set(values) != expected
        or not expected.issubset(table.c.keys())
    ):
        raise RegistrationConfigurationError(
            "Role-specific registration fields do not match database schema."
        )
    return table, values


def _clean_context(
    client_ip: str | None, user_agent: str | None
) -> dict[str, str | None]:
    """Validate caller-supplied trusted network context; no forwarding-header parsing."""
    normalized_ip: str | None = None
    if client_ip is not None:
        if not isinstance(client_ip, str):
            raise ValueError("client_ip must be a trusted IPv4 or IPv6 address.")
        try:
            normalized_ip = str(ipaddress.ip_address(client_ip))
        except ValueError:
            raise ValueError("client_ip must be a trusted IPv4 or IPv6 address.") from None
    if user_agent is not None:
        if (
            not isinstance(user_agent, str)
            or len(user_agent) > 512
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in user_agent)
        ):
            raise ValueError("Invalid browser user agent.")
    return {"ip_address": normalized_ip, "user_agent": user_agent}


def register_user(
    payload: HandoutRegisterRequest,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> RegistrationResult:
    """Persist strict registration, role fields, answer hashes and consent atomically.

    All eight INSERTs occur within one PostgreSQL transaction; any failure
    rolls back the new user, profile, role details, three answers and two
    audit events together. No email is sent here. File 44 issues and sends
    the OTP only AFTER this function has successfully committed.

    Registration is NOT publicly mounted yet. Future router must use the
    strictly validated HandoutRegisterRequest and pass a trusted client_ip.
    """
    if not isinstance(payload, HandoutRegisterRequest):
        raise TypeError("Strict HandoutRegisterRequest is required for registration.")
    if payload.privacy_consent is not True:
        raise ValueError("Privacy consent is required.")

    context = _clean_context(client_ip, user_agent)
    # Determine the role table and validate its four fields before account
    # creation. We accept only the strict request model from File 51.
    role_table, role_values = _role_insert_values(payload)

    # Hash before acquiring the transaction; answers are normalized to lower
    # case so answer comparison can later use the same normalization.
    password_hash = hash_password(payload.password.get_secret_value())
    answer_hashes = {
        answer_attribute: hash_password(
            getattr(payload, answer_attribute).get_secret_value().casefold()
        )
        for _label, answer_attribute, _text in ASSIGNED_QUESTIONS
    }

    try:
        with SessionLocal.begin() as session:
            # No users created if the question bank hasn't been populated.
            question_ids = _assigned_question_ids(session)

            user_id = session.execute(
                insert(users_table).values(
                    username=payload.username,
                    email=str(payload.email),
                    password_hash=password_hash,
                    role=payload.role,
                    account_status="pending_verification",
                ).returning(users_table.c.user_id)
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

            # File 51 has already validated the four fields. Save them in
            # the SAME transaction, instead of inserting only user_id.
            # Optional fields remain NULL if the user left them blank.
            session.execute(
                insert(role_table).values(user_id=user_id, **role_values)
            )

            for _label, answer_attribute, _text in ASSIGNED_QUESTIONS:
                session.execute(
                    insert(user_security_answers_table).values(
                        user_id=user_id,
                        question_id=question_ids[answer_attribute],
                        answer_hash=answer_hashes[answer_attribute],
                    )
                )

            # PostgreSQL's created_at default is the consent timestamp.
            # This is in the SAME transaction as the registration inserts.
            # Never store plaintext answers, passwords or OTP codes in JSON.
            session.execute(
                insert(security_logs_table).values(
                    user_id=user_id,
                    event_type="PRIVACY_CONSENT_GRANTED",
                    outcome="success",
                    event_details={
                        "consent": True,
                        "source": "registration_checkbox",
                    },
                    **context,
                )
            )
            session.execute(
                insert(security_logs_table).values(
                    user_id=user_id,
                    event_type="REGISTERED",
                    outcome="info",
                    event_details={"channel": "web"},
                    **context,
                )
            )
    except IntegrityError as exc:
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
