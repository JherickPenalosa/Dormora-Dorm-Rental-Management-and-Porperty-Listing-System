
"""Dormora Backend File 43: safe, repeatable security question catalog setup.

Destination: backend/app/db/security_question_seed.py

Commands (run from backend with .venv activated):
    python -m app.db.security_question_seed
    python -m app.db.security_question_seed --apply

Default mode is READ ONLY. --apply inserts only missing official questions into
public.security_questions. No tables, existing rows, user answers, passwords,
or other application data are changed. Inactive or ambiguous matching rows
cause a safe stop; existing questions are never overwritten or reactivated.

Important: Q7/Q2/Q4 are question bank labels, NOT assumed question_id values.
The existing registration service resolves their actual IDs by question text.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from sqlalchemy import MetaData, Table, insert, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError


SCHEMA = "public"
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
REQUIRED_FOR_DORMORA = ("Q7", "Q2", "Q4")
# Stable application-specific advisory lock ID for concurrent seed attempts.
_CATALOG_LOCK_ID = 43008402


class QuestionCatalogNotReady(Exception):
    """Matching questions need manual review before inserting new records."""


@dataclass(frozen=True)
class CatalogAudit:
    statuses: dict[str, str]
    existing_rows: int

    @property
    def all_required_ready(self) -> bool:
        return all(
            self.statuses[key] == "READY"
            for key in REQUIRED_FOR_DORMORA
        )

    @property
    def missing_labels(self) -> tuple[str, ...]:
        return tuple(
            label
            for label, status in self.statuses.items()
            if status == "MISSING"
        )


def _normalized_question(text_value: str) -> str:
    """Use the same punctuation-insensitive comparison as File 42."""
    return re.sub(
        r"[^a-z0-9]+", " ", text_value.casefold()
    ).strip()


def _question_table(connection: Connection) -> Table:
    schema = SCHEMA if connection.dialect.name == "postgresql" else None
    table = Table(
        "security_questions",
        MetaData(),
        schema=schema,
        autoload_with=connection,
    )
    mandatory = {"question_id", "question_text", "is_active"}
    if not mandatory.issubset(table.c.keys()):
        raise QuestionCatalogNotReady(
            "security_questions is missing expected columns; "
            "no records changed."
        )
    return table


def _inspect_catalog(connection: Connection, table: Table) -> CatalogAudit:
    """Read ONLY question-bank IDs, question text, and activity flags."""
    rows = connection.execute(
        select(
            table.c.question_id,
            table.c.question_text,
            table.c.is_active,
        )
    ).all()

    normalized_rows: dict[str, list[bool]] = {}
    for _database_id, question_text, is_active in rows:
        if not isinstance(question_text, str):
            raise QuestionCatalogNotReady(
                "Invalid question catalog text detected."
            )
        normalized_rows.setdefault(
            _normalized_question(question_text), []
        ).append(is_active is True)

    statuses: dict[str, str] = {}
    for label, canonical_text in QUESTION_BANK:
        matches = normalized_rows.get(
            _normalized_question(canonical_text), []
        )
        if not matches:
            statuses[label] = "MISSING"
        elif len(matches) > 1:
            statuses[label] = "CONFLICT"
        elif matches[0]:
            statuses[label] = "READY"
        else:
            statuses[label] = "INACTIVE"

    return CatalogAudit(
        statuses=statuses,
        existing_rows=len(rows),
    )


def print_audit(audit: CatalogAudit, *, prefix: str = "") -> None:
    print(f"{prefix}Existing catalog rows: {audit.existing_rows}")
    for label, canonical_text in QUESTION_BANK:
        flag = (
            " [needed for Dormora]"
            if label in REQUIRED_FOR_DORMORA
            else ""
        )
        print(f"  {label}: {audit.statuses[label]}{flag}")
    print("  Required Q7/Q2/Q4 ready:", audit.all_required_ready)


def run_catalog_setup(
    db_engine: Engine,
    *,
    apply: bool = False,
) -> CatalogAudit:
    """Inspect by default; explicitly --apply to add missing questions only.

    All apply-mode inserts run inside one transaction. A PostgreSQL advisory
    lock prevents two copies of this setup from racing each other.
    """
    with db_engine.begin() as connection:
        if apply and connection.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": _CATALOG_LOCK_ID},
            )

        table = _question_table(connection)
        before = _inspect_catalog(connection, table)

        print("DORMORA SECURITY QUESTION CATALOG — BACKEND FILE 43")
        print(
            "Mode:",
            "APPLY MISSING QUESTIONS" if apply else "READ ONLY",
        )
        print("Target:", f"{SCHEMA}.security_questions")
        print_audit(before)

        if not apply:
            print("No rows inserted, updated, or deleted.")
            return before

        blockers = [
            label
            for label, status in before.statuses.items()
            if status in {"INACTIVE", "CONFLICT"}
        ]
        if blockers:
            raise QuestionCatalogNotReady(
                "Inactive or ambiguous question(s): "
                + ", ".join(blockers)
                + ". No changes made; review the catalog first."
            )

        for label, canonical_text in QUESTION_BANK:
            if before.statuses[label] == "MISSING":
                connection.execute(
                    insert(table).values(
                        question_text=canonical_text,
                        is_active=True,
                    )
                )

        after = _inspect_catalog(connection, table)
        if any(
            after.statuses[label] != "READY"
            for label, _ in QUESTION_BANK
        ):
            raise QuestionCatalogNotReady(
                "Catalog verification failed; transaction rolled back."
            )

        print("\nAFTER INSERT:")
        print_audit(after)
        print("New questions inserted:", len(before.missing_labels))
        print(
            "Existing questions preserved; "
            "no user data or schema changed."
        )
        return after


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check or safely seed Dormora's official security question bank."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Read-only inspection (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Insert only missing questions.",
    )
    arguments = parser.parse_args()

    from app.db.database import engine

    try:
        run_catalog_setup(engine, apply=arguments.apply)
    except QuestionCatalogNotReady as exc:
        raise SystemExit(
            f"QUESTION CATALOG NEEDS REVIEW: {exc}"
        ) from None
    except (SQLAlchemyError, ValueError):
        raise SystemExit(
            "Question catalog operation could not complete. "
            "Check database connectivity and table permissions."
        ) from None


if __name__ == "__main__":
    main()
