"""Face enrollment & matching against pgvector store.

In production the heavy ArcFace embedding runs on the edge node. The backend
keeps the canonical embedding store (pgvector) used to rebuild FAISS indexes
that are pushed to edge nodes, plus an HR-side verify/enroll path.
"""
import uuid
from datetime import datetime, timezone
import numpy as np
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Employee, FaceEmbedding


class FaceEnrollmentService:
    def __init__(self, db: AsyncSession, embedder=None):
        self.db = db
        # embedder is injected; on the backend this can call an internal
        # embedding microservice. Falsy => embeddings supplied directly.
        self.embedder = embedder

    async def enroll_embeddings(self, employee_id: uuid.UUID, tenant_id: uuid.UUID,
                                embeddings: list[list[float]], angles: list[str] | None = None) -> dict:
        """Store pre-computed 512-d embeddings for an employee."""
        emp = await self.db.get(Employee, employee_id)
        if not emp:
            raise ValueError("Employee not found")

        angles = angles or [f"angle_{i}" for i in range(len(embeddings))]
        for i, emb in enumerate(embeddings):
            vec = self._normalize(emb)
            self.db.add(FaceEmbedding(
                employee_id=employee_id,
                tenant_id=tenant_id,
                embedding=vec,
                photo_angle=angles[i] if i < len(angles) else None,
                quality_score=0.95,
                is_primary=(i == 0),
            ))

        emp.is_enrolled = True
        emp.face_enrolled_at = datetime.now(timezone.utc)
        emp.embedding_version += 1
        await self.db.commit()
        return {"employee_id": str(employee_id), "embeddings_stored": len(embeddings),
                "version": emp.embedding_version}

    async def extract_and_enroll_image(self, employee_id: uuid.UUID, tenant_id: uuid.UUID, image_bytes: bytes) -> dict:
        """Production path: Decodes uploaded image, extracts embedding, and enrolls the face."""
        if not self.embedder:
            raise RuntimeError("ArcFace embedder is not configured on the backend. Cannot process raw images.")

        import asyncio, cv2
        from concurrent.futures import ThreadPoolExecutor
        from io import BytesIO

        # Apply EXIF orientation before decoding — phone photos are often rotated 90/270°
        # and OpenCV ignores the EXIF tag, causing face detection to fail.
        try:
            from PIL import Image as PILImage, ExifTags
            pil_img = PILImage.open(BytesIO(image_bytes))
            exif = pil_img._getexif() if hasattr(pil_img, "_getexif") else None
            if exif:
                orient_key = next((k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None)
                orientation = exif.get(orient_key) if orient_key else None
                rotations = {3: 180, 6: 270, 8: 90}
                if orientation in rotations:
                    pil_img = pil_img.rotate(rotations[orientation], expand=True)
            pil_img = pil_img.convert("RGB")
            # Resize very large photos — InsightFace works best up to ~1920px
            max_dim = 1920
            w, h = pil_img.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                pil_img = pil_img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)
            img = np.array(pil_img)[:, :, ::-1].copy()  # RGB → BGR for OpenCV/InsightFace
        except Exception:
            # Fall back to plain OpenCV decode if Pillow fails
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Invalid image file provided.")

        # Run CPU-bound inference in a thread so the event loop stays responsive
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            faces = await loop.run_in_executor(pool, self.embedder.detect_and_embed, img)

        if not faces:
            raise ValueError("No face detected in the uploaded image. Please provide a clear, well-lit, front-facing photo.")

        bbox, embedding, det_score = faces[0]
        return await self.enroll_embeddings(employee_id, tenant_id, [embedding], ["frontal"])

    async def match(self, embedding: list[float], tenant_id: uuid.UUID,
                    threshold: float = 0.82) -> tuple[uuid.UUID | None, float]:
        """Nearest-neighbor cosine match against the tenant's embeddings via pgvector."""
        vec = self._normalize(embedding)
        # pgvector cosine distance operator <=> ; similarity = 1 - distance
        stmt = (
            select(FaceEmbedding.employee_id,
                   (1 - FaceEmbedding.embedding.cosine_distance(vec)).label("sim"))
            .where(FaceEmbedding.tenant_id == tenant_id)
            .order_by(FaceEmbedding.embedding.cosine_distance(vec))
            .limit(1)
        )
        row = (await self.db.execute(stmt)).first()
        if row is None:
            return None, 0.0
        emp_id, sim = row[0], float(row[1])
        return (emp_id, sim) if sim >= threshold else (None, sim)

    async def delete_face_data(self, employee_id: uuid.UUID, tenant_id: uuid.UUID):
        """GDPR-compliant deletion of all face data for an employee."""
        await self.db.execute(
            delete(FaceEmbedding).where(
                FaceEmbedding.employee_id == employee_id,
                FaceEmbedding.tenant_id == tenant_id,
            )
        )
        emp = await self.db.get(Employee, employee_id)
        if emp:
            emp.is_enrolled = False
            emp.face_enrolled_at = None
        await self.db.commit()

    @staticmethod
    def _normalize(emb) -> list[float]:
        v = np.asarray(emb, dtype=np.float32)
        n = np.linalg.norm(v)
        return (v / n).tolist() if n > 0 else v.tolist()
