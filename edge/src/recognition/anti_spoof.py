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
        # Per-track temporal state for static-image detection (phone/tablet replays).
        # Keyed by track_id; holds {"prev_gray": np.ndarray, "static_count": int}.
        self._temporal: dict[int, dict] = {}

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
                self.threshold = 0.45

    def clear_track(self, track_id: int) -> None:
        """Drop temporal state for a disappeared track."""
        self._temporal.pop(track_id, None)

    def check(self, image: np.ndarray, bbox=None, track_id: int | None = None) -> tuple[bool, float]:
        """
        Returns (is_live, p_live).

        image : BGR image. If bbox is given, it is the larger region (person crop)
                and bbox=(x1,y1,x2,y2) locates the face within it; the model crop
                is expanded 1.5x around that face. If bbox is None, `image` is
                treated as an already-cropped face.
        track_id : optional caller-supplied track id used to maintain per-track
                   temporal state for static-image (phone/tablet) detection.
        """
        if image is None or image.size == 0:
            return True, 1.0  # nothing to judge — don't block

        face_tight = self._tight_face(image, bbox)

        if self.session is not None:
            score = self._model_infer(image, bbox)
        else:
            score = self._heuristic_infer(face_tight)

        # ── Screen-context: uniform backlit surround (works for model + heuristic) ──
        if bbox is not None:
            ctx = self._screen_context_check(image, bbox)
            score = score * (1.0 - ctx * 0.75)

        # ── Color-temperature: phone screens are blue-shifted; real skin is warm ──
        if face_tight is not None and face_tight.size > 0:
            score = score * self._color_temp_check(face_tight)

        # ── Temporal gate: catches static phone photos via histogram comparison ──
        if track_id is not None:
            score = self._temporal_gate(score, face_tight, track_id)

        return score >= self.threshold, round(float(score), 4)

    @staticmethod
    def _color_temp_check(face_bgr: np.ndarray) -> float:
        """Return a liveness multiplier based on skin colour temperature.

        Phone/tablet screens backlight the displayed photo with a cold
        blue-white LED (~6500 K). Real skin lit by indoor lighting has
        warm tones where the red channel dominates the blue channel.

        Multiplier = 1.0 (no change) for warm-toned faces.
        Multiplier approaches 0.0 as the face becomes increasingly blue-shifted.
        """
        if face_bgr is None or face_bgr.size == 0:
            return 1.0
        img = cv2.resize(face_bgr, (64, 64)).astype(np.float32)
        mean_b = float(img[:, :, 0].mean())
        mean_r = float(img[:, :, 2].mean())
        if mean_r < 1.0:
            return 1.0
        # blue_ratio > 1.0  → screen-like (cold light)
        # blue_ratio < 0.85 → real skin (warm light)
        blue_ratio = mean_b / mean_r
        # Linear ramp: no penalty below 0.85, full penalty at ratio ≥ 1.30
        penalty = min(1.0, max(0.0, (blue_ratio - 0.85) / 0.45))
        return 1.0 - penalty * 0.60  # at ratio=1.30 → ×0.40 multiplier

    def _temporal_gate(self, score: float, face: np.ndarray, track_id: int) -> float:
        """
        Histogram-based static-image detector (shift-invariant).

        Pixel-diff fails when the hand holding a phone trembles — a 2-3 px crop
        shift looks like "motion" even when the image content is frozen.
        Histogram comparison is unaffected by small spatial shifts: if the face
        on screen doesn't change (static photo), consecutive histograms are
        nearly identical.  A live face's histogram varies measurably each frame
        from micro-expressions, blinking, and head movement.
        """
        if face is None or face.size == 0:
            return score
        small = cv2.resize(face, (48, 48)) if min(face.shape[:2]) > 48 else face
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if len(small.shape) == 3 else small

        hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
        hist /= hist.sum() + 1e-6

        # Evict stale entries: keep only the most recent 1000 track IDs.
        # In a 24-hour session with 5 tracks/min this caps memory at ~1000 entries.
        if len(self._temporal) > 1000:
            oldest = next(iter(self._temporal))
            self._temporal.pop(oldest, None)

        state = self._temporal.setdefault(track_id, {"prev_hist": None, "static_count": 0})
        if state["prev_hist"] is not None:
            diff = float(np.sum(np.abs(hist - state["prev_hist"])))
            # Phone photo on screen: diff ≈ 0.01–0.04 (essentially frozen)
            # Real employee standing still: diff ≈ 0.06–0.15 (breathing, micro-expressions)
            if diff < 0.055:
                state["static_count"] = min(state["static_count"] + 1, 12)
            else:
                state["static_count"] = max(0, state["static_count"] - 1)
        state["prev_hist"] = hist.copy()

        # Penalty starts from count=1 (the SECOND frame we see this face).
        # With min_votes=4 the decision happens at frame 4. By that point a
        # static phone photo accumulates count=3 → 62.5% penalty, driving the
        # model score (typically 0.50–0.65 for a phone) below the threshold.
        # A real employee whose diff drops below 0.055 briefly gets at most
        # 12.5% reduction at count=1, which doesn't affect a confident match.
        #   count=1: ×0.875   count=2: ×0.750   count=3: ×0.625
        #   count=4: ×0.500   count=6: ×0.250   count=8+: → 0
        if state["static_count"] >= 1:
            penalty = max(0.0, 1.0 - state["static_count"] / 8.0)
            score = score * penalty
        return score

    @staticmethod
    def _screen_context_check(person_crop: np.ndarray, bbox) -> float:
        """
        Returns [0, 1] — probability that the face sits on a bright screen.

        Screens (phone/tablet/monitor) emit their own light, making the region
        SURROUNDING the face bbox significantly brighter and more uniform than
        any natural background.  For a real person the face is typically the
        brightest region in the crop (lit by ambient light from above/front);
        for a screen spoof the entire screen surface is uniformly backlit.
        """
        h, w = person_crop.shape[:2]
        x1, y1 = max(0, int(bbox[0])), max(0, int(bbox[1]))
        x2, y2 = min(w, int(bbox[2])), min(h, int(bbox[3]))
        if x2 <= x1 or y2 <= y1:
            return 0.0

        gray = cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
        face_brightness = float(gray[y1:y2, x1:x2].mean())

        # Expand bbox by 70% to sample the surrounding screen/background
        fw, fh = x2 - x1, y2 - y1
        pad = int(max(fw, fh) * 0.70)
        sx1, sy1 = max(0, x1 - pad), max(0, y1 - pad)
        sx2, sy2 = min(w, x2 + pad), min(h, y2 + pad)

        region = gray[sy1:sy2, sx1:sx2]
        # Build mask that excludes the face itself
        mask = np.ones(region.shape, dtype=bool)
        ry1, ry2 = y1 - sy1, y2 - sy1
        rx1, rx2 = x1 - sx1, x2 - sx1
        mask[max(0, ry1):ry2, max(0, rx1):rx2] = False
        bg = region[mask]
        if len(bg) < 200:
            return 0.0

        surround_mean = float(bg.mean())
        surround_std  = float(bg.std())

        # Cue 1: surroundings nearly as bright as the face — screen backlight
        # Real person: face much brighter than dark room/clothing (ratio 0.3–0.6)
        # Phone screen: surrounding screen area nearly as bright (ratio 0.7–1.1)
        bright_ratio = surround_mean / (face_brightness + 1e-6)
        bright_score = min(1.0, max(0.0, (bright_ratio - 0.60) / 0.45))

        # Cue 2: surroundings are spatially uniform — screen backlight is even
        # Real background: walls/clothing have natural texture (std 30–60)
        # Screen border region: very even illumination (std 10–25)
        uniform_score = min(1.0, max(0.0, 1.0 - surround_std / 30.0))

        return float(bright_score * 0.60 + uniform_score * 0.40)

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
        # Phone/tablet screens viewed through a budget camera appear extremely
        # sharp (lap_var often 400-1200). Real faces on cheap sensors are softer
        # (lap_var typically 60-280). Penalise excess sharpness so screens don't
        # score higher than live faces on this cue.
        if lap_var > 350.0:
            lap_score *= max(0.0, 1.0 - (lap_var - 350.0) / 600.0)

        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mean = float(np.sqrt(gx ** 2 + gy ** 2).mean())
        grad_score = min(1.0, grad_mean / 22.0)
        # Same excess-sharpness penalty for gradient magnitude
        if grad_mean > 25.0:
            grad_score *= max(0.0, 1.0 - (grad_mean - 25.0) / 35.0)

        hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
        sat_score = min(1.0, float(hsv[:, :, 1].std()) / 32.0)

        # FFT high-frequency ratio — screen replays add regular moiré energy
        # NOTE: heavy H.264 compression (V380 etc.) kills moiré, so this cue
        # is weak on budget cameras — compensated by lum_score below.
        f = np.fft.fftshift(np.fft.fft2(gray))
        mag = np.abs(f)
        cy, cx = mag.shape[0] // 2, mag.shape[1] // 2
        mask = np.ones_like(mag); mask[cy - 8:cy + 8, cx - 8:cx + 8] = 0
        hf_ratio = float((mag * mask).sum() / (mag.sum() + 1e-6))
        hf_score = min(1.0, hf_ratio * 1.4)

        # Luminance patch variance — screen backlight is spatially uniform;
        # real faces have patchy shadows from natural/indoor lighting.
        # Divide face into 4x4 blocks, compute std of block-mean luminance.
        # Low std = uniform illumination = likely a screen.
        block_means = []
        bh, bw = gray.shape[0] // 4, gray.shape[1] // 4
        for r in range(4):
            for c in range(4):
                block = gray[r*bh:(r+1)*bh, c*bw:(c+1)*bw]
                block_means.append(float(block.mean()))
        lum_std = float(np.std(block_means))
        # Real face under normal lighting: lum_std ~ 20-50. Screen: < 15.
        # Tighter normalisation (÷18 instead of ÷25) so screen values cluster low.
        lum_score = min(1.0, lum_std / 18.0)

        # Weight shift: sharpness cues (lap, grad) are DOWN because phone screens
        # outscore real faces on them; lum_score is UP as the strongest screen cue.
        return float(
            lap_score  * 0.15   # was 0.28 — reduced: screens too sharp on budget cams
            + grad_score * 0.10  # was 0.22 — same reason
            + sat_score  * 0.13  # was 0.15
            + hf_score   * 0.10  # unchanged
            + lum_score  * 0.52  # was 0.25 — dominant cue: screens are illumination-uniform
        )
