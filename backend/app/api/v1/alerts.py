import uuid, json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from ...dependencies import get_db, get_current_user, get_redis, role_required, CurrentUser
from ...models import Alert, Employee, Camera, AlertConfig
from ...schemas.alert_config import AlertSettingsUpdate, BlacklistEmployeeUpdate, RestrictedCameraUpdate, AdminPasswordCheck, AdminConfigPasswordIn
from ...core.security import verify_password
from ...core.exceptions import Unauthorized
from ...config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()


@router.get("", summary="List alerts for the tenant (newest first)")
async def list_alerts(
    alert_type: Optional[str] = None,
    unacked_only: bool = False,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = select(Alert).where(Alert.tenant_id == user.tenant_id)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if unacked_only:
        stmt = stmt.where(Alert.is_acknowledged.is_(False))
    stmt = stmt.order_by(Alert.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"id": str(a.id), "type": a.alert_type, "severity": a.severity,
         "message": a.message, "employee_id": str(a.employee_id) if a.employee_id else None,
         "camera_id": str(a.camera_id) if a.camera_id else None,
         "snapshot_url": a.snapshot_url, "is_acknowledged": a.is_acknowledged,
         "created_at": a.created_at.isoformat() if a.created_at else None}
        for a in rows
    ]


@router.post("/{alert_id}/acknowledge", summary="Acknowledge an alert")
async def acknowledge(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("security")),
):
    alert = await db.get(Alert, alert_id)
    if alert and alert.tenant_id == user.tenant_id:
        alert.is_acknowledged = True
        alert.acknowledged_by = user.id
        alert.acknowledged_at = datetime.now(timezone.utc)
        await db.commit()
    return {"acknowledged": True}


@router.get("/recent", summary="Get last 50 alerts from Redis cache (fastest)")
async def recent_alerts(
    redis=Depends(get_redis),
    user: CurrentUser = Depends(get_current_user),
):
    raw = await redis.lrange(f"alerts:recent:{user.tenant_id}", 0, 49)
    return [json.loads(r) for r in raw]


