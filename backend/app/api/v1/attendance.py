from datetime import date
from typing import Optional
import os
import uuid

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException, UploadFile, File, Form
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...dependencies import get_db, get_redis, get_current_user, role_required, verify_edge_token, CurrentUser
from ...services.attendance_service import AttendanceService
from ...schemas.attendance import (
    RecognitionEventIn, AttendanceLogOut, AttendanceSummary, AttendanceLogPatch,
)
from ...models import Tenant
from ...models.attendance import AttendanceLog

router = APIRouter()


async def _resolve_tenant(tenant_id: str, db: AsyncSession) -> uuid.UUID:
    """Accept either a UUID string or a tenant slug."""
    try:
        return uuid.UUID(tenant_id)
    except ValueError:
        pass
    row = (await db.execute(select(Tenant).where(Tenant.slug == tenant_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"Tenant '{tenant_id}' not found")
    return row.id


@router.post("/event", summary="Ingest a recognition event from an edge node")
async def receive_event(
    event: RecognitionEventIn,
    background: BackgroundTasks,
    tenant_id: str = Query(..., description="Tenant UUID or slug"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _: None = Depends(verify_edge_token),
):
    tid = await _resolve_tenant(tenant_id, db)
    service = AttendanceService(db, redis)
    return await service.process_recognition_event(event.model_dump(mode="json"), tid)


@router.post("/upload-snapshot", summary="Upload a detection snapshot from a remote edge node")
async def upload_snapshot(
    file: UploadFile = File(...),
    relative_path: str = Form(...),
    _: None = Depends(verify_edge_token),
):
    """Edge nodes that don't share a filesystem/volume with the backend (e.g. a
    cloud deployment where the edge runs on-prem) can't rely on SNAPSHOT_DIR
    being mounted in both containers. This lets the edge push the actual image
    bytes so they land in the same place a co-located edge would have written
    them, keeping snapshot_url values consistent either way."""
    safe_rel = os.path.normpath(relative_path).replace("\\", "/").lstrip("/")
    if safe_rel.startswith(".."):
        raise HTTPException(400, "Invalid relative_path")
    dest = os.path.join(settings.SNAPSHOT_DIR, safe_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(await file.read())
    return {"snapshot_url": dest}


@router.get("/logs", response_model=list[AttendanceLogOut])
async def get_logs(
    branch_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    service = AttendanceService(db)
    return await service.get_logs(user.tenant_id, branch_id, employee_id,
                                  date_from, date_to, page, page_size)


@router.get("/summary", response_model=AttendanceSummary)
async def get_summary(
    day: date = Query(default_factory=date.today, alias="date"),
    branch_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    service = AttendanceService(db)
    return await service.get_summary(day, user.tenant_id, branch_id)


@router.get("/live")
async def live_feed(
    redis=Depends(get_redis),
    user: CurrentUser = Depends(get_current_user),
):
    import json
    raw = await redis.lrange(f"attendance:live:{user.tenant_id}", 0, 49)
    return [json.loads(r) for r in raw]


@router.patch("/logs/{log_id}", response_model=AttendanceLogOut)
async def update_log(
    log_id: uuid.UUID,
    payload: AttendanceLogPatch,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    log = await db.get(AttendanceLog, log_id)
    if not log or log.tenant_id != user.tenant_id:
        raise HTTPException(404, "Log not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(log, k, v)
    if log.check_in_at and log.check_out_at:
        delta = log.check_out_at - log.check_in_at
        log.working_hours = round(delta.total_seconds() / 3600, 2)
    log.is_manual = True
    log.override_by = user.id
    await db.commit()
    await db.refresh(log)
    return log


@router.delete("/logs/{log_id}", status_code=204)
async def delete_log(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    log = await db.get(AttendanceLog, log_id)
    if not log or log.tenant_id != user.tenant_id:
        raise HTTPException(404, "Log not found")
    await db.delete(log)
    await db.commit()


@router.delete("/logs", status_code=204)
async def reset_logs(
    reset_date: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    await db.execute(
        sql_delete(AttendanceLog).where(
            AttendanceLog.tenant_id == user.tenant_id,
            AttendanceLog.attendance_date == reset_date,
        )
    )
    await db.commit()
