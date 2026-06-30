import uuid
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict


class RecognitionEventIn(BaseModel):
    camera_id: uuid.UUID
    employee_id: uuid.UUID | None = None
    direction: str | None = None
    track_id: int | None = None
    confidence: float = 0.0
    is_live: bool = True
    spoof_score: float | None = None
    snapshot_url: str | None = None
    embedding_dist: float | None = None
    timestamp: datetime | None = None
    # Extended event types from edge node
    type: str | None = None          # suspicious_object | masked_face | recognition | etc.
    object_label: str | None = None  # backpack | handbag | suitcase (for suspicious_object)


class AttendanceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    attendance_date: date
    check_in_at: datetime | None
    check_out_at: datetime | None
    status: str
    is_late: bool
    late_by_min: int
    is_early_leave: bool
    early_by_min: int = 0
    working_hours: float | None
    overtime_seconds: int = 0


class AttendanceLogPatch(BaseModel):
    attendance_date: date | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: str | None = None
    notes: str | None = None


class ManualAttendanceIn(BaseModel):
    employee_id: uuid.UUID
    attendance_date: date
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: str = "present"
    notes: str | None = None


class AttendanceSummary(BaseModel):
    date: date
    total_employees: int
    present: int
    absent: int
    late: int
    early_leave: int
    attendance_rate: float
