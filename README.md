# Smart AI Attendance System

**AI-powered attendance tracking with real-time face recognition, anti-spoofing, security alerts, and comprehensive analytics.**

Built with **YOLOv11 + ByteTrack + InsightFace (ArcFace R100)**, **FastAPI** backend, **Next.js 15** dashboard, **PostgreSQL + pgvector**, and **Docker**.

---

## Features

- **Real-time Face Recognition** — YOLOv11 + ByteTrack + ArcFace R100 with FAISS vector search
- **Multi-Frame Temporal Voting** — Recognition decided across N frames (majority vote + mean similarity), eliminating single-frame flip-flopping
- **Top-K Embedding Matching** — Averages similarity across an employee's multiple enrolled embeddings for robust identification
- **Face-Quality Gating** — Junk crops (blurry, turned away) are skipped before recognition; only high-quality detections count
- **Real Anti-Spoof Model** — MiniFASNet CNN (print+replay variant, CelebA-Spoof, AUC ~0.99) blocks printed photos and screen/phone replay attacks; texture heuristic fallback when model unavailable
- **Hardened Screen-Replay Detection** — Histogram-based temporal gate (shift-invariant; defeats hand-tremor false passes) + screen-context brightness check (detects phone/tablet backlight glow around face) work in concert to catch phone photo attacks even without the ONNX model
- **Face Mask Detection** — Detects surgical, cloth, and N95 masks using upper/lower face texture + saturation contrast; fires `masked_face` event with snapshot, shows yellow **MASKED** overlay; optional ONNX classifier slot for higher accuracy
- **Neural Super-Resolution** — FSRCNN x2 upscales face crops before ArcFace embedding (+10–25% similarity on compressed streams); falls back to Lanczos automatically
- **Budget Camera Support** — V380 / WiFi IP cameras fully supported via bilateral denoise + unsharp mask + CLAHE enhancement pipeline; 5 camera quality profiles built in
- **Multi-GPU Support** — NVIDIA (CUDA), AMD (ROCm), Intel (OpenVINO/Arc), Windows (DirectML), CPU — auto-detected at startup
- **Standalone Windows Mode** — `edge_standalone.py` runs without Docker: full anti-spoof, SR, face enhancement, multi-frame voting, GPU support, auto-reconnect
- **Security Alerts** — 9 types: intruder, blacklist, after-hours, restricted area, VIP, loitering, spoof attempt, unknown person, **masked face**
- **Email Notifications** — SMTP email for high-severity alerts (spoof, intruder, blacklist, after-hours) and daily attendance digest; configure via `.env`
- **Real-Time Alert WebSocket** — Alerts appear instantly on dashboard via `/ws/alerts/` (no polling delay)
- **Detection Evidence Log** — Every face detection saved with snapshot, timestamp, confidence score, and camera
- **Shift Management** — Create shifts with start/end times, grace periods, and early-leave buffers; late/early-leave/overtime calculated automatically
- **Live Feed** — Shows check-in/check-out, unknown persons, and spoof attempts in real-time
- **Role-Based Access Control** — 6-level hierarchy (super_admin → viewer) enforced on API and UI
- **Occupancy Analytics** — Building-wide and per-zone real-time counters
- **GDPR Compliance** — Tenant-wide data deletion endpoint
- **Dark Mode** — Full dark/light theme toggle, persisted to localStorage
- **CSV Export** — Monthly attendance reports
- **Celery Background Jobs** — Mark absentees, data-retention policy, snapshot purge, daily email digest

---

## How It Works

