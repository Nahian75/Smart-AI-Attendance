"""Background tasks. Sync wrappers around async DB work for Celery."""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from ..db.base import AsyncSessionLocal
from ..models import RecognitionEvent, Employee, AttendanceLog
from ..config import settings
from .celery_app import celery_app

SNAPSHOT_DIR = "/app/snapshots"
SNAPSHOT_RETENTION_DAYS = 7


def _run(coro):
    return asyncio.run(coro)


@celery_app.task
def apply_retention():
    async def _do():
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.EVENT_RETENTION_DAYS)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(RecognitionEvent).where(RecognitionEvent.created_at < cutoff))
            await db.commit()
    _run(_do())
    return "retention applied"


@celery_app.task
def mark_absentees():
    """Finalize the previous local day for each employee: create an absent record
    if no attendance log exists, skipping days outside the employee's assigned
    shift's work_days. Runs hourly (see celery_app.py); for each employee we only
    act once their branch has passed local midnight (00:00-03:59 local window),
    so branches in different timezones get finalized at their own local end-of-day
    instead of a single fixed UTC time."""
    async def _do():
        import pytz
        from ..models import Branch, EmployeeShift, Shift

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Employee, Branch)
                .outerjoin(Branch, Branch.id == Employee.branch_id)
                .where(Employee.is_active.is_(True))
            )).all()

            for e, branch in rows:
                tz = pytz.timezone(branch.timezone if branch else "UTC")
                now_local = datetime.now(timezone.utc).astimezone(tz)
                if now_local.hour >= 4:
                    continue  # not yet this employee's local finalize window
                target_date = now_local.date() - timedelta(days=1)

                existing = (await db.execute(
                    select(AttendanceLog).where(
                        AttendanceLog.employee_id == e.id,
                        AttendanceLog.tenant_id == e.tenant_id,
                        AttendanceLog.attendance_date == target_date,
                    )
                )).scalar_one_or_none()
                if existing:
                    continue

                shift = (await db.execute(
                    select(Shift).join(EmployeeShift, EmployeeShift.shift_id == Shift.id)
                    .where(
                        EmployeeShift.employee_id == e.id,
                        EmployeeShift.effective_from <= target_date,
                        (EmployeeShift.effective_to.is_(None)) | (EmployeeShift.effective_to > target_date),
                        Shift.is_active.is_(True),
                    )
                    .order_by(EmployeeShift.effective_from.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if shift and target_date.isoweekday() not in (shift.work_days or [1, 2, 3, 4, 5]):
                    continue  # not a scheduled work day for this employee

                db.add(AttendanceLog(
                    tenant_id=e.tenant_id, employee_id=e.id,
                    branch_id=e.branch_id, attendance_date=target_date,
                    shift_id=shift.id if shift else None,
                    status="absent",
                ))
            await db.commit()
    _run(_do())
    return "absentees marked"


@celery_app.task
def purge_snapshots():
    """Delete snapshot image files older than SNAPSHOT_RETENTION_DAYS (default 7 days).
    Runs nightly — keeps disk usage bounded without touching the DB records."""
    if not os.path.exists(SNAPSHOT_DIR):
        return "snapshot dir not found"
    cutoff = time.time() - (SNAPSHOT_RETENTION_DAYS * 86400)
    deleted = 0
    errors = 0
    for root, dirs, files in os.walk(SNAPSHOT_DIR):
        for fname in files:
            if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            fpath = os.path.join(root, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    deleted += 1
            except Exception:
                errors += 1
    return f"snapshots purged: {deleted} deleted, {errors} errors"


@celery_app.task
def email_digest():
    """Send a daily attendance digest email per tenant to ALERT_EMAIL_TO."""
    async def _do():
        from datetime import date
        from sqlalchemy import select, func, distinct
        from ..models import Employee, AttendanceLog
        from ..services.notification_service import NotificationService

        today = date.today()
        results = []
        async with AsyncSessionLocal() as db:
            tenant_ids = (await db.execute(
                select(distinct(Employee.tenant_id)).where(Employee.is_active.is_(True))
            )).scalars().all()

            notifier = NotificationService()
            for tid in tenant_ids:
                total = (await db.execute(
                    select(func.count(Employee.id)).where(
                        Employee.is_active.is_(True),
                        Employee.tenant_id == tid,
                    )
                )).scalar() or 0

                logs = (await db.execute(
                    select(AttendanceLog).where(
                        AttendanceLog.attendance_date == today,
                        AttendanceLog.tenant_id == tid,
                    )
                )).scalars().all()

                present = sum(1 for l in logs if l.status in ("present", "late"))
                late    = sum(1 for l in logs if l.is_late)
                absent  = max(total - present, 0)

                await notifier.notify_digest(
                    date_str=today.isoformat(),
                    total=total, present=present, absent=absent, late=late,
                )
                results.append(f"tenant={tid}: {present}/{total} present")

        return "; ".join(results) if results else "no active tenants"

    return _run(_do())
