#!/usr/bin/env python3
"""
Generate the Smart AI Attendance System -- Developer Guide PDF.
Covers every source file A-Z with logic, data flow, and changes.
Run:  pip install fpdf2 && python generate_developer_guide_pdf.py
Output: docs/developer_guide.pdf
"""

import os
from fpdf import FPDF

os.makedirs("docs", exist_ok=True)

BRAND  = (29, 158, 117)
DARK   = (20, 20, 20)
GRAY   = (90, 90, 90)
LGRAY  = (190, 190, 190)
WHITE  = (255, 255, 255)
BLUE   = (41, 128, 185)
PURPLE = (142, 68, 173)
RED    = (192, 57, 43)
AMBER  = (230, 126, 34)
HDR    = (33, 47, 61)
CODE_BG = (245, 245, 245)


class DevGuide(FPDF):
    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font("Courier", "I", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 7, "Smart AI Attendance -- Developer Guide", align="C")
        self.set_draw_color(*LGRAY)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.ln(5)
        self.set_text_color(*DARK)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")

    def cover(self):
        self.set_fill_color(*HDR)
        self.rect(0, 0, self.w, self.h, "F")
        self.set_y(50)
        self.set_font("Courier", "B", 32)
        self.set_text_color(*BRAND)
        self.cell(0, 14, "Smart AI Attendance", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Courier", "", 20)
        self.set_text_color(*WHITE)
        self.cell(0, 10, "Developer Guide", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(*LGRAY)
        self.cell(0, 7, "A-Z file reference with architecture, logic, and changes", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, "Version 1.1  |  2026", align="C")

    def chapter(self, num, title, color=None):
        self.add_page()
        c = color or BRAND
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*c)
        self.cell(0, 11, f"{num}. {title}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*c)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_line_width(0.2)
        self.ln(5)
        self.set_text_color(*DARK)

    def section(self, title, color=None):
        self._reset_x()
        c = color or BLUE
        self.ln(4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*c)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*DARK)

    def file_header(self, path, description):
        self.ln(3)
        self.set_fill_color(*HDR)
        self.set_text_color(*WHITE)
        self.set_font("Courier", "B", 9)
        self.cell(0, 7, f"  {path}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(*CODE_BG)
        self.set_text_color(*GRAY)
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 6, f"  {description}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*DARK)
        self.ln(2)

    def _reset_x(self):
        self.set_x(self.l_margin)

    def body(self, text):
        self._reset_x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text, indent=5):
        self._reset_x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.multi_cell(0, 5.5, "   - " + text)

    def code(self, text):
        self.set_fill_color(*CODE_BG)
        self.set_draw_color(*LGRAY)
        self.set_font("Courier", "", 8)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5, text, fill=True, border=1)
        self.set_text_color(*DARK)
        self.ln(2)

    def note(self, text, c=None):
        self._reset_x()
        color = c or BLUE
        self.set_fill_color(240, 248, 255)
        self.set_text_color(*color)
        self.set_font("Helvetica", "I", 9)
        self.multi_cell(0, 5, text, border="L", fill=True)
        self.set_text_color(*DARK)
        self._reset_x()
        self.ln(2)

    def table_header(self, cols):
        self.set_fill_color(*HDR)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 9)
        for label, width in cols:
            self.cell(width, 7, label, border=1, fill=True)
        self.ln()
        self.set_text_color(*DARK)

    def table_row(self, cells, widths, shade=False):
        if shade:
            self.set_fill_color(*CODE_BG)
        self.set_font("Helvetica", "", 8.5)
        for text, w in zip(cells, widths):
            self.cell(w, 6, str(text), border=1, fill=shade)
        self.ln()

    def change_tag(self, text, kind="fix"):
        colors = {"fix": RED, "new": BRAND, "change": AMBER, "security": PURPLE}
        c = colors.get(kind, GRAY)
        self.set_fill_color(*c)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 7)
        label = {"fix": "BUG FIX", "new": "NEW", "change": "CHANGE", "security": "SECURITY"}.get(kind, kind.upper())
        self.cell(16, 5, label, fill=True, align="C")
        self.set_fill_color(*CODE_BG)
        self.set_text_color(*DARK)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "  " + text, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)


# ─────────────────────────────────────────────────────────────────────────────
pdf = DevGuide()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(18, 20, 18)

pdf.add_page()
pdf.cover()

# ── Chapter 1: Architecture Overview ─────────────────────────────────────────
pdf.chapter(1, "Architecture Overview")

pdf.body(
    "The system has four layers: Edge Node (camera AI), Backend API (FastAPI), "
    "Frontend Dashboard (Next.js 15), and Infrastructure (Postgres, Redis, Nginx, Celery)."
)

pdf.section("Data flow")
pdf.code(
    "Camera (RTSP/IP)\n"
    "  -> Edge Node: YOLO detect -> ByteTrack -> face crop -> anti-spoof -> ArcFace embed -> FAISS match\n"
    "  -> POST /api/v1/attendance/event  [EDGE_TOKEN auth]\n"
    "  -> Backend: confidence gate -> cooldown check (Redis) -> shift calc -> Postgres write\n"
    "     -> fire alerts if needed -> Redis pub/sub publish\n"
    "  -> WebSocket server -> Next.js client (real-time feed)"
)

