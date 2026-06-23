"""Shift management — create/update shifts and assign them to employees."""
import uuid
from datetime import date, time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, get_current_user, role_required, CurrentUser
from ...models import Shift, EmployeeShift, Employee

router = APIRouter()

DAYS = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


class ShiftIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    start_time: str = Field(..., description="HH:MM (24-hour)")
    end_time: str = Field(..., description="HH:MM (24-hour)")
    grace_in_min: int = Field(default=10, ge=0, le=120, description="Minutes after start before marked late")
    early_out_min: int = Field(default=15, ge=0, le=120, description="Minutes before end before marked early leave")
    work_days: list[int] = Field(default=[1, 2, 3, 4, 5], description="1=Mon … 7=Sun")

    def parsed_start(self) -> time:
        h, m = self.start_time.split(":")
        return time(int(h), int(m))

    def parsed_end(self) -> time:
        h, m = self.end_time.split(":")
        return time(int(h), int(m))


class AssignIn(BaseModel):
    employee_id: uuid.UUID
    shift_id: uuid.UUID
    effective_from: date
    effective_to: Optional[date] = None


def _fmt_shift(s: Shift) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "start_time": s.start_time.strftime("%H:%M"),
        "end_time": s.end_time.strftime("%H:%M"),
        "grace_in_min": s.grace_in_min,
        "early_out_min": s.early_out_min,
        "work_days": s.work_days,
        "work_days_label": [DAYS.get(d, str(d)) for d in sorted(s.work_days)],
        "is_active": s.is_active,
    }


# ── Shifts CRUD ───────────────────────────────────────────────────────────────

@router.get("", summary="List all shifts for the tenant")
async def list_shifts(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    rows = (await db.execute(
        select(Shift).where(Shift.tenant_id == user.tenant_id, Shift.is_active.is_(True))
        .order_by(Shift.name)
    )).scalars().all()
    return [_fmt_shift(s) for s in rows]


@router.post("", summary="Create a new shift")
async def create_shift(
    payload: ShiftIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    s = Shift(
        tenant_id=user.tenant_id,
        name=payload.name,
        start_time=payload.parsed_start(),
        end_time=payload.parsed_end(),
        grace_in_min=payload.grace_in_min,
        early_out_min=payload.early_out_min,
        work_days=payload.work_days,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _fmt_shift(s)


@router.patch("/{shift_id}", summary="Update a shift")
async def update_shift(
    shift_id: uuid.UUID,
    payload: ShiftIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    s = await db.get(Shift, shift_id)
    if not s or s.tenant_id != user.tenant_id:
        raise HTTPException(404, "Shift not found")
    s.name = payload.name
    s.start_time = payload.parsed_start()
    s.end_time = payload.parsed_end()
    s.grace_in_min = payload.grace_in_min
    s.early_out_min = payload.early_out_min
    s.work_days = payload.work_days
    await db.commit()
    return _fmt_shift(s)


@router.delete("/{shift_id}", summary="Deactivate a shift")
async def delete_shift(
    shift_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    s = await db.get(Shift, shift_id)
    if not s or s.tenant_id != user.tenant_id:
        raise HTTPException(404, "Shift not found")
    s.is_active = False
    await db.commit()
    return {"id": str(shift_id), "deleted": True}


# ── Employee shift assignments ────────────────────────────────────────────────

@router.get("/assignments", summary="List all current employee–shift assignments")
async def list_assignments(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = (
        select(EmployeeShift, Employee, Shift)
        .join(Employee, Employee.id == EmployeeShift.employee_id)
        .join(Shift, Shift.id == EmployeeShift.shift_id)
        .where(
            Employee.tenant_id == user.tenant_id,
            Employee.is_active.is_(True),
        )
        .order_by(Employee.full_name)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "employee_id": str(es.employee_id),
            "employee_name": emp.full_name,
            "employee_code": emp.employee_code,
            "shift_id": str(es.shift_id),
            "shift_name": sh.name,
            "shift_start": sh.start_time.strftime("%H:%M"),
            "shift_end": sh.end_time.strftime("%H:%M"),
            "effective_from": es.effective_from.isoformat(),
            "effective_to": es.effective_to.isoformat() if es.effective_to else None,
        }
        for es, emp, sh in rows
    ]


@router.post("/assignments", summary="Assign or update a shift for an employee")
async def assign_shift(
    payload: AssignIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    # Verify employee belongs to this tenant
    emp = await db.get(Employee, payload.employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404, "Employee not found")

    # Verify shift belongs to this tenant
    sh = await db.get(Shift, payload.shift_id)
    if not sh or sh.tenant_id != user.tenant_id:
        raise HTTPException(404, "Shift not found")

    # Close any existing open assignment for this employee
    existing = (await db.execute(
        select(EmployeeShift).where(
            and_(
                EmployeeShift.employee_id == payload.employee_id,
                EmployeeShift.effective_to.is_(None),
            )
        )
    )).scalars().all()
    for old in existing:
        old.effective_to = payload.effective_from

    # Create new assignment
    new_es = EmployeeShift(
        employee_id=payload.employee_id,
        shift_id=payload.shift_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(new_es)
    await db.commit()
    return {
        "employee_id": str(payload.employee_id),
        "shift_id": str(payload.shift_id),
        "effective_from": payload.effective_from.isoformat(),
        "shift_name": sh.name,
        "shift_start": sh.start_time.strftime("%H:%M"),
        "shift_end": sh.end_time.strftime("%H:%M"),
    }


@router.delete("/assignments/{employee_id}", summary="Remove shift assignment for an employee")
async def remove_assignment(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    emp = await db.get(Employee, employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404, "Employee not found")

    rows = (await db.execute(
        select(EmployeeShift).where(
            and_(
                EmployeeShift.employee_id == employee_id,
                EmployeeShift.effective_to.is_(None),
            )
        )
    )).scalars().all()
    today = date.today()
    for es in rows:
        es.effective_to = today
    await db.commit()
    return {"employee_id": str(employee_id), "unassigned": True}
