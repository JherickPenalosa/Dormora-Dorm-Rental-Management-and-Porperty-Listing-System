
"""Dormora registration schemas — Backend File 40.

Destination: backend/app/schemas/auth.py (full replacement of File 32).

The old RegisterRequest remains available for unmounted development workflows.
HandoutRegisterRequest adds STRICT, student-seeded checks for future public
registration. Do not mount the public registration route yet: privacy consent
must be persisted, security answers must be hashed/stored, approved CAPTCHA
must be integrated, and system-specific fields must be validated and saved.

This module does not connect to PostgreSQL, send emails, or create accounts.
"""

import re
import secrets
from datetime import date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)


# Confirmed student seed: D1=9, D2=6.
STUDENT_D1 = 9
STUDENT_D2 = 6

USERNAME_MIN = 6 + STUDENT_D1 % 3
USERNAME_MAX = 16 + STUDENT_D2 % 5

PASSWORD_MIN = 8 + STUDENT_D2 % 4
PASSWORD_MAX = 64

NAME_MAX = 20 + STUDENT_D2

SECURITY_QUESTION_IDS = (
    STUDENT_D2 % 8 + 1,
    (STUDENT_D2 + 3) % 8 + 1,
    (STUDENT_D2 + 5) % 8 + 1,
)

_LEGACY_USERNAME = re.compile(r"[A-Za-z0-9_]{3,30}\Z")
_STRICT_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")


def password_strength(
    password: str,
) -> Literal["Weak", "Medium", "Strong"]:
    """Classify strength using four character groups.

    Lowercase, uppercase, digits, and symbols are the four groups.
    Fewer than three groups is Weak. Three is Medium.
    Four groups with at least 12 characters is Strong.

    Weak is never accepted by HandoutRegisterRequest.
    """
    if not isinstance(password, str):
        raise TypeError("password must be a string")

    groups = sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(
                not c.isalnum() and not c.isspace()
                for c in password
            ),
        )
    )

    if groups < 3:
        return "Weak"

    if groups == 4 and len(password) >= 12:
        return "Strong"

    return "Medium"


def _check_title_case(
    value: str,
    label: str,
    minimum: int,
    maximum: int,
) -> str:
    """Enforce length, spacing, letters, and capitalization."""
    if not minimum <= len(value) <= maximum:
        raise ValueError(
            f"{label} must have {minimum}–{maximum} characters."
        )

    if value != value.strip() or "  " in value:
        raise ValueError(
            f"{label} must not contain extra or double spaces."
        )

    if not all(
        c.isalpha() or c == " "
        for c in value
    ):
        raise ValueError(
            f"{label} may contain letters and single spaces only."
        )

    if value == value.upper():
        raise ValueError(
            f"{label} must not use all capital letters."
        )

    if any(
        word != word[0].upper() + word[1:].lower()
        for word in value.split(" ")
    ):
        raise ValueError(
            f"{label} must use Title Case."
        )

    folded = value.casefold()

    if any(
        folded[i] == folded[i + 1] == folded[i + 2]
        and folded[i].isalpha()
        for i in range(len(folded) - 2)
    ):
        raise ValueError(
            f"{label} cannot contain three identical letters in a row."
        )

    return value


