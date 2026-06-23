import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, get_current_user, role_required, CurrentUser
from ...models import Employee
from ...schemas.employee import EmployeeIn, EmployeeOut, EmployeeUpdate

router = APIRouter()


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = select(Employee).where(Employee.tenant_id == user.tenant_id)
    if not include_inactive:
        stmt = stmt.where(Employee.is_active == True)
    stmt = stmt.order_by(Employee.full_name)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.post("", response_model=EmployeeOut)
async def create_employee(payload: EmployeeIn, db: AsyncSession = Depends(get_db),
                           user: CurrentUser = Depends(role_required("hr"))):
    emp = Employee(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(emp); await db.commit(); await db.refresh(emp)
    return emp


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    emp = await db.get(Employee, employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404, "Employee not found")
    return emp


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(employee_id: uuid.UUID, payload: EmployeeUpdate,
                           db: AsyncSession = Depends(get_db),
                           user: CurrentUser = Depends(role_required("hr"))):
    emp = await db.get(Employee, employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404, "Employee not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(emp, field, value)
    await db.commit()
    await db.refresh(emp)
    return emp


@router.post("/{employee_id}/enroll", summary="Upload a face photo and extract ArcFace embedding")
async def enroll_face_image(
    employee_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    from ...core.ai import embedder
    from ...services.face_service import FaceEnrollmentService

    emp = await db.get(Employee, employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404, "Employee not found")

    image_bytes = await file.read()
    service = FaceEnrollmentService(db, embedder=embedder)
    try:
        result = await service.extract_and_enroll_image(employee_id, user.tenant_id, image_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return result


@router.patch("/{employee_id}/blacklist", summary="PRD §5.3: set or clear blacklist flag")
async def set_blacklist(employee_id: uuid.UUID, flagged: bool = True,
                         db: AsyncSession = Depends(get_db),
                         user: CurrentUser = Depends(role_required("admin"))):
    emp = await db.get(Employee, employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404)
    emp.is_blacklisted = flagged
    await db.commit()
    return {"employee_id": str(employee_id), "is_blacklisted": flagged}


@router.patch("/{employee_id}/vip", summary="PRD §5.3: set or clear VIP flag")
async def set_vip(employee_id: uuid.UUID, flagged: bool = True,
                  db: AsyncSession = Depends(get_db),
                  user: CurrentUser = Depends(role_required("admin"))):
    emp = await db.get(Employee, employee_id)
    if not emp or emp.tenant_id != user.tenant_id:
        raise HTTPException(404)
    emp.is_vip = flagged
    await db.commit()
    return {"employee_id": str(employee_id), "is_vip": flagged}


@router.delete("/{employee_id}")
async def deactivate_employee(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                               user: CurrentUser = Depends(role_required("hr"))):
    emp = await db.get(Employee, employee_id)
    if emp and emp.tenant_id == user.tenant_id:
        emp.is_active = False; await db.commit()
    return {"status": "deactivated"}
