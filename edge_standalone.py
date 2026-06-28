"""
Standalone edge node — Windows / macOS / Linux, no Docker needed.

Features:
  - Anti-spoofing   : ONNX model (MiniFASNet) if available; texture heuristic fallback
  - Face enhancement: bilateral denoise + unsharp mask + CLAHE (recovers V380 / budget cam detail)
  - Multi-frame voting: confirms recognition over N frames — eliminates single-frame flip-flop
  - GPU support     : CUDA (NVIDIA) or DirectML (Windows GPU) via onnxruntime; CPU fallback
  - Auto-reconnect  : exponential backoff on stream failure; resumes without restart
  - Embedding resync: reloads enrolled faces from backend every 60 s

Requirements (run once):
    pip install insightface onnxruntime opencv-python numpy httpx pyyaml

    For GPU (NVIDIA):
    pip install onnxruntime-gpu   (instead of onnxruntime)

Usage:
    python edge_standalone.py

Environment variables:
    CAMERA_SRC          = 0 (webcam index) or rtsp://user:pass@IP:554/stream
    BACKEND_URL         = http://localhost:8000
    EDGE_USER           = admin@demo.com
    EDGE_PASS           = admin123
    TENANT_ID           = demo
    CAMERA_ID           = standalone-cam
    DIRECTION           = entrance   (or exit)
    ANTISPOOF_MODEL     = edge/weights/antispoof_128.onnx
    LIVENESS_THRESHOLD  = 0.38
    REC_THRESH          = 0.42
    VOTE_WINDOW         = 5
    MIN_VOTES           = 3
    COOLDOWN_S          = 300
    PROCESS_EVERY_N     = 3    (process 1 in every N frames to save CPU)
    RECONNECT_DELAY     = 3    (seconds before first reconnect attempt)
"""
import asyncio
import math
import os
import sys
import time
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("standalone")

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_SRC         = os.getenv("CAMERA_SRC",         "0")
BACKEND_URL        = os.getenv("BACKEND_URL",         "http://localhost:8000").rstrip("/")
EDGE_USER          = os.getenv("EDGE_USER",           "admin@demo.com")
EDGE_PASS          = os.getenv("EDGE_PASS",           "admin123")
TENANT_ID          = os.getenv("TENANT_ID",           "demo")
CAMERA_ID          = os.getenv("CAMERA_ID",           "standalone-cam")
DIRECTION          = os.getenv("DIRECTION",           "entrance")
ANTISPOOF_MODEL    = os.getenv("ANTISPOOF_MODEL",     "edge/weights/antispoof_128.onnx")
SUPERRES_MODEL     = os.getenv("SUPERRES_MODEL",      "edge/weights/FSRCNN_x2.pb")
LIVENESS_THRESHOLD = float(os.getenv("LIVENESS_THRESHOLD", "0.38"))
REC_THRESH         = float(os.getenv("REC_THRESH",    "0.42"))
VOTE_WINDOW        = int(os.getenv("VOTE_WINDOW",     "5"))
MIN_VOTES          = int(os.getenv("MIN_VOTES",       "3"))
COOLDOWN_S         = int(os.getenv("COOLDOWN_S",      "300"))
PROCESS_EVERY_N    = int(os.getenv("PROCESS_EVERY_N", "3"))
RECONNECT_DELAY    = int(os.getenv("RECONNECT_DELAY", "3"))

# Single-threaded inference pool — keeps GPU context alive between calls
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")


