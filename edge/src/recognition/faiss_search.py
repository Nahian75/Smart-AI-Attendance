"""FAISS cosine-similarity index over enrolled embeddings (synced from backend).

Uses top-K neighbour aggregation: a query is matched against the K nearest
enrolled embeddings, and the candidate employee's score is the MEAN similarity
of their embeddings within that neighbourhood. This is far more robust than a
single top-1 lookup because every person is enrolled with several photos —
a single lucky/unlucky embedding can't dominate the decision.
"""
import numpy as np
from collections import defaultdict


class FaissSearch:
    def __init__(self, threshold: float = 0.82, top_k: int = 5):
        import faiss
        self.faiss = faiss
        self.threshold = threshold
        self.top_k = top_k
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

    def search_raw(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """Return the best-matching (employee_id, score) WITHOUT applying the
        threshold. score = mean cosine similarity of that employee's embeddings
        among the K nearest neighbours. Used by the multi-frame voting layer,
        which applies the threshold on the aggregate decision instead.
        """
        index, id_map = self._state
        if index is None or index.ntotal == 0:
            return None, 0.0

        k = min(self.top_k, index.ntotal)
        q = embedding.astype(np.float32).reshape(1, -1)
        sims, idx = index.search(q, k)
        sims, idx = sims[0], idx[0]

        per_emp: dict[str, list[float]] = defaultdict(list)
        for sim, i in zip(sims, idx):
            if i < 0:
                continue
            per_emp[id_map[int(i)]].append(float(sim))

        if not per_emp:
            return None, 0.0

        best_emp, best_score = None, -1.0
        for emp_id, emp_sims in per_emp.items():
            score = float(np.mean(emp_sims))
            if score > best_score:
                best_emp, best_score = emp_id, score
        return best_emp, best_score

    def search(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """Thresholded single-shot match. Returns (employee_id, score) if the
        best candidate clears the threshold, else (None, best_score)."""
        best_emp, best_score = self.search_raw(embedding)
        if best_emp is None or best_score < self.threshold:
            return None, best_score
        return best_emp, best_score
