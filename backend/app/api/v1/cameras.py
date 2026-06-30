import uuid
import os
import threading
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ...dependencies import get_db, get_current_user, role_required, CurrentUser
from ...models import Camera
from ...models.attendance import RecognitionEvent, UnknownDetection, Alert

router = APIRouter()

# Guards the OPENCV_FFMPEG_CAPTURE_OPTIONS env-var override so concurrent
# /preview and /auto-configure requests don't clobber each other's FFmpeg flags.
_ffmpeg_env_lock = threading.Lock()


# ── Auto-configure helpers ────────────────────────────────────────────────────

def _estimate_camera_angle(frame_bytes: bytes) -> dict:
    """
    Take a JPEG snapshot and estimate:
      - cctv_mode: True if camera appears to be overhead/ceiling mounted
      - direction: entrance / interior
      - camera_role: entrance_gate / general / meeting_room
    """
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"cctv_mode": False, "direction": "entrance", "camera_role": "general"}

        h, w = frame.shape[:2]

        # Brightness check — very bright areas at top = overhead light = ceiling cam
        top_strip    = frame[:h//4, :].mean()
        bottom_strip = frame[3*h//4:, :].mean()
        is_dark_top  = top_strip < 60 and bottom_strip > top_strip * 1.5

        # Perspective cue: in a ceiling/overhead shot the floor is the dominant
        # surface and has roughly uniform colour across the full width.
        # In a wall-mounted shot there's a clear horizon line.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Horizontal variance in bottom half — high = wall cam (furniture/objects);
        # low = ceiling cam (flat floor)
        bottom_half_var = float(gray[h//2:, :].var())
        likely_overhead = bottom_half_var < 800 or is_dark_top

        return {
            "cctv_mode":   likely_overhead,
            "direction":   "interior" if likely_overhead else "entrance",
            "camera_role": "general" if likely_overhead else "entrance_gate",
        }
    except Exception:
        return {"cctv_mode": False, "direction": "entrance", "camera_role": "general"}


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

    import cv2

    for transport in ("tcp", "udp"):
        opts = f"rtsp_transport;{transport}|analyzeduration;5000000|probesize;5000000"
        with _ffmpeg_env_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = opts
            capture = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
        capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)
        try:
            if not capture.isOpened():
                capture.release()
                continue
            ok, frame = capture.read()
            if not ok or frame is None:
                capture.release()
                continue
            encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not encoded:
                capture.release()
                continue
            return jpeg.tobytes()
        finally:
            capture.release()

    raise RuntimeError(
        "Could not connect to the camera stream. "
        "Check the RTSP URL, credentials, and that port 554 is reachable."
    )


@router.get("/scan", summary="Scan LAN for ONVIF cameras")
async def scan_cameras(user: CurrentUser = Depends(role_required("admin"))):
    """
    WS-Discovery probe — finds ONVIF-compliant cameras on the local network.
    Returns discovered devices with their ONVIF addresses so the admin can
    quickly register them without knowing the RTSP URL upfront.
    """
    def _scan():
        try:
            from wsdiscovery.discovery import ThreadedWSDiscovery as WSD
            wsd = WSD()
            wsd.start()
            services = wsd.searchServices(timeout=5)
            found = []
            for s in services:
                xaddrs = s.getXAddrs()
                if any("onvif" in x.lower() for x in xaddrs):
                    # Try to resolve the RTSP stream URL via ONVIF
                    rtsp_url = None
                    try:
                        from onvif import ONVIFCamera
                        from urllib.parse import urlparse
                        onvif_url = xaddrs[0]
                        p = urlparse(onvif_url)
                        cam = ONVIFCamera(p.hostname, p.port or 80, "admin", "",
                                         no_cache=True, adjust_time=False,
                                         transport={"timeout": 3})
                        media = cam.create_media_service()
                        profiles = media.GetProfiles()
                        if profiles:
                            uri_resp = media.GetStreamUri({
                                "StreamSetup": {"Stream": "RTP-Unicast",
                                                "Transport": {"Protocol": "RTSP"}},
                                "ProfileToken": profiles[0]._token,
                            })
                            rtsp_url = uri_resp.Uri
                    except Exception:
                        pass
                    found.append({
                        "onvif_url": xaddrs[0] if xaddrs else None,
                        "rtsp_url":  rtsp_url,
                        "types":     str(s.getTypes()),
                    })
            wsd.stop()
            return found
        except ImportError:
            return []
        except Exception:
            return []

    result = await run_in_threadpool(_scan)
    return {"cameras": result, "count": len(result)}


@router.post("/{camera_id}/auto-configure",
             summary="Analyse snapshot and auto-set direction, role, cctv_mode")
async def auto_configure(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    """
    Takes a live snapshot from the camera, runs a quick heuristic to detect
    whether it is an overhead/CCTV camera or a wall-mounted entrance camera,
    and updates direction / camera_role accordingly.
    """
    cam = await db.get(Camera, camera_id)
    if not cam or cam.tenant_id != user.tenant_id:
        raise HTTPException(404, "Camera not found")
    if not cam.rtsp_url:
        raise HTTPException(400, "Camera has no RTSP URL")

    try:
        frame_bytes = await run_in_threadpool(_capture_camera_frame, cam.rtsp_url)
    except RuntimeError as exc:
        raise HTTPException(502, f"Could not capture snapshot: {exc}") from exc

    config = await run_in_threadpool(_estimate_camera_angle, frame_bytes)

    cam.direction   = config["direction"]
    cam.camera_role = config["camera_role"]
    await db.commit()

    return {
        "id":          str(cam.id),
        "direction":   cam.direction,
        "camera_role": cam.camera_role,
        "cctv_mode":   config["cctv_mode"],
        "auto_configured": True,
        "note": "cctv_mode is applied by the edge node based on direction/role — "
                "restart edge node to activate.",
    }


@router.get("")
async def list_cameras(
    include_disabled: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = select(Camera).where(Camera.tenant_id == user.tenant_id)
    if not include_disabled:
        stmt = stmt.where(Camera.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": str(c.id), "name": c.name, "location": c.location,
             "rtsp_url": c.rtsp_url, "fps_target": c.fps_target,
             "status": c.status, "direction": c.direction,
             "camera_role": c.camera_role, "camera_zone": c.camera_zone,
             "is_restricted": c.is_restricted, "is_active": c.is_active,
             "last_seen_at": c.last_seen_at} for c in rows]


@router.post("/{camera_id}/toggle", summary="Enable or disable a camera")
async def toggle_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(role_required("admin")),
):
    cam = await db.get(Camera, camera_id)
    if not cam or cam.tenant_id != user.tenant_id:
        raise HTTPException(404, "Camera not found")
    cam.is_active = not cam.is_active
    if not cam.is_active:
        cam.status = "offline"
    await db.commit()
    return {"id": str(cam.id), "is_active": cam.is_active, "status": cam.status}


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


@router.delete("/{camera_id}", summary="Permanently remove a camera and all its data")
async def delete_camera(camera_id: uuid.UUID,
                        db: AsyncSession = Depends(get_db),
                        user: CurrentUser = Depends(role_required("admin"))):
    cam = await db.get(Camera, camera_id)
    if not cam or cam.tenant_id != user.tenant_id:
        raise HTTPException(404, "Camera not found")

    # Hard delete — remove all associated records then the camera itself.
    # Cascade order matters: Alerts → RecognitionEvents → UnknownDetections → Camera.
    await db.execute(sql_delete(Alert).where(Alert.camera_id == camera_id))
    await db.execute(sql_delete(RecognitionEvent).where(RecognitionEvent.camera_id == camera_id))
    await db.execute(sql_delete(UnknownDetection).where(UnknownDetection.camera_id == camera_id))
    await db.delete(cam)
    await db.commit()

    return {"id": str(camera_id), "deleted": True, "data_purged": True}


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
