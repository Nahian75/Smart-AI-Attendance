"""InsightFace ArcFace embedding + SCRFD face detection.

det_size controls the SCRFD face-detector input resolution:
  - Higher det_size → finds smaller/more distant faces but costs more GPU memory
  - Lower det_size → faster, good for close-up cameras or low-res streams

Use auto_det_size() to pick the optimal det_size from the camera's actual resolution
instead of hard-coding a value.
"""
import numpy as np
from ..utils.gpu import detect as detect_gpu


def auto_det_size(camera_width: int, camera_height: int) -> tuple[int, int]:
    """Pick the best SCRFD det_size for a given camera resolution.

    Rule of thumb: a face at typical entry-gate distance covers ~8-15% of
    frame height. SCRFD needs the face to be ≥20px in the resized input to
    detect reliably. So:
        min_det_dim = (face_px_in_frame / frame_height) * det_size ≥ 20px
        → det_size ≥ 20 / 0.10 = 200  (very conservative)

    In practice the camera resolution drives the choice:
        ≥1080p  →  960   (faces are relatively small, need high det res)
        ≥720p   →  640   (good balance)
        ≥480p   →  480   (close-up cameras, low-res streams)
        <480p   →  320   (minimum, very close cameras only)

    All values are multiples of 32 (SCRFD model requirement).
    """
    long_side = max(camera_width, camera_height)

    if long_side >= 1920:
        size = 960
    elif long_side >= 1280:
        size = 640
    elif long_side >= 640:
        size = 480
    else:
        size = 320

    return (size, size)


def probe_camera_resolution(rtsp_url: str, timeout: float = 8.0) -> tuple[int, int] | None:
    """Open the camera briefly, read its resolution, then close it.

    Returns (width, height) or None if the stream could not be opened or
    does not report a resolution (some RTSP cameras return 0×0 until the
    first frame arrives).
    """
    import cv2
    import threading

    result: list[tuple[int, int] | None] = [None]

    def _probe():
        try:
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                # Some streams return 0×0 without reading a frame first
                if w == 0 or h == 0:
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        h, w = frame.shape[:2]
                if w > 0 and h > 0:
                    result[0] = (w, h)
            cap.release()
        except Exception:
            pass

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout)
    return result[0]


class ArcFaceRecognizer:
    def __init__(self, model_name: str = "buffalo_l",
                 device: str = "auto",
                 det_size: tuple[int, int] = (640, 640)):
        import insightface

        gpu = detect_gpu()
        ctx_id = gpu["insightface_ctx"]

        self.app = insightface.app.FaceAnalysis(
            name=model_name,
            providers=gpu["ort_providers"],
        )
        # det_thresh=0.3 — default is 0.5 which misses faces at CCTV/overhead
        # angles where detection confidence is 0.3–0.45. Our min_det_score in
        # FrameProcessor filters out junk below the quality threshold we want.
        self.app.prepare(ctx_id=ctx_id, det_size=det_size, det_thresh=0.3)
        self._det_size = det_size

    @property
    def det_size(self) -> tuple[int, int]:
        return self._det_size

    def detect_and_embed(self, crop: np.ndarray):
        """Return list of (bbox, normalized_512d_embedding, det_score)."""
        faces = self.app.get(crop)
        out = []
        for f in faces:
            out.append((f.bbox.astype(int), f.normed_embedding, float(f.det_score)))
        return out
