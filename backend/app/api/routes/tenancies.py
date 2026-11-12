
"""
DORMORA — SYSTEM FUNCTIONALITY FILE 36

CREATE: backend/app/api/routes/tenancies.py

Authenticated endpoints for File 35's tenancy service.

The File 37 runner integration must supply the verified session identity
resolver and Dormora's existing signed-CSRF verifier. Do not read user IDs,
account roles, or ownership claims from the browser. The service rechecks
roles and property ownership against PostgreSQL.

No tables are created here, and no invoices or payments are generated.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

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

from app.services.tenancy_service import (
    TenancyAccessError,
    TenancyConflictError,
    TenancyError,
    TenancyNotFoundError,
    TenancyValidationError,
    assign_tenant,
    end_tenancy,
    list_owner_tenancies,
    list_renter_tenancies,
)


IdentityResolver = Callable[[Request], int | Awaitable[int]]
CSRFVerifier = Callable[[Request], None | Awaitable[None]]


class AssignTenantRequest(BaseModel):
    """Room assignment details chosen by the verified property owner."""

    model_config = ConfigDict(extra="forbid")

    inquiry_id: int = Field(gt=0)

    room_label: str = Field(
        min_length=1,
        max_length=60,
    )

    move_in_date: date = Field(
        description="Agreed move-in date (YYYY-MM-DD).",
    )

    # Send as a decimal string, e.g. "5000.00".
    # Omit to use the property's current listing price.
    agreed_monthly_rent: str | None = Field(
        default=None,
        max_length=24,
    )

    rent_due_day: int = Field(
        default=1,
        ge=1,
        le=28,
        strict=True,
    )


class EndTenancyRequest(BaseModel):
    """Optional move-out date; omit to use the current local date."""

    model_config = ConfigDict(extra="forbid")

    move_out_date: date | None = None


def _service_error(error: TenancyError) -> HTTPException:
    """Map expected business errors to appropriate HTTP responses."""

    if isinstance(error, TenancyValidationError):
        code = status.HTTP_400_BAD_REQUEST
        detail = str(error)

    elif isinstance(error, TenancyAccessError):
        code = status.HTTP_403_FORBIDDEN
        detail = "Account is not eligible for this operation."

    elif isinstance(error, TenancyNotFoundError):
        code = status.HTTP_404_NOT_FOUND
        detail = "Tenancy or accepted inquiry not found."

    elif isinstance(error, TenancyConflictError):
        code = status.HTTP_409_CONFLICT
        detail = str(error)

    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "Tenancy operation failed."

    return HTTPException(
        status_code=code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def build_tenancies_router(
    *,
    verified_session_user_id: IdentityResolver,
    verify_signed_csrf: CSRFVerifier,
) -> APIRouter:
    """
    Attach tenancy routes to the authenticated functionality runner.

    Use the same trusted identity and signed-CSRF callbacks already
    used by the rental-inquiries router.

    File 35 verifies account roles and property ownership in PostgreSQL.
    """

    if not callable(verified_session_user_id):
        raise TypeError(
            "Verified session identity callback is required."
        )

    if not callable(verify_signed_csrf):
        raise TypeError(
            "Signed CSRF verification callback is required."
        )

    router = APIRouter(
        prefix="/api/tenancies",
        tags=["Tenant Management"],
    )

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

    def private_response(response: Response) -> None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"

    # -----------------------------------------------------
    # PROPERTY OWNER: List their own tenants
    # -----------------------------------------------------

    @router.get(
        "/owner",
        name="list_owner_tenancies",
        summary="List tenants of properties owned by the current account",
    )
    def owner_tenancies(
        response: Response,
        user_id: int = Depends(current_user_id),
    ):
        private_response(response)

        try:
            items = list_owner_tenancies(
                owner_user_id=user_id,
            )

        except TenancyError as error:
            raise _service_error(error) from error

        return {
            "tenancies": items,
            "count": len(items),
        }

    # -----------------------------------------------------
    # RENTER: View personal rental history
    # -----------------------------------------------------

    @router.get(
        "/mine",
        name="list_my_tenancies",
        summary="View the renter's own rental history",
    )
    def my_tenancies(
        response: Response,
        user_id: int = Depends(current_user_id),
    ):
        private_response(response)

        try:
            items = list_renter_tenancies(
                renter_user_id=user_id,
            )

        except TenancyError as error:
            raise _service_error(error) from error

        return {
            "tenancies": items,
            "count": len(items),
        }

    # -----------------------------------------------------
    # PROPERTY OWNER: Assign a renter to a room
    # -----------------------------------------------------

    @router.post(
        "/assign",
        name="assign_renter_to_room",
        status_code=status.HTTP_201_CREATED,
        summary="Assign an accepted renter inquiry to a room",
    )
    def create_tenancy(
        payload: AssignTenantRequest,
        response: Response,
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        private_response(response)

        try:
            result = assign_tenant(
                owner_user_id=user_id,
                inquiry_id=payload.inquiry_id,
                room_label=payload.room_label,
                move_in_date=payload.move_in_date,
                agreed_monthly_rent=payload.agreed_monthly_rent,
                rent_due_day=payload.rent_due_day,
            )

        except TenancyError as error:
            raise _service_error(error) from error

        return {
            "tenancy": result,
        }

    # -----------------------------------------------------
    # PROPERTY OWNER: End an existing tenancy
    # -----------------------------------------------------

    @router.post(
        "/{tenancy_id}/end",
        name="end_renter_tenancy",
        summary="End an active tenancy and release its room",
    )
    def close_tenancy(
        payload: EndTenancyRequest,
        response: Response,
        tenancy_id: Annotated[int, Path(gt=0)],
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        private_response(response)

        try:
            result = end_tenancy(
                owner_user_id=user_id,
                tenancy_id=tenancy_id,
                move_out_date=payload.move_out_date,
            )

        except TenancyError as error:
            raise _service_error(error) from error

        return {
            "tenancy": result,
        }

    return router
