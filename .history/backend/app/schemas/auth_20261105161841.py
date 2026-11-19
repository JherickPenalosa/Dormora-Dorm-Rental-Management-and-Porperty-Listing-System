
"""Dormora registration schemas — Backend File 51.

Destination: backend/app/schemas/auth.py (full replacement of File 40).

The old RegisterRequest remains available for unmounted development workflows.
HandoutRegisterRequest adds STRICT, student-seeded checks for future public
registration. Do not mount the public registration route yet: privacy consent
must be persisted, security answers must be hashed/stored, approved CAPTCHA
must be integrated, and system-specific fields must be validated and saved.

File 51 validates the 4 optional renter / 4 optional owner preview fields
against the existing role-specific tables. These exact requirements are still
PROVISIONAL until compared against the instructor-approved proposal.
File 52 must persist these values inside the existing registration transaction.

This module does not connect to PostgreSQL, send emails, or create accounts.
"""

import re
import secrets
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)


# From the confirmed student seed (last two digits: 96).
STUDENT_D1 = 9
STUDENT_D2 = 6
USERNAME_MIN = 6 + STUDENT_D1 % 3                # 6
USERNAME_MAX = 16 + STUDENT_D2 % 5               # 17
PASSWORD_MIN = 8 + STUDENT_D2 % 4                # 10
PASSWORD_MAX = 64
NAME_MAX = 20 + STUDENT_D2                     # 26
SECURITY_QUESTION_IDS = (
    STUDENT_D2 % 8 + 1,                         # Q7
    (STUDENT_D2 + 3) % 8 + 1,                   # Q2
    (STUDENT_D2 + 5) % 8 + 1,                   # Q4
)

# File 51 provisional system-specific validation: existing React preview/UI.
# Cross-check exact rules and required/optional flags with signed proposal.
RENTER_TYPES = ("shared", "private", "either")
PROPERTY_TYPES = ("dormitory", "boarding-house", "apartment", "room")
MIN_AREA_LENGTH = 3
MAX_AREA_LENGTH = 100
_MONEY_PATTERN = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,2})?\Z")
_ROLE_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")

_LEGACY_USERNAME = re.compile(r"[A-Za-z0-9_]{3,30}\Z")
_STRICT_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")


def password_strength(password: str) -> Literal["Weak", "Medium", "Strong"]:
    """Design decision: <3 character groups is Weak, 3 Medium, 4 Strong.

    Groups: lowercase, uppercase, digits, symbols. A Strong password has
    all four groups and at least 12 characters. Weak is never accepted.
    Length rules are enforced separately by the request validator.
    """
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    groups = sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() and not c.isspace() for c in password),
        )
    )
    if groups < 3:
        return "Weak"
    if groups == 4 and len(password) >= 12:
        return "Strong"
    return "Medium"


def _check_title_case(value: str, label: str, minimum: int, maximum: int) -> str:
    """Enforce the handout's name/title-case rules without silent trimming."""
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} must have {minimum}–{maximum} characters.")
    if value != value.strip() or "  " in value:
        raise ValueError(f"{label} must not contain extra or double spaces.")
    if not all(c.isalpha() or c == " " for c in value):
        raise ValueError(f"{label} may contain letters and single spaces only.")
    if value == value.upper():
        raise ValueError(f"{label} must not use all capital letters.")
    if any(value_part != value_part[0].upper() + value_part[1:].lower()
           for value_part in value.split(" ")):
        raise ValueError(f"{label} must use Title Case.")
    folded = value.casefold()
    if any(
        folded[i] == folded[i + 1] == folded[i + 2]
        and folded[i].isalpha()
        for i in range(len(folded) - 2)
    ):
        raise ValueError(f"{label} cannot contain three identical letters in a row.")
    return value


class RegisterRequest(BaseModel):
    """Existing internal request (Files 12/32) retained for compatibility.

    NOT the public handout-compliant registration schema. The future public
    route must require HandoutRegisterRequest and persist its extra fields.
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=30)
    email: EmailStr = Field(max_length=255)
    password: SecretStr
    role: Literal["renter", "property_owner"]

    # Honeypot; exclude from serialized payload and never store it.
    website: str = Field(default="", max_length=255, exclude=True, repr=False)

