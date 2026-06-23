import uuid
import cv2
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ...dependencies import get_db, get_current_user, role_required, CurrentUser
from ...models import Camera

router = APIRouter()


class CameraIn(BaseModel):
    name: str
    location: str | None = None
    rtsp_url: str
    branch_id: uuid.UUID | None = None
    camera_type: str = "ip"
    direction: str = "entrance"     # entrance | exit | interior
    camera_role: str = "general"    # general | meeting_room | reception | entrance_gate
    camera_zone: str | None = None  # zone label for occupancy grouping
    is_restricted: bool = False     # PRD §5.3: any detection fires alert
    fps_target: int = Field(default=10, ge=1, le=60)

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            raise ValueError(
                "Stream URL must start with rtsp://, rtsps://, http://, or https://"
            )
        return value


class CameraUpdate(CameraIn):
    pass


def _capture_camera_frame(rtsp_url: str) -> bytes:
    # For HTTP cameras (e.g. Android IP Webcam), fetch /shot.jpg directly.
    # Opening the full MJPEG /video stream just to grab one frame takes 2-4s;
    # /shot.jpg is a plain HTTP GET that returns a JPEG in ~100ms.
    if rtsp_url.lower().startswith(("http://", "https://")):
        parsed = urlparse(rtsp_url)
        shot_url = f"{parsed.scheme}://{parsed.netloc}/shot.jpg"
        try:
            with urllib.request.urlopen(shot_url, timeout=8) as resp:
                data = resp.read()
            if not data:
                raise RuntimeError("Empty response from camera snapshot")
            return data
        except Exception as exc:
            raise RuntimeError(f"Could not fetch snapshot ({shot_url}): {exc}") from exc

    capture = cv2.VideoCapture(
        rtsp_url,
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
        ],
    )
    try:
        if not capture.isOpened():
            raise RuntimeError("Could not connect to the camera stream")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError("Connected, but could not read a camera frame")
        encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not encoded:
            raise RuntimeError("Could not encode the camera frame")
        return jpeg.tobytes()
    finally:
        capture.release()


@router.get("")
async def list_cameras(db: AsyncSession = Depends(get_db),
                        user: CurrentUser = Depends(get_current_user)):
    rows = (await db.execute(
        select(Camera).where(
            Camera.tenant_id == user.tenant_id,
            Camera.is_active.is_(True),
        )
    )).scalars().all()
    return [{"id": str(c.id), "name": c.name, "location": c.location,
             "rtsp_url": c.rtsp_url, "fps_target": c.fps_target,
             "status": c.status, "direction": c.direction,
             "camera_role": c.camera_role, "camera_zone": c.camera_zone,
             "is_restricted": c.is_restricted, "last_seen_at": c.last_seen_at} for c in rows]


@router.post("")
async def add_camera(payload: CameraIn, db: AsyncSession = Depends(get_db),
                      user: CurrentUser = Depends(role_required("admin"))):
    cam = Camera(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(cam); await db.commit(); await db.refresh(cam)
    return {"id": str(cam.id), "name": cam.name}


@router.patch("/{camera_id}", summary="Update camera settings")
async def update_camera(camera_id: uuid.UUID, payload: CameraUpdate,
                         db: AsyncSession = Depends(get_db),
                         user: CurrentUser = Depends(role_required("admin"))):
    cam = await db.get(Camera, camera_id)
    if not cam or cam.tenant_id != user.tenant_id:
        raise HTTPException(404, "Camera not found")
    for key, value in payload.model_dump().items():
        setattr(cam, key, value)
    await db.commit()
    return {"id": str(cam.id), "updated": True}


@router.delete("/{camera_id}", summary="Deactivate a camera")
async def delete_camera(camera_id: uuid.UUID,
                        db: AsyncSession = Depends(get_db),
                        user: CurrentUser = Depends(role_required("admin"))):
    cam = await db.get(Camera, camera_id)
    if not cam or cam.tenant_id != user.tenant_id:
        raise HTTPException(404, "Camera not found")
    cam.is_active = False
    cam.status = "offline"
    await db.commit()
    return {"id": str(camera_id), "deleted": True}


@router.get("/{camera_id}/preview", summary="Capture a JPEG preview from the camera")
async def camera_preview(camera_id: uuid.UUID,
                         db: AsyncSession = Depends(get_db),
                         user: CurrentUser = Depends(get_current_user)):
    cam = await db.get(Camera, camera_id)
    if not cam or cam.tenant_id != user.tenant_id or not cam.is_active:
        raise HTTPException(404, "Camera not found")
    if not cam.rtsp_url:
        raise HTTPException(400, "Camera has no RTSP URL")

    try:
        jpeg = await run_in_threadpool(_capture_camera_frame, cam.rtsp_url)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{camera_id}/heartbeat")
async def heartbeat(camera_id: uuid.UUID, status: str = "online",
                     db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if cam:
        cam.status = status; cam.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
    return {"ok": True}
