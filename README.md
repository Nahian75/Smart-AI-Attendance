# Oculus — Intelligent Vision Secure Operation

**Real-time face recognition, anti-spoofing, bag detection, security alerts, and attendance analytics powered by AI.**

Built with **YOLOv11 + ByteTrack + InsightFace (ArcFace R100)**, **FastAPI** backend, **Next.js 15** dashboard, **PostgreSQL + pgvector**, and **Docker**.

---

## Features

- **Real-time Face Recognition** — YOLOv11 + ByteTrack + ArcFace R100 with FAISS vector search
- **Dual-Pipeline Architecture** — Person detection and object alerts run on every frame (fast path); face recognition runs in a separate throttled pipeline — bags and intruders are flagged the moment they appear, not after recognition finishes
- **Dual-Mode Recognition** — Automatic frontal mode (entrance/kiosk cameras) and CCTV/overhead mode (staircase/ceiling cameras); each uses a tuned detection strategy and threshold set
- **Fast-Path Recognition** — Single high-confidence frame fires instantly (score ≥ threshold + margin); multi-frame voting is the fallback for ambiguous cases, eliminating flip-flopping without sacrificing speed for clear detections
- **Night Mode Detection** — CLAHE contrast boost applied automatically on dark frames before YOLO and face detection; dark-clothed employees on dark backgrounds are detected without any manual configuration
- **Per-Camera Head-Pose Limits** — MediaPipe yaw/pitch filter thresholds are set per camera profile; overhead/staircase cameras use wider limits (75°/70°) so downward-facing heads are not incorrectly rejected
- **Top-K Embedding Matching** — Averages similarity across an employee's multiple enrolled embeddings for robust identification
- **Head Pose Filter** — MediaPipe FaceLandmarker rejects side-profile and extreme-angle frames before embedding; reduces false "Unknown" votes
- **CCTV/Overhead Detection** — Head-crop-first strategy (top 40% of person bbox) + full-frame SCRFD sweep; detects faces looking downward without angle-specific retraining
- **Camera Enrollment from Live Snapshot** — HR can capture a live frame from any camera and select the face on-screen to enroll angle-specific embeddings directly from the dashboard
- **Face-Quality Gating** — Junk crops (blurry, turned away, too small) are rejected before recognition; only high-quality detections count
- **Per-Camera Anti-Spoof Control** — MiniFASNet CNN (print+replay, AUC ~0.99) enabled for frontal/kiosk cameras; disabled for CCTV/DVR cameras where the heuristic produces false positives on compressed streams
- **Face Mask Detection** — Detects surgical, cloth, and N95 masks; fires `masked_face` event + yellow MASKED overlay
- **Suspicious Object Detection** — YOLO detects backpacks (class 24), handbags (class 26), and suitcases (class 28); alert fires on the **first frame** the object appears near a person (per-track 30 s cooldown prevents spam)
- **Universal Camera Connectivity** — Auto-discovers stream type: ONVIF → RTSP (TCP/UDP/H.265) → Hikvision HCNetSDK → Dahua NetSDK
- **Multi-GPU Support** — NVIDIA (CUDA), AMD (ROCm), Intel (OpenVINO/Arc), CPU — auto-detected at startup
- **Security Alerts** — 10 types with plain-language messages: intruder, blacklist, after-hours, restricted area, VIP, loitering, spoof attempt, unknown person, masked face, suspicious object
- **Email Notifications** — SMTP email for high-severity alerts and daily attendance digest
- **Real-Time WebSocket** — Alerts and attendance events appear instantly on dashboard (no polling)
- **Detection Evidence Log** — Every face detection saved as a clean padded snapshot (512 px, exposure-corrected, no over-sharpening), with timestamp, confidence, and camera
- **Glassmorphism Dashboard** — Frosted-glass UI with light/dark mode toggle; employee names and alert messages readable in both modes
- **Shift Management** — Create shifts with grace periods and early-leave buffers; late/early-leave/overtime calculated automatically
- **Role-Based Access Control** — 6-level hierarchy (super\_admin → viewer) enforced on API and UI
- **CSV Export** — Monthly attendance reports
- **Celery Background Jobs** — Mark absentees, data-retention policy, snapshot purge, daily email digest

---

## How It Works

