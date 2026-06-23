"""FAISS cosine-similarity index over enrolled embeddings (synced from backend)."""
import numpy as np


class FaissSearch:
    def __init__(self, threshold: float = 0.82):
        import faiss
        self.faiss = faiss
        self.threshold = threshold
        # index and id_map are swapped together as a single tuple so a resync
        # (called from the asyncio loop thread) can never be observed half-applied
        # by search() (called from the inference worker thread).
        self._state: tuple = (None, [])

    @property
    def index(self):
        return self._state[0]

    @property
    def id_map(self) -> list[str]:
        return self._state[1]

    def build(self, embeddings: np.ndarray, employee_ids: list[str]):
        """embeddings: (N, 512) L2-normalized. Inner product == cosine sim."""
        d = embeddings.shape[1]
        index = self.faiss.IndexFlatIP(d)
        index.add(embeddings.astype(np.float32))
        self._state = (index, employee_ids)

    def search(self, embedding: np.ndarray) -> tuple[str | None, float]:
        index, id_map = self._state
        if index is None or index.ntotal == 0:
            return None, 0.0
        q = embedding.astype(np.float32).reshape(1, -1)
        sims, idx = index.search(q, 1)
        sim = float(sims[0][0])
        if sim < self.threshold:
            return None, sim
        return id_map[int(idx[0][0])], sim
