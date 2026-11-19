
"""
DORMORA — SYSTEM FUNCTIONALITY FILE 20

CREATE:
backend/app/services/rental_inquiry_service.py

Rental inquiry business logic.

Uses existing tables:
- public.users
- public.dorm_properties
- public.dorm_rental_inquiries

An accepted inquiry is NOT a confirmed tenancy.
Room availability and payment records remain unchanged.

Future API routes must pass authenticated user IDs obtained
from Dormora's existing server-side session verification.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlalchemy import (
    MetaData,
    Table,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal, engine


PHILIPPINE_TIME = ZoneInfo("Asia/Manila")


class RentalInquiryError(Exception):
    """Base error for rental inquiry operations."""


class InquiryValidationError(RentalInquiryError):
    """Invalid inquiry details or unavailable property."""


class InquiryAccessError(RentalInquiryError):
    """Account is not permitted to perform this operation."""


class InquiryNotFoundError(RentalInquiryError):
    """Inquiry does not exist or is not accessible."""


class InquiryConflictError(RentalInquiryError):
    """Inquiry already exists or cannot change status."""


@lru_cache(maxsize=1)
def _tables():
    """Read existing SQL tables without modifying the database."""
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

    inquiries = Table(
        "dorm_rental_inquiries",
        metadata,
        schema="public",
        autoload_with=engine,
    )

    return users, properties, inquiries


def _valid_id(value):
    return type(value) is int and value > 0


def _require_role(session, user_id, required_role):
    """Confirm that the account is active and has the correct role."""
    if not _valid_id(user_id):
        raise InquiryAccessError("Authentication required.")

    users, _, _ = _tables()

    account = session.execute(
        select(
            users.c.role,
            users.c.account_status,
            users.c.email_verified_at,
        ).where(users.c.user_id == user_id)
    ).mappings().one_or_none()

    if (
        account is None
        or account["role"] != required_role
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
    ):
        raise InquiryAccessError(
            "Your account cannot perform this action."
        )


def _prepare_message(message):
    if message is None:
        return None

    if not isinstance(message, str):
        raise InquiryValidationError("Invalid inquiry message.")

    cleaned = message.strip()

    if not cleaned:
        return None

    if len(cleaned) > 1000:
        raise InquiryValidationError(
            "Inquiry message cannot exceed 1000 characters."
        )

    return cleaned


def _prepare_date(value):
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        raise InquiryValidationError("Use a date without a time.")

    if isinstance(value, date):
        selected = value
    elif isinstance(value, str):
        try:
            selected = date.fromisoformat(value.strip())
        except ValueError as exc:
            raise InquiryValidationError(
                "Move-in date must follow YYYY-MM-DD."
            ) from exc
    else:
        raise InquiryValidationError("Invalid move-in date.")

    today = datetime.now(PHILIPPINE_TIME).date()

    if selected < today:
        raise InquiryValidationError(
            "Preferred move-in date cannot be in the past."
        )

    return selected


def _serialize(row):
    """Convert database values into JSON-compatible values."""
    result = dict(row)

    for key, value in result.items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = str(value)

    return result


def create_rental_inquiry(
    *,
    renter_user_id: int,
    property_id: int,
    message: str | None = None,
    preferred_move_in_date: str | date | None = None,
) -> dict:
    """Create a pending inquiry for a published, available property."""
    if not _valid_id(property_id):
        raise InquiryValidationError("Invalid property ID.")

    clean_message = _prepare_message(message)
    move_in = _prepare_date(preferred_move_in_date)

    _, properties, inquiries = _tables()

    try:
        with SessionLocal.begin() as session:
            _require_role(session, renter_user_id, "renter")

            # Lock this property while checking its current availability.
            property_row = session.execute(
                select(
                    properties.c.id,
                    properties.c.name,
                    properties.c.status,
                    properties.c.available_rooms,
                )
                .where(properties.c.id == property_id)
                .with_for_update()
            ).mappings().one_or_none()

            if (
                property_row is None
                or property_row["status"] != "published"
            ):
                raise InquiryValidationError(
                    "This property is not available for inquiries."
                )

            if property_row["available_rooms"] <= 0:
                raise InquiryValidationError(
                    "This property currently has no available rooms."
                )

            existing = session.execute(
                select(inquiries.c.id).where(
                    inquiries.c.property_id == property_id,
                    inquiries.c.renter_user_id == renter_user_id,
                    inquiries.c.status == "pending",
                )
            ).scalar_one_or_none()

            if existing is not None:
                raise InquiryConflictError(
                    "You already have a pending inquiry for this property."
                )

            result = session.execute(
                insert(inquiries)
                .values(
                    property_id=property_id,
                    renter_user_id=renter_user_id,
                    message=clean_message,
                    preferred_move_in_date=move_in,
                    status="pending",
                )
                .returning(inquiries.c.id)
            )

            inquiry_id = result.scalar_one()

            return {
                "id": inquiry_id,
                "property_id": property_id,
                "property_name": property_row["name"],
                "status": "pending",
                "message": "Rental inquiry submitted successfully.",
            }

    except IntegrityError as exc:
        # The database's partial unique index is the final protection
        # against simultaneous duplicate pending inquiries.
        if getattr(getattr(exc.orig, "diag", None),
                   "constraint_name", None) == (
            "uq_dorm_rental_inquiries_pending"
        ):
            raise InquiryConflictError(
                "You already have a pending inquiry for this property."
            ) from exc
        raise


def list_renter_inquiries(*, renter_user_id: int) -> list[dict]:
    """Retrieve only the authenticated renter's inquiries."""
    _, properties, inquiries = _tables()

    with SessionLocal() as session:
        _require_role(session, renter_user_id, "renter")

        rows = session.execute(
            select(
                *inquiries.c,
                properties.c.name.label("property_name"),
                properties.c.address.label("property_address"),
                properties.c.monthly_rent.label("monthly_rent"),
            )
            .join(
                properties,
                inquiries.c.property_id == properties.c.id,
            )
            .where(inquiries.c.renter_user_id == renter_user_id)
            .order_by(
                inquiries.c.created_at.desc(),
                inquiries.c.id.desc(),
            )
            .limit(100)
        ).mappings().all()

        return [_serialize(row) for row in rows]


