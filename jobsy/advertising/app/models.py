"""SQLAlchemy ORM models for the advertising service."""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.database import Base


class AdPlacement(Base):
    """Defines where ads can appear in the Jobsy UI."""

    __tablename__ = "ad_placements"

    id = Column(String, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)  # 'feed_card', 'profile_banner', etc.
    revive_zone_id = Column(Integer, nullable=True)  # maps to Revive Adserver zone
    description = Column(String, nullable=True)
    position = Column(String(50), nullable=True)  # where in the UI
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class AdCampaign(Base):
    """Local campaign management for Jamaican businesses."""

    __tablename__ = "ad_campaigns"

    id = Column(String, primary_key=True)
    advertiser_name = Column(String(200), nullable=False)
    advertiser_email = Column(String(255), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(String, nullable=True)
    image_url = Column(String(500), nullable=True)
    click_url = Column(String(500), nullable=False)  # destination URL
    target_parishes = Column(JSONB, default=[])  # geo-targeting
    target_categories = Column(JSONB, default=[])  # profession targeting
    budget_total = Column(Numeric(10, 2), nullable=True)  # JMD
    budget_daily = Column(Numeric(10, 2), nullable=True)
    cost_per_click = Column(Numeric(8, 4), nullable=True)
    cost_per_impression = Column(Numeric(8, 4), nullable=True)
    status = Column(String(20), default="active")  # active, paused, completed, expired
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_campaign_status", "status"),
    )


class AdImpression(Base):
    """Tracks ad impressions for reporting and billing."""

    __tablename__ = "ad_impressions"

    id = Column(String, primary_key=True)
    campaign_id = Column(String, nullable=False, index=True)
    placement_id = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    parish = Column(String(50), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False)


class AdClick(Base):
    """Tracks ad clicks for reporting and billing."""

    __tablename__ = "ad_clicks"

    id = Column(String, primary_key=True)
    campaign_id = Column(String, nullable=False, index=True)
    placement_id = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    parish = Column(String(50), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
