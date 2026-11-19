
"""Registration request validation for Dormora.

Backend File 12: backend/app/schemas/auth.py (full replacement of File 9).

Validates user account and required profile fields before registration.
This module performs no password hashing or database operations.
"""

import re
from datetime import date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,30}")


class RegisterRequest(BaseModel):
    """Public registration input for renters and property owners."""

    model_config = ConfigDict(extra="forbid")

    # Account information (public users may not assign themselves admin).
    username: str = Field(min_length=3, max_length=30)
    email: EmailStr = Field(max_length=255)
    password: SecretStr
    role: Literal["renter", "property_owner"]

    # Required fields in public.user_profiles.
    id_number: str = Field(pattern=r"^[0-9]{4}-[0-9]{4}$", min_length=9, max_length=9)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    family_name: str = Field(min_length=1, max_length=100)
    name_extension: Literal["Jr.", "Sr.", "Other"] | None = None
    other_extension: str | None = Field(default=None, max_length=50)
    birthdate: date
    street: str = Field(min_length=1, max_length=255)
    barangay: str = Field(min_length=1, max_length=150)
    city: str = Field(min_length=1, max_length=150)
    province: str = Field(min_length=1, max_length=150)
    country: str = Field(min_length=1, max_length=100)
    zip_code: str = Field(pattern=r"^[0-9]{4}$", min_length=4, max_length=4)

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
        if any(ord(char) < 32 or ord(char) == 127 for char in password):
            raise ValueError("Password cannot contain control characters.")
        return value

    @field_validator(
        "first_name", "family_name", "street", "barangay", "city", "province", "country"
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank or whitespace only.")
        return cleaned

    @field_validator("middle_name", "other_extension")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("birthdate")
    @classmethod
    def validate_birthdate(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Birthdate cannot be in the future.")
        return value

    @model_validator(mode="after")
    def validate_name_extension(self) -> Self:
        if self.name_extension == "Other" and not self.other_extension:
            raise ValueError(
                "other_extension is required when name_extension is 'Other'."
            )
        if self.name_extension != "Other" and self.other_extension:
            raise ValueError(
                "other_extension must be omitted unless name_extension is 'Other'."
            )
        return self
