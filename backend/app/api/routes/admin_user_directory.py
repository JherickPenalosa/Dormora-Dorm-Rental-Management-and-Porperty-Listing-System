
"""Dormora — System Functionality File 61.

CREATE: backend/app/api/routes/admin_user_directory.py

Read-only, admin-only user directory API backed by File 60.
File 62 must register this router with the EXISTING verified-session resolver.
No writes, schema changes, CSRF modifications, or browser-provided admin ID.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.services.admin_user_directory_service import (
    AdminDirectoryAccessError,
    AdminDirectoryError,
    AdminDirectoryValidationError,
    get_admin_user_directory,
)


IdentityResolver = Callable[[Request], int | Awaitable[int]]


def build_admin_user_directory_router(
    *,
    verified_session_user_id: IdentityResolver,
) -> APIRouter:
    """Create the directory route with Dormora's trusted session resolver.

    The callback MUST return the authenticated user ID from the verified
    server-side session. File 60 independently checks that the account is an
    active, email-verified admin. IDs supplied by the browser are never used.
    """
    if not callable(verified_session_user_id):
        raise TypeError("Verified session callback is required.")

    router = APIRouter(prefix="/api/admin", tags=["Admin User Directory"])

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

    @router.get(
        "/user-directory",
        name="get_admin_user_directory",
        summary="List renter and owner accounts for the authenticated admin",
    )
    def list_users(
        response: Response,
        user_id: int = Depends(current_user_id),
        search: str = Query(default="", max_length=60),
        role: Literal["all", "renter", "property_owner"] = "all",
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=50),
    ) -> dict:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"

        try:
            return get_admin_user_directory(
                admin_user_id=user_id,
                search=search,
                role=role,
                page=page,
                page_size=page_size,
            )
        except AdminDirectoryAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required.",
                headers={"Cache-Control": "no-store"},
            ) from exc
        except AdminDirectoryValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
                headers={"Cache-Control": "no-store"},
            ) from exc
        except AdminDirectoryError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load the user directory.",
                headers={"Cache-Control": "no-store"},
            ) from exc

    return router
