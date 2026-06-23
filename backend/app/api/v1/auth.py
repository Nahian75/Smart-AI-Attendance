from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from ...dependencies import get_db, get_current_user, CurrentUser
from ...models import User
from ...core.security import verify_password, hash_password, create_access_token, decode_token
from ...core.exceptions import Unauthorized
from ...schemas.auth import LoginIn, RefreshIn, TokenOut, ChangePasswordIn

router = APIRouter()


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise Unauthorized("Invalid credentials")
    if not user.is_active:
        raise Unauthorized("Account disabled")
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token(user.id, user.tenant_id, user.role)
    return TokenOut(access_token=token, role=user.role, tenant_id=str(user.tenant_id))


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn):
    """Issue a new access token from a still-valid existing token."""
    payload_data = decode_token(payload.access_token)
    if not payload_data:
        raise Unauthorized("Token expired or invalid — please log in again")
    token = create_access_token(
        payload_data["sub"],
        payload_data["tenant_id"],
        payload_data["role"],
    )
    return TokenOut(
        access_token=token,
        role=payload_data["role"],
        tenant_id=payload_data["tenant_id"],
    )


@router.post("/change-password", summary="Change the authenticated user's own password")
async def change_password(
    payload: ChangePasswordIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    db_user = await db.get(User, user.id)
    if not db_user:
        raise Unauthorized("User not found")
    if not verify_password(payload.current_password, db_user.hashed_password):
        raise Unauthorized("Current password is incorrect")
    db_user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}
