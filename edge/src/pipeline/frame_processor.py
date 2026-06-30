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
from ..detection.yolo_detector import YOLODetector, Track
from ..recognition.arcface import ArcFaceRecognizer
from ..recognition.anti_spoof import AntiSpoofChecker
from ..recognition.mask_detector import MaskDetector
from ..recognition.faiss_search import FaissSearch
from ..recognition.mediapipe_align import MediaPipeFaceAligner
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
# One worker per camera so multiple cameras can encode frames concurrently.
# max_workers=4 covers up to 4 cameras; extra cameras share the last slot.
_MJPEG_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mjpeg-encode")


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

    h, w = face_img.shape[:2]
    if h < 32 or w < 32:
        return face_img  # too small to enhance meaningfully

    # Upscale to at least 640 px on the short side (1080P source gives larger
    # raw crops so we can afford a higher target without excessive stretching).
    _TARGET = 640
    if min(h, w) < _TARGET:
        scale = _TARGET / min(h, w)
        work = cv2.resize(face_img, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_LANCZOS4)
    else:
        work = face_img.copy()

    # 1. Mild bilateral denoise — lighter pass so it doesn't smooth texture
    work = cv2.bilateralFilter(work, d=3, sigmaColor=20, sigmaSpace=3)

    # 2. Unsharp mask
    blurred = cv2.GaussianBlur(work, (0, 0), sigmaX=1.2)
    work = cv2.addWeighted(work, 1.8, blurred, -0.8, 0)
    work = np.clip(work, 0, 255).astype(np.uint8)

    # 3. CLAHE on L channel only (avoids colour shifts)
    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    l = clahe.apply(l)
    work = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

    # Return at the upscaled size — caller gets a larger image, not a sharpened
    # copy at the original tiny size.
    return work


