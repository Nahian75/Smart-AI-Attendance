# Deployment Guide

## Local — Docker Compose

### First run

```bash
cp .env.example .env
```

Fill in these two secrets in `.env`:

```env
SECRET_KEY=<output of: openssl rand -hex 32>
FACE_ENCRYPTION_KEY=<output of: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

Start everything:
```bash
docker compose up -d --build
```

Seed the database (once):
```bash
docker compose exec backend python seed.py
```

Open http://localhost:3000 — sign in as `admin@demo.com` / `admin123`.  
API docs at http://localhost:8000/api/docs.

> No demo employees are seeded. Add real employees and upload face photos via the Employees page.

---

## Edge node

### Camera configuration

Edit `edge/config/camera_config.yaml` before starting:

```yaml
device: cpu            # or "cuda" on NVIDIA hosts
recognition_threshold: 0.50   # raise to 0.80+ in production
cooldown_seconds: 10          # raise to 300 in production
antispoof_model: ~            # set to weights/antispoof.onnx when available

cameras:
  - id: cam-entrance
    rtsp_url: "rtsp://user:pass@192.168.1.10:554/Streaming/Channels/101"
    direction: entrance
    camera_zone: floor_1
    fps_target: 10
  - id: cam-exit
    rtsp_url: "rtsp://user:pass@192.168.1.11:554/Streaming/Channels/101"
    direction: exit
    camera_zone: floor_1
    fps_target: 10
```

### Docker (Linux / macOS / GPU server)

```bash
# CPU build (default — no GPU required)
docker compose up -d edge_node

# GPU build (NVIDIA)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d edge_node
```

The edge node:
1. Logs in automatically using `EDGE_USER` / `EDGE_PASS` env vars (default: `admin@demo.com` / `admin123`)
2. Fetches all enrolled face embeddings from `GET /api/v1/enrollment/export`
3. Builds a FAISS index in memory
4. Opens each camera in `camera_config.yaml`
5. Runs YOLO → ByteTrack → ArcFace → FAISS per frame
6. POSTs attendance events to the backend when a match is found

### Windows host — USB webcam (standalone script)

Docker Desktop on Windows cannot pass USB webcams into Linux containers. Use `edge_standalone.py` instead, which runs natively on Windows:

```powershell
# One-time setup
uv python install 3.11
uv venv --python 3.11 .edge_venv
uv pip install --python .edge_venv\Scripts\python.exe insightface onnxruntime opencv-python numpy httpx

# Run
$env:CAMERA_SRC  = "0"                       # webcam index, or RTSP/HTTP URL
$env:BACKEND_URL = "http://localhost:8000"
$env:REC_THRESH  = "0.50"                    # match threshold
$env:COOLDOWN_S  = "10"                      # seconds between events
.edge_venv\Scripts\python.exe edge_standalone.py
```

`uv` install: https://docs.astral.sh/uv/getting-started/installation/

The standalone script is functionally identical to the Docker edge node — same InsightFace model, same cosine similarity, same API calls.

### Remote / on-site GPU server

```bash
docker build -f edge/Dockerfile.edge.cpu -t attendance-edge ./edge
docker run -d \
  --gpus all \
  --network host \
  -v $(pwd)/edge/config:/app/config:ro \
  -e BACKEND_URL=http://<server-ip>:8000 \
  -e TENANT_ID=<tenant-id> \
  -e EDGE_USER=admin@demo.com \
  -e EDGE_PASS=admin123 \
  attendance-edge
```

Use `Dockerfile.edge` (GPU) instead of `Dockerfile.edge.cpu` for NVIDIA hosts.

### Jetson (arm64)

```bash
# Replace onnxruntime with onnxruntime-jetson in requirements.txt, then:
docker build --platform linux/arm64 -f edge/Dockerfile.edge -t attendance-edge-jetson ./edge
docker run --gpus all --network host -e BACKEND_URL=... attendance-edge-jetson
```

Use `yolo11n.pt` (nano) in `camera_config.yaml` for Jetson Nano/Xavier NX.

---

## Production — Kubernetes

```bash
kubectl apply -f infra/k8s/
```

Key resources:
- **Backend** — `Deployment` + HPA (scales 3–20 replicas on CPU/RPS)
- **Edge** — `DaemonSet` pinned to GPU-labelled nodes with `hostNetwork: true` (needed for LAN camera access)
- **Postgres** — StatefulSet or managed RDS/CloudSQL with `pgvector` extension enabled
- **Redis** — StatefulSet or managed ElastiCache/Memorystore

### Postgres scaling

Enable monthly partitioning for high-volume tables:
```sql
-- recognition_events and attendance_logs can grow to millions of rows
CREATE EXTENSION IF NOT EXISTS pg_partman;
```

### Embedding storage

- **Canonical store** — pgvector in Postgres. Every enrollment writes here.
- **Edge index** — FAISS `IndexFlatIP` built in memory at startup from `GET /enrollment/export`. Sub-millisecond search, no persistence needed.
- **Sync** — edge nodes pull the full index on startup. For live enrollment propagation, restart the edge node (or implement a webhook → edge reload endpoint).

### TLS / HTTPS

Terminate TLS at the nginx reverse proxy or your ingress controller. The backend and edge communicate over the internal Docker network and never need their own TLS in a single-host setup.

---

## Environment variables

### Backend (`backend/.env` or `docker-compose.yml`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://user:pass@postgres:5432/attendance` |
| `REDIS_URL` | yes | `redis://redis:6379/0` |
| `SECRET_KEY` | yes | JWT signing key — `openssl rand -hex 32` |
| `FACE_ENCRYPTION_KEY` | yes | Fernet key for face data encryption |
| `ALLOWED_ORIGINS` | no | CORS origins, comma-separated |

### Edge node

| Variable | Default | Description |
|---|---|---|
| `BACKEND_URL` | `http://backend:8000` | Backend API base URL |
| `EDGE_USER` | `admin@demo.com` | Auto-login email |
| `EDGE_PASS` | `admin123` | Auto-login password |
| `EDGE_TOKEN` | — | Static JWT (skips auto-login if set) |
| `TENANT_ID` | `demo` | Tenant identifier |
| `DEVICE` | `cpu` | `cpu` or `cuda` |
| `LIVENESS_THRESHOLD` | `0.80` | Anti-spoof threshold (overrides yaml) |
