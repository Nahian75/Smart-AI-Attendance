"""
Face mask / face-covering detector.

Primary path  : a binary ONNX classifier (mask / no_mask, 224×224 RGB).
                Expected output: [1, 2] logits → softmax → index 1 = P(mask).
                Drop any compatible model (e.g. face_mask_detector.onnx) at
                the path configured via `mask_model` in camera_config.yaml.

Fallback path : texture heuristic — splits the face crop into upper and
                lower halves and looks for the signature of a mask:
                  • low colour saturation in the lower face (nose/mouth/chin)
                  • low texture energy (Laplacian variance) in lower face
                  • unusually uniform luminance in lower face
                Catches surgical masks (white/blue), cloth masks, N95/FFP2.
                Will miss sheer lace masks or face paint that mimics skin tone.
"""
import os
import logging
import numpy as np
import cv2

log = logging.getLogger(__name__)

_MODEL_IMG_SIZE = 224


class MaskDetector:
    def __init__(self, model_path: str | None = None, threshold: float | None = None):
        if threshold is None:
            threshold = float(os.getenv("MASK_THRESHOLD", "0.55"))
        self.threshold = threshold
        self.session = None
        self.input_name = None
        self._using_heuristic = False

        if model_path and os.path.exists(model_path):
            from ..utils.gpu import detect as detect_gpu
            import onnxruntime as ort
            providers = detect_gpu()["ort_providers"]
            try:
                self.session = ort.InferenceSession(model_path, providers=providers)
            except Exception:
                self.session = ort.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"]
                )
            self.input_name = self.session.get_inputs()[0].name
            log.info("Mask detection model loaded: %s", model_path)
        else:
            if model_path:
                log.warning(
                    "Mask model not found at %r — using texture heuristic fallback.",
                    model_path,
                )
            else:
                log.info("No mask model configured — using texture heuristic fallback.")
            self._using_heuristic = True
            if threshold >= 0.55:
                self.threshold = 0.45

    def check(self, face_img: np.ndarray) -> tuple[bool, float]:
        """
        Returns (is_masked, mask_probability).

        face_img: BGR face crop — should be a tight crop of just the face,
                  at least 32×32 pixels.
        """
        if face_img is None or face_img.size == 0:
            return False, 0.0

        if self.session is not None:
            score = self._model_infer(face_img)
        else:
            score = self._heuristic_infer(face_img)

        return score >= self.threshold, round(float(score), 4)

    # ── Model path ────────────────────────────────────────────────────────

    def _model_infer(self, face_img: np.ndarray) -> float:
        rgb = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (_MODEL_IMG_SIZE, _MODEL_IMG_SIZE))
        blob = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = blob[None, ...]
        logits = self.session.run(None, {self.input_name: blob})[0][0]
        e = np.exp(logits - logits.max())
        probs = e / e.sum()
        return float(probs[1]) if len(probs) > 1 else float(probs[0])

    # ── Heuristic fallback ────────────────────────────────────────────────

    @staticmethod
    def _heuristic_infer(face_img: np.ndarray) -> float:
        """
        Estimate mask probability from lower-face vs upper-face texture/colour.

        A mask (surgical, cloth, N95) creates a large, low-texture region
        over the mouth and nose.  We compare the eye region (always
        high-texture, higher-saturation skin) against the mouth region.

        Upper band: forehead + eyes (top 40% of face crop)
        Lower band: nose + mouth + chin (bottom 45% of face crop)
        Middle 15% is excluded to avoid nose-tip ambiguity.
        """
        h, w = face_img.shape[:2]
        if h < 32 or w < 32:
            return 0.0

        face = cv2.resize(face_img, (96, 96))
        upper = face[: int(96 * 0.40), :]          # forehead + eyes
        lower = face[int(96 * 0.55) :, :]           # nose + mouth + chin

        if upper.size == 0 or lower.size == 0:
            return 0.0

        # Saturation: mask fabric is far less colourful than skin
        upper_sat = float(cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)[:, :, 1].mean())
        lower_sat = float(cv2.cvtColor(lower, cv2.COLOR_BGR2HSV)[:, :, 1].mean())

        # Texture (Laplacian variance): mask surface is smooth compared to skin
        upper_gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
        lower_gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY)
        upper_tex = float(cv2.Laplacian(upper_gray, cv2.CV_64F).var())
        lower_tex = float(cv2.Laplacian(lower_gray, cv2.CV_64F).var())

        # Luminance uniformity: mask is spatially uniform; skin has highlights/shadows
        lower_lum_std = float(lower_gray.std())

        eps = 1e-6

        # Score each cue as [0, 1] where 1 = strong mask signal
        sat_drop = max(0.0, 1.0 - lower_sat / (upper_sat + eps))
        sat_score = min(1.0, sat_drop / 0.45)          # full score at ≥45% drop

        tex_ratio = lower_tex / (upper_tex + eps)
        tex_score = min(1.0, max(0.0, 1.0 - tex_ratio / 0.55))

        # lower_lum_std < 18 → very uniform → likely mask
        lum_score = min(1.0, max(0.0, 1.0 - lower_lum_std / 18.0))

        return float(
            sat_score * 0.40
            + tex_score * 0.35
            + lum_score * 0.25
        )