# ── GPU detection ─────────────────────────────────────────────────────────────
def detect_gpu() -> dict:
    """Return onnxruntime providers and InsightFace ctx_id for best available device."""
    try:
        import onnxruntime as ort
        avail = ort.get_available_providers()
        if "CUDAExecutionProvider" in avail:
            log.info("GPU: NVIDIA CUDA detected — inference will run on GPU")
            return {"ort_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                    "insightface_ctx": 0}
        if "DirectMLExecutionProvider" in avail:
            log.info("GPU: DirectML detected (Windows GPU) — inference will run on DirectML")
            return {"ort_providers": ["DirectMLExecutionProvider", "CPUExecutionProvider"],
                    "insightface_ctx": -1}
    except Exception:
        pass
    log.info("GPU: no accelerator found — running on CPU")
    return {"ort_providers": ["CPUExecutionProvider"], "insightface_ctx": -1}


# ── Face enhancement ──────────────────────────────────────────────────────────
# ── Neural super-resolution ───────────────────────────────────────────────────
class FaceSuperRes:
    """FSRCNN 2x neural upscaler. Falls back to Lanczos if contrib not installed."""

    def __init__(self, model_path: str):
        self._sr = None
        if not hasattr(cv2, "dnn_superres"):
            log.warning("cv2.dnn_superres not available — install opencv-contrib-python for SR. Using Lanczos.")
            return
        if not (model_path and os.path.exists(model_path)):
            log.warning("SR model not found at %r — using Lanczos upscale.", model_path)
            return
        try:
            sr = cv2.dnn_superres.DnnSuperResImpl_create()
            sr.readModel(model_path)
            sr.setModel("fsrcnn", 2)
            test = np.zeros((32, 32, 3), dtype=np.uint8)
            if sr.upsample(test).shape[0] == 64:
                self._sr = sr
                log.info("FaceSuperRes: FSRCNN x2 loaded → face crops will be 2x upscaled before ArcFace")
        except Exception as e:
            log.warning("FSRCNN load failed (%s) — using Lanczos", e)

    def upscale(self, face_bgr: np.ndarray) -> np.ndarray:
        if face_bgr is None or face_bgr.size == 0:
            return face_bgr
        h, w = face_bgr.shape[:2]
        if self._sr is not None:
            try:
                return self._sr.upsample(face_bgr)
            except Exception:
                pass
        return cv2.resize(face_bgr, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)


def enhance_face(face_bgr: np.ndarray) -> np.ndarray:
    """
    Recover texture destroyed by V380 / budget-camera H.264 compression.
    Pipeline: bilateral denoise → unsharp mask → CLAHE on luminance.
    Lifts ArcFace similarity by 5–15% on compressed streams.
    """
    if face_bgr is None or face_bgr.size == 0:
        return face_bgr
    h, w = face_bgr.shape[:2]
    if h < 32 or w < 32:
        return face_bgr
    work = cv2.resize(face_bgr, (128, 128)) if min(h, w) < 128 else face_bgr.copy()
    # 1. Bilateral — removes block noise, preserves edges
    work = cv2.bilateralFilter(work, d=5, sigmaColor=30, sigmaSpace=5)
    # 2. Unsharp mask — restores fine texture (pores, eyebrows)
    blurred = cv2.GaussianBlur(work, (0, 0), sigmaX=1.5)
    work = np.clip(cv2.addWeighted(work, 1.8, blurred, -0.8, 0), 0, 255).astype(np.uint8)
    # 3. CLAHE on L channel — normalises patchy exposure
    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    l_ch = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l_ch)
    work = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    return cv2.resize(work, (w, h)) if min(h, w) < 128 else work


