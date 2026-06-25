"""Orchestrates detection -> tracking -> face crop -> liveness -> embed -> search -> publish.

Recognition is decided by MULTI-FRAME VOTING, not single frames. ArcFace similarity
for the same person varies frame-to-frame (e.g. 0.35–0.58 depending on pose/blur),
so deciding on one frame causes flip-flopping between "recognized" and "unknown".
Instead we accumulate good-quality observations per track and decide once we have
enough evidence:
  - face-quality gate: ignore frames whose face det_score is too low (junk embeddings)
  - per-track buffer of (employee, score, liveness) over a sliding window
  - decide when the buffer is full enough: the employee that wins the majority of
    frames AND whose mean similarity clears the threshold is recognized; persistent
    spoof frames fire a spoof alert; otherwise the person is logged as unknown.
"""
import asyncio
import time
import os
import math
import cv2
import numpy as np
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from ..detection.yolo_detector import YOLODetector
from ..recognition.arcface import ArcFaceRecognizer
from ..recognition.anti_spoof import AntiSpoofChecker
from ..recognition.mask_detector import MaskDetector
from ..recognition.faiss_search import FaissSearch
from ..utils.logger import get_logger
from ..utils.superres import FaceSuperRes

log = get_logger("pipeline")

# BGR annotation colours
_CLR_PERSON  = (0, 165, 255)   # orange  — person only, no face yet
_CLR_KNOWN   = (0, 200, 50)    # green   — recognised employee
_CLR_UNKNOWN = (0, 0, 220)     # red     — unknown face
_CLR_SPOOF   = (0, 0, 180)     # dark-red — spoof / liveness fail
_CLR_MASKED  = (0, 220, 220)   # yellow  — face mask detected
_FONT        = cv2.FONT_HERSHEY_SIMPLEX

_INFERENCE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")


def _enhance_face(face_img: np.ndarray) -> np.ndarray:
    """Sharpen + denoise a face crop to recover texture lost to H.264/H.265
    compression on budget cameras (V380, HiVideo, etc.).

    Pipeline:
      1. Mild bilateral denoise  — smooths compression block noise while
         preserving edges (skin/hair boundaries).
      2. Unsharp mask            — restores fine texture (pores, eyebrows)
         that heavy quantisation blurs away.
      3. CLAHE on luminance      — normalises patchy exposure from poor
         camera sensors / indoor lighting.

    Adds ~2–4 ms per face on GPU host. Can be disabled via
    `enhance_faces: false` in camera_config.yaml.
    """
    if face_img is None or face_img.size == 0:
        return face_img

    # Resize to a fixed input size so processing cost is predictable
    h, w = face_img.shape[:2]
    if h < 32 or w < 32:
        return face_img  # too small to enhance meaningfully

    work = cv2.resize(face_img, (128, 128)) if min(h, w) < 128 else face_img.copy()

    # 1. Bilateral denoise: removes block artifacts, keeps edges
    work = cv2.bilateralFilter(work, d=5, sigmaColor=30, sigmaSpace=5)

    # 2. Unsharp mask: amount=1.0, threshold=0
    blurred = cv2.GaussianBlur(work, (0, 0), sigmaX=1.5)
    work = cv2.addWeighted(work, 1.8, blurred, -0.8, 0)
    work = np.clip(work, 0, 255).astype(np.uint8)

    # 3. CLAHE on L channel only (avoids colour shifts)
    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    l = clahe.apply(l)
    work = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

    return cv2.resize(work, (w, h)) if min(h, w) < 128 else work


