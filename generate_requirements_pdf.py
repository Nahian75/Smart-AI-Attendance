#!/usr/bin/env python3
"""Generate a comprehensive A-Z requirements PDF for the Smart Attendance System."""

from fpdf import FPDF
import os

class ReqPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 8, "Smart Attendance Solution - A-Z Requirements Document", align="C")
            self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(29, 158, 117)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(29, 158, 117)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_text_color(0, 0, 0)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text, indent=10):
        self.set_font("Helvetica", "", 10)
        self.cell(indent)
        self.cell(5, 5.5, "-")
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def key_value(self, key, val, kw=50):
        self.set_font("Helvetica", "B", 10)
        self.cell(kw, 6, key)
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 6, val)
        self.ln(0.5)


pdf = ReqPDF()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)

# --- Cover Page ---
pdf.add_page()
pdf.ln(50)
pdf.set_font("Helvetica", "B", 28)
pdf.set_text_color(29, 158, 117)
pdf.cell(0, 15, "Smart Attendance Solution", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 16)
pdf.set_text_color(80, 80, 80)
pdf.cell(0, 12, "Complete A-to-Z Requirements Document", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(10)
pdf.set_font("Helvetica", "", 11)
pdf.cell(0, 8, "Hardware  |  Software  |  Plugins  |  Dependencies  |  Infrastructure", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(40)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 8, "Generated: June 2026", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 8, "Version: 1.0", align="C", new_x="LMARGIN", new_y="NEXT")

# --- Table of Contents ---
pdf.add_page()
pdf.set_font("Helvetica", "B", 18)
pdf.set_text_color(29, 158, 117)
pdf.cell(0, 12, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
toc = [
    "1. System Overview",
    "2. Hardware Requirements",
    "3. Software Requirements",
    "4. AI/ML Models & Plugins",
    "5. Python Dependencies (Backend)",
    "6. Python Dependencies (Edge Node)",
    "7. Node.js Dependencies (Frontend)",
    "8. Docker & Containerization",
    "9. Infrastructure & Orchestration",
    "10. Networking & Reverse Proxy",
    "11. Database Requirements",
    "12. Caching & Message Queue",
    "13. Storage Requirements",
    "14. Environment Configuration",
    "15. Security Requirements",
    "16. Deployment Scripts",
    "17. GPU & Accelerator Requirements",
    "18. Camera & Streaming Requirements",
]
pdf.set_font("Helvetica", "", 11)
for item in toc:
    pdf.cell(10)
    pdf.cell(0, 7, item, new_x="LMARGIN", new_y="NEXT")

# ============================================================
# SECTION 1: System Overview
# ============================================================
pdf.add_page()
pdf.section_title("1. System Overview")
pdf.body_text(
    "The Smart Attendance Solution is a production-grade, AI-powered attendance management "
    "system that uses real-time facial recognition for employee check-in/out. It processes "
    "live RTSP camera streams at the edge (GPU-accelerated), matches faces against enrolled "
    "employees using ArcFace embeddings, and provides a full-featured web dashboard for "
    "administration, reporting, and real-time monitoring."
)
pdf.sub_title("Architecture Layers")
layers = [
    "Edge Node (GPU/CUDA): YOLOv11 person detection + ArcFace recognition + ByteTrack tracking",
    "Backend API (Python/FastAPI): REST + WebSocket server, business logic, Celery tasks",
    "Database Layer: PostgreSQL 16 + pgvector (face embeddings), Redis 7 (caching + pub/sub)",
    "Frontend (Next.js 15 / React 19): Dashboard, live feed, analytics, camera management",
    "Infrastructure: Docker Compose (dev) / Kubernetes (prod), Nginx reverse proxy",
]
for l in layers:
    pdf.bullet(l)

# ============================================================
# SECTION 2: Hardware Requirements
# ============================================================
pdf.add_page()
pdf.section_title("2. Hardware Requirements")

pdf.sub_title("2.1 Server / Backend Hardware")
pdf.body_text("Minimum specifications for the backend server (running Docker/Postgres/Redis/FastAPI):")
rows = [
    ("CPU:", "4+ cores (x86_64 / ARM64)"),
    ("RAM:", "8 GB minimum, 16 GB recommended"),
    ("Storage:", "50 GB SSD (for Docker images, volumes, snapshots)"),
    ("Network:", "1 Gbps Ethernet"),
    ("OS:", "Linux (Ubuntu 22.04+/Debian 12), Windows 10+ Pro with Docker Desktop, macOS"),
]
for k, v in rows:
    pdf.key_value(f"  {k}", v, kw=35)

pdf.ln(4)
pdf.sub_title("2.2 Edge Node Hardware (GPU Required)")
pdf.body_text("Dedicated machine for real-time video processing. Runs YOLOv11 + ArcFace on camera streams.")
rows = [
    ("GPU:", "NVIDIA GPU with 6+ GB VRAM (GTX 1660, RTX 3060/4060, A4000, or better)"),
    ("", "  NVIDIA Jetson Orin/AGX (for edge deployments)"),
    ("CUDA Cores:", "2,000+ recommended for multi-camera setups"),
    ("VRAM:", "6 GB minimum, 8 GB+ for 4+ concurrent cameras"),
    ("CPU:", "4+ cores"),
    ("RAM:", "8 GB minimum, 16 GB recommended"),
    ("Storage:", "20 GB SSD (models, config, snapshots)"),
    ("Network:", "1 Gbps Ethernet (for RTSP streams + API communication)"),
]
for k, v in rows:
    pdf.key_value(f"  {k}", v, kw=35)

pdf.ln(4)
pdf.sub_title("2.3 Camera Requirements")
rows = [
    ("Type:", "IP Cameras with RTSP stream support"),
    ("Resolution:", "720p minimum, 1080p recommended (1920x1080)"),
    ("Frame Rate:", "15-30 FPS"),
    ("Protocol:", "RTSP (Real-Time Streaming Protocol)"),
    ("Placement:", "Entry/exit points, hallways, reception areas"),
    ("Lighting:", "Adequate ambient lighting or IR illumination for low-light conditions"),
    ("Angle:", "Front-facing, clear view of the face, 1-3 meters distance"),
]
for k, v in rows:
    pdf.key_value(f"  {k}", v, kw=40)

pdf.ln(4)
pdf.sub_title("2.4 Network Requirements")
rows = [
    ("Bandwidth:", "100+ Mbps local network (for HD RTSP streams)"),
    ("Latency:", "< 10 ms between edge node and cameras (local LAN)"),
    ("Connectivity:", "Edge node <-> Backend API via HTTP/WebSocket on LAN or VPN"),
]
for k, v in rows:
    pdf.key_value(f"  {k}", v, kw=40)

# ============================================================
# SECTION 3: Software Requirements
# ============================================================
pdf.add_page()
pdf.section_title("3. Software Requirements")

pdf.sub_title("3.1 Operating Systems")
os_list = [
    "Backend Server: Ubuntu 22.04+ / Debian 12 / Windows 10+ Pro (Docker) / macOS",
    "Edge Node: Ubuntu 22.04+ (with NVIDIA drivers) or NVIDIA JetPack (Jetson)",
    "Development: Any OS with Docker Desktop installed",
    "Client: Any modern web browser (Chrome 120+, Firefox 120+, Edge 120+)",
]
for o in os_list:
    pdf.bullet(o)

pdf.sub_title("3.2 Core Runtimes")
runtimes = [
    "Python 3.12+ (Backend API server)",
    "Python 3.11+ (Edge node - CPU fallback)",
    "Node.js 20+ (Frontend build and development)",
    "Docker Engine 24+ with Docker Compose v2+",
    "Docker Desktop 4.25+ (Windows/macOS development)",
]
for r in runtimes:
    pdf.bullet(r)

pdf.sub_title("3.3 Infrastructure Software")
infra = [
    "Docker Compose (for local development and testing)",
    "Kubernetes 1.28+ (production deployment, optional)",
    "Nginx 1.24+ (reverse proxy, load balancing)",
    "Helm 3 (Kubernetes package manager, optional)",
    "Kubectl (Kubernetes CLI, optional)",
]
for i in infra:
    pdf.bullet(i)

pdf.sub_title("3.4 Monitoring & Observability")
mon = [
    "Prometheus client library (built-in /metrics endpoint)",
    "Docker logs / Kubernetes logging (fluentd, Loki, or similar)",
    "PostgreSQL monitoring (pg_stat_statements, pgBadger)",
    "GPU monitoring: nvidia-smi, DCGM (for edge nodes)",
]
for m in mon:
    pdf.bullet(m)

# ============================================================
# SECTION 4: AI/ML Models & Plugins
# ============================================================
pdf.add_page()
pdf.section_title("4. AI/ML Models & Plugins")

pdf.sub_title("4.1 Object Detection - YOLOv11 (Ultralytics)")
yolo = [
    "Model: yolo11s.pt (default, balanced speed/accuracy)",
    "Alternatives: yolo11n.pt (Jetson/low-power), yolo11m.pt (higher accuracy)",
    "Input size: 640x640 pixels",
    "Confidence threshold: 0.45",
    "IOU threshold: 0.50",
    "Framework: Ultralytics 8.3.55 (PyTorch backend)",
    "Auto-downloaded on first run, cached in Docker volume (edge_yolo)",
]
for y in yolo:
    pdf.bullet(y)

pdf.sub_title("4.2 Face Detection & Recognition - InsightFace (ArcFace)")
arcface = [
    "Model pack: buffalo_l (contains SCRFD face detector + ArcFace R100 recognizer)",
    "Detection input size: 640x640 pixels",
    "Embedding dimension: 512 (output vector)",
    "Similarity metric: Cosine similarity (inner product in FAISS)",
    "Framework: InsightFace 0.7.3 + ONNX Runtime",
    "Model size: ~500 MB (buffalo_l pack)",
    "Auto-downloaded on first use, cached in Docker volume (edge_models)",
]
for a in arcface:
    pdf.bullet(a)

pdf.sub_title("4.3 Object Tracking - ByteTrack / BoT-SORT")
track = [
    "Built into Ultralytics, configured via bytetrack.yaml or botsort.yaml",
    "ByteTrack: Default tracker, good balance of accuracy and speed",
    "BoT-SORT: Higher accuracy, slightly more compute-intensive",
    "Re-identification: Appearance-based feature matching across frames",
]
for t in track:
    pdf.bullet(t)

pdf.sub_title("4.4 Vector Similarity Search")
vec = [
    "pgvector 0.3.6 (PostgreSQL extension for HNSW index on face embeddings)",
    "FAISS (CPU) IndexFlatIP on edge node for local matching",
    "Cosine distance threshold: 0.50 (test) / 0.82 (production)",
    "Edge node FAISS index auto-syncs from backend every 60 seconds",
]
for v in vec:
    pdf.bullet(v)

pdf.sub_title("4.5 Anti-Spoofing Plugin (Optional)")
spoof = [
    "Type: ONNX-based liveness detection model (not yet bundled)",
    "When available, place at edge/config/models/antispoof.onnx",
    "Configure via camera_config.yaml: antispoof_model path",
    "Without model: pass-through mode (assumes all detections are live)",
    "Liveness threshold: 0.80 (when model is configured)",
]
for s in spoof:
    pdf.bullet(s)

pdf.sub_title("4.6 ONNX Runtime")
onnx = [
    "Edge (GPU): onnxruntime-gpu 1.20.1 (CUDA 12.x execution provider)",
    "Edge (CPU fallback): onnxruntime 1.19.2",
    "Backend: onnxruntime 1.19.2 (CPU, for face enrollment embedding)",
    "TensorRT support available (precision: FP16, requires .engine export)",
]
for o in onnx:
    pdf.bullet(o)

# ============================================================
# SECTION 5: Python Dependencies (Backend)
# ============================================================
pdf.add_page()
pdf.section_title("5. Python Dependencies - Backend (requirements.txt)")

pdf.sub_title("5.1 Web Framework & ASGI Server")
for pkg, ver, desc in [
    ("fastapi", "0.115.6", "Async Python web framework with OpenAPI/Swagger docs"),
    ("uvicorn[standard]", "0.34.0", "ASGI server with uvloop, httptools, WebSocket support"),
    ("pydantic", "2.10.4", "Data validation & settings management"),
    ("pydantic-settings", "2.7.0", "Environment-variable-based configuration"),
    ("email-validator", "2.2.0", "Email address validation"),
    ("python-dotenv", "1.0.1", ".env file loading"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("5.2 Database & ORM")
for pkg, ver, desc in [
    ("sqlalchemy[asyncio]", "2.0.36", "Async SQL ORM with PostgreSQL support"),
    ("asyncpg", "0.30.0", "PostgreSQL async database driver"),
    ("alembic", "1.14.0", "Database migration management"),
    ("pgvector", "0.3.6", "pgvector client for vector similarity search"),
    ("redis", "5.2.1", "Redis client for caching, pub/sub, and Celery broker"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("5.3 Task Queue & Event Streaming")
for pkg, ver, desc in [
    ("celery", "5.4.0", "Distributed task queue (scheduled & async tasks)"),
    ("aiokafka", "0.12.0", "Async Kafka producer for event streaming"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("5.4 AI / Computer Vision")
for pkg, ver, desc in [
    ("insightface", "0.7.3", "Face detection (SCRFD) + recognition (ArcFace R100)"),
    ("onnxruntime", "1.19.2", "ONNX inference engine (CPU, backend face enrollment)"),
    ("opencv-python-headless", "4.10.0.84", "OpenCV image processing (headless/stateless)"),
    ("numpy", "2.2.1", "Numerical computation"),
    ("pillow", "11.1.0", "Image processing library"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("5.5 Auth & Security")
for pkg, ver, desc in [
    ("python-jose[cryptography]", "3.3.0", "JWT token creation & validation"),
    ("passlib[bcrypt]", "1.7.4", "Password hashing with bcrypt backend"),
    ("bcrypt", "4.0.1", "Native bcrypt implementation"),
    ("cryptography", "44.0.0", "Fernet encryption for face data at rest"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("5.6 Other Backend Dependencies")
for pkg, ver, desc in [
    ("python-multipart", "0.0.20", "Multipart form parsing (face enrollment uploads)"),
    ("httpx", "0.28.1", "Async HTTP client for external API calls"),
    ("pytz", "2024.2", "Timezone database"),
    ("prometheus-client", "0.21.1", "Metrics exposition at /metrics endpoint"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

# ============================================================
# SECTION 6: Python Dependencies (Edge Node)
# ============================================================
pdf.add_page()
pdf.section_title("6. Python Dependencies - Edge Node (requirements.txt)")

pdf.sub_title("6.1 AI / Computer Vision (Edge)")
for pkg, ver, desc in [
    ("ultralytics", "8.3.55", "YOLOv11 detection + ByteTrack/BoT-SORT tracking"),
    ("insightface", "0.7.3", "ArcFace R100 face recognition + SCRFD detection"),
    ("onnxruntime-gpu", "1.20.1", "GPU-accelerated ONNX inference (CUDA 12.x)"),
    ("opencv-python", "4.10.0.84", "OpenCV with full GUI support (for RTSP capture)"),
    ("numpy", "2.2.1", "Numerical computation"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("6.2 Edge Supporting Libraries")
for pkg, ver, desc in [
    ("faiss-cpu", "1.9.0", "Vector similarity search for face embedding gallery"),
    ("redis", "5.2.1", "Redis client for event pub/sub"),
    ("aiokafka", "0.12.0", "Async Kafka producer for event streaming"),
    ("httpx", "0.28.1", "Async HTTP client for backend API communication"),
    ("pyyaml", "6.0.2", "YAML configuration file parsing"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("6.3 Edge GPU Base Image Notes")
notes = [
    "GPU Dockerfile uses nvcr.io/nvidia/pytorch:24.10-py3 (CUDA 12.x, cuDNN, TensorRT)",
    "Requires numpy<2.0 for ABI compatibility with NVIDIA's prebuilt OpenCV .so",
    "Pre-installed opencv-python is removed and reinstalled cleanly",
    "CPU onnxruntime is uninstalled and replaced with onnxruntime-gpu",
]
for n in notes:
    pdf.bullet(n)

# ============================================================
# SECTION 7: Node.js Dependencies (Frontend)
# ============================================================
pdf.add_page()
pdf.section_title("7. Node.js Dependencies - Frontend (package.json)")

pdf.sub_title("7.1 Runtime Dependencies")
for pkg, ver, desc in [
    ("next", "15.1.3", "React framework with SSR, SSG, file-based routing"),
    ("react", "19.0.0", "UI component library"),
    ("react-dom", "19.0.0", "React DOM renderer"),
    ("recharts", "2.15.0", "Analytics charts and graphs (bar, line, pie)"),
    ("lucide-react", "0.469.0", "Icon component library"),
    ("clsx", "2.1.1", "Conditional CSS class name utility"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("7.2 Development Dependencies")
for pkg, ver, desc in [
    ("typescript", "5.7.2", "TypeScript compiler and type checking"),
    ("@types/node", "22.10.2", "Node.js type definitions"),
    ("@types/react", "19.0.2", "React type definitions"),
    ("@types/react-dom", "19.0.2", "ReactDOM type definitions"),
    ("tailwindcss", "3.4.17", "Utility-first CSS framework"),
    ("postcss", "8.4.49", "CSS post-processor (required by TailwindCSS)"),
    ("autoprefixer", "10.4.20", "CSS vendor prefix auto-insertion"),
]:
    pdf.bullet(f"{pkg} {ver} - {desc}")

pdf.sub_title("7.3 Build & Runtime Configuration")
cfg = [
    "Next.js output: standalone (self-contained deployment artifact)",
    "TypeScript target: ES2022, strict mode enabled",
    "Module resolution: bundler, path alias @/* maps to ./src/*",
    "Styling: TailwindCSS with custom brand colors (#1D9E75 / #0F6E56)",
    "Docker build: Multi-stage (node:20-alpine builder -> node:20-alpine runner)",
]
for c in cfg:
    pdf.bullet(c)

# ============================================================
# SECTION 8: Docker & Containerization
# ============================================================
pdf.add_page()
pdf.section_title("8. Docker & Containerization")

pdf.sub_title("8.1 Required Container Images")
images = [
    ("pgvector/pgvector:pg16", "PostgreSQL 16 with pgvector extension"),
    ("redis:7-alpine", "Redis 7 cache, pub/sub, and Celery broker"),
    ("nginx:alpine", "Reverse proxy and load balancer"),
    ("nvcr.io/nvidia/pytorch:24.10-py3", "NVIDIA CUDA 12.x base (edge GPU)"),
    ("python:3.12-slim", "Backend Python runtime"),
    ("python:3.11-slim", "Edge CPU fallback runtime"),
    ("node:20-alpine", "Frontend build and runtime"),
]
for img, desc in images:
    pdf.bullet(f"{img}  -  {desc}")

pdf.sub_title("8.2 Docker Compose Services (8 Total)")
services = [
    "postgres: Database server with health check + persistent volume",
    "redis: Cache with password auth + LRU eviction policy (2GB max)",
    "backend: FastAPI server, builds from ./backend, depends on healthy postgres+redis",
    "celery_worker: Task execution, builds from ./backend, 4 concurrent workers",
    "celery_beat: Scheduled task scheduler, builds from ./backend",
    "frontend: Next.js UI, builds from ./frontend, depends on backend",
    "edge_node: GPU-accelerated video processing, builds from ./edge, NVIDIA GPU reservation",
    "nginx: Reverse proxy routing to backend/frontend/edge on port 80",
]
for s in services:
    pdf.bullet(s)

pdf.sub_title("8.3 Docker Volumes (5 Persistent Volumes)")
volumes = [
    ("postgres_data", "/var/lib/postgresql/data", "All database tables and indexes"),
    ("redis_data", "/data", "Redis RDB persistence"),
    ("snapshots", "/app/snapshots", "Face snapshots (shared backend + edge)"),
    ("edge_models", "/root/.insightface", "InsightFace buffalo_l model pack (~500 MB)"),
    ("edge_yolo", "/root/.config/Ultralytics", "YOLOv11 model weights"),
]
for vol, mount, purpose in volumes:
    pdf.bullet(f"{vol} -> {mount} ({purpose})")

# ============================================================
# SECTION 9: Infrastructure & Orchestration
# ============================================================
pdf.add_page()
pdf.section_title("9. Infrastructure & Orchestration")

pdf.sub_title("9.1 Development Setup")
dev = [
    "Docker Compose (single-machine, all-in-one deployment)",
    "Quick start: docker compose up --build",
    "Windows helper: start.bat (checks Docker, starts services, opens browser)",
    "Shutdown: docker compose down (preserves volumes/data)",
    "Windows helper: stop.bat (docker compose down with data preservation notice)",
]
for d in dev:
    pdf.bullet(d)

pdf.sub_title("9.2 Production Setup (Kubernetes)")
k8s = [
    "Backend: 3 replicas (default), HPA autoscales 3-20 @ 70% CPU",
    "Backend resources: request 500m CPU/512Mi RAM, limit 2 CPU/2Gi RAM",
    "Edge: DaemonSet (one pod per GPU-equipped node)",
    "Edge network: hostNetwork: true (for RTSP LAN access)",
    "Edge node selector: hardware: gpu",
    "Secrets: K8s SecretRef (attendance-secrets) for all environment variables",
    "Health checks: Liveness probe on /health (port 8000), 15s delay, 20s interval",
]
for k in k8s:
    pdf.bullet(k)

pdf.sub_title("9.3 Makefile Commands")
make_cmds = [
    ("make dev", "docker compose up --build"),
    ("make down", "docker compose down"),
    ("make seed", "Run database seeder inside backend container"),
    ("make test", "Run pytest suite (backend)"),
    ("make logs", "Tail backend container logs"),
    ("make models", "Download edge AI models (YOLO + InsightFace)"),
    ("make build-prod", "Build production images"),
    ("make deploy-k8s", "kubectl apply -f infra/k8s/"),
]
for cmd, desc in make_cmds:
    pdf.key_value(f"  {cmd}", desc, kw=70)

# ============================================================
# SECTION 10: Networking & Reverse Proxy
# ============================================================
pdf.add_page()
pdf.section_title("10. Networking & Reverse Proxy")

pdf.sub_title("10.1 Port Mapping")
ports = [
    ("80", "Nginx reverse proxy (entry point for all traffic)"),
    ("3000", "Frontend Next.js dev server (direct access)"),
    ("5432", "PostgreSQL database (internal only)"),
    ("6379", "Redis cache (internal only)"),
    ("8000", "Backend FastAPI server + WebSocket"),
    ("8001", "Edge node MJPEG stream server"),
]
for port, desc in ports:
    pdf.key_value(f"  {port}", desc, kw=35)

pdf.sub_title("10.2 Nginx Routes")
routes = [
    ("/api/", "backend:8000 (REST API proxy)"),
    ("/ws/", "backend:8000 (WebSocket proxy with Upgrade headers)"),
    ("/metrics", "backend:8000 (Prometheus metrics endpoint)"),
    ("/stream/", "edge_node:8001 (Live MJPEG, buffering off, 3600s timeout)"),
    ("/", "frontend:3000 (Default -> Next.js frontend)"),
]
for loc, desc in routes:
    pdf.key_value(f"  {loc}", desc, kw=40)

# ============================================================
# SECTION 11: Database Requirements
# ============================================================
pdf.add_page()
pdf.section_title("11. Database Requirements")

pdf.sub_title("11.1 Database Engine")
db = [
    "PostgreSQL 16 with pgvector extension (vector similarity search)",
    "Extensions: uuid-ossp (UUID generation), vector (pgvector HNSW index)",
    "Connection pool: 20 connections (configurable), async driver (asyncpg)",
    "Bootstrap SQL: CREATE EXTENSION IF NOT EXISTS for uuid-ossp and vector",
]
for d in db:
    pdf.bullet(d)

pdf.sub_title("11.2 Database Tables (13 Tables)")
tables = [
    "tenants - Multi-tenant organization data (slug, plan, settings JSON)",
    "branches - Physical branch locations (timezone, geo-coordinates, radius)",
    "employees - Employee records (code, name, status, blacklist, VIP flags)",
    "face_embeddings - ArcFace 512-d vectors with pgvector index",
    "cameras - Camera configurations (RTSP URL, direction, zone, role, JSON config)",
    "shifts - Shift definitions (start/end time, work days array)",
    "employee_shifts - Employee-shift assignments (composite PK, effective from)",
    "attendance_logs - Check-in/out records (timestamps, status, hours)",
    "recognition_events - Raw face recognition events (confidence, snapshot, raw JSON)",
    "alerts - Security and violation alerts (type, severity, snapshot)",
    "unknown_detections - Unrecognized person detections (snapshot, confidence)",
    "users - System user accounts (email, hashed password, role, tenant FK)",
    "audit_logs - Audit trail (action, old/new values JSON, IP address)",
]
for t in tables:
    pdf.bullet(t)

pdf.sub_title("11.3 Data Retention")
retention = [
    "Recognition events: Auto-purged after 90 days (EVENT_RETENTION_DAYS)",
    "Celery scheduled task: apply_retention runs daily at 02:00",
    "Face data: Deletable via GDPR-compliant API endpoint",
]
for r in retention:
    pdf.bullet(r)

# ============================================================
# SECTION 12: Caching & Message Queue
# ============================================================
pdf.add_page()
pdf.section_title("12. Caching & Message Queue")

pdf.sub_title("12.1 Redis 7 (3 Roles)")
roles = [
    ("Cache:", "Live event buffers (List), occupancy counters, cooldown TTLs"),
    ("Pub/Sub:", "Real-time attendance events, alerts, recognition events"),
    ("Celery Broker:", "Task queue and result backend for Celery workers"),
]
for k, v in roles:
    pdf.key_value(f"  {k}", v, kw=50)

pdf.sub_title("12.2 Redis Configuration")
redis_cfg = [
    "Max memory: 2 GB (--maxmemory 2gb)",
    "Eviction policy: allkeys-lru (least recently used)",
    "Authentication: Password via REDIS_PASSWORD env var",
    "Persistence: RDB snapshots (volume: redis_data:/data)",
    "Health check: redis-cli ping with INCR-based check",
]
for r in redis_cfg:
    pdf.bullet(r)

pdf.sub_title("12.3 Celery Task Queue")
celery = [
    "Broker: Redis (same instance, db 0)",
    "Result backend: Redis",
    "Concurrency: 4 workers (configurable)",
    "Scheduled tasks: mark_absentees (23:30 daily), apply_retention (02:00 daily), email_digest (18:00 daily)",
]
for c in celery:
    pdf.bullet(c)

pdf.sub_title("12.4 Kafka Event Bus (Optional)")
kafka = [
    "Client: aiokafka (async producer, installed on backend + edge)",
    "Not required for basic operation (Redis pub/sub is default)",
    "Available for high-throughput event streaming in large deployments",
]
for k in kafka:
    pdf.bullet(k)

# ============================================================
# SECTION 13: Storage Requirements
# ============================================================
pdf.add_page()
pdf.section_title("13. Storage Requirements")
storage = [
    "Database storage: ~1 GB per 100,000 recognition events (projected)",
    "Snapshot storage: ~50 KB per snapshot JPEG, ~500 MB per 10,000 events",
    "AI models: ~500 MB (buffalo_l ArcFace) + ~50 MB (YOLOv11) = ~550 MB total",
    "Docker images: ~10 GB total for all services",
    "SSD recommended for all persistent volumes (database performance critical)",
    "Total minimum: 50 GB SSD, recommended: 100 GB+ SSD",
]
for s in storage:
    pdf.bullet(s)

# ============================================================
# SECTION 14: Environment Configuration
# ============================================================
pdf.add_page()
pdf.section_title("14. Environment Configuration")

pdf.sub_title("14.1 Environment Variables (15 Total)")
env_vars = [
    ("POSTGRES_USER", "attendance (PostgreSQL user)"),
    ("POSTGRES_PASSWORD", "(secret) (PostgreSQL password)"),
    ("POSTGRES_DB", "attendance_db (Database name)"),
    ("REDIS_PASSWORD", "(secret) (Redis auth password)"),
    ("SECRET_KEY", "(hex 256-bit) (JWT signing key)"),
    ("FACE_ENCRYPTION_KEY", "(Fernet key) (Face data encryption)"),
    ("CONFIDENCE_THRESHOLD", "0.50/0.82 (Recognition threshold)"),
    ("COOLDOWN_MINUTES", "5 (Per-person cooldown)"),
    ("EVENT_RETENTION_DAYS", "90 (Auto-purge events after N days)"),
    ("ENVIRONMENT", "production (Runtime label)"),
    ("TENANT_ID", "demo (Tenant identifier)"),
    ("DEVICE", "cuda (Edge compute device)"),
    ("EDGE_TOKEN", "(optional) (Edge auth token)"),
    ("NEXT_PUBLIC_API_URL", "http://localhost:8000 (Frontend API URL)"),
    ("NEXT_PUBLIC_WS_URL", "ws://localhost:8000 (Frontend WS URL)"),
]
for var, desc in env_vars:
    pdf.key_value(f"  {var}", desc, kw=65)

pdf.sub_title("14.2 Key Generation Notes")
keys = [
    "SECRET_KEY: Generate with 'openssl rand -hex 32'",
    "FACE_ENCRYPTION_KEY: Generate with Python Fernet.generate_key()",
    "ALL passwords must be changed in production",
    "Kubernetes: Store all env vars in attendance-secrets secret",
]
for k in keys:
    pdf.bullet(k)

# ============================================================
# SECTION 15: Security Requirements
# ============================================================
pdf.add_page()
pdf.section_title("15. Security Requirements")
sec = [
    "Authentication: JWT-based (HS256), 8-hour token expiry",
    "Password hashing: bcrypt via passlib with 12 rounds",
    "Role-based access control: super_admin, admin, hr, manager, security, viewer",
    "Face data encryption: Fernet symmetric encryption at rest",
    "API protection: Bearer token required on all endpoints (except /login and /health)",
    "WebSocket auth: Token passed as ?token= query parameter",
    "Stream endpoints: Token as query parameter for img tag compatibility",
    "Database: Internal network only (not exposed to host in production)",
    "Kubernetes secrets: All credentials via SecretRef, never in images",
    "Audit logging: All mutations tracked in audit_logs table (old/new values, IP)",
    "GDPR compliance: Face data deletion API endpoint available",
    "CSRF: Token-based auth (stateless, no cookies needed)",
]
for s in sec:
    pdf.bullet(s)

# ============================================================
# SECTION 16: Deployment Scripts
# ============================================================
pdf.add_page()
pdf.section_title("16. Deployment Scripts")

pdf.sub_title("16.1 Windows Deployment")
wins = [
    "start.bat: Checks Docker Desktop, runs docker compose up -d, waits for healthy backend, opens browser",
    "stop.bat: Runs docker compose down (preserves volumes)",
    "Prerequisites: Docker Desktop for Windows, Windows 10+ Pro/Enterprise",
]
for w in wins:
    pdf.bullet(w)

pdf.sub_title("16.2 Linux/Mac Deployment")
lin = [
    "docker compose up --build (or make dev)",
    "docker compose down (or make down)",
    "make seed: Initialize database with demo data",
    "make test: Run backend test suite",
    "make logs: Tail backend container logs",
]
for l in lin:
    pdf.bullet(l)

pdf.sub_title("16.3 Kubernetes Deployment")
k8s_deploy = [
    "kubectl apply -f infra/k8s/ (or make deploy-k8s)",
    "Requires: NVIDIA GPU operator installed for GPU scheduling",
    "Edge: DaemonSet deploys to all nodes with label hardware: gpu",
    "HPA: Auto-scales 3-20 backend replicas at 70% CPU",
    "Secrets: Must create attendance-secrets Secret in the namespace",
]
for k in k8s_deploy:
    pdf.bullet(k)

# ============================================================
# SECTION 17: GPU & Accelerator Requirements
# ============================================================
pdf.add_page()
pdf.section_title("17. GPU & Accelerator Requirements")
gpu = [
    "NVIDIA GPU with CUDA Compute Capability 7.0+ (Volta, Turing, Ampere, Ada Lovelace, Hopper)",
    "NVIDIA driver version: 525+ (Linux), 535+ recommended for CUDA 12.x",
    "NVIDIA Container Toolkit (nvidia-docker2) required for GPU access in Docker",
    "CUDA 12.x runtime (provided by nvcr.io/nvidia/pytorch:24.10-py3 base image)",
    "Alternative: CPU mode (device: cpu) for development/testing, ~2-5 FPS per camera",
    "Jetson support: use Dockerfile.edge.cpu with TensorRT and jetson-optimized YOLO models",
    "GPU memory per camera stream: ~1.5 GB at 1080p (YOLO + ArcFace combined)",
    "Recommended GPUs: RTX 3060 (2-3 cameras), RTX 4060 (3-4 cameras), A4000 (4-6 cameras)",
    "Enterprise: NVIDIA A10/A100/H100 for high-density deployments",
]
for g in gpu:
    pdf.bullet(g)

# ============================================================
# SECTION 18: Camera & Streaming Requirements
# ============================================================
pdf.add_page()
pdf.section_title("18. Camera & Streaming Requirements")
stream = [
    "Protocol: RTSP (Real-Time Streaming Protocol) over TCP",
    "Codec: H.264 preferred (H.265 supported but higher decode cost)",
    "Resolution: 1920x1080 (1080p) recommended, 1280x720 minimum",
    "Frame rate: 15 FPS minimum, 25-30 FPS recommended",
    "Authentication: RTSP URL with embedded credentials (rtsp://user:pass@ip:554/stream)",
    "Camera registration: Via web dashboard (no config file editing required)",
    "Fallback: Cameras list in edge/config/camera_config.yaml for startup",
    "Live preview: MJPEG stream via /stream/{camera_id} endpoint with Nginx proxy (buffering off)",
    "GStreamer: Optional hardware decode on Jetson (set use_gstreamer: true)",
    "Edge-to-camera latency target: <200 ms for real-time detection",
    "Edge-to-backend: Events published via Redis pub/sub (sub-second)",
    "WebSocket: Backend pushes to frontend for live dashboard updates",
]
for s in stream:
    pdf.bullet(s)

# --- Save ---
output_path = os.path.join(os.path.dirname(__file__), "Smart_Attendance_System_Requirements.pdf")
pdf.output(output_path)
print(f"PDF generated: {output_path}")
