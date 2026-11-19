
"""Dormora — System Functionality File 60.

CREATE: backend/app/services/admin_user_directory_service.py

Read-only directory for the existing Admin role. Lists only renter and
property-owner accounts; never returns passwords, emails, OTPs, security
answers, private contacts, or session data.

File 61 will expose this service through an authenticated admin-only GET API.
The API MUST use the verified server-side session ID, never a browser-supplied
admin ID. No schema changes and no account mutations.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import MetaData, Table, func, select

from app.db.database import SessionLocal, engine


VISIBLE_ROLES = ("renter", "property_owner")
MAX_PAGE_SIZE = 50
MAX_SEARCH_LENGTH = 60


class AdminDirectoryError(Exception):
    """Base class for expected directory errors."""


class AdminDirectoryAccessError(AdminDirectoryError):
    """Current session account is not an active, verified admin."""


class AdminDirectoryValidationError(AdminDirectoryError):
    """Directory filter or pagination is invalid."""


@lru_cache(maxsize=1)
def _users_table() -> Table:
    """Reflect the EXISTING users table without altering the schema."""
    metadata = MetaData()
    return Table("users", metadata, schema="public", autoload_with=engine)


def _require_admin(session, users: Table, admin_user_id: int) -> None:
    if type(admin_user_id) is not int or admin_user_id <= 0:
        raise AdminDirectoryAccessError("Authentication required.")

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
        raise AdminDirectoryAccessError("Admin access required.")


def _normalize_filters(
    *, search: str, role: str | None, page: int, page_size: int
) -> tuple[str, str | None]:
    if not isinstance(search, str):
        raise AdminDirectoryValidationError("Search must be text.")
    search = search.strip()
    if len(search) > MAX_SEARCH_LENGTH:
        raise AdminDirectoryValidationError("Search is too long.")

    if role in (None, "", "all"):
        role = None
    elif role not in VISIBLE_ROLES:
        raise AdminDirectoryValidationError("Invalid role filter.")

    if type(page) is not int or not 1 <= page <= 10000:
        raise AdminDirectoryValidationError("Page must be between 1 and 10000.")
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise AdminDirectoryValidationError(
            f"Page size must be between 1 and {MAX_PAGE_SIZE}."
        )
    return search, role


def _escape_like(text: str) -> str:
    """Treat %, _ and backslash as literal username search characters."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_admin_user_directory(
    *,
    admin_user_id: int,
    search: str = "",
    role: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List safe, non-sensitive account fields for an authenticated admin.

    Does not expose other admins or modify any records. Caller must obtain
    admin_user_id exclusively from the verified server-side session.
    """
    search, role = _normalize_filters(
        search=search, role=role, page=page, page_size=page_size
    )
    users = _users_table()

    with SessionLocal() as session:
        # Repeat authorization at the data-service boundary to fail closed.
        _require_admin(session, users, admin_user_id)

        all_public_users = users.c.role.in_(VISIBLE_ROLES)
        totals = session.execute(
            select(users.c.role, func.count().label("total"))
            .where(all_public_users)
            .group_by(users.c.role)
        ).all()
        role_totals = {"renter": 0, "property_owner": 0}
        for account_role, count in totals:
            role_totals[account_role] = int(count)

        filters = [all_public_users]
        if role is not None:
            filters.append(users.c.role == role)
        if search:
            pattern = f"%{_escape_like(search)}%"
            filters.append(users.c.username.ilike(pattern, escape="\\"))

        matched = int(
            session.execute(
                select(func.count()).select_from(users).where(*filters)
            ).scalar_one()
        )

        rows = session.execute(
            select(
                users.c.user_id,
                users.c.username,
                users.c.role,
                users.c.account_status,
                users.c.email_verified_at,
            )
            .where(*filters)
            .order_by(users.c.username.asc(), users.c.user_id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).mappings().all()

        return {
            "role": "admin",
            "summary": {
                "total_users": sum(role_totals.values()),
                "total_renters": role_totals["renter"],
                "total_property_owners": role_totals["property_owner"],
            },
            "filters": {"search": search, "role": role or "all"},
            "pagination": {
                "page": page,
                "page_size": page_size,
                "matched_users": matched,
                "total_pages": (matched + page_size - 1) // page_size,
            },
            "users": [
                {
                    "user_id": int(row["user_id"]),
                    "username": row["username"],
                    "role": row["role"],
                    "account_status": row["account_status"],
                    "email_verified": row["email_verified_at"] is not None,
                }
                for row in rows
            ],
        }
