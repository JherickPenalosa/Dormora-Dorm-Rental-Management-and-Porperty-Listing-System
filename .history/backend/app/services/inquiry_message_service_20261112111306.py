
"""
DORMORA — SYSTEM FUNCTIONALITY FILE 29

CREATE: backend/app/services/inquiry_message_service.py

Private, read-only conversation retrieval and append-only inquiry replies.
Uses existing PostgreSQL tables from Files 19 and 28. Does not create or
modify tables, change inquiry decisions, assign rooms, or record payments.

IMPORTANT: The future API must obtain user_id from the verified server-side
session; never accept a user ID from request JSON or query parameters.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import MetaData, Table, insert, select

from app.db.database import SessionLocal, engine


MAX_REPLY_LENGTH = 1000
MAX_DISPLAYED_REPLIES = 200
REPLYABLE_STATUSES = frozenset({"pending", "accepted"})


class InquiryMessagingError(Exception):
    """Base class for expected inquiry messaging errors."""


class InquiryMessageValidationError(InquiryMessagingError):
    """The submitted message or inquiry identifier is invalid."""


class InquiryMessageNotFoundError(InquiryMessagingError):
    """The inquiry does not exist or the account cannot access it."""


class InquiryMessageClosedError(InquiryMessagingError):
    """Replies are no longer allowed for this inquiry status."""


@lru_cache(maxsize=1)
def _tables():
    """Reflect the three existing tables; never create or alter schema."""
    metadata = MetaData()
    users = Table("users", metadata, schema="public", autoload_with=engine)
    properties = Table(
        "dorm_properties", metadata, schema="public", autoload_with=engine
    )
    inquiries = Table(
        "dorm_rental_inquiries", metadata, schema="public", autoload_with=engine
    )
    messages = Table(
        "dorm_inquiry_messages", metadata, schema="public", autoload_with=engine
    )
    return users, properties, inquiries, messages


def _positive_id(value, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise InquiryMessageValidationError(f"Invalid {name}.")
    return value


def _account_role(session, user_id: int) -> str:
    """Verify that the account is active and email-verified."""
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
        or account["account_status"] != "active"
        or account["email_verified_at"] is None
        or account["role"] not in {"renter", "property_owner"}
    ):
        # Use the same response for unauthorized and missing inquiries to
        # avoid revealing whether another person's inquiry exists.
        raise InquiryMessageNotFoundError("Inquiry not found.")

    return account["role"]


def _authorized_inquiry(session, *, inquiry_id: int, user_id: int, lock=False):
    """Fetch a thread only when the session user is one of its participants."""
    _, properties, inquiries, _ = _tables()

    role = _account_role(session, user_id)
    statement = (
        select(
            inquiries.c.id,
            inquiries.c.property_id,
            inquiries.c.renter_user_id,
            inquiries.c.message,
            inquiries.c.status,
            inquiries.c.created_at,
            properties.c.name.label("property_name"),
            properties.c.owner_user_id,
        )
        .select_from(
            inquiries.join(properties, inquiries.c.property_id == properties.c.id)
        )
        .where(inquiries.c.id == inquiry_id)
    )

    if lock:
        # Serialize replies against withdrawal or owner review, which also
        # lock this inquiry row before updating its status.
        statement = statement.with_for_update(of=inquiries)

    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise InquiryMessageNotFoundError("Inquiry not found.")

    is_renter = role == "renter" and row["renter_user_id"] == user_id
    is_owner = (
        role == "property_owner" and row["owner_user_id"] == user_id
    )

    if not (is_renter or is_owner):
        raise InquiryMessageNotFoundError("Inquiry not found.")

    return row


def _timestamp(value):
    return value.isoformat() if value is not None else None


def _format_message(row, *, renter_id: int) -> dict:
    return {
        "id": row["id"],
        "kind": "reply",
        "sender_role": (
            "renter" if row["sender_user_id"] == renter_id else "property_owner"
        ),
        "message_text": row["message_text"],
        "created_at": _timestamp(row["created_at"]),
    }


def _clean_reply(message_text: str) -> str:
    if not isinstance(message_text, str):
        raise InquiryMessageValidationError("Message must be text.")

    # Normalize line endings, preserve reasonable multiline replies, and
    # prevent PostgreSQL's unsupported NUL character from reaching storage.
    cleaned = message_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        raise InquiryMessageValidationError("Please enter a reply.")
    if "\x00" in cleaned:
        raise InquiryMessageValidationError("Message contains an invalid character.")
    if len(cleaned) > MAX_REPLY_LENGTH:
        raise InquiryMessageValidationError(
            f"Reply cannot exceed {MAX_REPLY_LENGTH} characters."
        )
    return cleaned


def get_inquiry_conversation(*, user_id: int, inquiry_id: int) -> dict:
    """
    Return a private inquiry conversation for its renter or property owner.

    The renter's initial inquiry text is stored in File 19's inquiry table;
    show it as the first conversation item rather than duplicating the row
    into File 28's messages table.

    At most the latest 200 replies are returned, oldest to newest. The
    has_older_replies flag tells the UI if earlier replies are omitted.
    """
    _positive_id(user_id, "user ID")
    _positive_id(inquiry_id, "inquiry ID")
    _, _, _, messages_table = _tables()

    with SessionLocal() as session:
        inquiry = _authorized_inquiry(
            session, inquiry_id=inquiry_id, user_id=user_id
        )

        newest_first = session.execute(
            select(
                messages_table.c.id,
                messages_table.c.sender_user_id,
                messages_table.c.message_text,
                messages_table.c.created_at,
            )
            .where(messages_table.c.inquiry_id == inquiry_id)
            .order_by(
                messages_table.c.created_at.desc(),
                messages_table.c.id.desc(),
            )
            .limit(MAX_DISPLAYED_REPLIES + 1)
        ).mappings().all()

        has_older_replies = len(newest_first) > MAX_DISPLAYED_REPLIES
        latest_replies = newest_first[:MAX_DISPLAYED_REPLIES]
        thread = [
            _format_message(row, renter_id=inquiry["renter_user_id"])
            for row in reversed(latest_replies)
        ]

        initial_text = inquiry["message"]
        if isinstance(initial_text, str) and initial_text.strip():
            thread.insert(0, {
                "id": None,
                "kind": "initial_inquiry",
                "sender_role": "renter",
                "message_text": initial_text,
                "created_at": _timestamp(inquiry["created_at"]),
            })

        return {
            "inquiry": {
                "id": inquiry["id"],
                "property_id": inquiry["property_id"],
                "property_name": inquiry["property_name"],
                "status": inquiry["status"],
                "created_at": _timestamp(inquiry["created_at"]),
                "can_reply": inquiry["status"] in REPLYABLE_STATUSES,
            },
            "messages": thread,
            "has_older_replies": has_older_replies,
        }


def send_inquiry_reply(*, user_id: int, inquiry_id: int, message_text: str) -> dict:
    """
    Append one reply to a pending or accepted inquiry.

    The database transaction also checks the current inquiry status while
    holding its row lock. No status or room-count changes occur here.
    """
    _positive_id(user_id, "user ID")
    _positive_id(inquiry_id, "inquiry ID")
    text = _clean_reply(message_text)
    _, _, _, messages_table = _tables()

    with SessionLocal.begin() as session:
        inquiry = _authorized_inquiry(
            session,
            inquiry_id=inquiry_id,
            user_id=user_id,
            lock=True,
        )

        if inquiry["status"] not in REPLYABLE_STATUSES:
            raise InquiryMessageClosedError(
                "This inquiry is closed for new replies."
            )

        saved = session.execute(
            insert(messages_table)
            .values(
                inquiry_id=inquiry_id,
                sender_user_id=user_id,
                message_text=text,
            )
            .returning(
                messages_table.c.id,
                messages_table.c.sender_user_id,
                messages_table.c.message_text,
                messages_table.c.created_at,
            )
        ).mappings().one()

        return {
            "inquiry_id": inquiry_id,
            "message": _format_message(
                saved, renter_id=inquiry["renter_user_id"]
            ),
        }
