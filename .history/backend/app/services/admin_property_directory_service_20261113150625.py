
"""Dormora — System Functionality File 64.

CREATE: backend/app/services/admin_property_directory_service.py

Read-only Admin Dorm Listing Directory service using existing PostgreSQL
users and dorm_properties tables. Lists the property, owner username,
listing status, monthly asking rent and room availability. Never returns
private contact data, login credentials, or renter/payment information.

File 65 will expose this through a verified-session, Admin-only GET route.
No schema changes and no account/listing mutations.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from sqlalchemy import MetaData, Table, case, func, or_, select

from app.db.database import SessionLocal, engine


MAX_SEARCH_LENGTH = 60
MAX_PAGE_SIZE = 50
VISIBLE_STATUSES = ("all", "published", "not_published")


class AdminPropertyDirectoryError(Exception):
    """Base error for the Admin property directory."""


class AdminPropertyDirectoryAccessError(AdminPropertyDirectoryError):
    """The session account is not an active, verified Admin."""


class AdminPropertyDirectoryValidationError(AdminPropertyDirectoryError):
    """One or more directory filters are invalid."""


@lru_cache(maxsize=1)
def _tables() -> tuple[Table, Table]:
    """Reflect existing PostgreSQL tables; never modify the schema."""
    metadata = MetaData()

    users = Table(
        "users",
        metadata,
        schema="public",
        autoload_with=engine,
    )

    properties = Table(
        "dorm_properties",
        metadata,
        schema="public",
        autoload_with=engine,
    )

    return users, properties


def _require_admin(
    session,
    users: Table,
    admin_user_id: int,
) -> None:
    """Re-check Admin eligibility in the database, not from browser input."""

    if type(admin_user_id) is not int or admin_user_id <= 0:
        raise AdminPropertyDirectoryAccessError(
            "Authentication required."
        )

    account = session.execute(
        select(
            users.c.role,
            users.c.account_status,
            users.c.email_verified_at,
        ).where(users.c.user_id == admin_user_id)
    ).mappings().one_or_none()

    if (
        account is None
        or account["role"] != "admin"
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
    ):
        raise AdminPropertyDirectoryAccessError(
            "Admin access required."
        )


def _validate_filters(
    *,
    search: str,
    status: str,
    page: int,
    page_size: int,
) -> tuple[str, str]:

    if not isinstance(search, str):
        raise AdminPropertyDirectoryValidationError(
            "Search must be text."
        )

    search = search.strip()

    if len(search) > MAX_SEARCH_LENGTH:
        raise AdminPropertyDirectoryValidationError(
            "Search is too long."
        )

    if (
        not isinstance(status, str)
        or status not in VISIBLE_STATUSES
    ):
        raise AdminPropertyDirectoryValidationError(
            "Invalid listing status filter."
        )

    if type(page) is not int or not 1 <= page <= 10000:
        raise AdminPropertyDirectoryValidationError(
            "Page must be between 1 and 10000."
        )

    if (
        type(page_size) is not int
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise AdminPropertyDirectoryValidationError(
            f"Page size must be between 1 and {MAX_PAGE_SIZE}."
        )

    return search, status


def _escape_like(text: str) -> str:
    """Treat SQL LIKE's %, _ and backslash as literal search characters."""

    return (
        text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _money(value) -> str | None:
    return (
        None
        if value is None
        else str(
            Decimal(str(value)).quantize(Decimal("0.01"))
        )
    )


def get_admin_property_directory(
    *,
    admin_user_id: int,
    search: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return a paginated, read-only listing directory for a verified Admin.

    admin_user_id MUST come from the verified server-side session in File 65.
    Never trust an Admin ID supplied by the request or browser.
    """

    search, status = _validate_filters(
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )

    users, properties = _tables()

    owner_properties = properties.join(
        users,
        properties.c.owner_user_id == users.c.user_id,
    )

    with SessionLocal() as session:
        _require_admin(
            session,
            users,
            admin_user_id,
        )

        summary = session.execute(
            select(
                func.count(
                    properties.c.id
                ).label("total_listings"),

                func.coalesce(
                    func.sum(
                        case(
                            (
                                properties.c.status == "published",
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("published_listings"),

                func.coalesce(
                    func.sum(properties.c.total_rooms),
                    0,
                ).label("total_rooms"),

                func.coalesce(
                    func.sum(properties.c.available_rooms),
                    0,
                ).label("available_rooms"),
            ).select_from(owner_properties)
        ).mappings().one()

        filters = []

        if status == "published":
            filters.append(
                properties.c.status == "published"
            )

        elif status == "not_published":
            filters.append(
                properties.c.status.is_distinct_from(
                    "published"
                )
            )

        if search:
            pattern = f"%{_escape_like(search)}%"

            filters.append(
                or_(
                    properties.c.name.ilike(
                        pattern,
                        escape="\\",
                    ),
                    properties.c.address.ilike(
                        pattern,
                        escape="\\",
                    ),
                    users.c.username.ilike(
                        pattern,
                        escape="\\",
                    ),
                )
            )

        matched = session.execute(
            select(
                func.count(properties.c.id)
            )
            .select_from(owner_properties)
            .where(*filters)
        ).scalar_one()

        listings = session.execute(
            select(
                properties.c.id.label("property_id"),
                properties.c.name.label("property_name"),
                properties.c.address,

                properties.c.status.label(
                    "listing_status"
                ),

                properties.c.monthly_rent,
                properties.c.total_rooms,
                properties.c.available_rooms,
                properties.c.owner_user_id,

                users.c.username.label(
                    "owner_username"
                ),
            )
            .select_from(owner_properties)
            .where(*filters)
            .order_by(properties.c.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).mappings().all()

        total = int(summary["total_listings"])
        published = int(summary["published_listings"])
        total_rooms = int(summary["total_rooms"])
        available_rooms = int(summary["available_rooms"])
        matched = int(matched)

        return {
            "role": "admin",

            "summary": {
                "total_listings": total,
                "published_listings": published,
                "not_published_listings": total - published,
                "total_rooms": total_rooms,
                "available_rooms": available_rooms,
            },

            "filters": {
                "search": search,
                "status": status,
            },

            "pagination": {
                "page": page,
                "page_size": page_size,
                "matched_listings": matched,
                "total_pages": (
                    matched + page_size - 1
                ) // page_size,
            },

            "properties": [
                {
                    "property_id": int(
                        item["property_id"]
                    ),

                    "property_name": item[
                        "property_name"
                    ],

                    "address": item["address"],

                    "listing_status": item[
                        "listing_status"
                    ],

                    "monthly_rent": _money(
                        item["monthly_rent"]
                    ),

                    "total_rooms": int(
                        item["total_rooms"]
                    ),

                    "available_rooms": int(
                        item["available_rooms"]
                    ),

                    "assigned_rooms": max(
                        0,
                        int(item["total_rooms"])
                        - int(item["available_rooms"]),
                    ),

                    "owner_user_id": int(
                        item["owner_user_id"]
                    ),

                    "owner_username": item[
                        "owner_username"
                    ],
                }
                for item in listings
            ],
        }
