"""Edge node entrypoint: load config, models, embeddings; run all cameras."""
import asyncio
import os
import time
import yaml
import numpy as np
import httpx

from .detection.yolo_detector import YOLODetector
from .recognition.arcface import ArcFaceRecognizer, probe_camera_resolution, auto_det_size
from .recognition.anti_spoof import AntiSpoofChecker
from .recognition.mask_detector import MaskDetector
from .recognition.faiss_search import FaissSearch
from .camera.rtsp_reader import RTSPReader
from .camera.mjpeg_server import MJPEGServer
from .pipeline.frame_processor import FrameProcessor
from .pipeline.event_publisher import EventPublisher
from .utils.logger import get_logger
from .utils.gpu import log_info as log_gpu_info

log = get_logger("edge")


async def wait_for_backend(backend_url: str, max_wait: int = 180) -> bool:
    """Retry the backend /health endpoint until it responds or we time out."""
    deadline = time.monotonic() + max_wait
    delay = 2
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{backend_url}/health")
                if r.status_code == 200:
                    log.info("Backend is reachable.")
                    return True
        except Exception:
            pass
        remaining = int(deadline - time.monotonic())
        log.info(f"Backend not ready, retrying in {delay}s (up to {remaining}s remaining)...")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 15)
    return False


def load_config(path="config/camera_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


async def get_token(backend_url: str) -> str:
    static_token = os.getenv("EDGE_TOKEN", "")
    if static_token:
        return static_token
    email = os.getenv("EDGE_USER", os.getenv("ADMIN_EMAIL", "admin@demo.com"))
    password = os.getenv("EDGE_PASS", os.getenv("ADMIN_PASSWORD", "admin123"))
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{backend_url}/api/v1/auth/login",
                             json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["access_token"]
            log.info("Edge authenticated successfully.")
            return token
    except Exception as e:
        log.warning(f"Edge login failed ({e}); embedding sync will be skipped.")
        return ""


async def ensure_token(backend_url: str, token_ref: list) -> str:
    """Try to refresh the current token; fall back to full login."""
    t = token_ref[0]
    if t:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{backend_url}/api/v1/auth/refresh",
                    json={"access_token": t},
                )
                if r.status_code == 200:
                    token_ref[0] = r.json()["access_token"]
                    return token_ref[0]
        except Exception:
            pass
    # Fall back to full login
    token_ref[0] = await get_token(backend_url)
    return token_ref[0]


async def load_cameras(backend_url: str, token: str, fallback: list) -> list:
    if not token:
        log.warning("No auth token; using cameras from config file.")
        return fallback
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{backend_url}/api/v1/cameras",
                            headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            cameras = [cam for cam in r.json() if cam.get("rtsp_url")]
        if cameras:
            log.info(f"Loaded {len(cameras)} camera(s) from backend.")
            return cameras
        log.warning("No cameras registered in backend; using config file cameras as fallback.")
        return fallback
    except Exception as e:
        log.warning(f"Could not load cameras from backend ({e}); using config file cameras.")
        return fallback


async def load_embeddings(backend_url: str, tenant_id: str, token: str) -> tuple[np.ndarray, list[str], dict[str, str]]:
    if not token:
        log.warning("No auth token; starting with empty FAISS index.")
        return np.zeros((0, 512), dtype=np.float32), [], {}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{backend_url}/api/v1/enrollment/export",
                            headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            data = r.json()
            if not data:
                log.info("No enrolled faces yet; FAISS index will be empty.")
                return np.zeros((0, 512), dtype=np.float32), [], {}
            embs = np.array([d["embedding"] for d in data], dtype=np.float32)
            ids = [d["employee_id"] for d in data]
            id_to_name = {d["employee_id"]: d.get("employee_name", d["employee_id"][:8]) for d in data}
            return embs, ids, id_to_name
    except Exception as e:
        log.warning(f"Embedding sync failed ({e}); starting with empty index.")
        return np.zeros((0, 512), dtype=np.float32), [], {}


async def heartbeat_loop(backend_url: str, token_ref: list, readers: dict,
                          publisher=None, interval: int = 30) -> None:
    """Ping the backend heartbeat endpoint every `interval` seconds for all cameras.
    Uses readers.keys() live so cameras added by camera_watch_loop are included."""
    while True:
        await asyncio.sleep(interval)
        for cam_id in list(readers.keys()):
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.post(
                        f"{backend_url}/api/v1/cameras/{cam_id}/heartbeat",
                        params={"status": "online"},
                        headers={"Authorization": f"Bearer {token_ref[0]}"},
                    )
                    if r.status_code == 401:
                        await ensure_token(backend_url, token_ref)
                        if publisher:
                            publisher.set_token(token_ref[0])
                        async with httpx.AsyncClient(timeout=5) as c:
                            await c.post(
                                f"{backend_url}/api/v1/cameras/{cam_id}/heartbeat",
                                params={"status": "online"},
                                headers={"Authorization": f"Bearer {token_ref[0]}"},
                            )
            except Exception:
                pass


