# Developer Notes — Smart AI Attendance System

Architecture decisions, bug-fix log, and extension guide for contributors.

---

## Architecture Decisions

### Why FastAPI + async SQLAlchemy?
The backend is I/O heavy: each recognition event hits the DB, Redis (cooldown check, pub/sub), and potentially Slack. Async FastAPI + asyncpg keeps all of this non-blocking on a single worker. Celery handles anything that can be deferred (marking absentees, retention cleanup).

### Why pgvector instead of a dedicated vector DB?
Face embeddings are 512-d floats. We store them in pgvector so joins with the `employees` table are free. The edge node uses FAISS locally for sub-millisecond nearest-neighbour search and syncs from Postgres every 60 s. This avoids a network round-trip on every frame while keeping the DB as source of truth.

### Why FAISS on the edge, not the backend?
Face matching must run at camera frame rate (5–10 fps per camera). A backend HTTP call per frame adds 10–50 ms round-trip latency. FAISS on the edge does the search in < 1 ms. The backend only receives confirmed match events.

### Why one ONNX Runtime session per model?
InsightFace's `FaceAnalysis.prepare()` loads the SCRFD detector and ArcFace recognition model into a single session. Sharing this across all cameras in a single process (via the shared `ArcFaceRecognizer` instance) avoids loading 500 MB of weights multiple times. `_INFERENCE_EXECUTOR` in `frame_processor.py` serialises inference calls so the models are used from one thread at a time.

### Why a single inference thread?
ONNX Runtime CUDA sessions are not thread-safe across concurrent `run()` calls on the same session. Serialising via `ThreadPoolExecutor(max_workers=1)` eliminates races without per-camera model copies. CPU throughput is unaffected for typical deployments (1–4 cameras).

### Why Redis for cooldowns and pub/sub?
Cooldown keys (`cooldown:{emp}:{cam}`) expire automatically via Redis TTL — no cleanup job needed. Pub/sub pushes attendance events to the WebSocket layer without polling. Redis restart is safe: cooldowns reset (mildly permissive) and live-feed history restarts (cosmetic).

### JWT design
Tokens carry `sub` (user UUID), `tenant_id`, `role`, `exp`, `iat`. The backend never hits the DB to validate a token — everything needed for auth and RBAC is in the payload. Token refresh issues a new token from a still-valid one; expired tokens must re-login.

### Tenant isolation
Every DB table has a `tenant_id` FK. Every query filters by `user.tenant_id` from the JWT. A single API instance serves multiple tenants without data leakage.

---

## Key Files and Their Roles

```
backend/app/
  config.py           Settings (pydantic-settings), startup secret guard
  dependencies.py     FastAPI deps: get_db, get_current_user, role_required, verify_edge_token
  main.py             App factory: middleware, route registration, lifespan (Redis)
  core/security.py    hash_password, verify_password, create_access_token, decode_token, ROLE_HIERARCHY
  core/middleware.py  TenantMiddleware, RateLimitMiddleware (in-memory, per-IP)
  core/exceptions.py  NotFound, Unauthorized, Forbidden (HTTPException subclasses)
  models/shift.py     Shift, EmployeeShift — controls late/early/OT classification
  services/attendance_service.py   Main business logic: confidence gate, cooldown, shift calc, alerts
  services/alert_service.py        Fires alerts, tracks loitering via Redis dwell timers
  api/v1/shifts.py    Shift CRUD + employee assignment endpoints
  api/v1/admin.py     User management (list, create, change role, deactivate)
  api/v1/auth.py      Login, refresh, change-password

edge/src/
  utils/gpu.py        Runtime GPU detection — single source of truth for ORT providers + torch device
  detection/yolo_detector.py   YOLOv11 track() wrapper — reads device from gpu.py
  recognition/arcface.py       InsightFace wrapper — reads providers/ctx_id from gpu.py
  recognition/anti_spoof.py    ONNX liveness model — reads providers from gpu.py
  pipeline/frame_processor.py  Main per-frame pipeline: detect → crop → anti-spoof → embed → search → publish
  pipeline/event_publisher.py  Posts events to backend with EDGE_TOKEN Bearer header

frontend/src/
  lib/rbac.ts         hasRole(), useRole() hook — mirrors backend ROLE_HIERARCHY exactly
  lib/api.ts          All API calls with 401 auto-refresh + redirect
  components/ui/DashboardShell.tsx   Sidebar with role badge, change-password modal, theme toggle
  app/dashboard/shifts/page.tsx      Shift management page with live threshold preview
  app/dashboard/admin/page.tsx       User management page
```

---

## Bug Fix Log

| Bug | File | Fix |
|---|---|---|
| `select` not imported | `reports.py` | Added `from sqlalchemy import select` |
| Duplicate `get_current_user` + `role_required` | `dependencies.py` | Removed second definitions (lines 79–105) |
| `Unauthorized` not imported | `alerts.py` | Added `from ...core.exceptions import Unauthorized` |
| `Mapped[float]` on Integer column | `alert_config.py` | Changed to `Mapped[int]` |
| `clear_loitering` sync calling `asyncio.create_task` | `alert_service.py` | Made async, `await self.redis.delete(key)` |
| POST `/match` unreachable (shadowed by `/{employee_id}`) | `enrollment.py` | Moved `/match` and `/export` before `/{employee_id}` |
| `early_by_min` missing from `AttendanceLogOut` | `schemas/attendance.py` | Added field |
| `ChangePasswordIn` name collision between two schemas | `alert_config.py` | Renamed to `AdminConfigPasswordIn` |
| Dead imports `RecognitionEvent`, `Camera` | `analytics.py` | Removed |
| Dead `import pytz as _tz` | `attendance_service.py` | Removed |
| Duplicate `"snapshot_url": snap` key | `frame_processor.py` | Fixed + added missing `snap` assignment in spoof branch |
| `nginx.conf` fails on startup if edge_node not running | `nginx.conf` | Changed to `resolver 127.0.0.11` + variable `$upstream` |
| Dark mode not working | `tailwind.config.js` | Added `darkMode: "class"` |
| `<body className="light">` fighting ThemeContext | `layout.tsx` | Removed the class |
| `hasRole()` always returns false on initial render | All dashboard pages | Replaced with `useRole()` hook (useEffect reads localStorage after mount) |
| Route `/match` shadowed by `/{employee_id}` | `enrollment.py` | Reordered routes |
| WebSocket `from_url` creates new Redis connection per connect | `ws.py` | Confirmed: `redis.asyncio.from_url` is synchronous, no await needed |
| `Camera` type had `start_time`/`end_time` fields backend never returns | `types/index.ts` | Removed fields |
| Unused `EmployeeEnrollment.tsx` component | — | Deleted |