```
Camera (RTSP / ONVIF / Hikvision HCNetSDK / Dahua NetSDK / USB / HTTP MJPEG)
  → Edge node — TWO independent pipelines per frame:

  ┌─ FAST PATH (every frame, _DETECTION_EXECUTOR) ──────────────────────────────┐
  │  _boost_dark_frame() — CLAHE if mean luminance < 80                         │
  │  YOLO detect → ByteTrack track                                               │
  │  └─ for each confirmed person track:                                         │
  │       object check: backpack / handbag / suitcase near person?               │
  │       └─ yes → suspicious_object alert (30 s per-track cooldown)             │
  └─────────────────────────────────────────────────────────────────────────────┘

  ┌─ SLOW PATH (throttled, _INFERENCE_EXECUTOR) ────────────────────────────────┐
  │  _boost_dark_frame() — same CLAHE pass for SCRFD / face crops               │
  │  YOLO detect → ByteTrack track                                               │
  │  └─ [per confirmed track]                                                    │
  │      ├─ CCTV mode: head crop (top 40%) → SCRFD → fallback: full padded crop │
  │      ├─ Frontal mode: full padded crop → SCRFD → fallback: head crop        │
  │      └─ full-frame SCRFD sweep, filter to person bbox                        │
  │          → face-quality gate (pixel size ≥ 80px, det_score ≥ min_det_score) │
  │              └─ low-confidence: mask check → masked_face event               │
  │          → MediaPipe head-pose filter (per-camera yaw/pitch limits)          │
  │              └─ too angled → frame dropped (not added to vote buffer)        │
  │          → mask check → MASKED overlay + masked_face event (60 s cooldown)  │
  │          → anti-spoof (frontal cameras): MiniFASNet ONNX                     │
  │          → bilateral denoise + CLAHE (LAB) enhancement (embed crop only)    │
  │          → ArcFace embed → top-K FAISS match                                 │
  │          → padded face snapshot (60% pad, 512px target, JPEG 95%) saved     │
  │          → FAST-FIRE: score ≥ threshold + margin AND liveness → instant event│
  │          → FALLBACK: multi-frame vote buffer (N frames, majority wins)       │
  │          → decision: recognized / unknown / spoof                            │
  └─────────────────────────────────────────────────────────────────────────────┘

  → POST /api/v1/attendance/event  (EDGE_TOKEN auth)
  → Backend: event type routing:
      suspicious_object / masked_face → alert only
      spoof_attempt → alert + store RecognitionEvent
      unknown_person → store UnknownDetection + alert
      recognition → confidence gate → cooldown → shift check →
                    late/early/OT calc → AttendanceLog → Postgres
  → Email notification (high-severity alerts, if SMTP configured)
  → Redis pub/sub → WebSocket → live dashboard (attendance + alerts channels)
```

---

## Quick Start (Windows)

```
Double-click start.bat
```

- First run: builds images and downloads AI models (~10–20 min, once only)
- Subsequent runs: starts in ~10 seconds, no rebuild, no downloads
- Dashboard opens at **http://localhost:8080**
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
git clone <repo> && cd oculus
chmod +x deploy.sh
./deploy.sh                  # auto-detects IP and GPU
./deploy.sh yourdomain.com
./deploy.sh --update
```

The deploy script automatically:
1. Checks Docker is running
2. **Detects GPU type** (NVIDIA/AMD/Intel) and selects the right Dockerfile
3. Detects server public IP (or uses your domain)
4. Generates all secrets (`SECRET_KEY`, `FACE_ENCRYPTION_KEY`, `EDGE_TOKEN`, DB passwords)
5. Builds production images with pre-baked AI models
6. Starts all services, seeds the database

### GPU Support Matrix

| Hardware | Dockerfile | ONNX Provider | Torch Device |
|---|---|---|---|
| NVIDIA GPU | `Dockerfile.edge` / `.nvidia` | `CUDAExecutionProvider` | `cuda` |
| AMD GPU (ROCm) | `Dockerfile.edge.amd` | `ROCMExecutionProvider` | `cuda` (ROCm compat) |
| Intel Arc / Iris | `Dockerfile.edge.intel` | `OpenVINOExecutionProvider` | `xpu` / `cpu` |
| CPU only | `Dockerfile.edge.cpu` | `CPUExecutionProvider` | `cpu` |

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Storage | 20 GB | 50 GB SSD |
| Docker | 20.10+ | 24.0+ |
| Camera | RTSP / IP / USB | HD IP camera (1920×1080+) |
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

## Camera Setup

Register cameras via the dashboard **Cameras** page. The edge node polls the backend every 60 seconds for new cameras.

### Supported Camera Types

| Camera type | URL format |
|---|---|
| Hikvision (main stream) | `rtsp://admin:pass@IP:554/Streaming/Channels/101` |
| Hikvision (channel N) | `rtsp://admin:pass@IP:554/Streaming/Channels/N01` |
| Dahua | `rtsp://admin:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |
| V380 / budget WiFi | `rtsp://admin:password@IP:554/stream1` |
| Reolink | `rtsp://admin:pass@IP:554/h264Preview_01_main` |
| Tapo / TP-Link | `rtsp://admin:pass@IP:554/stream1` |
| Axis | `rtsp://admin:pass@IP/axis-media/media.amp` |
| USB webcam | `0` (first), `1` (second) ... |
| Video file (testing) | `/path/to/video.mp4` |

