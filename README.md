# Smart AI Attendance System

**AI-powered attendance tracking with real-time face recognition, security alerts, and comprehensive analytics.**

Built with **YOLOv11 + ByteTrack + InsightFace (ArcFace R100)**, **FastAPI** backend, **Next.js 15** dashboard, **PostgreSQL + pgvector**, and **Docker**.

---

## Features

- **Real-time Face Recognition** — YOLOv11 + ByteTrack + ArcFace R100 with FAISS vector search
- **Multi-Frame Temporal Voting** — Recognition decided across 7 frames (majority vote + mean similarity), eliminating single-frame flip-flopping
- **Top-K Embedding Matching** — Averages similarity across an employee's multiple enrolled embeddings for robust identification
- **Face-Quality Gating** — Junk crops (blurry, turned away) are skipped before recognition; only high-quality detections count
- **Real Anti-Spoof Model** — Trained MiniFASNet CNN (CelebA-Spoof dataset, AUC-ROC ~0.99) blocks printed-photo and screen-replay attacks
- **Multi-GPU Support** — NVIDIA (CUDA), AMD (ROCm), Intel (OpenVINO/Arc), CPU — auto-detected at startup
- **Security Alerts** — 8 types: intruder, blacklist, after-hours, restricted area, VIP, loitering, spoof attempt, unknown person
- **Real-Time Alert WebSocket** — Alerts appear instantly on dashboard via `/ws/alerts/` (no polling delay)
- **Detection Evidence Log** — Every face detection saved with snapshot, timestamp, confidence score, and camera — verify the AI isn't hallucinating
- **Shift Management** — Create shifts with start/end times, grace periods, and early-leave buffers; late/early-leave/overtime calculated automatically
- **Live Feed** — Shows check-in/check-out, unknown persons, and spoof attempts in real-time
- **Role-Based Access Control** — 6-level hierarchy (super_admin → viewer) enforced on API and UI
- **Self-Service Password Change** — Any user changes their own password from the sidebar
- **Admin Panel** — Add users, change roles, deactivate accounts
- **Occupancy Analytics** — Building-wide and per-zone real-time counters
- **GDPR Compliance** — Tenant-wide data deletion endpoint
- **Dark Mode** — Full dark/light theme toggle, persisted to localStorage
- **CSV Export** — Monthly attendance reports
- **Celery Background Jobs** — Mark absentees, apply data-retention policy, email digest

---

## How It Works

```
Camera (RTSP / IP / USB)
  → Edge node:
      YOLO detect → ByteTrack track → 30% padded crop
      → face-quality gate (det_score ≥ 0.55)
      → anti-spoof check (MiniFASNet, 128×128 ONNX)
      → ArcFace embed (960×960 det_size) → top-K FAISS match
      → multi-frame vote buffer (7 frames, majority wins)
      → decision: recognized / unknown / spoof
  → POST /api/v1/attendance/event  (EDGE_TOKEN auth)
  → Backend: confidence gate → cooldown → shift check → late/early/OT calc → Postgres
  → Redis pub/sub → WebSocket → live dashboard (attendance + alerts channels)
```

---

## Quick Start (Windows)

```
Double-click start.bat
```

- First run: builds images and downloads AI models (~10-20 min, once only)
- Subsequent runs: starts in ~10 seconds, no rebuild, no downloads
- Dashboard opens automatically at **http://localhost:8080**
- Default login: `admin@demo.com` / `admin123`

To stop: double-click `stop.bat`

---

## One-Click Production Deploy

### Windows Server
```
Double-click deploy.bat
— or —
deploy.bat yourdomain.com
deploy.bat --update          # rebuild keeping existing .env secrets
deploy.bat --no-edge         # run without the camera AI node
deploy.bat --gpu nvidia      # force GPU type
```

### Linux / macOS
```bash
git clone <repo> && cd smart-ai-attendance
chmod +x deploy.sh
./deploy.sh                  # auto-detects IP and GPU
./deploy.sh yourdomain.com
./deploy.sh --update
```

The deploy script automatically:
1. Checks Docker is running
2. **Detects GPU type** (NVIDIA/AMD/Intel) and selects the right Dockerfile
3. Detects server public IP (or uses your domain)
4. Generates all secrets (`SECRET_KEY`, `FACE_ENCRYPTION_KEY`, `EDGE_TOKEN`, DB passwords) — shown once, stored in `.env`
5. Builds production images with pre-baked AI models
6. Starts all services, seeds the database, opens dashboard

