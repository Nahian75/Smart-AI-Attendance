"""User management endpoints — admin only."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, role_required, CurrentUser
from ...models import User
from ...core.security import hash_password

router = APIRouter()

VALID_ROLES = {"super_admin", "admin", "hr", "manager", "security", "viewer"}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="viewer")


class UserRoleUpdate(BaseModel):
    role: str
    is_active: bool | None = None


@router.get("", summary="List all users in the tenant")
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    rows = (await db.execute(
        select(User).where(User.tenant_id == user.tenant_id).order_by(User.created_at)
    )).scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]


@router.post("", summary="Create a new user")
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(role_required("admin")),
):
    if payload.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A user with this email already exists")
    u = User(
        tenant_id=current.tenant_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return {"id": str(u.id), "email": u.email, "role": u.role}


@router.patch("/{user_id}", summary="Update a user's role or active status")
async def update_user(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(role_required("admin")),
):
    if payload.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
    u = await db.get(User, user_id)
    if not u or u.tenant_id != current.tenant_id:
        raise HTTPException(404, "User not found")
    if str(u.id) == str(current.id):
        raise HTTPException(400, "You cannot change your own role")
    u.role = payload.role
    if payload.is_active is not None:
        u.is_active = payload.is_active
    await db.commit()
    return {"id": str(u.id), "email": u.email, "role": u.role, "is_active": u.is_active}


@router.delete("/{user_id}", summary="Deactivate a user")
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(role_required("admin")),
):
    u = await db.get(User, user_id)
    if not u or u.tenant_id != current.tenant_id:
        raise HTTPException(404, "User not found")
    if str(u.id) == str(current.id):
        raise HTTPException(400, "You cannot deactivate yourself")
    u.is_active = False
    await db.commit()
    return {"id": str(u.id), "deactivated": True}
