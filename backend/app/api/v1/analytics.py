"""Analytics endpoints: occupancy, hourly entry/exit, shift compliance, visitor count."""
import uuid
from datetime import date, timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, get_redis, get_current_user, CurrentUser
from ...models import AttendanceLog, Employee, UnknownDetection
from ...services.alert_service import OccupancyService

router = APIRouter()


@router.get("/occupancy", summary="Live occupancy counters per zone + building total")
async def occupancy(
    redis=Depends(get_redis),
    user: CurrentUser = Depends(get_current_user),
):
    svc = OccupancyService(redis)
    zones = await svc.get_all_zones(user.tenant_id)
    building = zones.pop("building", 0)
    return {"building": building, "zones": zones}


@router.get("/hourly", summary="Hourly entry/exit counts for a date (for bar chart)")
async def hourly(
    day: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Returns 24-slot array of {hour, entries, exits}. Powers the Recharts bar chart."""
    stmt = select(AttendanceLog).where(
        AttendanceLog.tenant_id == user.tenant_id,
        AttendanceLog.attendance_date == day,
    )
    logs = (await db.execute(stmt)).scalars().all()

    buckets = [{"hour": h, "entries": 0, "exits": 0} for h in range(24)]
    for l in logs:
        if l.check_in_at:
            buckets[l.check_in_at.hour]["entries"] += 1
        if l.check_out_at:
            buckets[l.check_out_at.hour]["exits"] += 1
    return buckets


@router.get("/shift-compliance", summary="PRD §5.1: % on-time per employee per week")
async def shift_compliance(
    week_start: date = Query(..., description="Monday of the week"),
    branch_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    week_end = week_start + timedelta(days=6)
    stmt = (
        select(AttendanceLog, Employee)
        .join(Employee, Employee.id == AttendanceLog.employee_id)
        .where(
            AttendanceLog.tenant_id == user.tenant_id,
            AttendanceLog.attendance_date >= week_start,
            AttendanceLog.attendance_date <= week_end,
        )
    )
    if branch_id:
        stmt = stmt.where(AttendanceLog.branch_id == branch_id)
    rows = (await db.execute(stmt)).all()

    # Group by employee
    emp_stats: dict[str, dict] = {}
    for log, emp in rows:
        eid = str(emp.id)
        if eid not in emp_stats:
            emp_stats[eid] = {"name": emp.full_name, "code": emp.employee_code,
                               "dept": emp.department, "total": 0, "on_time": 0, "late": 0, "absent": 0}
        emp_stats[eid]["total"] += 1
        if log.status == "absent":
            emp_stats[eid]["absent"] += 1
        elif log.is_late:
            emp_stats[eid]["late"] += 1
        else:
            emp_stats[eid]["on_time"] += 1

    out = []
    for eid, s in emp_stats.items():
        total_working = s["total"] - s["absent"]
        pct = round(s["on_time"] / total_working * 100, 1) if total_working else 0
        out.append({**s, "employee_id": eid, "on_time_pct": pct})
    return sorted(out, key=lambda x: x["on_time_pct"])


@router.get("/visitors", summary="PRD §5.2: unknown / visitor detection count per day")
async def visitors(
    day: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    count = (await db.execute(
        select(func.count(UnknownDetection.id)).where(
            UnknownDetection.tenant_id == user.tenant_id,
            UnknownDetection.detection_date == day,
        )
    )).scalar() or 0
    return {"date": day.isoformat(), "unknown_detections": count}


@router.get("/department-occupancy", summary="Department-based occupancy breakdown")
async def department_occupancy(
    day: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Get occupancy count by employee department."""
    stmt = (
        select(AttendanceLog, Employee)
        .join(Employee, Employee.id == AttendanceLog.employee_id)
        .where(
            AttendanceLog.tenant_id == user.tenant_id,
            AttendanceLog.attendance_date == day,
            AttendanceLog.check_in_at.isnot(None),
        )
    )
    rows = (await db.execute(stmt)).all()

    dept_counts: dict[str, int] = {}
    for log, emp in rows:
        dept = emp.department or "unassigned"
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

    return dept_counts


@router.get("/presence-duration", summary="PRD §5.2: check-in to check-out delta per employee")
async def presence_duration(
    day: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = (
        select(AttendanceLog, Employee)
        .join(Employee, Employee.id == AttendanceLog.employee_id)
        .where(AttendanceLog.tenant_id == user.tenant_id,
               AttendanceLog.attendance_date == day,
               AttendanceLog.working_hours.isnot(None))
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"employee_id": str(emp.id), "name": emp.full_name,
         "dept": emp.department, "working_hours": float(log.working_hours),
         "overtime_seconds": log.overtime_seconds}
        for log, emp in rows
    ]