> **Hikvision tip:** Always use the **main stream** (`/Channels/N01`), not sub-stream (`/Channels/N02`). Sub-stream is limited to 4CIF (704×576) with no 720P option.

### Camera Quality Profiles

`edge/config/camera_config.yaml` auto-selects a profile based on the camera name. Name your camera to match:

| Keywords in camera name | Profile | Notes |
|---|---|---|
| `kiosk`, `gate`, `reception`, `lobby` | Close-range frontal | Anti-spoof ON, strict thresholds |
| `hik`, `dvr`, `hikvision`, `level 1`, `entrance` | Hikvision entrance | 1080P+ tuning, anti-spoof ON |
| `staircase`, `ceiling`, `overhead`, `level 2` | CCTV/overhead | `cctv_mode=true`, anti-spoof OFF |
| `hivideo`, `v380`, `wifi`, `ip cam` | Budget WiFi | Enhancement ON, anti-spoof OFF |
| `meeting`, `conference`, `boardroom` | Meeting room | Overhead, lenient thresholds |

---

## Recognition Tuning

All thresholds in `edge/config/camera_config.yaml` — **no rebuild needed**, just restart edge node:

```yaml
recognition_threshold: 0.45   # raise to 0.55+ for quality cameras
min_det_score: 0.40            # minimum face detection confidence (raised for 1080P+)
vote_window: 4                 # frames to collect per person (fallback voting path)
min_votes: 2                   # minimum frames before deciding (fallback voting path)
vote_ttl_seconds: 8            # drop buffer if person absent this long
cooldown_seconds: 300          # suppress re-detection for 5 min
enhance_faces: true            # bilateral denoise + CLAHE on the embedding crop only

# Fast-path recognition — fires on the first frame with a confident match
fast_recognize_margin: 0.10    # score must exceed threshold by this much to fast-fire
                               # set to 0 to disable (always use vote buffer)

# Object / bag alert cooldown (fast path)
bag_cooldown_seconds: 30       # seconds before a second alert fires for the same track

# MediaPipe head-pose filter (set per camera profile in profiles: section)
mp_max_yaw: 65.0               # reject faces rotated > this many degrees left/right
mp_max_pitch: 50.0             # reject faces tilted > this many degrees up/down
                               # overhead/staircase profiles use 75°/70° by default

# Mask detection
mask_threshold: 0.72           # raised to prevent glasses false positives
mask_cooldown_seconds: 60      # seconds between repeat masked_face alerts
```

> **Per-camera head-pose:** Override `mp_max_yaw` / `mp_max_pitch` inside a profile block in `camera_config.yaml` to set tighter or wider limits for individual camera types without affecting other cameras.

To apply: `docker compose restart edge_node`

**Tuning tips:**
- Enrolled employees missed → lower `recognition_threshold` (try 0.38)
- Wrong people matching → raise `recognition_threshold` (try 0.55)
- Real faces rejected as spoof → lower `liveness_threshold` (try 0.32)
- Employee walks past and is not recorded → lower `fast_recognize_margin` (try `0.07`) or set `min_votes: 1`
- Too many bag alerts for the same person → raise `bag_cooldown_seconds` (try `60`)
- Employees not visible in dark environments → check edge logs for `mean_lum`; CLAHE runs automatically if luminance < 80
- Best improvement: re-enroll with 3–5 photos taken under the same lighting as the camera

---

## Email Notifications