### GPU Support Matrix

| Hardware | Dockerfile | ONNX Provider | Torch Device |
|---|---|---|---|
| NVIDIA GPU | `Dockerfile.edge` / `Dockerfile.edge.nvidia` | `CUDAExecutionProvider` | `cuda` |
| AMD GPU (ROCm) | `Dockerfile.edge.amd` | `ROCMExecutionProvider` | `cuda` (ROCm compat) |
| Intel Arc / Iris | `Dockerfile.edge.intel` | `OpenVINOExecutionProvider` | `xpu` / `cpu` |
| CPU only | `Dockerfile.edge.cpu` | `CPUExecutionProvider` | `cpu` |

Set `DEVICE=cuda` in `.env` for NVIDIA (auto-detected by `deploy.bat`).

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Storage | 20 GB | 50 GB SSD |
| Docker | 20.10+ | 24.0+ |
| Camera | RTSP / IP / USB | HD IP camera |
| GPU (optional) | Any | NVIDIA RTX / AMD RX 6000+ / Intel Arc |

---

## Default Ports

| Service | Port | Notes |
|---|---|---|
| Dashboard (nginx) | **8080** | Main entry point — `http://localhost:8080` |
| Backend API | 8000 | Direct access (also via nginx `/api/`) |
| Edge MJPEG | 8001 | Camera streams (also via nginx `/stream/`) |
| PostgreSQL | 5432 | |
| Redis | 6379 | |

> Port 80 is reserved by Docker Desktop on Windows. Nginx binds to 8080.

---

## Recognition Tuning

All thresholds are in `edge/config/camera_config.yaml` — **no rebuild needed**, just restart edge node:

```yaml
recognition_threshold: 0.50   # raise for fewer false matches, lower for more recall
liveness_threshold:    0.55   # P(live) below this = spoof (model-based)
min_det_score:         0.55   # skip face crops below this detection quality
vote_window:           7      # frames to collect per person before deciding
min_votes:             4      # minimum good frames needed to decide
vote_ttl_seconds:      5      # drop vote buffer if person unseen for this long
cooldown_seconds:      300    # suppress re-detection of same person for 5 min
```

To apply: `docker compose restart edge_node backend`

**Tips:**
- If enrolled employees are being missed → lower `recognition_threshold` (try 0.45)
- If wrong people are matching → raise `recognition_threshold` (try 0.60)
- Best fix for poor recognition: re-enroll with 3–5 clear front-facing photos under the same lighting as the camera

---

## Dashboard Pages

| Page | Path | Description |
|---|---|---|
| Overview | `/dashboard` | Stat cards, live cameras, occupancy, weekly/hourly charts, recent check-ins, live feed, alerts |
| Employees | `/dashboard/employees` | Employee list, face enrollment, blacklist/VIP flags |
| Cameras | `/dashboard/cameras` | Camera cards with MJPEG streams, add/edit/delete |
| **Detection Log** | `/dashboard/detection-log` | Every face detection: snapshot, timestamp, confidence, camera — verify AI accuracy |
| Alerts | `/dashboard/alerts` | All alert types, unacknowledged filter |
| Security Alerts | `/dashboard/security-alerts` | High-severity incidents + loitering section |
| Shifts | `/dashboard/shifts` | Create/edit shifts, assign employees |
| Analytics | `/dashboard/analytics` | Building occupancy, department breakdown, shift compliance |
| Reports | `/dashboard/reports` | Monthly CSV export |
| Admin | `/dashboard/admin` | User management, role assignment (admin+ only) |

### Live Dashboard (Overview)

The overview page shows three real-time panels:
- **Live Feed** — check-in/check-out events (green), unknown persons (orange), spoof attempts (red), all via WebSocket
- **Security Alerts** — fires instantly via WebSocket when any alert triggers (no 15s polling delay)
- **Detection Evidence Log** — browse every captured face with snapshot thumbnail, click to enlarge

---

## Security Model

### Authentication & Passwords
- All API endpoints (except `POST /auth/login`) require JWT Bearer token
- Tokens signed with `SECRET_KEY` (HS256), expire after `ACCESS_TOKEN_EXPIRE_HOURS` (default 8 h)
- All passwords hashed with **bcrypt** — never stored or logged in plain text

