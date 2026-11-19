
"""Dormora FastAPI application entry point.

Backend File 7: allow the configured React frontend to call the API.
This file preserves both health-check endpoints from File 6.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware # The middle
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import check_database_connection


app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend API for the Dormora rental management and "
        "property listing system."
    ),
    version=settings.app_version,
)

# Browsers require CORS permission when React and FastAPI run on
# different origins (for example, localhost:5173 and 127.0.0.1:8000).
# Only the specifically configured frontend origin is allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin.rstrip("/")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
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