def list_owner_inquiries(*, owner_user_id: int) -> list[dict]:
    """Retrieve inquiries for properties belonging to this owner."""
    users, properties, inquiries = _tables()

    renter = users.alias("inquiry_renter")

    with SessionLocal() as session:
        _require_role(session, owner_user_id, "property_owner")

        rows = session.execute(
            select(
                *inquiries.c,
                properties.c.name.label("property_name"),
                renter.c.username.label("renter_username"),
            )
            .join(
                properties,
                inquiries.c.property_id == properties.c.id,
            )
            .join(
                renter,
                inquiries.c.renter_user_id == renter.c.user_id,
            )
            .where(
                properties.c.owner_user_id == owner_user_id
            )
            .order_by(
                inquiries.c.created_at.desc(),
                inquiries.c.id.desc(),
            )
            .limit(100)
        ).mappings().all()

        return [_serialize(row) for row in rows]


def review_rental_inquiry(
    *,
    owner_user_id: int,
    inquiry_id: int,
    decision: str,
) -> dict:
    """Allow an owner to accept or reject a pending inquiry."""
    if not _valid_id(inquiry_id):
        raise InquiryNotFoundError("Inquiry not found.")

    if decision not in {"accepted", "rejected"}:
        raise InquiryValidationError(
            "Decision must be accepted or rejected."
        )

    _, properties, inquiries = _tables()

    with SessionLocal.begin() as session:
        _require_role(session, owner_user_id, "property_owner")

        row = session.execute(
            select(
                inquiries.c.id,
                inquiries.c.status,
            )
            .join(
                properties,
                inquiries.c.property_id == properties.c.id,
            )
            .where(
                inquiries.c.id == inquiry_id,
                properties.c.owner_user_id == owner_user_id,
            )
            .with_for_update(of=inquiries)
        ).mappings().one_or_none()

        if row is None:
            raise InquiryNotFoundError("Inquiry not found.")

        if row["status"] != "pending":
            raise InquiryConflictError(
                "Only pending inquiries can be reviewed."
            )

        session.execute(
            update(inquiries)
            .where(inquiries.c.id == inquiry_id)
            .values(
                status=decision,
                reviewed_at=func.now(),
                updated_at=func.now(),
            )
        )

        return {
            "id": inquiry_id,
            "status": decision,
            "message": (
                "Inquiry accepted. No room has been assigned yet."
                if decision == "accepted"
                else "Inquiry rejected."
            ),
        }


def withdraw_rental_inquiry(
    *,
    renter_user_id: int,
    inquiry_id: int,
) -> dict:
    """Allow renters to withdraw their own pending inquiries."""
    if not _valid_id(inquiry_id):
        raise InquiryNotFoundError("Inquiry not found.")

    _, _, inquiries = _tables()

    with SessionLocal.begin() as session:
        _require_role(session, renter_user_id, "renter")

        row = session.execute(
            select(
                inquiries.c.id,
                inquiries.c.status,
            )
            .where(
                inquiries.c.id == inquiry_id,
                inquiries.c.renter_user_id == renter_user_id,
            )
            .with_for_update()
        ).mappings().one_or_none()

        if row is None:
            raise InquiryNotFoundError("Inquiry not found.")

        if row["status"] != "pending":
            raise InquiryConflictError(
                "Only pending inquiries can be withdrawn."
            )

        session.execute(
            update(inquiries)
            .where(inquiries.c.id == inquiry_id)
            .values(
                status="withdrawn",
                updated_at=func.now(),
            )
        )

        return {
            "id": inquiry_id,
            "status": "withdrawn",
            "message": "Rental inquiry withdrawn successfully.",
        }