### Role Hierarchy

| Role | Level | Badge | Permissions |
|---|---|---|---|
| `super_admin` | 6 | Purple | Everything |
| `admin` | 5 | Red | Full tenant access |
| `hr` | 4 | Blue | Employees, enrollment, attendance overrides |
| `manager` | 3 | Green | Read-only + face match |
| `security` | 2 | Amber | Read-only + acknowledge alerts |
| `viewer` | 1 | Gray | Read-only dashboard |

### Edge Node Authentication
Edge nodes send `Authorization: Bearer <EDGE_TOKEN>`. In development (`EDGE_TOKEN` empty), check is skipped. In production, missing/wrong token returns 401.

### Rate Limiting
| Path | Limit |
|---|---|
| `POST /api/v1/auth/login` | 30 req / min / IP |
| `POST /api/v1/auth/refresh` | 30 req / min / IP |
| All other endpoints | 200 req / min / IP |

### Face Snapshot Storage & Auto-Purge
Snapshots are stored at `/app/snapshots` (Docker volume). Served at `/snapshots/` via FastAPI StaticFiles — accessible through nginx at `http://localhost:8080/snapshots/`.

**Auto-purge:** A Celery background job runs every night at **3:00 AM** and deletes snapshot image files older than **7 days**. DB records (detection log entries) are kept for **90 days** separately — you can still see the detection event, just without the snapshot image after 7 days.

---

## Shift Time Logic

| Event | Condition | Result |
|---|---|---|
| Check-in | After `start_time + grace_in_min` | Marked **Late** |
| Check-out | Before `end_time - early_out_min` | Marked **Early Leave** |
| Check-out | After `end_time` | **Overtime** seconds recorded |
| Detection | Outside shift days/hours | **After-hours** alert |

Example: Shift 09:00–18:00, grace 10 min, early buffer 15 min
- Late if check-in after **09:10**
- Early leave if check-out before **17:45**
- Overtime if check-out after **18:00**

---

## Adding Employees & Enrolling Faces

1. Go to **Employees** in the dashboard
2. Click **Add Employee** — fill name, code, department, designation, phone
3. Click the **face icon** on the employee row
4. Upload **3–10 clear front-facing photos** taken in the same lighting as your camera
5. The backend extracts a 512-d ArcFace embedding and marks the employee as enrolled

The edge node resyncs embeddings from the backend every 60 seconds — no restart needed.

> **Tip:** More photos = better recognition. Photos taken under the exact same lighting and angle as the camera give significantly higher similarity scores.

---

## Camera Setup

Register cameras via the dashboard Cameras page. The edge node polls the backend every 60 seconds for new cameras.

| Source | URL format |
|---|---|
| IP camera (RTSP) | `rtsp://user:pass@192.168.1.x:554/...` |
| HTTP webcam | `http://192.168.x.x:8080/video` |
| USB webcam (Linux/macOS) | `"0"` or `"1"` |

---

## API Endpoints

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | — | Login; returns JWT |
| POST | `/api/v1/auth/refresh` | — | Refresh JWT |
| POST | `/api/v1/auth/change-password` | JWT | Change own password |

### Attendance
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/attendance/event` | EDGE | Ingest recognition/unknown/spoof event |
| GET | `/api/v1/attendance/summary` | JWT | Daily summary |
| GET | `/api/v1/attendance/logs` | JWT | Paginated log history |
| GET | `/api/v1/attendance/live` | JWT | Last 50 live events (Redis) |
| PATCH | `/api/v1/attendance/logs/{id}` | **[hr]** | Manual override |
| DELETE | `/api/v1/attendance/logs/{id}` | **[hr]** | Delete single log |
| DELETE | `/api/v1/attendance/logs` | **[admin]** | Bulk reset for a date |

### Detection Evidence
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/detections` | JWT | Paginated detection log (recognition + unknown + spoof) |
| GET | `/api/v1/detections/stats` | JWT | Counts by type |
| GET | `/snapshots/{path}` | — | Serve captured face snapshot image |

