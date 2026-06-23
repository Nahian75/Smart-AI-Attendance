"""InsightFace ArcFace embedding + SCRFD face detection."""
import numpy as np
from ..utils.gpu import detect as detect_gpu


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
        self.app.prepare(ctx_id=ctx_id, det_size=det_size)

    def detect_and_embed(self, crop: np.ndarray):
        """Return list of (bbox, normalized_512d_embedding, det_score)."""
        faces = self.app.get(crop)
        out = []
        for f in faces:
            out.append((f.bbox.astype(int), f.normed_embedding, float(f.det_score)))
        return out
