# Smart AI Attendance System

**AI-powered attendance tracking with real-time face recognition, security alerts, and comprehensive analytics.**

Built with **YOLOv11 + ByteTrack + InsightFace (ArcFace R100)**, **FastAPI** backend, **Next.js 15** dashboard, **PostgreSQL + pgvector**, and **Docker**.

---

## Features

- **Real-time Face Recognition** — YOLOv11 + ByteTrack + ArcFace R100 with FAISS vector search
- **Multi-GPU Support** — NVIDIA (CUDA), AMD (ROCm), Intel (OpenVINO/Arc), CPU — auto-detected at startup
- **Security Alerts** — 8 types: intruder, blacklist, after-hours, restricted area, VIP, loitering, spoof attempt, unknown person
- **Liveness / Anti-Spoof** — ONNX-based spoof detection blocks printed-photo and screen-replay attacks
- **Shift Management** — Create shifts with start/end times, grace periods, and early-leave buffers; assign employees; late/early-leave/overtime calculated automatically
- **Role-Based Access Control** — 6-level hierarchy (super_admin → viewer) enforced on API and UI; colored role badge in sidebar
- **Self-Service Password Change** — Any user changes their own password from the sidebar; bcrypt-hashed
- **Admin Panel** — Add users, change roles, deactivate accounts
- **Occupancy Analytics** — Building-wide and per-zone real-time counters
- **Audit Trail** — Every action logged with user ID, IP, old/new values
- **GDPR Compliance** — Tenant-wide data deletion endpoint
- **Dark Mode** — Full dark/light theme toggle, persisted to localStorage
- **WebSocket Live Feed** — Real-time attendance events and security alerts
- **CSV Export** — Monthly attendance reports
- **Celery Background Jobs** — Mark absentees, apply data-retention policy, email digest

---

## How It Works

```
Camera (RTSP / IP / USB)
  → Edge node: YOLO detect → ByteTrack → face crop → anti-spoof → ArcFace embed → FAISS match
  → POST /api/v1/attendance/event  (EDGE_TOKEN auth)
  → Backend: confidence gate → cooldown → shift check → late/early/OT calc → Postgres
  → Redis pub/sub → WebSocket → live dashboard
```

---

## One-Click Production Deploy

### Linux / macOS
```bash
git clone <repo> && cd smart-ai-attendance
chmod +x deploy.sh
./deploy.sh                    # auto-detects IP and GPU
./deploy.sh yourdomain.com     # with custom domain
./deploy.sh --update           # rebuild keeping existing .env
```

### Windows Server
```
Double-click deploy.bat
— or —
deploy.bat yourdomain.com
```

The deploy script automatically:
1. Checks Docker is running
2. **Detects GPU type** (NVIDIA/AMD/Intel) and selects the right Dockerfile and compose override
3. Detects server public IP (or uses your domain)
4. Generates all secrets (`SECRET_KEY`, `FACE_ENCRYPTION_KEY`, `EDGE_TOKEN`, DB passwords) — shown once, stored in `.env`
5. Builds production images with pre-baked AI models (~10-20 min first run)
6. Starts all services
7. Seeds the database
8. Opens the dashboard

### GPU Support Matrix

| Hardware | Dockerfile | ONNX Provider | Torch Device |
|---|---|---|---|
| NVIDIA GPU | `Dockerfile.edge.nvidia` | `CUDAExecutionProvider` | `cuda` |
| AMD GPU (ROCm) | `Dockerfile.edge.amd` | `ROCMExecutionProvider` | `cuda` (ROCm compat) |
| Intel Arc / Iris | `Dockerfile.edge.intel` | `OpenVINOExecutionProvider` | `xpu` / `cpu` |
| CPU only | `Dockerfile.edge.cpu` | `CPUExecutionProvider` | `cpu` |

Force a specific GPU type:
```bash
./deploy.sh --gpu nvidia    # or amd | intel | cpu
make deploy-amd             # convenience make targets
```

### make targets

