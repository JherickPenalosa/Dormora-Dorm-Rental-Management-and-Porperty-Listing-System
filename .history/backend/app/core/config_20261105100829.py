
"""Centralized settings for the Dormora FastAPI backend.

Backend File 29 -- full replacement of backend/app/core/config.py.
Preserves database, OTP, and SMTP settings from File 20. Adds Cloudflare
Turnstile CAPTCHA configuration. It does not verify CAPTCHA tokens.
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

    # Application and PostgreSQL settings.
    app_name: str = "Dormora API"
    app_version: str = "0.1.0"
    environment: Literal[
        "development", "test", "production"
    ] = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str | None = None

    # OTP HMAC key — Files 17 and 18.
    otp_hmac_secret: SecretStr | None = Field(
        default=None,
        repr=False,
    )

    # SMTP email-delivery settings — File 20.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(
        default=None,
        repr=False,
    )
    smtp_from_email: EmailStr | None = None
    smtp_from_name: str = Field(
        default="Dormora",
        min_length=1,
        max_length=80,
    )
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    smtp_timeout_seconds: int = Field(
        default=15,
        ge=5,
        le=60,
    )

    # Cloudflare Turnstile CAPTCHA settings — File 29.
    # These are optional while public registration is not enabled.
    turnstile_site_key: str | None = None
    turnstile_secret_key: SecretStr | None = Field(
        default=None,
        repr=False,
    )
    turnstile_timeout_seconds: int = Field(
        default=10,
        ge=3,
        le=30,
    )

    @field_validator("otp_hmac_secret")
    @classmethod
    def validate_otp_hmac_secret(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        if value is not None:
            decode_otp_secret(value.get_secret_value())
        return value

    @field_validator("smtp_host", "smtp_username")
    @classmethod
    def clean_optional_smtp_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()

        if "\r" in cleaned or "\n" in cleaned:
            raise ValueError(
                "SMTP fields must not contain line breaks."
            )

        return cleaned or None

    @field_validator("smtp_from_name")
    @classmethod
    def clean_sender_name(cls, value: str) -> str:
        cleaned = value.strip()

        if (
            not cleaned
            or "\r" in cleaned
            or "\n" in cleaned
        ):
            raise ValueError(
                "SMTP sender name must be nonblank and single-line."
            )

        return cleaned

    @field_validator("turnstile_site_key")
    @classmethod
    def validate_turnstile_site_key(
        cls,
        value: str | None,
    ) -> str | None:
        """Validate the public CAPTCHA site key."""
        if value is None:
            return None

        cleaned = value.strip()

        if not cleaned or any(
            char.isspace() for char in cleaned
        ):
            raise ValueError(
                "Turnstile site key must be nonblank with no whitespace."
            )

        return cleaned

    @field_validator("turnstile_secret_key")
    @classmethod
    def validate_turnstile_secret_key(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        """Reject blank or malformed private secrets."""
        if value is not None:
            secret = value.get_secret_value()

            if not secret or any(
                char.isspace() for char in secret
            ):
                raise ValueError(
                    "Turnstile secret key must not be blank or spaced."
                )

        return value

    def require_otp_hmac_key(self) -> bytes:
        """Return the configured OTP key."""
        if self.otp_hmac_secret is None:
            raise RuntimeError(
                "DORMORA_OTP_HMAC_SECRET is not configured. "
                "Set it privately in backend/.env before enabling OTP."
            )

        return decode_otp_secret(
            self.otp_hmac_secret.get_secret_value()
        )

    def require_smtp_configuration(self) -> None:
        """Ensure SMTP settings are available."""
        if not (
            self.smtp_host
            and self.smtp_username
            and self.smtp_password is not None
            and self.smtp_password.get_secret_value()
            and self.smtp_from_email
        ):
            raise RuntimeError(
                "SMTP email delivery is not configured. "
                "Set DORMORA_SMTP_HOST, "
                "DORMORA_SMTP_USERNAME, "
                "DORMORA_SMTP_PASSWORD, and "
                "DORMORA_SMTP_FROM_EMAIL privately in backend/.env."
            )

    def require_turnstile_configuration(self) -> None:
        """Reject CAPTCHA operations without configuration.

        Cloudflare's published test secrets must not be
        accepted in production.
        """
        if (
            self.turnstile_site_key is None
            or self.turnstile_secret_key is None
        ):
            raise RuntimeError(
                "Cloudflare Turnstile is not configured. "
                "Set DORMORA_TURNSTILE_SITE_KEY and "
                "DORMORA_TURNSTILE_SECRET_KEY "
                "privately in backend/.env before enabling registration."
            )

        secret = self.turnstile_secret_key.get_secret_value()

        test_secrets = {
            "1x0000000000000000000000000000000AA",
            "2x0000000000000000000000000000000AA",
            "3x0000000000000000000000000000000AA",
        }

        if (
            self.environment == "production"
            and secret in test_secrets
        ):
            raise RuntimeError(
                "Cloudflare Turnstile test keys are forbidden in production."
            )

    def require_turnstile_secret(self) -> str:
        """Return the private key for server-side verification."""
        self.require_turnstile_configuration()

        assert self.turnstile_secret_key is not None

        return self.turnstile_secret_key.get_secret_value()


settings = Settings()
