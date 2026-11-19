
"""PostgreSQL connection and session management for Dormora.

Backend File 5. Connects to the existing Dormora database.
This module does not create, alter, or delete database tables.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


if not settings.database_url:
    raise RuntimeError(
        "DORMORA_DATABASE_URL is missing. Configure it in backend/.env."
    )


# Creating an engine does not immediately open a database connection.
engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

# Each request will receive its own SQLAlchemy session.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide a session for FastAPI endpoints and close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> str:
    """Query PostgreSQL and return the connected database name."""
    with engine.connect() as connection:
        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()
    return str(database_name)
