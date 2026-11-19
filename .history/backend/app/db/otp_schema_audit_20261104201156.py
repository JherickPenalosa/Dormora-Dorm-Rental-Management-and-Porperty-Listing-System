
"""Inspect the existing Dormora email OTP table without modifying it.

Backend File 15
Destination: backend/app/db/otp_schema_audit.py
Run from backend/: python -m app.db.otp_schema_audit

This diagnostic reads PostgreSQL schema metadata only. It never fetches OTP
codes/digests or user data, creates tables, or modifies database records.
"""

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine


SCHEMA = "public"
TABLE = "email_otps"


def _show_items(items: list[dict], format_item) -> None:
    """Print a section's entries, or a short note when there are none."""
    if not items:
        print("  None reported")
        return
    for item in items:
        print(f"  {format_item(item)}")


def main() -> None:
    """Display columns, keys, checks, and indexes for public.email_otps."""
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            print("DORMORA EMAIL OTP SCHEMA AUDIT")
            print(f"Connected database: {database_name}")
            print(f"Target table: {SCHEMA}.{TABLE}")
            print("Read-only metadata inspection; no OTPs or user records shown.")

            if not inspector.has_table(TABLE, schema=SCHEMA):
                print(f"ERROR: {SCHEMA}.{TABLE} does not exist.")
                raise SystemExit(1)

            print("\nCOLUMNS:")
            for column in inspector.get_columns(TABLE, schema=SCHEMA):
                name = column["name"]
                data_type = str(column["type"])
                nullable = bool(column.get("nullable", True))
                default = column.get("default")
                generated = bool(column.get("identity") or column.get("computed"))

                details = ["NULL allowed" if nullable else "NOT NULL"]
                if default is not None:
                    details.append(f"default={default}")
                if generated:
                    details.append("database-generated")
                if not nullable and default is None and not generated:
                    details.append("REQUIRED on INSERT")
                print(f"  {name}: {data_type} | {', '.join(details)}")

            print("\nPRIMARY KEY:")
            primary_key = inspector.get_pk_constraint(TABLE, schema=SCHEMA)
            columns = primary_key.get("constrained_columns") or []
            print("  " + (", ".join(columns) if columns else "None reported"))

            print("\nUNIQUE CONSTRAINTS:")
            _show_items(
                inspector.get_unique_constraints(TABLE, schema=SCHEMA),
                lambda item: (
                    f"{item.get('name', '(unnamed)')}: "
                    f"{', '.join(item.get('column_names') or [])}"
                ),
            )

            print("\nCHECK CONSTRAINTS:")
            _show_items(
                inspector.get_check_constraints(TABLE, schema=SCHEMA),
                lambda item: (
                    f"{item.get('name', '(unnamed)')}: {item.get('sqltext', '')}"
                ),
            )

            print("\nFOREIGN KEYS:")
            _show_items(
                inspector.get_foreign_keys(TABLE, schema=SCHEMA),
                lambda item: (
                    f"{', '.join(item.get('constrained_columns') or [])} -> "
                    f"{item.get('referred_schema') or SCHEMA}."
                    f"{item.get('referred_table', '?')}"
                    f"({', '.join(item.get('referred_columns') or [])})"
                ),
            )

            # Include expression and partial-index definitions.
            # This returns schema definitions, not OTP or account values.
            print("\nINDEX DEFINITIONS:")
            indexes = connection.execute(
                text(
                    "SELECT indexname, indexdef "
                    "FROM pg_catalog.pg_indexes "
                    "WHERE schemaname = :schema AND tablename = :table "
                    "ORDER BY indexname"
                ),
                {"schema": SCHEMA, "table": TABLE},
            ).all()

            if not indexes:
                print("  None reported")
            else:
                for index_name, definition in indexes:
                    print(f"  {index_name}: {definition}")

        print("\nOTP schema inspection complete. No database changes made.")
    except SQLAlchemyError:
        print("Database schema inspection failed. Check PostgreSQL and backend/.env.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
