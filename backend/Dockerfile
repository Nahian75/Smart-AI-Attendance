FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download InsightFace buffalo_l model so the first enrollment request
# doesn't block on a ~500 MB download at runtime.
RUN python - <<'EOF'
from insightface.app import FaceAnalysis
a = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
a.prepare(ctx_id=-1, det_size=(640, 640))
print("InsightFace buffalo_l model cached.")
EOF

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
