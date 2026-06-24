"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, ShieldAlert, Eye, Clock, UserX, ShieldOff, HelpCircle } from "lucide-react";
import { api } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { connectAlertsWS } from "@/lib/websocket";
import type { AlertItem } from "@/types";

const ICONS: Record<string, React.ElementType> = {
  intruder:        ShieldAlert,
  blacklist:       UserX,
  after_hours:     Clock,
  restricted_area: Eye,
  spoof_attempt:   ShieldOff,
  unknown_person:  HelpCircle,
  default:         AlertTriangle,
};

const SEV_COLOR: Record<string, string> = {
  high:   "bg-red-50   dark:bg-red-900/20   border-red-200   dark:border-red-800   text-red-700   dark:text-red-400",
  medium: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400",
  low:    "bg-blue-50  dark:bg-blue-900/20  border-blue-200  dark:border-blue-800  text-blue-700  dark:text-blue-400",
};

export default function AlertsFeed({ limit = 8 }: { limit?: number }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  useEffect(() => {
    const s = getSession();

    // Initial load from REST
    api.recentAlerts().then(setAlerts).catch(() => {});

    // Real-time updates via WebSocket
    const handle = s
      ? connectAlertsWS(s.tenantId, s.token, (raw) => {
          // WS payload shape from alert_service: { type:"alert", alert_type, severity, message, ... }
          const p = raw as Record<string, string | null | undefined>;
          if (!p.alert_type && p.type === "ping") return;
          const item: AlertItem = {
            id: String(Date.now()),
            type: p.alert_type ?? p.type ?? "alert",
            severity: (p.severity as AlertItem["severity"]) ?? "medium",
            message: p.message ?? "",
            employee_id: p.employee_id ?? null,
            camera_id: p.camera_id ?? null,
            snapshot_url: p.snapshot_url ?? null,
            is_acknowledged: false,
            created_at: p.timestamp ?? new Date().toISOString(),
          };
          setAlerts((prev) => [item, ...prev].slice(0, 50));
        })
      : null;

    // Fallback poll every 10 s in case WS drops
    const t = setInterval(() => api.recentAlerts().then(setAlerts).catch(() => {}), 10_000);

    return () => {
      handle?.close();
      clearInterval(t);
    };
  }, []);

  const top = alerts.slice(0, limit);
  const unacked = alerts.filter((a) => !a.is_acknowledged).length;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700">
      <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-1.5">
          <AlertTriangle size={14} className="text-red-500" /> Security alerts
        </span>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-xs text-brand">
            <span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" /> live
          </span>
          {unacked > 0 && (
            <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 px-2 py-0.5 rounded-full">
              {unacked} new
            </span>
          )}
        </div>
      </div>
      {top.length === 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-500 p-4 text-center">No alerts</p>
      )}
      {top.map((a, i) => {
        const Icon = ICONS[a.type] || ICONS.default;
        const color = SEV_COLOR[a.severity] || SEV_COLOR.low;
        return (
          <div
            key={a.id || i}
            className={`flex gap-3 px-4 py-3 border-b last:border-0 border ${color} ${i === 0 ? "rounded-t-none" : ""}`}
          >
            <Icon size={15} className="mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium capitalize">{(a.type ?? "").replace(/_/g, " ")}</p>
              <p className="text-xs opacity-80 truncate">{a.message}</p>
            </div>
            <span className="text-xs opacity-60 whitespace-nowrap">
              {a.created_at
                ? new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                : "now"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
