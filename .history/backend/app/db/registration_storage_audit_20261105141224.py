
"""Dormora Backend File 41: read-only registration storage audit.

Install at: backend/app/db/registration_storage_audit.py
Run from backend: python -m app.db.registration_storage_audit

Only SQLAlchemy inspection / PostgreSQL catalog lookups are used. The script
never reads user rows, credentials, answers, or security event records, and it
never writes or changes the schema. Do not paste .env content into the output.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine


SCHEMA = "public"

# Always show these known registration-related tables if they exist.
KNOWN_REGISTRATION_TABLES = frozenset(
    {
        "users",
        "user_profiles",
        "renter_preferences",
        "property_owner_details",
    }
)

# Pick up registration-related tables even when their names are unfamiliar.
TABLE_KEYWORDS = (
    "user", "profile", "question", "answer", "consent", "privacy",
    "renter", "owner", "registration", "credential", "identity",
)
COLUMN_KEYWORDS = (
    "question", "answer", "consent", "privacy", "agreement",
    "accepted", "verified", "id_number", "first_name", "family_name",
    "birthdate", "rental_type", "property_type", "encrypted", "cipher",
)


def _column_is_required(column: Mapping[str, object]) -> bool:
    """Infer whether a column is required for INSERT from metadata only."""
    return (
        not bool(column.get("nullable", True))
        and column.get("default") is None
        and not column.get("identity")
        and not column.get("computed")
        and column.get("autoincrement") is not True
    )


def _print_table_details(inspector, name: str, columns: list[dict]) -> None:
    """Print public structural metadata; never any data or default values."""
    print(f"\nTABLE: {SCHEMA}.{name}")
    print("  COLUMNS:")
    for column in columns:
        column_name = str(column["name"])
        column_type = str(column["type"])
        nullability = "nullable" if column.get("nullable", True) else "NOT NULL"
        required = ", required on INSERT" if _column_is_required(column) else ""
        print(f"    {column_name}: {column_type} | {nullability}{required}")

    pk = inspector.get_pk_constraint(name, schema=SCHEMA)
    pk_columns = pk.get("constrained_columns") or []
    print("  PRIMARY KEY:", ", ".join(pk_columns) if pk_columns else "none reported")

    foreign_keys = inspector.get_foreign_keys(name, schema=SCHEMA)
    print("  FOREIGN KEYS:")
    if foreign_keys:
        for fk in foreign_keys:
            origin_cols = ", ".join(fk.get("constrained_columns") or [])
            target_cols = ", ".join(fk.get("referred_columns") or [])
            referred_schema = fk.get("referred_schema") or SCHEMA
            print(
                f"    {origin_cols} -> "
                f"{referred_schema}.{fk.get('referred_table')}({target_cols})"
            )
    else:
        print("    none reported")

    unique_constraints = inspector.get_unique_constraints(name, schema=SCHEMA)
    unique_indexes = [
        index for index in inspector.get_indexes(name, schema=SCHEMA)
        if index.get("unique")
    ]
    print("  UNIQUENESS (constraints/indexes):")
    if not unique_constraints and not unique_indexes:
        print("    none reported")
    for constraint in unique_constraints:
        print(
            "    constraint:", constraint.get("name") or "unnamed",
            "columns:", ", ".join(constraint.get("column_names") or []),
        )
    for index in unique_indexes:
        # PostgreSQL expression indexes (for example lower(email)) may
        # appear as None in column_names; include the expression metadata.
        indexed_parts = [
            str(part) if part is not None else "(expression)"
            for part in (index.get("column_names") or [])
        ]
        if index.get("expressions"):
            indexed_parts.extend(str(item) for item in index["expressions"])
        print(
            "    unique index:", index.get("name") or "unnamed",
            "columns/expressions:", ", ".join(indexed_parts) or "not reported",
        )

    # CHECK rules are helpful for ID formats and consent, but printing the
    # SQL text is unnecessary: it might be verbose or contain literal data.
    checks = inspector.get_check_constraints(name, schema=SCHEMA)
    print("  CHECK CONSTRAINT NAMES:")
    if checks:
        for check in checks:
            print("   ", check.get("name") or "unnamed")
    else:
        print("    none reported")


def run_audit() -> None:
    """Inspect registration storage capabilities without touching stored rows."""
    with engine.connect() as connection:
        inspector = inspect(connection)
        database_name = connection.execute(text("SELECT current_database()")).scalar_one()
        table_names = sorted(inspector.get_table_names(schema=SCHEMA))
        if not table_names:
            raise RuntimeError("No ordinary tables found in public schema.")

        # Inspect metadata for every table so we do not assume that consent or
        # authentication answers live under particular table names.
        columns_by_table = {
            name: inspector.get_columns(name, schema=SCHEMA)
            for name in table_names
        }

        relevant = []
        for name in table_names:
            matching_name = name in KNOWN_REGISTRATION_TABLES or any(
                keyword in name.lower() for keyword in TABLE_KEYWORDS
            )
            matching_column = any(
                any(keyword in str(col["name"]).lower() for keyword in COLUMN_KEYWORDS)
                for col in columns_by_table[name]
            )
            if matching_name or matching_column:
                relevant.append(name)

        print("DORMORA REGISTRATION STORAGE AUDIT — BACKEND FILE 41")
        print("Connected database:", database_name)
        print("Schema:", SCHEMA)
        print("Mode: READ ONLY (metadata only; no personal data or secrets)")
        print("\nALL PUBLIC TABLES:")
        for name in table_names:
            print("  -", name)
        print(f"Table count: {len(table_names)}")
        print("\nREGISTRATION-RELATED TABLES IDENTIFIED:")
        if relevant:
            for name in relevant:
                print("  -", name)
        else:
            print("  None found by metadata keywords")

        for name in relevant:
            _print_table_details(inspector, name, columns_by_table[name])

        print("\nSCHEMA FEATURES TO REVIEW BEFORE ACTIVATING REGISTRATION:")
        print("  1. Privacy consent: where is agreement plus timestamp stored?")
        print("  2. Three security answers: where can 3 hashes per user be stored?")
        print("  3. Renter/owner-specific fields: are approved fields represented?")
        print("  4. Sensitive field: which field can support AES-256 encryption at rest?")
        print("  5. Uniqueness: how are ID number, email and username enforced?")
        print("\nIMPORTANT: This is a schema inspection, not a verification of")
        print("registration behavior, privacy consent, hashing, or encryption.")
        print("Registration storage audit complete. No database changes made.")


if __name__ == "__main__":
    try:
        run_audit()
    except (SQLAlchemyError, RuntimeError):
        # Never print raw SQLAlchemy/database exceptions: URLs and SQL may
        # contain sensitive information. See the private backend error logs.
        raise SystemExit(
            "Registration storage audit could not complete. "
            "Check database connectivity and table permissions."
        ) from None