```
Camera (RTSP / IP / USB / HTTP MJPEG)
  → Edge node:
      YOLO detect → ByteTrack track → 30% padded crop
      → face-quality gate (det_score ≥ min_det_score)
          └─ low-confidence face (mask_det_min ≤ score < min_det_score)
             → mask check → masked_face event if detected
      → mask check (upper/lower face texture contrast)
          └─ masked → MASKED overlay + masked_face event (60 s cooldown)
      → anti-spoof check (MiniFASNet ONNX or heuristic fallback):
          ├─ screen context: surrounding brightness/uniformity (phone backlight)
          ├─ heuristic: sharpness ×penalty + saturation + luminance uniformity
          └─ histogram temporal gate: shift-invariant static-image detector
      → FSRCNN x2 neural SR on face crop
      → bilateral denoise + unsharp mask + CLAHE
      → ArcFace embed → top-K FAISS match (no threshold at this stage)
      → multi-frame vote buffer (N frames, majority wins)
      → decision: recognized / unknown / spoof
  → POST /api/v1/attendance/event  (EDGE_TOKEN auth)
  → Backend: confidence gate → cooldown → shift check → late/early/OT calc → Postgres
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
- Dashboard opens automatically at **http://localhost:8080**
- Default login: `admin@demo.com` / `admin123`

To stop: double-click `stop.bat`

---

## Standalone Mode (Windows, no Docker)

Run directly on Windows without Docker — useful for development or single-camera deployments:

```powershell
# Install dependencies (once)
pip install insightface onnxruntime opencv-contrib-python numpy httpx pyyaml

# Run
python edge_standalone.py
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `CAMERA_SRC` | `0` | `0` = webcam, or RTSP/HTTP URL |
| `BACKEND_URL` | `http://localhost:8000` | Backend API URL |
| `EDGE_USER` | `admin@demo.com` | Login email |
| `EDGE_PASS` | `admin123` | Login password |
| `ANTISPOOF_MODEL` | `edge/weights/antispoof_128.onnx` | Anti-spoof model path |
| `SUPERRES_MODEL` | `edge/weights/FSRCNN_x2.pb` | FSRCNN super-res model path |
| `LIVENESS_THRESHOLD` | `0.38` | Anti-spoof threshold |
| `REC_THRESH` | `0.42` | Recognition similarity threshold |
| `VOTE_WINDOW` | `5` | Frames to collect per person |
| `MIN_VOTES` | `3` | Min frames before deciding |
| `COOLDOWN_S` | `300` | Seconds between re-detections |

> **GPU:** Install `onnxruntime-gpu` (NVIDIA) instead of `onnxruntime` for GPU acceleration.
> **Super-resolution:** Requires `opencv-contrib-python` (not plain `opencv-python`). Falls back to Lanczos if not available.

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
| Windows GPU | standalone only | `DirectMLExecutionProvider` | `cpu` |

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Storage | 20 GB | 50 GB SSD |
| Docker | 20.10+ | 24.0+ |
| Camera | RTSP / IP / USB | HD IP camera (1280×720+) |
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

| Camera type | `CAMERA_SRC` / URL format |
|---|---|
| V380 / budget WiFi | `rtsp://admin:password@IP:554/stream1` (HD main stream) |
| Hikvision | `rtsp://admin:pass@IP:554/Streaming/Channels/101` |
| Dahua | `rtsp://admin:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Reolink | `rtsp://admin:pass@IP:554/h264Preview_01_main` |
| Tapo / TP-Link | `rtsp://admin:pass@IP:554/stream1` |
| Axis | `rtsp://admin:pass@IP/axis-media/media.amp` |
| USB webcam | `0` (first), `1` (second) ... |
| Android IP Webcam app | `http://PHONE_IP:8080/video` |
| DroidCam (Android/iOS) | `http://PHONE_IP:4747/video` |
| IVCam | `rtsp://PHONE_IP:8554/live` |
| Video file (testing) | `/path/to/video.mp4` |

> **V380 tip:** Use `/stream1` (main HD stream) not `/stream` or `/stream2` (sub SD stream). Stopping camera recording in the V380 app frees compression bandwidth for a cleaner live stream.

### Camera Quality Profiles

`edge/config/camera_config.yaml` has 5 pre-configured profiles — uncomment the one matching your camera:

| Profile | Camera | `recognition_threshold` | `liveness_threshold` | SR |
|---|---|---|---|---|
| 1 (active) | V380 / budget WiFi | 0.42 | 0.38 | On |
| 2 | Mid-range IP (Hikvision, Dahua) | 0.55 | 0.48 | Off |
| 3 | Quality camera (Axis, Bosch) | 0.65 | 0.55 | Off |
| 4 | USB webcam | 0.60 | 0.50 | Off |
| 5 | Phone IP cam (DroidCam) | 0.50 | 0.44 | On |

