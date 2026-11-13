"""Dormora — System Functionality File 43.

CREATE: backend/app/services/rent_management_service.py

PostgreSQL-backed monthly rent charges and owner-recorded payments.
Depends on the File 42 tables/view and the existing tenancy schema.

No charge is created automatically, no money is transferred, and no
existing tenancy/property/inquiry record is modified by this service.
The future API must obtain user IDs from verified server-side sessions.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlalchemy import MetaData, Table, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal, engine


_MANILA = ZoneInfo("Asia/Manila")
_METHODS = frozenset({"cash", "bank_transfer", "e_wallet", "other"})
_MONEY_PATTERN = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,2})?\Z")
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_MONTH_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}(?:-01)?\Z")


class RentManagementError(Exception):
    """Base class for expected rent-management errors."""


class RentValidationError(RentManagementError):
    """A submitted amount, date, or other field is invalid."""


class RentAccessError(RentManagementError):
    """The current account cannot use the requested operation."""


class RentNotFoundError(RentManagementError):
    """The requested charge or tenancy is missing or not accessible."""


class RentConflictError(RentManagementError):
    """The operation conflicts with an existing charge or payment."""


@lru_cache(maxsize=1)
def _tables() -> dict[str, Table]:
    """Reflect the existing tables and balance view without altering them."""
    metadata = MetaData()
    names = (
        "users", "dorm_properties", "dorm_tenancies",
        "dorm_rent_charges", "dorm_rent_payments", "dorm_rent_balances",
    )
    return {
        name: Table(name, metadata, schema="public", autoload_with=engine)
        for name in names
    }


def _require_id(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise RentValidationError(f"Invalid {label}.")
    return value


def _account_role(session, user_id: int) -> str:
    """Confirm an active, email-verified renter or property owner."""
    _require_id(user_id, "account ID")
    users = _tables()["users"]
    account = session.execute(
        select(
            users.c.role, users.c.account_status, users.c.email_verified_at,
        ).where(users.c.user_id == user_id)
    ).mappings().one_or_none()
    if (
        account is None
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
        or account["role"] not in {"renter", "property_owner"}
    ):
        raise RentAccessError("Account is not eligible for rent management.")
    return account["role"]


def _require_owner(session, owner_user_id: int) -> None:
    if _account_role(session, owner_user_id) != "property_owner":
        raise RentAccessError("Property owner access required.")


def _parse_month(value: str | date) -> date:
    """Accept YYYY-MM, YYYY-MM-01, or a first-of-month date object."""
    if isinstance(value, datetime):
        raise RentValidationError("Billing month must not contain a time.")
    if isinstance(value, date):
        result = value
    elif isinstance(value, str):
        raw = value.strip()
        if not _MONTH_PATTERN.fullmatch(raw):
            raise RentValidationError("Billing month must be YYYY-MM.")
        try:
            result = date.fromisoformat(raw + "-01" if len(raw) == 7 else raw)
        except ValueError as exc:
            raise RentValidationError("Invalid billing month.") from exc
    else:
        raise RentValidationError("Invalid billing month.")
    if result.day != 1:
        raise RentValidationError("Billing month must start on day 1.")
    return result


def _parse_paid_on(value: str | date | None) -> date:
    if value is None:
        result = datetime.now(_MANILA).date()
    elif isinstance(value, datetime):
        raise RentValidationError("Payment date must not contain a time.")
    elif isinstance(value, date):
        result = value
    elif isinstance(value, str) and _DATE_PATTERN.fullmatch(value.strip()):
        try:
            result = date.fromisoformat(value.strip())
        except ValueError as exc:
            raise RentValidationError("Invalid payment date.") from exc
    else:
        raise RentValidationError("Payment date must be YYYY-MM-DD.")
    if result > datetime.now(_MANILA).date():
        raise RentValidationError("Payment date cannot be in the future.")
    return result


def _parse_amount(value: str | int | Decimal) -> Decimal:
    """Require a positive exact peso amount with at most two decimal places."""
    if isinstance(value, bool) or isinstance(value, float):
        raise RentValidationError("Enter the payment amount as a decimal string.")
    if not isinstance(value, (str, int, Decimal)):
        raise RentValidationError("Invalid payment amount.")
    raw = str(value).strip()
    if not _MONEY_PATTERN.fullmatch(raw):
        raise RentValidationError("Amount must be positive with at most 2 decimals.")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise RentValidationError("Invalid payment amount.") from exc
    if result <= 0:
        raise RentValidationError("Payment amount must be greater than zero.")
    return result


def _parse_note(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RentValidationError("Payment note must be text.")
    result = value.strip()
    if not result:
        return None
    if len(result) > 200 or "\x00" in result:
        raise RentValidationError("Payment note must be at most 200 characters.")
    return result


def _serialize(row) -> dict:
    """Make SQLAlchemy result mappings safe for FastAPI JSON responses."""
    data = dict(row)
    for key, value in data.items():
        if isinstance(value, Decimal):
            data[key] = str(value)
        elif isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
    return data


def create_monthly_rent_charge(
    *, owner_user_id: int, tenancy_id: int, billing_month: str | date,
) -> dict:
    """Create exactly one charge for a tenancy's rental month.

    The amount is the agreed monthly rent stored on the tenancy, not the
    property's currently advertised price. Full-month billing is used;
    automatic prorating is intentionally not supported in this version.
    """
    _require_id(tenancy_id, "tenancy ID")
    month = _parse_month(billing_month)
    tables = _tables()
    tenancies = tables["dorm_tenancies"]
    properties = tables["dorm_properties"]
    charges = tables["dorm_rent_charges"]

    try:
        with SessionLocal.begin() as session:
            _require_owner(session, owner_user_id)
            tenancy = session.execute(
                select(
                    tenancies.c.id,
                    tenancies.c.status,
                    tenancies.c.move_in_date,
                    tenancies.c.monthly_rent,
                    tenancies.c.rent_due_day,
                )
                .select_from(
                    tenancies.join(
                        properties, tenancies.c.property_id == properties.c.id,
                    )
                )
                .where(
                    tenancies.c.id == tenancy_id,
                    properties.c.owner_user_id == owner_user_id,
                )
                .with_for_update(of=tenancies)
            ).mappings().one_or_none()

            if tenancy is None:
                raise RentNotFoundError("Tenancy not found.")
            if tenancy["status"] != "active":
                raise RentConflictError("Only active tenancies can receive new charges.")
            move_in_month = tenancy["move_in_date"].replace(day=1)
            if month < move_in_month:
                raise RentValidationError(
                    "Billing month cannot precede the agreed move-in month."
                )
            due_day = int(tenancy["rent_due_day"])
            if not 1 <= due_day <= 28:
                raise RentValidationError("Tenancy has an invalid rent due day.")
            due_date = month.replace(day=due_day)

            existing = session.execute(
                select(charges.c.id).where(
                    charges.c.tenancy_id == tenancy_id,
                    charges.c.billing_month == month,
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise RentConflictError("This tenancy already has a charge for that month.")

            amount_due = tenancy["monthly_rent"]
            charge_id = session.execute(
                insert(charges)
                .values(
                    tenancy_id=tenancy_id,
                    billing_month=month,
                    due_date=due_date,
                    amount_due=amount_due,
                )
                .returning(charges.c.id)
            ).scalar_one()

            return {
                "id": charge_id,
                "tenancy_id": tenancy_id,
                "billing_month": month.isoformat(),
                "due_date": due_date.isoformat(),
                "amount_due": str(amount_due),
                "message": "Monthly rent charge created.",
            }
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "dorm_rent_charges_one_per_month":
            raise RentConflictError(
                "This tenancy already has a charge for that month."
            ) from exc
        raise


def record_rent_payment(
    *,
    owner_user_id: int,
    charge_id: int,
    amount: str | int | Decimal,
    payment_method: str,
    paid_on: str | date | None = None,
    reference_note: str | None = None,
) -> dict:
    """Record an owner-confirmed payment without performing a money transfer.

    A FOR UPDATE lock on the charge serializes payment writers so concurrent
    submissions cannot each spend the same remaining balance.
    """
    _require_id(charge_id, "charge ID")
    paid_amount = _parse_amount(amount)
    payment_date = _parse_paid_on(paid_on)
    note = _parse_note(reference_note)
    method = payment_method.strip().lower() if isinstance(payment_method, str) else ""
    if method not in _METHODS:
        raise RentValidationError("Select a valid payment method.")

    tables = _tables()
    charges = tables["dorm_rent_charges"]
    payments = tables["dorm_rent_payments"]
    tenancies = tables["dorm_tenancies"]
    properties = tables["dorm_properties"]

    with SessionLocal.begin() as session:
        _require_owner(session, owner_user_id)
        charge = session.execute(
            select(charges.c.id, charges.c.amount_due)
            .select_from(
                charges.join(
                    tenancies, charges.c.tenancy_id == tenancies.c.id,
                ).join(
                    properties, tenancies.c.property_id == properties.c.id,
                )
            )
            .where(
                charges.c.id == charge_id,
                properties.c.owner_user_id == owner_user_id,
            )
            .with_for_update(of=tenancies)
        ).mappings().one_or_none()
        if charge is None:
            raise RentNotFoundError("Rent charge not found.")

        paid_before = session.execute(
            select(func.coalesce(func.sum(payments.c.amount), 0)).where(
                payments.c.charge_id == charge_id,
            )
        ).scalar_one()
        remaining = charge["amount_due"] - paid_before
        if remaining <= 0:
            raise RentConflictError("This rent charge is already paid.")
        if paid_amount > remaining:
            raise RentConflictError(
                f"Payment exceeds the outstanding balance of {remaining:.2f}."
            )

        saved = session.execute(
            insert(payments)
            .values(
                charge_id=charge_id,
                recorded_by_user_id=owner_user_id,
                amount=paid_amount,
                payment_method=method,
                paid_on=payment_date,
                reference_note=note,
            )
            .returning(payments.c.id, payments.c.created_at)
        ).mappings().one()
        return {
            "id": saved["id"],
            "charge_id": charge_id,
            "amount": str(paid_amount),
            "payment_method": method,
            "paid_on": payment_date.isoformat(),
            "remaining_balance": str(remaining - paid_amount),
            "created_at": saved["created_at"].isoformat(),
            "message": "Payment recorded. No online transfer was performed.",
        }


def _ledger_query():
    """One shared, consistent balance query for owner and renter views."""
    tables = _tables()
    balances = tables["dorm_rent_balances"]
    tenancies = tables["dorm_tenancies"]
    properties = tables["dorm_properties"]
    users = tables["users"]
    renter = users.alias("rent_ledger_renter")

    statement = (
        select(
            balances.c.charge_id,
            balances.c.tenancy_id,
            balances.c.billing_month,
            balances.c.due_date,
            balances.c.amount_due,
            balances.c.total_paid,
            balances.c.balance_due,
            balances.c.payment_status,
            balances.c.created_at,
            tenancies.c.renter_user_id,
            renter.c.username.label("renter_username"),
            tenancies.c.room_label,
            properties.c.id.label("property_id"),
            properties.c.name.label("property_name"),
        )
        .select_from(
            balances.join(
                tenancies, balances.c.tenancy_id == tenancies.c.id,
            ).join(
                properties, tenancies.c.property_id == properties.c.id,
            ).join(
                renter, tenancies.c.renter_user_id == renter.c.user_id,
            )
        )
        .order_by(balances.c.billing_month.desc(), balances.c.charge_id.desc())
        .limit(300)
    )
    return statement, tenancies, properties


def list_owner_rent_records(*, owner_user_id: int) -> list[dict]:
    """List rent charges and computed balances for this owner's properties."""
    statement, _, properties = _ledger_query()
    with SessionLocal() as session:
        _require_owner(session, owner_user_id)
        rows = session.execute(
            statement.where(properties.c.owner_user_id == owner_user_id)
        ).mappings().all()
        return [_serialize(row) for row in rows]