| Command | What it does |
|---|---|
| `make deploy` | Production deploy (auto GPU) |
| `make deploy-gpu` | Force NVIDIA |
| `make deploy-amd` | Force AMD ROCm |
| `make deploy-intel` | Force Intel OpenVINO |
| `make deploy-cpu` | CPU only |
| `make update` | Rebuild keeping .env |
| `make prod-logs` | Tail production logs |
| `make prod-down` | Stop production |
| `make prod-reset` | Stop + wipe all data |

---

## Local Development (one click)

### Windows
```
Double-click start.bat
```

### macOS / Linux
```bash
chmod +x start.sh && ./start.sh
```

Uses `docker-compose.dev.yml` with:
- Fast backend Dockerfile (no model pre-download — models download on first enrollment)
- Nginx on port 80
- CPU edge node (optional, `--profile edge`)
- Auto-creates `.env` from `.env.dev` on first run
- Auto-seeds database on first run

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

## Security Model

### Authentication & Passwords
- All API endpoints (except `POST /auth/login`) require a JWT Bearer token
- Tokens signed with `SECRET_KEY` (HS256), expire after `ACCESS_TOKEN_EXPIRE_HOURS` (default 8 h)
- All passwords hashed with **bcrypt** via passlib — never stored or logged in plain text
- Production startup **refuses to start** if `SECRET_KEY`, `FACE_ENCRYPTION_KEY`, or `EDGE_TOKEN` are still set to their insecure defaults

### Role Hierarchy

| Role | Level | Badge | Permissions |
|---|---|---|---|
| `super_admin` | 6 | Purple | Everything |
| `admin` | 5 | Red | Full tenant access: cameras, bulk reset, blacklist/VIP, alert config, user management |
| `hr` | 4 | Blue | Add/edit/deactivate employees, enroll faces, manual attendance overrides |
| `manager` | 3 | Green | Read-only + face match endpoint |
| `security` | 2 | Amber | Read-only + acknowledge alerts |
| `viewer` | 1 | Gray | Read-only dashboard |

### Dashboard UI Permission Matrix

| Action | viewer | security | manager | hr | admin |
|---|:---:|:---:|:---:|:---:|:---:|
| View all pages | ✓ | ✓ | ✓ | ✓ | ✓ |
| Acknowledge alerts | | ✓ | ✓ | ✓ | ✓ |
| Edit / delete attendance log | | | | ✓ | ✓ |
| Add / edit / deactivate employee | | | | ✓ | ✓ |
| Enroll face photos | | | | ✓ | ✓ |
| Toggle blacklist / VIP | | | | | ✓ |
| Add / edit / delete cameras | | | | | ✓ |
| Bulk reset attendance | | | | | ✓ |
| Manage users and roles | | | | | ✓ |

Every user can **change their own password** from the sidebar.

### Edge Node Authentication
Edge nodes send `Authorization: Bearer <EDGE_TOKEN>` when posting recognition events. In development (`EDGE_TOKEN` empty), the check is skipped. In production, a missing or wrong token returns 401.

### Rate Limiting
| Path | Limit |
|---|---|
| `POST /api/v1/auth/login` | 30 req / min / IP |
| `POST /api/v1/auth/refresh` | 30 req / min / IP |
| All other endpoints | 200 req / min / IP |

### API Docs
Swagger (`/api/docs`) and Redoc (`/api/redoc`) are **disabled in production** (`ENVIRONMENT=production`).

---

## Dashboard Pages

| Page | Path | Description |
|---|---|---|
| Overview | `/dashboard` | Stat cards, live camera feeds, occupancy, weekly/hourly charts, recent check-ins |
| Employees | `/dashboard/employees` | Employee list, face enrollment, blacklist/VIP flags |
| Cameras | `/dashboard/cameras` | Camera cards with MJPEG streams, add/edit/delete |
| Alerts | `/dashboard/alerts` | All alert types, unacknowledged filter |
| Security Alerts | `/dashboard/security-alerts` | High-severity incidents + loitering section |
| Shifts | `/dashboard/shifts` | Create/edit shifts, assign employees, view late/early thresholds |
| Analytics | `/dashboard/analytics` | Building occupancy, department breakdown, shift compliance |
| Reports | `/dashboard/reports` | Monthly CSV export, shift compliance summary |
| Admin | `/dashboard/admin` | User management, role assignment (admin+ only) |

