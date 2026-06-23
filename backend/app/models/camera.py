import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, JSON, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..db.base import Base
from ._mixins import UUIDMixin


class Camera(UUIDMixin, Base):
    __tablename__ = "cameras"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rtsp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    onvif_ip: Mapped[str | None] = mapped_column(String(100), nullable=True)
    camera_type: Mapped[str] = mapped_column(String(50), default="ip")
    direction: Mapped[str] = mapped_column(String(50), default="entrance")   # entrance | exit | interior
    # PRD §5.3: flag camera as restricted → any detection fires alert
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    # PRD §5.4: zone/role for occupancy grouping and smart-office logic
    camera_zone: Mapped[str | None] = mapped_column(String(100), nullable=True)   # e.g. "floor_1", "zone_a"
    camera_role: Mapped[str] = mapped_column(String(50), default="general")       # general | meeting_room | reception | entrance_gate
    fps_target: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="offline")
    edge_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
