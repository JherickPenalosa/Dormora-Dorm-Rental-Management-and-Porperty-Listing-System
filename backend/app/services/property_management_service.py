
"""Dormora System Functionality File 11 — edit and publish owner properties.

CREATE: backend/app/services/property_management_service.py

Uses File 6's existing validation, owner checks and SQLAlchemy tables.
Only backend-verified owner IDs may be passed by a future API route.
Does not change login, existing property creation, or the database schema.
"""

from __future__ import annotations

from sqlalchemy import func, select, update

from app.db.database import SessionLocal
from app.services.property_service import (
    PropertyValidationError,
    _require_owner,
    _tables,
    _validate_details,
)


class PropertyNotFoundError(LookupError):
    """The property does not exist or is not owned by this account."""


def _validate_property_id(property_id: int) -> None:
    if type(property_id) is not int or property_id < 1:
        raise PropertyNotFoundError("Property not found.")


def update_owner_property(
    *,
    owner_user_id: int,
    property_id: int,
    name: str,
    address: str,
    description: str,
    monthly_rent: str,
    total_rooms: str,
    available_rooms: str,
) -> dict:
    """Edit details of an owner's existing draft or published property.

    Photos are preserved; this method never adds or deletes photo files.
    """
    _validate_property_id(property_id)
    details = _validate_details(
        name, address, description,
        monthly_rent, total_rooms, available_rooms,
    )
    properties, _ = _tables()

    with SessionLocal.begin() as db:
        _require_owner(db, owner_user_id)

        row = db.execute(
            select(properties.c.id, properties.c.status)
            .where(
                properties.c.id == property_id,
                properties.c.owner_user_id == owner_user_id,
            )
            .with_for_update()
        ).mappings().one_or_none()

        if row is None:
            raise PropertyNotFoundError("Property not found.")
        if row["status"] == "archived":
            raise PropertyValidationError(
                "Archived properties cannot be edited."
            )

        db.execute(
            update(properties)
            .where(
                properties.c.id == property_id,
                properties.c.owner_user_id == owner_user_id,
            )
            .values(**details, updated_at=func.now())
        )

        return {
            "id": property_id,
            "status": row["status"],
            "message": "Property details updated.",
        }


def publish_owner_property(
    *, owner_user_id: int, property_id: int
) -> dict:
    """Publish the owner's draft only when it has at least three photos."""
    _validate_property_id(property_id)
    properties, photos = _tables()

    with SessionLocal.begin() as db:
        _require_owner(db, owner_user_id)

        row = db.execute(
            select(properties.c.id, properties.c.status)
            .where(
                properties.c.id == property_id,
                properties.c.owner_user_id == owner_user_id,
            )
            .with_for_update()
        ).mappings().one_or_none()

        if row is None:
            raise PropertyNotFoundError("Property not found.")
        if row["status"] == "archived":
            raise PropertyValidationError(
                "Archived properties cannot be published."
            )

        photo_count = db.execute(
            select(func.count(photos.c.id))
            .where(photos.c.property_id == property_id)
        ).scalar_one()

        if photo_count < 3:
            raise PropertyValidationError(
                "Add at least three photos before publishing."
            )

        if row["status"] != "published":
            db.execute(
                update(properties)
                .where(
                    properties.c.id == property_id,
                    properties.c.owner_user_id == owner_user_id,
                )
                .values(status="published", updated_at=func.now())
            )

        return {
            "id": property_id,
            "status": "published",
            "message": "Property is published.",
        }