pdf.section("Technology stack")
cols = [("Layer", 35), ("Technology", 55), ("Why", 100)]
pdf.table_header(cols)
stack = [
    ("Edge AI", "YOLOv11 + ByteTrack", "Fast multi-object detection + persistent track IDs"),
    ("Face AI", "InsightFace ArcFace R100", "512-d embeddings, best accuracy/speed tradeoff"),
    ("Vector search", "FAISS (edge) + pgvector (DB)", "Sub-ms local search, persistent storage in Postgres"),
    ("Backend", "FastAPI + asyncpg", "Async I/O for Redis, DB, and Slack without blocking"),
    ("DB", "PostgreSQL 16 + pgvector", "ACID + native vector extension"),
    ("Cache/broker", "Redis 7", "Cooldown TTLs, pub/sub, Celery broker"),
    ("Frontend", "Next.js 15 App Router", "SSR/SSG, TypeScript, Tailwind dark mode"),
    ("Auth", "JWT HS256 + bcrypt", "Stateless, no DB lookup on each request"),
    ("GPU", "ORT auto-detect", "NVIDIA/AMD/Intel/CPU selected at runtime"),
]
for i, r in enumerate(stack):
    pdf.table_row(r, [35, 55, 100], shade=(i % 2 == 0))

pdf.section("Multi-tenancy")
pdf.body(
    "Every DB table has a tenant_id FK. The JWT payload carries tenant_id. "
    "Every query filters by user.tenant_id from the JWT payload -- no cross-tenant data leakage is possible "
    "without a compromised JWT secret."
)

# ── Chapter 2: Backend Files ──────────────────────────────────────────────────
pdf.chapter(2, "Backend Files", BLUE)

# config.py
pdf.file_header("backend/app/config.py", "Application settings loaded from .env via pydantic-settings")
pdf.body(
    "Uses pydantic-settings BaseSettings. All settings are read from environment variables (or .env file). "
    "The validate_production_secrets() method is called at startup and raises RuntimeError if "
    "SECRET_KEY, FACE_ENCRYPTION_KEY, or EDGE_TOKEN are still set to their insecure defaults "
    "when ENVIRONMENT=production."
)
pdf.change_tag("Added EDGE_TOKEN field + validate_production_secrets() startup guard", "security")
pdf.bullet("SECRET_KEY: signs JWT tokens (HS256). Must be 64+ random hex chars in production.")
pdf.bullet("FACE_ENCRYPTION_KEY: Fernet key for face embeddings at rest.")
pdf.bullet("EDGE_TOKEN: shared secret authenticating edge-node event POSTs.")
pdf.bullet("CONFIDENCE_THRESHOLD: minimum face match cosine similarity (0.75 dev, 0.82 prod).")

# main.py
pdf.file_header("backend/app/main.py", "FastAPI application factory: middleware, lifespan, route registration")
pdf.body(
    "Creates the FastAPI app, registers all middleware, mounts all routers, and manages "
    "the Redis connection lifecycle via @asynccontextmanager lifespan."
)
pdf.change_tag("Swagger/Redoc disabled in ENVIRONMENT=production", "security")
pdf.change_tag("Rate limit lowered from 1000 to 200 rpm; login/refresh capped at 30 rpm", "security")
pdf.change_tag("Added shifts.router and admin.router", "new")
pdf.bullet("TenantMiddleware: reads X-Tenant-ID header into request.state.tenant_id.")
pdf.bullet("RateLimitMiddleware: per-IP sliding window, separate tighter limit for auth paths.")
pdf.bullet("CORSMiddleware: origins from settings.ALLOWED_ORIGINS.")

# dependencies.py
pdf.file_header("backend/app/dependencies.py", "FastAPI dependency injectors used across all routes")
pdf.body("Contains: get_db (yields AsyncSession), get_redis (lazy reconnect), get_current_user (validates JWT), role_required (RBAC gate), verify_edge_token (HMAC edge auth).")
pdf.change_tag("Removed duplicate get_current_user + role_required definitions", "fix")
pdf.change_tag("Added verify_edge_token using secrets.compare_digest (timing-safe)", "security")
pdf.code(
    "async def verify_edge_token(authorization: Header) -> None:\n"
    "    if not settings.EDGE_TOKEN: return  # dev: skip check\n"
    "    if not secrets.compare_digest(token_str, settings.EDGE_TOKEN):\n"
    "        raise HTTP 401"
)

# core/security.py
pdf.file_header("backend/app/core/security.py", "JWT creation/decoding, password hashing, role hierarchy")
pdf.body(
    "ROLE_HIERARCHY maps role names to integers (super_admin=6 .. viewer=1). "
    "require_role(user_role, minimum) returns True if user_role level >= minimum level. "
    "create_access_token embeds sub, tenant_id, role, exp, iat into the JWT payload."
)
pdf.bullet("hash_password / verify_password: bcrypt via passlib CryptContext.")
pdf.bullet("decode_token: jose jwt.decode with HS256 -- validates signature and expiry without DB call.")

