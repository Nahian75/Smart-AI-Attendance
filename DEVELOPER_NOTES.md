# Developer Notes — Smart AI Attendance System

Architecture decisions, bug-fix log, and extension guide for contributors.

---

## Architecture Decisions

### Why FastAPI + async SQLAlchemy?
The backend is I/O heavy: each recognition event hits the DB, Redis (cooldown check, pub/sub), and potentially Slack. Async FastAPI + asyncpg keeps all of this non-blocking on a single worker. Celery handles anything that can be deferred (marking absentees, retention cleanup, snapshot purge).

### Why pgvector instead of a dedicated vector DB?
Face embeddings are 512-d floats. We store them in pgvector so joins with the `employees` table are free. The edge node uses FAISS locally for sub-millisecond nearest-neighbour search and syncs from Postgres every 60 s. This avoids a network round-trip on every frame while keeping the DB as source of truth.

### Why FAISS on the edge, not the backend?
Face matching must run at camera frame rate (5–10 fps per camera). A backend HTTP call per frame adds 10–50 ms round-trip latency. FAISS on the edge does the search in < 1 ms. The backend only receives confirmed match events.

### Why multi-frame voting instead of per-frame decisions?
ArcFace similarity for the same person varies frame-to-frame (e.g. 0.35–0.58) due to pose, blur, and lighting. Deciding on a single frame causes flip-flopping between "recognised" and "unknown". The voting engine accumulates `vote_window` (default 7) quality-gated observations per track and decides when `min_votes` (default 4) are collected. The winning employee needs both a majority of frames AND mean similarity above the threshold. This eliminates the need to lower the threshold to catch bad frames.

### Why top-K FAISS matching instead of single top-1?
Each employee may have multiple enrolled photos (different angles, lighting). Single top-1 lookup returns whichever enrolled embedding happens to be closest — one bad enrollment photo can dominate. Top-K retrieves the `top_k` (default 5) nearest embeddings, groups them by employee, and scores each candidate as the mean of their similarities in that neighbourhood. This is more robust to partial facial occlusion and lighting variation.

### Why one ONNX Runtime session per model?
InsightFace's `FaceAnalysis.prepare()` loads the SCRFD detector and ArcFace recognition model into a single session. Sharing this across all cameras in a single process (via the shared `ArcFaceRecognizer` instance) avoids loading 500 MB of weights multiple times. `_INFERENCE_EXECUTOR` in `frame_processor.py` serialises inference calls so the models are used from one thread at a time.

### Why a single inference thread?
ONNX Runtime CUDA sessions are not thread-safe across concurrent `run()` calls on the same session. Serialising via `ThreadPoolExecutor(max_workers=1)` eliminates races without per-camera model copies.

### Why Redis for cooldowns and pub/sub?
Cooldown keys (`cooldown:{emp}:{cam}`) expire automatically via Redis TTL — no cleanup job needed. Pub/sub pushes attendance events to two WebSocket channels (`attendance:{tenant}` and `alerts:{tenant}`) without polling. Redis restart is safe: cooldowns reset (mildly permissive) and live-feed history restarts (cosmetic).

### Why separate WebSocket channels for attendance and alerts?
The `attendance:{tenant}` channel carries both raw edge events (recognition, unknown_person, spoof_attempt) and processed backend results (check_in, check_out). The `alerts:{tenant}` channel carries only security alert payloads from `AlertService.fire()`. Separating them means the alert panel connects to `/ws/alerts/` and receives alerts the moment they are created — without polling and without filtering out attendance noise.

### JWT design
Tokens carry `sub` (user UUID), `tenant_id`, `role`, `exp`, `iat`. The backend never hits the DB to validate a token — everything needed for auth and RBAC is in the payload. Token refresh issues a new token from a still-valid one; expired tokens must re-login.

### Tenant isolation
Every DB table has a `tenant_id` FK. Every query filters by `user.tenant_id` from the JWT. A single API instance serves multiple tenants without data leakage.

