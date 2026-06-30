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
    """Create absent records for active employees with no log today."""
    async def _do():
        from datetime import date
        today = date.today()
        async with AsyncSessionLocal() as db:
            emps = (await db.execute(
                select(Employee).where(Employee.is_active.is_(True))
            )).scalars().all()
            for e in emps:
                existing = (await db.execute(
                    select(AttendanceLog).where(
                        AttendanceLog.employee_id == e.id,
                        AttendanceLog.tenant_id == e.tenant_id,
                        AttendanceLog.attendance_date == today,
                    )
                )).scalar_one_or_none()
                if not existing:
                    db.add(AttendanceLog(
                        tenant_id=e.tenant_id, employee_id=e.id,
                        branch_id=e.branch_id, attendance_date=today,
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
