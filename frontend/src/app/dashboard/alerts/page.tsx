"use client";
import { useEffect, useState } from "react";
import { ShieldAlert, Check } from "lucide-react";
import { api } from "@/lib/api";
import { useRole } from "@/lib/rbac";
import DashboardShell from "@/components/ui/DashboardShell";
import type { AlertItem } from "@/types";

const SEV: Record<string, string> = {
  high:   "border-l-4 border-red-400",
  medium: "border-l-4 border-amber-400",
  low:    "border-l-4 border-blue-300",
};
const TYPE_LABEL: Record<string, string> = {
  intruder: "Intruder",
  blacklist: "Blacklist",
  after_hours: "After-hours",
  restricted_area: "Restricted area",
  vip: "VIP",
  loitering: "Loitering",
  spoof_attempt: "Spoof attempt",
  unknown_person: "Unknown person",
};

export default function AlertsPage() {
  const { can } = useRole();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [filter, setFilter] = useState<"all" | "unacked">("unacked");
  const load = () => api.alerts(filter === "unacked").then(setAlerts).catch(() => {});
  useEffect(() => { load(); }, [filter]);
  async function ack(id: string) {
    await api.acknowledgeAlert(id);
    setAlerts((prev: AlertItem[]) => prev.map((a) => a.id === id ? { ...a, is_acknowledged: true } : a));
  }
  return (
    <DashboardShell>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium flex items-center gap-2">
          <ShieldAlert size={18} className="text-red-500" /> Security Alerts
        </h2>
        <div className="flex rounded-lg border overflow-hidden text-xs">
          {(["unacked", "all"] as const).map((v) => (
            <button key={v} onClick={() => setFilter(v)}
                    className={`px-3 py-1.5 ${filter === v ? "bg-gray-100 dark:bg-gray-700 font-medium" : "bg-white dark:bg-gray-800"}`}>
              {v === "unacked" ? "Unacknowledged" : "All"}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        {alerts.length === 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-8 text-center text-gray-400 dark:text-gray-500 text-sm">
            No alerts {filter === "unacked" ? "requiring action" : "found"}
          </div>
        )}
        {alerts.map((a) => (
          <div key={a.id} className={`rounded-xl bg-white dark:bg-gray-800 border dark:border-gray-700 p-4 flex items-start gap-3 ${SEV[a.severity] || ""}`}>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium">{TYPE_LABEL[a.type] || a.type}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${
                  a.severity === "high" ? "bg-red-100 text-red-700"
                  : a.severity === "medium" ? "bg-amber-100 text-amber-700"
                  : "bg-blue-100 text-blue-700"}`}>{a.severity}</span>
                {a.is_acknowledged && <span className="text-xs text-gray-400 dark:text-gray-500">✓ acknowledged</span>}
              </div>
              <p className="text-sm text-gray-600">{a.message}</p>
              {a.created_at && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{new Date(a.created_at).toLocaleString()}</p>}
            </div>
            {!a.is_acknowledged && can("security") && (
              <button onClick={() => ack(a.id)}
                      className="flex items-center gap-1 text-xs bg-white dark:bg-gray-700 border dark:border-gray-600 px-2 py-1 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 dark:text-gray-200">
                <Check size={12} /> Ack
              </button>
            )}
          </div>
        ))}
      </div>
    </DashboardShell>
  );
}