### Why nginx on port 8080 instead of 80?
Docker Desktop on Windows reserves port 80 internally. Port 80 conflicts prevent the nginx container from binding. Port 8080 is used instead and is documented in `.env` via `NEXT_PUBLIC_API_URL`.

### Snapshot storage and auto-purge
Snapshots (face crops from detections) are saved by the edge node to `/app/snapshots/{employee_id|unknown}/{timestamp}.jpg` and served via FastAPI `StaticFiles` at `/snapshots/`. A Celery beat task (`purge_snapshots`) runs nightly at 3 AM and deletes files older than 7 days. DB records are retained for 90 days (configurable via `EVENT_RETENTION_DAYS`).

---

## Key Files and Their Roles

```
backend/app/
  config.py                    Settings (pydantic-settings); production secret warnings
  dependencies.py              FastAPI deps: get_db, get_current_user, role_required, verify_edge_token
  main.py                      App factory: middleware, route registration, lifespan (Redis),
                                StaticFiles mount for /snapshots/
  core/security.py             hash_password, verify_password, create_access_token, decode_token
  core/middleware.py           TenantMiddleware, RateLimitMiddleware (in-memory, per-IP)
  models/attendance.py         RecognitionEvent, AttendanceLog, Alert, UnknownDetection
  models/shift.py              Shift, EmployeeShift — controls late/early/OT classification
  services/attendance_service.py   Main logic: confidence gate, cooldown, shift calc, alerts,
                                    _handle_unknown() fires unknown_person alert always (not just after-hours)
  services/alert_service.py        Fires alerts to DB + Redis pub/sub (alerts:{tenant})
  api/v1/ws.py                 Two WebSocket endpoints: /ws/attendance/ and /ws/alerts/
  api/v1/detections.py         Unified detection evidence log: RecognitionEvent + UnknownDetection
  api/v1/shifts.py             Shift CRUD + employee assignment
  api/v1/admin.py              User management (list, create, change role, deactivate)
  workers/tasks.py             apply_retention (DB), purge_snapshots (files, 7-day), mark_absentees
  workers/celery_app.py        Beat schedule: absentees@23:30, retention@02:00, snapshots@03:00, digest@18:00

edge/src/
  utils/gpu.py                 Runtime GPU detection — single source of truth for ORT providers + torch device
  detection/yolo_detector.py   YOLOv11 track() — device from gpu.py, 30% padded crops via frame_processor
  recognition/arcface.py       InsightFace ArcFace R100 (det_size=960×960 for better small-face detection)
  recognition/anti_spoof.py    MiniFASNet ONNX model (128×128, CelebA-Spoof trained) + heuristic fallback;
                                uses exact upstream preprocessing: RGB, 1.5× bbox expansion, letterbox, /255
  recognition/faiss_search.py  Top-K cosine search with per-employee mean aggregation; search_raw() for voting
  pipeline/frame_processor.py  Multi-frame voting engine: face-quality gate (min_det_score), per-track
                                observation buffer, majority-vote decision, provisional MJPEG labels
  pipeline/event_publisher.py  Posts recognition, unknown_person, spoof_attempt to backend; publishes all to Redis
  config/camera_config.yaml    All recognition thresholds — no rebuild needed, just restart edge_node

frontend/src/
  lib/api.ts                   All API calls; 401 auto-refresh + redirect
  lib/websocket.ts             connectAttendanceWS() + connectAlertsWS() — both with auto-reconnect
  lib/rbac.ts                  hasRole(), useRole() hook
  components/live/
    LiveEventFeed.tsx           Shows check_in/out (green), unknown_person (orange), spoof_attempt (red)
    AlertsFeed.tsx              Real-time via connectAlertsWS(); fallback 10s poll
  app/dashboard/detection-log/ Evidence log: every face capture with snapshot, confidence, camera, timestamp
  components/ui/DashboardShell.tsx  Sidebar with Detection Log nav entry, role badge, theme toggle
```

---

## Recognition Pipeline (Frame-by-Frame)

