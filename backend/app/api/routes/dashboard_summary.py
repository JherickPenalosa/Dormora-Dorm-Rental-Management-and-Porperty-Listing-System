
"""Dormora — System Functionality File 52.

CREATE: backend/app/api/routes/dashboard_summary.py

Read-only, authenticated dashboard summary API for File 51.

File 53 will register build_dashboard_summary_router() in the existing
functionality runner using the same trusted session resolver as the rental,
tenancy, and rent-management APIs.

No new database objects, CSRF changes, mutations, or browser-supplied IDs.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.services.dashboard_summary_service import (
    DashboardSummaryAccessError,
    DashboardSummaryError,
    get_dashboard_summary,
)


IdentityResolver = Callable[[Request], int | Awaitable[int]]


def build_dashboard_summary_router(
    *,
    verified_session_user_id: IdentityResolver,
) -> APIRouter:
    """Use Dormora's existing verified-session identity callback.

    The callback MUST resolve the current account from the verified server-side
    session. The service independently re-checks account state and role in
    PostgreSQL, then returns data for that account only.
    """
    if not callable(verified_session_user_id):
        raise TypeError("Verified session identity callback is required.")

    router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Summary"])

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
        "/summary",
        name="get_my_dashboard_summary",
        summary="Get the signed-in account's role-specific Home dashboard statistics",
    )
    def dashboard_summary(
        response: Response,
        user_id: int = Depends(current_user_id),
    ) -> dict:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"

        try:
            summary = get_dashboard_summary(user_id=user_id)
        except DashboardSummaryAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="An active, verified renter or property owner account is required.",
                headers={"Cache-Control": "no-store"},
            ) from exc
        except DashboardSummaryError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load dashboard summary.",
                headers={"Cache-Control": "no-store"},
            ) from exc

        return {"summary": summary}

    return router
