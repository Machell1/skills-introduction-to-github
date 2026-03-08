"""SQLAlchemy ORM models for the reviews service.

Supports both service reviews (after completing a job) and
user reputation scoring.
"""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String, Text

from shared.database import Base


class Review(Base):
    """A review left by one user about another after a completed service."""

    __tablename__ = "reviews"

    id = Column(String, primary_key=True)
    reviewer_id = Column(String, nullable=False)
    reviewee_id = Column(String, nullable=False)
    listing_id = Column(String, nullable=True)
    transaction_id = Column(String, nullable=True)

    rating = Column(Integer, nullable=False)  # 1-5 stars
    title = Column(String(200), nullable=True)
    body = Column(Text, nullable=True)

    # Structured ratings
    quality_rating = Column(Integer, nullable=True)  # 1-5
    punctuality_rating = Column(Integer, nullable=True)  # 1-5
    communication_rating = Column(Integer, nullable=True)  # 1-5
    value_rating = Column(Integer, nullable=True)  # 1-5

    is_verified = Column(Boolean, default=False)  # linked to completed transaction
    is_flagged = Column(Boolean, default=False)
    is_visible = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_review_reviewee", "reviewee_id", "created_at"),
        Index("idx_review_reviewer", "reviewer_id"),
        Index("idx_review_listing", "listing_id"),
    )


class ReviewResponse(Base):
    """A response from the reviewee to a review."""

    __tablename__ = "review_responses"

    id = Column(String, primary_key=True)
    review_id = Column(String, unique=True, nullable=False)
    responder_id = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class UserRating(Base):
    """Aggregated rating summary for a user (materialized view updated on review changes)."""

    __tablename__ = "user_ratings"

    user_id = Column(String, primary_key=True)
    total_reviews = Column(Integer, default=0)
    average_rating = Column(Numeric(3, 2), default=0)
    average_quality = Column(Numeric(3, 2), nullable=True)
    average_punctuality = Column(Numeric(3, 2), nullable=True)
    average_communication = Column(Numeric(3, 2), nullable=True)
    average_value = Column(Numeric(3, 2), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
