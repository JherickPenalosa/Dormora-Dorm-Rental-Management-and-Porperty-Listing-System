
"""Validation schemas for Dormora's public registration API.

Backend File 9: backend/app/schemas/auth.py

This module validates incoming registration data only. It does not create
accounts, query PostgreSQL, hash passwords, or send verification emails.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,30}")


class RegisterRequest(BaseModel):
    """Input accepted when a renter or property owner registers."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=3,
        max_length=30,
        description="3–30 characters: letters, numbers, and underscores only.",
    )
    email: EmailStr = Field(description="A valid email address.")
    password: SecretStr = Field(description="12–128 characters; handled as a secret.")
    role: Literal["renter", "property_owner"] = Field(
        description="Public registration cannot create administrator accounts."
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        username = value.strip()
        if not _USERNAME_PATTERN.fullmatch(username):
            raise ValueError(
                "Username must be 3–30 characters and contain only letters, "
                "numbers, or underscores."
            )
        return username

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 12 <= len(password) <= 128:
            raise ValueError("Password must contain 12–128 characters.")
        if not password.strip():
            raise ValueError("Password cannot consist only of whitespace.")
        if any(ord(character) < 32 or ord(character) == 127 for character in password):
            raise ValueError("Password cannot contain control characters.")
        return value
