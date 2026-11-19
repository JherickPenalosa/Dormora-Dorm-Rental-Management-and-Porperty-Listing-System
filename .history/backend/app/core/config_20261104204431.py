
"""Centralized application settings for the Dormora FastAPI backend.

Backend File 17: full replacement for backend/app/core/config.py.

Preserves the existing File 2 settings and prepares a private HMAC key for
email OTP verification. The key is optional while OTP endpoints are not
active; OTP operations must explicitly require it before they are enabled.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.otp_security import decode_otp_secret


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings loaded from OS environment variables or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="DORMORA_",
        extra="ignore",
    )

    # Existing application and PostgreSQL configuration from File 2.
    app_name: str = "Dormora API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str | None = None

    # Configured in backend/.env during File 18. Never commit or display it.
    # 64 hex characters represent 32 random secret bytes.
    otp_hmac_secret: SecretStr | None = Field(default=None, repr=False)

    @field_validator("otp_hmac_secret")
    @classmethod
    def validate_otp_hmac_secret(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        """Reject incorrectly formatted keys when a value is supplied."""
        if value is not None:
            decode_otp_secret(value.get_secret_value())
        return value

    def require_otp_hmac_key(self) -> bytes:
        """Get the key only for an OTP operation; never generate a fallback.

        Fail closed if the key has not been configured. A stable key is needed
        to verify unexpired OTPs after a server restart.
        """
        if self.otp_hmac_secret is None:
            raise RuntimeError(
                "DORMORA_OTP_HMAC_SECRET is not configured. "
                "Set it privately in backend/.env before enabling OTP."
            )
        return decode_otp_secret(self.otp_hmac_secret.get_secret_value())


settings = Settings()
