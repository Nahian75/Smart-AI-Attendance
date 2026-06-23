"""Alert configuration model for storing custom settings."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..db.base import Base
from ._mixins import UUIDMixin, TimestampMixin


class AlertConfig(UUIDMixin, TimestampMixin, Base):
    """Stores alert configuration settings per tenant."""
    __tablename__ = "alert_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True)

    # Recognition thresholds (stored as integer 0-100; divided by 100 in API responses)
    confidence_threshold: Mapped[int] = mapped_column(Integer, default=50)
    liveness_threshold: Mapped[int] = mapped_column(Integer, default=80)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=5)

    # Alert thresholds
    after_hours_buffer_min: Mapped[int] = mapped_column(Integer, default=30)
    loitering_threshold_min: Mapped[int] = mapped_column(Integer, default=10)

    # Notifications
    slack_webhook_url: Mapped[str] = mapped_column(String(2048), default="")
    smtp_host: Mapped[str] = mapped_column(String(255), default="")
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str] = mapped_column(String(255), default="")
    smtp_password: Mapped[str] = mapped_column(String(255), default="")
    alert_email_to: Mapped[str] = mapped_column(String(255), default="")

    # Storage/privacy
    event_retention_days: Mapped[int] = mapped_column(Integer, default=90)

    # Admin settings (password protected)
    admin_password_hash: Mapped[str] = mapped_column(String(255), default="")
    last_password_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)