Add to `.env` to enable:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL_TO=admin@company.com,security@company.com
```

Emails sent for: spoof attempts, intruders, blacklisted employees, after-hours detections, and daily attendance digest (18:00 via Celery).

Gmail: use an **App Password** (not your account password). Go to Google Account → Security → 2-Step Verification → App passwords.

---

## Dashboard Pages

| Page | Path | Description |
|---|---|---|
| Overview | `/dashboard` | Stat cards, live cameras, occupancy, weekly/hourly charts, recent check-ins, live feed, alerts |
| Employees | `/dashboard/employees` | Employee list, face enrollment, blacklist/VIP flags |
| Cameras | `/dashboard/cameras` | Camera cards with MJPEG streams, add/edit/delete |
| Detection Log | `/dashboard/detection-log` | Every face detection: clean 512 px snapshot, timestamp, confidence, camera |
| Alerts | `/dashboard/alerts` | All alert types, unacknowledged filter |
| Security Alerts | `/dashboard/security-alerts` | High-severity incidents + loitering section |
| Shifts | `/dashboard/shifts` | Create/edit shifts, assign employees |
| Analytics | `/dashboard/analytics` | Building occupancy, department breakdown, shift compliance |
| Reports | `/dashboard/reports` | Monthly CSV export |
| Admin | `/dashboard/admin` | User management, role assignment (admin+ only) |

---

## Security Model

### Authentication & Passwords
- All API endpoints (except `POST /auth/login`) require JWT Bearer token
- Tokens signed with `SECRET_KEY` (HS256), expire after `ACCESS_TOKEN_EXPIRE_HOURS` (default 8 h)
- All passwords hashed with **bcrypt** — never stored or logged in plain text

### Role Hierarchy

| Role | Level | Permissions |
|---|---|---|
| `super_admin` | 6 | Everything |
| `admin` | 5 | Full tenant access |
| `hr` | 4 | Employees, enrollment, attendance overrides |
| `manager` | 3 | Read-only + face match |
| `security` | 2 | Read-only + acknowledge alerts |
| `viewer` | 1 | Read-only dashboard |

### Rate Limiting
| Path | Limit |
|---|---|
| `POST /api/v1/auth/login` | 30 req / min / IP |
| All other endpoints | 200 req / min / IP |

### Face Snapshot Storage & Auto-Purge
Snapshots stored at `/app/snapshots/`, served at `/snapshots/` via nginx.  
**Auto-purge:** Celery task at 3:00 AM deletes files older than 7 days. DB records kept for 90 days.

---

## Shift Time Logic

| Event | Condition | Result |
|---|---|---|
| Check-in | After `start_time + grace_in_min` | Marked **Late** + email notification |
| Check-out | Before `end_time - early_out_min` | Marked **Early Leave** |
| Check-out | After `end_time` | **Overtime** seconds recorded |
| Detection | Outside shift days/hours | **After-hours** alert + email |

---

## Adding Employees & Enrolling Faces

1. Go to **Employees** in the dashboard
2. Click **Add Employee** — fill name, code, department, designation, phone
3. Click the **face icon** on the employee row
4. Upload **3–10 clear front-facing photos** taken under the same lighting as the camera
5. The backend extracts a 512-d ArcFace embedding and marks the employee as enrolled

The edge node resyncs embeddings every 60 seconds — no restart needed.

> **Tip:** Photos taken at the same angle and lighting as the camera give significantly higher similarity scores.

---

## API Reference

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

### Cameras
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/cameras` | JWT | List active cameras |
| POST | `/api/v1/cameras` | **[admin]** | Add camera |
| PATCH | `/api/v1/cameras/{id}` | **[admin]** | Update settings |
| DELETE | `/api/v1/cameras/{id}` | **[admin]** | Deactivate |

