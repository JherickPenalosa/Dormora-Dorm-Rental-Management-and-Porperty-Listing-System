
"""Read-only schema reflection and ORM mapping for Dormora's existing users table.

Backend File 8: backend/app/models/user.py

The users table was previously created in PostgreSQL. We reflect its actual
columns and constraints instead of guessing their definitions or creating a
new table. Importing this module requires a working database connection.

No user records are retrieved by this module on import.
"""

from sqlalchemy import Table
from sqlalchemy.orm import registry

from app.db.database import engine


# A registry holds SQLAlchemy's ORM mappings.
mapper_registry = registry()

# Read PostgreSQL's existing table definition (columns and primary key).
# This inspects the schema; it does not CREATE or ALTER the table.
users_table = Table(
    "users",
    mapper_registry.metadata,
    schema="public",
    autoload_with=engine,
)


class User:
    """ORM representation of a row in the existing public.users table."""


# Map the class to the reflected table without inventing column definitions.
mapper_registry.map_imperatively(User, users_table)
