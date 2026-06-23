"""Orchestrates detection -> tracking -> face crop -> liveness -> embed -> search -> publish."""
import asyncio
import time
import os
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from ..detection.yolo_detector import YOLODetector
from ..recognition.arcface import ArcFaceRecognizer
from ..recognition.anti_spoof import AntiSpoofChecker
from ..recognition.faiss_search import FaissSearch
from ..utils.logger import get_logger

log = get_logger("pipeline")

# BGR annotation colours
_CLR_PERSON  = (0, 165, 255)   # orange  — person only, no face yet
_CLR_KNOWN   = (0, 200, 50)    # green   — recognised employee
_CLR_UNKNOWN = (0, 0, 220)     # red     — unknown face
_CLR_SPOOF   = (0, 0, 180)     # dark-red — spoof / liveness fail
_FONT        = cv2.FONT_HERSHEY_SIMPLEX

# All FrameProcessor instances share one worker thread: the detector/recognizer/
# anti_spoof/face_search model objects are shared across cameras and are not
# thread-safe, and a single worker keeps inference off the asyncio event loop
# (which also serves the MJPEG stream) without races between cameras.
_INFERENCE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")


class FrameProcessor:
    def __init__(self, camera_id: str, direction: str, config: dict,
                 detector: YOLODetector, recognizer: ArcFaceRecognizer,
                 anti_spoof: AntiSpoofChecker, face_search: FaissSearch,
                 publisher, snapshot_dir: str = "/app/snapshots",
                 mjpeg_server=None, id_to_name: dict | None = None):
        self.camera_id = camera_id
        self.direction = direction
        self.detector = detector
        self.recognizer = recognizer
        self.anti_spoof = anti_spoof
        self.face_search = face_search
        self.publisher = publisher
        self.snapshot_dir = snapshot_dir
        self.cooldown_s = config.get("cooldown_seconds", 300)
        self._cooldown: dict[int, float] = {}
        self._frame_count = 0
        self._last_log = 0.0
        self._mjpeg = mjpeg_server
        # Kept as the same dict object (not copied) so embedding_watch_loop's
        # in-place clear()+update() resync is visible here without re-wiring.
        self._id_to_name: dict[str, str] = id_to_name if id_to_name is not None else {}
        # Sticky per-track labels survive until the track is re-evaluated
        self._track_labels: dict[int, tuple[str, tuple]] = {}

    async def process(self, frame: np.ndarray, ts: float):
        """Runs detection/recognition off the event loop, then publishes results.

        The event loop also serves the MJPEG stream; running CPU-bound inference
        synchronously here would stall the stream for the duration of each frame.
        """
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(_INFERENCE_EXECUTOR, self._process_sync, frame, ts)
        for event in events:
            await self.publisher.publish(event)

    def _process_sync(self, frame: np.ndarray, ts: float) -> list[dict]:
        events: list[dict] = []
        self._frame_count += 1

        tracks = self.detector.track(frame)

        if ts - self._last_log > 30:
            log.info(
                f"[{self.camera_id}] alive — "
                f"frame #{self._frame_count} | "
                f"tracks={len(tracks)} | "
                f"faiss_size={self.face_search.index.ntotal if self.face_search.index else 0}"
            )
            self._last_log = ts

        confirmed = [t for t in tracks if t.is_confirmed() and not self._in_cooldown(t.track_id, ts)]

        if tracks and not confirmed:
            log.debug(f"[{self.camera_id}] {len(tracks)} track(s) found but all in cooldown or unconfirmed")

        for tr in confirmed:
            crop = self._crop(frame, tr.bbox)
            if crop.size == 0:
                continue

            faces = self.recognizer.detect_and_embed(crop)
            if not faces:
                log.info(
                    f"[{self.camera_id}] person track={tr.track_id} conf={tr.confidence:.2f} "
                    f"— no face detected in crop (person may be turned away or too small)"
                )
                continue

            bbox, embedding, det_score = faces[0]
            log.info(
                f"[{self.camera_id}] face detected track={tr.track_id} "
                f"det_score={det_score:.3f} — running liveness check"
            )

            face_img = self._crop(crop, bbox)
            is_live, spoof_score = self.anti_spoof.check(face_img)
            if not is_live:
                log.warning(
                    f"[{self.camera_id}] SPOOF detected track={tr.track_id} "
                    f"spoof_score={spoof_score:.3f}"
                )
                self._track_labels[tr.track_id] = ("SPOOF", _CLR_SPOOF)
                snap = self._save_snapshot(face_img, None, ts, is_unknown=True)
                events.append({
                    "type": "spoof_attempt", "camera_id": self.camera_id,
                    "track_id": tr.track_id, "timestamp": ts,
                    "snapshot_url": snap, "is_live": False,
                    "spoof_score": spoof_score, "employee_id": None, "confidence": 0,
                })
                continue

            emp_id, sim = self.face_search.search(np.asarray(embedding))

            if emp_id is None:
                if self.face_search.index is None or self.face_search.index.ntotal == 0:
                    log.warning(
                        f"[{self.camera_id}] face found but FAISS index is EMPTY — "
                        f"enroll employees first, then restart the edge node."
                    )
                else:
                    log.info(
                        f"[{self.camera_id}] face found, no match "
                        f"(best_sim={sim:.3f}, threshold={self.face_search.threshold}) "
                        f"— unknown person"
                    )
                self._track_labels[tr.track_id] = ("Unknown", _CLR_UNKNOWN)
                snap = self._save_snapshot(face_img, emp_id, ts, is_unknown=True)
                events.append({
                    "type": "unknown_person", "camera_id": self.camera_id,
                    "direction": self.direction, "track_id": tr.track_id,
                    "employee_id": None, "confidence": round(sim, 4),
                    "is_live": True, "spoof_score": round(spoof_score, 4),
                    "timestamp": ts,
                })
                continue

            name = self._id_to_name.get(str(emp_id), str(emp_id)[:8])
            log.info(
                f"[{self.camera_id}] RECOGNIZED {name} (emp={emp_id}) "
                f"sim={sim:.3f} det_score={det_score:.3f}"
            )
            self._track_labels[tr.track_id] = (f"{name}", _CLR_KNOWN)
            snap = self._save_snapshot(face_img, emp_id, ts)
            events.append({
                "type": "recognition", "camera_id": self.camera_id,
                "direction": self.direction, "track_id": tr.track_id,
                "employee_id": emp_id, "confidence": round(sim, 4),
                "is_live": True, "spoof_score": round(spoof_score, 4),
                "embedding_dist": round(1 - sim, 5), "snapshot_url": snap,
                "timestamp": ts,
            })
            self._cooldown[tr.track_id] = ts

        # ── Push annotated frame to MJPEG server ─────────────────────────
        if self._mjpeg is not None:
            annotated = self._draw_overlays(frame.copy(), tracks)
            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 72])
            self._mjpeg.put_frame(self.camera_id, jpeg.tobytes())

        return events

    # ── Helpers ──────────────────────────────────────────────────────────

    def _draw_overlays(self, frame: np.ndarray, tracks) -> np.ndarray:
        for tr in tracks:
            x1, y1, x2, y2 = map(int, tr.bbox)
            label, color = self._track_labels.get(tr.track_id, (f"#{tr.track_id}", _CLR_PERSON))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, _FONT, 0.6, 2)
            cv2.rectangle(frame, (x1, max(y1 - th - 10, 0)), (x1 + tw + 6, y1), color, -1)
            cv2.putText(frame, label, (x1 + 3, max(y1 - 4, th + 4)),
                        _FONT, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        return frame

    def _in_cooldown(self, tid: int, ts: float) -> bool:
        return (ts - self._cooldown.get(tid, 0)) < self.cooldown_s

    @staticmethod
    def _crop(img, bbox):
        x1, y1, x2, y2 = map(int, bbox)
        h, w = img.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        return img[y1:y2, x1:x2]

    def _save_snapshot(self, face_img, emp_id, ts, is_unknown: bool = False) -> str:
        if is_unknown:
            d = os.path.join(self.snapshot_dir, "unknown")
        else:
            d = os.path.join(self.snapshot_dir, str(emp_id))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{int(ts)}.jpg")
        try:
            cv2.imwrite(path, face_img)
        except Exception:
            pass
        return path