class FrameProcessor:
    def __init__(self, camera_id: str, direction: str, config: dict,
                 detector: YOLODetector, recognizer: ArcFaceRecognizer,
                 anti_spoof: AntiSpoofChecker, face_search: FaissSearch,
                 publisher, snapshot_dir: str = "/app/snapshots",
                 mjpeg_server=None, id_to_name: dict | None = None,
                 mask_detector: MaskDetector | None = None):
        self.camera_id = camera_id
        self.direction = direction
        self.detector = detector
        self.recognizer = recognizer
        self.anti_spoof = anti_spoof
        self.mask_detector = mask_detector or MaskDetector()
        self.face_search = face_search
        self.publisher = publisher
        self.snapshot_dir = snapshot_dir
        self.cooldown_s = config.get("cooldown_seconds", 300)
        # Minimum det_score to still attempt mask detection on a low-confidence face.
        # Faces above min_det_score go through normal recognition; faces between
        # mask_det_min and min_det_score are only checked for mask/covering.
        self.mask_det_min = float(config.get("mask_det_min", 0.25))
        # Separate, shorter cooldown for mask alerts so repeated alerts are suppressed
        # but a fresh alert fires again within a reasonable window (default 60 s).
        self.mask_cooldown_s = float(config.get("mask_cooldown_seconds", 60))

        # ── Voting / quality parameters (all tunable via camera_config.yaml) ──
        self.min_det_score  = float(config.get("min_det_score", 0.50))
        self.enhance_faces  = bool(config.get("enhance_faces", True))
        self.vote_window   = int(config.get("vote_window", 7))
        _sr_model = config.get("superres_model", "edge/weights/FSRCNN_x2.pb")
        self._face_sr = FaceSuperRes(_sr_model) if config.get("superres", True) else None
        self.min_votes     = int(config.get("min_votes", 4))
        self.obs_ttl_s     = float(config.get("vote_ttl_seconds", 5))

        self._busy = False  # drop-if-busy gate — prevents executor queue buildup
        self._cooldown: dict[int, float] = {}
        self._mask_cooldown: dict[int, float] = {}
        self._track_obs: dict[int, list[dict]] = {}
        self._frame_count = 0
        self._last_log = 0.0
        self._mjpeg = mjpeg_server
        self._id_to_name: dict[str, str] = id_to_name if id_to_name is not None else {}
        self._track_labels: dict[int, tuple[str, tuple]] = {}
        # Tracks whose last fired event was a spoof — keeps the SPOOF overlay
        # visible during cooldown instead of flipping to the employee's name.
        self._spoof_tracks: set[int] = set()
        # Last time each track id was seen, for garbage-collecting per-track state.
        # ByteTrack ids are monotonic and never reused, so once a track is gone
        # all of its state (obs buffer, label, cooldown) can be dropped.
        self._track_seen: dict[int, float] = {}
        self._gc_ttl_s = max(8.0, float(config.get("vote_ttl_seconds", 3)) * 3)

    async def process(self, frame: np.ndarray, ts: float):
        # Drop frame if previous inference is still running.
        # Without this, frames queue up in the executor and cause accumulating delay.
        if self._busy:
            return
        self._busy = True
        try:
            loop = asyncio.get_running_loop()
            events = await loop.run_in_executor(_INFERENCE_EXECUTOR, self._process_sync, frame, ts)
            for event in events:
                await self.publisher.publish(event)
        finally:
            self._busy = False

    def _process_sync(self, frame: np.ndarray, ts: float) -> list[dict]:
        events: list[dict] = []
        self._frame_count += 1

        tracks = self.detector.track(frame)
        for t in tracks:
            self._track_seen[t.track_id] = ts

        if ts - self._last_log > 30:
            log.info(
                f"[{self.camera_id}] alive — frame #{self._frame_count} | "
                f"tracks={len(tracks)} | "
                f"faiss_size={self.face_search.index.ntotal if self.face_search.index else 0}"
            )
            self._last_log = ts

        self._prune_stale(ts)

        # All confirmed tracks run recognition for live display.
        # Cooldown only blocks attendance event recording — not label updates.
        confirmed = [t for t in tracks if t.is_confirmed()]

        for tr in confirmed:
            in_cooldown = self._in_cooldown(tr.track_id, ts)
            crop = self._crop_padded(frame, tr.bbox, pad=0.30)
            if crop.size == 0:
                continue

            faces = self.recognizer.detect_and_embed(crop)
            if not faces:
                continue

            # Pick the highest-quality face in the crop
            bbox, embedding, det_score = max(faces, key=lambda f: f[2])

            face_img = self._crop(crop, bbox)

            # ── Face-quality gate: skip junk crops that yield garbage embeddings ──
            # Low-confidence detections (mask_det_min ≤ score < min_det_score) still
            # get a mask check — a face mask causes exactly this kind of score drop.
            if det_score < self.min_det_score:
                if det_score >= self.mask_det_min and face_img.size > 0:
                    is_masked, mask_conf = self.mask_detector.check(face_img)
                    if is_masked:
                        self._handle_masked(tr.track_id, face_img, mask_conf, ts, events)
                continue

            # ── Budget-camera face enhancement + neural SR ────────────────────
            # Pipeline: FSRCNN 2x SR → bilateral denoise → unsharp → CLAHE.
            # SR doubles the face crop resolution (e.g. 80x80 → 160x160) so
            # ArcFace operates on more pixels. Enhancement then recovers texture
            # lost to H.264 compression. Together: +10-25% similarity on V380.
            if self.enhance_faces and face_img.size > 0:
                # 1. Neural 2x upscale (FSRCNN) — adds real detail, not just bigger pixels
                sr_face = self._face_sr.upscale(face_img) if self._face_sr else face_img
                # 2. Classical enhancement on the upscaled crop
                enhanced = _enhance_face(sr_face)
                # Re-embed from the upscaled+sharpened crop
                reembed = self.recognizer.detect_and_embed(enhanced)
                if reembed:
                    _, embedding, _ = max(reembed, key=lambda f: f[2])

            # ── Mask check (runs even on quality-passing faces to catch partial masks) ──
            is_masked, mask_conf = self.mask_detector.check(face_img)
            if is_masked:
                self._handle_masked(tr.track_id, face_img, mask_conf, ts, events)
                continue

            is_live, spoof_score = self.anti_spoof.check(crop, bbox, track_id=tr.track_id)
            emp_id, score = self.face_search.search_raw(np.asarray(embedding))

            obs = {
                "emp_id": emp_id, "score": float(score),
                "is_live": bool(is_live), "spoof_score": float(spoof_score),
                "det_score": float(det_score), "face_img": face_img, "ts": ts,
            }
            buf = self._track_obs.setdefault(tr.track_id, [])

            # Clear stale label when a fresh observation window starts so a
            # new face doesn't inherit the previous person's name.
            if len(buf) == 0:
                self._track_labels.pop(tr.track_id, None)

            buf.append(obs)
            if len(buf) > self.vote_window:
                buf.pop(0)

            # Always update provisional label — even during cooldown — so the
            # MJPEG overlay reflects whoever is actually in front of the camera.
            self._provisional_label(tr.track_id, obs)

            if in_cooldown:
                # Still collecting for display; skip attendance event.
                continue

            if len(buf) >= self.min_votes:
                ev = self._decide(tr.track_id, buf, ts)
                if ev is not None:
                    events.append(ev)
                    self._cooldown[tr.track_id] = ts
                    self._track_obs.pop(tr.track_id, None)
                    if ev["type"] == "spoof_attempt":
                        self._spoof_tracks.add(tr.track_id)
                    else:
                        self._spoof_tracks.discard(tr.track_id)

        if self._mjpeg is not None:
            # Resize to 720p before encoding — 1080p JPEG encode costs ~80ms on CPU,
            # 720p costs ~35ms, 640p costs ~15ms. Inference thread must not be blocked
            # by encoding. Preview quality at 720p is still sharp on any dashboard screen.
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                preview = cv2.resize(frame, (1280, int(h * scale)),
                                     interpolation=cv2.INTER_LINEAR)
            else:
                preview = frame
                scale = 1.0
            annotated = self._draw_overlays(preview, tracks, bbox_scale=scale)
            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 60])
            self._mjpeg.put_frame(self.camera_id, jpeg.tobytes())

        return events

    # ── Decision engine ───────────────────────────────────────────────────
    def _decide(self, track_id: int, buf: list[dict], ts: float):
        n = len(buf)
        majority = max(2, math.ceil(n / 2))
        threshold = self.face_search.threshold

        # 1) Spoof — fire if liveness fails in 25% or more of frames.
        # Phone/tablet replays often pass the liveness check on a few frames
        # (perspective shift, glare) but consistently fail on the rest.
        # ceil(n/4) is more aggressive than the old (majority-1): at n=7 this
        # requires only 2 spoof frames instead of 3.
        spoof_threshold = max(1, math.ceil(n / 4))
        spoof_obs = [o for o in buf if not o["is_live"]]
        if len(spoof_obs) >= spoof_threshold:
            rep = min(spoof_obs, key=lambda o: o["spoof_score"])
            log.warning(f"[{self.camera_id}] SPOOF confirmed track={track_id} "
                        f"({len(spoof_obs)}/{n} frames, score={rep['spoof_score']:.3f})")
            self._track_labels[track_id] = ("SPOOF", _CLR_SPOOF)
            snap = self._save_snapshot(rep["face_img"], None, ts, is_unknown=True)
            return {
                "type": "spoof_attempt", "camera_id": self.camera_id,
                "track_id": track_id, "timestamp": ts, "snapshot_url": snap,
                "is_live": False, "spoof_score": rep["spoof_score"],
                "employee_id": None, "confidence": 0,
            }

        # 2) Recognition — vote among live frames
        live = [o for o in buf if o["is_live"]]
        votes: dict[str, list[float]] = defaultdict(list)
        for o in live:
            if o["emp_id"] is not None:
                votes[o["emp_id"]].append(o["score"])

        if votes:
            winner = max(votes, key=lambda e: (len(votes[e]), sum(votes[e]) / len(votes[e])))
            wcount = len(votes[winner])
            wmean = float(np.mean(votes[winner]))
            if wcount >= majority and wmean >= threshold:
                name = self._id_to_name.get(str(winner), str(winner)[:8])
                best = max((o for o in live if o["emp_id"] == winner), key=lambda o: o["score"])
                log.info(f"[{self.camera_id}] RECOGNIZED {name} (emp={winner}) "
                         f"votes={wcount}/{n} mean_sim={wmean:.3f}")
                self._track_labels[track_id] = (name, _CLR_KNOWN)
                snap = self._save_snapshot(best["face_img"], winner, ts)
                return {
                    "type": "recognition", "camera_id": self.camera_id,
                    "direction": self.direction, "track_id": track_id,
                    "employee_id": winner, "confidence": round(wmean, 4),
                    "is_live": True, "spoof_score": round(best["spoof_score"], 4),
                    "embedding_dist": round(1 - wmean, 5), "snapshot_url": snap,
                    "timestamp": ts,
                }
            # Not enough agreement yet — keep collecting unless the window is full
            if n < self.vote_window:
                return None

        # 3) Unknown — window full (or no candidates) and nobody won
        if n < self.vote_window:
            return None
        best = max(buf, key=lambda o: o["score"])
        if self.face_search.index is None or self.face_search.index.ntotal == 0:
            log.warning(f"[{self.camera_id}] face seen but FAISS index EMPTY — enroll employees first.")
        else:
            log.info(f"[{self.camera_id}] UNKNOWN confirmed track={track_id} "
                     f"(best_sim={best['score']:.3f}, threshold={threshold})")
        self._track_labels[track_id] = ("Unknown", _CLR_UNKNOWN)
        snap = self._save_snapshot(best["face_img"], None, ts, is_unknown=True)
        return {
            "type": "unknown_person", "camera_id": self.camera_id,
            "direction": self.direction, "track_id": track_id,
            "employee_id": None, "confidence": round(best["score"], 4),
            "is_live": True, "spoof_score": round(best["spoof_score"], 4),
            "snapshot_url": snap, "timestamp": ts,
        }

    # ── Helpers ──────────────────────────────────────────────────────────
    def _provisional_label(self, track_id: int, obs: dict):
        """Update the MJPEG overlay label immediately from the latest observation.
        Called on every frame — including cooldown frames — so the display always
        reflects the current face, not a cached result from a previous person.
        """
        if not obs["is_live"]:
            self._track_labels[track_id] = ("SPOOF", _CLR_SPOOF)
        elif track_id in self._spoof_tracks and self._in_cooldown(track_id, obs["ts"]):
            # A spoof event was fired for this track and we are still in the cooldown
            # window.  Keep SPOOF on screen so the overlay doesn't immediately flip to
            # the employee name while the attacker holds the phone up.
            self._track_labels[track_id] = ("SPOOF", _CLR_SPOOF)
        elif obs["emp_id"] is not None and obs["score"] >= self.face_search.threshold:
            name = self._id_to_name.get(str(obs["emp_id"]), str(obs["emp_id"])[:8])
            # Green = confident match above threshold
            self._track_labels[track_id] = (name, _CLR_KNOWN)
        else:
            # Orange = person detected but not yet matched
            self._track_labels[track_id] = ("scanning…", _CLR_PERSON)

    def _prune_stale(self, ts: float):
        """Garbage-collect all per-track state once a track is gone.

        Vote buffers are dropped quickly (obs_ttl_s) so a person who pauses then
        re-approaches starts a fresh decision. Labels and cooldowns are kept a bit
        longer (gc_ttl_s) so the overlay stays stable across brief occlusions, then
        fully reclaimed. ByteTrack ids never repeat, so nothing here is ever needed
        again once the track disappears.
        """
        for tid in list(self._track_obs.keys()):
            buf = self._track_obs[tid]
            if buf and (ts - buf[-1]["ts"]) > self.obs_ttl_s:
                self._track_obs.pop(tid, None)

        for tid in list(self._track_seen.keys()):
            if (ts - self._track_seen[tid]) > self._gc_ttl_s:
                self._track_seen.pop(tid, None)
                self._track_labels.pop(tid, None)
                self._cooldown.pop(tid, None)
                self._track_obs.pop(tid, None)
                self._spoof_tracks.discard(tid)
                self._mask_cooldown.pop(tid, None)
                self.anti_spoof.clear_track(tid)

    def _draw_overlays(self, frame: np.ndarray, tracks,
                       bbox_scale: float = 1.0) -> np.ndarray:
        for tr in tracks:
            x1, y1, x2, y2 = (int(v * bbox_scale) for v in tr.bbox)
            label, color = self._track_labels.get(tr.track_id, (f"#{tr.track_id}", _CLR_PERSON))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, _FONT, 0.6, 2)
            cv2.rectangle(frame, (x1, max(y1 - th - 10, 0)), (x1 + tw + 6, y1), color, -1)
            cv2.putText(frame, label, (x1 + 3, max(y1 - 4, th + 4)),
                        _FONT, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        return frame

    def _in_cooldown(self, tid: int, ts: float) -> bool:
        return (ts - self._cooldown.get(tid, 0)) < self.cooldown_s

    def _in_mask_cooldown(self, tid: int, ts: float) -> bool:
        return (ts - self._mask_cooldown.get(tid, 0)) < self.mask_cooldown_s

    def _handle_masked(self, track_id: int, face_img: np.ndarray,
                       mask_conf: float, ts: float, events: list) -> None:
        """Update overlay and optionally fire a masked_face event."""
        self._track_labels[track_id] = ("MASKED", _CLR_MASKED)
        if self._in_mask_cooldown(track_id, ts):
            return
        self._mask_cooldown[track_id] = ts
        snap = self._save_snapshot(face_img, None, ts, is_unknown=True)
        log.info(
            f"[{self.camera_id}] MASK detected track={track_id} "
            f"conf={mask_conf:.3f}"
        )
        events.append({
            "type": "masked_face",
            "camera_id": self.camera_id,
            "direction": self.direction,
            "track_id": track_id,
            "mask_confidence": round(mask_conf, 4),
            "employee_id": None,
            "snapshot_url": snap,
            "timestamp": ts,
        })

    @staticmethod
    def _crop(img, bbox):
        x1, y1, x2, y2 = map(int, bbox)
        h, w = img.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        return img[y1:y2, x1:x2]

    @staticmethod
    def _crop_padded(img, bbox, pad: float = 0.30):
        """Crop with percentage padding so the full head is always included."""
        x1, y1, x2, y2 = map(int, bbox)
        bw, bh = x2 - x1, y2 - y1
        px, py = int(bw * pad), int(bh * pad)
        h, w = img.shape[:2]
        x1 = max(0, x1 - px)
        y1 = max(0, y1 - py)
        x2 = min(w, x2 + px)
        y2 = min(h, y2 + py)
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