# core/middleware.py
pdf.file_header("backend/app/core/middleware.py", "Tenant context injection and rate limiting")
pdf.change_tag("Auth paths capped at 30 rpm (was 10, which was too low for normal use)", "change")
pdf.change_tag("_cleanup() added to purge stale IP buckets every 5 minutes (memory leak fix)", "fix")
pdf.body(
    "RateLimitMiddleware stores timestamps per IP in a dict. "
    "The window is 60 seconds (sliding). The cleanup method removes IP entries idle > 60 s every 5 minutes."
)

# models
pdf.section("Models (backend/app/models/)")
pdf.body("SQLAlchemy 2.0 ORM with Mapped[] type annotations. Every model inherits UUIDMixin (auto UUID PK) and TimestampMixin (created_at).")

pdf.file_header("backend/app/models/shift.py", "Shift and EmployeeShift -- core of late/early/OT logic")
pdf.body("Shift stores: name, start_time, end_time, grace_in_min (late threshold), early_out_min (early leave threshold), work_days (int array). EmployeeShift is a composite-PK join table with effective_from/to dates.")
pdf.change_tag("New model (shifts feature)", "new")

pdf.file_header("backend/app/models/alert_config.py", "Per-tenant configurable thresholds")
pdf.change_tag("confidence_threshold and liveness_threshold changed from Mapped[float] to Mapped[int] -- stored as 0-100 integer, divided by 100 in API response", "fix")

pdf.file_header("backend/app/models/user.py", "User accounts and audit logs")
pdf.body("User has: tenant_id, email (unique), hashed_password, full_name, role, is_active, last_login_at. AuditLog records every action with ip_address (INET type), user_agent, old_values, new_values (JSON).")

# services
pdf.section("Services (backend/app/services/)")

pdf.file_header("backend/app/services/attendance_service.py", "Main business logic for event processing")
pdf.body(
    "process_recognition_event() is the core function. It runs in this order:\n"
    "1. Liveness gate: spoof detected? Fire alert, skip.\n"
    "2. Restricted camera check: fire alert if is_restricted=True.\n"
    "3. Confidence gate: below threshold? Handle as unknown person.\n"
    "4. Employee lookup + active check.\n"
    "5. Cooldown check (Redis key: cooldown:{emp_id}:{cam_id}, TTL=COOLDOWN_MINUTES).\n"
    "6. Blacklist + VIP alert firing.\n"
    "7. Shift lookup for the employee today.\n"
    "8. After-hours check (compares now_local vs shift window).\n"
    "9. Loitering check (Redis dwell timer).\n"
    "10. Get or create AttendanceLog for today.\n"
    "11. Determine action: check_in, check_out (exit camera), or skip_duplicate.\n"
    "12. Calculate late_by_min (check-in after start+grace) or early_by_min (check-out before end-buffer).\n"
    "13. Commit to DB, set cooldown key, publish to Redis pub/sub."
)
pdf.change_tag("Removed dead import pytz as _tz", "fix")
pdf.change_tag("clear_loitering made async (was sync calling asyncio.create_task)", "fix")
pdf.change_tag("UUID parsing in _handle_unknown wrapped in try/except", "fix")

pdf.file_header("backend/app/services/alert_service.py", "Alert firing and loitering dwell tracking")
pdf.body(
    "fire() creates an Alert DB record, publishes to Redis, and sends Slack for VIP/blacklist. "
    "check_loitering() stores a Redis key with first-seen timestamp; fires when elapsed >= LOITERING_THRESHOLD_MIN. "
    "clear_loitering() is called on check-out to reset the dwell timer."
)

# api routes
pdf.section("API Routes (backend/app/api/v1/)")

pdf.file_header("backend/app/api/v1/auth.py", "Login, token refresh, password change")
pdf.change_tag("New: POST /change-password -- verifies current password before accepting new", "new")
pdf.body("change_password() loads the User by JWT sub, verifies current_password with bcrypt, hashes new_password, saves.")

pdf.file_header("backend/app/api/v1/enrollment.py", "Face embedding enrollment and export")
pdf.change_tag("CRITICAL BUG FIX: /match and /export moved before /{employee_id} -- FastAPI was matching 'match' as an employee UUID, making those endpoints unreachable", "fix")

pdf.file_header("backend/app/api/v1/shifts.py", "Shift CRUD + employee assignment -- NEW file")
pdf.change_tag("New file -- all shift management endpoints", "new")
pdf.body("GET /shifts, POST /shifts, PATCH /shifts/{id}, DELETE /shifts/{id}. GET /assignments, POST /assignments (closes previous open assignment first), DELETE /assignments/{emp_id}.")

pdf.file_header("backend/app/api/v1/admin.py", "User management -- NEW file")
pdf.change_tag("New file -- user CRUD for admin role", "new")
pdf.body("GET/POST/PATCH/DELETE /admin/users. Cannot change own role. Checks tenant_id on every user lookup.")