```
Frame arrives from RTSPReader
  └─ YOLO track() → person bounding boxes (ByteTrack IDs)
       └─ For each confirmed, non-cooldown track:
            └─ _crop_padded(frame, bbox, pad=0.30)   ← 30% padding ensures full head
                 └─ ArcFaceRecognizer.detect_and_embed(crop)  ← det_size=960
                      └─ face det_score < min_det_score (0.55)?  → SKIP (quality gate)
                           └─ AntiSpoofChecker.check(crop, bbox) → (is_live, spoof_score)
                                └─ FaissSearch.search_raw(embedding) → (best_emp, score)  ← no threshold
                                     └─ Append to per-track vote buffer
                                          └─ buffer.len >= min_votes (4)?
                                               └─ _decide() → majority vote + mean similarity
                                                    ├─ spoof_frames >= majority → spoof_attempt event
                                                    ├─ winner_votes >= majority AND mean >= threshold → recognition event
                                                    └─ vote_window full, no winner → unknown_person event
```

---

## Bug Fix Log

| Bug | File | Fix |
|---|---|---|
| `select` not imported | `reports.py` | Added `from sqlalchemy import select` |
| Duplicate `get_current_user` + `role_required` | `dependencies.py` | Removed second definitions |
| `Unauthorized` not imported | `alerts.py` | Added `from ...core.exceptions import Unauthorized` |
| `Mapped[float]` on Integer column | `alert_config.py` | Changed to `Mapped[int]` |
| `clear_loitering` sync calling `asyncio.create_task` | `alert_service.py` | Made async |
| POST `/match` unreachable (shadowed by `/{employee_id}`) | `enrollment.py` | Moved `/match` before `/{employee_id}` |
| `early_by_min` missing from `AttendanceLogOut` | `schemas/attendance.py` | Added field |
| `ChangePasswordIn` name collision | `alert_config.py` | Renamed to `AdminConfigPasswordIn` |
| Dark mode not working | `tailwind.config.js` | Added `darkMode: "class"` |
| `hasRole()` always returns false on initial render | All pages | Replaced with `useRole()` hook |
| unknown_person / spoof_attempt events never reached backend | `event_publisher.py` | Extended to send all 3 event types |
| `employee_id` required in schema but None for unknown/spoof | `schemas/attendance.py` | Made `employee_id` optional |
| Unknown person alert only fired after hours | `attendance_service.py` | Always fire `unknown_person` alert |
| DB alerts never committed (rolled back on request end) | `attendance_service.py` | Added `await db.commit()` after spoof path and `_handle_unknown()` |
| `snapshot_url` missing from `unknown_person` event | `frame_processor.py` | Added `snap` to event dict |
| Unknown/spoof tracks not cooled down → alert spam | `frame_processor.py` | Set `_cooldown[track_id]` for all event types |
| `_get_current_shift()` could return wrong/deactivated shift | `attendance_service.py` | Added `Shift.is_active` filter + `order_by(effective_from.desc())` |
| Same-day shift reassignment: old + new both match | `attendance_service.py` | Changed `effective_to >= day` → `effective_to > day` |
| Frontend `NEXT_PUBLIC_*` not baked in at build time | `docker-compose.yml` | Moved from `environment` to `build.args` |
| ENVIRONMENT=development enabled verbose SQL logging | `.env` | Changed to `production` + downgraded secret check to warnings |
| Port 80 conflict with Docker Desktop on Windows | `docker-compose.yml` | Changed nginx to `8080:80` |
| ALLOWED_ORIGINS didn't include port 8080 | `.env` | Added `ALLOWED_ORIGINS=http://localhost:8080` |
| Anti-spoof in pass-through mode (no model) | `anti_spoof.py` | Downloaded MiniFASNet ONNX + implemented heuristic fallback |
| Single-frame recognition flip-flop | `frame_processor.py` | Multi-frame temporal voting engine (7 frames, majority vote) |
| Single top-1 FAISS unstable for varied photos | `faiss_search.py` | Top-K matching with per-employee mean similarity aggregation |
| Face crops cutting off heads (tight YOLO bbox) | `frame_processor.py` | 30% padding via `_crop_padded()` |
| Low similarity scores from small faces | `arcface.py` | `det_size` increased 640→960 |
| Alerts polled every 15s (stale) | `AlertsFeed.tsx` | Real-time WebSocket `/ws/alerts/` + 10s fallback poll |
| Live feed showed only check-in/out (missed unknown/spoof) | `LiveEventFeed.tsx` | Extended to show all event types with color coding |
| Snapshot files accumulated forever (disk full) | `tasks.py` + `celery_app.py` | `purge_snapshots` task: deletes files >7 days, runs nightly at 03:00 |

