"""
DORMORA — SYSTEM FUNCTIONALITY FILE 35

CREATE: backend/app/services/tenancy_service.py

Create, list, and end formal tenancies using File 34's existing tables.
An accepted inquiry is required before assignment. All changes to a tenancy
and the property's available-room count occur in ONE database transaction.

The future API MUST pass user IDs from verified server-side sessions. Never
accept an owner_user_id or renter_user_id supplied directly by the browser.
No payment records or rent invoices are created by this service.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlalchemy import MetaData, Table, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal, engine


LOCAL_TZ = ZoneInfo("Asia/Manila")
MAX_MONTHLY_RENT = Decimal("9999999999.99")  # NUMERIC(12, 2)


class TenancyError(Exception):
    """Base class for expected tenancy-related errors."""


class TenancyValidationError(TenancyError):
    """Incorrect or incomplete tenancy details."""


class TenancyAccessError(TenancyError):
    """Account is not authorized to act as the required role."""


class TenancyNotFoundError(TenancyError):
    """Requested property or tenancy is absent or inaccessible."""


class TenancyConflictError(TenancyError):
    """Assignment would conflict with current rental state."""


@lru_cache(maxsize=1)
def _tables():
    """Reflect existing tables; do not create or alter schema."""
    metadata = MetaData()
    users = Table("users", metadata, schema="public", autoload_with=engine)
    properties = Table(
        "dorm_properties", metadata, schema="public", autoload_with=engine
    )
    inquiries = Table(
        "dorm_rental_inquiries", metadata, schema="public", autoload_with=engine
    )
    tenancies = Table(
        "dorm_tenancies", metadata, schema="public", autoload_with=engine
    )
    return users, properties, inquiries, tenancies


def _id(value, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise TenancyValidationError(f"Invalid {label}.")
    return value


def _require_role(session, *, user_id: int, role: str) -> None:
    """Recheck active, verified account status inside the DB operation."""
    users, _, _, _ = _tables()
    account = session.execute(
        select(
            users.c.role,
            users.c.account_status,
            users.c.email_verified_at,
        ).where(users.c.user_id == user_id)
    ).mappings().one_or_none()

    if (
        account is None
        or account["role"] != role
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
    ):
        raise TenancyAccessError("Account is not eligible for this operation.")


def _room_label(value: str) -> str:
    if not isinstance(value, str):
        raise TenancyValidationError("Room label must be text.")
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > 60:
        raise TenancyValidationError("Room label must contain 1–60 characters.")
    if any(not char.isprintable() for char in cleaned):
        raise TenancyValidationError("Room label contains invalid characters.")
    return cleaned


def _money(value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise TenancyValidationError("A valid monthly rent is required.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TenancyValidationError("Monthly rent must be a number.") from exc
    if not amount.is_finite() or not (Decimal("0") < amount <= MAX_MONTHLY_RENT):
        raise TenancyValidationError("Monthly rent is outside the allowed range.")
    if amount != amount.quantize(Decimal("0.01")):
        raise TenancyValidationError("Monthly rent supports at most two decimals.")
    return amount.quantize(Decimal("0.01"))


def _date(value, label: str) -> date:
    if isinstance(value, datetime):
        raise TenancyValidationError(f"{label} must not include a time.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise TenancyValidationError(f"{label} must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TenancyValidationError(f"Invalid {label.lower()}.") from exc


def _due_day(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 28:
        raise TenancyValidationError("Rent due day must be between 1 and 28.")
    return value


def _serialize(row) -> dict:
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = str(value)
    return result


def _assert_property_counts(property_row) -> tuple[int, int]:
    total = property_row["total_rooms"]
    available = property_row["available_rooms"]
    if (
        type(total) is not int or type(available) is not int
        or total < 1 or available < 0 or available > total
    ):
        raise TenancyConflictError(
            "Property room counts need correction before assigning or ending a tenancy."
        )
    return total, available


def assign_tenant(
    *,
    owner_user_id: int,
    inquiry_id: int,
    room_label: str,
    move_in_date: str | date,
    agreed_monthly_rent: str | Decimal | None = None,
    rent_due_day: int = 1,
) -> dict:
    """
    Formally assign a renter from an ACCEPTED inquiry.

    Lock the property BEFORE the inquiry to serialize occupancy changes.
    Creating the tenancy and reducing available_rooms commit together.
    A future move-in date is allowed: the room becomes allocated as soon as
    the active tenancy is created, even if physical occupancy begins later.
    """
    _id(owner_user_id, "owner ID")
    _id(inquiry_id, "inquiry ID")
    label = _room_label(room_label)
    start_date = _date(move_in_date, "Move-in date")
    due_day = _due_day(rent_due_day)
    agreed = None if agreed_monthly_rent is None else _money(agreed_monthly_rent)

    _, properties, inquiries, tenancies = _tables()
    try:
        with SessionLocal.begin() as session:
            _require_role(session, user_id=owner_user_id, role="property_owner")

            # Read the property ID first. Do not trust one supplied by the client.
            property_id = session.execute(
                select(inquiries.c.property_id).where(inquiries.c.id == inquiry_id)
            ).scalar_one_or_none()
            if property_id is None:
                raise TenancyNotFoundError("Accepted inquiry not found.")

            # One lock controls room availability across all tenants in a property.
            property_row = session.execute(
                select(
                    properties.c.id,
                    properties.c.owner_user_id,
                    properties.c.status,
                    properties.c.name,
                    properties.c.monthly_rent,
                    properties.c.total_rooms,
                    properties.c.available_rooms,
                )
                .where(properties.c.id == property_id)
                .with_for_update()
            ).mappings().one_or_none()
            if property_row is None or property_row["owner_user_id"] != owner_user_id:
                raise TenancyNotFoundError("Accepted inquiry not found.")

            # Lock again after property lock to prevent races with inquiry review.
            inquiry_row = session.execute(
                select(
                    inquiries.c.id,
                    inquiries.c.property_id,
                    inquiries.c.renter_user_id,
                    inquiries.c.status,
                )
                .where(inquiries.c.id == inquiry_id)
                .with_for_update()
            ).mappings().one_or_none()
            if inquiry_row is None or inquiry_row["property_id"] != property_id:
                raise TenancyNotFoundError("Accepted inquiry not found.")
            if inquiry_row["status"] != "accepted":
                raise TenancyConflictError("Only accepted inquiries can become tenancies.")
            if property_row["status"] != "published":
                raise TenancyConflictError("Property must be published to assign a tenant.")

            renter_id = inquiry_row["renter_user_id"]
            _require_role(session, user_id=renter_id, role="renter")
            _, available = _assert_property_counts(property_row)
            if available == 0:
                raise TenancyConflictError("There are no available rooms.")

            if session.execute(
                select(tenancies.c.id).where(tenancies.c.inquiry_id == inquiry_id)
            ).scalar_one_or_none() is not None:
                raise TenancyConflictError("This inquiry already has a tenancy record.")

            if session.execute(
                select(tenancies.c.id).where(
                    tenancies.c.renter_user_id == renter_id,
                    tenancies.c.status == "active",
                )
            ).first() is not None:
                raise TenancyConflictError("This renter already has an active tenancy.")

            if session.execute(
                select(tenancies.c.id).where(
                    tenancies.c.property_id == property_id,
                    func.lower(func.btrim(tenancies.c.room_label)) == label.lower(),
                    tenancies.c.status == "active",
                )
            ).first() is not None:
                raise TenancyConflictError("This room is already assigned.")

            rent = agreed if agreed is not None else _money(property_row["monthly_rent"])
            tenancy_id = session.execute(
                insert(tenancies)
                .values(
                    inquiry_id=inquiry_id,
                    property_id=property_id,
                    renter_user_id=renter_id,
                    room_label=label,
                    monthly_rent=rent,
                    rent_due_day=due_day,
                    move_in_date=start_date,
                    status="active",
                )
                .returning(tenancies.c.id)
            ).scalar_one()

            session.execute(
                update(properties)
                .where(properties.c.id == property_id)
                .values(
                    available_rooms=available - 1,
                    updated_at=func.now(),
                )
            )

            return {
                "id": tenancy_id,
                "inquiry_id": inquiry_id,
                "property_id": property_id,
                "property_name": property_row["name"],
                "renter_user_id": renter_id,
                "room_label": label,
                "monthly_rent": str(rent),
                "rent_due_day": due_day,
                "move_in_date": start_date.isoformat(),
                "status": "active",
                "available_rooms_after": available - 1,
            }
    except IntegrityError as exc:
        # The DB's unique indexes remain the final protection against races
        # involving different properties or simultaneous assignment requests.
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise TenancyConflictError(
                "This inquiry, renter, or room is already assigned."
            ) from exc
        raise


def list_owner_tenancies(*, owner_user_id: int) -> list[dict]:
    """Only tenancies belonging to properties owned by this account."""
    _id(owner_user_id, "owner ID")
    users, properties, _, tenancies = _tables()
    with SessionLocal() as session:
        _require_role(session, user_id=owner_user_id, role="property_owner")
        rows = session.execute(
            select(
                tenancies.c.id,
                tenancies.c.inquiry_id,
                tenancies.c.property_id,
                tenancies.c.renter_user_id,
                tenancies.c.room_label,
                tenancies.c.monthly_rent,
                tenancies.c.rent_due_day,
                tenancies.c.move_in_date,
                tenancies.c.move_out_date,
                tenancies.c.status,
                tenancies.c.created_at,
                tenancies.c.ended_at,
                properties.c.name.label("property_name"),
                users.c.username.label("renter_username"),
            )
            .select_from(
                tenancies.join(properties, tenancies.c.property_id == properties.c.id)
                .join(users, tenancies.c.renter_user_id == users.c.user_id)
            )
            .where(properties.c.owner_user_id == owner_user_id)
            .order_by(tenancies.c.created_at.desc(), tenancies.c.id.desc())
            .limit(100)
        ).mappings().all()
        return [_serialize(row) for row in rows]


def list_renter_tenancies(*, renter_user_id: int) -> list[dict]:
    """Only the current renter's rental history; no private owner details."""
    _id(renter_user_id, "renter ID")
    _, properties, _, tenancies = _tables()
    with SessionLocal() as session:
        _require_role(session, user_id=renter_user_id, role="renter")
        rows = session.execute(
            select(
                tenancies.c.id,
                tenancies.c.inquiry_id,
                tenancies.c.property_id,
                tenancies.c.room_label,
                tenancies.c.monthly_rent,
                tenancies.c.rent_due_day,
                tenancies.c.move_in_date,
                tenancies.c.move_out_date,
                tenancies.c.status,
                tenancies.c.created_at,
                tenancies.c.ended_at,
                properties.c.name.label("property_name"),
                properties.c.address.label("property_address"),
            )
            .join(properties, tenancies.c.property_id == properties.c.id)
            .where(tenancies.c.renter_user_id == renter_user_id)
            .order_by(tenancies.c.created_at.desc(), tenancies.c.id.desc())
            .limit(100)
        ).mappings().all()
        return [_serialize(row) for row in rows]


