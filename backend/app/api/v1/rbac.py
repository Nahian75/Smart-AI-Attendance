"""RBAC audit and security endpoints."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ipaddress import IPv4Address

from ...dependencies import get_db, get_current_user, role_required, CurrentUser
from ...models import AuditLog, User

router = APIRouter()


@router.get("/audit", summary="Get RBAC audit logs")
async def get_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by user ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    """Retrieve RBAC audit logs for the tenant."""
    stmt = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)

    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)

    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "user_email": None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "user_agent": log.user_agent,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/audit/users", summary="Get user audit log")
async def get_user_audit(
    user_id: uuid.UUID = Query(..., description="User ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    """Get audit logs for a specific user."""
    stmt = select(AuditLog).where(
        AuditLog.tenant_id == user.tenant_id,
        AuditLog.user_id == user_id,
    ).order_by(AuditLog.created_at.desc()).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": str(log.id),
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/audit/actions", summary="Get available audit actions")
async def get_audit_actions(user: CurrentUser = Depends(role_required("admin"))):
    """Get list of available audit actions for filtering."""
    return {
        "actions": [
            "login", "logout", "create", "update", "delete",
            "enroll_face", "blacklist", "unblacklist",
            "restrict_camera", "unrestrict_camera",
            "acknowledge_alert", "change_config",
            "reset_attendance", "export_data"
        ]
    }


@router.get("/audit/stats", summary="Get audit statistics")
async def get_audit_stats(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    """Get audit statistics for the tenant."""
    from sqlalchemy import func

    total_logs = (await db.execute(
        select(func.count()).where(AuditLog.tenant_id == user.tenant_id)
    )).scalar()

    recent_logs = (await db.execute(
        select(func.count()).where(
            AuditLog.tenant_id == user.tenant_id,
            AuditLog.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        )
    )).scalar()

    recent_24h = (await db.execute(
        select(func.count()).where(
            AuditLog.tenant_id == user.tenant_id,
            AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
        )
    )).scalar()

    return {
        "total_logs": total_logs,
        "today_logs": recent_logs,
        "last_24h_logs": recent_24h,
        "top_actions": (await db.execute(
            select(AuditLog.action, func.count().label("count"))
            .where(AuditLog.tenant_id == user.tenant_id)
            .group_by(AuditLog.action)
            .order_by(func.count().desc())
            .limit(10)
        )).all(),
    }