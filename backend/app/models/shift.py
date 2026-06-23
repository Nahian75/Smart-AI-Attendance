import uuid
from datetime import time, date
from sqlalchemy import String, Boolean, Integer, Time, Date, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..db.base import Base
from ._mixins import UUIDMixin


class Shift(UUIDMixin, Base):
    __tablename__ = "shifts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    grace_in_min: Mapped[int] = mapped_column(Integer, default=10)
    early_out_min: Mapped[int] = mapped_column(Integer, default=15)
    work_days: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [1, 2, 3, 4, 5])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class EmployeeShift(Base):
    __tablename__ = "employee_shifts"

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shifts.id"), primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date, primary_key=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