def end_tenancy(
    *,
    owner_user_id: int,
    tenancy_id: int,
    move_out_date: str | date | None = None,
) -> dict:
    """
    End an active tenancy and restore exactly one available room, atomically.

    The date must be between the move-in date and today. Ending a future
    tenancy is not supported by this simple active/ended schema.
    """
    _id(owner_user_id, "owner ID")
    _id(tenancy_id, "tenancy ID")
    today = datetime.now(LOCAL_TZ).date()
    out_date = today if move_out_date is None else _date(move_out_date, "Move-out date")
    if out_date > today:
        raise TenancyValidationError("Move-out date cannot be in the future.")

    _, properties, _, tenancies = _tables()
    with SessionLocal.begin() as session:
        _require_role(session, user_id=owner_user_id, role="property_owner")
        property_id = session.execute(
            select(tenancies.c.property_id).where(tenancies.c.id == tenancy_id)
        ).scalar_one_or_none()
        if property_id is None:
            raise TenancyNotFoundError("Tenancy not found.")

        property_row = session.execute(
            select(
                properties.c.id,
                properties.c.owner_user_id,
                properties.c.total_rooms,
                properties.c.available_rooms,
            )
            .where(properties.c.id == property_id)
            .with_for_update()
        ).mappings().one_or_none()
        if property_row is None or property_row["owner_user_id"] != owner_user_id:
            raise TenancyNotFoundError("Tenancy not found.")

        tenancy = session.execute(
            select(
                tenancies.c.id,
                tenancies.c.status,
                tenancies.c.move_in_date,
            )
            .where(tenancies.c.id == tenancy_id, tenancies.c.property_id == property_id)
            .with_for_update()
        ).mappings().one_or_none()
        if tenancy is None:
            raise TenancyNotFoundError("Tenancy not found.")
        if tenancy["status"] != "active":
            raise TenancyConflictError("Tenancy has already ended.")
        if out_date < tenancy["move_in_date"]:
            raise TenancyValidationError("Move-out date cannot precede move-in date.")

        total, available = _assert_property_counts(property_row)
        if available >= total:
            raise TenancyConflictError(
                "Room availability is already full; reconcile counts before ending."
            )

        session.execute(
            update(tenancies)
            .where(tenancies.c.id == tenancy_id)
            .values(
                status="ended",
                move_out_date=out_date,
                ended_at=func.now(),
                updated_at=func.now(),
            )
        )
        session.execute(
            update(properties)
            .where(properties.c.id == property_id)
            .values(
                available_rooms=available + 1,
                updated_at=func.now(),
            )
        )
        return {
            "id": tenancy_id,
            "status": "ended",
            "move_out_date": out_date.isoformat(),
            "available_rooms_after": available + 1,
        }
