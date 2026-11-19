
"""Dormora FullStack 3 -- File 134: registration honeypot verification.

CREATE: backend/app/registration_honeypot_check.py
RUN:    python -m app.registration_honeypot_check --check

Read-only checks of the ACTUAL installed registration request models,
FastAPI route annotation, and the existing React registration form.

A populated `website` field must fail Pydantic validation BEFORE the
registration endpoint handler can create an account. A blank `website`
must not cause a honeypot-specific validation error. This checker deliberately
submits INCOMPLETE, synthetic data directly to Pydantic, so it cannot create
an account, call CAPTCHA, send OTP email, or write database rows.

IMPORTANT: This tests the schema/route linkage, not the full live HTTP path.
Leave File 129 and other working Dormora services unchanged.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import get_type_hints

from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent.parent
FRONTEND_FILE = PROJECT_DIR / "frontend" / "src" / "pages" / "RegisterPage.jsx"


class HoneypotCheckError(RuntimeError):
    """A required link or validation was not verified."""


def _has_website_validation_error(model: type[BaseModel], value: str) -> bool:
    """Test the website validator alone; other required fields are omitted.

    Pydantic validates supplied fields even when unrelated required fields
    are missing. Only errors located at `website` count for this test.
    """
    try:
        model.model_validate({"website": value})
    except ValidationError as error:
        return any(
            detail.get("loc", ())[:1] == ("website",)
            for detail in error.errors(include_input=False, include_context=False)
        )
    return False


def _check_schema() -> type[BaseModel]:
    from app.schemas.auth import HandoutRegisterRequest
    from app.api.routes.secure_registration import SecureRegistrationSubmission

    if not issubclass(SecureRegistrationSubmission, HandoutRegisterRequest):
        raise HoneypotCheckError(
            "The public registration payload no longer inherits the strict schema."
        )

    for model in (HandoutRegisterRequest, SecureRegistrationSubmission):
        if not issubclass(model, BaseModel):
            raise HoneypotCheckError("Registration model is not Pydantic-based.")
        field = model.model_fields.get("website")
        if field is None:
            raise HoneypotCheckError("Registration model has no website field.")
        if field.exclude is not True or field.repr is not False:
            raise HoneypotCheckError(
                "Honeypot must not be included in serialized account data."
            )
        if _has_website_validation_error(model, ""):
            raise HoneypotCheckError("An empty honeypot was rejected.")
        for filled in ("spam.example", "https://bot.invalid", " "):
            if not _has_website_validation_error(model, filled):
                raise HoneypotCheckError(
                    "A populated website field was not rejected by registration validation."
                )
    return SecureRegistrationSubmission


def _check_route(expected_model: type[BaseModel]) -> None:
    from app.api.routes import secure_registration

    matching = [
        route for route in secure_registration.router.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/auth/register"
        and "POST" in route.methods
    ]
    if len(matching) != 1:
        raise HoneypotCheckError(
            "Expected one POST /api/auth/register route in the secure registration router."
        )

    annotations = get_type_hints(matching[0].endpoint)
    if annotations.get("payload") is not expected_model:
        raise HoneypotCheckError(
            "The registration endpoint does not use the verified request schema."
        )


def _check_frontend() -> None:
    if not FRONTEND_FILE.is_file():
        raise HoneypotCheckError("frontend/src/pages/RegisterPage.jsx not found.")
    try:
        source = FRONTEND_FILE.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise HoneypotCheckError("Cannot read the registration JSX file.") from error

    if not re.search(r'\bname\s*=\s*["\']website["\']', source):
        raise HoneypotCheckError("React registration form lacks the website input.")
    if not re.search(r'\bwebsite\s*:\s*read\s*\(\s*["\']website["\']\s*\)', source):
        raise HoneypotCheckError(
            "React registration still does not send the actual website field value."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Dormora backend and frontend honeypot verification"
    )
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()

    try:
        model = _check_schema()
        _check_route(model)
        _check_frontend()
    except HoneypotCheckError as error:
        print("FILE 134 STOPPED:", str(error))
        raise SystemExit(1) from None
    except Exception as error:
        print("FILE 134 FAILED:", type(error).__name__)
        print("Inspect the installed registration schema, router, and React source.")
        raise SystemExit(1) from None

    print("DORMORA FILE 134 -- REGISTRATION HONEYPOT VERIFICATION")
    print("React input and submitted website value: VERIFIED")
    print("Strict backend and public route payload: VERIFIED")
    print("Empty honeypot field: ALLOWED by the honeypot validator")
    print("Populated honeypot field: REJECTED by both schemas")
    print("Registration route binds the checked Pydantic schema: VERIFIED")
    print("No HTTP request, CAPTCHA, OTP, account, or database write was made.")
    print("File 134 check OK")


if __name__ == "__main__":
    main()