async def embedding_watch_loop(backend_url: str, tenant_id: str, token_ref: list,
                                face_search: FaissSearch, id_to_name: dict,
                                interval: int = 60) -> None:
    """Reload enrolled face embeddings from the backend every `interval` seconds,
    so newly-enrolled employees are recognised without restarting the edge node."""
    while True:
        await asyncio.sleep(interval)
        try:
            await ensure_token(backend_url, token_ref)
            embs, ids, new_id_to_name = await load_embeddings(backend_url, tenant_id, token_ref[0])
            if len(ids):
                face_search.build(embs, ids)
                id_to_name.clear()
                id_to_name.update(new_id_to_name)
                log.info(f"FAISS index resynced: {len(ids)} face embedding(s).")
        except Exception as e:
            log.warning(f"Embedding resync error: {e}")


def _start_reader(cam: dict, processor: FrameProcessor, cfg: dict,
                  loop: asyncio.AbstractEventLoop) -> RTSPReader:
    def make_cb(proc):
        def cb(frame, ts):
            asyncio.run_coroutine_threadsafe(proc.process(frame, ts), loop)
        return cb

    reader = RTSPReader(
        cam["id"], cam["rtsp_url"],
        fps_target=cam.get("fps_target") or cfg.get("fps_target", 6),
        use_gstreamer=cfg.get("use_gstreamer", False),
    )
    reader.start(make_cb(processor))
    log.info(f"Started camera {cam['id']} ({cam.get('direction')})")
    return reader


async def camera_watch_loop(backend_url: str, token_ref: list, fallback: list,
                             readers: dict, processors: dict,
                             cfg: dict, mjpeg: MJPEGServer,
                             publisher: EventPublisher,
                             make_detector, recognizer: ArcFaceRecognizer,
                             anti_spoof: AntiSpoofChecker, face_search: FaissSearch,
                             id_to_name: dict, snapshot_dir: str,
                             loop: asyncio.AbstractEventLoop,
                             interval: int = 60) -> None:
    """Reload camera list from backend every `interval` seconds.
    Starts new cameras and restarts ones whose URL changed."""
    while True:
        await asyncio.sleep(interval)
        try:
            await ensure_token(backend_url, token_ref)
            cameras = await load_cameras(backend_url, token_ref[0], fallback)
            new_map = {c["id"]: c for c in cameras}

            # Restart cameras whose URL changed
            for cam_id, reader in list(readers.items()):
                new_cam = new_map.get(cam_id)
                if new_cam and new_cam.get("rtsp_url") != reader.rtsp_url:
                    log.info(f"Camera {cam_id} URL changed — restarting reader.")
                    reader.stop()
                    proc = processors[cam_id]
                    readers[cam_id] = _start_reader(new_cam, proc, cfg, loop)

            # Start brand-new cameras — each gets its own YOLODetector
            for cam_id, cam in new_map.items():
                if cam_id not in readers:
                    log.info(f"New camera detected: {cam_id}")
                    proc = FrameProcessor(
                        camera_id=cam_id, direction=cam.get("direction", "entrance"),
                        config=cfg, detector=make_detector(), recognizer=recognizer,
                        anti_spoof=anti_spoof, face_search=face_search, publisher=publisher,
                        snapshot_dir=snapshot_dir, mjpeg_server=mjpeg, id_to_name=id_to_name,
                        mask_detector=mask_detector,
                    )
                    processors[cam_id] = proc
                    readers[cam_id] = _start_reader(cam, proc, cfg, loop)

        except Exception as e:
            log.warning(f"Camera watch error: {e}")


