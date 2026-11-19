
"""Dormora — System Functionality File 51.

CREATE: backend/app/services/dashboard_summary_service.py

Read-only, role-specific Home dashboard statistics from existing PostgreSQL
records. File 52 will expose get_dashboard_summary() through an authenticated
FastAPI endpoint; a later frontend file will replace the Home placeholders.

This module NEVER creates charges, records payments, changes room counts,
or modifies accounts. Caller IDs must come from verified server-side sessions.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache

from sqlalchemy import MetaData, Table, case, func, select

from app.db.database import SessionLocal, engine


ZERO = Decimal("0.00")


class DashboardSummaryError(Exception):
    """Base class for expected dashboard summary errors."""


class DashboardSummaryAccessError(DashboardSummaryError):
    """Session account is missing, inactive, unverified, or not supported."""


@lru_cache(maxsize=1)
def _tables() -> dict[str, Table]:
    """Reflect existing tables and view; never create or change schema."""
    metadata = MetaData()
    names = (
        "users",
        "dorm_properties",
        "dorm_tenancies",
        "dorm_rent_balances",
    )
    return {
        name: Table(name, metadata, schema="public", autoload_with=engine)
        for name in names
    }


def _authorized_role(session, user_id: int, users: Table) -> str:
    if type(user_id) is not int or user_id <= 0:
        raise DashboardSummaryAccessError("Authentication required.")

    account = session.execute(
        select(
            users.c.role,
            users.c.account_status,
            users.c.email_verified_at,
        ).where(users.c.user_id == user_id)
    ).mappings().one_or_none()

    if (
        account is None
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
        or account["role"] not in {"renter", "property_owner"}
    ):
        raise DashboardSummaryAccessError(
            "An active, verified renter or property owner account is required."
        )
    return account["role"]


def _money(value) -> str:
    """Return exact decimal money as a JSON-friendly two-decimal string."""
    amount = Decimal(str(value)) if value is not None else ZERO
    return str(amount.quantize(Decimal("0.01")))


def _date(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _owner_summary(session, user_id: int, tables: dict[str, Table]) -> dict:
    properties = tables["dorm_properties"]
    tenancies = tables["dorm_tenancies"]
    balances = tables["dorm_rent_balances"]

    property_totals = session.execute(
        select(
            func.count(properties.c.id).label("total_listings"),
            func.coalesce(func.sum(properties.c.total_rooms), 0).label(
                "total_rooms"
            ),
            func.coalesce(func.sum(properties.c.available_rooms), 0).label(
                "available_rooms"
            ),
        ).where(properties.c.owner_user_id == user_id)
    ).mappings().one()

    active_tenants = session.execute(
        select(func.count(tenancies.c.id))
        .select_from(
            tenancies.join(
                properties,
                tenancies.c.property_id == properties.c.id
            )
        )
        .where(
            properties.c.owner_user_id == user_id,
            tenancies.c.status == "active",
        )
    ).scalar_one()

    # Owners see only charges belonging to their own properties.
    rent_totals = session.execute(
        select(
            func.count(balances.c.charge_id).label("rent_charge_count"),
            func.coalesce(
                func.sum(
                    case(
                        (balances.c.balance_due > 0, balances.c.balance_due),
                        else_=0,
                    )
                ),
                0,
            ).label("outstanding_balance"),
            func.coalesce(
                func.sum(
                    case(
                        (balances.c.payment_status == "overdue", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("overdue_charge_count"),
        )
        .select_from(
            balances.join(
                tenancies,
                balances.c.tenancy_id == tenancies.c.id
            ).join(
                properties,
                tenancies.c.property_id == properties.c.id
            )
        )
        .where(properties.c.owner_user_id == user_id)
    ).mappings().one()

    total_rooms = int(property_totals["total_rooms"])
    available_rooms = int(property_totals["available_rooms"])

    return {
        "role": "property_owner",
        "total_listings": int(property_totals["total_listings"]),
        "total_rooms": total_rooms,
        "available_rooms": available_rooms,
        # Allocated rooms includes future move-ins.
        # This is not necessarily physical occupancy.
        "assigned_rooms": max(0, total_rooms - available_rooms),
        "active_tenants": int(active_tenants),
        "rent_charge_count": int(rent_totals["rent_charge_count"]),
        "outstanding_balance": _money(
            rent_totals["outstanding_balance"]
        ),
        "overdue_charge_count": int(
            rent_totals["overdue_charge_count"]
        ),
    }


def _renter_summary(session, user_id: int, tables: dict[str, Table]) -> dict:
    properties = tables["dorm_properties"]
    tenancies = tables["dorm_tenancies"]
    balances = tables["dorm_rent_balances"]

    rental = session.execute(
        select(
            tenancies.c.id.label("tenancy_id"),
            tenancies.c.property_id,
            properties.c.name.label("property_name"),
            tenancies.c.room_label,
            tenancies.c.monthly_rent,
            tenancies.c.rent_due_day,
            tenancies.c.move_in_date,
        )
        .select_from(
            tenancies.join(
                properties,
                tenancies.c.property_id == properties.c.id
            )
        )
        .where(
            tenancies.c.renter_user_id == user_id,
            tenancies.c.status == "active",
        )
        .order_by(
            tenancies.c.created_at.desc(),
            tenancies.c.id.desc()
        )
        .limit(1)
    ).mappings().one_or_none()

    renter_charges = (
        select(
            balances.c.charge_id,
            balances.c.billing_month,
            balances.c.due_date,
            balances.c.balance_due,
            balances.c.payment_status,
        )
        .select_from(
            balances.join(
                tenancies,
                balances.c.tenancy_id == tenancies.c.id
            )
        )
        .where(tenancies.c.renter_user_id == user_id)
    )

    # Older unpaid charges remain visible, even after a tenancy ends.
    next_unpaid = session.execute(
        renter_charges.where(balances.c.balance_due > 0)
        .order_by(
            balances.c.due_date.asc(),
            balances.c.charge_id.asc()
        )
        .limit(1)
    ).mappings().one_or_none()

    latest_charge = None

    if next_unpaid is None:
        latest_charge = session.execute(
            renter_charges.order_by(
                balances.c.billing_month.desc(),
                balances.c.charge_id.desc()
            ).limit(1)
        ).mappings().one_or_none()

    outstanding = session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (balances.c.balance_due > 0, balances.c.balance_due),
                        else_=0,
                    )
                ),
                0,
            )
        )
        .select_from(
            balances.join(
                tenancies,
                balances.c.tenancy_id == tenancies.c.id
            )
        )
        .where(tenancies.c.renter_user_id == user_id)
    ).scalar_one()

    return {
        "role": "renter",
        "tenancy_id": rental["tenancy_id"] if rental else None,
        "property_id": rental["property_id"] if rental else None,
        "current_property_name": (
            rental["property_name"] if rental else None
        ),
        "current_room_label": (
            rental["room_label"] if rental else None
        ),
        "monthly_rent": (
            _money(rental["monthly_rent"]) if rental else None
        ),
        "rent_due_day": (
            rental["rent_due_day"] if rental else None
        ),
        "move_in_date": (
            _date(rental["move_in_date"]) if rental else None
        ),
        "next_unpaid_charge_id": (
            next_unpaid["charge_id"] if next_unpaid else None
        ),
        "next_due_date": (
            _date(next_unpaid["due_date"]) if next_unpaid else None
        ),
        "payment_status": (
            next_unpaid["payment_status"]
            if next_unpaid
            else latest_charge["payment_status"]
            if latest_charge
            else "no_records"
        ),
        "outstanding_balance": _money(outstanding),
    }


def get_dashboard_summary(*, user_id: int) -> dict:
    """Read only the authenticated user's role-specific dashboard totals.

    File 52 must call this with a verified session user ID,
    not a user-controlled query/body parameter.
    No writes are performed.
    """
    tables = _tables()

    with SessionLocal() as session:
        role = _authorized_role(session, user_id, tables["users"])

        if role == "property_owner":
            return _owner_summary(session, user_id, tables)

        return _renter_summary(session, user_id, tables)