---

## Recognition Tuning

All thresholds in `edge/config/camera_config.yaml` — **no rebuild needed**, just restart edge node:

```yaml
# Currently tuned for V380 / budget WiFi cameras
recognition_threshold: 0.42   # raise to 0.55+ for quality cameras
liveness_threshold: 0.38      # raise to 0.50+ for quality cameras
min_det_score: 0.48           # skip blurry/turned face crops
vote_window: 5                # frames to collect per person
min_votes: 3                  # minimum frames before deciding
vote_ttl_seconds: 3           # drop buffer if person absent this long
cooldown_seconds: 300         # suppress re-detection for 5 min
enhance_faces: true           # bilateral + unsharp + CLAHE (disable for quality cams)
superres: true                # FSRCNN x2 neural SR on face crops (disable for quality cams)

# Mask / face-covering detection
mask_det_min: 0.25            # min det_score to still attempt mask check on low-conf faces
mask_threshold: 0.55          # mask classifier confidence threshold
mask_cooldown_seconds: 60     # seconds between repeat masked_face alerts per track
# mask_model: edge/weights/face_mask_detector.onnx  # optional ONNX classifier

# Anti-spoof model path (MiniFASNet)
# antispoof_model: edge/weights/antispoof_128.onnx
```

To apply: `docker compose restart edge_node`

**Tuning tips:**
- Enrolled employees missed → lower `recognition_threshold` (try 0.38)
- Wrong people matching → raise `recognition_threshold` (try 0.55)
- Real faces rejected as spoof → lower `liveness_threshold` (try 0.32)
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
SLACK_WEBHOOK_URL=https://hooks.slack.com/...   # optional
```

Emails sent for: spoof attempts, intruders, blacklisted employees, after-hours detections, late arrivals, and daily attendance digest (18:00 via Celery).

Gmail: use an **App Password** (not your account password). Go to Google Account → Security → 2-Step Verification → App passwords.

---

## Downloaded Model Files

Both models are already downloaded in `edge/weights/`:

| File | Size | Purpose |
|---|---|---|
| `antispoof_128.onnx` | 1.85 MB | Anti-spoof: MiniFASNet print+replay (CelebA-Spoof) |
| `FSRCNN_x2.pb` | 9.4 KB | Neural super-resolution x2 for face crops |

If models are missing, see `edge/weights/DOWNLOAD_MODELS.txt` for instructions.

---

## Dashboard Pages

| Page | Path | Description |
|---|---|---|
| Overview | `/dashboard` | Stat cards, live cameras, occupancy, weekly/hourly charts, recent check-ins, live feed, alerts |
| Employees | `/dashboard/employees` | Employee list, face enrollment, blacklist/VIP flags |
| Cameras | `/dashboard/cameras` | Camera cards with MJPEG streams, add/edit/delete |
| Detection Log | `/dashboard/detection-log` | Every face detection: snapshot, timestamp, confidence, camera |
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
| `POST /api/v1/auth/refresh` | 30 req / min / IP |
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

## Production Security Checklist

- [ ] `SECRET_KEY` set to a random 64-char hex string
- [ ] `FACE_ENCRYPTION_KEY` set to a generated Fernet key
- [ ] `EDGE_TOKEN` set and matching on edge node
- [ ] `ENVIRONMENT=production`
- [ ] Default admin password changed immediately after first login
- [ ] Postgres and Redis not exposed on public interfaces
- [ ] Nginx configured with SSL
- [ ] Prometheus `/metrics` firewalled to internal network only
- [ ] SMTP credentials in `.env`, not committed to git

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
│   │   └── services/
│   │       ├── attendance_service.py   Main logic: gates, shifts, alerts, late notif
│   │       ├── alert_service.py        Fires alerts → DB + Redis + email
│   │       ├── face_service.py         Enrollment + pgvector match
│   │       └── notification_service.py SMTP email + webhook notifications
│   └── workers/             Celery: absentees, retention, snapshot purge, email digest
│
├── edge/
│   ├── src/
│   │   ├── utils/
│   │   │   ├── gpu.py          Runtime GPU auto-detection
│   │   │   └── superres.py     FaceSuperRes — FSRCNN x2 neural SR (with Lanczos fallback)
│   │   ├── detection/          YOLOv11 + ByteTrack person detector
│   │   ├── recognition/
│   │   │   ├── arcface.py      InsightFace ArcFace R100
│   │   │   ├── anti_spoof.py   MiniFASNet ONNX + heuristic (screen context + histogram temporal gate)
│   │   │   ├── mask_detector.py Upper/lower face texture classifier + optional ONNX slot
│   │   │   └── faiss_search.py Top-K cosine similarity
│   │   ├── camera/             RTSP reader (TCP, reconnect, backoff), MJPEG server
│   │   └── pipeline/
│   │       ├── frame_processor.py  SR → enhance → embed → vote engine
│   │       └── event_publisher.py  Redis + backend POST
│   ├── config/
│   │   └── camera_config.yaml  5 camera quality profiles, all thresholds
│   └── weights/
│       ├── antispoof_128.onnx  MiniFASNet print+replay model (1.85 MB) — downloaded
│       ├── FSRCNN_x2.pb        FSRCNN neural SR x2 model (9.4 KB) — downloaded
│       └── DOWNLOAD_MODELS.txt Download instructions
│
├── edge_standalone.py    Windows standalone: anti-spoof + SR + voting + GPU + reconnect
├── frontend/             Next.js 15 dashboard
├── infra/nginx/          Reverse proxy config
├── start.bat / stop.bat  Windows one-click start/stop
└── deploy.bat            Windows production deploy
```

