
"""
DORMORA — SYSTEM FUNCTIONALITY FILE 30

CREATE: backend/app/api/routes/inquiry_messages.py

Private inquiry conversation endpoints. Connects the File 29 service to the
existing verified-session and signed-CSRF callbacks. File 31 must register
this router in backend/app/local_functionality_runner.py.

Do not accept user IDs or role claims from the browser.
No inquiry decisions, room assignments, or payments are changed here.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.services.inquiry_message_service import (
    InquiryMessageClosedError,
    InquiryMessageNotFoundError,
    InquiryMessageValidationError,
    InquiryMessagingError,
    get_inquiry_conversation,
    send_inquiry_reply,
)


IdentityResolver = Callable[[Request], int | Awaitable[int]]
CSRFVerifier = Callable[[Request], None | Awaitable[None]]


class SendInquiryReplyRequest(BaseModel):
    """Reply body; sender identity is taken from the verified session."""

    model_config = ConfigDict(extra="forbid")

    message_text: str = Field(
        min_length=1,
        max_length=1000,
        description="Text of the reply (maximum 1,000 characters).",
    )


def _service_http_error(error: InquiryMessagingError) -> HTTPException:
    """Expose only expected, user-safe service errors."""
    if isinstance(error, InquiryMessageValidationError):
        code = status.HTTP_400_BAD_REQUEST
        detail = str(error)
    elif isinstance(error, InquiryMessageNotFoundError):
        # Same response for missing and unauthorized conversations.
        code = status.HTTP_404_NOT_FOUND
        detail = "Inquiry not found."
    elif isinstance(error, InquiryMessageClosedError):
        code = status.HTTP_409_CONFLICT
        detail = str(error)
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "Unable to process the inquiry message."

    return HTTPException(
        status_code=code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def build_inquiry_messages_router(
    *,
    verified_session_user_id: IdentityResolver,
    verify_signed_csrf: CSRFVerifier,
) -> APIRouter:
    """Build message routes using Dormora's existing security callbacks.

    The caller must supply the trusted identity resolver from the already
    working session system and the same signed-CSRF verifier used for other
    state-changing endpoints. File 29 checks inquiry participant ownership.
    """
    if not callable(verified_session_user_id):
        raise TypeError("Verified session callback is required.")
    if not callable(verify_signed_csrf):
        raise TypeError("Signed CSRF callback is required.")

    router = APIRouter(
        prefix="/api/rental-inquiries",
        tags=["Inquiry Messages"],
    )

    async def current_user_id(request: Request) -> int:
        result = verified_session_user_id(request)
        if inspect.isawaitable(result):
            result = await result

        if type(result) is not int or result <= 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"Cache-Control": "no-store"},
            )
        return result

    async def require_csrf(request: Request) -> None:
        result = verify_signed_csrf(request)
        if inspect.isawaitable(result):
            await result

    @router.get(
        "/{inquiry_id}/messages",
        name="get_inquiry_messages",
        summary="View the private conversation for an inquiry",
    )
    def get_messages(
        response: Response,
        inquiry_id: Annotated[int, Path(gt=0)],
        user_id: int = Depends(current_user_id),
    ):
        """Only the inquiry's renter or actual property owner can read it."""
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
        try:
            return get_inquiry_conversation(
                user_id=user_id,
                inquiry_id=inquiry_id,
            )
        except InquiryMessagingError as error:
            raise _service_http_error(error) from error

    @router.post(
        "/{inquiry_id}/messages",
        name="send_inquiry_message",
        summary="Send a reply to an inquiry",
        status_code=status.HTTP_201_CREATED,
    )
    def post_message(
        payload: SendInquiryReplyRequest,
        response: Response,
        inquiry_id: Annotated[int, Path(gt=0)],
        user_id: int = Depends(current_user_id),
        _csrf: None = Depends(require_csrf),
    ):
        """Append a reply to a pending or accepted inquiry, with CSRF check."""
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
        try:
            return send_inquiry_reply(
                user_id=user_id,
                inquiry_id=inquiry_id,
                message_text=payload.message_text,
            )
        except InquiryMessagingError as error:
            raise _service_http_error(error) from error

    return router