### Alerts
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/alerts` | JWT | List alerts |
| GET | `/api/v1/alerts/recent` | JWT | Last 50 from Redis |
| POST | `/api/v1/alerts/{id}/acknowledge` | **[security]** | Acknowledge |

### WebSocket
| Path | Auth | Description |
|---|---|---|
| `WS /ws/attendance/{tenant_id}?token=...` | JWT | Real-time check-in/out events |
| `WS /ws/alerts/{tenant_id}?token=...` | JWT | Real-time security alerts |

---

## Project Structure

```
oculus/
├── backend/
│   ├── app/
│   │   ├── api/v1/          auth, attendance, employees, shifts, cameras,
│   │   │                    alerts, analytics, reports, enrollment, admin,
│   │   │                    rbac, ws (attendance + alerts WebSocket), detections
│   │   ├── core/            security (JWT/bcrypt/RBAC), middleware, exceptions
│   │   ├── models/          SQLAlchemy ORM (User, Employee, Shift, Camera, Alert,
│   │   │                    AttendanceLog, RecognitionEvent, UnknownDetection)
│   │   ├── schemas/         Pydantic I/O schemas
│   │   └── services/
│   │       ├── attendance_service.py   Main logic: gates, shifts, alerts, late notif
│   │       ├── alert_service.py        Fires alerts → DB + Redis + email
│   │       ├── face_service.py         Enrollment + pgvector match
│   │       └── notification_service.py SMTP email + webhook notifications
│   └── workers/             Celery: absentees, retention, snapshot purge, email digest
│
├── edge/
│   ├── src/
│   │   ├── detection/          YOLOv11 + ByteTrack person + object detector
│   │   ├── recognition/
│   │   │   ├── arcface.py          InsightFace ArcFace R100
│   │   │   ├── anti_spoof.py       MiniFASNet ONNX + heuristic fallback
│   │   │   ├── mask_detector.py    Face mask classifier + optional ONNX slot
│   │   │   ├── mediapipe_align.py  Head-pose filter + 5-point alignment
│   │   │   └── faiss_search.py     Top-K cosine similarity
│   │   ├── camera/             RTSP/ONVIF/HCNetSDK reader + MJPEG server
│   │   └── pipeline/
│   │       ├── frame_processor.py  Enhance → embed → vote engine
│   │       └── event_publisher.py  Redis + backend POST
│   ├── config/
│   │   └── camera_config.yaml  Camera profiles, all thresholds
│   └── weights/
│       ├── antispoof_128.onnx  MiniFASNet print+replay model (1.85 MB)
│       └── face_landmarker.task  MediaPipe head-pose model
│
├── frontend/             Next.js 15 glassmorphism dashboard
├── infra/nginx/          Reverse proxy config
├── start.bat / stop.bat  Windows one-click start/stop
└── deploy.bat            Windows production deploy
```

---

## Production Security Checklist

- [ ] `SECRET_KEY` set to a random 64-char hex string
- [ ] `FACE_ENCRYPTION_KEY` set to a generated Fernet key
- [ ] `EDGE_TOKEN` set and matching on edge node
- [ ] `ENVIRONMENT=production`
- [ ] Default admin password changed immediately after first login
- [ ] Postgres and Redis not exposed on public interfaces
- [ ] Nginx configured with SSL
- [ ] SMTP credentials in `.env`, not committed to git

---

## Troubleshooting

**Employee walks past too quickly and is not recorded**
- The fast-recognition path fires on the first frame where `score ≥ threshold + fast_recognize_margin`; lower `fast_recognize_margin` (try `0.07`) in `camera_config.yaml` to make it fire sooner
- Also set `min_votes: 1` so the voting fallback fires on the very first clean frame
- If the face is genuinely too small or blurry, reposition the camera so faces are ≥ 80 px wide in the frame

**Bags / objects not alerted immediately**
- Object alerts now fire on the very first frame the object appears (fast path, every frame); if you see delays check that `_detection_busy` is not stuck — restart the edge node
- To reduce alert spam per person raise `bag_cooldown_seconds` (default `30`)

**Dark clothing / dark background — employees not detected at night**
- CLAHE night-mode boost is automatic when frame luminance < 80; no configuration needed
- If still missed, check camera IR is active and point-of-view is within ~3–5 m of the subject

**Anti-spoof triggers on real people**
- Lower `liveness_threshold` in `camera_config.yaml` (try 0.25)
- If heuristic is running (no ONNX model): check `edge/weights/antispoof_128.onnx` exists

**Employees detected as unknown**
- Check edge logs for `best_sim=` values
- If sim is 0.35–0.45: lower `recognition_threshold`, re-enroll with better photos
- Make sure embeddings synced: look for `FAISS index resynced: N face embeddings`

**Alert messages show raw IDs instead of names**
- Ensure the backend has been restarted after the latest update; alert messages now always resolve the camera and employee name before firing

**Head-pose filter rejecting too many frames**
- Raise `mp_max_yaw` / `mp_max_pitch` in `camera_config.yaml`
- Global defaults: `mp_max_yaw: 60.0`, `mp_max_pitch: 45.0`

**Detection log images blurry**
- Ensure cameras use the **main stream**, not sub-stream
- Minimum face size gate is 80px — distant faces (< 80px wide) are filtered out by design
- Snapshots are saved at 1024px minimum with 60% padding and JPEG quality 97

**"Could not reach the server" on login**
- Ensure `NEXT_PUBLIC_API_URL=http://localhost:8080` in `.env`
- Rebuild frontend: `docker compose up -d --build frontend`

**GPU not used by edge node**
- Set `DEVICE=cuda` in `.env` and restart: `docker compose restart edge_node`

See `DEVELOPER_NOTES.md` for architecture decisions, pipeline details, and extension guide.
