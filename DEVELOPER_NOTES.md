# Developer Notes — Smart AI Attendance System

Architecture decisions, bug-fix log, extension guide, and tuning reference for contributors.

---

## Architecture Decisions

### Why FastAPI + async SQLAlchemy?
The backend is I/O heavy: each recognition event hits the DB, Redis (cooldown check, pub/sub), and optionally SMTP + Slack. Async FastAPI + asyncpg keeps all of this non-blocking on a single worker. Celery handles deferrable work (marking absentees, retention cleanup, email digest).

### Why pgvector instead of a dedicated vector DB?
Face embeddings are 512-d floats stored in pgvector so joins with `employees` are free. The edge node uses FAISS locally for sub-millisecond search and syncs from Postgres every 60 s. This avoids a network round-trip on every frame while keeping the DB as source of truth.

### Why FAISS on the edge, not the backend?
Face matching must run at camera frame rate (5–10 fps). A backend HTTP call per frame adds 10–50 ms latency. FAISS on the edge does the search in < 1 ms. The backend only receives confirmed match events.

### Why multi-frame voting instead of per-frame decisions?
ArcFace similarity for the same person varies frame-to-frame (0.35–0.58) due to pose, blur, and lighting. Single-frame decisions cause flip-flopping. The voting engine accumulates `vote_window` quality-gated observations per ByteTrack ID and decides when `min_votes` are collected. The winning employee needs both a majority of frames AND mean similarity above threshold.

### Why top-K FAISS matching instead of single top-1?
Each employee has multiple enrolled photos. Single top-1 returns whichever enrolled embedding is closest — one bad photo can dominate. Top-K retrieves the K nearest, groups by employee, scores by mean similarity in that neighbourhood. More robust to partial occlusion and lighting variation.

### Why FSRCNN for face-crop super-resolution?
V380 and budget WiFi cameras apply heavy H.264 quantisation — faces at typical entry-gate distances end up as 50–100 px wide crops. FSRCNN-small_x2 (9.4 KB) runs in 1–3 ms per crop on CPU and gives genuine 2× resolution from CNN weights, not just bicubic interpolation. Applied before ArcFace embedding it lifts similarity scores 10–25% on compressed streams. Full-frame SR would cost ~400 ms/frame (unusable); face-crop SR adds ~2 ms.

