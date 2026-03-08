"""Event consumers that keep the search index in sync with listings and profiles."""

import asyncio
import logging

from shared.events import consume_events

from app.elasticsearch_client import index_listing, index_profile

logger = logging.getLogger(__name__)


async def handle_listing_event(payload: dict) -> None:
    """Index a listing when it's created or updated."""
    data = payload.get("data", {})
    if data.get("id"):
        await index_listing(data)
        logger.info("Indexed listing %s", data["id"])


async def handle_profile_event(payload: dict) -> None:
    """Index a profile when it's created or updated."""
    data = payload.get("data", {})
    if data.get("id"):
        await index_profile(data)
        logger.info("Indexed profile %s", data["id"])


async def start_consumers() -> None:
    """Start search indexing consumers."""
    logger.info("Starting search index consumers...")
    await asyncio.gather(
        consume_events("search.listing_created", "listing.created", handle_listing_event),
        consume_events("search.listing_updated", "listing.updated", handle_listing_event),
        consume_events("search.profile_updated", "profile.updated", handle_profile_event),
    )
