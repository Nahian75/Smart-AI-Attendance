"""FastAPI application factory."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import redis.asyncio as aioredis
from prometheus_client import make_asgi_app

from .config import settings
from .core.middleware import TenantMiddleware, RateLimitMiddleware
from .api.v1 import auth, attendance, employees, enrollment, cameras, reports, ws, alerts, analytics, rbac, admin, shifts, detections

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.redis = await aioredis.from_url(
            settings.REDIS_URL, decode_responses=True,
            socket_connect_timeout=5, socket_timeout=5,
        )
    except Exception as e:
        logger.warning("Redis unavailable at startup: %s", e)
        app.state.redis = None
    yield
    if hasattr(app.state, "redis") and app.state.redis is not None:
        await app.state.redis.close()


_docs_url = None if settings.ENVIRONMENT == "production" else "/api/docs"
_redoc_url = None if settings.ENVIRONMENT == "production" else "/api/redoc"

app = FastAPI(
    title="Smart Attendance API",
    version="1.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=200)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Original routes
app.include_router(auth.router,        prefix="/api/v1/auth",        tags=["auth"])
app.include_router(attendance.router,  prefix="/api/v1/attendance",  tags=["attendance"])
app.include_router(employees.router,   prefix="/api/v1/employees",   tags=["employees"])
app.include_router(enrollment.router,  prefix="/api/v1/enrollment",  tags=["enrollment"])
app.include_router(cameras.router,     prefix="/api/v1/cameras",     tags=["cameras"])
app.include_router(reports.router,     prefix="/api/v1/reports",     tags=["reports"])
# New routes matching PRD §5.2, §5.3, §5.4
app.include_router(alerts.router,      prefix="/api/v1/alerts",      tags=["alerts"])
app.include_router(analytics.router,   prefix="/api/v1/analytics",   tags=["analytics"])
app.include_router(rbac.router,        prefix="/api/v1/rbac",        tags=["rbac"])
app.include_router(admin.router,       prefix="/api/v1/admin/users",  tags=["admin"])
app.include_router(shifts.router,      prefix="/api/v1/shifts",       tags=["shifts"])
app.include_router(detections.router,  prefix="/api/v1/detections",   tags=["detections"])
# WebSocket
app.include_router(ws.router,          prefix="/ws",                  tags=["websocket"])

app.mount("/metrics", make_asgi_app())

# Serve face snapshots — lets the frontend display captured images directly
_snap_dir = settings.SNAPSHOT_DIR
if os.path.exists(_snap_dir):
    app.mount("/snapshots", StaticFiles(directory=_snap_dir), name="snapshots")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": "1.1.0", "environment": settings.ENVIRONMENT}
