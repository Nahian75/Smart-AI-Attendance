import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Integer, DateTime, Date, Numeric, Text, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..db.base import Base
from ._mixins import UUIDMixin, TimestampMixin


class RecognitionEvent(UUIDMixin, TimestampMixin, Base):
    """Raw event from edge AI node — before attendance logic is applied."""
    __tablename__ = "recognition_events"
    __table_args__ = (
        Index("ix_recog_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    is_live: Mapped[bool] = mapped_column(Boolean, default=True)
    spoof_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_dist: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    raw_event: Mapped[dict] = mapped_column(JSON, default=dict)


class AttendanceLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        Index("ix_attlog_tenant_date", "tenant_id", "attendance_date"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=True)

    attendance_date: Mapped[date] = mapped_column(Date)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_in_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    check_out_source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="present")  # present|absent|late|half_day|holiday
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    late_by_min: Mapped[int] = mapped_column(Integer, default=0)
    is_early_leave: Mapped[bool] = mapped_column(Boolean, default=False)
    early_by_min: Mapped[int] = mapped_column(Integer, default=0)
    working_hours: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # PRD §5.1: overtime_seconds = seconds past shift end_time (aggregated weekly)
    overtime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    override_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


# PRD §5.3: all security alert types
class Alert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    # Types: intruder | blacklist | after_hours | restricted_area | vip | loitering | spoof_attempt | unknown_person
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20), default="high")   # high | medium | low
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


# PRD §5.2: unknown/visitor detections that don't match any enrolled face
class UnknownDetection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "unknown_detections"
    __table_args__ = (
        Index("ix_unknown_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_best: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    is_visitor: Mapped[bool] = mapped_column(Boolean, default=False)    # tagged after repeated appearances
    detection_date: Mapped[date] = mapped_column(Date)
    detection_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
