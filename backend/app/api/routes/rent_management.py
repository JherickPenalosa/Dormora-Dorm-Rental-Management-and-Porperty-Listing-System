
"""Dormora — System Functionality File 44.

CREATE: backend/app/api/routes/rent_management.py

Authenticated rent ledger endpoints for File 43's service. File 45 must
register this router with the already-working server-side session resolver
and signed-CSRF verifier in local_functionality_runner.py.

No online payments, table creation, or automatic billing occurs here.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from app.services.rent_management_service import (
    RentAccessError,
    RentConflictError,
    RentManagementError,
    RentNotFoundError,
    RentValidationError,
    create_monthly_rent_charge,
    list_charge_payments,
    list_owner_rent_records,
    list_renter_rent_records,
    record_rent_payment,
)


IdentityResolver = Callable[[Request], int | Awaitable[int]]
CSRFVerifier = Callable[[Request], None | Awaitable[None]]


class CreateMonthlyChargeRequest(BaseModel):
    """Create one charge for a tenancy and month (no automatic prorating)."""

    model_config = ConfigDict(extra="forbid")

    tenancy_id: int = Field(gt=0, strict=True)
    billing_month: str = Field(
        min_length=7,
        max_length=10,
        description="Billing period: YYYY-MM or YYYY-MM-01.",
    )


class RecordRentPaymentRequest(BaseModel):
    """Record a payment the owner has already received outside Dormora."""

    model_config = ConfigDict(extra="forbid")

    charge_id: int = Field(gt=0, strict=True)
    amount: str = Field(
        min_length=1,
        max_length=24,
        description='Exact positive peso amount, e.g. "2000.00".',
    )
    payment_method: Literal[
        "cash", "bank_transfer", "e_wallet", "other"
    ]
    paid_on: str | None = Field(
        default=None,
        max_length=10,
        description="Payment date YYYY-MM-DD; omit for today in Manila.",
    )
    reference_note: str | None = Field(
        default=None,
        max_length=200,
        description="Optional reference or note; do not include secrets.",
    )


def _service_error(exc: RentManagementError) -> HTTPException:
    """Map expected business failures; never expose raw database exceptions."""
    if isinstance(exc, RentValidationError):
        code, detail = status.HTTP_400_BAD_REQUEST, str(exc)
    elif isinstance(exc, RentAccessError):
        code, detail = (
            status.HTTP_403_FORBIDDEN,
            "Account is not eligible for this rent operation.",
        )
    elif isinstance(exc, RentNotFoundError):
        code, detail = status.HTTP_404_NOT_FOUND, "Rent record not found."
    elif isinstance(exc, RentConflictError):
        code, detail = status.HTTP_409_CONFLICT, str(exc)
    else:
        code, detail = (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Rent management operation failed.",
        )
    return HTTPException(
        status_code=code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def build_rent_management_router(
    *,
    verified_session_user_id: IdentityResolver,
    verify_signed_csrf: CSRFVerifier,
) -> APIRouter:
    """Build routes using the same trusted callbacks as rental inquiries.

    The identity resolver must obtain the user ID from the server-side session.
    File 43 independently checks account roles and property/tenancy ownership.
    Never pass a browser-supplied account ID to these service functions.
    """
    if not callable(verified_session_user_id):
        raise TypeError("Verified session callback is required.")
    if not callable(verify_signed_csrf):
        raise TypeError("Signed CSRF callback is required.")

    router = APIRouter(prefix="/api/rent-records", tags=["Rent Management"])

    async def current_user_id(request: Request) -> int:
        user_id = verified_session_user_id(request)
        if inspect.isawaitable(user_id):
            user_id = await user_id
        if type(user_id) is not int or user_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"Cache-Control": "no-store"},
            )
        return user_id

    async def require_csrf(request: Request) -> None:
        result = verify_signed_csrf(request)
        if inspect.isawaitable(result):
            await result

    def mark_private(response: Response) -> None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"

    @router.get(
        "/owner",
        name="owner_rent_records",
        summary="List rent charges and balances for the owner's properties",
    )
    def owner_records(
        response: Response,
        user_id: int = Depends(current_user_id),
    ):
        mark_private(response)
        try:
            rows = list_owner_rent_records(owner_user_id=user_id)
        except RentManagementError as exc:
            raise _service_error(exc) from exc
        return {"records": rows, "count": len(rows)}

    @router.get(
        "/mine",
        name="renter_rent_records",
        summary="List the renter's own rent charges and balances",
    )
    def my_records(
        response: Response,
        user_id: int = Depends(current_user_id),
    ):
        mark_private(response)
        try:
            rows = list_renter_rent_records(renter_user_id=user_id)
        except RentManagementError as exc:
            raise _service_error(exc) from exc
        return {"records": rows, "count": len(rows)}

    @router.get(
        "/charges/{charge_id}/payments",
        name="charge_payment_history",
        summary="View payments recorded against an accessible rent charge",
    )
    def charge_payments(
        response: Response,
        charge_id: Annotated[int, Path(gt=0)],
        user_id: int = Depends(current_user_id),
    ):
        mark_private(response)
        try:
            rows = list_charge_payments(user_id=user_id, charge_id=charge_id)
        except RentManagementError as exc:
            raise _service_error(exc) from exc
        return {"payments": rows, "count": len(rows), "charge_id": charge_id}

    @router.post(
        "/charges",
        status_code=status.HTTP_201_CREATED,
        name="create_monthly_rent_charge",
        summary="Owner creates a monthly rent charge for a tenancy",
    )
    def create_charge(
        payload: CreateMonthlyChargeRequest,
        response: Response,
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        mark_private(response)
        try:
            charge = create_monthly_rent_charge(
                owner_user_id=user_id,
                tenancy_id=payload.tenancy_id,
                billing_month=payload.billing_month,
            )
        except RentManagementError as exc:
            raise _service_error(exc) from exc
        return {"charge": charge}

    @router.post(
        "/payments",
        status_code=status.HTTP_201_CREATED,
        name="record_rent_payment",
        summary="Owner records a payment already received outside Dormora",
    )
    def add_payment(
        payload: RecordRentPaymentRequest,
        response: Response,
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        mark_private(response)
        try:
            payment = record_rent_payment(
                owner_user_id=user_id,
                charge_id=payload.charge_id,
                amount=payload.amount,
                payment_method=payload.payment_method,
                paid_on=payload.paid_on,
                reference_note=payload.reference_note,
            )
        except RentManagementError as exc:
            raise _service_error(exc) from exc
        return {"payment": payment}

    return router
