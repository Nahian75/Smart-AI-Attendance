"""Background tasks. Sync wrappers around async DB work for Celery."""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from ..db.base import AsyncSessionLocal
from ..models import RecognitionEvent, Employee, AttendanceLog
from ..config import settings
from .celery_app import celery_app


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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
        async with AsyncSessionLocal() as db:
            emps = (await db.execute(select(Employee).where(Employee.is_active.is_(True)))).scalars().all()
            for e in emps:
                existing = (await db.execute(
                    select(AttendanceLog).where(
                        AttendanceLog.employee_id == e.id,
                        AttendanceLog.attendance_date == date.today(),
                    )
                )).scalar_one_or_none()
                if not existing:
                    db.add(AttendanceLog(tenant_id=e.tenant_id, employee_id=e.id,
                                         branch_id=e.branch_id, attendance_date=date.today(),
                                         status="absent"))
            await db.commit()
    _run(_do())
    return "absentees marked"


@celery_app.task
def email_digest():
    return "digest queued"