class FrameProcessor:
    def __init__(self, camera_id: str, direction: str, config: dict,
                 detector: YOLODetector, recognizer: ArcFaceRecognizer,
                 anti_spoof: AntiSpoofChecker, face_search: FaissSearch,
                 publisher, snapshot_dir: str = "/app/snapshots",
                 mjpeg_server=None, id_to_name: dict | None = None,
                 mask_detector: MaskDetector | None = None,
                 face_aligner: MediaPipeFaceAligner | None = None):
        self.camera_id = camera_id
        self.direction = direction
        self.detector = detector
        self.recognizer = recognizer
        self.anti_spoof = anti_spoof
        self.mask_detector = mask_detector or MaskDetector()
        self.face_aligner  = face_aligner   # None = disabled (mediapipe not installed)
        self.face_search = face_search
        self.publisher = publisher
        self.snapshot_dir = snapshot_dir
        self.cctv_mode      = bool(config.get("cctv_mode", False))
        # skip_antispoof: disable liveness check for cameras where the heuristic
        # fallback produces 100% false positives (CCTV/DVR compressed streams).
        self.skip_antispoof = bool(config.get("skip_antispoof", False))
        # detect_bags: run YOLO object detection each frame for bags/suitcases.
        self.detect_bags    = bool(config.get("detect_bags", True))
        self.cooldown_s = config.get("cooldown_seconds", 300)
        # Minimum det_score to still attempt mask detection on a low-confidence face.
        # Faces above min_det_score go through normal recognition; faces between
        # mask_det_min and min_det_score are only checked for mask/covering.
        self.mask_det_min = float(config.get("mask_det_min", 0.25))
        self.recognition_threshold = float(
            config.get("recognition_threshold", face_search.threshold)
        )
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
        # Full-frame face sweep cache — SCRFD runs on the entire frame once per
        # inference cycle so all confirmed tracks can use the result without
        # repeating an expensive full-frame detection.
        self._ff_faces: list = []   # cached full-frame faces
        self._ff_frame_id: int = -1  # frame_count when cache was populated
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
        self._last_tracks: list = []  # cached for MJPEG overlay on dropped frames
        self._mjpeg_busy = False      # drop-if-busy gate for MJPEG encoder

    def push_mjpeg(self, frame: np.ndarray) -> None:
        """Push a frame to the MJPEG live feed from any thread, drop-if-busy.

        Called directly from the RTSPReader dispatch thread so the live stream
        updates at camera FPS without touching the async event loop at all.
        """
        if self._mjpeg is not None and not self._mjpeg_busy:
            self._mjpeg_busy = True
            _MJPEG_EXECUTOR.submit(self._encode_and_push, frame)

    async def process(self, frame: np.ndarray, ts: float):
        # _busy is set True by the dispatch thread before scheduling this coroutine.
        # The finally block releases it so the next frame can be scheduled.
        try:
            loop = asyncio.get_running_loop()
            events = await loop.run_in_executor(_INFERENCE_EXECUTOR, self._process_sync, frame, ts)
        finally:
            self._busy = False

        for event in events:
            asyncio.create_task(self.publisher.publish(event))

    def _process_sync(self, frame: np.ndarray, ts: float) -> list[dict]:
        events: list[dict] = []
        self._frame_count += 1

        tracks = self.detector.track(frame)
        self._last_tracks = tracks
        for t in tracks:
            self._track_seen[t.track_id] = ts

        if ts - self._last_log > 30:
            log.info(
                f"[{self.camera_id}] alive — frame #{self._frame_count} | "
                f"tracks={len(tracks)} | "
                f"faiss_size={self.face_search.index.ntotal if self.face_search.index else 0}"
            )
            self._last_log = ts

        # ── Bag / suspicious object detection ────────────────────────────────
        # Runs every 15 frames (~1.5s at 10fps) to avoid GPU contention with
        # the face recognition pipeline. Only fires when a person is present.
        if self.detect_bags and tracks and self._frame_count % 15 == 0:
            try:
                objects = self.detector.detect_objects(frame)
                for obj in objects:
                    # Alert if the object overlaps or is near any person track.
                    # Margin = 60% of person width/height so it scales with
                    # frame resolution and camera distance (staircase vs. kiosk).
                    ox = (obj.bbox[0] + obj.bbox[2]) / 2
                    oy = (obj.bbox[1] + obj.bbox[3]) / 2
                    near_person = False
                    for t in tracks:
                        pw = t.bbox[2] - t.bbox[0]
                        ph = t.bbox[3] - t.bbox[1]
                        mx, my = max(60, pw * 0.6), max(60, ph * 0.6)
                        if (t.bbox[0] - mx <= ox <= t.bbox[2] + mx and
                                t.bbox[1] - my <= oy <= t.bbox[3] + my):
                            near_person = True
                            break
                    if near_person:
                        snap = self._save_snapshot(frame, None, ts, is_unknown=True)
                        log.info("[%s] %s detected near person (conf=%.2f)",
                                 self.camera_id, obj.label, obj.confidence)
                        events.append({
                            "type": "suspicious_object",
                            "camera_id": self.camera_id,
                            "object_label": obj.label,
                            "confidence": round(float(obj.confidence), 3),
                            "snapshot_url": snap,
                            "timestamp": ts,
                            "employee_id": None,
                            "is_live": True,
                            "spoof_score": 0.0,
                        })
            except Exception as exc:
                log.warning("[%s] bag detection error: %s", self.camera_id, exc)

        self._prune_stale(ts)

        # All confirmed tracks run recognition for live display.
        # Cooldown only blocks attendance event recording — not label updates.
        confirmed = [t for t in tracks if t.is_confirmed()]

        # ── Synthetic tracks for orphan faces ─────────────────────────────────
        # When a person is close to the camera (kiosk / desk cam), only their
        # head+shoulders are visible and YOLO often fails to detect a "person".
        # But SCRFD still finds the face on the full frame. Run full-frame
        # detection now and, for any face NOT covered by a YOLO person box,
        # synthesise a person-track so the recognition loop processes it.
        # Pseudo track-id is derived from the quantised face position so votes
        # accumulate across frames for a roughly stationary face.
        if self._ff_frame_id != self._frame_count:
            self._ff_faces    = self.recognizer.detect_and_embed(frame)
            self._ff_frame_id = self._frame_count
        _H, _W = frame.shape[:2]
        for _f in self._ff_faces:
            fx1, fy1, fx2, fy2 = _f[0]
            cx = (fx1 + fx2) / 2; cy = (fy1 + fy2) / 2
            covered = False
            for t in confirmed:
                tx1, ty1, tx2, ty2 = t.bbox
                tw = tx2 - tx1; th = ty2 - ty1
                if (tx1 - tw*0.15) <= cx <= (tx2 + tw*0.15) and \
                   (ty1 - th*0.15) <= cy <= (ty2 + th*0.15):
                    covered = True
                    break
            if covered:
                continue
            fw = fx2 - fx1; fh = fy2 - fy1
            pb = (max(0, fx1 - fw*0.5), max(0, fy1 - fh*0.5),
                  min(_W, fx2 + fw*0.5), min(_H, fy2 + fh*0.5))
            pid = 10_000_000 + int(cy / 100) * 1000 + int(cx / 100)
            confirmed.append(Track(track_id=pid, bbox=pb, confidence=1.0))
            self._track_seen[pid] = ts

        for tr in confirmed:
            in_cooldown = self._in_cooldown(tr.track_id, ts)

            # CCTV cameras need more padding — at downward angles the head sits
            # above the YOLO person bbox centroid, so 60% padding ensures it's
            # fully included. Frontal cameras use 30% (enough for close faces).
            pad       = 0.60 if self.cctv_mode else 0.30
            crop      = self._crop_padded(frame, tr.bbox, pad=pad)
            head_crop = self._crop_head(frame, tr.bbox)
            if crop.size == 0:
                continue

            # ── Full-frame face detection (primary) ───────────────────────────
            # Already run once before this loop and cached in self._ff_faces.
            # Do NOT re-run here — that would invoke SCRFD once per track.
            x1, y1, x2, y2 = map(int, tr.bbox)
            bw, bh = x2 - x1, y2 - y1
            exp = 0.15  # small expansion so heads just above the bbox are included
            ex1 = max(0, int(x1 - bw * exp))
            ey1 = max(0, int(y1 - bh * exp))
            ex2 = min(frame.shape[1], int(x2 + bw * exp))
            ey2 = min(frame.shape[0], int(y2 + bh * exp))
            faces = [
                f for f in self._ff_faces
                if ex1 <= int((f[0][0] + f[0][2]) / 2) <= ex2
                and ey1 <= int((f[0][1] + f[0][3]) / 2) <= ey2
            ]
            face_from_full = bool(faces)

            # Fallback: head crop / full crop (for distant faces the full-frame
            # pass may under-resolve, e.g. someone far down a staircase).
            # fallback_crop is LOCAL to this loop iteration — never shared across tracks.
            fallback_crop = None
            if not faces:
                primary = head_crop if self.cctv_mode else crop
                faces = self.recognizer.detect_and_embed(primary) if primary.size > 0 else []
                face_from_full = False
                fallback_crop = primary

            if not faces:
                if self._frame_count % 30 == 0:
                    log.info("[%s] no face for track=%d (full-frame faces=%d, person %dx%d)",
                             self.camera_id, tr.track_id, len(self._ff_faces), bw, bh)
                continue

            # Pick the highest-quality face
            bbox, embedding, det_score = max(faces, key=lambda f: f[2])

            # Extract the face image from the correct coordinate space:
            # full-frame bbox → crop from `frame`; fallback bbox → crop from the
            # crop image it was detected in.
            if face_from_full:
                face_img = self._crop(frame, bbox)
            else:
                face_img = self._crop(fallback_crop, bbox)

            if self._frame_count % 5 == 0:
                log.debug("[%s] track=%d ff=%s det=%.3f face=%dx%d",
                          self.camera_id, tr.track_id, face_from_full,
                          det_score, face_img.shape[1] if face_img.size > 0 else 0,
                          face_img.shape[0] if face_img.size > 0 else 0)

            # ── Face-quality gate: skip junk crops that yield garbage embeddings ──
            if det_score < self.min_det_score:
                if self._frame_count % 30 == 0:
                    log.info("[%s] face det_score=%.3f below min=%.2f (track=%d)",
                             self.camera_id, det_score, self.min_det_score, tr.track_id)
                if det_score >= self.mask_det_min and face_img.size > 0:
                    is_masked, mask_conf = self.mask_detector.check(face_img)
                    if is_masked:
                        self._handle_masked(tr.track_id, face_img, mask_conf, ts, events)
                continue

            # ── Minimum face size gate ────────────────────────────────────────
            # SCRFD at det_thresh=0.3 detects false positives (texture patches)
            # that pass the det_score gate but are too small to be real faces.
            # At 1080P main stream, real faces are ≥80 px wide; anything smaller
            # is too distant/blurry to be useful for recognition or the log.
            fh, fw = face_img.shape[:2]
            if fh < 80 or fw < 80:
                continue

            # ── MediaPipe head-pose filter + alignment ────────────────────────
            # Rejects side-profile frames and warps accepted faces to the
            # canonical ArcFace 112×112 alignment before embedding.
            # Skipped transparently when mediapipe is not installed.
            if self.face_aligner is not None and self.face_aligner.available:
                face_img, is_frontal = self.face_aligner.process(face_img)
                if self._frame_count % 5 == 0:
                    log.debug("[%s] MediaPipe frontal=%s track=%d", self.camera_id, is_frontal, tr.track_id)
                if not is_frontal:
                    continue   # angled face — don't pollute the vote buffer

            # ── Budget-camera face enhancement + neural SR ────────────────────
            # Pipeline: FSRCNN 2x SR → bilateral denoise → unsharp → CLAHE.
            # SR doubles the face crop resolution (e.g. 80x80 → 160x160) so
            # ArcFace operates on more pixels. Enhancement then recovers texture
            # lost to H.264 compression. Together: +10-25% similarity on V380.
            snap_face = face_img  # default snapshot source — overwritten if enhancement runs
            if self.enhance_faces and face_img.size > 0:
                # 1. Neural 2x upscale (FSRCNN) — adds real detail, not just bigger pixels
                sr_face = self._face_sr.upscale(face_img) if self._face_sr else face_img
                # 2. Classical enhancement on the upscaled crop
                enhanced = _enhance_face(sr_face)
                snap_face = enhanced  # save the enhanced version to disk, not the raw crop
                # Re-embed from the upscaled+sharpened crop
                reembed = self.recognizer.detect_and_embed(enhanced)
                if reembed:
                    _, embedding, _ = max(reembed, key=lambda f: f[2])

            # ── Mask check (runs even on quality-passing faces to catch partial masks) ──
            is_masked, mask_conf = self.mask_detector.check(face_img)
            if is_masked:
                self._handle_masked(tr.track_id, face_img, mask_conf, ts, events)
                continue

            if self.skip_antispoof:
                # Liveness check disabled for this camera — heuristic fallback
                # produces false positives on CCTV/DVR compressed streams.
                # Mask detection remains active (separate path).
                is_live, spoof_score = True, 1.0
            else:
                # bbox coords are relative to `frame` when face_from_full, else to fallback_crop
                _spoof_src = frame if face_from_full else fallback_crop
                is_live, spoof_score = self.anti_spoof.check(_spoof_src, bbox, track_id=tr.track_id)
            emp_id, score = self.face_search.search_raw(np.asarray(embedding))

            # Padded face crop for snapshot — includes forehead, ears, chin.
            # bbox is in full-frame coords when the face came from the full-frame
            # pass, else in person-crop coords.
            _snap_src = frame if face_from_full else (fallback_crop if fallback_crop is not None else crop)
            face_snap = self._crop_padded(_snap_src, bbox, pad=0.60)
            # Apply exposure fix + enhancement to the snapshot crop so security
            # footage is clear regardless of lighting or camera quality.
            if face_snap.size > 0:
                face_snap = self._fix_exposure(face_snap)
                face_snap = _enhance_face(face_snap)
                # 2× upscale snapshot before save — Lanczos fallback when FSRCNN
                # unavailable; still gives more pixels for the display thumbnail.
                if self._face_sr:
                    face_snap = self._face_sr.upscale(face_snap)

            obs = {
                "emp_id": emp_id, "score": float(score),
                "is_live": bool(is_live), "spoof_score": float(spoof_score),
                "det_score": float(det_score), "face_img": snap_face,
                "face_snap": face_snap,   # padded + enhanced crop for detection log
                "person_crop": crop,
                "ts": ts,
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

        # ── Duplicate-identity spoof detection ────────────────────────────────
        # If two confirmed tracks in the same frame both match the same employee,
        # the smaller bounding-box face is a phone/tablet/print replica.
        # This fires immediately — no vote accumulation needed — because showing
        # someone's own photo to the camera always produces exactly this pattern.
        emp_to_tracks: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for tr in confirmed:
            buf = self._track_obs.get(tr.track_id)
            if not buf or len(buf) < 2:
                continue
            # Count votes per employee in this track's observation buffer
            vote_map: dict[str, int] = defaultdict(int)
            for obs in buf:
                if obs["emp_id"]:
                    vote_map[obs["emp_id"]] += 1
            if not vote_map:
                continue
            top_emp = max(vote_map, key=vote_map.__getitem__)
            if vote_map[top_emp] < 2:
                continue
            area = (tr.bbox[2] - tr.bbox[0]) * (tr.bbox[3] - tr.bbox[1])
            emp_to_tracks[top_emp].append((tr.track_id, area))

        for emp_id, track_areas in emp_to_tracks.items():
            if len(track_areas) < 2:
                continue
            # Largest bounding box = closest real person; smaller = phone replica
            track_areas.sort(key=lambda x: x[1], reverse=True)
            for dup_track_id, _ in track_areas[1:]:
                if self._in_cooldown(dup_track_id, ts):
                    continue
                log.warning(
                    "[%s] PHONE/PRINT SPOOF — emp=%s seen in track %d (duplicate, smaller face)",
                    self.camera_id, emp_id[:8], dup_track_id,
                )
                self._track_labels[dup_track_id] = ("SPOOF", _CLR_SPOOF)
                self._spoof_tracks.add(dup_track_id)
                self._cooldown[dup_track_id] = ts
                face_obs = (self._track_obs.get(dup_track_id) or [{}])[-1]
                snap = self._save_snapshot(
                    face_obs.get("person_crop", face_obs.get("face_img",
                        np.zeros((64, 64, 3), np.uint8))),
                    None, ts, is_unknown=True,
                )
                events.append({
                    "type": "spoof_attempt",
                    "camera_id": self.camera_id,
                    "track_id": dup_track_id,
                    "timestamp": ts,
                    "snapshot_url": snap,
                    "is_live": False,
                    "spoof_score": 0.0,
                    "employee_id": emp_id,
                    "confidence": 0,
                })

        return events

    # ── Decision engine ───────────────────────────────────────────────────
    def _decide(self, track_id: int, buf: list[dict], ts: float):
        n = len(buf)
        majority = max(2, math.ceil(n / 2))
        threshold = getattr(self, "recognition_threshold", self.face_search.threshold)

        # 1) Spoof — fire if liveness fails in 40% or more of frames.
        # Raised from ceil(n/4) to ceil(n/2.5) so a single frame with a transient
        # liveness dip (motion blur, partial occlusion) doesn't flag a real employee.
        # At n=5: old=2 frames needed, new=2 (same); at n=2: old=1, new=1 still,
        # but the minimum is now 2 so one bad frame alone never fires spoof.
        spoof_threshold = max(2, math.ceil(n / 2.5))
        spoof_obs = [o for o in buf if not o["is_live"]]
        if len(spoof_obs) >= spoof_threshold:
            rep = min(spoof_obs, key=lambda o: o["spoof_score"])
            log.warning(f"[{self.camera_id}] SPOOF confirmed track={track_id} "
                        f"({len(spoof_obs)}/{n} frames, score={rep['spoof_score']:.3f})")
            self._track_labels[track_id] = ("SPOOF", _CLR_SPOOF)
            best_snap = max(buf, key=lambda o: o["det_score"])
            snap = self._save_snapshot(best_snap.get("face_snap", best_snap.get("face_img")), None, ts, is_unknown=True, already_enhanced=True)
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
                # Best frame for snapshot = highest det_score (clearest face),
                # not highest similarity score (which is for recognition quality).
                best_snap = max(buf, key=lambda o: o["det_score"])
                log.info(f"[{self.camera_id}] RECOGNIZED {name} (emp={winner}) "
                         f"votes={wcount}/{n} mean_sim={wmean:.3f}")
                self._track_labels[track_id] = (name, _CLR_KNOWN)
                snap = self._save_snapshot(best_snap.get("face_snap", best_snap.get("face_img")), winner, ts, already_enhanced=True)
                return {
                    "type": "recognition", "camera_id": self.camera_id,
                    "direction": self.direction, "track_id": track_id,
                    "employee_id": winner, "confidence": round(wmean, 4),
                    "is_live": True, "spoof_score": round(best_snap["spoof_score"], 4),
                    "embedding_dist": round(1 - wmean, 5), "snapshot_url": snap,
                    "timestamp": ts,
                }
            # Not enough agreement yet — keep collecting unless the window is full
            if n < self.vote_window:
                return None

        # 3) Unknown — window full (or no candidates) and nobody won
        if n < self.vote_window:
            return None
        # Pick clearest frame for snapshot (highest det_score = best face quality)
        best_snap = max(buf, key=lambda o: o["det_score"])
        best_score = max(buf, key=lambda o: o["score"])
        if self.face_search.index is None or self.face_search.index.ntotal == 0:
            log.warning(f"[{self.camera_id}] face seen but FAISS index EMPTY — enroll employees first.")
        else:
            log.info(f"[{self.camera_id}] UNKNOWN confirmed track={track_id} "
                     f"(best_sim={best_score['score']:.3f}, threshold={threshold})")
        self._track_labels[track_id] = ("Unknown", _CLR_UNKNOWN)
        snap = self._save_snapshot(best_snap.get("face_snap", best_snap.get("face_img")), None, ts, is_unknown=True, already_enhanced=True)
        return {
            "type": "unknown_person", "camera_id": self.camera_id,
            "direction": self.direction, "track_id": track_id,
            "employee_id": None, "confidence": round(best_score["score"], 4),
            "is_live": True, "spoof_score": round(best_snap["spoof_score"], 4),
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
        elif obs["emp_id"] is not None and obs["score"] >= self.recognition_threshold:
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

    def _encode_and_push(self, frame: np.ndarray) -> None:
        """Encode frame to JPEG and push to the MJPEG live feed.

        Runs in _MJPEG_EXECUTOR (separate from inference) so the camera stream
        updates at camera FPS rather than stuttering at the slower inference rate.
        Uses the last known tracks/labels so overlays stay visible on dropped frames.
        """
        try:
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                preview = cv2.resize(frame, (1280, int(h * scale)),
                                     interpolation=cv2.INTER_LINEAR)
            else:
                preview = frame
                scale = 1.0
            annotated = self._draw_overlays(preview, self._last_tracks, bbox_scale=scale)
            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 60])
            self._mjpeg.put_frame(self.camera_id, jpeg.tobytes())
        except Exception:
            pass
        finally:
            self._mjpeg_busy = False

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
    def _crop_head(img, bbox) -> np.ndarray:
        """Crop the upper 40% of the person bbox (head + shoulders).

        For CCTV/overhead cameras the face sits in the top portion of the
        person bounding box. Giving SCRFD a head-focused crop instead of the
        full body crop dramatically improves face detection at downward angles.
        A 15% horizontal pad is added so the full head width is included.
        """
        x1, y1, x2, y2 = map(int, bbox)
        bh = y2 - y1
        bw = x2 - x1
        head_y2 = y1 + int(bh * 0.40)       # top 40% = head + shoulders
        px = int(bw * 0.15)                  # 15% horizontal padding
        h, w = img.shape[:2]
        x1c = max(0, x1 - px)
        x2c = min(w, x2 + px)
        y1c = max(0, y1)
        y2c = min(h, head_y2)
        return img[y1c:y2c, x1c:x2c]

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

    @staticmethod
    def _fix_exposure(img: np.ndarray) -> np.ndarray:
        """Correct dark / underexposed snapshots so they are legible in the log.

        Two-stage pipeline:
          1. Gamma correction — if the image is dark overall, apply a brightening
             gamma (<1.0) to lift shadows without blowing out highlights.
          2. CLAHE per-channel — restores local contrast so face details (eyes,
             skin texture) stay sharp even after global brightening.
        """
        if img is None or img.size == 0:
            return img
        mean_lum = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())

        # Only correct images that are genuinely dark (mean < 100 out of 255).
        # Bright or well-lit shots are left unchanged to avoid washing them out.
        if mean_lum < 100:
            # Gamma: 0.4 for very dark (<40), scaling linearly to 1.0 at 100.
            gamma = max(0.4, mean_lum / 100.0)
            table = np.array([((i / 255.0) ** gamma) * 255
                              for i in range(256)], dtype=np.uint8)
            img = cv2.LUT(img, table)

        # CLAHE on L channel only (LAB) — avoids the colour shifts that
        # per-channel CLAHE causes on skin tones (purple/green tinting).
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        img = cv2.cvtColor(cv2.merge([clahe.apply(l_ch), a_ch, b_ch]), cv2.COLOR_LAB2BGR)
        return img

    def _save_snapshot(self, img, emp_id, ts, is_unknown: bool = False,
                       already_enhanced: bool = False) -> str:
        if is_unknown:
            d = os.path.join(self.snapshot_dir, "unknown")
        else:
            d = os.path.join(self.snapshot_dir, str(emp_id))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{int(ts)}.jpg")
        try:
            if img is None or img.size == 0:
                return path

            if not already_enhanced:
                # Fix dark / underexposed frames, then enhance texture.
                img = self._fix_exposure(img)
                img = _enhance_face(img)

            # 3. Enforce a minimum display size — 1024px for crisp log thumbnails
            #    at 1080P source quality. Larger base → less interpolation damage.
            h, w = img.shape[:2]
            if h < 1024 or w < 1024:
                scale = max(1024 / h, 1024 / w)
                img = cv2.resize(img, (int(w * scale), int(h * scale)),
                                 interpolation=cv2.INTER_LANCZOS4)
                # Sharpening pass after final upscale to recover edge crispness.
                blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=1.0)
                img = cv2.addWeighted(img, 1.6, blurred, -0.6, 0)
                img = np.clip(img, 0, 255).astype(np.uint8)

            # 4. Save at high quality.
            cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 97])
        except Exception:
            pass
        return path
