"""SQLAlchemy ORM models for the admin service."""

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.database import Base


class AuditLog(Base):
    """Tracks admin actions for accountability and compliance."""

    __tablename__ = "audit_log"

    id = Column(String, primary_key=True)
    admin_id = Column(String, nullable=False, index=True)
    action = Column(String(100), nullable=False)  # user.suspend, review.remove, listing.delete, etc.
    target_type = Column(String(50), nullable=False)  # user, listing, review, campaign
    target_id = Column(String, nullable=False)
    details = Column(JSONB, default={})
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_audit_action", "action", "created_at"),
        Index("idx_audit_target", "target_type", "target_id"),
    )


class ModerationQueue(Base):
    """Items flagged for admin review."""

    __tablename__ = "moderation_queue"

    id = Column(String, primary_key=True)
    item_type = Column(String(50), nullable=False)  # review, listing, profile, message
    item_id = Column(String, nullable=False)
    reported_by = Column(String, nullable=True)
    reason = Column(String(200), nullable=True)
    status = Column(String(20), default="pending")  # pending, reviewed, resolved, dismissed
    reviewed_by = Column(String, nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_moderation_status", "status", "created_at"),
    )