---

## Security Architecture

### Password hashing
```python
# backend/app/core/security.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hash_password(p)        # → bcrypt hash
verify_password(p, h)   # → bool
```

### JWT flow
```
POST /auth/login → validate bcrypt → create_access_token(sub, tenant_id, role) → return
GET  /any        → get_current_user dependency → decode_token(jwt) → CurrentUser dataclass
```
`decode_token` validates signature + expiry without a DB call.

### Edge token
`verify_edge_token` uses `secrets.compare_digest` (constant-time). In dev (`EDGE_TOKEN == ""`), check is skipped.

### Rate limiter
`RateLimitMiddleware` is in-process — one bucket dict per worker. Auth endpoints capped at 30 req/min/IP; others at 200 req/min/IP.

---

## GPU Detection Flow

```
DEVICE env var → use it directly
Otherwise:
  ORT available providers?
    CUDAExecutionProvider  → NVIDIA
    ROCMExecutionProvider  → AMD
    OpenVINOExecutionProvider → Intel
    DmlExecutionProvider   → DirectML (Windows)
  torch.xpu available?     → Intel IPEX
  fallback                 → CPU

Result cached in _CACHED (module-level singleton)
```

Set `DEVICE=cuda` in `.env` for NVIDIA. The edge node logs which providers are active on startup.

---

## Anti-Spoof Model Details

**Model:** `hairymax/Face-AntiSpoofing` — MiniFASNet-style CNN trained on CelebA-Spoof dataset
- Input: `[1, 3, 128, 128]` float32, **RGB**, letterboxed, pixels / 255
- Output: `[1, 2]` logits → softmax → **index 0 = P(live)**, index 1 = P(spoof)
- Face crop expanded **1.5× around bbox** before preprocessing (matches upstream training crop)
- Accuracy: ~92.9%, AUC-ROC ~0.987 on CelebA-Spoof binary classification
- Model file: `edge/weights/antispoof_128.onnx` — mounted as volume, swappable without rebuild

**Fallback heuristic** (when no model file): multi-cue texture analysis
- Laplacian variance (40%) + Sobel gradient energy (30%) + HSV saturation std (20%) + FFT high-freq ratio (10%)
- Threshold auto-lowered to 0.35 in heuristic mode; model mode uses 0.55

---

## Recognition Tuning Reference

All in `edge/config/camera_config.yaml` — restart edge_node to apply (no rebuild):

| Parameter | Default | Effect |
|---|---|---|
| `recognition_threshold` | 0.50 | Min mean similarity to confirm a match. Raise → fewer false matches. Lower → more recall. |
| `liveness_threshold` | 0.55 | Min P(live) from anti-spoof model. Lower → fewer false spoof blocks. |
| `min_det_score` | 0.55 | Skip face crops below this detection quality (turned/blurry). |
| `vote_window` | 7 | Frames to buffer per track before deciding. Higher → more stable but slower. |
| `min_votes` | 4 | Min good frames needed before decision is made. |
| `vote_ttl_seconds` | 5 | Clear vote buffer if person not seen for this many seconds. |
| `cooldown_seconds` | 300 | Suppress re-recognition of same person for this long. |
| `faiss_top_k` | 5 | Neighbours to retrieve per query. Higher = more stable for employees with many photos. |

---

## How to Add a New API Endpoint