### Sidebar (all pages)
- Colored **role badge** showing current user's role
- **Change Password** modal — verifies current password, enforces 8-char minimum
- Active-page highlight
- Theme toggle (dark/light)

---

## Shift Time Logic

Shifts control how attendance is classified:

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
4. Upload 3–10 clear front-facing photos (drag-and-drop supported)
5. The backend extracts a 512-d ArcFace embedding and marks the employee as enrolled

The edge node resyncs embeddings from the backend every 60 seconds — no restart needed.

---

## Camera Setup

Register cameras via the dashboard Cameras page or in `edge/config/camera_config.yaml`:

```yaml
cameras:
  - id: cam-main
    rtsp_url: "rtsp://user:pass@192.168.1.10:554/stream"
    direction: entrance   # entrance | exit | interior
    fps_target: 5
```

| Source | URL format |
|---|---|
| IP camera (RTSP) | `rtsp://user:pass@192.168.1.x:554/...` |
| HTTP webcam | `http://192.168.x.x:8080/video` |
| USB webcam (Linux/macOS) | `"0"` or `"1"` |
| USB webcam (Windows) | use `edge_standalone.py` |

---

## API Endpoints

> **[admin]** = `role >= admin` · **[hr]** = `role >= hr` · **[security]** = `role >= security` · JWT = any valid token · EDGE = `EDGE_TOKEN` header

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | — | Login; returns JWT |
| POST | `/api/v1/auth/refresh` | — | Refresh still-valid JWT |
| POST | `/api/v1/auth/change-password` | JWT | Change own password |

### Attendance
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/attendance/event` | EDGE | Ingest recognition event |
| GET | `/api/v1/attendance/summary` | JWT | Daily summary |
| GET | `/api/v1/attendance/logs` | JWT | Paginated log history |
| GET | `/api/v1/attendance/live` | JWT | Last 50 live events |
| PATCH | `/api/v1/attendance/logs/{id}` | **[hr]** | Manual override |
| DELETE | `/api/v1/attendance/logs/{id}` | **[hr]** | Delete single log |
| DELETE | `/api/v1/attendance/logs` | **[admin]** | Bulk reset for a date |

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
| POST | `/api/v1/shifts/assignments` | **[hr]** | Assign shift to employee |
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
| POST | `/api/v1/alerts/config/password` | **[admin]** | Change config password |

### Analytics & Reports
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/analytics/occupancy` | JWT | Live occupancy |
| GET | `/api/v1/analytics/hourly` | JWT | Hourly entry/exit chart data |
| GET | `/api/v1/analytics/shift-compliance` | JWT | On-time % per employee |
| GET | `/api/v1/analytics/visitors` | JWT | Unknown person count |
| GET | `/api/v1/analytics/department-occupancy` | JWT | Occupancy by department |
| GET | `/api/v1/reports/monthly.csv` | JWT | CSV export |

### Admin (User Management)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/admin/users` | **[admin]** | List users |
| POST | `/api/v1/admin/users` | **[admin]** | Create user |
| PATCH | `/api/v1/admin/users/{id}` | **[admin]** | Change role / status |
| DELETE | `/api/v1/admin/users/{id}` | **[admin]** | Deactivate user |