@router.get("/config", summary="Get current alert configuration settings")
async def get_alert_config(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    """Retrieve current alert configuration settings."""
    config = await db.get(AlertConfig, user.tenant_id)
    if not config:
        return {"message": "No configuration found, using defaults"}
    settings = get_settings()
    return {
        "confidence_threshold": config.confidence_threshold / 100,
        "liveness_threshold": config.liveness_threshold / 100,
        "cooldown_minutes": config.cooldown_minutes,
        "after_hours_buffer_min": config.after_hours_buffer_min,
        "loitering_threshold_min": config.loitering_threshold_min,
        "slack_webhook_url": config.slack_webhook_url,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_user": config.smtp_user,
        "alert_email_to": config.alert_email_to,
        "event_retention_days": config.event_retention_days,
        "admin_password_set": bool(config.admin_password_hash),
        "last_password_change": config.last_password_change.isoformat() if config.last_password_change else None,
    }


@router.post("/config/update", summary="Update alert configuration settings")
async def update_alert_config(
    settings_update: AlertSettingsUpdate,
    password_check: AdminPasswordCheck,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Update alert configuration settings. Requires admin password verification."""
    config = await db.get(AlertConfig, user.tenant_id)
    if not config:
        config = AlertConfig(tenant_id=user.tenant_id)
        db.add(config)

    # Verify admin password
    if config.admin_password_hash:
        if not verify_password(password_check.password, config.admin_password_hash):
            raise Unauthorized("Invalid admin password")
    else:
        # First time setup - set password
        config.admin_password_hash = pwd_context.hash(password_check.password)
        config.last_password_change = datetime.now(timezone.utc)

    # Update settings
    if settings_update.confidence_threshold is not None:
        config.confidence_threshold = int(settings_update.confidence_threshold * 100)
    if settings_update.liveness_threshold is not None:
        config.liveness_threshold = int(settings_update.liveness_threshold * 100)
    if settings_update.cooldown_minutes is not None:
        config.cooldown_minutes = settings_update.cooldown_minutes
    if settings_update.after_hours_buffer_min is not None:
        config.after_hours_buffer_min = settings_update.after_hours_buffer_min
    if settings_update.loitering_threshold_min is not None:
        config.loitering_threshold_min = settings_update.loitering_threshold_min
    if settings_update.slack_webhook_url is not None:
        config.slack_webhook_url = settings_update.slack_webhook_url
    if settings_update.smtp_host is not None:
        config.smtp_host = settings_update.smtp_host
    if settings_update.smtp_port is not None:
        config.smtp_port = settings_update.smtp_port
    if settings_update.smtp_user is not None:
        config.smtp_user = settings_update.smtp_user
    if settings_update.smtp_password is not None:
        config.smtp_password = settings_update.smtp_password
    if settings_update.alert_email_to is not None:
        config.alert_email_to = settings_update.alert_email_to
    if settings_update.event_retention_days is not None:
        config.event_retention_days = settings_update.event_retention_days

    await db.commit()
    await db.refresh(config)
    return {"message": "Alert configuration updated successfully"}


@router.post("/config/password", summary="Set or change admin password")
async def set_admin_password(
    payload: AdminConfigPasswordIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    """Set or change the admin password for configuration access. Requires admin role and old password."""
    from ...core.security import verify_password as _vp
    config = await db.get(AlertConfig, user.tenant_id)
    if not config:
        config = AlertConfig(tenant_id=user.tenant_id)
        db.add(config)

    # Verify old password when one is already set
    if config.admin_password_hash and not _vp(payload.old_password, config.admin_password_hash):
        raise Unauthorized("Current password is incorrect")

    config.admin_password_hash = pwd_context.hash(payload.new_password)
    config.last_password_change = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)

    return {"message": "Admin password updated successfully"}


@router.get("/employees/{employee_id}/blacklist", summary="Get employee blacklist status")
async def get_blacklist_status(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Retrieve employee blacklist status."""
    employee = await db.get(Employee, employee_id)
    if not employee or employee.tenant_id != user.tenant_id:
        raise Unauthorized("Employee not found")
    return {
        "employee_id": str(employee_id),
        "full_name": employee.full_name,
        "is_blacklisted": employee.is_blacklisted,
        "notes": employee.extra.get("blacklist_notes", ""),
    }


@router.post("/employees/{employee_id}/blacklist", summary="Update employee blacklist status")
async def update_blacklist_status(
    employee_id: uuid.UUID,
    blacklist_update: BlacklistEmployeeUpdate,
    password_check: AdminPasswordCheck,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Update employee blacklist status. Requires admin password verification."""
    employee = await db.get(Employee, employee_id)
    if not employee or employee.tenant_id != user.tenant_id:
        raise Unauthorized("Employee not found")

    # Verify admin password
    config = await db.get(AlertConfig, user.tenant_id)
    if config and config.admin_password_hash and not verify_password(password_check.password, config.admin_password_hash):
        raise Unauthorized("Invalid admin password")

    employee.is_blacklisted = blacklist_update.is_blacklisted
    if blacklist_update.notes:
        employee.extra["blacklist_notes"] = blacklist_update.notes
    else:
        employee.extra.pop("blacklist_notes", None)

    await db.commit()
    return {"message": f"Employee blacklist status updated to {blacklist_update.is_blacklisted}"}


@router.get("/cameras/{camera_id}/restricted", summary="Get camera restricted status")
async def get_restricted_status(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Retrieve camera restricted area status."""
    camera = await db.get(Camera, camera_id)
    if not camera or camera.tenant_id != user.tenant_id:
        raise Unauthorized("Camera not found")
    return {
        "camera_id": str(camera_id),
        "name": camera.name,
        "is_restricted": camera.is_restricted,
    }


@router.post("/cameras/{camera_id}/restricted", summary="Update camera restricted status")
async def update_restricted_status(
    camera_id: uuid.UUID,
    restricted_update: RestrictedCameraUpdate,
    password_check: AdminPasswordCheck,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Update camera restricted area status. Requires admin password verification."""
    camera = await db.get(Camera, camera_id)
    if not camera or camera.tenant_id != user.tenant_id:
        raise Unauthorized("Camera not found")

    # Verify admin password
    config = await db.get(AlertConfig, user.tenant_id)
    if config and config.admin_password_hash and not verify_password(password_check.password, config.admin_password_hash):
        raise Unauthorized("Invalid admin password")

    camera.is_restricted = restricted_update.is_restricted
    await db.commit()
    return {"message": f"Camera restricted status updated to {restricted_update.is_restricted}"}
