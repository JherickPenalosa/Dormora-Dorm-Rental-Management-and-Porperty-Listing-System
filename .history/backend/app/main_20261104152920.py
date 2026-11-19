
"""Dormora FastAPI application entry point.

Backend File 1: minimal API with a health-check endpoint.
Database connectivity and authentication are added in later files.
"""

from fastapi import FastAPI


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
