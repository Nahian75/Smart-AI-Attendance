"""
Detection evidence log — unified view of every face event captured by the system.
Combines RecognitionEvent (known employees + spoof attempts) and UnknownDetection
(unrecognised faces) into one paginated, filterable endpoint.

Purpose: lets operators verify the AI is not hallucinating and catch cheating.
"""
import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, get_current_user, CurrentUser
from ...models.attendance import RecognitionEvent, UnknownDetection
from ...models.employee import Employee
from ...models.camera import Camera

router = APIRouter()

SNAPSHOT_ROOT = "/app/snapshots"


def _snap_to_url(path: str | None) -> str | None:
    """Convert filesystem snapshot path to a web-accessible URL."""
    if not path:
        return None
    return "/snapshots" + path.replace(SNAPSHOT_ROOT, "")


@router.get("")
async def list_detections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = Query(None, description="recognition | unknown_person | spoof_attempt | all"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns every face detection event with timestamp, snapshot URL, confidence,
    employee name, and camera name. Sorted newest first.
    """
    offset = (page - 1) * page_size
    # We only ever need the newest (offset + page_size) rows from each source to
    # build the requested page, since results are merged and sliced by timestamp.
    fetch_cap = offset + page_size
    results = []
    total = 0

    # ── 1. RecognitionEvents (known employees + spoofs) ──────────────────
    if event_type in (None, "all", "recognition", "spoof_attempt"):
        base_where = [RecognitionEvent.tenant_id == user.tenant_id]
        if event_type == "spoof_attempt":
            base_where.append(RecognitionEvent.is_live.is_(False))
        elif event_type == "recognition":
            base_where.append(RecognitionEvent.is_live.is_(True))
            base_where.append(RecognitionEvent.employee_id.isnot(None))
        if date_from:
            base_where.append(func.date(RecognitionEvent.created_at) >= date_from)
        if date_to:
            base_where.append(func.date(RecognitionEvent.created_at) <= date_to)

        total += (await db.execute(
            select(func.count()).select_from(RecognitionEvent).where(*base_where)
        )).scalar() or 0

        stmt = (
            select(
                RecognitionEvent,
                Employee.full_name.label("employee_name"),
                Camera.name.label("camera_name"),
            )
            .outerjoin(Employee, Employee.id == RecognitionEvent.employee_id)
            .outerjoin(Camera, Camera.id == RecognitionEvent.camera_id)
            .where(*base_where)
            .order_by(RecognitionEvent.created_at.desc())
            .limit(fetch_cap)
        )
        rows = (await db.execute(stmt)).all()
        for rec, emp_name, cam_name in rows:
            if not rec.is_live:
                etype = "spoof_attempt"
            elif rec.employee_id is None:
                etype = "unknown_person"
            else:
                etype = "recognition"
            results.append({
                "id": str(rec.id),
                "event_type": etype,
                "timestamp": rec.created_at.isoformat() if rec.created_at else None,
                "employee_id": str(rec.employee_id) if rec.employee_id else None,
                "employee_name": emp_name,
                "camera_id": str(rec.camera_id) if rec.camera_id else None,
                "camera_name": cam_name,
                "confidence": float(rec.confidence) if rec.confidence is not None else None,
                "is_live": rec.is_live,
                "spoof_score": float(rec.spoof_score) if rec.spoof_score is not None else None,
                "snapshot_url": _snap_to_url(rec.snapshot_url),
            })

    # ── 2. UnknownDetections ─────────────────────────────────────────────
    if event_type in (None, "all", "unknown_person"):
        u_where = [UnknownDetection.tenant_id == user.tenant_id]
        if date_from:
            u_where.append(UnknownDetection.detection_date >= date_from)
        if date_to:
            u_where.append(UnknownDetection.detection_date <= date_to)

        total += (await db.execute(
            select(func.count()).select_from(UnknownDetection).where(*u_where)
        )).scalar() or 0

        ustmt = (
            select(
                UnknownDetection,
                Camera.name.label("camera_name"),
            )
            .outerjoin(Camera, Camera.id == UnknownDetection.camera_id)
            .where(*u_where)
            .order_by(UnknownDetection.created_at.desc())
            .limit(fetch_cap)
        )
        urows = (await db.execute(ustmt)).all()
        for ud, cam_name in urows:
            results.append({
                "id": str(ud.id),
                "event_type": "unknown_person",
                "timestamp": (
                    ud.detection_timestamp.isoformat()
                    if ud.detection_timestamp else None
                ),
                "employee_id": None,
                "employee_name": None,
                "camera_id": str(ud.camera_id) if ud.camera_id else None,
                "camera_name": cam_name,
                "confidence": float(ud.confidence_best) if ud.confidence_best else None,
                "is_live": True,
                "spoof_score": None,
                "snapshot_url": _snap_to_url(ud.snapshot_url),
            })

    # Merge the two capped sources, sort newest-first, slice the requested page.
    # Each source returned its newest `fetch_cap` rows, which is enough to fill
    # any page up to `offset + page_size`. `total` comes from real count queries.
    results.sort(key=lambda r: r["timestamp"] or "", reverse=True)
    page_items = results[offset: offset + page_size]

    return {"total": total, "page": page, "page_size": page_size, "items": page_items}


@router.get("/stats")
async def detection_stats(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Quick counts for the stats bar at the top of the detection log."""
    rec_total = (await db.execute(
        select(func.count()).where(RecognitionEvent.tenant_id == user.tenant_id)
    )).scalar() or 0
    spoof_total = (await db.execute(
        select(func.count()).where(
            RecognitionEvent.tenant_id == user.tenant_id,
            RecognitionEvent.is_live.is_(False),
        )
    )).scalar() or 0
    unknown_total = (await db.execute(
        select(func.count()).where(UnknownDetection.tenant_id == user.tenant_id)
    )).scalar() or 0
    return {
        "total_detections": rec_total + unknown_total,
        "recognised": rec_total - spoof_total,
        "unknown": unknown_total,
        "spoof_attempts": spoof_total,
    }
