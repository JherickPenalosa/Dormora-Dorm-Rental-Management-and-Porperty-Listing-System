
"""
Dormora — System Functionality File 15
Renter Dorm Discovery API

CREATE:
backend/app/api/routes/renter_discovery.py

Provides read-only endpoints for authenticated renters to discover
published dorm properties.

Dependencies:
- File 14: dorm_discovery_service.py
- Existing verified session authentication

The File 16 runner must supply a callback that verifies the caller
has an authenticated, active renter account.

No CSRF token is required for these read-only GET endpoints.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import FileResponse

from app.services.dorm_discovery_service import (
    get_published_dorm,
    get_published_dorm_photo,
    list_published_dorms,
)


IdentityResolver = Callable[
    [Request],
    int | Awaitable[int],
]


def build_renter_discovery_router(
    *,
    verified_session_user_id: IdentityResolver,
) -> APIRouter:
    """
    Create renter discovery routes using trusted session verification.

    IMPORTANT:
    The supplied callback must:
    1. Check the actual server-side session.
    2. Require an active renter account.
    3. Reject unauthenticated/non-renter users.
    4. Return the verified user's integer ID.

    Never accept a user ID or role from browser parameters.
    """

    if not callable(verified_session_user_id):
        raise TypeError(
            "A verified renter session callback is required."
        )

    router = APIRouter(
        prefix="/api/renter/discovery",
        tags=["Renter Dorm Discovery"],
    )

    async def require_renter(
        request: Request,
    ) -> int:
        """
        Verify renter identity through the existing session system.

        File 16 will supply the role-restricted callback.
        """

        result = verified_session_user_id(request)

        if inspect.isawaitable(result):
            result = await result

        if type(result) is not int or result <= 0:
            raise HTTPException(
                status_code=401,
                detail="Authentication required.",
            )

        return result

    def prepare_property(
        request: Request,
        property_row: dict,
    ) -> dict:
        """
        Convert stored photo keys into authenticated API URLs.

        Exclude internal storage identifiers from the response.
        """

        item = dict(property_row)

        photo_keys = item.pop("photo_keys", [])

        photo_urls = [
            str(
                request.url_for(
                    "renter_discovery_photo",
                    storage_key=key,
                )
            )
            for key in photo_keys
        ]

        item["photo_urls"] = photo_urls

        item["cover_photo_url"] = (
            photo_urls[0]
            if photo_urls
            else None
        )

        return item

    @router.get(
        "",
        name="renter_discovery_list",
    )
    def discover_properties(
        request: Request,
        search: str = Query(
            default="",
            max_length=100,
            description="Search dorm names or addresses.",
        ),
        limit: int = Query(
            default=50,
            ge=1,
            le=50,
        ),
        _renter_id: int = Depends(require_renter),
    ):
        """
        Return published property listings.

        Optional query parameters:
        - search: dorm name or address
        - limit: maximum number of results (1–50)
        """

        rows = list_published_dorms(
            search=search,
            limit=limit,
        )

        properties = [
            prepare_property(request, row)
            for row in rows
        ]

        return {
            "properties": properties,
            "count": len(properties),
        }

    # Keep this route before /{property_id}.
    @router.get(
        "/photos/{storage_key}",
        name="renter_discovery_photo",
    )
    def property_photo(
        storage_key: str,
        _renter_id: int = Depends(require_renter),
    ):
        """
        Serve only photos linked to published properties.

        The service checks both the database association and
        the file path before returning the image.
        """

        result = get_published_dorm_photo(
            storage_key=storage_key,
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Property photo not found.",
            )

        file_path, media_type = result

        return FileResponse(
            path=file_path,
            media_type=media_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get(
        "/{property_id}",
        name="renter_discovery_detail",
    )
    def property_details(
        property_id: int,
        request: Request,
        _renter_id: int = Depends(require_renter),
    ):
        """
        Return one published property's complete listing details.

        Draft, archived, and nonexistent properties return 404.
        """

        property_row = get_published_dorm(
            property_id=property_id,
        )

        if property_row is None:
            raise HTTPException(
                status_code=404,
                detail="Property not found.",
            )

        return {
            "property": prepare_property(
                request,
                property_row,
            ),
        }

    return router
