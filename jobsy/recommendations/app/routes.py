"""Recommendation service API routes."""

import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db

from app.models import UserPreference
from app.ranker import rank_candidate

router = APIRouter(tags=["recommendations"])

GEOSHARD_URL = os.getenv("GEOSHARD_SERVICE_URL", "http://geoshard.railway.internal:8000")
LISTINGS_URL = os.getenv("LISTINGS_SERVICE_URL", "http://listings.railway.internal:8000")
PROFILES_URL = os.getenv("PROFILES_SERVICE_URL", "http://profiles.railway.internal:8000")


def _get_user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user context")
    return user_id


class PreferencesUpdate(BaseModel):
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_parishes: list[str] = Field(default_factory=list)
    budget_range: dict = Field(default_factory=dict)
    max_distance_km: float = 25.0


class FeedbackCreate(BaseModel):
    target_id: str
    target_type: str
    action: str  # 'view', 'dwell', etc.
    duration_ms: int | None = None


@router.get("/feed")
async def get_recommendation_feed(
    request: Request,
    lat: float | None = None,
    lng: float | None = None,
    limit: int = Query(default=20, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get a ranked feed of listings/profiles for the swipe interface.

    Flow:
    1. Fetch user preferences from DB
    2. Query geoshard service for nearby entities
    3. Fetch full entity details from listings/profiles services
    4. Score and rank using the ranker algorithm
    5. Return sorted results
    """
    user_id = _get_user_id(request)

    # 1. Get user preferences
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    prefs = result.scalar_one_or_none()

    preferred_categories = prefs.preferred_categories if prefs else []
    budget_range = prefs.budget_range if prefs else {}
    max_distance = float(prefs.max_distance_km) if prefs else 25.0

    # 2. Get nearby entities from geoshard
    nearby_entities = []
    if lat is not None and lng is not None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{GEOSHARD_URL}/nearby",
                    params={
                        "lat": lat,
                        "lng": lng,
                        "radius_km": max_distance,
                        "entity_type": "listing",
                        "limit": limit * 3,  # fetch more to filter/rank from
                    },
                )
                if resp.status_code == 200:
                    nearby_entities = resp.json()
        except httpx.RequestError:
            pass  # Fall back to unranked results

    # 3. Fetch listing details for nearby entities
    ranked_results = []
    if nearby_entities:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for entity in nearby_entities:
                try:
                    resp = await client.get(
                        f"{LISTINGS_URL}/{entity['entity_id']}",
                        headers={"X-User-ID": user_id},
                    )
                    if resp.status_code != 200:
                        continue
                    listing = resp.json()

                    # 4. Score the candidate
                    created_at = datetime.fromisoformat(listing.get("created_at", datetime.now(timezone.utc).isoformat()))
                    score_result = rank_candidate(
                        distance_km=entity.get("distance_km"),
                        listing_category=listing.get("category"),
                        listing_budget_min=Decimal(str(listing["budget_min"])) if listing.get("budget_min") else None,
                        listing_budget_max=Decimal(str(listing["budget_max"])) if listing.get("budget_max") else None,
                        created_at=created_at,
                        user_preferred_categories=preferred_categories,
                        user_budget_range=budget_range,
                    )

                    ranked_results.append({
                        **listing,
                        "distance_km": entity.get("distance_km"),
                        "score": score_result["total_score"],
                        "score_factors": score_result["factors"],
                    })
                except httpx.RequestError:
                    continue

    # 5. Sort by score descending
    ranked_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return ranked_results[:limit]


@router.put("/preferences")
async def update_preferences(
    data: PreferencesUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    """Update user's recommendation preferences."""
    user_id = _get_user_id(request)
    now = datetime.now(timezone.utc)

    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    prefs = result.scalar_one_or_none()

    if prefs:
        prefs.preferred_categories = data.preferred_categories
        prefs.preferred_parishes = data.preferred_parishes
        prefs.budget_range = data.budget_range
        prefs.max_distance_km = data.max_distance_km
        prefs.updated_at = now
    else:
        prefs = UserPreference(
            user_id=user_id,
            preferred_categories=data.preferred_categories,
            preferred_parishes=data.preferred_parishes,
            budget_range=data.budget_range,
            max_distance_km=data.max_distance_km,
            updated_at=now,
        )
        db.add(prefs)

    await db.flush()
    return {"status": "updated", "user_id": user_id}


@router.post("/feedback")
async def record_feedback(data: FeedbackCreate, request: Request):
    """Record implicit user feedback (dwell time, views) for future ML training."""
    user_id = _get_user_id(request)
    # For now, just acknowledge. In production, write to interaction_log.
    return {"status": "recorded", "user_id": user_id, "target_id": data.target_id}
