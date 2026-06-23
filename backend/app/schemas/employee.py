import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class EmployeeIn(BaseModel):
    full_name: str
    employee_code: str | None = None
    email: str | None = None
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    branch_id: uuid.UUID | None = None


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    employee_code: str | None = None
    email: str | None = None
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    branch_id: uuid.UUID | None = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    employee_code: str | None
    email: str | None
    phone: str | None
    department: str | None
    designation: str | None
    is_enrolled: bool
    is_active: bool
    is_blacklisted: bool
    is_vip: bool
    face_enrolled_at: datetime | None
