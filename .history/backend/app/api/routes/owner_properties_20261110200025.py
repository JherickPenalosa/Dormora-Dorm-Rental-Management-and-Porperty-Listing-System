
"""Dormora System Functionality File 12 — owner property API.

REPLACE: backend/app/api/routes/owner_properties.py
Preserves File 7 listing/creation/photo routes and adds edit/publish.
File 8 supplies the existing authenticated-session and CSRF callbacks.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.services.property_service import (
    PropertyAccessError,
    PropertyValidationError,
    create_owner_property,
    get_owner_photo,
    list_owner_properties,
)
from app.services.property_management_service import (
    PropertyNotFoundError,
    publish_owner_property,
    update_owner_property,
)

IdentityResolver = Callable[[Request], int | Awaitable[int]]
WriteProtector = Callable[[Request], None | Awaitable[None]]


def build_owner_properties_router(
    *,
    verified_session_user_id: IdentityResolver,
    verify_signed_csrf: WriteProtector,
) -> APIRouter:
    """Build routes with File 8's existing trusted session/CSRF callbacks."""
    if not callable(verified_session_user_id) or not callable(verify_signed_csrf):
        raise TypeError("Verified session and CSRF callbacks are required.")

    router = APIRouter(
        prefix="/api/owner/properties",
        tags=["Owner Properties"],
    )

    async def owner_user_id(request: Request) -> int:
        result = verified_session_user_id(request)
        if inspect.isawaitable(result):
            result = await result
        if type(result) is not int or result <= 0:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return result

    async def csrf_guard(request: Request) -> None:
        result = verify_signed_csrf(request)
        if inspect.isawaitable(result):
            await result

    def photo_urls(request: Request, keys: list[str]) -> list[str]:
        return [
            str(request.url_for("owner_property_photo", storage_key=key))
            for key in keys
        ]

    @router.get("", name="list_owner_properties")
    def get_properties(
        request: Request,
        user_id: int = Depends(owner_user_id),
    ):
        try:
            rows = list_owner_properties(owner_user_id=user_id)
        except PropertyAccessError as exc:
            raise HTTPException(
                status_code=403, detail="Property-owner access required."
            ) from exc

        properties = []
        for property_row in rows:
            row = dict(property_row)
            urls = photo_urls(request, row.pop("photo_keys", []))
            row["photo_urls"] = urls
            row["cover_photo_url"] = urls[0] if urls else None
            properties.append(row)
        return {"properties": properties}

    @router.post(
        "", name="create_owner_property",
        status_code=status.HTTP_201_CREATED,
    )
    def post_property(
        name: str = Form(...),
        address: str = Form(...),
        description: str = Form(...),
        monthly_rent: str = Form(...),
        total_rooms: str = Form(...),
        available_rooms: str = Form(...),
        photos: list[UploadFile] = File(...),
        user_id: int = Depends(owner_user_id),
        _csrf: None = Depends(csrf_guard),
    ):
        try:
            result = create_owner_property(
                owner_user_id=user_id,
                name=name,
                address=address,
                description=description,
                monthly_rent=monthly_rent,
                total_rooms=total_rooms,
                available_rooms=available_rooms,
                photos=photos,
            )
        except PropertyValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PropertyAccessError as exc:
            raise HTTPException(
                status_code=403, detail="Property-owner access required."
            ) from exc
        return {"message": "Property draft created.", **result}

    @router.get("/photos/{storage_key}", name="owner_property_photo")
    def property_photo(
        storage_key: str,
        user_id: int = Depends(owner_user_id),
    ):
        try:
            path, media_type = get_owner_photo(
                owner_user_id=user_id, storage_key=storage_key
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Photo not found.") from exc
        except PropertyAccessError as exc:
            raise HTTPException(
                status_code=403, detail="Property-owner access required."
            ) from exc
        return FileResponse(
            path,
            media_type=media_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    # File 8's existing CSRF callback currently accepts POST requests.
    # Use action-based POST for edit/publish to preserve that integration.
    @router.post("/{property_id}/edit", name="edit_owner_property")
    def edit_property(
        property_id: int,
        name: str = Form(...),
        address: str = Form(...),
        description: str = Form(...),
        monthly_rent: str = Form(...),
        total_rooms: str = Form(...),
        available_rooms: str = Form(...),
        user_id: int = Depends(owner_user_id),
        _csrf: None = Depends(csrf_guard),
    ):
        try:
            return update_owner_property(
                owner_user_id=user_id,
                property_id=property_id,
                name=name,
                address=address,
                description=description,
                monthly_rent=monthly_rent,
                total_rooms=total_rooms,
                available_rooms=available_rooms,
            )
        except PropertyNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Property not found.") from exc
        except PropertyValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PropertyAccessError as exc:
            raise HTTPException(
                status_code=403, detail="Property-owner access required."
            ) from exc

    @router.post("/{property_id}/publish", name="publish_owner_property")
    def publish_property(
        property_id: int,
        user_id: int = Depends(owner_user_id),
        _csrf: None = Depends(csrf_guard),
    ):
        try:
            return publish_owner_property(
                owner_user_id=user_id,
                property_id=property_id,
            )
        except PropertyNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Property not found.") from exc
        except PropertyValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PropertyAccessError as exc:
            raise HTTPException(
                status_code=403, detail="Property-owner access required."
            ) from exc

    return router
