
"""Dormora FastAPI application entry point.

Backend File 6: keep the API health check and add a PostgreSQL health check.
The database check uses the existing read-only query from File 5.
"""

from fastapi import FastAPI, HTTPException # This returns
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import check_database_connection


app = FastAPI(
    title="Dormora API",
    description="Backend API for the Dormora rental management and property listing system.",
    version="0.1.0",
)


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Confirm the FastAPI application is running."""
    return {
        "status": "healthy",
        "service": "Dormora API",
    }


@app.get("/api/health/db", tags=["Health"])
def database_health_check() -> dict[str, str]:
    """Confirm PostgreSQL is reachable without exposing credentials."""
    try:
        database_name = check_database_connection()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable.",
        ) from None

    return {
        "status": "connected",
        "database": database_name,
    }
