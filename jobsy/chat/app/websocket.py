"""WebSocket handler for real-time chat between matched users.

Uses Redis pub/sub for cross-instance message delivery, ensuring
messages reach users regardless of which server instance they're
connected to.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import or_, select

from shared.auth import decode_token
from shared.config import REDIS_URL
from shared.database import async_session_factory
from shared.events import publish_event

from app.models import Conversation, Message

logger = logging.getLogger(__name__)

# Active WebSocket connections: {conversation_id: {user_id: websocket}}
_connections: dict[str, dict[str, WebSocket]] = {}


async def _get_redis():
    return aioredis.from_url(REDIS_URL, decode_responses=True)


async def _authenticate(websocket: WebSocket) -> str | None:
    """Authenticate WebSocket via token query param."""
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return payload["sub"]
    except JWTError:
        return None


async def _verify_participant(user_id: str, conversation_id: str) -> bool:
    """Check that the user is a participant in this conversation."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                or_(
                    Conversation.user_a_id == user_id,
                    Conversation.user_b_id == user_id,
                ),
            )
        )
        return result.scalar_one_or_none() is not None


async def _save_message(conversation_id: str, sender_id: str, content: str, message_type: str = "text") -> dict:
    """Persist a message to the database."""
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        message = Message(
            id=msg_id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            created_at=now,
        )
        db.add(message)
        await db.commit()

    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "content": content,
        "message_type": message_type,
        "created_at": now.isoformat(),
    }


async def _start_redis_listener(conversation_id: str, websocket: WebSocket, user_id: str):
    """Subscribe to Redis channel for cross-instance message delivery."""
    try:
        redis_client = await _get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"chat:{conversation_id}")

        async for raw_message in pubsub.listen():
            if raw_message["type"] != "message":
                continue
            data = json.loads(raw_message["data"])
            # Don't echo back to the sender on the same instance
            if data.get("sender_id") != user_id:
                await websocket.send_json(data)
    except Exception:
        logger.exception("Redis listener error for conversation %s", conversation_id)
    finally:
        await pubsub.unsubscribe(f"chat:{conversation_id}")
        await redis_client.close()


async def chat_websocket(websocket: WebSocket, conversation_id: str):
    """Handle a WebSocket connection for a chat conversation.

    Protocol:
    1. Client connects with ?token=<JWT>
    2. Server authenticates and verifies conversation membership
    3. Client sends JSON: {"content": "...", "type": "text"}
    4. Server broadcasts to all participants via Redis pub/sub
    5. Server persists message to database
    6. Server emits message.new event for notifications
    """
    user_id = await _authenticate(websocket)
    if not user_id:
        await websocket.close(code=4001, reason="Authentication required")
        return

    if not await _verify_participant(user_id, conversation_id):
        await websocket.close(code=4003, reason="Not a conversation participant")
        return

    await websocket.accept()

    # Track connection
    if conversation_id not in _connections:
        _connections[conversation_id] = {}
    _connections[conversation_id][user_id] = websocket

    # Start Redis listener for cross-instance messages
    import asyncio
    listener_task = asyncio.create_task(
        _start_redis_listener(conversation_id, websocket, user_id)
    )

    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "").strip()
            message_type = data.get("type", "text")

            if not content:
                continue

            # Save to database
            msg = await _save_message(conversation_id, user_id, content, message_type)

            # Broadcast via Redis pub/sub (reaches other instances)
            redis_client = await _get_redis()
            await redis_client.publish(f"chat:{conversation_id}", json.dumps(msg))
            await redis_client.close()

            # Send to local connections (same instance)
            for uid, ws in _connections.get(conversation_id, {}).items():
                if uid != user_id:
                    try:
                        await ws.send_json(msg)
                    except Exception:
                        pass

            # Emit event for notifications service
            await publish_event("message.new", {
                "message_id": msg["id"],
                "conversation_id": conversation_id,
                "sender_id": user_id,
            })

    except WebSocketDisconnect:
        logger.info("User %s disconnected from conversation %s", user_id, conversation_id)
    except Exception:
        logger.exception("WebSocket error for user %s in conversation %s", user_id, conversation_id)
    finally:
        listener_task.cancel()
        if conversation_id in _connections:
            _connections[conversation_id].pop(user_id, None)
            if not _connections[conversation_id]:
                del _connections[conversation_id]