def list_renter_rent_records(*, renter_user_id: int) -> list[dict]:
    """List rent charges and computed balances for this renter only."""
    statement, tenancies, _ = _ledger_query()
    with SessionLocal() as session:
        if _account_role(session, renter_user_id) != "renter":
            raise RentAccessError("Renter access required.")
        rows = session.execute(
            statement.where(tenancies.c.renter_user_id == renter_user_id)
        ).mappings().all()
        return [_serialize(row) for row in rows]


def list_charge_payments(*, user_id: int, charge_id: int) -> list[dict]:
    """Allow the property's owner or its renter to see that charge's payments."""
    _require_id(charge_id, "charge ID")
    tables = _tables()
    charges = tables["dorm_rent_charges"]
    payments = tables["dorm_rent_payments"]
    tenancies = tables["dorm_tenancies"]
    properties = tables["dorm_properties"]

    with SessionLocal() as session:
        role = _account_role(session, user_id)
        query = (
            select(charges.c.id)
            .select_from(
                charges.join(
                    tenancies, charges.c.tenancy_id == tenancies.c.id,
                ).join(
                    properties, tenancies.c.property_id == properties.c.id,
                )
            )
            .where(charges.c.id == charge_id)
        )
        if role == "property_owner":
            query = query.where(properties.c.owner_user_id == user_id)
        else:
            query = query.where(tenancies.c.renter_user_id == user_id)
        if session.execute(query).scalar_one_or_none() is None:
            raise RentNotFoundError("Rent charge not found.")

        rows = session.execute(
            select(
                payments.c.id,
                payments.c.charge_id,
                payments.c.amount,
                payments.c.payment_method,
                payments.c.paid_on,
                payments.c.reference_note,
                payments.c.created_at,
            )
            .where(payments.c.charge_id == charge_id)
            .order_by(payments.c.paid_on.desc(), payments.c.id.desc())
            .limit(300)
        ).mappings().all()
        return [_serialize(row) for row in rows]