class RegisterRequest(BaseModel):
    """Existing internal registration request.

    Retained so earlier unmounted backend workflows and tests keep
    their original expected input structure.

    Future public registration MUST use HandoutRegisterRequest.
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=30)
    email: EmailStr = Field(max_length=255)
    password: SecretStr
    role: Literal["renter", "property_owner"]

    # Honeypot: never store the value.
    website: str = Field(
        default="",
        max_length=255,
        exclude=True,
        repr=False,
    )

    id_number: str = Field(
        pattern=r"^[0-9]{4}-[0-9]{4}$",
        min_length=9,
        max_length=9,
    )

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

    zip_code: str = Field(
        pattern=r"^[0-9]{4}$",
        min_length=4,
        max_length=4,
    )

    @field_validator("website")
    @classmethod
    def reject_filled_honeypot(cls, value: str) -> str:
        if value:
            raise ValueError("Registration could not be completed.")
        return value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()

        if not _LEGACY_USERNAME.fullmatch(cleaned):
            raise ValueError(
                "Username must have 3–30 letters, digits, or underscores."
            )

        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        candidate = value.get_secret_value()

        if not 12 <= len(candidate) <= 128:
            raise ValueError(
                "Password must contain 12–128 characters."
            )

        if (
            not candidate.strip()
            or any(
                ord(c) < 32 or ord(c) == 127
                for c in candidate
            )
        ):
            raise ValueError(
                "Password must not be blank or contain control characters."
            )

        return value

    @field_validator(
        "first_name",
        "family_name",
        "street",
        "barangay",
        "city",
        "province",
        "country",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("This field cannot be blank.")

        return cleaned

    @field_validator("middle_name", "other_extension")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
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
        if (
            self.name_extension == "Other"
            and not self.other_extension
        ):
            raise ValueError(
                "Other name extension is required when selecting Other."
            )

        if (
            self.name_extension != "Other"
            and self.other_extension
        ):
            raise ValueError(
                "Other name extension must be blank unless Other is selected."
            )

        return self


class HandoutRegisterRequest(RegisterRequest):
    """Strict future public-registration payload using D1=9, D2=6.

    Additional fields are validated here but are NOT yet stored by
    the existing File 13 registration service.

    Do not expose registration until the consent timestamp and
    hashed authentication answers are persisted.
    """

    confirm_password: SecretStr = Field(
        repr=False,
        exclude=True,
    )

    privacy_consent: bool

    security_answer_1: SecretStr = Field(
        repr=False,
        exclude=True,
    )  # Q7

    security_answer_2: SecretStr = Field(
        repr=False,
        exclude=True,
    )  # Q2

    security_answer_3: SecretStr = Field(
        repr=False,
        exclude=True,
    )  # Q4

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not _STRICT_USERNAME.fullmatch(value):
            raise ValueError(
                "Username must start with a letter and "
                "contain letters and digits only."
            )

        if not USERNAME_MIN <= len(value) <= USERNAME_MAX:
            raise ValueError(
                f"Username must contain "
                f"{USERNAME_MIN}–{USERNAME_MAX} characters."
            )

        return value

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_length(cls, value: object) -> object:
        if (
            not isinstance(value, str)
            or len(value) > 100
            or any(ch.isspace() for ch in value)
        ):
            raise ValueError(
                "Email must be valid, contain no spaces, "
                "and be at most 100 characters."
            )

        return value

    @field_validator("password")
    @classmethod
    def validate_password(
        cls,
        value: SecretStr,
        info: ValidationInfo,
    ) -> SecretStr:
        candidate = value.get_secret_value()

        if not PASSWORD_MIN <= len(candidate) <= PASSWORD_MAX:
            raise ValueError(
                f"Password must contain "
                f"{PASSWORD_MIN}–{PASSWORD_MAX} characters."
            )

        if any(
            ord(c) < 32 or ord(c) == 127
            for c in candidate
        ):
            raise ValueError(
                "Password cannot contain control characters."
            )

        if password_strength(candidate) == "Weak":
            raise ValueError(
                "Weak passwords are not accepted; "
                "use at least three character groups."
            )

        username = info.data.get("username")

        if (
            isinstance(username, str)
            and username.casefold() in candidate.casefold()
        ):
            raise ValueError(
                "Password must not contain the username."
            )

        return value

    @field_validator("privacy_consent", mode="before")
    @classmethod
    def require_privacy_consent(cls, value: object) -> bool:
        if value is not True:
            raise ValueError(
                "You must agree to the Privacy Notice to register."
            )

        return True

    @field_validator(
        "first_name",
        "family_name",
        "street",
        "barangay",
        "city",
        "province",
        "country",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field = info.field_name

        if field == "street":
            if (
                not 3 <= len(value) <= 50
                or value != value.strip()
                or "  " in value
                or not all(
                    c.isalpha() or c.isdigit() or c == " "
                    for c in value
                )
            ):
                raise ValueError(
                    "Purok / Street must contain 3–50 letters, "
                    "digits and single spaces."
                )

            return value

        label = {
            "first_name": "First Name",
            "family_name": "Family Name",
            "barangay": "Barangay",
            "city": "Municipality / City",
            "province": "Province",
            "country": "Country",
        }[field]

        highest = (
            NAME_MAX
            if field in {"first_name", "family_name"}
            else (100 if field == "country" else 50)
        )

        return _check_title_case(
            value,
            label,
            2,
            highest,
        )

    @field_validator("middle_name", "other_extension")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None or value == "":
            return None

        if info.field_name == "middle_name":
            return _check_title_case(
                value,
                "Middle Name",
                2,
                NAME_MAX,
            )

        if value not in {"I", "II", "III", "IV", "IX", "X"}:
            raise ValueError(
                "Other name extension must be "
                "I, II, III, IV, IX, or X."
            )

        return value

    @field_validator("birthdate")
    @classmethod
    def validate_birthdate(cls, value: date) -> date:
        today = date.today()

        if value > today:
            raise ValueError(
                "Birthdate cannot be in the future."
            )

        age = (
            today.year
            - value.year
            - (
                (today.month, today.day)
                < (value.month, value.day)
            )
        )

        if age < 18:
            raise ValueError(
                "You must be at least 18 years old to register."
            )

        return value

    @field_validator(
        "security_answer_1",
        "security_answer_2",
        "security_answer_3",
    )
    @classmethod
    def validate_security_answer(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        answer = value.get_secret_value()

        if (
            not 2 <= len(answer) <= 50
            or answer != answer.strip()
            or "  " in answer
            or not all(
                ch.isalpha() or ch == " "
                for ch in answer
            )
        ):
            raise ValueError(
                "Security answer must contain 2–50 letters "
                "and single spaces only."
            )

        return value

    @model_validator(mode="after")
    def validate_confirm_password(self) -> Self:
        if not secrets.compare_digest(
            self.password.get_secret_value().encode("utf-8"),
            self.confirm_password.get_secret_value().encode("utf-8"),
        ):
            raise ValueError("Passwords do not match.")

        return self