pdf.file_header("backend/app/api/v1/alerts.py", "Alert listing, acknowledgement, config")
pdf.change_tag("Missing Unauthorized import added", "fix")
pdf.change_tag("GET /config changed to require admin role (was accessible to all)", "security")
pdf.change_tag("POST /config/password: moved password from query param to request body; requires old password; requires admin role", "security")
pdf.change_tag("ChangePasswordIn renamed to AdminConfigPasswordIn to avoid collision with auth.py", "fix")

pdf.file_header("backend/app/api/v1/attendance.py", "Event ingestion and log management")
pdf.change_tag("POST /event now requires EDGE_TOKEN (verify_edge_token dependency)", "security")
pdf.change_tag("PATCH/DELETE /logs/{id} changed from get_current_user to role_required('hr')", "security")
pdf.change_tag("DELETE /logs (bulk reset) changed to role_required('admin')", "security")

pdf.file_header("backend/app/api/v1/analytics.py", "Occupancy, hourly, shift compliance, visitors")
pdf.change_tag("Removed dead imports RecognitionEvent, Camera", "fix")

pdf.file_header("backend/app/api/v1/rbac.py", "Audit log endpoints")
pdf.change_tag("All audit endpoints changed from get_current_user to role_required('admin') -- audit logs contain IP addresses and action history", "security")
pdf.change_tag("GET /audit/actions endpoint now requires admin auth (was unauthenticated)", "security")

# schemas
pdf.section("Schemas (backend/app/schemas/)")

pdf.file_header("backend/app/schemas/attendance.py", "Pydantic request/response models for attendance")
pdf.change_tag("Added early_by_min: int = 0 to AttendanceLogOut -- model had field, schema didn't", "fix")

pdf.file_header("backend/app/schemas/alert_config.py", "Alert configuration schemas")
pdf.change_tag("Renamed ChangePasswordIn to AdminConfigPasswordIn to avoid collision with auth.py ChangePasswordIn", "fix")

pdf.file_header("backend/app/schemas/auth.py", "Auth request/response schemas")
pdf.change_tag("Added ChangePasswordIn (current_password, new_password) for the change-password endpoint", "new")

# ── Chapter 3: Frontend Files ─────────────────────────────────────────────────
pdf.chapter(3, "Frontend Files", PURPLE)

pdf.file_header("frontend/src/lib/rbac.ts", "Role hierarchy + React hook for client-side RBAC -- NEW file")
pdf.change_tag("New file", "new")
pdf.body(
    "LEVELS dict mirrors backend ROLE_HIERARCHY exactly. "
    "hasRole(minimum) is a pure function -- reads localStorage synchronously. "
    "useRole() is a React hook that initialises to 'viewer' (safe for SSR) then sets the real role "
    "in useEffect after mount. This fixes the hydration bug where hasRole() called during SSR always "
    "returned false (window undefined), causing role-gated buttons to never render."
)
pdf.code(
    "export function useRole() {\n"
    "  const [role, setRole] = useState('viewer');\n"
    "  useEffect(() => { setRole(getRole()); }, []);\n"
    "  const can = (min) => (LEVELS[role] ?? 0) >= (LEVELS[min] ?? 99);\n"
    "  return { role, can };\n"
    "}"
)

pdf.file_header("frontend/src/lib/api.ts", "All API calls with auto-refresh on 401")
pdf.body(
    "request() fetches the API, intercepts 401, tries tryRefresh() once, redirects to login if refresh fails. "
    "requestBlob() is the same for file downloads. "
    "All API methods are typed with TypeScript generics."
)
pdf.change_tag("Added changePassword, shift management methods, adminUsers CRUD", "new")

pdf.file_header("frontend/src/types/index.ts", "TypeScript interfaces matching backend response shapes")
pdf.change_tag("Removed start_time and end_time from Camera interface -- backend never returns these fields", "fix")

pdf.file_header("frontend/src/components/ui/DashboardShell.tsx", "Sidebar layout shared by all dashboard pages")
pdf.change_tag("Added useRole() hook -- role badge, Admin nav link (visible to admin+ after hydration)", "new")
pdf.change_tag("Added ChangePasswordModal with current/new/confirm fields, show/hide toggle, bcrypt verified server-side", "new")
pdf.change_tag("ThemeToggle moved into sidebar footer", "change")
pdf.change_tag("Active route highlight using usePathname()", "new")
pdf.change_tag("Full dark mode classes throughout", "fix")

pdf.file_header("frontend/src/components/live/CameraFeed.tsx", "Shared MJPEG camera stream component -- NEW file")
pdf.change_tag("New file -- extracted from cameras/page.tsx for reuse on overview dashboard", "new")
pdf.body("Shows MJPEG stream with retry-on-failure (5 s). streamOnly prop renders just the video area without card wrapper, used inside cameras/page.tsx cards.")

