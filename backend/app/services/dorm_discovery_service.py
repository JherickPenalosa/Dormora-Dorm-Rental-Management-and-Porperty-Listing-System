
"""
Dormora — System Functionality File 14
Published Dorm Discovery Service

CREATE:
backend/app/services/dorm_discovery_service.py

Provides read-only access to published properties and their photos.

The future renter-facing API must enforce authentication.
This service never exposes draft or archived properties.
"""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from sqlalchemy import MetaData, Table, or_, select

from app.db.database import SessionLocal, engine


PHOTO_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "storage"
    / "property_photos"
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


@lru_cache(maxsize=1)
def _get_tables():
    """Reflect the existing property tables without changing their schema."""
    metadata = MetaData()

    properties = Table(
        "dorm_properties",
        metadata,
        schema="public",
        autoload_with=engine,
    )

    photos = Table(
        "dorm_property_photos",
        metadata,
        schema="public",
        autoload_with=engine,
    )

    return properties, photos


def _property_columns(properties):
    """Select only fields appropriate for renter discovery."""
    return [
        properties.c.id,
        properties.c.name,
        properties.c.address,
        properties.c.description,
        properties.c.monthly_rent,
        properties.c.total_rooms,
        properties.c.available_rooms,
        properties.c.status,
        properties.c.created_at,
    ]


def _attach_photos(session, property_rows, photos_table):
    """Attach ordered photo identifiers to the selected properties."""
    if not property_rows:
        return []

    property_ids = [row["id"] for row in property_rows]

    photo_rows = session.execute(
        select(
            photos_table.c.property_id,
            photos_table.c.storage_key,
        )
        .where(photos_table.c.property_id.in_(property_ids))
        .order_by(
            photos_table.c.property_id,
            photos_table.c.sort_order,
            photos_table.c.id,
        )
    ).mappings().all()

    photo_map = defaultdict(list)

    for photo in photo_rows:
        photo_map[photo["property_id"]].append(
            photo["storage_key"]
        )

    results = []

    for row in property_rows:
        item = dict(row)

        # Return a JSON-friendly representation of monetary values.
        item["monthly_rent"] = str(item["monthly_rent"])

        created_at = item.get("created_at")
        if created_at is not None:
            item["created_at"] = created_at.isoformat()

        item["photo_keys"] = photo_map.get(item["id"], [])

        results.append(item)

    return results


def list_published_dorms(
    *,
    search: str = "",
    limit: int = 50,
):
    """
    Retrieve published dorm listings.

    Draft and archived properties never appear in the results.
    Search is implemented using parameterized SQLAlchemy expressions.
    """
    properties, photos = _get_tables()

    limit = max(1, min(int(limit), 50))
    search = str(search or "").strip()[:100]

    query = (
        select(*_property_columns(properties))
        .where(properties.c.status == "published")
        .order_by(
            properties.c.created_at.desc(),
            properties.c.id.desc(),
        )
        .limit(limit)
    )

    if search:
        search_pattern = f"%{search}%"

        query = query.where(
            or_(
                properties.c.name.ilike(search_pattern),
                properties.c.address.ilike(search_pattern),
            )
        )

    with SessionLocal() as session:
        rows = session.execute(query).mappings().all()

        return _attach_photos(
            session,
            rows,
            photos,
        )


def get_published_dorm(property_id: int):
    """
    Retrieve one published property's details and photos.

    Returns None when the property is missing or unpublished.
    """
    if type(property_id) is not int or property_id <= 0:
        return None

    properties, photos = _get_tables()

    query = (
        select(*_property_columns(properties))
        .where(
            properties.c.id == property_id,
            properties.c.status == "published",
        )
    )

    with SessionLocal() as session:
        row = session.execute(query).mappings().one_or_none()

        if row is None:
            return None

        results = _attach_photos(
            session,
            [row],
            photos,
        )

        return results[0] if results else None


def get_published_dorm_photo(storage_key: str):
    """
    Resolve a photo belonging to a published property.

    Returns (absolute_file_path, MIME_type), or None.

    A file is never exposed unless its database record belongs
    to a published property.
    """
    if not isinstance(storage_key, str):
        return None

    if (
        not storage_key
        or len(storage_key) > 255
        or "/" in storage_key
        or "\\" in storage_key
        or storage_key in {".", ".."}
        or Path(storage_key).name != storage_key
    ):
        return None

    properties, photos = _get_tables()

    query = (
        select(
            photos.c.storage_key,
            photos.c.mime_type,
        )
        .select_from(
            photos.join(
                properties,
                photos.c.property_id == properties.c.id,
            )
        )
        .where(
            photos.c.storage_key == storage_key,
            properties.c.status == "published",
        )
    )

    with SessionLocal() as session:
        photo = session.execute(query).mappings().one_or_none()

    if photo is None:
        return None

    media_type = photo["mime_type"]

    if media_type not in ALLOWED_IMAGE_TYPES:
        return None

    storage_root = PHOTO_DIRECTORY.resolve()
    file_path = (storage_root / storage_key).resolve()

    # Prevent path traversal and links outside the storage directory.
    if storage_root not in file_path.parents:
        return None

    if not file_path.is_file():
        return None

    return file_path, media_type
