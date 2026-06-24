"""
Liveness / anti-spoofing gate.

Primary path: a trained MiniFASNet-style ONNX model (CelebA-Spoof, 128x128 binary)
from the hairymax/Face-AntiSpoofing project. This is a real CNN that reliably
catches printed-photo and screen-replay attacks (AUC-ROC ~0.99 on CelebA-Spoof).

Model contract (verified against the upstream inference code):
  - input  : [1, 3, 128, 128] float32, RGB, letterboxed, pixels / 255
  - output : [1, 2] logits → softmax → index 0 = P(real/live), index 1 = P(spoof)
  - the face bbox is expanded 1.5x before cropping (bbox_inc=1.5)

Fallback path: if no model file is present, a multi-cue texture heuristic is used
(Laplacian variance + gradient energy + saturation + FFT moiré). Far weaker than
the model but better than blindly passing everything as live.
"""
import os
import logging
import numpy as np
import cv2

log = logging.getLogger(__name__)


class AntiSpoofChecker:
    def __init__(self, model_path: str | None = None, threshold: float | None = None,
                 bbox_inc: float = 1.5, model_img_size: int = 128):
        if threshold is None:
            threshold = float(os.getenv("LIVENESS_THRESHOLD", "0.55"))
        self.threshold = threshold
        self.bbox_inc = bbox_inc
        self.model_img_size = model_img_size
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
                self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            self.input_name = self.session.get_inputs()[0].name
            in_shape = self.session.get_inputs()[0].shape
            if len(in_shape) == 4 and isinstance(in_shape[2], int):
                self.model_img_size = in_shape[2]
            log.info("Anti-spoof model loaded: %s (input=%s, providers=%s)",
                     model_path, in_shape, providers)
        else:
            if model_path:
                log.warning(
                    "Anti-spoof model not found at %r — using texture heuristic fallback.", model_path
                )
            else:
                log.info("No anti-spoof model configured — using texture heuristic fallback.")
            self._using_heuristic = True
            # Heuristic uses a different score scale; clamp threshold to a sane value
            if threshold >= 0.55:
                self.threshold = 0.35

    def check(self, image: np.ndarray, bbox=None) -> tuple[bool, float]:
        """
        Returns (is_live, p_live).

        image : BGR image. If bbox is given, it is the larger region (person crop)
                and bbox=(x1,y1,x2,y2) locates the face within it; the model crop
                is expanded 1.5x around that face. If bbox is None, `image` is
                treated as an already-cropped face.
        """
        if image is None or image.size == 0:
            return True, 1.0  # nothing to judge — don't block

        if self.session is not None:
            score = self._model_infer(image, bbox)
        else:
            face = self._tight_face(image, bbox)
            score = self._heuristic_infer(face)
        return score >= self.threshold, round(float(score), 4)

    # ── Model path ────────────────────────────────────────────────────────
    def _model_infer(self, image: np.ndarray, bbox) -> float:
        crop = self._increased_crop(image, bbox, self.bbox_inc)
        if crop.size == 0:
            return 1.0
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        blob = self._letterbox(rgb, self.model_img_size)
        blob = blob.transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = blob[None, ...]
        logits = self.session.run(None, {self.input_name: blob})[0][0]
        e = np.exp(logits - logits.max())
        probs = e / e.sum()
        return float(probs[0])  # index 0 = P(live)

    @staticmethod
    def _increased_crop(img, bbox, bbox_inc: float):
        """Expand the face bbox by bbox_inc and crop a square, zero-padding edges."""
        h_img, w_img = img.shape[:2]
        if bbox is None:
            bbox = (0, 0, w_img, h_img)
        x1, y1, x2, y2 = [int(v) for v in bbox]
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            return img
        l = max(w, h)
        xc, yc = x1 + w / 2, y1 + h / 2
        x = int(xc - l * bbox_inc / 2)
        y = int(yc - l * bbox_inc / 2)
        side = int(l * bbox_inc)
        cx1 = max(0, x)
        cy1 = max(0, y)
        cx2 = min(w_img, x + side)
        cy2 = min(h_img, y + side)
        crop = img[cy1:cy2, cx1:cx2, :]
        # Pad so the result is the full `side` square even at frame edges
        top, left = cy1 - y, cx1 - x
        bottom, right = side - (cy2 - y), side - (cx2 - x)
        if any(v > 0 for v in (top, bottom, left, right)):
            crop = cv2.copyMakeBorder(
                crop, max(0, top), max(0, bottom), max(0, left), max(0, right),
                cv2.BORDER_CONSTANT, value=[0, 0, 0],
            )
        return crop

    @staticmethod
    def _letterbox(img, size: int) -> np.ndarray:
        """Aspect-preserving resize + zero-pad to a square `size` x `size`."""
        old_h, old_w = img.shape[:2]
        ratio = float(size) / max(old_h, old_w)
        nh, nw = int(old_h * ratio), int(old_w * ratio)
        resized = cv2.resize(img, (nw, nh))
        dh, dw = size - nh, size - nw
        top, bottom = dh // 2, dh - dh // 2
        left, right = dw // 2, dw - dw // 2
        return cv2.copyMakeBorder(resized, top, bottom, left, right,
                                  cv2.BORDER_CONSTANT, value=[0, 0, 0])

    # ── Heuristic fallback ────────────────────────────────────────────────
    @staticmethod
    def _tight_face(image, bbox):
        if bbox is None:
            return image
        h_img, w_img = image.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img, x2), min(h_img, y2)
        if x2 <= x1 or y2 <= y1:
            return image
        return image[y1:y2, x1:x2]

    def _heuristic_infer(self, face_crop: np.ndarray) -> float:
        if face_crop is None or face_crop.size == 0:
            return 0.5
        face = cv2.resize(face_crop, (96, 96))
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)

        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        lap_score = min(1.0, lap_var / 350.0)

        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_score = min(1.0, float(np.sqrt(gx ** 2 + gy ** 2).mean()) / 22.0)

        hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
        sat_score = min(1.0, float(hsv[:, :, 1].std()) / 32.0)

        # FFT high-frequency ratio — screen replays add regular moiré energy
        f = np.fft.fftshift(np.fft.fft2(gray))
        mag = np.abs(f)
        cy, cx = mag.shape[0] // 2, mag.shape[1] // 2
        mask = np.ones_like(mag); mask[cy - 8:cy + 8, cx - 8:cx + 8] = 0
        hf_ratio = float((mag * mask).sum() / (mag.sum() + 1e-6))
        hf_score = min(1.0, hf_ratio * 1.4)

        return float(lap_score * 0.35 + grad_score * 0.30 + sat_score * 0.20 + hf_score * 0.15)
