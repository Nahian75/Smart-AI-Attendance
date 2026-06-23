"""Shared FastAPI dependencies: DB session, Redis, current user."""
import logging
import secrets
from typing import Annotated
from dataclasses import dataclass
import uuid

from fastapi import Depends, Request, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from .db.base import get_session
from .core.security import decode_token
from .core.exceptions import Unauthorized, Forbidden
from .core.security import require_role
from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class CurrentUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


async def get_db() -> AsyncSession:
    async for s in get_session():
        yield s


async def get_redis(request: Request):
    r = getattr(request.app.state, "redis", None)
    if r is not None:
        return r
    # Lazy reconnect — Redis may have been down at startup but available now
    try:
        r = await aioredis.from_url(
            settings.REDIS_URL, decode_responses=True,
            socket_connect_timeout=5, socket_timeout=5,
        )
        request.app.state.redis = r
        logger.info("Redis reconnected lazily")
        return r
    except Exception as e:
        logger.warning("Redis still unavailable: %s", e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service temporarily unavailable")


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    token: str | None = None
) -> CurrentUser:
    if authorization and authorization.startswith("Bearer "):
        token_str = authorization.removeprefix("Bearer ")
    elif token:
        token_str = token
    else:
        raise Unauthorized()
    
    payload = decode_token(token_str)
    if not payload:
        raise Unauthorized("Invalid or expired token")
    return CurrentUser(
        id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        role=payload["role"],
    )


def role_required(minimum: str):
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not require_role(user.role, minimum):
            raise Forbidden(f"Requires role: {minimum}")
        return user
    return _check


async def verify_edge_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Validate that the request carries the shared EDGE_TOKEN secret.

    In development (EDGE_TOKEN not set) requests pass through freely so the
    system works out-of-the-box without additional configuration.
    In production EDGE_TOKEN MUST be set (enforced by validate_production_secrets)
    and every request to the event-ingest endpoint must carry it.
    """
    configured = settings.EDGE_TOKEN
    if not configured:
        return  # dev mode — no token required

    token_str: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token_str = authorization.removeprefix("Bearer ")

    if not token_str or not secrets.compare_digest(token_str, configured):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing edge token")
