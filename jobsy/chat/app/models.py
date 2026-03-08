"""SQLAlchemy ORM models for the chat service."""

from sqlalchemy import Boolean, Column, DateTime, Index, String

from shared.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    match_id = Column(String, unique=True, nullable=False)
    user_a_id = Column(String, nullable=False)
    user_b_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_convo_user_a", "user_a_id"),
        Index("idx_convo_user_b", "user_b_id"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, nullable=False)
    sender_id = Column(String, nullable=False)
    content = Column(String, nullable=False)
    message_type = Column(String(20), default="text")  # text, image, location
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_messages_convo", "conversation_id", "created_at"),
    )
