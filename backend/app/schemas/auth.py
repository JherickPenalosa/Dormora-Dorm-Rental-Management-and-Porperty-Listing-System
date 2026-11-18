"""Dormora registration schemas — Backend File 14 (Requirement Validation continuation).

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

File 14 adds an OPTIONAL normalized contact_number field to the strict
registration model, matching File 13 AES-256-GCM input rules. It stays
optional until File 15 persistence and a later frontend form are integrated.
A contact submitted before then is NOT SAVED by the existing registration
service; do not use registration to collect actual phone numbers yet.

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
USERNAME_MIN = 6  # Instructor uniform requirement
USERNAME_MAX = 20  # Instructor uniform requirement
PASSWORD_MIN = 8  # Instructor uniform requirement
PASSWORD_MAX = 64
NAME_MAX = 50  # Instructor uniform requirement
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
# Match the normalization accepted by File 13 AES-256 private-contact storage.
_CONTACT_NUMBER_PATTERN = re.compile(r"\+?[0-9][0-9() .-]{5,24}\Z")


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
            raise ValueError("Username must have 3–30 letters, digits, or underscores.")
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
            raise ValueError("Password must contain 12–128 characters.")
        if not candidate.strip() or any(ord(c) < 32 or ord(c) == 127 for c in candidate):
            raise ValueError("Password must not be blank or contain control characters.")
        return value

    @field_validator("first_name", "family_name", "street", "barangay", "city", "province", "country")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
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
            raise ValueError("Other name extension is required when selectingOther.")
        if self.name_extension != "Other" and self.other_extension:
            raise ValueError("Other name extension must be blank unless Otheris selected.")
        return self


class HandoutRegisterRequest(RegisterRequest):
    """Strict future public-registration payload, using D1=9 and D2=6.

    Adds consent, password confirmation, and Q7/Q2/Q4 answers; these fields
    are validated, NOT yet stored by File 13. Do NOT expose registration until
    a service persists consent time and securely hashes/stores the answers.
    """

    confirm_password: SecretStr = Field(repr=False, exclude=True)
    privacy_consent: bool
    # Transition field: OPTIONAL to preserve the currently working registration
    # UI while backend persistence and frontend collection are integrated.
    # Never put a contact number in application logs, error replies, or model_dump.
    # This field does not make contact numbers unique; families may share one.
    contact_number: str | None = Field(
        default=None, max_length=26, repr=False, exclude=True,
    )
    # Three required questions selected by the user.
    security_question_1: Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"] = Field(...)
    security_question_2: Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"] = Field(...)
    security_question_3: Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"] = Field(...)

    security_answer_1: SecretStr = Field(repr=False, exclude=True)  # Q7
    security_answer_2: SecretStr = Field(repr=False, exclude=True)  # Q2
    security_answer_3: SecretStr = Field(repr=False, exclude=True)  # Q4

    @field_validator("contact_number", mode="before")
    @classmethod
    def validate_contact_number(cls, value: object) -> str | None:
        """Normalize safely for File 13 encryption (7–15 digits, optional +).

        Spaces, hyphens, dots and parentheses are formatting only. The
        canonical form is digits, optionally prefixed with +. This is data
        validation only; actual encrypted persistence is wired in a later file.
        """
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("Enter a valid contact number.")
        stripped = value.strip()
        if len(stripped) > 26 or not _CONTACT_NUMBER_PATTERN.fullmatch(stripped):
            raise ValueError("Enter a valid contact number (7–15 digits).")
        digits = "".join(character for character in stripped if character.isdigit())
        if not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid contact number (7–15 digits).")
        return ("+" if stripped.startswith("+") else "") + digits

    @model_validator(mode="after")
    def validate_distinct_selected_questions(self):
        selected = (
            self.security_question_1,
            self.security_question_2,
            self.security_question_3,
        )
        if len(set(selected)) != 3:
            raise ValueError("Choose three different security questions.")
        return self

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Four PROVISIONAL renter fields (public.renter_preferences).
    preferred_rental_type: Literal["shared", "private", "either"] | None = Field(
        default=None,
        validation_alias=AliasChoices("preferred_rental_type", "preferredRentalType"),
    )
    preferred_rental_area: str | None = Field(
        default=None,
        validation_alias=AliasChoices("preferred_rental_area", "preferredRentalArea"),
    )
    maximum_monthly_budget: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        allow_inf_nan=False,
        validation_alias=AliasChoices("maximum_monthly_budget", "monthlyBudget"),
    )
    target_move_in_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("target_move_in_date", "targetMoveInDate"),
    )

    # Four PROVISIONAL owner fields (public.property_owner_details).
    primary_property_type: Literal[
        "dormitory", "boarding-house", "apartment", "room"
    ] | None = Field(
        default=None,
        validation_alias=AliasChoices("primary_property_type", "primaryPropertyType"),
    )
    primary_property_area: str | None = Field(
        default=None,
        validation_alias=AliasChoices("primary_property_area", "primaryPropertyArea"),
    )
    expected_monthly_rent: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        allow_inf_nan=False,
        validation_alias=AliasChoices("expected_monthly_rent", "expectedRent"),
    )
    expected_availability_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("expected_availability_date", "expectedAvailableDate"),
    )


    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not _STRICT_USERNAME.fullmatch(value):
            raise ValueError("Username must start with a letter and contain letters and digits only.")
        if not USERNAME_MIN <= len(value) <= USERNAME_MAX:
            raise ValueError(f"Username must contain {USERNAME_MIN}–{USERNAME_MAX} characters.")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_length(cls, value: object) -> object:
        if not isinstance(value, str) or len(value) > 100 or any(ch.isspace()for ch in value):
            raise ValueError("Email must be valid, contain no spaces, and be at most 100 characters.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        candidate = value.get_secret_value()
        if not PASSWORD_MIN <= len(candidate) <= PASSWORD_MAX:
            raise ValueError(f"Password must contain {PASSWORD_MIN}–{PASSWORD_MAX} characters.")
        if any(ord(c) < 32 or ord(c) == 127 for c in candidate):
            raise ValueError("Password cannot contain control characters.")
        if password_strength(candidate) == "Weak":
            raise ValueError("Weak passwords are not accepted; use at least three character groups.")
        username = info.data.get("username")
        if isinstance(username, str) and username.casefold() in candidate.casefold():
            raise ValueError("Password must not contain the username.")
        return value

    @field_validator("privacy_consent", mode="before")
    @classmethod
    def require_privacy_consent(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("You must agree to the Privacy Notice to register.")
        return True

    @field_validator("first_name", "family_name", "street", "barangay", "city", "province", "country")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        field = info.field_name
        if field == "street":
            if (
                not 3 <= len(value) <= 50
                or value != value.strip()
                or "  " in value
                or not all(c.isalpha() or c.isdigit() or c == " " for c in value)
            ):
                raise ValueError("Purok / Street must contain 3–50 letters,digits and single spaces.")
            return value
        label = {
            "first_name": "First Name",
            "family_name": "Family Name",
            "barangay": "Barangay",
            "city": "Municipality / City",
            "province": "Province",
            "country": "Country",
        }[field]
        highest = NAME_MAX if field in {"first_name", "family_name"} else (100 if field == "country" else 50)
        return _check_title_case(value, label, 2, highest)

    @field_validator("middle_name", "other_extension")
    @classmethod
    def normalize_optional_text(cls, value: str | None, info: ValidationInfo)-> str | None:
        if value is None or value == "":
            return None
        if info.field_name == "middle_name":
            return _check_title_case(value, "Middle Name", 2, NAME_MAX)
        if value not in {"I", "II", "III", "IV", "IX", "X"}:
            raise ValueError("Other name extension must be I, II, III, IV, IX, or X.")
        return value

    @field_validator("birthdate")
    @classmethod
    def validate_birthdate(cls, value: date) -> date:
        today = date.today()
        if value > today:
            raise ValueError("Birthdate cannot be in the future.")
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise ValueError("You must be at least 18 years old to register.")
        return value

    @field_validator("security_answer_1", "security_answer_2", "security_answer_3")
    @classmethod
    def validate_security_answer(cls, value: SecretStr) -> SecretStr:
        answer = value.get_secret_value()
        if (
            not 2 <= len(answer) <= 50
            or answer != answer.strip()
            or "  " in answer
            or not all(ch.isalpha() or ch == " " for ch in answer)
        ):
            raise ValueError("Security answer must contain 2–50 letters andsingle spaces only.")
        return value

    @model_validator(mode="after")
    def validate_confirm_password(self) -> Self:
        if not secrets.compare_digest(
            self.password.get_secret_value().encode("utf-8"),
            self.confirm_password.get_secret_value().encode("utf-8"),
        ):
            raise ValueError("Passwords do not match.")
        return self


    # ---- File 51: optional Dormora-specific fields validation ----

    @field_validator("preferred_rental_type", "primary_property_type", mode="before")
    @classmethod
    def validate_dropdown(cls, value: object, info: ValidationInfo) -> str | None:
        if value is None or value == "":
            return None
        choices = (
            RENTER_TYPES if info.field_name == "preferred_rental_type"
            else PROPERTY_TYPES
        )
        if not isinstance(value, str) or value not in choices:
            label = (
                "Preferred Rental Type" if info.field_name == "preferred_rental_type"
                else "Primary Property Type"
            )
            raise ValueError(
                f"{label} must be one of: {', '.join(choices)}."
            )
        return value

    @field_validator("preferred_rental_area", "primary_property_area", mode="before")
    @classmethod
    def validate_area(cls, value: object, info: ValidationInfo) -> str | None:
        if value is None or value == "":
            return None
        label = (
            "Preferred Rental Area" if info.field_name == "preferred_rental_area"
            else "Primary Property Area"
        )
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text.")
        if not MIN_AREA_LENGTH <= len(value) <= MAX_AREA_LENGTH:
            raise ValueError(
                f"{label} must contain {MIN_AREA_LENGTH}–{MAX_AREA_LENGTH} characters."
            )
        if value != value.strip() or "  " in value:
            raise ValueError(f"{label} must not contain extra or double spaces.")
        # A location can contain letters, numbers, single spaces and limited
        # punctuation (e.g. "Brgy. 2, Butuan City"). No markup/control chars.
        if not all(
            ch.isalpha() or ch.isdigit() or ch in " .,'-"
            for ch in value
        ):
            raise ValueError(
                f"{label} may contain letters, digits, spaces, commas, "
                "periods, apostrophes and hyphens only."
            )
        if not any(ch.isalpha() for ch in value):
            raise ValueError(f"{label} must contain at least one letter.")
        return value

    @field_validator("maximum_monthly_budget", "expected_monthly_rent", mode="before")
    @classmethod
    def validate_money(cls, value: object, info: ValidationInfo) -> Decimal |None:
        if value is None or value == "":
            return None
        label = (
            "Maximum Monthly Budget" if info.field_name == "maximum_monthly_budget"
            else "Expected Monthly Rent"
        )
        # React number inputs submit text. Reject floats/booleans, exponents,
        # negative amounts, separators and more than two decimal places.
        if type(value) not in (str, int, Decimal):
            raise ValueError(f"{label} must be a positive amount with at most2 decimals.")
        raw = str(value)
        if not _MONEY_PATTERN.fullmatch(raw):
            raise ValueError(
                f"{label} must be a positive amount with at most 2 decimals."
            )
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError(f"{label} must be greater than zero.")
        return amount

    @field_validator("target_move_in_date", "expected_availability_date", mode="before")
    @classmethod
    def validate_date(cls, value: object, info: ValidationInfo) -> date | None:
        if value is None or value == "":
            return None
        label = (
            "Target Move-in Date" if info.field_name == "target_move_in_date"
            else "Expected Availability Date"
        )
        if type(value) is date:
            selected = value
        elif isinstance(value, str) and _ROLE_DATE_PATTERN.fullmatch(value):
            try:
                selected = date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"{label} must be a valid YYYY-MM-DD date.")from None
        else:
            raise ValueError(f"{label} must be a valid YYYY-MM-DD date.")
        if selected < date.today():
            raise ValueError(f"{label} cannot be in the past.")
        return selected

    @model_validator(mode="after")
    def validate_role_fields(self) -> Self:
        if self.role == "renter" and any(
            value is not None
            for value in (
                self.primary_property_type,
                self.primary_property_area,
                self.expected_monthly_rent,
                self.expected_availability_date,
            )
        ):
            raise ValueError("Property-owner fields cannot be sent by renter accounts.")
        if self.role == "property_owner" and any(
            value is not None
            for value in (
                self.preferred_rental_type,
                self.preferred_rental_area,
                self.maximum_monthly_budget,
                self.target_move_in_date,
            )
        ):
            raise ValueError("Renter preference fields cannot be sent by property-owner accounts.")
        return self

    @property
    def target_table(self) -> str:
        """Return the existing role detail table name (not user-controlled SQL)."""
        return (
            "renter_preferences" if self.role == "renter"
            else "property_owner_details"
        )

    def role_specific_db_values(self) -> dict[str, str | Decimal | date | None]:
        """Return exactly the four relevant existing DB columns (no user_id).

        File 52 must merge these values into the same INSERT that includes
        the new account's user_id, inside its atomic registration transaction.
        """
        if self.role == "renter":
            return {
                "preferred_rental_type": self.preferred_rental_type,
                "preferred_rental_area": self.preferred_rental_area,
                "maximum_monthly_budget": self.maximum_monthly_budget,
                "target_move_in_date": self.target_move_in_date,
            }
        return {
            "primary_property_type": self.primary_property_type,
            "primary_property_area": self.primary_property_area,
            "expected_monthly_rent": self.expected_monthly_rent,
            "expected_availability_date": self.expected_availability_date,
        }
