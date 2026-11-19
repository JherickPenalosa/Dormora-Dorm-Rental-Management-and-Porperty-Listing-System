
"""Dormora System Functionality File 6 — owner property storage service.

CREATE: backend/app/services/property_service.py

Uses public.dorm_properties and public.dorm_property_photos (File 5).
The next file will connect this service to authenticated FastAPI routes.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from fastapi import UploadFile
from sqlalchemy import MetaData, Table, insert, select

from app.db.database import SessionLocal, engine
from app.models.user import users_table

PHOTO_DIR = Path(__file__).resolve().parents[2] / "storage" / "property_photos"
MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_FORMATS = {
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": (".webp", b"RIFF"),
}
STORAGE_KEY_PATTERN = re.compile(r"[0-9a-f]{32}\.(?:jpg|png|webp)\Z")


class PropertyValidationError(ValueError):
    """The provided property details or photo files are invalid."""


class PropertyAccessError(PermissionError):
    """The authenticated account is not an active property owner."""


def _tables():
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


def _require_owner(db, user_id: int) -> None:
    # user_id MUST come from the backend-verified session.
    # Never trust a user ID submitted in a browser form.
    if type(user_id) is not int or user_id <= 0:
        raise PropertyAccessError("Property-owner access required.")

    account = db.execute(
        select(
            users_table.c.role,
            users_table.c.account_status,
            users_table.c.email_verified_at,
        ).where(users_table.c.user_id == user_id)
    ).mappings().one_or_none()

    if (
        account is None
        or account["role"] != "property_owner"
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
    ):
        raise PropertyAccessError("Property-owner access required.")


def _validate_details(
    name,
    address,
    description,
    monthly_rent,
    total_rooms,
    available_rooms,
) -> dict:
    details = {}

    for key, value, maximum in (
        ("name", name, 120),
        ("address", address, 250),
        ("description", description, 1500),
    ):
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > maximum
        ):
            raise PropertyValidationError(
                f"Enter a valid {key.replace('_', ' ')}."
            )

        details[key] = value.strip()

    try:
        rent = Decimal(str(monthly_rent))
        rooms = int(str(total_rooms))
        available = int(str(available_rooms))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PropertyValidationError(
            "Rent and room counts must be valid numbers."
        ) from exc

    if (
        not rent.is_finite()
        or rent <= 0
        or rent > Decimal("9999999999.99")
    ):
        raise PropertyValidationError(
            "Monthly rent must be greater than zero."
        )

    if rent.as_tuple().exponent < -2:
        raise PropertyValidationError(
            "Monthly rent can have at most two decimal places."
        )

    if (
        rooms < 1
        or available < 0
        or available > rooms
        or rooms > 100000
    ):
        raise PropertyValidationError("Room counts are invalid.")

    details.update(
        monthly_rent=rent,
        total_rooms=rooms,
        available_rooms=available,
    )

    return details


def _verify_signature(mime: str, header: bytes) -> bool:
    if mime not in PHOTO_FORMATS:
        return False

    _, signature = PHOTO_FORMATS[mime]

    if mime == "image/webp":
        return (
            header.startswith(b"RIFF")
            and header[8:12] == b"WEBP"
        )

    return header.startswith(signature)


def _save_photos(
    uploads: Sequence[UploadFile],
    saved: list[Path],
) -> list[dict]:
    if not 3 <= len(uploads) <= MAX_PHOTOS:
        raise PropertyValidationError(
            "Select 3 to 8 property photos."
        )

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    records = []

    for number, upload in enumerate(uploads, start=1):
        mime = upload.content_type or ""

        if mime not in PHOTO_FORMATS:
            raise PropertyValidationError(
                "Photos must be JPG, PNG, or WebP."
            )

        extension = PHOTO_FORMATS[mime][0]
        storage_key = uuid.uuid4().hex + extension
        target = PHOTO_DIR / storage_key

        upload.file.seek(0)
        size = 0
        first_bytes = b""

        with target.open("xb") as output:
            saved.append(target)

            while True:
                chunk = upload.file.read(1024 * 1024)

                if not chunk:
                    break

                size += len(chunk)

                if size > MAX_PHOTO_BYTES:
                    raise PropertyValidationError(
                        "Each photo must be 5 MB or smaller."
                    )

                if len(first_bytes) < 12:
                    first_bytes += chunk[
                        :12 - len(first_bytes)
                    ]

                output.write(chunk)

        if size == 0 or not _verify_signature(
            mime, first_bytes
        ):
            raise PropertyValidationError(
                "One or more photos are not valid image files."
            )

        records.append({
            "storage_key": storage_key,
            "mime_type": mime,
            "byte_size": size,
            "sort_order": number,
        })

    return records


def create_owner_property(
    *,
    owner_user_id: int,
    name: str,
    address: str,
    description: str,
    monthly_rent: str,
    total_rooms: str,
    available_rooms: str,
    photos: Sequence[UploadFile],
) -> dict:
    """Create a draft listing with three or more photos.

    The route must supply owner_user_id from an authenticated session.
    """

    details = _validate_details(
        name,
        address,
        description,
        monthly_rent,
        total_rooms,
        available_rooms,
    )

    if not 3 <= len(photos) <= MAX_PHOTOS:
        raise PropertyValidationError(
            "Select at least 3 and at most 8 photos."
        )

    property_table, photo_table = _tables()
    saved: list[Path] = []

    try:
        with SessionLocal.begin() as db:
            _require_owner(db, owner_user_id)

            photo_records = _save_photos(
                photos,
                saved,
            )

            property_id = db.execute(
                insert(property_table)
                .values(
                    owner_user_id=owner_user_id,
                    **details,
                    status="draft",
                )
                .returning(property_table.c.id)
            ).scalar_one()

            db.execute(
                insert(photo_table),
                [
                    {
                        "property_id": property_id,
                        **record,
                    }
                    for record in photo_records
                ],
            )

        return {
            "id": int(property_id),
            "status": "draft",
            "photo_count": len(saved),
        }

    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        raise


def list_owner_properties(
    *,
    owner_user_id: int,
) -> list[dict]:
    """Return properties belonging to the authenticated owner."""

    property_table, photo_table = _tables()

    with SessionLocal() as db:
        _require_owner(db, owner_user_id)

        rows = db.execute(
            select(property_table)
            .where(
                property_table.c.owner_user_id == owner_user_id
            )
            .order_by(
                property_table.c.created_at.desc(),
                property_table.c.id.desc(),
            )
        ).mappings().all()

        if not rows:
            return []

        ids = [row["id"] for row in rows]

        photo_rows = db.execute(
            select(
                photo_table.c.property_id,
                photo_table.c.storage_key,
            )
            .where(photo_table.c.property_id.in_(ids))
            .order_by(photo_table.c.sort_order.asc())
        ).mappings().all()

    photos_by_property = {
        property_id: [] for property_id in ids
    }

    for photo in photo_rows:
        photos_by_property[
            photo["property_id"]
        ].append(photo["storage_key"])

    result = []

    for row in rows:
        result.append({
            "id": int(row["id"]),
            "name": row["name"],
            "address": row["address"],
            "description": row["description"],
            "monthly_rent": str(row["monthly_rent"]),
            "total_rooms": row["total_rooms"],
            "available_rooms": row["available_rooms"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat(),
            "photo_keys": photos_by_property[row["id"]],
        })

    return result


def get_owner_photo(
    *,
    owner_user_id: int,
    storage_key: str,
) -> tuple[Path, str]:
    """Resolve a stored photo belonging to an authenticated owner."""

    if (
        not isinstance(storage_key, str)
        or not STORAGE_KEY_PATTERN.fullmatch(storage_key)
    ):
        raise FileNotFoundError("Photo not found.")

    property_table, photo_table = _tables()

    with SessionLocal() as db:
        _require_owner(db, owner_user_id)

        mime = db.execute(
            select(photo_table.c.mime_type)
            .join(
                property_table,
                photo_table.c.property_id == property_table.c.id,
            )
            .where(
                property_table.c.owner_user_id == owner_user_id,
                photo_table.c.storage_key == storage_key,
            )
        ).scalar_one_or_none()

    target = PHOTO_DIR / storage_key

    if mime is None or not target.is_file():
        raise FileNotFoundError("Photo not found.")

    return target, mime