### Why the anti-spoof heuristic uses luminance variance?
Screen backlight emits spatially uniform light: a phone held to the camera has very uniform block-mean luminance across the face region. Real faces under room lighting have natural shadow gradients. This cue survives H.264 compression — unlike FFT moiré detection which requires the screen pixel grid to be preserved in the stream (it isn't on V380). The luminance score carries 25% weight in the heuristic.

### Why spoof voting fires at majority-1 frames?
The MiniFASNet model assigns P(live) scores that vary per frame — a phone held at an angle may score above the threshold 2 out of 5 times. Using strict majority (ceil(n/2)) allowed these marginal attacks through. Firing at `max(1, majority-1)` requires only one less spoof frame to trigger, catching phone replays that occasionally fool the model.

### Why MediaPipe for head-pose filtering instead of a custom model?
MediaPipe Face Mesh gives 468 3D landmarks from a single 50 KB TFLite model in ~5–8 ms on CPU. The key insight is that we don't need exact angle degrees — we only need a reliable relative measure. Normalising nose-tip displacement by inter-eye distance gives a pose proxy that's invariant to face size and works on 80–200 px crops. A similarity transform from the 5 key points (eyes, nose, mouth corners) warps the face to the same positions ArcFace was trained on, eliminating the random ~15° rotation and scale variance that degrades similarity scores. The result is each vote in the buffer comes from a geometrically consistent input — raising mean similarity 5–15% on entry-gate cameras where people walk in at angles.

`static_image_mode=True` is used instead of video mode because we pass cropped face images (not full frames) from potentially different people across cameras — temporal tracking across crops would give wrong landmark predictions.

### Why one ONNX Runtime session per model?
InsightFace `FaceAnalysis.prepare()` loads SCRFD + ArcFace into a single session. Sharing across cameras via the shared `ArcFaceRecognizer` instance avoids loading 500 MB of weights multiple times. `_INFERENCE_EXECUTOR(max_workers=1)` in `frame_processor.py` serialises inference calls so models are used from one thread at a time (CUDA sessions are not thread-safe).

### Why Redis for cooldowns and pub/sub?
Cooldown keys (`cooldown:{emp}:{cam}`) expire automatically via Redis TTL — no cleanup job needed. Pub/sub pushes events to two WebSocket channels without polling. Redis restart is safe: cooldowns reset (mildly permissive) and live-feed history restarts (cosmetic only).

### Why separate WebSocket channels for attendance and alerts?
`attendance:{tenant}` carries raw edge events and processed backend results. `alerts:{tenant}` carries only security alert payloads from `AlertService.fire()`. Separating them means the alert panel receives alerts the moment they are created — without polling and without filtering attendance noise.

### Why SMTP runs in a ThreadPoolExecutor?
`smtplib` is blocking. Running it in `_MAIL_POOL` (single-threaded executor) keeps the FastAPI async event loop unblocked. A single thread is enough — email is best-effort, not latency-sensitive.

---

## Key Files and Their Roles

```
backend/app/
  config.py                    Settings (pydantic-settings); SMTP, Slack, thresholds, storage
  dependencies.py              FastAPI deps: get_db, get_current_user, role_required, verify_edge_token
  main.py                      App factory: middleware, route registration, lifespan (Redis), StaticFiles
  core/security.py             hash_password, verify_password, create_access_token, decode_token
  core/middleware.py           TenantMiddleware, RateLimitMiddleware (in-memory, per-IP)
  models/attendance.py         RecognitionEvent, AttendanceLog, Alert, UnknownDetection
  models/shift.py              Shift, EmployeeShift — controls late/early/OT classification
  services/attendance_service.py   Main logic: confidence gate, cooldown, shift calc, alerts, late email
  services/alert_service.py        Fires alerts → DB + Redis pub/sub + email (_notify_email)
  services/notification_service.py SMTP email (TLS/STARTTLS via smtplib executor) + webhook fire
  services/face_service.py         Enrollment + pgvector nearest-neighbour match
  api/v1/ws.py                 Two WebSocket endpoints: /ws/attendance/ and /ws/alerts/
  api/v1/detections.py         Unified detection evidence log: RecognitionEvent + UnknownDetection
  workers/tasks.py             apply_retention, purge_snapshots, mark_absentees, email_digest (implemented)
  workers/celery_app.py        Beat schedule: absentees@23:30, retention@02:00, snapshots@03:00, digest@18:00

edge/src/
  utils/gpu.py                 Runtime GPU detection — single source of truth for ORT providers + torch device
  utils/superres.py            FaceSuperRes: FSRCNN x2 via cv2.dnn_superres; Lanczos fallback
  detection/yolo_detector.py   YOLOv11 track() with ByteTrack; device from gpu.py
  recognition/arcface.py          InsightFace ArcFace R100; auto det_size from camera resolution
  recognition/anti_spoof.py       MiniFASNet ONNX (print+replay, 1.5× bbox crop, 128×128 RGB, /255)
                                   + heuristic: Laplacian(28%) + gradient(22%) + saturation(15%)
                                              + FFT(10%) + luminance_patch_variance(25%)
                                   Spoof voting fires at majority-1 frames (stricter than majority)
  recognition/mediapipe_align.py  MediaPipeFaceAligner: head-pose filter (yaw/pitch via nose displacement)
                                   + 5-point similarity transform to 112×112 ArcFace canonical alignment
                                   Shared across all cameras (static_image_mode=True, stateless per call)
                                   Thresholds: mp_max_yaw (default 40°), mp_max_pitch (default 30°)
                                   Gracefully disabled if mediapipe not installed
  recognition/faiss_search.py     Top-K cosine search with per-employee mean aggregation; search_raw() for voting
  pipeline/frame_processor.py     Full pipeline: quality gate → pose filter+align → anti-spoof → SR → enhance → embed → vote
  pipeline/event_publisher.py  Posts all event types (recognition, unknown, spoof) to backend + Redis
  config/camera_config.yaml    5 camera quality profiles; all recognition thresholds; no rebuild needed
  weights/antispoof_128.onnx   MiniFASNet print+replay model (1.85 MB) — downloaded
  weights/FSRCNN_x2.pb         FSRCNN-small x2 neural SR model (9.4 KB) — downloaded

edge_standalone.py             Windows standalone (no Docker):
                                - Anti-spoof: ONNX model + heuristic fallback (was hardcoded is_live=True)
                                - Multi-frame voting: VoteBuffer (embedding-cluster pseudo-tracking)
                                - GPU: CUDA / DirectML / CPU auto-detected
                                - Face enhancement: bilateral + unsharp + CLAHE
                                - Neural SR: FSRCNN x2 via FaceSuperRes inline class
                                - Auto-reconnect: exponential backoff on stream failure
                                - Embedding resync: every 60 s from backend
                                - HTTP MJPEG support (DroidCam, IP Webcam app)
                                - Logs actual stream resolution on connect

frontend/src/
  lib/api.ts                   All API calls; 401 auto-refresh + redirect
  lib/websocket.ts             connectAttendanceWS() + connectAlertsWS() — both with auto-reconnect
  lib/rbac.ts                  hasRole(), useRole() hook
  components/live/
    LiveEventFeed.tsx           check_in/out (green), unknown_person (orange), spoof_attempt (red)
    AlertsFeed.tsx              Real-time via connectAlertsWS(); fallback 10 s poll
  app/dashboard/detection-log/ Evidence log: every face capture with snapshot, confidence, camera
```

---

## Recognition Pipeline (Frame-by-Frame)

```
Frame arrives from RTSPReader
  └─ YOLO track() → person bounding boxes (ByteTrack IDs)
       └─ For each confirmed track (is_confirmed() == True):
            └─ _crop_padded(frame, bbox, pad=0.30)   ← 30% padding ensures full head
                 └─ ArcFaceRecognizer.detect_and_embed(crop)  ← auto det_size
                      └─ det_score < min_det_score?  → SKIP (quality gate)
                           └─ AntiSpoofChecker.check(raw_crop, bbox)
                              → (is_live, spoof_score)
                              [uses raw unenhanced crop — enhancement removes screen artifacts]
                                   └─ FaceSuperRes.upscale(face_crop)  ← FSRCNN x2 neural SR
                                        └─ _enhance_face(sr_face)      ← bilateral+unsharp+CLAHE
                                             └─ ArcFaceRecognizer.detect_and_embed(enhanced)
                                             └─ MediaPipeFaceAligner.process(face_img)
                                                  ├─ too angled → SKIP frame (not added to vote buffer)
                                                  └─ aligned 112×112 crop (similarity transform)
                                                       └─ FaissSearch.search_raw(embedding)
                                                            → (best_emp, score)  ← no threshold yet
                                                            └─ Append to per-track vote buffer
                                                                 └─ buffer.len >= min_votes?
                                                                      └─ _decide()
                                                                           ├─ spoof_frames >= majority-1
                                                                           │   → spoof_attempt event
                                                                           ├─ winner_votes >= majority
                                                                           │   AND mean >= threshold
                                                                           │   → recognition event
                                                                           └─ window full, no winner
                                                                               → unknown_person event
```

---

## Anti-Spoof Model Details

**Model:** `AntiSpoofing_print-replay_1.5_128.onnx` (saved as `antispoof_128.onnx`)
- Source: `hairymax/Face-AntiSpoofing` on GitHub
- Trained to detect both **print attacks** (photos) and **replay attacks** (phone/screen)
- Input: `[1, 3, 128, 128]` float32, RGB, letterboxed, pixels / 255
- Output: `[1, 2]` logits → softmax → **index 0 = P(live)**, index 1 = P(spoof)
- Face bbox expanded **1.5× (bbox_inc)** before preprocessing — matches training crop
- AUC-ROC ~0.987 on CelebA-Spoof binary classification

**Spoof voting rule (frame_processor.py):**
```python
spoof_threshold = max(1, majority - 1)   # fires one frame earlier than majority
spoof_obs = [o for o in buf if not o["is_live"]]
if len(spoof_obs) >= spoof_threshold:
    → spoof_attempt event
```

**Heuristic fallback** (when model file missing):
| Cue | Weight | Why |
|---|---|---|
| Laplacian variance | 28% | Printed photos are blurry |
| Sobel gradient energy | 22% | Low energy = flat surface |
| HSV saturation std | 15% | Printed ink has less colour range |
| FFT high-freq ratio | 10% | Screen moiré (weak on H.264 streams) |
| Luminance patch variance | 25% | Screen backlight is uniform; real faces have shadow gradients |

---

## Neural Super-Resolution Details

**Model:** FSRCNN-small_x2.pb (9.4 KB)
- Source: `Saafke/FSRCNN_Tensorflow` on GitHub
- Architecture: Fast Super-Resolution CNN — designed for real-time use
- Scale: 2× (e.g., 70×70 face crop → 140×140)
- Runtime: 1–3 ms per face crop on CPU via `cv2.dnn_superres`
- Requires: `opencv-contrib-python` (NOT plain `opencv-python`)

**Placement in pipeline:**
- SR runs **after** anti-spoof, **before** ArcFace re-embedding
- Anti-spoof intentionally uses the raw compressed crop — the screen pixel grid / moiré (however faint) is more visible before upscaling
- ArcFace sees the upscaled+enhanced crop — more pixels = better 512-d embedding

**Fallback:** If `cv2.dnn_superres` is unavailable or model missing, `FaceSuperRes.upscale()` falls back to `cv2.resize(..., INTER_LANCZOS4)` silently.

---

## MediaPipe Face Alignment Details

**Module:** `edge/src/recognition/mediapipe_align.py`  
**Dependency:** `mediapipe==0.10.35` (already in `edge/requirements.txt`)

### Head-pose estimation

Uses normalised nose-tip displacement relative to the eye midpoint:

```
nose_dx = (nose_tip.x - eye_mid.x) / eye_dist   # yaw proxy   — 0 = frontal
nose_dy = (nose_tip.y - eye_mid.y) / eye_dist   # pitch proxy  — ~0.5 = frontal
```

| Condition | Meaning | Action |
|---|---|---|
| `abs(nose_dx) > 0.35` | Yaw > ~40° (face turned left/right) | Skip frame |
| `nose_dy < 0.10` | Extreme upward tilt | Skip frame |
| `nose_dy > 0.75` | Extreme downward tilt | Skip frame |

Tune via `camera_config.yaml`: `mp_max_yaw` and `mp_max_pitch`.

### 5-point alignment

Key landmarks used:
| Point | Face Mesh indices |
|---|---|
| Left eye centre | avg(33, 133) |
| Right eye centre | avg(362, 263) |
| Nose tip | 4 |
| Left mouth corner | 61 |
| Right mouth corner | 291 |

`cv2.estimateAffinePartial2D(src, dst, method=LMEDS)` computes a 4-DOF similarity transform (uniform scale + rotation + translation — no shear). Output is a 112×112 crop with eyes, nose, and mouth at the canonical positions ArcFace was trained on.

### Pipeline position

```
quality gate → [MediaPipe: pose check → warp] → mask check → anti-spoof → SR → enhance → re-embed → vote
```

Placed **before** enhancement: the aligner produces a geometrically correct crop; enhancement then sharpens it. Both steps feed the same `detect_and_embed` re-embed call.

### Graceful degradation

If `mediapipe` is not installed, `_init_mesh()` catches the `ImportError` and sets `self._mesh = None`. `FrameProcessor` checks `face_aligner.available` before calling — frames pass through completely unchanged. No code path breaks.

---

## Notification Service

`backend/app/services/notification_service.py` — all outbound communications:

```python
# Email methods (all skip silently if SMTP not configured)
await notifier.notify_spoof(camera_id, snapshot_url)
await notifier.notify_intruder(camera_id, snapshot_url)
await notifier.notify_blacklist(employee_name, camera_id, snapshot_url)
await notifier.notify_late(employee_name, late_by_min)
await notifier.notify_after_hours(employee_name, camera_id)
await notifier.notify_digest(date_str, total, present, absent, late)
```

Called automatically from:
- `AlertService._notify_email()` — for spoof, intruder, blacklist, after_hours alerts
- `AttendanceService.process_recognition_event()` — for late arrivals
- `tasks.email_digest` Celery task — for daily digest at 18:00

SMTP uses `smtplib` in a `ThreadPoolExecutor` (non-blocking). Supports STARTTLS (port 587) and SSL (port 465).

---

## Camera Quality Profiles

`edge/config/camera_config.yaml` has 5 profiles. Uncomment the matching one:

| Profile | Type | `recognition_threshold` | `liveness_threshold` | `superres` | `enhance_faces` |
|---|---|---|---|---|---|
| 1 (active) | V380 / budget WiFi 640p | 0.42 | 0.38 | true | true |
| 2 | Mid-range IP 1080p | 0.55 | 0.48 | false | true |
| 3 | Quality camera (Axis, Bosch) | 0.65 | 0.55 | false | false |
| 4 | USB webcam (close range) | 0.60 | 0.50 | false | false |
| 5 | Phone IP camera | 0.50 | 0.44 | true | true |

Restart edge node after changing profile: `docker compose restart edge_node`

---

## Standalone Mode (edge_standalone.py)

Full-featured single-file edge node for Windows without Docker:

| Feature | Old (before update) | New |
|---|---|---|
| Anti-spoof | Hardcoded `is_live=True` | ONNX model + heuristic fallback |
| Multi-frame voting | None (single frame) | VoteBuffer with EMA centroid tracking |
| GPU support | CPU only | CUDA / DirectML / CPU auto-detect |
| Face enhancement | None | Bilateral + unsharp + CLAHE |
| Neural SR | None | FSRCNN x2 (with Lanczos fallback) |
| Reconnect on drop | Log and stop | Exponential backoff (3 s → 30 s) |
| Embedding resync | Never | Every 60 s from backend |
| Camera types | RTSP + webcam | + HTTP MJPEG (DroidCam, IP Webcam app) |
| Resolution logging | None | Logs WxH @ fps on connect + warns if < 640 wide |

Run in conda env that has `opencv-contrib-python`:
```powershell
$env:CAMERA_SRC="rtsp://admin:admin@192.168.x.x:554/stream1"
C:\Users\ANTS-Pc\.conda\envs\mouza_processor_venv\python.exe edge_standalone.py
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
| DB alerts never committed | `attendance_service.py` | Added `await db.commit()` after spoof/unknown paths |
| `snapshot_url` missing from `unknown_person` event | `frame_processor.py` | Added `snap` to event dict |
| Unknown/spoof tracks not cooled down → alert spam | `frame_processor.py` | Set `_cooldown[track_id]` for all event types |
| `_get_current_shift()` returned wrong/deactivated shift | `attendance_service.py` | Added `Shift.is_active` filter + `order_by(effective_from.desc())` |
| Same-day shift reassignment: old + new both match | `attendance_service.py` | Changed `effective_to >= day` → `effective_to > day` |
| Frontend `NEXT_PUBLIC_*` not baked in at build time | `docker-compose.yml` | Moved from `environment` to `build.args` |
| Port 80 conflict with Docker Desktop on Windows | `docker-compose.yml` | Changed nginx to `8080:80` |
| ALLOWED_ORIGINS didn't include port 8080 | `.env` | Added `http://localhost:8080` |
| **Standalone: anti-spoof bypassed** | `edge_standalone.py` | Full rewrite — ONNX model + heuristic; removed hardcoded `is_live=True` |
| **Standalone: no multi-frame voting** | `edge_standalone.py` | Added `VoteBuffer` with EMA centroid pseudo-tracking |
| **Standalone: GPU not used** | `edge_standalone.py` | Added `detect_gpu()` — CUDA / DirectML / CPU |
| **Standalone: no reconnect on stream drop** | `edge_standalone.py` | Exponential backoff reconnect loop |
| **Standalone: embeddings never resynced** | `edge_standalone.py` | Resync every 60 s from backend |
| **`mask_detector` not passed to `camera_watch_loop`** | `main.py` | Added `mask_detector` parameter — hot-added cameras now get mask detection |
| **MediaPipe head-pose filter + alignment** | `recognition/mediapipe_align.py`, `frame_processor.py`, `main.py` | New `MediaPipeFaceAligner` — rejects angled frames, warps to canonical 112×112 for ArcFace |
| **SDK `.so` symlinks breaking Docker build context** | `edge/.dockerignore` | Added `.dockerignore` to exclude `sdk/` (already volume-mounted at runtime) |
| **Anti-spoof weak on screen replay (H.264)** | `anti_spoof.py` | Added luminance patch variance cue (25% weight) |
| **Anti-spoof spoof threshold too lenient** | `frame_processor.py` | Fires at `majority - 1` frames (not `majority`) |
| **No neural SR on face crops** | `frame_processor.py`, `edge_standalone.py` | FSRCNN x2 via `superres.py` before ArcFace embed |
| **No email notifications** | `notification_service.py` | Full SMTP implementation (TLS, HTML templates) |
| **`email_digest` was a stub** | `tasks.py` | Implemented: DB query → `NotificationService.notify_digest()` |
| **Alert emails not sent** | `alert_service.py` | Added `_notify_email()` wired for high-severity types |
| **Late arrival not emailed** | `attendance_service.py` | Added `NotificationService().notify_late()` call |

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
POST /auth/login → validate bcrypt → create_access_token(sub, tenant_id, role) → return JWT
GET  /any        → get_current_user → decode_token(jwt) → CurrentUser dataclass
```
`decode_token` validates signature + expiry without a DB call.

### Edge token
`verify_edge_token` uses `secrets.compare_digest` (constant-time). In dev (`EDGE_TOKEN == ""`), check skipped.

---

## GPU Detection Flow

```
DEVICE env var → use directly
Otherwise:
  ORT available providers?
    CUDAExecutionProvider       → NVIDIA
    ROCMExecutionProvider       → AMD
    OpenVINOExecutionProvider   → Intel
    DirectMLExecutionProvider   → Windows GPU (standalone only)
  fallback                      → CPU

Result cached as _CACHED (module-level singleton, re-used by all models)
```

Both the anti-spoof ONNX session and InsightFace use the same ORT providers from `detect_gpu()`.

---

## Celery Scheduled Tasks

| Task | Schedule | What it does |
|---|---|---|
| `mark_absentees` | 23:30 daily | Creates `absent` records for active employees with no log today |
| `apply_retention` | 02:00 daily | Deletes `RecognitionEvent` DB rows older than `EVENT_RETENTION_DAYS` (default 90 days) |
| `purge_snapshots` | 03:00 daily | Deletes snapshot image files older than 7 days from `/app/snapshots/` |
| `email_digest` | 18:00 daily | Queries today's attendance stats → sends HTML digest email via SMTP |

---

## How to Add a New API Endpoint

1. Add route to `backend/app/api/v1/*.py`
2. Add role check: `user: CurrentUser = Depends(role_required("hr"))`
3. Add Pydantic schema to `backend/app/schemas/*.py` if needed
4. Register router in `main.py` if new file
5. Add TypeScript method to `frontend/src/lib/api.ts`

## How to Add a New Alert Type

1. Add to `SEVERITY` dict in `alert_service.py`
2. Call `await self.alerts.fire(tenant_id, "new_type", message, ...)` from service
3. Add email handler in `alert_service._notify_email()` if high-severity
4. Add icon to `ICONS` dict in `AlertsFeed.tsx`
5. Add to alert type filters in `alerts/page.tsx` and `security-alerts/page.tsx`

## How to Add a New Email Notification

1. Add method to `NotificationService` in `notification_service.py`
2. Use `await self._send_all(subject, body_text, body_html)` — sends email + webhooks
3. Use `_html_alert(title, color, lines)` helper for consistent HTML template
4. Call from the appropriate service method

## How to Add a Camera Quality Profile

1. Add a new commented block to `edge/config/camera_config.yaml`
2. Document thresholds: `recognition_threshold`, `liveness_threshold`, `min_det_score`, `enhance_faces`, `superres`
3. Update the profiles table in `README.md` and this file

## How to Support a New GPU

1. Create `edge/Dockerfile.edge.<name>` with GPU-specific base image and ONNX Runtime package
2. Add detection logic to `edge/src/utils/gpu.py`
3. Create `docker-compose.prod.<name>.yml` override with device mounts
4. Add to `deploy.sh` / `deploy.bat` GPU detection block

---

## Development Workflow

```bash
# Start (Windows)
start.bat          # First run builds images; subsequent runs start in ~10s

# Stop
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

# Run standalone (Windows, no Docker)
$env:CAMERA_SRC="0"
C:\Users\ANTS-Pc\.conda\envs\mouza_processor_venv\python.exe edge_standalone.py
```

### Threshold changes (no rebuild needed)
Edit `edge/config/camera_config.yaml`, then:
```bash
docker compose restart edge_node
```

### Frontend hot-reload
Production compose uses a built Next.js image — no hot-reload. For frontend dev:
```bash
cd frontend && npm run dev
# Set NEXT_PUBLIC_API_URL=http://localhost:8080 in .env.local
```

---

## Known Limitations

1. **Rate limiter is in-process** — does not share state across multiple uvicorn workers. For multi-worker prod deployments, use Redis-backed rate limiting (e.g. `slowapi` with Redis).

2. **Celery tasks are fire-and-forget** — no dead-letter queue. Failed tasks are logged but not retried. Add `autoretry_for` decorators for production reliability.

3. **SMTP password in plaintext .env** — for production, use a secrets manager or Docker secrets instead of `.env`.

4. **Single FAISS index per edge node** — reloaded in full every 60 s. For tenants with 10,000+ employees, consider incremental updates or a persistent FAISS index file.

5. **WebSocket creates a new Redis connection per client** — acceptable for small deployments. For high concurrency, share a single pub/sub connection via `app.state`.

6. **Anti-spoof limited to print and replay attacks** — the MiniFASNet model (CelebA-Spoof) detects print and screen replay well but 3D silicone mask attacks may pass. For very high-security deployments, integrate a depth sensor or a more comprehensive liveness model.

7. **FSRCNN SR requires opencv-contrib-python** — plain `opencv-python` does not include `dnn_superres`. If only `opencv-python` is installed, SR silently falls back to Lanczos bicubic. Both `frame_processor.py` and `edge_standalone.py` handle this gracefully.

8. **Snapshot purge runs on celery_worker** — worker must have the `/app/snapshots` volume mounted (already configured in `docker-compose.yml`). On multi-host deployments, handle snapshot cleanup externally.
