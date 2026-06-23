import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, JSON, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from ..db.base import Base
from ._mixins import UUIDMixin, TimestampMixin


class Employee(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "employees"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    employee_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_enrolled: Mapped[bool] = mapped_column(Boolean, default=False)
    face_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_version: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # PRD §5.3: blacklist fires an alert on match; VIP routes to separate Slack channel
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    branch = relationship("Branch", back_populates="employees")
    embeddings = relationship("FaceEmbedding", back_populates="employee", cascade="all, delete-orphan")


class FaceEmbedding(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "face_embeddings"

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    quality_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    photo_angle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    employee = relationship("Employee", back_populates="embeddings")
