
"""Centralized configuration for the Dormora FastAPI backend.

Backend File 2. The optional .env file will be added in later files.
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="DORMORA_",
        extra="ignore",
    )

    app_name: str = "Dormora API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str | None = None


settings = Settings()
