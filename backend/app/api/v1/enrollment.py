import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, get_current_user, role_required, CurrentUser
from ...models import FaceEmbedding
from ...services.face_service import FaceEnrollmentService

router = APIRouter()


@router.post("/match", summary="Match a probe embedding to an employee")
async def match(
    embedding: list[float] = Body(..., embed=True),
    threshold: float = Body(0.82, embed=True),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("manager")),
):
    service = FaceEnrollmentService(db)
    emp_id, sim = await service.match(embedding, user.tenant_id, threshold)
    return {"employee_id": str(emp_id) if emp_id else None, "similarity": round(sim, 4)}


@router.get("/export", summary="Export all enrolled embeddings for edge FAISS sync")
async def export_embeddings(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    rows = (await db.execute(
        select(FaceEmbedding)
        .options(joinedload(FaceEmbedding.employee))
        .where(FaceEmbedding.tenant_id == user.tenant_id)
    )).unique().scalars().all()
    return [
        {
            "employee_id": str(row.employee_id),
            "employee_name": row.employee.full_name if row.employee else str(row.employee_id)[:8],
            "embedding": [float(x) for x in row.embedding],
            "photo_angle": row.photo_angle,
        }
        for row in rows
    ]


@router.post("/{employee_id}", summary="Enroll precomputed face embeddings")
async def enroll(
    employee_id: uuid.UUID,
    embeddings: list[list[float]] = Body(..., embed=True,
        description="3-10 normalized 512-d ArcFace embeddings"),
    angles: list[str] | None = Body(default=None, embed=True),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    if len(embeddings) < 3:
        raise HTTPException(400, "Minimum 3 embeddings required for reliable enrollment")
    if any(len(e) != 512 for e in embeddings):
        raise HTTPException(400, "Each embedding must be 512-dimensional")
    service = FaceEnrollmentService(db)
    return await service.enroll_embeddings(employee_id, user.tenant_id, embeddings, angles)


@router.delete("/{employee_id}", summary="GDPR delete all face data")
async def delete_face(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("hr")),
):
    service = FaceEnrollmentService(db)
    await service.delete_face_data(employee_id, user.tenant_id)
    return {"message": f"Face data for {employee_id} deleted"}
