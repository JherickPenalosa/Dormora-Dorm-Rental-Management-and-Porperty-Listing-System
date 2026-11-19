
"""Dormora Requirement Validation File 3 — registration persistence.

REPLACE: backend/app/services/registration.py

Preserves atomic, role-aware registration, private Argon2id answer hashes,
privacy-consent logging, and the existing OTP workflow. Adds support for
three user-selected, distinct official Q1–Q8 security questions.

TRANSITION: Until the next schema/frontend files declare
security_question_1/2/3, preserve the existing Q7/Q2/Q4 registration contract.
Once all three selection fields are declared on HandoutRegisterRequest,
registration REQUIRES valid, distinct choices and cannot silently fall back.
No tables, existing account records, OTP delivery, or routes are modified.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from sqlalchemy import Table, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.database import SessionLocal, engine
from app.models.user import users_table
from app.schemas.auth import HandoutRegisterRequest


# Reflect existing tables; PostgreSQL remains the source of schema truth.
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


# These are official QUESTION LABELS, not database-generated question_id values.
QUESTION_BANK: tuple[tuple[str, str], ...] = (
    ("Q1", "What was the name of your first pet?"),
    ("Q2", "Who was your best friend in elementary school?"),
    ("Q3", "Who was your favorite teacher in high school?"),
    ("Q4", "What is your mother's maiden first name?"),
    ("Q5", "What street did you live on in Grade 1?"),
    ("Q6", "What was the first song you learned by heart?"),
    ("Q7", "What was the name of your elementary school?"),
    ("Q8", "What dish did you cook for the first time?"),
)
_QUESTION_TEXT_BY_CODE = dict(QUESTION_BANK)
_QUESTION_FIELDS = (
    "security_question_1",
    "security_question_2",
    "security_question_3",
)
_ANSWER_FIELDS = (
    "security_answer_1",
    "security_answer_2",
    "security_answer_3",
)
_LEGACY_QUESTION_CODES = ("Q7", "Q2", "Q4")

# Keep the old module-level interface for any existing readiness checks.
ASSIGNED_QUESTIONS = (
    ("Q7", "security_answer_1", _QUESTION_TEXT_BY_CODE["Q7"]),
    ("Q2", "security_answer_2", _QUESTION_TEXT_BY_CODE["Q2"]),
    ("Q4", "security_answer_3", _QUESTION_TEXT_BY_CODE["Q4"]),
)

# Server-owned table/column allowlist. Never use user input as a SQL identifier.
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
    """A username, email, or profile ID is already registered."""


class RegistrationConfigurationError(Exception):
    """Required question catalog or registration configuration is invalid."""


@dataclass(frozen=True)
class RegistrationResult:
    """Non-secret registration result, pending email verification."""

    user_id: int
    username: str
    email: str
    role: str
    account_status: str


def _normalize_question_text(value: str) -> str:
    """Compare official text independent of punctuation and apostrophe style."""

    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _question_labels_for_payload(
    payload: HandoutRegisterRequest,
) -> tuple[str, str, str]:
    """Accept new 3-choice schema, retaining old fixed fields temporarily.

    The next schema file will declare all three security_question_N fields.
    As soon as it does, choices become mandatory and no legacy fallback exists.
    """

    declared = tuple(name in type(payload).model_fields for name in _QUESTION_FIELDS)
    if any(declared) and not all(declared):
        raise RegistrationConfigurationError(
            "Registration schema must define all three question selectors."
        )

    if all(declared):
        raw_labels = tuple(getattr(payload, name) for name in _QUESTION_FIELDS)
    else:
        # Temporary compatibility with existing Q7/Q2/Q4 registration UI.
        raw_labels = _LEGACY_QUESTION_CODES

    if (
        len(raw_labels) != 3
        or any(type(code) is not str or code not in _QUESTION_TEXT_BY_CODE
               for code in raw_labels)
        or len(set(raw_labels)) != 3
    ):
        raise ValueError("Select three different questions from Q1 through Q8.")

    return raw_labels  # type: ignore[return-value]


def _question_ids_for_labels(session, labels: tuple[str, str, str]) -> dict[str, int]:
    """Resolve selected official texts to unique ACTIVE database question IDs."""

    rows = session.execute(
        select(
            security_questions_table.c.question_id,
            security_questions_table.c.question_text,
        ).where(security_questions_table.c.is_active.is_(True))
    ).all()

    lookup: dict[str, list[int]] = {}
    for question_id, question_text in rows:
        normalized = _normalize_question_text(str(question_text))
        lookup.setdefault(normalized, []).append(int(question_id))

    question_ids: dict[str, int] = {}
    for attribute, code in zip(_ANSWER_FIELDS, labels):
        matches = lookup.get(
            _normalize_question_text(_QUESTION_TEXT_BY_CODE[code]), []
        )
        if len(matches) != 1:
            raise RegistrationConfigurationError(
                f"Question {code} is missing, inactive, or duplicated in "
                "the official database catalog."
            )
        question_ids[attribute] = matches[0]

    if len(set(question_ids.values())) != 3:
        raise RegistrationConfigurationError(
            "Selected questions must resolve to three distinct database records."
        )
    return question_ids


def _assigned_question_ids(session) -> dict[str, int]:
    """Backward-compatible Q7/Q2/Q4 resolver for existing internal callers."""

    return _question_ids_for_labels(session, _LEGACY_QUESTION_CODES)


def inspect_assigned_question_readiness() -> dict[str, bool]:
    """Keep legacy read-only Q7/Q2/Q4 readiness check unchanged in meaning."""

    with SessionLocal() as session:
        rows = session.execute(
            select(
                security_questions_table.c.question_text,
                security_questions_table.c.is_active,
            )
        ).all()

    active_texts = [
        _normalize_question_text(str(question_text))
        for question_text, active in rows if active
    ]
    return {
        label: active_texts.count(_normalize_question_text(question_text)) == 1
        for label, _attribute, question_text in ASSIGNED_QUESTIONS
    }


def _role_insert_values(payload: HandoutRegisterRequest) -> tuple[Table, dict]:
    """Build role-specific INSERT from four validated, server-allowlisted fields."""

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


def _clean_context(client_ip: str | None, user_agent: str | None) -> dict:
    """Validate network metadata supplied by the trusted HTTP layer."""

    normalized_ip: str | None = None
    if client_ip is not None:
        if not isinstance(client_ip, str):
            raise ValueError("client_ip must be a trusted IPv4 or IPv6 address.")
        try:
            normalized_ip = str(ipaddress.ip_address(client_ip))
        except ValueError:
            raise ValueError(
                "client_ip must be a trusted IPv4 or IPv6 address."
            ) from None

    if user_agent is not None and (
        not isinstance(user_agent, str)
        or len(user_agent) > 512
        or any(ord(character) < 32 or ord(character) == 127
               for character in user_agent)
    ):
        raise ValueError("Invalid browser user agent.")

    return {"ip_address": normalized_ip, "user_agent": user_agent}


def register_user(
    payload: HandoutRegisterRequest,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> RegistrationResult:
    """Create pending user, profile, role details, 3 answer hashes and logs.

    All inserts share one transaction, so any error rolls back all changes.
    No OTP is sent here; the existing workflow handles email verification.
    """

    if not isinstance(payload, HandoutRegisterRequest):
        raise TypeError("Strict HandoutRegisterRequest is required for registration.")
    if payload.privacy_consent is not True:
        raise ValueError("Privacy consent is required.")

    # Select and validate question codes before beginning any database writes.
    selected_labels = _question_labels_for_payload(payload)
    context = _clean_context(client_ip, user_agent)
    role_table, role_values = _role_insert_values(payload)

    # Hash before acquiring the DB transaction; never store plaintext answers.
    password_hash = hash_password(payload.password.get_secret_value())
    answer_hashes = {
        attribute: hash_password(
            getattr(payload, attribute).get_secret_value().casefold()
        )
        for attribute in _ANSWER_FIELDS
    }

    try:
        with SessionLocal.begin() as session:
            # Check all three selected questions before inserting anything.
            question_ids = _question_ids_for_labels(session, selected_labels)

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

            session.execute(
                insert(role_table).values(user_id=user_id, **role_values)
            )

            for attribute in _ANSWER_FIELDS:
                session.execute(
                    insert(user_security_answers_table).values(
                        user_id=user_id,
                        question_id=question_ids[attribute],
                        answer_hash=answer_hashes[attribute],
                    )
                )

            # PostgreSQL created_at is the privacy-consent event timestamp.
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
