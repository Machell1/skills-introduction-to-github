"""SQLAlchemy ORM models for the recommendation engine."""

from sqlalchemy import Column, DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id = Column(String, primary_key=True)
    preferred_categories = Column(JSONB, default=[])
    preferred_parishes = Column(JSONB, default=[])
    budget_range = Column(JSONB, default={})  # {"min": 0, "max": 50000}
    max_distance_km = Column(Numeric(6, 1), default=25.0)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class InteractionScore(Base):
    __tablename__ = "interaction_scores"

    user_id = Column(String, primary_key=True)
    target_id = Column(String, primary_key=True)
    score = Column(Numeric(5, 4), nullable=False)  # 0.0000 to 1.0000
    factors = Column(JSONB, default={})  # breakdown of scoring components
    computed_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_interaction_user", "user_id"),
        Index("idx_interaction_score", "user_id", "score"),
    )


class InteractionLog(Base):
    """Raw interaction events for training the ranking model."""

    __tablename__ = "interaction_log"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    target_id = Column(String, nullable=False)
    target_type = Column(String(20), nullable=False)
    action = Column(String(20), nullable=False)  # 'right_swipe', 'left_swipe', 'view', 'message'
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), nullable=False)
