"""SQLAlchemy ORM models for the notification service."""

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.database import Base


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    token = Column(String(500), nullable=False)
    platform = Column(String(10), nullable=False)  # 'ios', 'android', 'web'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_device_user_token", "user_id", "token", unique=True),
    )


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String(200), nullable=True)
    body = Column(String, nullable=True)
    data = Column(JSONB, default={})
    notification_type = Column(String(30), nullable=False)  # match, message, listing_expired
    is_read = Column(Boolean, default=False)
    delivered = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=False)