---

## Troubleshooting

**Anti-spoof triggers on real people**
- Lower `liveness_threshold` in `camera_config.yaml` (try 0.32)
- Check edge logs for `spoof_score` values — values below threshold are flagged as spoof
- If heuristic is running (no ONNX model): check `edge/weights/antispoof_128.onnx` exists

**Anti-spoof not catching phone/screen replay**
- Verify model is loaded: check logs for `Anti-spoof model loaded` (not `heuristic fallback`)
- Lower `liveness_threshold` (try 0.35) — compressed streams produce lower P(live) scores
- Check V380 stream quality: use `/stream1` (HD) not `/stream2` (SD)
- Heuristic mode: screen-context check fires on frame 1 (phone backlight); histogram temporal gate builds over 3+ frames — both are active automatically

**Person wearing a face mask detected as unknown**
- Expected behaviour — ArcFace cannot generate a reliable embedding from a masked face
- A `masked_face` event fires with a snapshot; overlay shows yellow **MASKED** label
- To suppress false positives: raise `mask_threshold` in `camera_config.yaml` (try 0.65)
- To use an ONNX classifier: set `mask_model: edge/weights/face_mask_detector.onnx`

**Employees detected as unknown**
- Check edge logs for `best_sim=` values
- If sim is 0.35–0.45: lower `recognition_threshold`, re-enroll with better photos
- Make sure embeddings synced: look for `FAISS index resynced: N face embeddings`

**Super-resolution not working**
- Requires `opencv-contrib-python` (not plain `opencv-python`)
- Check logs for `FaceSuperRes: FSRCNN x2 loaded` — if not present, SR fell back to Lanczos
- Install: `pip install opencv-contrib-python`

**Standalone not detecting faces**
- Camera resolution may be too low — check log line `Camera connected: ... → WxH @ fps`
- If below 640 wide: standalone warns you automatically; switch to HD stream or higher-res camera

**Email notifications not sending**
- Set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO` in `.env`
- Gmail: use an App Password, not your login password
- Check backend logs for `SMTP error sending`

**"Could not reach the server" on login**
- Ensure `NEXT_PUBLIC_API_URL=http://localhost:8080` in `.env`
- Rebuild frontend: `docker compose up -d --build frontend`

**GPU not used by edge node**
- Set `DEVICE=cuda` in `.env` and restart: `docker compose restart edge_node`
- Verify: `docker compose logs edge_node | grep CUDAExecution`

**Port 80 conflict on Windows**
- Docker Desktop uses port 80 internally — use port 8080 instead (already configured)

See `DEVELOPER_NOTES.md` for architecture decisions, pipeline details, and extension guide.
