
"""Dormora File 121 -- read-only registered security-question verification.

CREATE: backend/app/services/recovery_security_questions.py

Internal backend service only. Not a public route and never an authentication
session. File 120 may issue a reset OTP only after the later recovery route has
verified reCAPTCHA, the selected answer, IP/account lockout, and rate limits.

Matches Dormora's current registration schema:
  public.users(user_id, account_status, email_verified_at)
  public.security_questions(question_id, question_text, is_active)
  public.user_security_answers(user_id, question_id, answer_hash)

The assigned questions are Q7, Q2 and Q4. Question IDs are discovered by
question text; they are NEVER assumed to be 7, 2, and 4.
Answers are stored as Argon2id hashes of answer.casefold() by registration.
No secret, hash, answer, username or other account detail is printed by --check.

CALLER CONTRACT FOR THE FUTURE ROUTE:
  - Establish an account-specific recovery challenge only after server-side
    CAPTCHA and generic anti-enumeration account identification.
  - NEVER accept a browser-supplied user_id or trust an arbitrary question_id.
  - Use the issued challenge to look up the trusted user_id server-side.
  - Count wrong answers toward the SAME server-side account lockout as login;
    record safe audit events, enforce rate limiting and generic messages.
  - Do not send a reset OTP unless verify_recovery_answer returns True.
  - Use a transaction for all reads; do not log or return answer hashes.

Read-only preflight:
  python -m app.services.recovery_security_questions --check
"""

from __future__ import annotations

import argparse
import ipaddress
import re
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, engine
from app.models.user import users_table


class RecoveryQuestionsUnavailable(RuntimeError):
    """Required question schema/registration records cannot be trusted."""


@dataclass(frozen=True, slots=True)
class RecoveryQuestion:
    """Public question text and an opaque DB ID, for a trusted recovery flow."""

    code: str
    question_id: int
    question_text: str


# Keep the exact seed-assigned question texts from Dormora registration.
ASSIGNED_QUESTIONS = (
    ("Q7", "What was the name of your elementary school?"),
    ("Q2", "Who was your best friend in elementary school?"),
    ("Q4", "What is your mother's maiden first name?"),
)

_HASHER = PasswordHasher()
_ANSWER_TABLE = "user_security_answers"
_QUESTIONS_TABLE = "security_questions"