### Employees
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/employees` | JWT | List employees |
| POST | `/api/v1/employees` | **[hr]** | Create employee |
| PATCH | `/api/v1/employees/{id}` | **[hr]** | Update employee |
| DELETE | `/api/v1/employees/{id}` | **[hr]** | Deactivate |
| POST | `/api/v1/employees/{id}/enroll` | **[hr]** | Upload face photo |
| PATCH | `/api/v1/employees/{id}/blacklist` | **[admin]** | Set/clear blacklist |
| PATCH | `/api/v1/employees/{id}/vip` | **[admin]** | Set/clear VIP |

### Shifts
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/shifts` | JWT | List shifts |
| POST | `/api/v1/shifts` | **[hr]** | Create shift |
| PATCH | `/api/v1/shifts/{id}` | **[hr]** | Update shift |
| DELETE | `/api/v1/shifts/{id}` | **[hr]** | Deactivate shift |
| GET | `/api/v1/shifts/assignments` | JWT | List employee assignments |
| POST | `/api/v1/shifts/assignments` | **[hr]** | Assign shift |
| DELETE | `/api/v1/shifts/assignments/{emp_id}` | **[hr]** | Remove assignment |

### Cameras
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/cameras` | JWT | List active cameras |
| POST | `/api/v1/cameras` | **[admin]** | Add camera |
| PATCH | `/api/v1/cameras/{id}` | **[admin]** | Update settings |
| DELETE | `/api/v1/cameras/{id}` | **[admin]** | Deactivate |
| GET | `/api/v1/cameras/{id}/preview` | JWT | JPEG snapshot |

### Alerts
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/alerts` | JWT | List alerts |
| GET | `/api/v1/alerts/recent` | JWT | Last 50 from Redis |
| POST | `/api/v1/alerts/{id}/acknowledge` | **[security]** | Acknowledge |
| GET | `/api/v1/alerts/config` | **[admin]** | Get thresholds |
| POST | `/api/v1/alerts/config/update` | **[admin]** | Update thresholds |

