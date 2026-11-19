
"""Dormora — System Functionality File 65.

CREATE: backend/app/api/routes/admin_property_directory.py

Admin-only, read-only property-listing directory API built on File 64.
File 66 must register this router using the existing Admin-only verified
session identity callback from the corrected File 62 runner.

No database migrations, account/listing mutations, or browser-supplied IDs.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status as http_status

from app.services.admin_property_directory_service import (
    AdminPropertyDirectoryAccessError,
    AdminPropertyDirectoryError,
    AdminPropertyDirectoryValidationError,
    get_admin_property_directory,
)


IdentityResolver = Callable[[Request], int | Awaitable[int]]


def build_admin_property_directory_router(
    *,
    verified_session_user_id: IdentityResolver,
) -> APIRouter:
    """Build the directory router using a trusted server-side session.

    IMPORTANT: File 66 must pass the Admin-only resolver, e.g.
    verified_admin_directory_user_id, NOT verified_inquiry_user_id.
    File 64 independently verifies the current database account is an
    active, email-verified Admin before exposing any listing data.
    """
    if not callable(verified_session_user_id):
        raise TypeError("An Admin-only verified-session resolver is required.")

    router = APIRouter(
        prefix="/api/admin",
        tags=["Admin Property Directory"],
    )

    async def current_admin_id(request: Request) -> int:
        user_id = verified_session_user_id(request)
        if inspect.isawaitable(user_id):
            user_id = await user_id

        if type(user_id) is not int or user_id <= 0:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"Cache-Control": "no-store"},
            )
        return user_id

    @router.get(
        "/property-directory",
        name="get_admin_property_directory",
        summary="List dorm properties for the authenticated Admin (read-only)",
    )
    def list_properties(
        response: Response,
        admin_user_id: int = Depends(current_admin_id),
        search: str = Query(default="", max_length=60),
        listing_status: Literal["all", "published", "not_published"] = Query(
            default="all", alias="status"
        ),
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=50),
    ) -> dict:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"

        try:
            return get_admin_property_directory(
                admin_user_id=admin_user_id,
                search=search,
                status=listing_status,
                page=page,
                page_size=page_size,
            )
        except AdminPropertyDirectoryAccessError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Admin access required.",
                headers={"Cache-Control": "no-store"},
            ) from exc
        except AdminPropertyDirectoryValidationError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
                headers={"Cache-Control": "no-store"},
            ) from exc
        except AdminPropertyDirectoryError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load the property directory.",
                headers={"Cache-Control": "no-store"},
            ) from exc

    return router
