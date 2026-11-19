
"""Dormora FastAPI application entry point.

Backend File 31: add security response headers while preserving the
React CORS configuration and both existing health endpoints.

These headers protect API responses. React pages are served separately
by Vite/a frontend host and must also receive headers from that host.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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

# Preserve the configured React frontend origin from Backend File 7.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin.rstrip("/")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Prevent API framing and disable MIME-type sniffing."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
