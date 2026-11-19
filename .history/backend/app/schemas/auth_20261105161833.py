return value

    @model_validator(mode="after")
    def validate_name_extension(self) -> Self:
        if self.name_extension == "Other" and not self.other_extension:
            raise ValueError("Other name extension is required when selecting Other.")
        if self.name_extension != "Other" and self.other_extension:
            raise ValueError("Other name extension must be blank unless Other is selected.")
        return self


class HandoutRegisterRequest(RegisterRequest):
    """Strict future public-registration payload, using D1=9 and D2=6.

    Adds consent, password confirmation, and Q7/Q2/Q4 answers; these fields
    are validated, NOT yet stored by File 13. Do NOT expose registration until
    a service persists consent time and securely hashes/stores the answers.
    """

    confirm_password: SecretStr = Field(repr=False, exclude=True)
    privacy_consent: bool
    security_answer_1: SecretStr = Field(repr=False, exclude=True)  # Q7
    security_answer_2: SecretStr = Field(repr=False, exclude=True)  # Q2
    security_answer_3: SecretStr = Field(repr=False, exclude=True)  # Q4

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
        if not isinstance(value, str) or len(value) > 100 or any(ch.isspace() for ch in value):
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
                raise ValueError("Purok / Street must contain 3–50 letters, digits and single spaces.")
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
    def normalize_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
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