---

## Security Architecture

### Password hashing
```python
# backend/app/core/security.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hash_password(p)    # → bcrypt hash
verify_password(p, h)   # → bool
```
Both user account passwords and admin config passwords use this. SMTP passwords in `alert_configs` are stored plaintext — treat DB access as a secret.

### JWT flow
```
POST /auth/login → validate bcrypt → create_access_token(sub, tenant_id, role) → return
GET  /any        → get_current_user dependency → decode_token(jwt) → CurrentUser dataclass
```
`decode_token` validates signature + expiry without a DB call. `role_required(min)` then checks `ROLE_HIERARCHY[user.role] >= ROLE_HIERARCHY[min]`.

### Edge token
`verify_edge_token` dependency uses `secrets.compare_digest` (constant-time) to prevent timing attacks. In dev (`EDGE_TOKEN == ""`), the check is skipped entirely.

### Rate limiter
`RateLimitMiddleware` is in-process — one bucket dict per worker. Auth endpoints are capped at 30 req/min/IP (brute-force protection); others at 200 req/min/IP. The bucketed timestamp list is cleaned every 5 minutes to prevent memory growth.

---

## GPU Detection Flow

```
DEVICE env var set? → use it directly
Otherwise:
  onnxruntime available providers?
    CUDAExecutionProvider  → NVIDIA
    ROCMExecutionProvider  → AMD
    OpenVINOExecutionProvider → Intel
    DmlExecutionProvider   → DirectML (Windows)
  torch.xpu available?     → Intel IPEX
  fallback                 → CPU

Result cached in _CACHED (module-level singleton)
```

Each model class reads from `detect()` on construction. Adding support for a new hardware type means adding one `elif` in `gpu.py` — no changes to model classes.

---

## How to Add a New API Endpoint

1. Add the route function to the appropriate `backend/app/api/v1/*.py`
2. Add role check: `user: CurrentUser = Depends(role_required("hr"))`
3. Add the Pydantic schema to `backend/app/schemas/*.py` if needed
4. Register in `main.py` if a new router file
5. Add the TypeScript API method to `frontend/src/lib/api.ts`
6. Use it from the relevant page component

## How to Add a New Alert Type

1. Add to `SEVERITY` dict in `backend/app/services/alert_service.py`
2. Call `await self.alerts.fire(tenant_id, "new_type", message, ...)` from `attendance_service.py`
3. Add to `TYPE_LABEL` dict in `frontend/src/app/dashboard/alerts/page.tsx` and `security-alerts/page.tsx`
4. Add to the available audit actions list in `rbac.py`

## How to Add a New Dashboard Page

1. Create `frontend/src/app/dashboard/<name>/page.tsx`
2. Import and use `DashboardShell` and `useRole`
3. Add nav entry to `NAV` array in `DashboardShell.tsx`
4. If admin-only: use `{can("admin") && <button>...}` pattern

## How to Support a New GPU

1. Create `edge/Dockerfile.edge.<name>` with the GPU-specific base image and ONNX Runtime package
2. Add detection logic in `edge/src/utils/gpu.py` (`detect()` function)
3. Create `docker-compose.prod.<name>.yml` override with required device mounts
4. Add to `deploy.sh` GPU detection block and compose command logic
5. Add `make deploy-<name>` target to `Makefile`

---

## Development Workflow

```bash
# Start dev environment
make start          # or ./start.sh

# Watch backend logs
make logs

# Re-seed after DB wipe
make seed

# Run backend tests
cd backend && pytest

# Wipe everything and start fresh
make reset && make start
```

### Frontend hot-reload
The dev compose uses a built Next.js image — it does **not** hot-reload. For frontend development, run Next.js directly:
```bash
cd frontend && npm run dev
```
Point `NEXT_PUBLIC_API_URL=http://localhost:8000` and run backend via `make dev`.

---

## Known Limitations

1. **Rate limiter is in-process** — does not share state across multiple uvicorn workers. For multi-worker prod deployments, move to Redis-backed rate limiting (e.g., `slowapi` with Redis storage).

2. **Celery tasks are fire-and-forget** — no dead-letter queue. Failed tasks are logged but not retried automatically. Add `autoretry_for` decorators for production reliability.

3. **SMTP password stored in plaintext** — the `alert_configs.smtp_password` column is not encrypted. For production, use an environment variable or secrets manager instead.

4. **Single FAISS index per edge node** — reloaded in full every 60 s. For tenants with 10,000+ employees, consider incremental updates or a persistent FAISS index file.

5. **WebSocket creates a new Redis connection per connection** — acceptable for small deployments, but for high concurrency use a shared pub/sub connection from app.state.
