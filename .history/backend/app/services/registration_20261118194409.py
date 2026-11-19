
"""Dormora Requirement Validation — File 15: encrypted registration contact.

REPLACE: backend/app/services/registration.py

Keep the existing atomic account/profile/role/question/audit transaction,
Argon2id password and answer hashing, and the pending email-OTP workflow.

Identify the exact PostgreSQL unique constraint/index when available, including
the verified LOWER(username/email) case-insensitive expression indexes, so the
registration API can distinguish username, email and ID number without any
account-existence query. No schema changes.

When File 14 supplies an optional contact_number, File 13 encrypts and
persists it in the SAME account-creation transaction. Without a contact number,
the existing registration behavior remains unchanged. The contact never enters
profile plaintext fields, security logs, or a public API response.

The registration API's OTP workflow remains unchanged and starts only after
the entire account-creation transaction commits. No database schema change.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from sqlalchemy import Table, UniqueConstraint, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.database import SessionLocal, engine
from app.models.user import users_table
from app.schemas.auth import HandoutRegisterRequest
from app.services.private_contact_encryption import save_pending_registration_contact


# Reflect the real PostgreSQL schema; never assume a migration was applied.
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
    "security_question_1", "security_question_2", "security_question_3",
)
_ANSWER_FIELDS = (
    "security_answer_1", "security_answer_2", "security_answer_3",
)
_LEGACY_QUESTION_CODES = ("Q7", "Q2", "Q4")

# Keep old module-level interface for existing read-only readiness checks.
ASSIGNED_QUESTIONS = (
    ("Q7", "security_answer_1", _QUESTION_TEXT_BY_CODE["Q7"]),
    ("Q2", "security_answer_2", _QUESTION_TEXT_BY_CODE["Q2"]),
    ("Q4", "security_answer_3", _QUESTION_TEXT_BY_CODE["Q4"]),
)

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

# PostgreSQL unique indexes/constraints—not a pre-registration account lookup—
# are the authority. Only these three fields receive specific duplicate labels.
_UNIQUE_REGISTRATION_FIELDS = (
    (users_table, "username", "username"),
    (users_table, "email", "email"),
    (user_profiles_table, "id_number", "id_number"),
)

# Confirmed by the read-only pg_indexes query on Dormora's real database.
# These are PostgreSQL expression indexes (LOWER(username/email)), so their
# reflected SQLAlchemy Index.columns may not be a single plain column.
# Match only their exact trusted names, table and PostgreSQL error code 23505.
_CASE_INSENSITIVE_INDEXES = {
    ("users", "users_username_case_insensitive_uq"): "username",
    ("users", "users_email_case_insensitive_uq"): "email",
}

_DUPLICATE_MESSAGES = {
    "username": "This username already exists.",
    "email": "This email is already used.",
    "id_number": "This ID number already exists.",
}
_GENERIC_DUPLICATE_MESSAGE = "Username, email, or ID number is already registered."


class DuplicateRegistrationError(Exception):
    """A unique registration value conflicts with a database constraint.

    field is server-internal, known only when PostgreSQL identifies a
    verified unique index/constraint for one of the three allowed columns.
    File 11 uses the recognized field for its allowlisted 409 response;
    an unrecognized constraint remains a generic duplicate error.
    """

    def __init__(self, field: str | None = None) -> None:
        self.field = field if field in _DUPLICATE_MESSAGES else None
        super().__init__(
            _DUPLICATE_MESSAGES[self.field]
            if self.field is not None else _GENERIC_DUPLICATE_MESSAGE
        )


class RegistrationConfigurationError(Exception):
    """Required official question catalog or registration config is invalid."""


@dataclass(frozen=True)
class RegistrationResult:
    """Non-secret pending-registration result; not a login session."""

    user_id: int
    username: str
    email: str
    role: str
    account_status: str


def _duplicate_field_from_integrity_error(error: IntegrityError) -> str | None:
    """Map PostgreSQL 23505 to a trusted unique column, if identifiable.

    Never parse PostgreSQL's human-readable exception message: it can include
    submitted PII and is not stable. Compare the driver's diagnostic constraint
    name with the exact verified case-insensitive index names, or with
    constraints/indexes reflected from the existing database schema.
    Unknown or compound uniqueness violations receive a generic error.
    """
    original = getattr(error, "orig", None)
    code = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if code != "23505":
        return None

    diagnostic = getattr(original, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    table_name = getattr(diagnostic, "table_name", None)
    schema_name = getattr(diagnostic, "schema_name", None)
    if not isinstance(name, str) or not name or schema_name not in (None, "public"):
        return None

    # Verified case-insensitive expression indexes on public.users.
    for (allowed_table, allowed_index), field in _CASE_INSENSITIVE_INDEXES.items():
        if name == allowed_index and table_name in (None, allowed_table):
            return field

    # Preserve the existing single-column constraint/index mapping, including
    # user_profiles_id_number_key on public.user_profiles.id_number.
    for table, column_name, field in _UNIQUE_REGISTRATION_FIELDS:
        if table_name not in (None, table.name):
            continue
        for constraint in table.constraints:
            if (
                isinstance(constraint, UniqueConstraint)
                and constraint.name == name
                and tuple(col.name for col in constraint.columns) == (column_name,)
            ):
                return field
        for index in table.indexes:
            if (
                index.unique
                and index.name == name
                and tuple(col.name for col in index.columns) == (column_name,)
            ):
                return field
    return None


def _normalize_question_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _question_labels_for_payload(
    payload: HandoutRegisterRequest,
) -> tuple[str, str, str]:
    """Use selected Q1-Q8 question codes, preserving legacy compatibility."""
    declared = tuple(name in type(payload).model_fields for name in _QUESTION_FIELDS)
    if any(declared) and not all(declared):
        raise RegistrationConfigurationError(
            "Registration schema must define all three question selectors."
        )

    if all(declared):
        raw_labels = tuple(getattr(payload, name) for name in _QUESTION_FIELDS)
    else:
        raw_labels = _LEGACY_QUESTION_CODES

    if (
        len(raw_labels) != 3
        or any(
            type(code) is not str or code not in _QUESTION_TEXT_BY_CODE
            for code in raw_labels
        )
        or len(set(raw_labels)) != 3
    ):
        raise ValueError("Select three different questions from Q1 through Q8.")
    return raw_labels  # type: ignore[return-value]


def _question_ids_for_labels(session, labels: tuple[str, str, str]) -> dict[str, int]:
    """Resolve official question text to unique ACTIVE PostgreSQL IDs."""
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
    return _question_ids_for_labels(session, _LEGACY_QUESTION_CODES)


def inspect_assigned_question_readiness() -> dict[str, bool]:
    """Keep previous read-only compatibility preflight."""
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
    """Build allowlisted role-specific INSERT values from the schema."""
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
    """Validate network metadata provided by the trusted HTTP layer."""
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
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in user_agent
        )
    ):
        raise ValueError("Invalid browser user agent.")
    return {"ip_address": normalized_ip, "user_agent": user_agent}


def register_user(
    payload: HandoutRegisterRequest,
    *,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> RegistrationResult:
    """Atomically insert pending user, profile, role, answer hashes and logs.

    A duplicate violation rolls back every insert. The exact conflicting field
    is exposed internally only if it matches a confirmed unique constraint.
    If provided, the contact number is encrypted for the newly-created pending
    user in this very transaction. A failed encryption or insert aborts the
    entire registration, never leaving an unencrypted partial account.
    No OTP is sent here; the existing workflow does that after commit.
    """
    if not isinstance(payload, HandoutRegisterRequest):
        raise TypeError("Strict HandoutRegisterRequest is required for registration.")
    if payload.privacy_consent is not True:
        raise ValueError("Privacy consent is required.")

    selected_labels = _question_labels_for_payload(payload)
    context = _clean_context(client_ip, user_agent)
    role_table, role_values = _role_insert_values(payload)

    # Hash outside the transaction; never store plaintext answers or password.
    password_hash = hash_password(payload.password.get_secret_value())
    answer_hashes = {
        attribute: hash_password(
            getattr(payload, attribute).get_secret_value().casefold()
        )
        for attribute in _ANSWER_FIELDS
    }

    try:
        with SessionLocal.begin() as session:
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

            # File 14 validates and normalizes this optional number; File 13
            # validates it again, encrypts with AES-256-GCM and binds the AAD
            # to the server-issued user_id. Never log or return this value.
            # Passing a new user_id from INSERT above (not from the browser)
            # keeps the contact insert within the SAME transaction. An invalid
            # key or unavailable encrypted table aborts all registration rows.
            if payload.contact_number is not None:
                save_pending_registration_contact(
                    session,
                    newly_registered_user_id=int(user_id),
                    contact_number=payload.contact_number,
                )

            for attribute in _ANSWER_FIELDS:
                session.execute(
                    insert(user_security_answers_table).values(
                        user_id=user_id,
                        question_id=question_ids[attribute],
                        answer_hash=answer_hashes[attribute],
                    )
                )

            # PostgreSQL created_at records the privacy consent timestamp.
            session.execute(
                insert(security_logs_table).values(
                    user_id=user_id,
                    event_type="PRIVACY_CONSENT_GRANTED",
                    outcome="success",
                    event_details={"consent": True, "source": "registration_checkbox"},
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
        code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        if code == "23505":
            field = _duplicate_field_from_integrity_error(exc)
            raise DuplicateRegistrationError(field) from None
        raise

    return RegistrationResult(
        user_id=int(user_id),
        username=payload.username,
        email=str(payload.email),
        role=payload.role,
        account_status="pending_verification",
    )