def _normalized_question_text(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(
        r"\s+", " ", value.strip().replace("\u2019", "'")
    ).casefold()


def _answer_to_verify(answer: str) -> str | None:
    """Match the registration rule: letters/spaces, 2-50, no double spaces.

    Case-fold for Argon2 comparison; never silently alter a valid answer by
    removing internal whitespace or accents. Return None for invalid shapes.
    """
    if not isinstance(answer, str) or not (2 <= len(answer) <= 50):
        return None
    if answer != answer.strip() or "  " in answer:
        return None
    if not all(char == " " or char.isalpha() for char in answer):
        return None
    return answer.casefold()


def _require_session(db: Session) -> None:
    if not isinstance(db, Session) or not db.in_transaction():
        raise RecoveryQuestionsUnavailable(
            "An active caller-owned transaction is required."
        )


def _read_tables(db: Session) -> tuple[Table, Table]:
    _require_session(db)
    conn = db.connection()
    inspector = inspect(conn)

    if not inspector.has_table(_QUESTIONS_TABLE, schema="public"):
        raise RecoveryQuestionsUnavailable("Question bank is missing.")
    if not inspector.has_table(_ANSWER_TABLE, schema="public"):
        raise RecoveryQuestionsUnavailable("Registered answers table is missing.")

    questions = Table(
        _QUESTIONS_TABLE, MetaData(),
        schema="public", autoload_with=conn,
    )
    answers = Table(
        _ANSWER_TABLE, MetaData(),
        schema="public", autoload_with=conn,
    )

    if not {
        "question_id", "question_text", "is_active"
    }.issubset(questions.c.keys()):
        raise RecoveryQuestionsUnavailable(
            "Question-bank columns are incompatible."
        )

    if not {
        "user_id", "question_id", "answer_hash"
    }.issubset(answers.c.keys()):
        raise RecoveryQuestionsUnavailable(
            "Registered-answer columns are incompatible."
        )

    pk = inspector.get_pk_constraint(_ANSWER_TABLE, schema="public")
    if set(pk.get("constrained_columns") or ()) != {
        "user_id", "question_id"
    }:
        raise RecoveryQuestionsUnavailable(
            "Registered-answer ownership constraint is missing."
        )

    fks = inspector.get_foreign_keys(_ANSWER_TABLE, schema="public")

    if not any(
        fk.get("constrained_columns") == ["user_id"]
        and fk.get("referred_table") == "users"
        and fk.get("referred_columns") == ["user_id"]
        for fk in fks
    ):
        raise RecoveryQuestionsUnavailable(
            "Registered-answer user FK is missing."
        )

    if not any(
        fk.get("constrained_columns") == ["question_id"]
        and fk.get("referred_table") == _QUESTIONS_TABLE
        and fk.get("referred_columns") == ["question_id"]
        for fk in fks
    ):
        raise RecoveryQuestionsUnavailable(
            "Registered-answer question FK is missing."
        )

    for name in ("user_id", "account_status", "email_verified_at"):
        if name not in users_table.c:
            raise RecoveryQuestionsUnavailable(
                "Current user model is incompatible."
            )

    return questions, answers


def _question_bank(
    db: Session,
    questions: Table,
) -> tuple[RecoveryQuestion, ...]:

    rows = db.execute(
        select(
            questions.c.question_id,
            questions.c.question_text,
        ).where(questions.c.is_active.is_(True))
    ).all()

    by_text: dict[str, list[tuple[int, str]]] = {}

    for question_id, question_text in rows:
        if (
            type(question_id) is not int
            or question_id <= 0
            or not isinstance(question_text, str)
        ):
            raise RecoveryQuestionsUnavailable(
                "Invalid active question entry."
            )

        key = _normalized_question_text(question_text)
        by_text.setdefault(key, []).append(
            (question_id, question_text)
        )

    result: list[RecoveryQuestion] = []

    for code, expected_text in ASSIGNED_QUESTIONS:
        found = by_text.get(
            _normalized_question_text(expected_text), []
        )

        if len(found) != 1:
            raise RecoveryQuestionsUnavailable(
                "Assigned security question is missing or ambiguous."
            )

        result.append(
            RecoveryQuestion(code, found[0][0], found[0][1])
        )

    if len({
        entry.question_id for entry in result
    }) != len(ASSIGNED_QUESTIONS):
        raise RecoveryQuestionsUnavailable(
            "Assigned security-question IDs overlap."
        )

    return tuple(result)


def _eligible_user(db: Session, user_id: int) -> bool:
    if type(user_id) is not int or user_id <= 0:
        raise RecoveryQuestionsUnavailable(
            "Trusted user identity is invalid."
        )

    user = db.execute(
        select(
            users_table.c.account_status,
            users_table.c.email_verified_at,
        ).where(users_table.c.user_id == user_id)
    ).one_or_none()

    return bool(
        user is not None
        and user.account_status == "active"
        and user.email_verified_at is not None
    )


def _registered_answers(
    db: Session,
    answers: Table,
    user_id: int,
    bank: tuple[RecoveryQuestion, ...],
) -> dict[int, str]:

    question_ids = [
        item.question_id for item in bank
    ]

    rows = db.execute(
        select(
            answers.c.question_id,
            answers.c.answer_hash,
        ).where(
            answers.c.user_id == user_id,
            answers.c.question_id.in_(question_ids),
        )
    ).all()

    if len(rows) != len(bank):
        raise RecoveryQuestionsUnavailable(
            "Account does not have its three assigned answers."
        )

    result: dict[int, str] = {}

    for question_id, answer_hash in rows:
        if (
            type(question_id) is not int
            or question_id in result
            or not isinstance(answer_hash, str)
            or not answer_hash.startswith("$argon2id$")
            or len(answer_hash) > 255
        ):
            raise RecoveryQuestionsUnavailable(
                "Registered answer hash is incompatible."
            )

        result[question_id] = answer_hash

    if set(result) != set(question_ids):
        raise RecoveryQuestionsUnavailable(
            "Registered answers do not match assigned questions."
        )

    return result


def list_recovery_questions(
    db: Session,
    *,
    trusted_user_id: int,
) -> tuple[RecoveryQuestion, ...]:
    """List only this account's three seed-assigned questions.

    INTERNAL ONLY: the caller must derive trusted_user_id from a protected
    server-side recovery challenge. Never expose this by arbitrary username or
    user ID without a CAPTCHA, anti-enumeration flow and request limits.
    """
    questions, answers = _read_tables(db)
    bank = _question_bank(db, questions)

    if not _eligible_user(db, trusted_user_id):
        raise RecoveryQuestionsUnavailable(
            "Recovery account is not eligible."
        )

    _registered_answers(
        db, answers, trusted_user_id, bank
    )

    return bank


def verify_recovery_answer(
    db: Session,
    *,
    trusted_user_id: int,
    question_id: int,
    answer: str,
    answer_confirmation: str,
) -> bool:
    """Verify case-insensitively against the existing Argon2id answer hash.

    Returns False for a wrong answer or non-assigned question; never creates an
    OTP or resets a password. The future route MUST count False toward the
    login lockout, audit it, and use identical public error messages.
    """
    questions, answers = _read_tables(db)
    bank = _question_bank(db, questions)

    if not _eligible_user(db, trusted_user_id):
        raise RecoveryQuestionsUnavailable(
            "Recovery account is not eligible."
        )

    registered = _registered_answers(
        db, answers, trusted_user_id, bank
    )

    if type(question_id) is not int or question_id not in registered:
        return False

    normalized = _answer_to_verify(answer)
    confirmation = _answer_to_verify(answer_confirmation)

    if (
        normalized is None
        or confirmation is None
        or normalized != confirmation
    ):
        return False

    try:
        return bool(
            _HASHER.verify(
                registered[question_id],
                normalized,
            )
        )
    except VerifyMismatchError:
        return False
    except (
        InvalidHashError,
        VerificationError,
        ValueError,
        TypeError,
    ):
        raise RecoveryQuestionsUnavailable(
            "Stored recovery answer cannot be verified."
        ) from None


def _local_preflight() -> None:
    from app.core.config import settings

    if settings.environment != "development":
        raise RecoveryQuestionsUnavailable(
            "Development environment required."
        )

    if (
        engine.dialect.name != "postgresql"
        or engine.url.database != "dormora_db"
    ):
        raise RecoveryQuestionsUnavailable(
            "Expected local PostgreSQL dormora_db."
        )

    host = engine.url.host or ""

    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.casefold() == "localhost"

    if not local:
        raise RecoveryQuestionsUnavailable(
            "Only local PostgreSQL is permitted."
        )

    with SessionLocal() as db:
        with db.begin():
            db.execute(text("SET TRANSACTION READ ONLY"))
            questions, _ = _read_tables(db)
            found = _question_bank(db, questions)

    if tuple(question.code for question in found) != (
        "Q7", "Q2", "Q4"
    ):
        raise RecoveryQuestionsUnavailable(
            "Assigned question mapping changed."
        )

    # Pure verification check only. Never use real answers in a CLI self-test.
    sample_hash = _HASHER.hash("sample answer")

    if not _HASHER.verify(
        sample_hash,
        _answer_to_verify("SAMPLE ANSWER"),
    ):
        raise RecoveryQuestionsUnavailable(
            "Case-insensitive Argon2id verification failed."
        )

    print("DORMORA FILE 121 -- RECOVERY SECURITY QUESTIONS")
    print("Local development and PostgreSQL: PASS")
    print("Question/answer schema: PRESENT and compatible")
    print(
        "Seed-assigned questions: Q7, Q2, Q4 | "
        "Active question mapping: READY"
    )
    print(
        "Answer hashing: Argon2id | "
        "Case-insensitive comparison: PASS"
    )
    print(
        "No account, password, security answer, "
        "session, or OTP was modified."
    )
    print("File 121 check OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dormora recovery security-question verification"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        required=True,
        help="read-only local question schema and hash check",
    )
    parser.parse_args()

    try:
        _local_preflight()
    except RecoveryQuestionsUnavailable as exc:
        print("FILE 121 STOPPED:", str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("FILE 121 FAILED:", type(exc).__name__)
        print(
            "Inspect local question schema "
            "and related registration records."
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