async def main():
    # OPENCV_FFMPEG_CAPTURE_OPTIONS is set per-connection in RTSPReader._connect()
    # with low-latency flags (nobuffer, low_delay). Do not set a default here
    # as it would be overridden anyway and the high analyzeduration/probesize
    # values (2000000) caused long stream-open times and added to buffer delay.

    cfg = load_config(os.getenv("CAMERA_CONFIG", "config/camera_config.yaml"))
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    tenant_id = os.getenv("TENANT_ID", cfg.get("tenant_id", "demo"))
    snapshot_dir = os.getenv("SNAPSHOT_DIR", "/app/snapshots")

    log.info(f"Connecting to backend at {backend_url} ...")
    if not await wait_for_backend(backend_url):
        log.error(f"Backend unreachable after 3 minutes at {backend_url}. Exiting.")
        return

    # ── Load cameras first so we can probe resolution before loading models ──
    token = await get_token(backend_url)
    token_ref = [token]
    embs, ids, id_to_name = await load_embeddings(backend_url, tenant_id, token)

    cameras = await load_cameras(backend_url, token, cfg.get("cameras", []))
    if not cameras:
        log.warning(
            "No cameras found in backend or config. "
            "Register cameras in the dashboard — edge node will poll every 30s."
        )
        while not cameras:
            await asyncio.sleep(30)
            await ensure_token(backend_url, token_ref)
            cameras = await load_cameras(backend_url, token_ref[0], cfg.get("cameras", []))
        log.info(f"Cameras loaded: {len(cameras)}")

    # ── Auto-select det_size from actual camera resolution ────────────────────
    # Config `det_size` overrides auto-detection if set explicitly.
    _det_size = (640, 640)
    _cfg_det = cfg.get("det_size")
    if _cfg_det:
        _det_size = (int(_cfg_det), int(_cfg_det))
        log.info(f"det_size set by config: {_det_size[0]}×{_det_size[1]}")
    else:
        _rtsp = cameras[0].get("rtsp_url", "") if cameras else ""
        if _rtsp:
            log.info("Probing camera resolution to auto-select det_size ...")
            _res = probe_camera_resolution(_rtsp)
            if _res:
                _det_size = auto_det_size(*_res)
                log.info(
                    f"Camera: {_res[0]}×{_res[1]} → det_size auto-selected: "
                    f"{_det_size[0]}×{_det_size[1]}"
                )
            else:
                log.warning("Could not probe camera resolution — using det_size=640×640")
        else:
            log.info("No camera URL available for probe — using det_size=640×640")

    # ── Load AI models ────────────────────────────────────────────────────────
    device = os.getenv("DEVICE", cfg.get("device", "auto"))
    log.info(f"Loading models on device={device} ...")
    log_gpu_info()
    # NOTE: YOLODetector is intentionally NOT shared across cameras.
    # ByteTrack maintains per-instance tracker state (track IDs, Kalman filters).
    # If one model is shared, alternating frames from cam1/cam2 corrupt the tracker
    # state causing tracks to never confirm (shows tracks=0 on secondary cameras).
    # Each camera gets its own YOLODetector — weights are cached by PyTorch so VRAM
    # usage is only marginally higher (~50MB extra per additional camera).
    _yolo_model = cfg.get("yolo_model", "yolo11s.pt")
    _tracker_cfg = cfg.get("tracker", "bytetrack.yaml")

    def _make_detector() -> YOLODetector:
        return YOLODetector(_yolo_model, device=device, tracker_cfg=_tracker_cfg)

    recognizer = ArcFaceRecognizer(device=device, det_size=_det_size)
    anti_spoof = AntiSpoofChecker(
        cfg.get("antispoof_model"),
        threshold=cfg.get("liveness_threshold"),
    )
    mask_detector = MaskDetector(
        cfg.get("mask_model"),
        threshold=cfg.get("mask_threshold"),
    )

    face_search = FaissSearch(
        threshold=cfg.get("recognition_threshold", 0.82),
        top_k=cfg.get("faiss_top_k", 5),
    )
    if len(ids):
        face_search.build(embs, ids)

    if len(ids) == 0:
        log.warning(
            "FAISS index is EMPTY — no enrolled faces loaded. "
            "Enroll employees via the dashboard, then restart the edge node."
        )
    else:
        log.info(f"FAISS index ready: {len(ids)} face embedding(s) for recognition.")

    mjpeg = MJPEGServer(port=int(os.getenv("MJPEG_PORT", "8001")))
    await mjpeg.start()

    publisher = EventPublisher(redis_url, backend_url, tenant_id)
    publisher.set_token(token_ref[0])
    loop = asyncio.get_event_loop()

    readers: dict[str, RTSPReader] = {}
    processors: dict[str, FrameProcessor] = {}

    for cam in cameras:
        proc = FrameProcessor(
            camera_id=cam["id"], direction=cam.get("direction", "entrance"),
            config=cfg, detector=_make_detector(), recognizer=recognizer,
            anti_spoof=anti_spoof, face_search=face_search, publisher=publisher,
            snapshot_dir=snapshot_dir, mjpeg_server=mjpeg, id_to_name=id_to_name,
            mask_detector=mask_detector,
        )
        processors[cam["id"]] = proc
        readers[cam["id"]] = _start_reader(cam, proc, cfg, loop)

    try:
        await asyncio.gather(
            heartbeat_loop(backend_url, token_ref, readers, publisher=publisher),
            camera_watch_loop(
                backend_url, token_ref, cfg.get("cameras", []),
                readers, processors, cfg, mjpeg, publisher,
                _make_detector, recognizer, anti_spoof, face_search,
                id_to_name, snapshot_dir, loop,
            ),
            embedding_watch_loop(backend_url, tenant_id, token_ref, face_search, id_to_name),
        )
    finally:
        for r in readers.values():
            r.stop()
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