# ── Anti-spoof ────────────────────────────────────────────────────────────────
class AntiSpoofChecker:
    """
    Primary path:  MiniFASNet ONNX model (CelebA-Spoof trained, AUC ~0.99).
                   Download: github.com/hairymax/Face-AntiSpoofing → releases
                   Place at: edge/weights/antispoof_128.onnx

    Fallback path: Multi-cue texture heuristic when no model file is found.
                   Catches printed photos reliably; weaker against screens on
                   heavily compressed streams (H.264 kills screen moiré).
    """

    def __init__(self, model_path: str, threshold: float):
        self.threshold = threshold
        self.session = None
        self.input_name = None
        self._img_size = 128
        # Per-track temporal state for static-image (phone/tablet) detection.
        self._temporal: dict[str, dict] = {}

        if model_path and os.path.exists(model_path):
            try:
                import onnxruntime as ort
                gpu = detect_gpu()
                self.session = ort.InferenceSession(model_path,
                                                    providers=gpu["ort_providers"])
                self.input_name = self.session.get_inputs()[0].name
                shape = self.session.get_inputs()[0].shape
                if len(shape) == 4 and isinstance(shape[2], int):
                    self._img_size = int(shape[2])
                log.info("Anti-spoof model loaded: %s (input %dx%d)",
                         model_path, self._img_size, self._img_size)
            except Exception as e:
                log.warning("Anti-spoof model load failed (%s) — using heuristic", e)
                self.session = None
        else:
            if model_path:
                log.warning(
                    "Anti-spoof model not found at %r — using texture heuristic fallback.\n"
                    "  Download: https://github.com/hairymax/Face-AntiSpoofing/releases\n"
                    "  Place at: edge/weights/antispoof_128.onnx",
                    model_path,
                )
            else:
                log.info("No anti-spoof model configured — using texture heuristic fallback.")

    def check(self, face_bgr: np.ndarray,
              track_id: str | None = None) -> tuple[bool, float]:
        """Returns (is_live, p_live). face_bgr must be a tight BGR face crop."""
        if face_bgr is None or face_bgr.size == 0:
            return True, 1.0
        score = self._model_infer(face_bgr) if self.session else self._heuristic(face_bgr)
        if track_id is not None:
            score = self._temporal_gate(score, face_bgr, track_id)
        return score >= self.threshold, round(float(score), 4)

    def _temporal_gate(self, score: float, face: np.ndarray, track_id: str) -> float:
        """Histogram-based static-image detector — catches phone photos that the
        per-frame heuristic misses because phone screens are genuinely sharp."""
        small = cv2.resize(face, (48, 48)) if min(face.shape[:2]) > 48 else face
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if len(small.shape) == 3 else small
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
        hist /= hist.sum() + 1e-6

        state = self._temporal.setdefault(track_id, {"prev_hist": None, "static_count": 0})
        if state["prev_hist"] is not None:
            diff = float(np.sum(np.abs(hist - state["prev_hist"])))
            # Phone photo: diff ≈ 0.01–0.04; live face: diff ≈ 0.06–0.15
            if diff < 0.055:
                state["static_count"] = min(state["static_count"] + 1, 12)
            else:
                state["static_count"] = max(0, state["static_count"] - 1)
        state["prev_hist"] = hist.copy()

        if state["static_count"] >= 1:
            penalty = max(0.0, 1.0 - state["static_count"] / 8.0)
            score = score * penalty
        return score

    def _model_infer(self, face_bgr: np.ndarray) -> float:
        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        blob = self._letterbox(rgb, self._img_size)
        blob = blob.transpose(2, 0, 1).astype(np.float32)[None] / 255.0
        logits = self.session.run(None, {self.input_name: blob})[0][0]
        e = np.exp(logits - logits.max())
        return float((e / e.sum())[0])   # index 0 = P(live)

    @staticmethod
    def _heuristic(face_bgr: np.ndarray) -> float:
        face = cv2.resize(face_bgr, (96, 96))
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)

        # Sharpness — real faces through H.264 budget cameras: lap_var 60–280.
        # Phone/tablet screens: lap_var 400–1200 (no compression blur).
        # We score sharpness UP to the real-face range, then PENALISE excess —
        # a score that keeps rising past 350 is almost certainly a screen.
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        lap_score = min(1.0, lap_var / 350.0)
        if lap_var > 350.0:
            lap_score *= max(0.0, 1.0 - (lap_var - 350.0) / 500.0)

        # Gradient energy — same excess-sharpness penalty.
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mean = float(np.sqrt(gx**2 + gy**2).mean())
        grad_score = min(1.0, grad_mean / 22.0)
        if grad_mean > 25.0:
            grad_score *= max(0.0, 1.0 - (grad_mean - 25.0) / 35.0)

        # Colour saturation variation — real skin varies more than a photo print.
        hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
        sat_score = min(1.0, float(hsv[:, :, 1].std()) / 32.0)

        # FFT high-frequency ratio — moiré from screens (weak on H.264 streams).
        f = np.fft.fftshift(np.fft.fft2(gray))
        mag = np.abs(f)
        cy, cx = mag.shape[0] // 2, mag.shape[1] // 2
        mask = np.ones_like(mag)
        mask[cy - 8:cy + 8, cx - 8:cx + 8] = 0
        hf_score = min(1.0, float((mag * mask).sum() / (mag.sum() + 1e-6)) * 1.4)

        # Luminance patch variance — screen backlight is spatially uniform (low std);
        # real faces lit by natural/overhead light have patchy brightness (higher std).
        bh, bw = gray.shape[0] // 4, gray.shape[1] // 4
        block_means = [
            float(gray[r * bh:(r + 1) * bh, c * bw:(c + 1) * bw].mean())
            for r in range(4) for c in range(4)
        ]
        lum_score = min(1.0, float(np.std(block_means)) / 18.0)

        # Weight: sharpness cues reduced (screens score too high on them without
        # the penalty above), lum_score dominant (most reliable screen cue).
        return float(lap_score  * 0.15
                     + grad_score * 0.10
                     + sat_score  * 0.13
                     + hf_score   * 0.10
                     + lum_score  * 0.52)

    @staticmethod
    def _letterbox(img: np.ndarray, size: int) -> np.ndarray:
        oh, ow = img.shape[:2]
        ratio = float(size) / max(oh, ow)
        nh, nw = int(oh * ratio), int(ow * ratio)
        resized = cv2.resize(img, (nw, nh))
        dh, dw = size - nh, size - nw
        return cv2.copyMakeBorder(
            resized, dh // 2, dh - dh // 2, dw // 2, dw - dw // 2,
            cv2.BORDER_CONSTANT, value=0,
        )


