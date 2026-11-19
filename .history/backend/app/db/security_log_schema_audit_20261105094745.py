
"""Inspect Dormora's existing security_logs PostgreSQL table.

Backend File 26
Destination: backend/app/db/security_log_schema_audit.py
Run from backend/: python -m app.db.security_log_schema_audit

Read-only inspection of database metadata: no security log records are read,
and no data or schema is modified.
"""

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine


SCHEMA = "public"
TABLE = "security_logs"


def _print_items(items: list[dict], formatter) -> None:
    """Print zero or more schema entries without querying table records."""
    if not items:
        print("  None reported")
        return
    for item in items:
        print("  " + formatter(item))


def main() -> None:
    """Report the table definition needed for future audit-log inserts."""
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            print("DORMORA SECURITY LOGS SCHEMA AUDIT")
            print(f"Connected database: {database_name}")
            print(f"Target table: {SCHEMA}.{TABLE}")
            print("Read-only schema inspection; no log or account records shown.")

            if not inspector.has_table(TABLE, schema=SCHEMA):
                print(f"ERROR: {SCHEMA}.{TABLE} was not found.")
                raise SystemExit(1)

            print("\nCOLUMNS:")
            for column in inspector.get_columns(TABLE, schema=SCHEMA):
                name = column["name"]
                column_type = str(column["type"])
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
                print(f"  {name}: {column_type} | {', '.join(details)}")

            print("\nPRIMARY KEY:")
            primary_key = inspector.get_pk_constraint(TABLE, schema=SCHEMA)
            primary_columns = primary_key.get("constrained_columns") or []
            print(
                "  " + (
                    ", ".join(primary_columns)
                    if primary_columns
                    else "None reported"
                )
            )

            print("\nUNIQUE CONSTRAINTS:")
            _print_items(
                inspector.get_unique_constraints(TABLE, schema=SCHEMA),
                lambda item: (
                    f"{item.get('name') or '(unnamed)'}: "
                    f"{', '.join(item.get('column_names') or [])}"
                ),
            )

            print("\nCHECK CONSTRAINTS:")
            _print_items(
                inspector.get_check_constraints(TABLE, schema=SCHEMA),
                lambda item: (
                    f"{item.get('name') or '(unnamed)'}: "
                    f"{item.get('sqltext') or '(no definition returned)'}"
                ),
            )

            print("\nFOREIGN KEYS:")
            _print_items(
                inspector.get_foreign_keys(TABLE, schema=SCHEMA),
                lambda item: (
                    f"{', '.join(item.get('constrained_columns') or [])} -> "
                    f"{item.get('referred_schema') or SCHEMA}."
                    f"{item.get('referred_table') or '?'}"
                    f"({', '.join(item.get('referred_columns') or [])})"
                ),
            )

            # PostgreSQL catalog metadata, not security_logs records.
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
                for index_name, index_definition in indexes:
                    print(f"  {index_name}: {index_definition}")

        print("\nSecurity logs schema inspection complete. No changes made.")

    except SQLAlchemyError:
        print("Schema inspection failed. Check PostgreSQL and backend/.env.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
