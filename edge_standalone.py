"""
Standalone edge node — runs directly on Windows (no Docker needed).

Requirements (run once):
    pip install insightface onnxruntime opencv-python numpy httpx pyyaml ultralytics

Usage:
    python edge_standalone.py

Camera source (edit below or set env vars):
    CAMERA_SRC   = 0          (webcam index)  or  rtsp://user:pass@IP:554/...
    BACKEND_URL  = http://localhost:8000
    EDGE_USER    = admin@demo.com
    EDGE_PASS    = admin123
    TENANT_ID    = demo
"""
import asyncio
import os
import sys
import time
import logging
import cv2
import numpy as np
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("edge")

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_SRC   = os.getenv("CAMERA_SRC",   "0")          # "0" = webcam, or RTSP URL
BACKEND_URL  = os.getenv("BACKEND_URL",  "http://localhost:8000")
EDGE_USER    = os.getenv("EDGE_USER",    "admin@demo.com")
EDGE_PASS    = os.getenv("EDGE_PASS",    "admin123")
TENANT_ID    = os.getenv("TENANT_ID",   "demo")
REC_THRESH   = float(os.getenv("REC_THRESH",   "0.50"))   # similarity threshold
COOLDOWN_S   = int(os.getenv("COOLDOWN_S",     "10"))      # seconds between events


# ── Auth ──────────────────────────────────────────────────────────────────────
async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BACKEND_URL}/api/v1/auth/login",
                          json={"email": EDGE_USER, "password": EDGE_PASS})
    r.raise_for_status()
    token = r.json()["access_token"]
    log.info("Authenticated with backend.")
    return token


# ── Embedding sync ────────────────────────────────────────────────────────────
async def load_index(client: httpx.AsyncClient, token: str):
    r = await client.get(f"{BACKEND_URL}/api/v1/enrollment/export",
                         headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    data = r.json()
    if not data:
        log.warning("No enrolled faces. Enroll employees in the dashboard first.")
        return None, []
    embs = np.array([d["embedding"] for d in data], dtype=np.float32)
    ids  = [d["employee_id"] for d in data]
    log.info(f"Loaded {len(ids)} face embedding(s) into recognition index.")
    return embs, ids


def cosine_search(probe: np.ndarray, embs: np.ndarray, ids: list, threshold: float):
    """Simple numpy cosine similarity search (no FAISS needed)."""
    if embs is None or len(embs) == 0:
        return None, 0.0
    probe = probe / (np.linalg.norm(probe) + 1e-8)
    sims  = embs @ probe          # embs rows are already L2-normalised
    best  = int(np.argmax(sims))
    score = float(sims[best])
    if score >= threshold:
        return ids[best], score
    return None, score


# ── Attendance event ──────────────────────────────────────────────────────────
async def send_event(client: httpx.AsyncClient, token: str, employee_id: str,
                     camera_id: str, direction: str, confidence: float):
    payload = {
        "camera_id":   camera_id,
        "employee_id": employee_id,
        "confidence":  confidence,
        "is_live":     True,
        "spoof_score": 1.0,
        "direction":   direction,
        "timestamp":   time.time(),
    }
    try:
        r = await client.post(f"{BACKEND_URL}/api/v1/attendance/event",
                              json=payload,
                              headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            log.info(f"Attendance event sent → employee {employee_id} ({direction})")
        else:
            log.warning(f"Event rejected: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.error(f"Failed to send event: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────
async def run():
    # Determine camera source
    src = int(CAMERA_SRC) if CAMERA_SRC.strip().lstrip("-").isdigit() else CAMERA_SRC
    log.info(f"Opening camera: {src}")
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        log.error(f"Cannot open camera {src!r}. Check CAMERA_SRC.")
        sys.exit(1)
    log.info("Camera connected.")

    # Load InsightFace
    log.info("Loading InsightFace (buffalo_l)… first run downloads ~500 MB")
    from insightface.app import FaceAnalysis
    fa = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    fa.prepare(ctx_id=-1, det_size=(640, 640))
    log.info("Face model ready.")

    async with httpx.AsyncClient(timeout=15) as client:
        token = await login(client)
        embs, ids = await load_index(client, token)

        cooldown: dict[str, float] = {}
        frame_n = 0
        last_heartbeat = 0.0

        while True:
            ok, frame = cap.read()
            if not ok:
                log.warning("Frame read failed, retrying…")
                await asyncio.sleep(0.5)
                continue

            frame_n += 1
            now = time.time()

            # Heartbeat every 15 seconds
            if now - last_heartbeat > 15:
                log.info(f"Frame #{frame_n} | index_size={len(ids) if ids else 0}")
                last_heartbeat = now

            # Process every 3rd frame on CPU to keep up
            if frame_n % 3 != 0:
                await asyncio.sleep(0.01)
                continue

            faces = fa.get(frame)
            if not faces:
                await asyncio.sleep(0.05)
                continue

            log.info(f"Frame #{frame_n}: {len(faces)} face(s) detected")

            for face in faces:
                emb = np.array(face.normed_embedding, dtype=np.float32)
                emp_id, sim = cosine_search(emb, embs, ids, REC_THRESH)

                if emp_id is None:
                    if not ids:
                        log.warning("No enrolled employees — nothing to match against.")
                    else:
                        log.info(f"Unknown face (best_sim={sim:.3f}, threshold={REC_THRESH})")
                    continue

                # Cooldown per employee
                if now - cooldown.get(emp_id, 0) < COOLDOWN_S:
                    continue
                cooldown[emp_id] = now

                log.info(f"MATCH: employee={emp_id}  sim={sim:.3f}")
                await send_event(client, token, emp_id,
                                 camera_id="standalone-cam",
                                 direction="entrance",
                                 confidence=sim)

            await asyncio.sleep(0.01)


if __name__ == "__main__":
    asyncio.run(run())
