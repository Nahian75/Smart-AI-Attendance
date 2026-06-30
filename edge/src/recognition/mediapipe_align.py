"""
MediaPipe Face Landmarker — head pose filter and landmark-based alignment for ArcFace.

Uses the MediaPipe Tasks API (mp.tasks.vision.FaceLandmarker) introduced in 0.10+.
The old mp.solutions.face_mesh API was removed in 0.10 — this module targets the
current API only.

Requires a model file: edge/weights/face_landmarker.task (~3 MB)
Auto-downloaded on first use if not present.

Why this exists:
  ArcFace was trained on aligned faces (eyes at fixed pixel positions). Feeding
  unaligned crops — person walking in at an angle, looking away — degrades
  similarity scores and causes enrolled employees to be voted "Unknown".

What this does:
  1. Runs FaceLandmarker on the face crop to extract 478 landmarks.
  2. Rejects faces whose yaw or pitch exceed configurable thresholds so junk
     frames are never added to the vote buffer.
  3. Warps accepted faces to the canonical ArcFace 112×112 alignment using a
     similarity transform from 5 key points (eyes, nose, mouth corners).
"""
import os
import urllib.request
import cv2
import numpy as np
from ..utils.logger import get_logger

log = get_logger("mp_align")

# Model file — auto-downloaded on first use
_MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
_MODEL_DEFAULT = "edge/weights/face_landmarker.task"

# FaceLandmarker landmark indices for pose estimation
_IDX_L_EYE_OUTER = 33
_IDX_L_EYE_INNER = 133
_IDX_R_EYE_INNER = 362
_IDX_R_EYE_OUTER = 263
_IDX_NOSE_TIP    = 4


def _ensure_model(model_path: str) -> str:
    """Download the FaceLandmarker .task model if not already present."""
    if os.path.exists(model_path):
        return model_path
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    log.info("Downloading FaceLandmarker model to %s ...", model_path)
    try:
        urllib.request.urlretrieve(_MODEL_URL, model_path)
        size_mb = os.path.getsize(model_path) / 1_048_576
        log.info("FaceLandmarker model downloaded (%.1f MB).", size_mb)
    except Exception as exc:
        if os.path.exists(model_path):
            os.remove(model_path)
        raise RuntimeError(f"Could not download FaceLandmarker model: {exc}") from exc
    return model_path


