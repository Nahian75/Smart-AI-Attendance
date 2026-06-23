"""Celery app + scheduled beat tasks."""
from celery import Celery
from celery.schedules import crontab
from ..config import settings

celery_app = Celery(
    "attendance",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "mark-absentees-nightly": {
            "task": "app.workers.tasks.mark_absentees",
            "schedule": crontab(hour=23, minute=30),
        },
        "apply-retention-daily": {
            "task": "app.workers.tasks.apply_retention",
            "schedule": crontab(hour=2, minute=0),
        },
        "email-daily-digest": {
            "task": "app.workers.tasks.email_digest",
            "schedule": crontab(hour=18, minute=0),
        },
    },
)
