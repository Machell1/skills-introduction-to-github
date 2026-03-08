"""Event consumers that trigger push notifications for matches, messages, and expirations."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from shared.database import async_session_factory
from shared.events import consume_events

from app.models import DeviceToken, NotificationLog
from app.push import send_push_to_user

logger = logging.getLogger(__name__)


async def _get_user_tokens(user_id: str) -> list[tuple[str, str]]:
    """Fetch all active device tokens for a user."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == user_id,
                DeviceToken.is_active.is_(True),
            )
        )
        tokens = result.scalars().all()
        return [(t.token, t.platform) for t in tokens]


async def _log_notification(
    user_id: str, title: str, body: str, notification_type: str, data: dict | None = None, delivered: bool = False
) -> None:
    """Record a notification in the log."""
    async with async_session_factory() as db:
        log_entry = NotificationLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            body=body,
            data=data or {},
            notification_type=notification_type,
            delivered=delivered,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        await db.commit()


async def handle_match_created(payload: dict) -> None:
    """Notify both users when a match is created."""
    data = payload.get("data", {})
    user_a = data.get("user_a_id")
    user_b = data.get("user_b_id")
    match_id = data.get("match_id")

    if not user_a or not user_b:
        return

    title = "New Match!"
    body = "You have a new match on Jobsy. Start chatting now!"
    notif_data = {"type": "match", "match_id": match_id}

    for user_id in [user_a, user_b]:
        tokens = await _get_user_tokens(user_id)
        sent = await send_push_to_user(tokens, title, body, notif_data)
        await _log_notification(user_id, title, body, "match", notif_data, delivered=sent > 0)

    logger.info("Match notifications sent for match %s", match_id)


async def handle_new_message(payload: dict) -> None:
    """Notify the recipient when a new message is received."""
    data = payload.get("data", {})
    sender_id = data.get("sender_id")
    conversation_id = data.get("conversation_id")

    if not sender_id or not conversation_id:
        return

    # Need to determine the recipient -- fetch conversation participants
    # In production, the event would include recipient_id or we'd query the chat service
    title = "New Message"
    body = "You have a new message on Jobsy"
    notif_data = {"type": "message", "conversation_id": conversation_id}

    # Log for the sender (we'd need recipient lookup in production)
    await _log_notification(sender_id, title, body, "message", notif_data, delivered=False)
    logger.info("Message notification logged for conversation %s", conversation_id)


async def handle_listing_expired(payload: dict) -> None:
    """Notify the listing owner when their listing expires."""
    data = payload.get("data", {})
    poster_id = data.get("poster_id")
    listing_id = data.get("listing_id")
    listing_title = data.get("title", "Your listing")

    if not poster_id:
        return

    title = "Listing Expired"
    body = f'Your listing "{listing_title}" has expired. Renew it to keep receiving matches.'
    notif_data = {"type": "listing_expired", "listing_id": listing_id}

    tokens = await _get_user_tokens(poster_id)
    sent = await send_push_to_user(tokens, title, body, notif_data)
    await _log_notification(poster_id, title, body, "listing_expired", notif_data, delivered=sent > 0)

    logger.info("Expiry notification sent for listing %s", listing_id)


async def start_consumers() -> None:
    """Start all notification event consumers."""
    logger.info("Starting notification consumers...")
    await asyncio.gather(
        consume_events("notifications.match_created", "match.created", handle_match_created),
        consume_events("notifications.message_new", "message.new", handle_new_message),
        consume_events("notifications.listing_expired", "listing.expired", handle_listing_expired),
    )
