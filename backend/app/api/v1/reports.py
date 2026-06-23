import uuid
from datetime import date, timedelta, datetime, timezone
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import io

from ...dependencies import get_db, get_current_user, CurrentUser
from ...services.report_service import ReportService

router = APIRouter()


@router.get("/monthly.csv")
async def monthly_csv(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    service = ReportService(db)
    csv_text = await service.monthly_csv(user.tenant_id, year, month)
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{year}_{month:02d}.csv"},
    )


@router.get("/weekly")
async def weekly(db: AsyncSession = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    service = ReportService(db)
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    return await service.weekly_rates(user.tenant_id, days)


@router.get("/shift-compliance")
async def shift_compliance(db: AsyncSession = Depends(get_db),
                           user: CurrentUser = Depends(get_current_user)):
    """Get shift compliance for current week."""
    service = ReportService(db)
    return await service.shift_compliance(user.tenant_id)


@router.get("/per-camera")
async def per_camera_analytics(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    camera_id: uuid.UUID | None = Query(None, description="Optional camera ID filter"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Get analytics filtered by camera."""
    service = ReportService(db)
    return await service.per_camera_analytics(user.tenant_id, start_date, end_date, camera_id)


@router.delete("/gdpr/delete", summary="GDPR data deletion request")
async def gdpr_delete(
    reason: str = Query(..., min_length=10, description="Reason for data deletion (GDPR compliance)"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Initiate GDPR data deletion for the tenant. This will delete all employee data, attendance logs, and face embeddings."""
    from ...models import Employee, AttendanceLog, FaceEmbedding, RecognitionEvent, UnknownDetection, Camera

    # Get tenant info for audit log
    tenant_id = user.tenant_id

    # Delete all data for this tenant
    deleted_count = {
        "employees": 0,
        "attendance_logs": 0,
        "face_embeddings": 0,
        "recognition_events": 0,
        "unknown_detections": 0,
        "cameras": 0,
    }

    # Delete employees and their related data
    employees = (await db.execute(
        select(Employee).where(Employee.tenant_id == tenant_id)
    )).scalars().all()
    deleted_count["employees"] = len(employees)

    for emp in employees:
        # Delete face embeddings
        embeddings = (await db.execute(
            select(FaceEmbedding).where(FaceEmbedding.employee_id == emp.id)
        )).scalars().all()
        for emb in embeddings:
            await db.delete(emb)
        deleted_count["face_embeddings"] += len(embeddings)

        # Delete recognition events
        events = (await db.execute(
            select(RecognitionEvent).where(RecognitionEvent.employee_id == emp.id)
        )).scalars().all()
        for evt in events:
            await db.delete(evt)
        deleted_count["recognition_events"] += len(events)

        await db.delete(emp)

    # Delete attendance logs
    logs = (await db.execute(
        select(AttendanceLog).where(AttendanceLog.tenant_id == tenant_id)
    )).scalars().all()
    deleted_count["attendance_logs"] = len(logs)
    for log in logs:
        await db.delete(log)

    # Delete unknown detections
    unknowns = (await db.execute(
        select(UnknownDetection).where(UnknownDetection.tenant_id == tenant_id)
    )).scalars().all()
    deleted_count["unknown_detections"] = len(unknowns)
    for unk in unknowns:
        await db.delete(unk)

    # Delete cameras
    cameras = (await db.execute(
        select(Camera).where(Camera.tenant_id == tenant_id)
    )).scalars().all()
    deleted_count["cameras"] = len(cameras)
    for cam in cameras:
        await db.delete(cam)

    await db.commit()

    return {
        "message": "GDPR data deletion completed",
        "tenant_id": str(tenant_id),
        "deleted_count": deleted_count,
        "reason": reason,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
    }