pdf.file_header("frontend/tailwind.config.js", "Tailwind configuration")
pdf.change_tag("CRITICAL: Added darkMode: 'class' -- without this, NO dark: variants were generated at all", "fix")

pdf.file_header("frontend/src/app/layout.tsx", "Root Next.js layout")
pdf.change_tag("Removed className='light' from <body> -- was overriding ThemeContext's dark class on <html>", "fix")

pdf.file_header("frontend/src/app/globals.css", "Global CSS")
pdf.change_tag("Added .dark body { background: #111827; color: #f9fafb; } for dark mode body", "fix")

pdf.file_header("frontend/src/app/dashboard/page.tsx", "Overview / home page")
pdf.change_tag("Added Live Cameras section -- loads api.cameras() and shows CameraFeed grid", "new")
pdf.change_tag("Replaced hasRole() with useRole() hook to fix SSR hydration issue", "fix")

pdf.file_header("frontend/src/app/dashboard/shifts/page.tsx", "Shift management page -- NEW file")
pdf.change_tag("New file -- create/edit shifts with live threshold preview; assign employees", "new")
pdf.body("The modal shows a live summary: 'Late after HH:MM' and 'Early leave before HH:MM' calculated from form values in real time.")

pdf.file_header("frontend/src/app/dashboard/admin/page.tsx", "User management page -- NEW file")
pdf.change_tag("New file -- user list with role badges, edit-role modal, add-user modal", "new")

pdf.file_header("frontend/src/app/dashboard/employees/page.tsx", "Employee management")
pdf.change_tag("Bangladesh-friendly autocomplete via <datalist> for Department (17 options) and Designation (50 options)", "new")
pdf.change_tag("Phone placeholder changed to +880 1XXX-XXXXXX format", "change")
pdf.change_tag("Role guards: Add/Edit/Enroll/Deactivate require hr+; Blacklist/VIP require admin+", "security")

pdf.file_header("frontend/src/app/dashboard/cameras/page.tsx", "Camera management")
pdf.change_tag("Removed start_time/end_time fields from form -- backend Camera model never had these columns", "fix")
pdf.change_tag("Role guards: Add/Edit/Delete require admin+", "security")
pdf.change_tag("Empty state when no cameras registered, showing contextual message per role", "new")

pdf.file_header("frontend/src/app/login/page.tsx", "Login page")
pdf.change_tag("Removed hardcoded default credentials (admin@demo.com / admin123)", "security")
pdf.change_tag("Error message now distinguishes 429 rate-limit from 401 wrong credentials from network error", "fix")

pdf.file_header("frontend/src/components/EmployeeEnrollment.tsx", "DELETED -- was never imported anywhere")
pdf.change_tag("Deleted -- dead code, completely unused component", "fix")

# ── Chapter 4: Edge Node Files ────────────────────────────────────────────────
pdf.chapter(4, "Edge Node Files", AMBER)

pdf.file_header("edge/src/utils/gpu.py", "Runtime GPU auto-detection -- NEW file")
pdf.change_tag("New file -- single source of truth for ORT providers and PyTorch device", "new")
pdf.body(
    "detect() is called once at startup and cached. It queries onnxruntime.get_available_providers() "
    "and returns a dict with device_type, ort_providers list, torch_device string, and insightface_ctx int."
)
pdf.body("Priority: CUDAExecutionProvider -> ROCMExecutionProvider -> OpenVINOExecutionProvider -> DmlExecutionProvider -> torch.xpu -> CPUExecutionProvider.")
pdf.body("DEVICE env var overrides auto-detection ('cuda', 'rocm', 'openvino', 'cpu').")

pdf.file_header("edge/src/detection/yolo_detector.py", "YOLOv11 person detector + ByteTrack")
pdf.change_tag("device parameter now defaults to 'auto' -- reads torch_device from gpu.detect()", "change")
pdf.body("Uses ultralytics YOLO.track() which runs detection AND ByteTrack in one call. persist=True maintains track IDs across frames. PERSON_CLASS=0 filters to humans only.")

pdf.file_header("edge/src/recognition/arcface.py", "InsightFace ArcFace R100 face embedder")
pdf.change_tag("Now reads ort_providers and insightface_ctx from gpu.detect() instead of hardcoded ctx_id=0", "change")
pdf.body("detect_and_embed() returns list of (bbox, normed_embedding_512d, det_score). InsightFace's buffalo_l model includes SCRFD face detector + ArcFace embedder in one package.")

pdf.file_header("edge/src/recognition/anti_spoof.py", "ONNX liveness / anti-spoof model")
pdf.change_tag("Hardcoded ['CUDAExecutionProvider', 'CPUExecutionProvider'] replaced with gpu.detect()['ort_providers']", "fix")
pdf.body("Loads an ONNX model from model_path. check() returns (is_live: bool, score: float). If no model file found, returns 1.0 (pass-through). _infer() resizes face to 80x80, runs ONNX session, returns P(live) from softmax output.")

