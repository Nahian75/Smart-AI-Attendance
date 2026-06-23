"""
Liveness / anti-spoofing gate.

PRD §6.3: liveness threshold = 0.80 (configurable via LIVENESS_THRESHOLD env var).
Catches printed-photo and screen-replay attacks.
If no model file is found, all faces are treated as live (pass-through mode).
"""
import os
import logging
import numpy as np

log = logging.getLogger(__name__)


class AntiSpoofChecker:
    def __init__(self, model_path: str | None = None, threshold: float | None = None):
        if threshold is None:
            threshold = float(os.getenv("LIVENESS_THRESHOLD", "0.80"))
        self.threshold = threshold
        self.session = None

        if model_path and os.path.exists(model_path):
            from ..utils.gpu import detect as detect_gpu
            import onnxruntime as ort
            providers = detect_gpu()["ort_providers"]
            self.session = ort.InferenceSession(model_path, providers=providers)
            log.info("Anti-spoof model loaded with providers: %s", providers)
        elif model_path:
            log.warning(
                "Anti-spoof model not found at %r — running in pass-through mode "
                "(all faces treated as live).", model_path
            )

    def check(self, face_crop: np.ndarray) -> tuple[bool, float]:
        """Returns (is_live, score). Score < threshold → spoof."""
        score = self._infer(face_crop)
        return score >= self.threshold, round(score, 4)

    def _infer(self, face_crop: np.ndarray) -> float:
        if self.session is None:
            return 1.0
        import cv2
        img = cv2.resize(face_crop, (80, 80)).astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))[None, ...]
        out = self.session.run(None, {self.session.get_inputs()[0].name: img})[0]
        probs = np.exp(out[0]) / np.exp(out[0]).sum()
        return float(probs[1])  # P(live)
