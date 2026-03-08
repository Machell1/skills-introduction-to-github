"""Revive Adserver integration client.

Revive Adserver is an open-source ad server that manages ad inventory,
delivery rules, geo-targeting, frequency caps, and campaign reporting.

This module communicates with Revive's XML-RPC or REST API to:
1. Request ad creatives for a given zone/placement
2. Record impressions and clicks
3. Fetch campaign performance reports

When Revive is not configured, falls back to serving local campaigns
directly from the Jobsy database.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

REVIVE_BASE_URL = os.getenv("REVIVE_BASE_URL")  # e.g., http://revive.railway.internal
REVIVE_API_KEY = os.getenv("REVIVE_API_KEY")


async def fetch_ad_from_revive(zone_id: int, user_parish: str | None = None) -> dict | None:
    """Fetch an ad creative from Revive Adserver for a given zone.

    Args:
        zone_id: Revive zone ID mapped to a Jobsy placement
        user_parish: User's parish for geo-targeting

    Returns:
        dict with ad creative data, or None if Revive is unavailable
    """
    if not REVIVE_BASE_URL:
        logger.debug("Revive not configured, using local campaigns")
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            params = {"zoneid": zone_id}
            if user_parish:
                params["geo"] = user_parish

            resp = await client.get(
                f"{REVIVE_BASE_URL}/www/delivery/ajs.php",
                params=params,
                headers={"X-Api-Key": REVIVE_API_KEY} if REVIVE_API_KEY else {},
            )

            if resp.status_code == 200:
                return {
                    "source": "revive",
                    "zone_id": zone_id,
                    "creative_html": resp.text,
                }
    except httpx.RequestError:
        logger.warning("Failed to fetch ad from Revive for zone %d", zone_id)

    return None


async def report_impression_to_revive(zone_id: int, banner_id: int | None = None) -> None:
    """Report an impression to Revive for accurate campaign tracking."""
    if not REVIVE_BASE_URL:
        return

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(
                f"{REVIVE_BASE_URL}/www/delivery/lg.php",
                params={"zoneid": zone_id, "bannerid": banner_id or 0},
            )
    except httpx.RequestError:
        pass


async def report_click_to_revive(zone_id: int, banner_id: int | None = None) -> None:
    """Report a click to Revive for accurate campaign tracking."""
    if not REVIVE_BASE_URL:
        return

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(
                f"{REVIVE_BASE_URL}/www/delivery/ck.php",
                params={"zoneid": zone_id, "bannerid": banner_id or 0},
            )
    except httpx.RequestError:
        pass