pdf.file_header("edge/src/recognition/faiss_search.py", "FAISS nearest-neighbour face search")
pdf.body("build() creates an IndexFlatIP (inner product = cosine similarity on L2-normalised vectors). search() returns (employee_id, similarity_score). Returns (None, 0) if index is empty or score < threshold.")

pdf.file_header("edge/src/pipeline/frame_processor.py", "Main per-frame AI pipeline")
pdf.change_tag("CRITICAL BUG FIX: duplicate 'snapshot_url' key in spoof_attempt event dict (second value silently overwrote first)", "fix")
pdf.change_tag("snap variable was referenced before assignment in spoof branch -- now assigned before event dict", "fix")
pdf.body("_INFERENCE_EXECUTOR is a module-level ThreadPoolExecutor(max_workers=1). This serialises all ONNX/FAISS calls across all cameras since the models are not thread-safe. process() offloads to the executor via run_in_executor() so the asyncio event loop (and MJPEG server) stays responsive.")
pdf.body("Per-track cooldown (_cooldown dict) prevents the same track from being processed multiple times. Per-track labels (_track_labels) make bounding box annotations persist between detections.")

pdf.file_header("edge/src/pipeline/event_publisher.py", "Posts events to backend with EDGE_TOKEN auth")
pdf.change_tag("Added EDGE_TOKEN header: reads os.getenv('EDGE_TOKEN') and sends as Authorization: Bearer", "security")
pdf.body("publish() first posts to Redis pub/sub (recognition:{tenant_id}), then HTTP POSTs to backend /attendance/event with the EDGE_TOKEN header. Redis publish is fire-and-forget; HTTP POST logs errors but does not block the pipeline.")

pdf.file_header("edge/src/main.py", "Edge node entrypoint")
pdf.change_tag("Calls log_gpu_info() at startup to log detected GPU type and ORT providers", "new")
pdf.change_tag("Passes device='auto' to all model constructors (was device=os.getenv('DEVICE', 'cuda'))", "change")
pdf.body("Loads config -> authenticates with backend -> loads cameras -> loads embeddings -> builds FAISS -> starts MJPEG server -> starts FrameProcessors per camera -> runs heartbeat + embedding-watch + camera-watch loops.")

# ── Chapter 5: Dockerfiles ────────────────────────────────────────────────────
pdf.chapter(5, "Dockerfiles", GRAY)

pdf.file_header("backend/Dockerfile", "Production backend -- pre-bakes InsightFace buffalo_l at build time")
pdf.body("Runs 'python -c from insightface...' during docker build to download the 500 MB model pack into the image layer. First build is slow; subsequent builds use the cached layer.")

pdf.file_header("backend/Dockerfile.dev", "Development backend -- skips model pre-download")
pdf.change_tag("New file -- faster dev build (models download on first enrollment request)", "new")

pdf.file_header("edge/Dockerfile.edge.nvidia", "NVIDIA CUDA edge (renamed from Dockerfile.edge)")
pdf.body("Base: nvcr.io/nvidia/pytorch. Installs onnxruntime-gpu. Pre-downloads InsightFace and YOLO11s. Force-reinstalls numpy<2.0 to fix ABI conflict with NVIDIA's bundled OpenCV.")

pdf.file_header("edge/Dockerfile.edge.amd", "AMD ROCm edge -- NEW file")
pdf.change_tag("New file", "new")
pdf.body("Base: rocm/pytorch:rocm6.2.4. Removes onnxruntime-gpu, installs onnxruntime-rocm from AMD's extra-index. Pre-downloads models using ROCMExecutionProvider.")

pdf.file_header("edge/Dockerfile.edge.intel", "Intel OpenVINO edge -- NEW file")
pdf.change_tag("New file", "new")
pdf.body("Base: ubuntu:22.04 with python3.11. Installs openvino and onnxruntime-openvino. Models pre-downloaded with OpenVINOExecutionProvider.")

pdf.file_header("edge/Dockerfile.edge.cpu", "CPU-only edge (existing, unchanged)")
pdf.body("Base: python:3.11-slim. Swaps onnxruntime-gpu for onnxruntime via sed on requirements.txt. Suitable for any machine.")

# ── Chapter 6: Infrastructure Files ──────────────────────────────────────────
pdf.chapter(6, "Infrastructure Files", HDR)

pdf.file_header("infra/nginx/nginx.conf", "Nginx reverse proxy configuration")
pdf.change_tag("CRITICAL FIX: Added resolver 127.0.0.11 (Docker DNS) + set $upstream variables. Previously nginx crashed on startup if edge_node was not running because upstream block did DNS resolution at parse time.", "fix")
pdf.body("All upstream hostnames are now in set $var variables, resolved at request time by Docker's DNS server (127.0.0.11). /stream/ returns 502 gracefully when edge_node is offline.")

pdf.file_header("docker-compose.dev.yml", "Development compose -- NEW file")
pdf.change_tag("New file -- no NVIDIA GPU requirement, fast backend Dockerfile, nginx on port 80, edge_node optional via --profile edge", "new")

