"""
ArcFace embedder for the backend (CPU, lazy-loaded).

Initialises InsightFace directly — no dependency on the edge module.
The model pack (~500 MB) is downloaded from the InsightFace CDN on first
use and cached at ~/.insightface/models/buffalo_l/ inside the container.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class _BackendEmbedder:
    """Thin wrapper around insightface.app.FaceAnalysis with lazy init."""

    def __init__(self):
        self._app = None

    def _load(self):
        if self._app is not None:
            return
        try:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=(640, 640))
            self._app = app
            logger.info("InsightFace buffalo_l model ready (CPU).")
        except Exception as exc:
            logger.error("InsightFace init failed: %s", exc)
            raise RuntimeError(f"ArcFace model failed to load: {exc}") from exc

    def detect_and_embed(self, img: np.ndarray) -> list:
        """
        Detect faces and return embeddings.
        Returns list of (bbox, embedding_list, det_score) tuples.
        """
        self._load()
        faces = self._app.get(img)
        if not faces:
            return []
        results = []
        for face in faces:
            bbox = face.bbox.tolist() if hasattr(face.bbox, "tolist") else list(face.bbox)
            emb = face.embedding.tolist() if hasattr(face.embedding, "tolist") else list(face.embedding)
            score = float(face.det_score) if hasattr(face, "det_score") else 1.0
            results.append((bbox, emb, score))
        return results


try:
    embedder = _BackendEmbedder()
    logger.info("_BackendEmbedder created (model loads on first enrollment call).")
except Exception as _e:
    logger.warning("Could not create _BackendEmbedder: %s", _e)
    embedder = None
