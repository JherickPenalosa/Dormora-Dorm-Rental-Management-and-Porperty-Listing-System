
"""Dormora registration API router (not yet mounted in main.py).

Backend File 14 — destination: backend/app/api/routes/auth.py

This module prepares the HTTP contract for registration. Do not include the
router in main.py until required CAPTCHA, email OTP initiation, and other
registration protections are integrated. Importing this module does not
create an account or change database records.
"""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.auth import RegisterRequest
from app.services.registration import (
    DuplicateRegistrationError,
    RegistrationResult,
    register_user,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class RegistrationResponse(BaseModel):
    """Safe public response; excludes password hashes and profile identifiers."""

    user_id: int
    username: str
    email: EmailStr
    role: Literal["renter", "property_owner"]
    account_status: Literal["pending_verification"]
    message: str


def get_registration_service() -> Callable[[RegisterRequest], RegistrationResult]:
    """Supply the registration service (can be replaced during API tests)."""
    return register_user


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pending account (not yet publicly enabled)",
    responses={
        409: {"description": "Registration details conflict with an existing record."},
        503: {"description": "Database unavailable."},
    },
)
def register_account(
    payload: RegisterRequest,
    registration_service: Annotated[
        Callable[[RegisterRequest], RegistrationResult],
        Depends(get_registration_service),
    ],
) -> RegistrationResponse:
    """Prepare registration handling; only mount after security controls exist.

    FastAPI performs input validation using File 12. File 13 then performs
    password hashing and atomic database inserts. This route does not send an
    OTP or mark an email as verified.
    """
    try:
        result = registration_service(payload)
    except DuplicateRegistrationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration information conflicts with an existing account.",
        ) from None
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
        ) from None

    return RegistrationResponse(
        user_id=result.user_id,
        username=result.username,
        email=result.email,
        role=result.role,
        account_status="pending_verification",
        message="Account created. Email verification is required before login.",
    )
