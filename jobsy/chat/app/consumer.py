"""Event consumer that auto-creates conversations when matches are formed."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from shared.database import async_session_factory
from shared.events import consume_events

from app.models import Conversation

logger = logging.getLogger(__name__)


async def handle_match_created(payload: dict) -> None:
    """Create a conversation when a new match is formed."""
    data = payload.get("data", {})
    match_id = data.get("match_id")
    user_a_id = data.get("user_a_id")
    user_b_id = data.get("user_b_id")

    if not match_id or not user_a_id or not user_b_id:
        logger.warning("Invalid match.created event: %s", data)
        return

    async with async_session_factory() as db:
        # Check if conversation already exists for this match
        result = await db.execute(
            select(Conversation).where(Conversation.match_id == match_id)
        )
        if result.scalar_one_or_none():
            logger.info("Conversation already exists for match %s", match_id)
            return

        conversation = Conversation(
            id=str(uuid.uuid4()),
            match_id=match_id,
            user_a_id=user_a_id,
            user_b_id=user_b_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        await db.commit()

    logger.info("Created conversation for match %s between %s and %s", match_id, user_a_id, user_b_id)


async def start_consumer() -> None:
    """Start the chat event consumer."""
    logger.info("Starting chat consumer...")
    await consume_events("chat.match_created", "match.created", handle_match_created)
