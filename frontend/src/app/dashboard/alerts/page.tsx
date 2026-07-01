"use client";
import { useEffect, useState } from "react";
import {
  ShieldAlert, Check, AlertTriangle, Clock, UserX, ShieldOff,
  HelpCircle, Eye, Package, Siren, Bell, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useRole } from "@/lib/rbac";
import DashboardShell from "@/components/ui/DashboardShell";
import type { AlertItem } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost";

const TYPE_META: Record<string, { label: string; Icon: React.ElementType }> = {
  intruder:          { label: "After-Hours Intruder",     Icon: Siren },
  blacklist:         { label: "Blocked Person Detected",  Icon: UserX },
  after_hours:       { label: "Outside Shift Hours",      Icon: Clock },
  restricted_area:   { label: "Restricted Area Entry",    Icon: Eye },
  vip:               { label: "VIP Arrival",              Icon: Bell },
  loitering:         { label: "Extended Stay",            Icon: Clock },
  spoof_attempt:     { label: "Fake Face Attempt",        Icon: ShieldOff },
  unknown_person:    { label: "Unknown Person",           Icon: HelpCircle },
  masked_face:       { label: "Face Covering Detected",   Icon: Eye },
  suspicious_object: { label: "Suspicious Object",        Icon: Package },
};

const SEV_META: Record<string, { label: string; card: string; iconBg: string; badge: string }> = {
  high: {
    label:  "Urgent",
    card:   "border-red-200 dark:border-red-800/50 bg-white dark:bg-gray-800/80",
    iconBg: "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400",
    badge:  "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
  },
  medium: {
    label:  "Attention",
    card:   "border-amber-200 dark:border-amber-800/50 bg-white dark:bg-gray-800/80",
    iconBg: "bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400",
    badge:  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400",
  },
  low: {
    label:  "Info",
    card:   "border-blue-200 dark:border-blue-800/50 bg-white dark:bg-gray-800/80",
    iconBg: "bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400",
    badge:  "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
  },
};

function AlertCard({ a, onAck, canAck }: { a: AlertItem; onAck: (id: string) => void; canAck: boolean }) {
  const meta  = TYPE_META[a.type] ?? { label: a.type.replace(/_/g, " "), Icon: AlertTriangle };
  const sev   = SEV_META[a.severity] ?? SEV_META.low;
  const { Icon } = meta;

  return (
    <div className={`flex gap-4 rounded-xl border p-4 shadow-sm transition-opacity ${sev.card} ${a.is_acknowledged ? "opacity-60" : ""}`}>
      {/* Icon badge */}
      <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${sev.iconBg}`}>
        <Icon size={18} />
      </div>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <span className="text-sm font-semibold text-gray-900 dark:text-white">{meta.label}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sev.badge}`}>{sev.label}</span>
          {a.is_acknowledged && (
            <span className="flex items-center gap-0.5 text-xs text-gray-400 dark:text-gray-500">
              <Check size={11} /> Reviewed
            </span>
          )}
        </div>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-snug">{a.message}</p>
        {a.created_at && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
            {new Date(a.created_at).toLocaleString()}
          </p>
        )}
      </div>

      {/* Snapshot thumbnail */}
      {a.snapshot_url && (
        <img
          src={a.snapshot_url.startsWith("http") ? a.snapshot_url : `${API_BASE}${a.snapshot_url}`}
          alt="snapshot"
          className="flex-shrink-0 w-14 h-14 rounded-lg object-cover border dark:border-gray-700"
          onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
        />
      )}

      {/* Ack button */}
      {!a.is_acknowledged && canAck && (
        <button
          onClick={() => onAck(a.id)}
          title="Mark as reviewed"
          className="flex-shrink-0 self-start mt-0.5 flex items-center gap-1 text-xs font-medium
                     bg-gray-50 dark:bg-gray-700 border dark:border-gray-600 text-gray-600 dark:text-gray-300
                     px-2.5 py-1.5 rounded-lg hover:bg-green-50 hover:text-green-700
                     dark:hover:bg-green-900/30 dark:hover:text-green-400 transition-colors"
        >
          <Check size={12} /> Review
        </button>
      )}
    </div>
  );
}

export default function AlertsPage() {
  const { can } = useRole();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [filter, setFilter] = useState<"all" | "unacked">("unacked");

  const load = () => api.alerts(filter === "unacked").then(setAlerts).catch(() => {});
  useEffect(() => { load(); }, [filter]);

  async function ack(id: string) {
    await api.acknowledgeAlert(id).catch(() => {});
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_acknowledged: true } : a));
  }

  const unacked = alerts.filter(a => !a.is_acknowledged).length;

  return (
    <DashboardShell>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-red-100 dark:bg-red-900/40 flex items-center justify-center">
            <ShieldAlert size={18} className="text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-gray-900 dark:text-white leading-tight">Alerts</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {unacked > 0 ? `${unacked} requiring review` : "All up to date"}
            </p>
          </div>
        </div>

        {/* Filter toggle */}
        <div className="flex rounded-lg border dark:border-gray-700 overflow-hidden text-xs">
          {(["unacked", "all"] as const).map(v => (
            <button
              key={v}
              onClick={() => setFilter(v)}
              className={`px-3 py-1.5 transition-colors ${
                filter === v
                  ? "bg-blue-600 text-white font-medium"
                  : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
              }`}
            >
              {v === "unacked" ? "Needs Review" : "All Alerts"}
            </button>
          ))}
        </div>
      </div>

      {/* Alert list */}
      <div className="space-y-2.5">
        {alerts.length === 0 && (
          <div className="glass rounded-xl p-10 flex flex-col items-center gap-3 text-gray-400 dark:text-gray-500">
            <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
              <Bell size={22} className="opacity-50" />
            </div>
            <p className="text-sm">{filter === "unacked" ? "No alerts requiring review" : "No alerts found"}</p>
          </div>
        )}
        {alerts.map(a => (
          <AlertCard key={a.id} a={a} onAck={ack} canAck={can("security")} />
        ))}
      </div>
    </DashboardShell>
  );
}
