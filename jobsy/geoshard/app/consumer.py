"""Event consumer that updates the geoshard index when profiles/listings change location."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from shared.database import async_session_factory
from shared.events import consume_events
from shared.geo import encode_geohash, get_parish

from app.models import GeoshardEntry
from app.s2_utils import lat_lng_to_s2_cell_id

logger = logging.getLogger(__name__)


async def handle_profile_updated(payload: dict) -> None:
    """Index or update a profile's geospatial entry."""
    data = payload.get("data", {})
    user_id = data.get("user_id")
    lat = data.get("latitude")
    lng = data.get("longitude")

    if not user_id or lat is None or lng is None:
        return

    await _upsert_entry(entity_id=user_id, entity_type="profile", lat=lat, lng=lng)
    logger.info("Indexed profile %s at (%s, %s)", user_id, lat, lng)


async def handle_listing_created(payload: dict) -> None:
    """Index a new listing's geospatial entry."""
    data = payload.get("data", {})
    listing_id = data.get("listing_id")
    lat = data.get("latitude")
    lng = data.get("longitude")

    if not listing_id or lat is None or lng is None:
        return

    await _upsert_entry(entity_id=listing_id, entity_type="listing", lat=lat, lng=lng)
    logger.info("Indexed listing %s at (%s, %s)", listing_id, lat, lng)


async def _upsert_entry(entity_id: str, entity_type: str, lat: float, lng: float) -> None:
    """Insert or update a geoshard index entry."""
    geohash = encode_geohash(lat, lng, precision=7)
    s2_cell_id = lat_lng_to_s2_cell_id(lat, lng)
    parish = get_parish(lat, lng)
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        result = await db.execute(
            select(GeoshardEntry).where(
                GeoshardEntry.entity_id == entity_id,
                GeoshardEntry.entity_type == entity_type,
            )
        )
        entry = result.scalar_one_or_none()

        if entry:
            entry.geohash = geohash
            entry.s2_cell_id = s2_cell_id
            entry.latitude = lat
            entry.longitude = lng
            entry.parish = parish
            entry.updated_at = now
        else:
            entry = GeoshardEntry(
                id=str(uuid.uuid4()),
                entity_id=entity_id,
                entity_type=entity_type,
                geohash=geohash,
                s2_cell_id=s2_cell_id,
                latitude=lat,
                longitude=lng,
                parish=parish,
                created_at=now,
                updated_at=now,
            )
            db.add(entry)

        await db.commit()


async def start_consumers() -> None:
    """Start all geoshard event consumers."""
    logger.info("Starting geoshard consumers...")
    await asyncio.gather(
        consume_events("geoshard.profile_updated", "profile.updated", handle_profile_updated),
        consume_events("geoshard.listing_created", "listing.created", handle_listing_created),
    )