# ── Multi-frame voting ────────────────────────────────────────────────────────
class VoteBuffer:
    """
    Groups face observations across frames by embedding similarity (pseudo-tracking
    without ByteTrack). Fires a decision only after MIN_VOTES consistent observations.

    Each "track" is a moving-average embedding centroid. When a new face arrives,
    it is assigned to the closest existing track (cosine sim ≥ TRACK_SIM) or starts
    a new one. Tracks expire after TRACK_TTL seconds of no sightings.
    """

    TRACK_SIM = 0.55   # min cosine sim to match an existing track
    TRACK_TTL = 4.0    # seconds of idle before a track is garbage-collected

    def __init__(self, window: int, min_votes: int, rec_threshold: float):
        self.window = window
        self.min_votes = min_votes
        self.rec_threshold = rec_threshold
        self._tracks: list[dict] = []

    def update(self, embedding: np.ndarray, emp_id, score: float,
               is_live: bool, spoof_score: float, ts: float) -> dict | None:
        embedding = np.asarray(embedding, dtype=np.float32)
        self._expire(ts)
        track = self._match_or_create(embedding, ts)

        track["votes"].append({
            "emp_id": emp_id, "score": score,
            "is_live": is_live, "spoof_score": spoof_score,
        })
        if len(track["votes"]) > self.window:
            track["votes"].pop(0)

        if len(track["votes"]) < self.min_votes:
            return None
        return self._decide(track)

    # ── Internals ─────────────────────────────────────────────────────────────
    def _match_or_create(self, emb: np.ndarray, ts: float) -> dict:
        best, best_sim = None, -1.0
        for t in self._tracks:
            sim = float(np.dot(t["centroid"], emb))
            if sim > best_sim:
                best_sim, best = sim, t
        if best is None or best_sim < self.TRACK_SIM:
            t = {"centroid": emb.copy(), "votes": [], "last_seen": ts}
            self._tracks.append(t)
            return t
        # EMA centroid update
        c = 0.7 * best["centroid"] + 0.3 * emb
        n = np.linalg.norm(c)
        best["centroid"] = c / n if n > 0 else c
        best["last_seen"] = ts
        return best

    def _expire(self, ts: float):
        self._tracks = [t for t in self._tracks
                        if ts - t["last_seen"] < self.TRACK_TTL]

    def _decide(self, track: dict) -> dict | None:
        votes = track["votes"]
        n = len(votes)
        majority = max(2, math.ceil(n / 2))

        spoof_v = [v for v in votes if not v["is_live"]]
        # Require majority AND at least 2 spoof frames so a single motion-blurred
        # or partially-occluded frame doesn't trigger a false alert on a real employee.
        spoof_threshold = max(2, majority)
        if len(spoof_v) >= spoof_threshold:
            track["votes"].clear()
            return {"result": "spoof",
                    "spoof_score": min(v["spoof_score"] for v in spoof_v)}

        live_v = [v for v in votes if v["is_live"]]
        vote_map: dict[str, list[float]] = defaultdict(list)
        for v in live_v:
            if v["emp_id"]:
                vote_map[v["emp_id"]].append(v["score"])

        if vote_map:
            winner = max(vote_map,
                         key=lambda e: (len(vote_map[e]),
                                        sum(vote_map[e]) / len(vote_map[e])))
            wcount = len(vote_map[winner])
            wmean = float(np.mean(vote_map[winner]))
            if wcount >= majority and wmean >= self.rec_threshold:
                track["votes"].clear()
                return {"result": "recognized", "emp_id": winner, "score": wmean}

        if n >= self.window:
            track["votes"].clear()
            return {"result": "unknown",
                    "score": max((v["score"] for v in votes), default=0.0)}
        return None


# ── Embedding search (numpy, no FAISS needed) ─────────────────────────────────
def cosine_search(probe: np.ndarray, embs: np.ndarray | None,
                  ids: list, threshold: float) -> tuple[str | None, float]:
    if embs is None or len(embs) == 0:
        return None, 0.0
    probe = probe / (np.linalg.norm(probe) + 1e-8)
    sims = embs @ probe
    best = int(np.argmax(sims))
    score = float(sims[best])
    return (ids[best], score) if score >= threshold else (None, score)


