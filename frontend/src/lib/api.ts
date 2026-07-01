declare const process: { env: Record<string, string | undefined> };

// ── Shift types ───────────────────────────────────────────────────────────────
export interface ShiftRow {
  id: string; name: string;
  start_time: string; end_time: string;
  grace_in_min: number; early_out_min: number;
  work_days: number[]; work_days_label: string[];
  is_active: boolean;
}
export interface ShiftPayload {
  name: string; start_time: string; end_time: string;
  grace_in_min: number; early_out_min: number;
  work_days: number[];
}
export interface AssignmentRow {
  employee_id: string; employee_name: string; employee_code: string | null;
  shift_id: string; shift_name: string;
  shift_start: string; shift_end: string;
  effective_from: string; effective_to: string | null;
}
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost";

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function tryRefresh(): Promise<string | null> {
  const token = localStorage.getItem("token");
  if (!token) return null;
  try {
    const res = await fetch(`${API}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    localStorage.setItem("token", data.access_token);
    return data.access_token;
  } catch {
    return null;
  }
}

function redirectToLogin() {
  if (typeof window === "undefined") return;
  localStorage.clear();
  window.location.href = "/login";
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(opts.headers || {}),
    },
  });

  // ── 401 interception: try silent refresh once, then redirect ──
  if (res.status === 401) {
    const newToken = await tryRefresh();
    if (newToken) {
      const retry = await fetch(`${API}${path}`, {
        ...opts,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${newToken}`,
          ...(opts.headers || {}),
        },
      });
      if (retry.ok) return retry.json() as Promise<T>;
    }
    redirectToLogin();
    throw new Error("Session expired");
  }

  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function requestBlob(path: string): Promise<Blob> {
  const res = await fetch(`${API}${path}`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (res.status === 401) {
    const newToken = await tryRefresh();
    if (newToken) {
      const retry = await fetch(`${API}${path}`, {
        headers: { Authorization: `Bearer ${newToken}` },
        cache: "no-store",
      });
      if (retry.ok) return retry.blob();
    }
    redirectToLogin();
    throw new Error("Session expired");
  }
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.blob();
}

export const api = {
  // Auth
  login: (email: string, password: string) =>
    request<{ access_token: string; role: string; tenant_id: string }>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) }
    ),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ message: string }>(
      "/api/v1/auth/change-password",
      { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }
    ),

  // Attendance
  summary: (date?: string) =>
    request<import("@/types").AttendanceSummary>(
      `/api/v1/attendance/summary${date ? `?date=${date}` : ""}`
    ),
  logs: (params = "") =>
    request<import("@/types").AttendanceLog[]>(`/api/v1/attendance/logs?${params}`),
  updateLog: (id: string, payload: { attendance_date?: string; check_in_at?: string | null; check_out_at?: string | null; status?: string; notes?: string }) =>
    request<import("@/types").AttendanceLog>(`/api/v1/attendance/logs/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteLog: (id: string) =>
    request(`/api/v1/attendance/logs/${id}`, { method: "DELETE" }),
  resetLogs: (date: string) =>
    request(`/api/v1/attendance/logs?reset_date=${date}`, { method: "DELETE" }),
  liveFeed: () =>
    request<import("@/types").LiveEvent[]>("/api/v1/attendance/live"),
  visitors: () =>
    request<{ unknown_detections: number }>("/api/v1/analytics/visitors"),

  // Weekly attendance rate (last 7 days)
  weekly: async (): Promise<{ date: string; rate: number }[]> => {
    const today = new Date();
    const dates = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(today);
      d.setDate(d.getDate() - (6 - i));
      return d.toISOString().slice(0, 10);
    });
    return Promise.all(
      dates.map(date =>
        request<import("@/types").AttendanceSummary>(`/api/v1/attendance/summary?date=${date}`)
          .then(s => ({ date, rate: Math.round(s.attendance_rate) }))
          .catch(() => ({ date, rate: 0 }))
      )
    );
  },

  // Employees
  employees: () => request<import("@/types").Employee[]>("/api/v1/employees"),
  createEmployee: (payload: Partial<import("@/types").Employee>) =>
    request<import("@/types").Employee>("/api/v1/employees", { method: "POST", body: JSON.stringify(payload) }),
  updateEmployee: (id: string, payload: Partial<import("@/types").Employee>) =>
    request<import("@/types").Employee>(`/api/v1/employees/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  enrollFace: async (id: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const doUpload = (bearer: string | null) =>
      fetch(`${API}/api/v1/employees/${id}/enroll`, {
        method: "POST",
        headers: bearer ? { Authorization: `Bearer ${bearer}` } : {},
        body: formData,
      });
    let res = await doUpload(token);
    if (res.status === 401) {
      const newToken = await tryRefresh();
      if (newToken) {
        res = await doUpload(newToken);
      } else {
        redirectToLogin();
        throw new Error("Session expired");
      }
    }
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },
  deleteEmployee: (id: string) =>
    request(`/api/v1/employees/${id}`, { method: "DELETE" }),
  setBlacklist: (id: string, flagged: boolean) =>
    request(`/api/v1/employees/${id}/blacklist?flagged=${flagged}`, { method: "PATCH" }),
  setVip: (id: string, flagged: boolean) =>
    request(`/api/v1/employees/${id}/vip?flagged=${flagged}`, { method: "PATCH" }),

  // Cameras
  cameras: (includeDisabled = false) =>
    request<import("@/types").Camera[]>(`/api/v1/cameras?include_disabled=${includeDisabled}`),
  addCamera: (payload: object) =>
    request("/api/v1/cameras", { method: "POST", body: JSON.stringify(payload) }),
  updateCamera: (id: string, payload: object) =>
    request(`/api/v1/cameras/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteCamera: (id: string) =>
    request(`/api/v1/cameras/${id}`, { method: "DELETE" }),
  toggleCamera: (id: string) =>
    request<{ id: string; is_active: boolean; status: string }>(`/api/v1/cameras/${id}/toggle`, { method: "POST" }),
  scanCameras: () =>
    request<{ cameras: { onvif_url: string | null; rtsp_url: string | null; types: string }[]; count: number }>("/api/v1/cameras/scan"),
  autoConfigure: (id: string) =>
    request<{ id: string; direction: string; camera_role: string; cctv_mode: boolean; note: string }>(`/api/v1/cameras/${id}/auto-configure`, { method: "POST" }),
  cameraPreview: (id: string) =>
    requestBlob(`/api/v1/cameras/${id}/preview`),

  // Alerts (PRD §5.3)
  alerts: (unackedOnly = false) =>
    request<import("@/types").AlertItem[]>(
      `/api/v1/alerts?unacked_only=${unackedOnly}&page_size=50`
    ),
  recentAlerts: () =>
    request<import("@/types").AlertItem[]>("/api/v1/alerts/recent"),
  acknowledgeAlert: (id: string) =>
    request(`/api/v1/alerts/${id}/acknowledge`, { method: "POST" }),

  // Analytics (PRD §5.2, §5.4)
  occupancy: () =>
    request<{ building: number; zones: Record<string, number> }>("/api/v1/analytics/occupancy"),
  hourly: (date?: string) =>
    request<{ hour: number; entries: number; exits: number }[]>(
      `/api/v1/analytics/hourly${date ? `?day=${date}` : ""}`
    ),
  shiftCompliance: (weekStart: string) =>
    request<import("@/types").ComplianceRow[]>(
      `/api/v1/analytics/shift-compliance?week_start=${weekStart}`
    ),
  departmentOccupancy: () =>
    request<Record<string, number>>("/api/v1/analytics/department-occupancy"),
  // Shifts
  shifts: () =>
    request<ShiftRow[]>("/api/v1/shifts"),
  createShift: (p: ShiftPayload) =>
    request<ShiftRow>("/api/v1/shifts", { method: "POST", body: JSON.stringify(p) }),
  updateShift: (id: string, p: ShiftPayload) =>
    request<ShiftRow>(`/api/v1/shifts/${id}`, { method: "PATCH", body: JSON.stringify(p) }),
  deleteShift: (id: string) =>
    request(`/api/v1/shifts/${id}`, { method: "DELETE" }),
  shiftAssignments: () =>
    request<AssignmentRow[]>("/api/v1/shifts/assignments"),
  assignShift: (p: { employee_id: string; shift_id: string; effective_from: string }) =>
    request<AssignmentRow>("/api/v1/shifts/assignments", { method: "POST", body: JSON.stringify(p) }),
  removeAssignment: (employee_id: string) =>
    request(`/api/v1/shifts/assignments/${employee_id}`, { method: "DELETE" }),

  // Admin — user management
  adminUsers: () =>
    request<{ id: string; email: string; full_name: string | null; role: string; is_active: boolean; last_login_at: string | null; created_at: string | null }[]>(
      "/api/v1/admin/users"
    ),
  adminCreateUser: (payload: { email: string; password: string; full_name: string; role: string }) =>
    request<{ id: string; email: string; role: string }>(
      "/api/v1/admin/users", { method: "POST", body: JSON.stringify(payload) }
    ),
  adminUpdateUser: (id: string, payload: { role: string; is_active?: boolean }) =>
    request<{ id: string; email: string; role: string; is_active: boolean }>(
      `/api/v1/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }
    ),
  adminDeleteUser: (id: string) =>
    request(`/api/v1/admin/users/${id}`, { method: "DELETE" }),

  monthlyCsvUrl: (year: number, month: number) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    return `${API}/api/v1/reports/monthly.csv?year=${year}&month=${month}${token ? `&token=${token}` : ""}`;
  },
};