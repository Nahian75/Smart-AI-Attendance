"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, ShieldAlert, Eye, Clock, UserX } from "lucide-react";
import { api } from "@/lib/api";
import type { AlertItem } from "@/types";

const ICONS: Record<string, React.ElementType> = {
  intruder: ShieldAlert, blacklist: UserX, after_hours: Clock,
  restricted_area: Eye, default: AlertTriangle,
};

const SEV_COLOR: Record<string, string> = {
  high:   "bg-red-50   dark:bg-red-900/20   border-red-200   dark:border-red-800   text-red-700   dark:text-red-400",
  medium: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400",
  low:    "bg-blue-50  dark:bg-blue-900/20  border-blue-200  dark:border-blue-800  text-blue-700  dark:text-blue-400",
};

export default function AlertsFeed({ limit = 8 }: { limit?: number }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  useEffect(() => {
    const load = () => api.recentAlerts().then(setAlerts).catch(() => {});
    load();
    // Poll every 15 s — the attendance WebSocket carries check-in events, not alerts
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, []);

  const top = alerts.slice(0, limit);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700">
      <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-1.5">
          <AlertTriangle size={14} className="text-red-500" /> Security alerts
        </span>
        {alerts.filter((a) => !a.is_acknowledged).length > 0 && (
          <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 px-2 py-0.5 rounded-full">
            {alerts.filter((a) => !a.is_acknowledged).length} unacked
          </span>
        )}
      </div>
      {top.length === 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-500 p-4 text-center">No alerts</p>
      )}
      {top.map((a, i) => {
        const Icon = ICONS[a.type] || ICONS.default;
        const color = SEV_COLOR[a.severity] || SEV_COLOR.low;
        return (
          <div key={a.id || i}
               className={`flex gap-3 px-4 py-3 border-b last:border-0 border ${color} ${i === 0 ? "rounded-t-none" : ""}`}>
            <Icon size={15} className="mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium capitalize">{a.type?.replace(/_/g, " ")}</p>
              <p className="text-xs opacity-80 truncate">{a.message}</p>
            </div>
            <span className="text-xs opacity-60 whitespace-nowrap">
              {a.created_at ? new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "now"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
