
"""Centralized settings for Dormora's FastAPI backend.

Backend File 20 -- replace backend/app/core/config.py.
Preserves database, frontend, and OTP settings from File 17, and adds
SMTP configuration for future email verification delivery.

This module does not connect to an SMTP server or send email.
"""

from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.otp_security import decode_otp_secret


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Load Dormora settings from OS variables or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="DORMORA_",
        extra="ignore",
    )

    # Application and PostgreSQL settings (Files 2 and 17).
    app_name: str = "Dormora API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str | None = None

    # OTP HMAC key (Files 17 and 18). Keep the actual value in backend/.env.
    otp_hmac_secret: SecretStr | None = Field(default=None, repr=False)

    # SMTP email-delivery settings. Configure in a later file.
    # STARTTLS typically uses port 587; implicit TLS ("ssl") typically uses 465.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_email: EmailStr | None = None
    smtp_from_name: str = Field(default="Dormora", min_length=1, max_length=80)
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    smtp_timeout_seconds: int = Field(default=15, ge=5, le=60)

    @field_validator("otp_hmac_secret")
    @classmethod
    def validate_otp_hmac_secret(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        """Reject malformed OTP keys without displaying the key."""
        if value is not None:
            decode_otp_secret(value.get_secret_value())
        return value

    @field_validator("smtp_host", "smtp_username")
    @classmethod
    def clean_optional_smtp_text(cls, value: str | None) -> str | None:
        """Normalize optional SMTP fields; reject embedded newlines."""
        if value is None:
            return None
        cleaned = value.strip()
        if "\r" in cleaned or "\n" in cleaned:
            raise ValueError("SMTP fields must not contain line breaks.")
        return cleaned or None

    @field_validator("smtp_from_name")
    @classmethod
    def clean_sender_name(cls, value: str) -> str:
        """Keep the sender name safe for use in an email header later."""
        cleaned = value.strip()
        if not cleaned or "\r" in cleaned or "\n" in cleaned:
            raise ValueError("SMTP sender name must be nonblank and single-line.")
        return cleaned

    def require_otp_hmac_key(self) -> bytes:
        """Return the previously configured 32-byte OTP key; never invent one."""
        if self.otp_hmac_secret is None:
            raise RuntimeError(
                "DORMORA_OTP_HMAC_SECRET is not configured. "
                "Set it privately in backend/.env before enabling OTP."
            )
        return decode_otp_secret(self.otp_hmac_secret.get_secret_value())

    def require_smtp_configuration(self) -> None:
        """Reject email delivery until all required SMTP settings are present.

        The future email sender calls this before attempting delivery.
        No credentials or secret values are returned or printed here.
        """
        if not (
            self.smtp_host
            and self.smtp_username
            and self.smtp_password is not None
            and self.smtp_password.get_secret_value()
            and self.smtp_from_email
        ):
            raise RuntimeError(
                "SMTP email delivery is not configured. Set DORMORA_SMTP_HOST, "
                "DORMORA_SMTP_USERNAME, DORMORA_SMTP_PASSWORD, and "
                "DORMORA_SMTP_FROM_EMAIL privately in backend/.env."
            )


settings = Settings()
