"""Advertising service API routes -- ad serving, impression/click tracking, campaigns."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db

from app.models import AdCampaign, AdClick, AdImpression, AdPlacement
from app.revive import fetch_ad_from_revive, report_click_to_revive, report_impression_to_revive

router = APIRouter(tags=["advertising"])


def _get_user_id(request: Request) -> str | None:
    return request.headers.get("X-User-ID")


@router.get("/serve/{placement_name}")
async def serve_ad(
    placement_name: str,
    request: Request,
    parish: str | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Serve an ad creative for a given placement.

    Flow:
    1. Look up placement in database
    2. Try Revive Adserver if configured
    3. Fall back to local campaign matching (geo + category targeting)
    4. Return ad creative data
    """
    user_id = _get_user_id(request)

    # Find the placement
    result = await db.execute(
        select(AdPlacement).where(
            AdPlacement.name == placement_name,
            AdPlacement.is_active.is_(True),
        )
    )
    placement = result.scalar_one_or_none()
    if not placement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Placement not found")

    # Try Revive first
    if placement.revive_zone_id:
        revive_ad = await fetch_ad_from_revive(placement.revive_zone_id, parish)
        if revive_ad:
            return revive_ad

    # Fall back to local campaigns
    query = select(AdCampaign).where(AdCampaign.status == "active")

    # Geo-targeting: match user's parish
    if parish:
        # Campaigns targeting this parish OR targeting all (empty array)
        query = query.where(
            AdCampaign.target_parishes.op("@>")(f'["{parish}"]')
            | (AdCampaign.target_parishes == [])
        )

    # Category targeting
    if category:
        query = query.where(
            AdCampaign.target_categories.op("@>")(f'["{category}"]')
            | (AdCampaign.target_categories == [])
        )

    query = query.limit(1)
    result = await db.execute(query)
    campaign = result.scalar_one_or_none()

    if not campaign:
        return {"ad": None, "placement": placement_name}

    # Record impression
    impression = AdImpression(
        id=str(uuid.uuid4()),
        campaign_id=campaign.id,
        placement_id=placement.id,
        user_id=user_id,
        parish=parish,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(impression)
    await db.flush()

    if placement.revive_zone_id:
        await report_impression_to_revive(placement.revive_zone_id)

    return {
        "ad": {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "description": campaign.description,
            "image_url": campaign.image_url,
            "click_url": f"/ads/click/{campaign.id}?placement={placement.id}",
        },
        "placement": placement_name,
    }


@router.get("/click/{campaign_id}")
async def record_click(
    campaign_id: str,
    request: Request,
    placement: str | None = None,
    parish: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Record an ad click and redirect to the advertiser's URL."""
    user_id = _get_user_id(request)

    result = await db.execute(select(AdCampaign).where(AdCampaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Record click
    click = AdClick(
        id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        placement_id=placement,
        user_id=user_id,
        parish=parish,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(click)
    await db.flush()

    return RedirectResponse(url=campaign.click_url, status_code=302)


@router.post("/impression")
async def record_impression(
    request: Request,
    campaign_id: str = Query(...),
    placement_id: str | None = None,
    parish: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Record an ad impression (called by frontend clients)."""
    user_id = _get_user_id(request)

    impression = AdImpression(
        id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        placement_id=placement_id,
        user_id=user_id,
        parish=parish,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(impression)
    await db.flush()

    return {"status": "recorded"}


# --- Campaign management (for admin/advertiser use) ---


class CampaignCreate(BaseModel):
    advertiser_name: str = Field(..., max_length=200)
    advertiser_email: str | None = None
    title: str = Field(..., max_length=200)
    description: str | None = None
    image_url: str | None = None
    click_url: str
    target_parishes: list[str] = Field(default_factory=list)
    target_categories: list[str] = Field(default_factory=list)
    budget_total: float | None = None
    budget_daily: float | None = None
    cost_per_click: float | None = None
    cost_per_impression: float | None = None


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    """Create a new advertising campaign."""
    now = datetime.now(timezone.utc)
    campaign = AdCampaign(
        id=str(uuid.uuid4()),
        advertiser_name=data.advertiser_name,
        advertiser_email=data.advertiser_email,
        title=data.title,
        description=data.description,
        image_url=data.image_url,
        click_url=data.click_url,
        target_parishes=data.target_parishes,
        target_categories=data.target_categories,
        budget_total=data.budget_total,
        budget_daily=data.budget_daily,
        cost_per_click=data.cost_per_click,
        cost_per_impression=data.cost_per_impression,
        created_at=now,
        updated_at=now,
    )
    db.add(campaign)
    await db.flush()

    return {"id": campaign.id, "title": campaign.title, "status": campaign.status}


@router.get("/campaigns")
async def list_campaigns(
    status_filter: str = Query(default="active", alias="status"),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List advertising campaigns."""
    query = select(AdCampaign).where(AdCampaign.status == status_filter).limit(limit)
    result = await db.execute(query)
    campaigns = result.scalars().all()

    return [
        {
            "id": c.id,
            "advertiser_name": c.advertiser_name,
            "title": c.title,
            "status": c.status,
            "target_parishes": c.target_parishes,
            "created_at": c.created_at.isoformat(),
        }
        for c in campaigns
    ]


@router.get("/campaigns/{campaign_id}/report")
async def campaign_report(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """Get performance report for a campaign (impressions, clicks, CTR)."""
    result = await db.execute(select(AdCampaign).where(AdCampaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    impressions_result = await db.execute(
        select(func.count()).where(AdImpression.campaign_id == campaign_id)
    )
    impressions = impressions_result.scalar() or 0

    clicks_result = await db.execute(
        select(func.count()).where(AdClick.campaign_id == campaign_id)
    )
    clicks = clicks_result.scalar() or 0

    ctr = (clicks / impressions * 100) if impressions > 0 else 0.0

    return {
        "campaign_id": campaign_id,
        "title": campaign.title,
        "advertiser": campaign.advertiser_name,
        "impressions": impressions,
        "clicks": clicks,
        "ctr_percent": round(ctr, 2),
        "status": campaign.status,
    }
