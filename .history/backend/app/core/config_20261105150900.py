
"""Centralized settings for the Dormora FastAPI backend.

Backend File 47 -- full replacement of backend/app/core/config.py.
Preserves existing application, PostgreSQL, OTP, SMTP, Turnstile, and CSRF settings.
Adds optional Google reCAPTCHA v2 Checkbox configuration for File 46.
No database changes, cookies, or public routes are created here.
"""

import re
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.otp_security import decode_otp_secret


BACKEND_DIR = Path(__file__).resolve().parents[2]
_CSRF_SECRET_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
_RECAPTCHA_HOST_LABEL = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z"
)

# Google's publicly documented v2 test pair always passes challenges.
# It may be used for isolated testing, but NEVER for a production deployment.
_RECAPTCHA_V2_PUBLIC_TEST_SITE_KEY = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
_RECAPTCHA_V2_PUBLIC_TEST_SECRET_KEY = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"


class Settings(BaseSettings):
    """Load Dormora settings from OS environment variables or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="DORMORA_",
        extra="ignore",
    )

    # Existing application and PostgreSQL settings.
    app_name: str = "Dormora API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str | None = None

    # OTP HMAC secret (Files 17-18): 32 bytes represented by 64 hex characters.
    otp_hmac_secret: SecretStr | None = Field(default=None, repr=False)

    # SMTP settings (File 20): credentials stay in backend/.env.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_email: EmailStr | None = None
    smtp_from_name: str = Field(default="Dormora", min_length=1, max_length=80)
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    smtp_timeout_seconds: int = Field(default=15, ge=5, le=60)

    # Cloudflare Turnstile settings (File 29).
    turnstile_site_key: str | None = None
    turnstile_secret_key: SecretStr | None = Field(default=None, repr=False)
    turnstile_timeout_seconds: int = Field(default=10, ge=3, le=30)

    # CSRF signing secret (File 34): set in backend/.env during File 35.
    # Keep it distinct from the OTP HMAC key; do not generate a fallback.
    csrf_secret: SecretStr | None = Field(default=None, repr=False)

    # Google reCAPTCHA v2 Checkbox (Files 46-47).
    # Optional until the secured registration API is mounted; verification
    # must fail closed once enabled. Site key is public; secret stays server-only.
    recaptcha_v2_site_key: str | None = None
    recaptcha_v2_secret_key: SecretStr | None = Field(default=None, repr=False)
    recaptcha_v2_expected_hostname: str = "localhost"
    recaptcha_v2_timeout_seconds: int = Field(default=10, ge=3, le=30)

    @field_validator("otp_hmac_secret")
    @classmethod
    def validate_otp_hmac_secret(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is not None:
            decode_otp_secret(value.get_secret_value())
        return value

    @field_validator("smtp_host", "smtp_username")
    @classmethod
    def clean_optional_smtp_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if "\r" in cleaned or "\n" in cleaned:
            raise ValueError("SMTP fields must not contain line breaks.")
        return cleaned or None

    @field_validator("smtp_from_name")
    @classmethod
    def clean_sender_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "\r" in cleaned or "\n" in cleaned:
            raise ValueError("SMTP sender name must be nonblank and single-line.")
        return cleaned

    @field_validator("turnstile_site_key")
    @classmethod
    def validate_turnstile_site_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned or any(char.isspace() for char in cleaned):
            raise ValueError("Turnstile site key must be nonblank with no whitespace.")
        return cleaned

    @field_validator("turnstile_secret_key")
    @classmethod
    def validate_turnstile_secret_key(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is not None:
            secret = value.get_secret_value()
            if not secret or any(char.isspace() for char in secret):
                raise ValueError("Turnstile secret key must not be blank or spaced.")
        return value

    @field_validator("csrf_secret")
    @classmethod
    def validate_csrf_secret(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        """Require a 32-byte CSRF key encoded as exactly 64 hex characters."""
        if value is not None and not _CSRF_SECRET_PATTERN.fullmatch(
            value.get_secret_value()
        ):
            raise ValueError("CSRF secret must contain exactly 64 hexadecimal characters.")
        return value

    @field_validator("recaptcha_v2_site_key")
    @classmethod
    def validate_recaptcha_v2_site_key(cls, value: str | None) -> str | None:
        """Reject invalid site keys without affecting an unconfigured backend."""
        if value is None:
            return None
        if not 1 <= len(value) <= 512 or not value.isascii() or any(
            ord(char) < 33 or ord(char) > 126 for char in value
        ):
            raise ValueError("Google reCAPTCHA v2 site key is malformed.")
        return value

    @field_validator("recaptcha_v2_secret_key")
    @classmethod
    def validate_recaptcha_v2_secret_key(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        """Keep malformed server-side secrets out of the application."""
        if value is not None:
            secret = value.get_secret_value()
            if not 1 <= len(secret) <= 512 or not secret.isascii() or any(
                ord(char) < 33 or ord(char) > 126 for char in secret
            ):
                raise ValueError("Google reCAPTCHA v2 server secret is malformed.")
        return value

    @field_validator("recaptcha_v2_expected_hostname")
    @classmethod
    def validate_recaptcha_v2_expected_hostname(cls, value: str) -> str:
        """Accept only a fixed hostname, not a URL, port, wildcard or path."""
        if (
            not value
            or len(value) > 253
            or value.endswith(".")
            or not all(_RECAPTCHA_HOST_LABEL.fullmatch(part) for part in value.split("."))
        ):
            raise ValueError("Google reCAPTCHA expected hostname is invalid.")
        return value.lower()

    def require_otp_hmac_key(self) -> bytes:
        """Return the private OTP key; never invent a fallback."""
        if self.otp_hmac_secret is None:
            raise RuntimeError(
                "DORMORA_OTP_HMAC_SECRET is not configured. "
                "Set it privately in backend/.env before enabling OTP."
            )
        return decode_otp_secret(self.otp_hmac_secret.get_secret_value())

    def require_smtp_configuration(self) -> None:
        """Reject SMTP delivery until credentials and sender are configured."""
        if not (
            self.smtp_host
            and self.smtp_username
            and self.smtp_password is not None
            and self.smtp_password.get_secret_value()
            and self.smtp_from_email
        ):
            raise RuntimeError(
                "SMTP email delivery is not configured. "
                "Set DORMORA_SMTP_HOST, DORMORA_SMTP_USERNAME, "
                "DORMORA_SMTP_PASSWORD, and DORMORA_SMTP_FROM_EMAIL "
                "privately in backend/.env."
            )

    def require_turnstile_configuration(self) -> None:
        """Require Turnstile keys and forbid published test keys in production."""
        if self.turnstile_site_key is None or self.turnstile_secret_key is None:
            raise RuntimeError(
                "Cloudflare Turnstile is not configured. "
                "Set DORMORA_TURNSTILE_SITE_KEY and "
                "DORMORA_TURNSTILE_SECRET_KEY privately in backend/.env."
            )

        test_secrets = {
            "1x0000000000000000000000000000000AA",
            "2x0000000000000000000000000000000AA",
            "3x0000000000000000000000000000000AA",
        }
        if (
            self.environment == "production"
            and self.turnstile_secret_key.get_secret_value() in test_secrets
        ):
            raise RuntimeError(
                "Cloudflare Turnstile test keys are forbidden in production."
            )

    def require_turnstile_secret(self) -> str:
        """Return the private Turnstile key for server-side verification."""
        self.require_turnstile_configuration()
        assert self.turnstile_secret_key is not None
        return self.turnstile_secret_key.get_secret_value()

    def require_csrf_key(self) -> bytes:
        """Return a stable CSRF signing key, separate from the OTP HMAC key.

        Only call this when CSRF endpoints/middleware are being integrated.
        Until File 35, the CSRF key can be absent without breaking health checks.
        """
        if self.csrf_secret is None:
            raise RuntimeError(
                "DORMORA_CSRF_SECRET is not configured. "
                "Set it privately in backend/.env before enabling CSRF protection."
            )

        csrf_key = bytes.fromhex(self.csrf_secret.get_secret_value())
        if self.otp_hmac_secret is not None and csrf_key == self.require_otp_hmac_key():
            raise RuntimeError("CSRF and OTP HMAC keys must be different.")
        return csrf_key

    def require_recaptcha_v2_configuration(self) -> None:
        """Require complete configuration before real verification.

        Missing keys do not break the existing health endpoints. However,
        callers MUST invoke this before issuing any CAPTCHA-protected action.
        Google's published test keys are rejected in production.
        """
        if self.recaptcha_v2_site_key is None or self.recaptcha_v2_secret_key is None:
            raise RuntimeError(
                "Google reCAPTCHA v2 is not configured. Set "
                "DORMORA_RECAPTCHA_V2_SITE_KEY and "
                "DORMORA_RECAPTCHA_V2_SECRET_KEY privately in backend/.env."
            )

        if self.recaptcha_v2_site_key == self.recaptcha_v2_secret_key.get_secret_value():
            raise RuntimeError("Google reCAPTCHA site and secret keys must be different.")

        if self.environment == "production":
            if self.recaptcha_v2_expected_hostname == "localhost":
                raise RuntimeError(
                    "Production reCAPTCHA must use the deployed website hostname."
                )
            if (
                self.recaptcha_v2_site_key == _RECAPTCHA_V2_PUBLIC_TEST_SITE_KEY
                or self.recaptcha_v2_secret_key.get_secret_value()
                == _RECAPTCHA_V2_PUBLIC_TEST_SECRET_KEY
            ):
                raise RuntimeError(
                    "Google's public reCAPTCHA test keys are forbidden in production."
                )

    def require_recaptcha_v2_site_key(self) -> str:
        """Return only the public key for later React widget integration."""
        self.require_recaptcha_v2_configuration()
        assert self.recaptcha_v2_site_key is not None
        return self.recaptcha_v2_site_key

    def build_recaptcha_v2_verifier(self, *, client_ip: str | None = None):
        """Construct File 46's callable server-side verifier from private keys.

        A future registration route passes its trusted Request.client.host.
        Never obtain client_ip from user-controlled payloads or untrusted
        forwarding headers. Never return this verifier to the frontend.
        """
        self.require_recaptcha_v2_configuration()
        from app.services.recaptcha_v2_service import RecaptchaV2Verifier

        assert self.recaptcha_v2_secret_key is not None
        return RecaptchaV2Verifier(
            secret_key=self.recaptcha_v2_secret_key.get_secret_value(),
            expected_hostname=self.recaptcha_v2_expected_hostname,
            client_ip=client_ip,
            timeout_seconds=self.recaptcha_v2_timeout_seconds,
        )


settings = Settings()
