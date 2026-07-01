"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { UserCheck, UserX, Clock, ScanEye, Users, Pencil, Trash2, RotateCcw, X } from "lucide-react";
import { api } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { connectAttendanceWS } from "@/lib/websocket";
import { useRole } from "@/lib/rbac";
import type { AttendanceSummary, AttendanceLog, Employee } from "@/types";
import LiveEventFeed from "@/components/live/LiveEventFeed";
import AlertsFeed from "@/components/live/AlertsFeed";
import OccupancyCards from "@/components/live/OccupancyCards";
import CameraFeed from "@/components/live/CameraFeed";
import WeeklyChart from "@/components/charts/WeeklyChart";
import HourlyChart from "@/components/charts/HourlyChart";
import DashboardShell from "@/components/ui/DashboardShell";
import type { Camera } from "@/types";

// ── Edit modal ───────────────────────────────────────────────────────────────
type EditState = {
  id: string;
  attendance_date: string;
  check_in_at: string;
  check_out_at: string;
  status: string;
};

function toLocalDatetime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function EditLogModal({ log, onClose, onSaved }: { log: EditState; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState(log);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  async function save() {
    setSaving(true); setErr("");
    try {
      await api.updateLog(form.id, {
        attendance_date: form.attendance_date || undefined,
        check_in_at: form.check_in_at ? new Date(form.check_in_at).toISOString() : null,
        check_out_at: form.check_out_at ? new Date(form.check_out_at).toISOString() : null,
        status: form.status,
      });
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="glass-heavy rounded-xl p-5 w-80 space-y-3">
        <div className="flex items-center justify-between">
          <span className="font-medium text-sm">Edit Attendance</span>
          <button onClick={onClose}><X size={16} /></button>
        </div>
        <label className="block text-xs text-gray-500">Date
          <input type="date" className="mt-0.5 w-full border rounded px-2 py-1.5 text-sm"
            value={form.attendance_date}
            onChange={e => setForm(f => ({ ...f, attendance_date: e.target.value }))} />
        </label>
        <label className="block text-xs text-gray-500">Check-in
          <input type="datetime-local" className="mt-0.5 w-full border rounded px-2 py-1.5 text-sm"
            value={form.check_in_at}
            onChange={e => setForm(f => ({ ...f, check_in_at: e.target.value }))} />
        </label>
        <label className="block text-xs text-gray-500">Check-out
          <input type="datetime-local" className="mt-0.5 w-full border rounded px-2 py-1.5 text-sm"
            value={form.check_out_at}
            onChange={e => setForm(f => ({ ...f, check_out_at: e.target.value }))} />
        </label>
        <label className="block text-xs text-gray-500">Status
          <select className="mt-0.5 w-full border rounded px-2 py-1.5 text-sm"
            value={form.status}
            onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
            {["present","late","absent","half_day","holiday"].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        {err && <p className="text-xs text-red-600">{err}</p>}
        <div className="flex gap-2 pt-1">
          <button onClick={onClose} className="flex-1 border rounded py-1.5 text-xs text-gray-600 hover:bg-gray-50">Cancel</button>
          <button onClick={save} disabled={saving}
            className="flex-1 bg-blue-600 text-white rounded py-1.5 text-xs hover:bg-blue-700 disabled:opacity-50">
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Overview page ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const router = useRouter();
  const { can } = useRole();
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [logs, setLogs] = useState<AttendanceLog[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [visitors, setVisitors] = useState(0);
  const [editLog, setEditLog] = useState<EditState | null>(null);
  const [resetting, setResetting] = useState(false);
  const [logPage, setLogPage] = useState(1);
  const [logHasMore, setLogHasMore] = useState(false);
  const LOG_PAGE_SIZE = 10;

  const todayStr = new Date().toISOString().slice(0, 10);

  function fetchLogs(page = 1) {
    api.logs(`page=${page}&page_size=${LOG_PAGE_SIZE}`).then((rows) => {
      setLogs(rows);
      setLogPage(page);
      setLogHasMore(rows.length === LOG_PAGE_SIZE);
    }).catch(() => {});
  }

  useEffect(() => {
    const s = getSession();
    if (!s) { router.push("/login"); return; }

    const refreshStats = () => {
      api.summary().then(setSummary).catch(() => {});
      api.visitors().then((r) => setVisitors(r.unknown_detections)).catch(() => {});
    };

    refreshStats();
    fetchLogs(1);
    api.employees().then(setEmployees).catch(() => {});
    api.cameras().then(setCameras).catch(() => {});

    // Poll every 30 s so stats stay current even during cooldown windows
    const pollTimer = setInterval(() => { refreshStats(); fetchLogs(1); }, 30_000);

    // Also refresh immediately (1 s delay) on each WebSocket check-in/out event
    let debounce: ReturnType<typeof setTimeout> | null = null;
    const handle = connectAttendanceWS(s.tenantId, s.token, () => {
      if (debounce) return;
      debounce = setTimeout(() => {
        debounce = null;
        refreshStats();
        fetchLogs(1);
      }, 1000);
    });

    return () => {
      clearInterval(pollTimer);
      handle.close();
      if (debounce) clearTimeout(debounce);
    };
  }, [router]);

  async function handleDelete(id: string) {
    if (!confirm("Delete this attendance record?")) return;
    await api.deleteLog(id).catch(() => {});
    fetchLogs(logPage);
  }

  async function handleReset() {
    if (!confirm(`Reset ALL attendance records for today (${todayStr})?`)) return;
    setResetting(true);
    await api.resetLogs(todayStr).catch(() => {});
    setResetting(false);
    fetchLogs(1);
    api.summary().then(setSummary).catch(() => {});
  }

  function openEdit(l: AttendanceLog) {
    setEditLog({
      id: l.id,
      attendance_date: l.attendance_date,
      check_in_at: toLocalDatetime(l.check_in_at),
      check_out_at: toLocalDatetime(l.check_out_at),
      status: l.status,
    });
  }

  const empName = (id: string) => employees.find((e) => e.id === id)?.full_name || id.slice(0, 8);

  const stats = [
    { label: "Present today", value: summary?.present ?? "—", icon: UserCheck, color: "text-green-600" },
    { label: "Absent",        value: summary?.absent  ?? "—", icon: UserX,    color: "text-red-600" },
    { label: "Late arrivals", value: summary?.late    ?? "—", icon: Clock,    color: "text-amber-600" },
    { label: "Visitors today",value: visitors,                icon: Users,    color: "text-blue-600" },
    { label: "Attendance %",  value: summary ? `${summary.attendance_rate}%` : "—", icon: ScanEye, color: "text-green-600" },
  ];

  return (
    <DashboardShell>
      <h1 className="text-lg font-medium">Overview</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="glass rounded-xl p-3">
            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-1.5">
              <s.icon size={13} /> {s.label}
            </div>
            <div className={`text-xl font-medium ${s.color}`}>{String(s.value)}</div>
          </div>
        ))}
      </div>

      {/* Occupancy + weekly */}
      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
        <OccupancyCards />
        <WeeklyChart />
      </div>

      {/* Hourly chart */}
      <HourlyChart />

      {/* Edit modal */}
      {editLog && (
        <EditLogModal
          log={editLog}
          onClose={() => setEditLog(null)}
          onSaved={() => { setEditLog(null); fetchLogs(); api.summary().then(setSummary).catch(() => {}); }}
        />
      )}

      {/* Live cameras */}
      <div className="glass rounded-xl">
        <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-sm font-medium text-gray-900 dark:text-white">Live Cameras</span>
          <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
            {cameras.length === 0 ? "No cameras registered" : `${cameras.length} camera${cameras.length !== 1 ? "s" : ""}`}
          </span>
        </div>
        {cameras.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-gray-400 dark:text-gray-500">
            <svg className="w-10 h-10 mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
            <p className="text-sm">No cameras added yet</p>
            <p className="text-xs mt-1">Go to <strong>Cameras</strong> to register your first camera</p>
          </div>
        ) : (
          <div className={`p-3 grid gap-3 ${
            cameras.length === 1 ? "grid-cols-1 max-w-sm" :
            "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
          }`}>
            {cameras.map(cam => (
              <CameraFeed
                key={cam.id}
                cameraId={cam.id}
                cameraName={cam.name}
                location={cam.location}
                direction={cam.direction}
                status={cam.status}
              />
            ))}
          </div>
        )}
      </div>

      {/* 3-col live area */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px_280px] gap-4">
        {/* Recent check-ins table */}
        <div className="glass rounded-xl">
          <div className="px-4 py-3 border-b dark:border-gray-700 text-sm font-medium text-gray-900 dark:text-white flex items-center justify-between">
            <span>Recent check-ins</span>
            {can("admin") && (
              <button onClick={handleReset} disabled={resetting}
                className="flex items-center gap-1 text-xs text-red-600 hover:text-red-800 disabled:opacity-50">
                <RotateCcw size={12} /> {resetting ? "Resetting…" : "Reset today"}
              </button>
            )}
          </div>
          <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-xs text-gray-400 dark:text-gray-500 border-b dark:border-gray-700">
                <th className="text-left px-4 py-2">Employee</th>
                <th className="text-left px-4 py-2">In</th>
                <th className="text-left px-4 py-2">Out</th>
                <th className="text-left px-4 py-2">OT (sec)</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 text-gray-900 dark:text-gray-100">
                  <td className="px-4 py-2">{empName(l.employee_id)}</td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {l.check_in_at ? new Date(l.check_in_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {l.check_out_at ? new Date(l.check_out_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-amber-700">
                    {l.overtime_seconds > 0 ? `+${l.overtime_seconds}s` : "—"}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      l.status === "late" ? "bg-amber-50 text-amber-700"
                      : l.status === "absent" ? "bg-red-50 text-red-700"
                      : "bg-green-50 text-green-700"}`}>
                      {l.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      {can("hr") && (
                        <button onClick={() => openEdit(l)} className="text-gray-400 hover:text-blue-600" title="Edit log">
                          <Pencil size={13} />
                        </button>
                      )}
                      {can("hr") && (
                        <button onClick={() => handleDelete(l.id)} className="text-gray-400 hover:text-red-600" title="Delete log">
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400 dark:text-gray-500 text-xs">No records yet</td></tr>
              )}
            </tbody>
          </table>
          </div>
          {(logPage > 1 || logHasMore) && (
            <div className="flex items-center justify-between px-4 py-2 border-t dark:border-gray-700">
              <button
                onClick={() => fetchLogs(logPage - 1)}
                disabled={logPage === 1}
                className="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 disabled:opacity-30">
                ← Prev
              </button>
              <span className="text-xs text-gray-400">Page {logPage}</span>
              <button
                onClick={() => fetchLogs(logPage + 1)}
                disabled={!logHasMore}
                className="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 disabled:opacity-30">
                Next →
              </button>
            </div>
          )}
        </div>

        <LiveEventFeed />
        <AlertsFeed limit={6} />
      </div>
    </DashboardShell>
  );
}
