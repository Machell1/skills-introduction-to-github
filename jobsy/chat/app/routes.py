"""Chat service REST API routes for conversation and message history."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db

from app.models import Conversation, Message

router = APIRouter(tags=["chat"])


def _get_user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user context")
    return user_id


@router.get("/conversations")
async def list_conversations(
    request: Request,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current user."""
    user_id = _get_user_id(request)
    query = (
        select(Conversation)
        .where(or_(Conversation.user_a_id == user_id, Conversation.user_b_id == user_id))
        .order_by(Conversation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    conversations = result.scalars().all()

    return [
        {
            "id": c.id,
            "match_id": c.match_id,
            "other_user_id": c.user_b_id if c.user_a_id == user_id else c.user_a_id,
            "created_at": c.created_at.isoformat(),
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=50, le=100),
    before: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get paginated message history for a conversation."""
    user_id = _get_user_id(request)

    # Verify user is a participant
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            or_(Conversation.user_a_id == user_id, Conversation.user_b_id == user_id),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a conversation participant")

    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    messages = result.scalars().all()

    return [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "content": m.content,
            "message_type": m.message_type,
            "is_read": m.is_read,
            "created_at": m.created_at.isoformat(),
        }
        for m in reversed(messages)  # oldest first
    ]


@router.put("/conversations/{conversation_id}/read")
async def mark_messages_read(
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark all messages in a conversation as read for the current user."""
    user_id = _get_user_id(request)

    # Verify participation
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            or_(Conversation.user_a_id == user_id, Conversation.user_b_id == user_id),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a conversation participant")

    # Mark unread messages from the other user as read
    await db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_id != user_id,
            Message.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.flush()

    return {"status": "ok"}