pdf.file_header("docker-compose.prod.yml", "Production compose")
pdf.change_tag("Backend command overridden to --workers 2 for production throughput", "change")
pdf.change_tag("NEXT_PUBLIC_* passed as build args to bake server URL into frontend", "change")
pdf.change_tag("Edge node uses CPU Dockerfile by default; GPU via overlay files", "change")

pdf.file_header("docker-compose.prod.gpu.yml", "NVIDIA GPU overlay")
pdf.body("Overrides edge_node to use Dockerfile.edge.nvidia, DEVICE=cuda, and adds nvidia deploy.resources.reservations.devices.")

pdf.file_header("docker-compose.prod.amd.yml", "AMD ROCm overlay -- NEW file")
pdf.change_tag("New file", "new")
pdf.body("Mounts /dev/kfd and /dev/dri, adds user to render+video groups. Uses Dockerfile.edge.amd with DEVICE=rocm.")

pdf.file_header("docker-compose.prod.intel.yml", "Intel GPU overlay -- NEW file")
pdf.change_tag("New file", "new")
pdf.body("Mounts /dev/dri, adds user to render+video groups. Uses Dockerfile.edge.intel with DEVICE=openvino.")

pdf.file_header("deploy.sh", "Linux/Mac production one-click deploy")
pdf.change_tag("Full GPU detection: NVIDIA (nvidia-smi + nvidia-container-toolkit check), AMD (/dev/kfd + rocm-smi), Intel (lspci + /dev/dri)", "new")
pdf.change_tag("Secret auto-generation: openssl rand-hex for keys, python3 base64.urlsafe_b64encode for Fernet key", "new")
pdf.change_tag("--update flag preserves .env but updates server URL", "new")
pdf.change_tag("--gpu flag forces specific GPU type", "new")

pdf.file_header("deploy.bat", "Windows Server production one-click deploy")
pdf.change_tag("PowerShell-based secret generation using RandomNumberGenerator", "new")
pdf.change_tag("GPU detection via WMI Win32_VideoController for AMD/Intel; nvidia-smi for NVIDIA", "new")

# ── Chapter 7: Security Architecture ─────────────────────────────────────────
pdf.chapter(7, "Security Architecture", RED)

pdf.section("Complete threat model")
cols = [("Threat", 65), ("Mitigation", 125)]
pdf.table_header(cols)
threats = [
    ("Forged JWT token", "SECRET_KEY=random 64-char hex; startup refuses default in prod"),
    ("Brute-force login", "30 req/min/IP rate limit on /auth/login"),
    ("Fake check-in events", "EDGE_TOKEN Bearer auth on /attendance/event"),
    ("API enumeration", "Swagger disabled in production"),
    ("Privilege escalation", "JWT role claim validated against DB-backed role on every request"),
    ("Cross-tenant access", "Every query filters by tenant_id from JWT payload"),
    ("Spoof attack (photo)", "ONNX liveness model; score < 0.80 blocks recognition"),
    ("Face data exposure", "Embeddings encrypted at rest with Fernet key"),
    ("Password brute-force", "bcrypt with 12 rounds; rate limiting on login endpoint"),
    ("Config data leak", "GET /alerts/config requires admin role"),
    ("Audit bypass", "All user actions logged with IP + user agent to audit_logs table"),
    ("Token replay", "JWT expires in ACCESS_TOKEN_EXPIRE_HOURS (default 8 h)"),
]
for i, r in enumerate(threats):
    pdf.table_row(r, [65, 125], shade=(i % 2 == 0))

pdf.section("RBAC enforcement points")
pdf.body("Two independent enforcement points:")
pdf.bullet("Backend: every endpoint has a Depends(role_required('hr')) or similar -- 403 Forbidden if insufficient role")
pdf.bullet("Frontend: useRole() hook + can() function hide buttons and pages after hydration -- defence in depth, not a substitute for backend checks")

# ── Chapter 8: Database Schema ────────────────────────────────────────────────
pdf.chapter(8, "Database Schema")

pdf.body("All tables have a UUID primary key generated by the uuid-ossp extension. pgvector extension installed via init.sql.")