1. Add route to `backend/app/api/v1/*.py`
2. Add role check: `user: CurrentUser = Depends(role_required("hr"))`
3. Add Pydantic schema to `backend/app/schemas/*.py` if needed
4. Register router in `main.py` if new file
5. Add TypeScript method to `frontend/src/lib/api.ts`
6. Use from page component

## How to Add a New Alert Type

1. Add to `SEVERITY` dict in `alert_service.py`
2. Call `await self.alerts.fire(tenant_id, "new_type", message, ...)` from `attendance_service.py`
3. Add icon to `ICONS` dict in `AlertsFeed.tsx`
4. Add to alert type filters in `alerts/page.tsx` and `security-alerts/page.tsx`

## How to Add a New Dashboard Page

1. Create `frontend/src/app/dashboard/<name>/page.tsx`
2. Import and use `DashboardShell` and `useRole`
3. Add nav entry to `NAV` array in `DashboardShell.tsx`
4. If admin-only: use `{can("admin") && ...}` pattern

## How to Support a New GPU

1. Create `edge/Dockerfile.edge.<name>` with GPU-specific base image and ONNX Runtime package
2. Add detection logic to `edge/src/utils/gpu.py`
3. Create `docker-compose.prod.<name>.yml` override with device mounts
4. Add to `deploy.sh` / `deploy.bat` GPU detection block
5. Add `make deploy-<name>` target to `Makefile`

---

## Celery Scheduled Tasks

| Task | Schedule | What it does |
|---|---|---|
| `mark_absentees` | 23:30 daily | Creates `absent` attendance records for employees with no log today |
| `apply_retention` | 02:00 daily | Deletes `RecognitionEvent` DB rows older than `EVENT_RETENTION_DAYS` (default 90) |
| `purge_snapshots` | 03:00 daily | Deletes snapshot image files older than 7 days from `/app/snapshots/` |
| `email_digest` | 18:00 daily | Placeholder — implement SMTP digest here |

---

## Development Workflow

```bash
# Start (Windows)
start.bat          # First run builds images; subsequent runs start in ~10s

# Stop (Windows)
stop.bat

# Watch logs
docker compose logs -f edge_node
docker compose logs -f backend

# Restart edge only (after config change)
docker compose restart edge_node

# Rebuild specific service
docker compose up -d --build backend

# Re-seed database
docker compose exec backend python seed.py
```

### Threshold changes (no rebuild)
Edit `edge/config/camera_config.yaml`, then:
```bash
docker compose restart edge_node backend
```

### Frontend hot-reload
The production compose uses a built Next.js image — no hot-reload. For frontend development, run directly:
```bash
cd frontend && npm run dev
# Set NEXT_PUBLIC_API_URL=http://localhost:8080 in .env.local
```

---

## Known Limitations

1. **Rate limiter is in-process** — does not share state across multiple uvicorn workers. For multi-worker prod deployments, use Redis-backed rate limiting (e.g. `slowapi` with Redis storage).

2. **Celery tasks are fire-and-forget** — no dead-letter queue. Failed tasks are logged but not retried automatically. Add `autoretry_for` decorators for production reliability.

3. **SMTP password stored in plaintext** — `alert_configs.smtp_password` is not encrypted. For production, use an environment variable or secrets manager.

4. **Single FAISS index per edge node** — reloaded in full every 60 s. For tenants with 10,000+ employees, consider incremental updates or a persistent FAISS index file.

5. **WebSocket creates a new Redis connection per client** — acceptable for small deployments. For high concurrency, share a single pub/sub connection from `app.state`.

6. **Anti-spoof model not trained on all attack types** — MiniFASNet (CelebA-Spoof) detects print and replay attacks well, but 3D mask attacks may pass. For high-security deployments, integrate a more comprehensive liveness model.

7. **Snapshot purge runs on celery_worker** — worker must have the `/app/snapshots` volume mounted (already configured in `docker-compose.yml`). If the worker is on a different host, snapshot cleanup must be handled externally.
