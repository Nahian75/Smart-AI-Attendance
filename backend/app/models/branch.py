import uuid
from sqlalchemy import String, Integer, Boolean, Numeric, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db.base import Base
from ._mixins import UUIDMixin, TimestampMixin


class Branch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "branches"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    geo_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    geo_lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    geo_radius_m: Mapped[int] = mapped_column(Integer, default=200)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    employees = relationship("Employee", back_populates="branch")
