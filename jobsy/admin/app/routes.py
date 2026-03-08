"""Admin service API routes -- dashboard stats, user management, moderation, audit log."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db

from app.deps import require_admin
from app.models import AuditLog, ModerationQueue

router = APIRouter(tags=["admin"])


async def _log_action(
    db: AsyncSession,
    admin_id: str,
    action: str,
    target_type: str,
    target_id: str,
    reason: str | None = None,
    details: dict | None = None,
) -> None:
    """Record an admin action in the audit log."""
    entry = AuditLog(
        id=str(uuid.uuid4()),
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        details=details or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)


# --- Dashboard ---


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    admin_id: str = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get platform overview statistics.

    Queries aggregate counts from the shared database.
    In production, these would be cached or pre-computed.
    """
    # These queries hit the shared database tables from other services
    stats = {}

    # Moderation queue stats
    pending_result = await db.execute(
        select(func.count()).select_from(ModerationQueue).where(ModerationQueue.status == "pending")
    )
    stats["pending_moderation"] = pending_result.scalar() or 0

    resolved_result = await db.execute(
        select(func.count()).select_from(ModerationQueue).where(ModerationQueue.status == "resolved")
    )
    stats["resolved_moderation"] = resolved_result.scalar() or 0

    # Recent admin actions
    actions_result = await db.execute(
        select(func.count()).select_from(AuditLog)
    )
    stats["total_admin_actions"] = actions_result.scalar() or 0

    return stats


# --- Moderation ---


@router.get("/moderation")
async def list_moderation_items(
    admin_id: str = Depends(require_admin),
    status_filter: str = Query(default="pending", alias="status"),
    item_type: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List items in the moderation queue."""
    query = (
        select(ModerationQueue)
        .where(ModerationQueue.status == status_filter)
        .order_by(ModerationQueue.created_at.asc())
        .offset(offset)
        .limit(limit)
    )

    if item_type:
        query = query.where(ModerationQueue.item_type == item_type)

    result = await db.execute(query)
    items = result.scalars().all()

    return [
        {
            "id": item.id,
            "item_type": item.item_type,
            "item_id": item.item_id,
            "reported_by": item.reported_by,
            "reason": item.reason,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


class ModerateAction(BaseModel):
    action: str = Field(..., pattern=r"^(approve|remove|dismiss)$")
    reason: str | None = None


@router.post("/moderation/{item_id}/resolve")
async def resolve_moderation_item(
    item_id: str,
    data: ModerateAction,
    admin_id: str = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a moderation queue item."""
    result = await db.execute(select(ModerationQueue).where(ModerationQueue.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Moderation item not found")

    now = datetime.now(timezone.utc)

    if data.action == "dismiss":
        item.status = "dismissed"
    else:
        item.status = "resolved"

    item.reviewed_by = admin_id
    item.resolution = f"{data.action}: {data.reason or 'No reason provided'}"
    item.resolved_at = now
    await db.flush()

    await _log_action(
        db, admin_id,
        action=f"moderation.{data.action}",
        target_type=item.item_type,
        target_id=item.item_id,
        reason=data.reason,
        details={"moderation_item_id": item_id},
    )
    await db.flush()

    return {"status": "resolved", "action": data.action, "item_id": item_id}


# --- User management ---


class UserAction(BaseModel):
    action: str = Field(..., pattern=r"^(suspend|unsuspend|warn|delete)$")
    reason: str = Field(..., min_length=1)


@router.post("/users/{user_id}/action")
async def admin_user_action(
    user_id: str,
    data: UserAction,
    admin_id: str = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Take an administrative action on a user account.

    Actions: suspend, unsuspend, warn, delete.
    All actions are logged in the audit trail.
    """
    await _log_action(
        db, admin_id,
        action=f"user.{data.action}",
        target_type="user",
        target_id=user_id,
        reason=data.reason,
    )
    await db.flush()

    return {
        "status": "ok",
        "action": data.action,
        "user_id": user_id,
        "admin_id": admin_id,
    }


# --- Audit log ---


@router.get("/audit-log")
async def get_audit_log(
    admin_id: str = Depends(require_admin),
    action: str | None = None,
    target_type: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """View the admin audit log."""
    query = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if action:
        query = query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)

    result = await db.execute(query)
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "admin_id": e.admin_id,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "reason": e.reason,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


# --- Content management ---


class ReportCreate(BaseModel):
    item_type: str = Field(..., pattern=r"^(review|listing|profile|message)$")
    item_id: str
    reason: str = Field(..., max_length=200)


@router.post("/report", status_code=status.HTTP_201_CREATED)
async def submit_report(
    data: ReportCreate,
    admin_id: str = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add an item to the moderation queue (can also be called internally)."""
    item = ModerationQueue(
        id=str(uuid.uuid4()),
        item_type=data.item_type,
        item_id=data.item_id,
        reported_by=admin_id,
        reason=data.reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.flush()

    return {"id": item.id, "status": "pending"}