### Analytics & Reports
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/analytics/occupancy` | JWT | Live occupancy |
| GET | `/api/v1/analytics/hourly` | JWT | Hourly entry/exit chart |
| GET | `/api/v1/analytics/shift-compliance` | JWT | On-time % per employee |
| GET | `/api/v1/analytics/visitors` | JWT | Unknown person count |
| GET | `/api/v1/reports/monthly.csv` | JWT | CSV export |

### WebSocket
| Path | Auth | Description |
|---|---|---|
| `WS /ws/attendance/{tenant_id}?token=...` | JWT (query) | Real-time check-in/out events |
| `WS /ws/alerts/{tenant_id}?token=...` | JWT (query) | Real-time security alerts |

---

## Production Security Checklist

- [ ] `SECRET_KEY` set to a random 64-char hex string
- [ ] `FACE_ENCRYPTION_KEY` set to a generated Fernet key
- [ ] `EDGE_TOKEN` set and matching on edge node
- [ ] `ENVIRONMENT=production`
- [ ] Default admin password changed immediately after first login
- [ ] Postgres and Redis not exposed on public interfaces
- [ ] Nginx configured with SSL
- [ ] Prometheus `/metrics` firewalled to internal network only

---

## Project Structure

```
smart-ai-attendance/
├── backend/
│   ├── app/
│   │   ├── api/v1/          auth, attendance, employees, shifts, cameras,
│   │   │                    alerts, analytics, reports, enrollment, admin,
│   │   │                    rbac, ws (attendance + alerts WebSocket), detections
│   │   ├── core/            security (JWT/bcrypt/RBAC), middleware, exceptions
│   │   ├── models/          SQLAlchemy ORM (User, Employee, Shift, Camera, Alert,
│   │   │                    AttendanceLog, RecognitionEvent, UnknownDetection)
│   │   ├── schemas/         Pydantic I/O schemas
│   │   ├── services/        AttendanceService, AlertService, FaceEnrollmentService
│   │   └── workers/         Celery tasks (mark absentees, retention, digest)
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── seed.py
│
├── edge/
│   ├── src/
│   │   ├── utils/gpu.py        Runtime GPU auto-detection
│   │   ├── detection/          YOLOv11 + ByteTrack person detector
│   │   ├── recognition/
│   │   │   ├── arcface.py      InsightFace ArcFace R100 (det_size=960)
│   │   │   ├── anti_spoof.py   MiniFASNet ONNX model (CelebA-Spoof) + heuristic fallback
│   │   │   └── faiss_search.py Top-K cosine similarity with per-employee mean aggregation
│   │   ├── camera/             RTSP reader, MJPEG server
│   │   └── pipeline/
│   │       ├── frame_processor.py  Multi-frame voting engine, face-quality gating
│   │       └── event_publisher.py  Redis pub/sub + backend POST for all event types
│   ├── config/camera_config.yaml   Tunable thresholds (no rebuild needed)
│   ├── weights/antispoof_128.onnx  MiniFASNet anti-spoof model
│   ├── Dockerfile.edge             NVIDIA CUDA (primary)
│   ├── Dockerfile.edge.amd         AMD ROCm
│   ├── Dockerfile.edge.intel       Intel OpenVINO
│   └── Dockerfile.edge.cpu         CPU only
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   └── dashboard/
│   │   │       ├── page.tsx            Overview (stats, cameras, live feed, alerts)
│   │   │       ├── detection-log/      Evidence log with snapshots
│   │   │       ├── employees/          Employee management + enrollment
│   │   │       ├── cameras/            Camera management + live streams
│   │   │       ├── alerts/             Alert list + acknowledge
│   │   │       ├── security-alerts/    High-severity incident log
│   │   │       ├── shifts/             Shift management + assignments
│   │   │       ├── analytics/          Charts + compliance
│   │   │       ├── reports/            CSV export
│   │   │       └── admin/              User management
│   │   ├── components/
│   │   │   ├── live/
│   │   │   │   ├── LiveEventFeed.tsx   Real-time events (check-in, unknown, spoof)
│   │   │   │   ├── AlertsFeed.tsx      Real-time alerts via WebSocket
│   │   │   │   ├── CameraFeed.tsx      Live MJPEG stream display
│   │   │   │   └── OccupancyCards.tsx  Zone occupancy
│   │   │   └── ui/DashboardShell.tsx   Sidebar + nav
│   │   ├── lib/
│   │   │   ├── api.ts              All API calls
│   │   │   ├── websocket.ts        connectAttendanceWS + connectAlertsWS
│   │   │   └── auth.ts / rbac.ts   Session + role helpers
│   │   └── types/index.ts          TypeScript interfaces
│   └── Dockerfile
│
├── infra/nginx/nginx.conf    Proxies /api/, /ws/, /stream/, /snapshots/ → backend
├── start.bat / stop.bat      Windows one-click start/stop (no rebuild after first run)
├── deploy.bat                Windows production deploy (GPU auto-detect + secrets gen)
├── docker-compose.yml        Main compose (nginx on :8080, CUDA edge)
├── docker-compose.dev.yml    Original dev compose (nginx on :80, CPU edge)
└── docker-compose.prod.yml   Production compose
```

---

## Troubleshooting

**"Could not reach the server" on login**
- Ensure `NEXT_PUBLIC_API_URL=http://localhost:8080` in `.env`
- Rebuild frontend: `docker compose up -d --build frontend`

**Employees detected as unknown**
- Check edge logs: `docker compose logs edge_node | grep -E "sim=|best_sim"`
- If `best_sim` is around 0.4–0.5: lower `recognition_threshold` to 0.45 in `camera_config.yaml`
- Re-enroll employees with 3–5 photos taken under the same lighting as the camera

**Anti-spoof triggering on real people**
- Lower `liveness_threshold` in `camera_config.yaml` (try 0.45)
- Check edge logs for `spoof_score` values

**Face detection failing ("no face detected in crop")**
- Person may be too far or turned sideways
- Check that the camera angle shows faces clearly

**Port 80 conflict on Windows**
- Docker Desktop uses port 80 internally — use port 8080 instead (already configured)

**GPU not used by edge node**
- Set `DEVICE=cuda` in `.env` and restart: `docker compose restart edge_node`
- Verify: `docker compose logs edge_node | grep CUDAExecution`

**App slow / edge node high CPU**
- Confirm `DEVICE=cuda` — CPU inference is 10–20× slower
- Check: `nvidia-smi` to see GPU memory usage

**Alerts not appearing in real-time**
- Both attendance and alerts use WebSocket — check browser console for WS connection errors
- Confirm nginx `/ws/` proxy is configured (already set in `infra/nginx/nginx.conf`)

See `DEVELOPER_NOTES.md` for architecture decisions and extension guide.
