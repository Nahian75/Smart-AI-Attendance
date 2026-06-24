"use client";
import { useEffect, useState, useCallback } from "react";
import { ShieldOff, HelpCircle, UserCheck, RefreshCw, ZoomIn, X, Camera } from "lucide-react";
import DashboardShell from "@/components/ui/DashboardShell";
import { api } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────────────────────
interface DetectionItem {
  id: string;
  event_type: "recognition" | "unknown_person" | "spoof_attempt";
  timestamp: string | null;
  employee_id: string | null;
  employee_name: string | null;
  camera_id: string | null;
  camera_name: string | null;
  confidence: number | null;
  is_live: boolean;
  spoof_score: number | null;
  snapshot_url: string | null;
}

interface Stats {
  total_detections: number;
  recognised: number;
  unknown: number;
  spoof_attempts: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

function token() {
  return typeof window !== "undefined" ? localStorage.getItem("token") : null;
}

async function fetchDetections(page: number, filter: string, dateFrom: string, dateTo: string) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: "24",
    ...(filter !== "all" ? { event_type: filter } : {}),
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  });
  const res = await fetch(`${API}/api/v1/detections?${params}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!res.ok) throw new Error("Failed to load detections");
  return res.json() as Promise<{ total: number; page: number; page_size: number; items: DetectionItem[] }>;
}

async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API}/api/v1/detections/stats`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!res.ok) throw new Error("Failed");
  return res.json();
}

// ── Badge ─────────────────────────────────────────────────────────────────────
function TypeBadge({ type, isLive }: { type: string; isLive: boolean }) {
  if (!isLive || type === "spoof_attempt")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
        <ShieldOff size={11} /> Spoof
      </span>
    );
  if (type === "unknown_person")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
        <HelpCircle size={11} /> Unknown
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
      <UserCheck size={11} /> Recognised
    </span>
  );
}

// ── Snapshot thumbnail ────────────────────────────────────────────────────────
function Snapshot({ url, name, onClick }: { url: string | null; name: string; onClick: () => void }) {
  const [err, setErr] = useState(false);

  if (!url || err) {
    return (
      <div className="w-full aspect-square bg-gray-100 dark:bg-gray-700 rounded-lg flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 gap-1">
        <Camera size={24} />
        <span className="text-xs">No snapshot</span>
      </div>
    );
  }

  return (
    <button
      onClick={onClick}
      className="relative w-full aspect-square bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden group"
      title="Click to enlarge"
    >
      <img
        src={`${API}${url}`}
        alt={name}
        className="w-full h-full object-cover"
        onError={() => setErr(true)}
      />
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
        <ZoomIn size={20} className="text-white" />
      </div>
    </button>
  );
}

// ── Lightbox ──────────────────────────────────────────────────────────────────
function Lightbox({ url, onClose }: { url: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button className="absolute top-4 right-4 text-white" onClick={onClose}>
        <X size={28} />
      </button>
      <img
        src={`${API}${url}`}
        alt="Detection snapshot"
        className="max-w-full max-h-full rounded-xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────
function DetectionCard({ item, onZoom }: { item: DetectionItem; onZoom: (url: string) => void }) {
  const ts = item.timestamp ? new Date(item.timestamp) : null;
  const conf = item.confidence != null ? `${Math.round(item.confidence * 100)}%` : "—";
  const spoof = item.spoof_score != null ? item.spoof_score.toFixed(3) : null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 overflow-hidden hover:shadow-md transition-shadow">
      <Snapshot
        url={item.snapshot_url}
        name={item.employee_name || "Unknown"}
        onClick={() => item.snapshot_url && onZoom(item.snapshot_url)}
      />
      <div className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-1">
          <TypeBadge type={item.event_type} isLive={item.is_live} />
          {ts && (
            <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
              {ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
          )}
        </div>

        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
          {item.employee_name || (item.event_type === "spoof_attempt" ? "Spoof attempt" : "Unknown person")}
        </p>

        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
          {ts && (
            <p>{ts.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" })}</p>
          )}
          {item.camera_name && <p>📷 {item.camera_name}</p>}
          <p>Confidence: <span className="font-mono font-medium">{conf}</span></p>
          {spoof && (
            <p className="text-red-600 dark:text-red-400">
              Liveness score: <span className="font-mono">{spoof}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
const FILTERS = [
  { key: "all",            label: "All" },
  { key: "recognition",   label: "Recognised" },
  { key: "unknown_person",label: "Unknown" },
  { key: "spoof_attempt", label: "Spoof" },
];

export default function DetectionLogPage() {
  const [items, setItems] = useState<DetectionItem[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);

  const PAGE_SIZE = 24;

  const load = useCallback(
    async (p = page) => {
      setLoading(true);
      try {
        const data = await fetchDetections(p, filter, dateFrom, dateTo);
        setItems(data.items);
        setTotal(data.total);
        setPage(p);
      } catch { /* silent */ }
      finally { setLoading(false); }
    },
    [filter, dateFrom, dateTo, page]
  );

  useEffect(() => {
    fetchStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, dateFrom, dateTo]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <DashboardShell>
      {lightbox && <Lightbox url={lightbox} onClose={() => setLightbox(null)} />}

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-medium text-gray-900 dark:text-white">Detection Evidence Log</h1>
        <button
          onClick={() => { fetchStats().then(setStats).catch(() => {}); load(page); }}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Total Detections", value: stats.total_detections, color: "text-gray-800 dark:text-gray-100" },
            { label: "Recognised",       value: stats.recognised,       color: "text-green-600 dark:text-green-400" },
            { label: "Unknown Persons",  value: stats.unknown,          color: "text-orange-600 dark:text-orange-400" },
            { label: "Spoof Attempts",   value: stats.spoof_attempts,   color: "text-red-600 dark:text-red-400" },
          ].map((s) => (
            <div key={s.label} className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-3">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{s.label}</p>
              <p className={`text-2xl font-semibold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
                filter === f.key
                  ? "bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm font-medium"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <label className="text-xs text-gray-500">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="text-xs border dark:border-gray-600 rounded px-2 py-1 dark:bg-gray-700 dark:text-gray-200"
          />
          <label className="text-xs text-gray-500">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="text-xs border dark:border-gray-600 rounded px-2 py-1 dark:bg-gray-700 dark:text-gray-200"
          />
          {(dateFrom || dateTo) && (
            <button
              onClick={() => { setDateFrom(""); setDateTo(""); }}
              className="text-xs text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Grid */}
      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center py-20 text-gray-400 dark:text-gray-500 text-sm">
          Loading detections…
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
          <Camera size={40} className="mb-2 opacity-30" />
          <p className="text-sm">No detections found</p>
          <p className="text-xs mt-1">Detections will appear here once cameras start processing faces</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {items.map((item) => (
            <DetectionCard key={item.id} item={item} onZoom={setLightbox} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>{total} detections total</span>
          <div className="flex items-center gap-2">
            <button
              disabled={page === 1}
              onClick={() => load(page - 1)}
              className="px-3 py-1.5 border dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30"
            >
              ← Prev
            </button>
            <span>Page {page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => load(page + 1)}
              className="px-3 py-1.5 border dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </DashboardShell>
  );
}