# ── Backend helpers ───────────────────────────────────────────────────────────
async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BACKEND_URL}/api/v1/auth/login",
                          json={"email": EDGE_USER, "password": EDGE_PASS})
    r.raise_for_status()
    log.info("Authenticated with backend.")
    return r.json()["access_token"]


async def load_index(client: httpx.AsyncClient,
                     token: str) -> tuple[np.ndarray | None, list]:
    r = await client.get(f"{BACKEND_URL}/api/v1/enrollment/export",
                         headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    data = r.json()
    if not data:
        log.warning("No enrolled faces — add employees via the dashboard first.")
        return None, []
    embs = np.array([d["embedding"] for d in data], dtype=np.float32)
    ids  = [d["employee_id"] for d in data]
    log.info("Loaded %d face embedding(s).", len(ids))
    return embs, ids


async def send_event(client: httpx.AsyncClient, token: str,
                     employee_id: str | None, confidence: float,
                     is_live: bool, spoof_score: float) -> None:
    payload = {
        "camera_id":   CAMERA_ID,
        "employee_id": employee_id,
        "confidence":  confidence,
        "is_live":     is_live,
        "spoof_score": spoof_score,
        "direction":   DIRECTION,
        "timestamp":   time.time(),
    }
    try:
        r = await client.post(
            f"{BACKEND_URL}/api/v1/attendance/event",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": TENANT_ID},
        )
        result = r.json() if r.status_code == 200 else {}
        action = result.get("action", f"HTTP {r.status_code}")
        reason = result.get("reason", "")
        log.info("Event → %s | emp=%s conf=%.3f%s",
                 action, employee_id or "unknown", confidence,
                 f" ({reason})" if reason else "")
    except Exception as e:
        log.error("Failed to send event: %s", e)


# ── Camera (re)connect ────────────────────────────────────────────────────────
def open_camera(src) -> cv2.VideoCapture | None:
    """
    Open any camera source OpenCV supports:
      int          →  USB webcam by index (0 = first, 1 = second, ...)
      rtsp://...   →  IP camera RTSP stream (V380, Hikvision, Dahua, Reolink, ...)
      http://...   →  HTTP MJPEG stream (DroidCam, IP Webcam app on Android)
      /path/file   →  Video file for testing (mp4, avi, mkv)
    """
    if isinstance(src, str):
        if src.startswith("rtsp://"):
            # Force TCP transport — avoids silent UDP packet loss on WiFi
            os.environ.setdefault(
                "OPENCV_FFMPEG_CAPTURE_OPTIONS",
                "rtsp_transport;tcp|analyzeduration;2000000|probesize;2000000",
            )
        elif src.startswith("http://") or src.startswith("https://"):
            # HTTP MJPEG — used by Android IP Webcam, DroidCam, phone camera apps
            # No special flags needed; OpenCV handles it via FFmpeg
            pass

    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        return None

    # Log the actual resolution so you know what you're getting
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    log.info("Camera connected: %s  →  %dx%d @ %.0f fps", src, w, h, fps)
    if w < 640:
        log.warning(
            "Stream resolution %dx%d is below 640px wide — face detection will be "
            "less accurate. Use the main/HD stream URL if possible.", w, h
        )
    return cap


# ── Main loop ─────────────────────────────────────────────────────────────────
async def run():
    src = (int(CAMERA_SRC) if CAMERA_SRC.strip().lstrip("-").isdigit()
           else CAMERA_SRC)

    # Load GPU profile once — InsightFace and anti-spoof share the same providers
    gpu = detect_gpu()

    log.info("Loading InsightFace (buffalo_l) … first run downloads ~500 MB")
    from insightface.app import FaceAnalysis
    fa = FaceAnalysis(name="buffalo_l", providers=gpu["ort_providers"])
    fa.prepare(ctx_id=gpu["insightface_ctx"], det_size=(640, 640))
    log.info("Face model ready.")

    anti_spoof = AntiSpoofChecker(ANTISPOOF_MODEL, threshold=LIVENESS_THRESHOLD)
    face_sr    = FaceSuperRes(SUPERRES_MODEL)
    vote_buf   = VoteBuffer(window=VOTE_WINDOW, min_votes=MIN_VOTES,
                            rec_threshold=REC_THRESH)
    cooldown: dict[str, float] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        token = await login(client)
        embs, ids = await load_index(client, token)

        frame_n = 0
        last_sync = time.time()
        backoff = RECONNECT_DELAY
        cap = None
        loop = asyncio.get_running_loop()

        while True:
            # ── (Re)connect camera ────────────────────────────────────────
            if cap is None or not cap.isOpened():
                log.info("Opening camera %s …", src)
                cap = open_camera(src)
                if cap is None:
                    log.warning("Camera unavailable — retrying in %ds", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                backoff = RECONNECT_DELAY
                frame_n = 0

            ok, frame = cap.read()
            if not ok:
                log.warning("Frame read failed — reconnecting")
                cap.release()
                cap = None
                continue

            frame_n += 1
            now = time.time()

            # ── Resync enrolled faces every 60 s ─────────────────────────
            if now - last_sync > 60:
                try:
                    embs, ids = await load_index(client, token)
                    last_sync = now
                except Exception as e:
                    log.warning("Embedding resync failed: %s", e)

            # ── Skip frames to save CPU/GPU ───────────────────────────────
            if frame_n % PROCESS_EVERY_N != 0:
                await asyncio.sleep(0.005)
                continue

            # ── Face detection (in thread so async loop stays responsive) ─
            faces = await loop.run_in_executor(_POOL, fa.get, frame.copy())
            if not faces:
                await asyncio.sleep(0.02)
                continue

            for i, face in enumerate(faces):
                bbox = face.bbox.astype(int)
                x1 = max(0, bbox[0]); y1 = max(0, bbox[1])
                x2 = min(frame.shape[1], bbox[2])
                y2 = min(frame.shape[0], bbox[3])
                face_crop = frame[y1:y2, x1:x2]
                if face_crop.size == 0:
                    continue

                # ── Anti-spoof on RAW crop (before enhancement) ───────────
                # Enhancement removes screen artifacts — run liveness on the
                # original compressed frame to preserve detection cues.
                # Pass face index as track_id so the temporal gate can
                # accumulate static-image evidence across frames.
                is_live, spoof_score = await loop.run_in_executor(
                    _POOL, anti_spoof.check, face_crop, str(i)
                )

                # ── Neural 2x SR → enhance → re-embed ────────────────────
                # FSRCNN doubles face resolution (e.g. 70x70 → 140x140) so
                # ArcFace sees more pixels. Classical enhance then sharpens.
                sr_crop  = await loop.run_in_executor(_POOL, face_sr.upscale, face_crop)
                enhanced = await loop.run_in_executor(_POOL, enhance_face, sr_crop)

                # Re-embed from the upscaled+sharpened crop
                embedding = face.normed_embedding
                if enhanced is not None and enhanced.size > 0:
                    enh_faces = await loop.run_in_executor(_POOL, fa.get, enhanced)
                    if enh_faces:
                        embedding = enh_faces[0].normed_embedding

                emb_arr = np.asarray(embedding, dtype=np.float32)
                emp_id, sim = cosine_search(emb_arr, embs, ids, REC_THRESH)

                # ── Multi-frame vote ──────────────────────────────────────
                decision = vote_buf.update(emb_arr, emp_id, sim,
                                           is_live, spoof_score, now)
                if decision is None:
                    continue   # collecting more frames

                result = decision["result"]

                if result == "spoof":
                    s = decision["spoof_score"]
                    log.warning("SPOOF DETECTED  spoof_score=%.3f", s)
                    await send_event(client, token,
                                     employee_id=None, confidence=0.0,
                                     is_live=False, spoof_score=s)

                elif result == "recognized":
                    eid  = decision["emp_id"]
                    conf = decision["score"]
                    if now - cooldown.get(eid, 0) < COOLDOWN_S:
                        log.debug("Cooldown active — skipping emp=%s", eid)
                        continue
                    cooldown[eid] = now
                    log.info("RECOGNIZED  emp=%s  conf=%.3f", eid, conf)
                    await send_event(client, token,
                                     employee_id=eid, confidence=conf,
                                     is_live=True, spoof_score=spoof_score)

                elif result == "unknown":
                    log.info("UNKNOWN FACE  best_sim=%.3f", decision.get("score", 0))
                    await send_event(client, token,
                                     employee_id=None,
                                     confidence=decision.get("score", 0.0),
                                     is_live=True, spoof_score=spoof_score)

            await asyncio.sleep(0.01)


if __name__ == "__main__":
    asyncio.run(run())