class MediaPipeFaceAligner:
    """
    Filters and aligns face crops using MediaPipe FaceLandmarker (Tasks API).

    Instantiate once and share across cameras — RunningMode.IMAGE makes every
    call independent (no state between frames), so thread-safe when called from
    the single-worker inference executor.

    Usage:
        aligner = MediaPipeFaceAligner()
        if aligner.available:
            face_img, accepted = aligner.process(face_crop)
            if not accepted:
                continue          # too angled — skip frame
            # feed face_img to ArcFace / enhancement
    """

    def __init__(self, max_yaw: float = 40.0, max_pitch: float = 30.0,
                 model_path: str = _MODEL_DEFAULT):
        """
        max_yaw:    reject faces rotated more than this many degrees left/right.
        max_pitch:  reject faces tilted more than this many degrees up/down.
        model_path: path to face_landmarker.task; auto-downloaded if missing.
        """
        self.max_yaw     = max_yaw
        self.max_pitch   = max_pitch
        self._landmarker = None
        self._init_landmarker(model_path)

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_landmarker(self, model_path: str) -> None:
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            path = _ensure_model(model_path)

            base_opts = python.BaseOptions(model_asset_path=path)
            opts = vision.FaceLandmarkerOptions(
                base_options=base_opts,
                running_mode=vision.RunningMode.IMAGE,  # stateless per call
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._landmarker = vision.FaceLandmarker.create_from_options(opts)
            self._mp = mp
            log.info(
                "MediaPipe FaceLandmarker initialised "
                "(head-pose filter + alignment active, model=%s).", path
            )
        except Exception as exc:
            log.warning(
                "MediaPipe FaceLandmarker not available (%s). "
                "Head-pose filter disabled — frames passed through unchanged.",
                exc,
            )
            self._landmarker = None

    @property
    def available(self) -> bool:
        return self._landmarker is not None

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, face_img: np.ndarray) -> tuple[np.ndarray, bool]:
        """
        Run head-pose check on a face crop. Always returns the ORIGINAL image.

        MediaPipe is used for filtering only — angled frames are rejected so
        they don't pollute the vote buffer, but the geometric warp is intentionally
        skipped. ArcFace's internal SCRFD detector aligns the face during embedding,
        exactly as it did at enrollment time. Applying a second alignment here would
        produce different embeddings and break recognition.

        Returns:
            (face_img, True)   — face is frontal; pass to ArcFace unchanged.
            (face_img, False)  — face is too angled; caller should skip frame.
        """
        if self._landmarker is None or face_img is None or face_img.size == 0:
            return face_img, True

        h, w = face_img.shape[:2]
        if h < 32 or w < 32:
            return face_img, True

        # Upscale very small crops — landmark accuracy drops below ~96 px
        work  = face_img
        scale = 1.0
        if min(h, w) < 128:
            scale = 128.0 / min(h, w)
            work  = cv2.resize(face_img, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_LINEAR)
            h, w = work.shape[:2]

        rgb      = cv2.cvtColor(work, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=rgb,
        )
        result = self._landmarker.detect(mp_image)

        if not result.face_landmarks:
            return face_img, True   # no face found — pass through

        lm = result.face_landmarks[0]   # NormalizedLandmark list

        def pt(idx: int) -> np.ndarray:
            p = lm[idx]
            return np.array([p.x * w, p.y * h], dtype=np.float32)

        left_eye  = (pt(_IDX_L_EYE_OUTER) + pt(_IDX_L_EYE_INNER)) * 0.5
        right_eye = (pt(_IDX_R_EYE_INNER) + pt(_IDX_R_EYE_OUTER)) * 0.5
        nose_tip  = pt(_IDX_NOSE_TIP)

        # ── Head-pose estimation ──────────────────────────────────────────────
        eye_mid  = (left_eye + right_eye) * 0.5
        eye_dist = float(np.linalg.norm(right_eye - left_eye))

        if eye_dist < 4:
            return face_img, True   # landmarks too close — unreliable

        # Nose displacement from eye midpoint, normalised by inter-eye distance.
        # Frontal face: nose_dx ≈ 0,  nose_dy ≈ 0.45–0.55
        nose_dx = (nose_tip[0] - eye_mid[0]) / eye_dist   # yaw proxy
        nose_dy = (nose_tip[1] - eye_mid[1]) / eye_dist   # pitch proxy

        # Convert degree thresholds to the nose_dx / nose_dy coordinate scale.
        # nose_dx ≈ sin(yaw) × 0.5 → degrees ≈ nose_dx × 115
        yaw_limit   = min(self.max_yaw / 115.0, 0.55)
        # nose_dy range (0.10 → 0.75) spans ~90° of pitch; center ≈ 0.425
        pitch_margin = (self.max_pitch / 90.0) * 0.325
        pitch_lo = max(0.05, 0.425 - pitch_margin)
        pitch_hi = min(0.90, 0.425 + pitch_margin)

        if abs(nose_dx) > yaw_limit:
            log.debug("pose filter: yaw≈%.0f° — skipping frame",
                      float(nose_dx) * 115.0)
            return face_img, False

        if not (pitch_lo < nose_dy < pitch_hi):
            log.debug("pose filter: extreme pitch (nose_dy=%.2f) — skipping frame",
                      float(nose_dy))
            return face_img, False

        # Pose is acceptable — return the original crop unchanged.
        # ArcFace handles its own alignment via SCRFD landmarks, exactly as
        # it did at enrollment. A second geometric warp here would break the
        # embedding consistency and cause recognition failures.
        return face_img, True

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