### RBAC / Audit
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/rbac/audit` | **[admin]** | Audit logs |
| GET | `/api/v1/rbac/audit/stats` | **[admin]** | Audit statistics |

### WebSocket
| Path | Auth | Description |
|---|---|---|
| `WS /ws/attendance/{tenant_id}?token=...` | JWT (query) | Real-time events |

---

## Production Security Checklist

- [ ] `SECRET_KEY` set to a random 64-char hex string
- [ ] `FACE_ENCRYPTION_KEY` set to a generated Fernet key
- [ ] `EDGE_TOKEN` set and matching on edge node
- [ ] `ENVIRONMENT=production`
- [ ] Default admin password changed immediately after first login
- [ ] Postgres and Redis not exposed on public interfaces
- [ ] Nginx configured with SSL (see certbot instructions in `deploy.sh` output)
- [ ] Prometheus `/metrics` firewalled to internal network only

---

## Project Structure

```
smart-ai-attendance/
├── backend/
│   ├── app/
│   │   ├── api/v1/          auth, attendance, employees, shifts, cameras,
│   │   │                    alerts, analytics, reports, enrollment, admin, rbac, ws
│   │   ├── core/            security (JWT/bcrypt/RBAC), middleware, exceptions
│   │   ├── models/          SQLAlchemy ORM (User, Employee, Shift, Camera, Alert, ...)
│   │   ├── schemas/         Pydantic I/O schemas
│   │   ├── services/        AttendanceService, AlertService, FaceEnrollmentService
│   │   └── workers/         Celery tasks (mark absentees, retention, digest)
│   ├── Dockerfile            Production (pre-baked InsightFace models)
│   ├── Dockerfile.dev        Fast dev (models download on first use)
│   └── seed.py
│
├── edge/
│   ├── src/
│   │   ├── utils/gpu.py      Runtime GPU auto-detection (NVIDIA/AMD/Intel/CPU)
│   │   ├── detection/        YOLOv11 + ByteTrack person detector
│   │   ├── recognition/      ArcFace embedder, anti-spoof, FAISS search
│   │   ├── camera/           RTSP reader, MJPEG server
│   │   └── pipeline/         FrameProcessor, EventPublisher
│   ├── Dockerfile.edge.nvidia   NVIDIA CUDA
│   ├── Dockerfile.edge.amd      AMD ROCm
│   ├── Dockerfile.edge.intel    Intel OpenVINO
│   └── Dockerfile.edge.cpu      CPU only
│
├── frontend/
│   ├── src/
│   │   ├── app/             Next.js app router pages
│   │   ├── components/      DashboardShell, CameraFeed, charts, live feeds
│   │   ├── lib/             api.ts, auth.ts, rbac.ts (hasRole/useRole)
│   │   └── types/           TypeScript interfaces
│   └── Dockerfile
│
├── infra/nginx/nginx.conf    Docker DNS resolver, variable upstreams
├── docs/                     user_manual.pdf, developer_guide.pdf
│
├── deploy.sh                 Linux/Mac production one-click
├── deploy.bat                Windows Server production one-click
├── start.sh / start.bat      Local dev one-click
├── docker-compose.prod.yml   Production (CPU edge)
├── docker-compose.prod.gpu.yml    NVIDIA override
├── docker-compose.prod.amd.yml    AMD override
├── docker-compose.prod.intel.yml  Intel override
└── docker-compose.dev.yml    Development
```

---

## Documents

| File | Description |
|---|---|
| `docs/user_manual.pdf` | End-user guide: dashboard, employees, shifts, alerts |
| `docs/developer_guide.pdf` | A-Z file guide: every file explained with logic and changes |
| `DEVELOPER_NOTES.md` | Architecture decisions, bug-fix log, extension guide |

Generate PDFs (requires `pip install fpdf2`):
```bash
python generate_user_manual_pdf.py
python generate_developer_guide_pdf.py
```

---

## Troubleshooting

**"Invalid credentials" on login**
- Check if the backend rate limiter blocked you (too many attempts in 1 min)
- Verify the seed ran: `docker compose logs backend | grep Seeded`

**Edge node rejected (401)**
- Confirm `EDGE_TOKEN` matches in `.env` and edge node environment
- In dev, leave `EDGE_TOKEN` empty to skip the check

**Dark mode not switching**
- Tailwind requires `darkMode: "class"` (already set)
- ThemeContext writes `dark`/`light` to `<html>` — check browser DevTools

**Face recognition not working**
- Check `CONFIDENCE_THRESHOLD` (default 0.75 dev, 0.82 prod)
- FAISS index empty? Enroll employees first
- Edge node logs: `docker compose logs edge_node`

**GPU not detected**
- NVIDIA: confirm nvidia-container-toolkit installed
- AMD: confirm `/dev/kfd` exists and user is in `render` group
- Intel: confirm `/dev/dri` exists
- Run `./deploy.sh --gpu cpu` as a fallback

**App refuses to start in production**
- `docker compose logs backend` — startup prints which secrets are still at defaults

See `DEVELOPER_NOTES.md` for architecture details and extension guide.
