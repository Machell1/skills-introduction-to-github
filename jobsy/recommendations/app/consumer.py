"""Event consumer that logs user interactions for recommendation training."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from shared.database import async_session_factory
from shared.events import consume_events

from app.models import InteractionLog

logger = logging.getLogger(__name__)


async def handle_swipe_right(payload: dict) -> None:
    """Log a positive interaction signal."""
    data = payload.get("data", {})
    await _log_interaction(
        user_id=data.get("swiper_id"),
        target_id=data.get("target_id"),
        target_type=data.get("target_type", "unknown"),
        action="right_swipe",
    )


async def handle_swipe_left(payload: dict) -> None:
    """Log a negative interaction signal."""
    data = payload.get("data", {})
    await _log_interaction(
        user_id=data.get("swiper_id"),
        target_id=data.get("target_id"),
        target_type=data.get("target_type", "unknown"),
        action="left_swipe",
    )


async def _log_interaction(user_id: str | None, target_id: str | None, target_type: str, action: str) -> None:
    if not user_id or not target_id:
        return

    async with async_session_factory() as db:
        log_entry = InteractionLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            target_id=target_id,
            target_type=target_type,
            action=action,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        await db.commit()

    logger.info("Logged %s: user=%s target=%s", action, user_id, target_id)


async def start_consumers() -> None:
    """Start recommendation event consumers."""
    logger.info("Starting recommendation consumers...")
    await asyncio.gather(
        consume_events("recommendations.swipe_right", "swipe.right", handle_swipe_right),
        consume_events("recommendations.swipe_left", "swipe.left", handle_swipe_left),
    )