tables = [
    ("tenants", "id, name, slug, plan, max_employees, max_cameras, is_active, settings(JSON)"),
    ("branches", "id, tenant_id, name, code, timezone, geo_lat, geo_lng, is_active"),
    ("shifts", "id, tenant_id, branch_id, name, start_time, end_time, grace_in_min, early_out_min, work_days(INT[])"),
    ("employee_shifts", "employee_id, shift_id, effective_from, effective_to (composite PK)"),
    ("employees", "id, tenant_id, branch_id, full_name, employee_code, email, phone, department, is_enrolled, is_blacklisted, is_vip, extra(JSON)"),
    ("face_embeddings", "id, employee_id, tenant_id, embedding(VECTOR(512)), quality_score, photo_angle"),
    ("cameras", "id, tenant_id, name, rtsp_url, direction, camera_role, camera_zone, is_restricted, fps_target, status"),
    ("attendance_logs", "id, tenant_id, employee_id, shift_id, attendance_date, check_in_at, check_out_at, status, is_late, late_by_min, is_early_leave, early_by_min, working_hours, overtime_seconds"),
    ("recognition_events", "id, tenant_id, camera_id, employee_id, confidence, is_live, spoof_score, raw_event(JSON)"),
    ("alerts", "id, tenant_id, alert_type, severity, employee_id, camera_id, is_acknowledged, acknowledged_by"),
    ("alert_configs", "id, tenant_id, confidence_threshold, liveness_threshold, cooldown_minutes, loitering_threshold_min, admin_password_hash"),
    ("users", "id, tenant_id, email, hashed_password, full_name, role, is_active, last_login_at"),
    ("audit_logs", "id, tenant_id, user_id, action, resource_type, resource_id, old_values(JSON), new_values(JSON), ip_address(INET)"),
    ("unknown_detections", "id, tenant_id, camera_id, track_id, snapshot_url, confidence_best, detection_date"),
]
cols = [("Table", 50), ("Key columns", 140)]
pdf.table_header(cols)
for i, (t, c) in enumerate(tables):
    pdf.table_row([t, c], [50, 140], shade=(i % 2 == 0))

# ── Chapter 9: GPU Support Reference ─────────────────────────────────────────
pdf.chapter(9, "GPU Support Reference")

pdf.section("Detection order in gpu.py")
pdf.code(
    "DEVICE env var override  (cuda | rocm | openvino | cpu)\n"
    "  |\n"
    "onnxruntime.get_available_providers()\n"
    "  CUDAExecutionProvider     -> NVIDIA\n"
    "  ROCMExecutionProvider     -> AMD (Linux ROCm)\n"
    "  OpenVINOExecutionProvider -> Intel Arc / Iris / UHD\n"
    "  DmlExecutionProvider      -> DirectML (Windows, any DirectX 12 GPU)\n"
    "  |\n"
    "torch.xpu.is_available()    -> Intel IPEX XPU\n"
    "  |\n"
    "CPUExecutionProvider        -> CPU fallback"
)

pdf.section("Runtime graceful degradation")
pdf.body(
    "If a provider initialises but fails on first run() call, ONNX Runtime automatically "
    "falls through to the next provider in the list. For example, if CUDAExecutionProvider is "
    "listed but the GPU runs out of memory, the next inference call uses CPUExecutionProvider. "
    "No crash, no manual intervention needed."
)

pdf.section("Host requirements per GPU type")
cols = [("GPU", 30), ("Host requirement", 80), ("Docker mount", 80)]
pdf.table_header(cols)
reqs = [
    ("NVIDIA", "nvidia-driver + nvidia-container-toolkit", "--gpus all"),
    ("AMD", "ROCm drivers (Linux only)", "/dev/kfd + /dev/dri"),
    ("Intel", "i915 or xe kernel module (standard)", "/dev/dri"),
    ("CPU", "None", "None"),
]
for i, r in enumerate(reqs):
    pdf.table_row(r, [30, 80, 80], shade=(i % 2 == 0))

# ── Chapter 10: Extension Guide ───────────────────────────────────────────────
pdf.chapter(10, "Extension Guide")

pdf.section("Adding a new API endpoint")
pdf.bullet("1. Add route function to appropriate backend/app/api/v1/*.py")
pdf.bullet("2. Add role check: Depends(role_required('hr'))")
pdf.bullet("3. Add Pydantic schema to backend/app/schemas/ if needed")
pdf.bullet("4. Register new router file in main.py if creating a new file")
pdf.bullet("5. Add TypeScript API method to frontend/src/lib/api.ts")
pdf.bullet("6. Use from page component with useRole() for conditional UI")

pdf.section("Adding a new dashboard page")
pdf.bullet("1. Create frontend/src/app/dashboard/<name>/page.tsx")
pdf.bullet("2. Import DashboardShell and useRole()")
pdf.bullet("3. Add nav entry to NAV array in DashboardShell.tsx")
pdf.bullet("4. If admin-only: add to the conditional Admin link block (not NAV array)")

pdf.section("Adding a new alert type")
pdf.bullet("1. Add to SEVERITY dict in alert_service.py")
pdf.bullet("2. Call alerts.fire(tenant_id, 'new_type', message) from attendance_service.py")
pdf.bullet("3. Add to TYPE_LABEL in alerts/page.tsx and security-alerts/page.tsx")
pdf.bullet("4. Add to available actions list in rbac.py for audit filtering")

pdf.section("Supporting a new GPU")
pdf.bullet("1. Create edge/Dockerfile.edge.<name> with GPU-specific base image")
pdf.bullet("2. Add detection logic in edge/src/utils/gpu.py detect() function")
pdf.bullet("3. Create docker-compose.prod.<name>.yml with required device mounts")
pdf.bullet("4. Add GPU detection to deploy.sh and set GPU_OVERRIDE variable")
pdf.bullet("5. Add make deploy-<name> target to Makefile")

# Save
out = "docs/developer_guide.pdf"
pdf.output(out)
print(f"Developer guide saved: {out}  ({os.path.getsize(out) // 1024} KB)")
