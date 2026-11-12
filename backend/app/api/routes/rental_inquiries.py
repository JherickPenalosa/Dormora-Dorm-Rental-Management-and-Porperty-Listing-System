
"""
DORMORA — SYSTEM FUNCTIONALITY FILE 21

CREATE:
backend/app/api/routes/rental_inquiries.py

Authenticated Rental Inquiry API.

Connects File 20's service to FastAPI.

The functionality runner must supply:
- A verified, server-side session identity callback
- The existing signed CSRF verification callback

No account identity is accepted from request bodies.
All POST requests require CSRF verification.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Request,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from app.services.rental_inquiry_service import (
    RentalInquiryError,
    InquiryValidationError,
    InquiryAccessError,
    InquiryNotFoundError,
    InquiryConflictError,
    create_rental_inquiry,
    list_renter_inquiries,
    list_owner_inquiries,
    review_rental_inquiry,
    withdraw_rental_inquiry,
)


IdentityResolver = Callable[
    [Request],
    int | Awaitable[int],
]

CSRFVerifier = Callable[
    [Request],
    None | Awaitable[None],
]


class CreateInquiryRequest(BaseModel):
    """Data supplied by a renter when creating an inquiry."""

    model_config = ConfigDict(extra="forbid")

    property_id: int = Field(
        gt=0,
        description="Published property ID.",
    )

    message: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional message to the property owner.",
    )

    preferred_move_in_date: str | None = Field(
        default=None,
        description="Optional preferred date in YYYY-MM-DD format.",
    )


class ReviewInquiryRequest(BaseModel):
    """Owner decision on a pending inquiry."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected"]


def _http_error(error: RentalInquiryError) -> HTTPException:
    """
    Convert expected service errors to appropriate HTTP responses.

    Unexpected database errors are not exposed to users.
    """

    if isinstance(error, InquiryValidationError):
        code = status.HTTP_400_BAD_REQUEST

    elif isinstance(error, InquiryAccessError):
        code = status.HTTP_403_FORBIDDEN

    elif isinstance(error, InquiryNotFoundError):
        code = status.HTTP_404_NOT_FOUND

    elif isinstance(error, InquiryConflictError):
        code = status.HTTP_409_CONFLICT

    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rental inquiry operation failed.",
        )

    return HTTPException(
        status_code=code,
        detail=str(error),
    )


def build_rental_inquiries_router(
    *,
    verified_session_user_id: IdentityResolver,
    verify_signed_csrf: CSRFVerifier,
) -> APIRouter:
    """
    Build inquiry routes using the existing security callbacks.

    IMPORTANT:
    verified_session_user_id must return the actual user ID
    from a validated server-side session.

    File 20 independently checks account role, activity,
    and email verification before database operations.
    """

    if not callable(verified_session_user_id):
        raise TypeError(
            "Verified session callback is required."
        )

    if not callable(verify_signed_csrf):
        raise TypeError(
            "Signed CSRF verification callback is required."
        )

    router = APIRouter(
        prefix="/api/rental-inquiries",
        tags=["Rental Inquiries"],
    )

    async def current_user_id(request: Request) -> int:
        """
        Resolve the authenticated account using Dormora's
        trusted session system.
        """

        result = verified_session_user_id(request)

        if inspect.isawaitable(result):
            result = await result

        if type(result) is not int or result <= 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )

        return result

    async def require_csrf(request: Request) -> None:
        """
        Apply the existing signed CSRF protection
        to state-changing requests.
        """

        result = verify_signed_csrf(request)

        if inspect.isawaitable(result):
            await result

    # ----------------------------------------------------
    # RENTER: Submit an inquiry
    # ----------------------------------------------------

    @router.post(
        "",
        name="create_rental_inquiry",
        status_code=status.HTTP_201_CREATED,
    )
    def submit_inquiry(
        payload: CreateInquiryRequest,
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        """
        Submit one pending inquiry.

        Only active, verified renter accounts may submit.

        A rental inquiry does not reserve a room.
        """

        try:
            result = create_rental_inquiry(
                renter_user_id=user_id,
                property_id=payload.property_id,
                message=payload.message,
                preferred_move_in_date=(
                    payload.preferred_move_in_date
                ),
            )

            return result

        except RentalInquiryError as exc:
            raise _http_error(exc) from exc

    # ----------------------------------------------------
    # RENTER: View own inquiries
    # ----------------------------------------------------

    @router.get(
        "/mine",
        name="list_my_rental_inquiries",
    )
    def my_inquiries(
        user_id: int = Depends(current_user_id),
    ):
        """
        Return inquiries belonging only to the
        authenticated renter.
        """

        try:
            inquiries = list_renter_inquiries(
                renter_user_id=user_id,
            )

            return {
                "inquiries": inquiries,
                "count": len(inquiries),
            }

        except RentalInquiryError as exc:
            raise _http_error(exc) from exc

    # ----------------------------------------------------
    # PROPERTY OWNER: View received inquiries
    # ----------------------------------------------------

    @router.get(
        "/owner",
        name="list_owner_rental_inquiries",
    )
    def received_inquiries(
        user_id: int = Depends(current_user_id),
    ):
        """
        Return inquiries for properties belonging
        to the authenticated property owner.
        """

        try:
            inquiries = list_owner_inquiries(
                owner_user_id=user_id,
            )

            return {
                "inquiries": inquiries,
                "count": len(inquiries),
            }

        except RentalInquiryError as exc:
            raise _http_error(exc) from exc

    # ----------------------------------------------------
    # PROPERTY OWNER: Accept or reject an inquiry
    # ----------------------------------------------------

    @router.post(
        "/{inquiry_id}/review",
        name="review_rental_inquiry",
    )
    def review_inquiry(
        payload: ReviewInquiryRequest,
        inquiry_id: int = Path(gt=0),
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        """
        Accept or reject a pending inquiry.

        Only the owner of the associated property
        can review the request.

        Accepting an inquiry is NOT tenant assignment.
        """

        try:
            return review_rental_inquiry(
                owner_user_id=user_id,
                inquiry_id=inquiry_id,
                decision=payload.decision,
            )

        except RentalInquiryError as exc:
            raise _http_error(exc) from exc

    # ----------------------------------------------------
    # RENTER: Withdraw a pending inquiry
    # ----------------------------------------------------

    @router.post(
        "/{inquiry_id}/withdraw",
        name="withdraw_rental_inquiry",
    )
    def withdraw_inquiry(
        inquiry_id: int = Path(gt=0),
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        """
        Withdraw an inquiry owned by the authenticated renter.

        Only pending inquiries can be withdrawn.
        """

        try:
            return withdraw_rental_inquiry(
                renter_user_id=user_id,
                inquiry_id=inquiry_id,
            )

        except RentalInquiryError as exc:
            raise _http_error(exc) from exc

    return router
