"use client";
import { useEffect, useState } from "react";
import {
  AlertTriangle, Clock, UserX, ShieldOff,
  HelpCircle, Eye, Package, Siren, Bell, ShieldAlert,
} from "lucide-react";
import { api } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { connectAlertsWS } from "@/lib/websocket";
import type { AlertItem } from "@/types";

const TYPE_META: Record<string, { label: string; Icon: React.ElementType }> = {
  intruder:          { label: "Intruder",         Icon: Siren },
  blacklist:         { label: "Blocked Person",   Icon: UserX },
  after_hours:       { label: "After Hours",      Icon: Clock },
  restricted_area:   { label: "Restricted Area",  Icon: Eye },
  vip:               { label: "VIP Arrival",      Icon: Bell },
  loitering:         { label: "Loitering",        Icon: Clock },
  spoof_attempt:     { label: "Spoof Attempt",    Icon: ShieldOff },
  unknown_person:    { label: "Unknown Person",   Icon: HelpCircle },
  masked_face:       { label: "Face Covering",    Icon: Eye },
  suspicious_object: { label: "Suspicious Object",Icon: Package },
};

const SEV_STYLE: Record<string, { bar: string; iconBg: string; badge: string }> = {
  high: {
    bar:    "bg-red-500",
    iconBg: "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400",
    badge:  "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
  },
  medium: {
    bar:    "bg-amber-400",
    iconBg: "bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400",
    badge:  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400",
  },
  low: {
    bar:    "bg-blue-400",
    iconBg: "bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400",
    badge:  "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
  },
};

const SEV_LABEL: Record<string, string> = {
  high: "Urgent", medium: "Attention", low: "Info",
};

export default function AlertsFeed({ limit = 8 }: { limit?: number }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  // The Redis-cached payload uses { type:"alert", alert_type:"intruder" }.
  // The DB REST endpoint uses { type:"intruder" }. Normalize both to AlertItem.
  function normalize(raw: unknown): AlertItem {
    const r = raw as Record<string, unknown>;
    return {
      id:               String(r.id ?? `${Date.now()}-${Math.random()}`),
      type:             String(r.alert_type ?? r.type ?? "alert"),
      severity:         (r.severity as AlertItem["severity"]) ?? "medium",
      message:          String(r.message ?? ""),
      employee_id:      (r.employee_id as string | null) ?? null,
      camera_id:        (r.camera_id as string | null) ?? null,
      snapshot_url:     (r.snapshot_url as string | null) ?? null,
      is_acknowledged:  Boolean(r.is_acknowledged ?? false),
      created_at:       String(r.timestamp ?? r.created_at ?? new Date().toISOString()),
    };
  }

  useEffect(() => {
    const s = getSession();

    api.recentAlerts()
      .then(raw => setAlerts((raw as unknown[]).map(normalize)))
      .catch(() => {});

    const handle = s
      ? connectAlertsWS(s.tenantId, s.token, (raw) => {
          const p = raw as Record<string, unknown>;
          if (p.type === "ping") return;
          const alertType = (p.alert_type ?? p.type) as string | undefined;
          if (!alertType || alertType === "ping") return;
          setAlerts(prev => [normalize({ ...p, alert_type: alertType }), ...prev].slice(0, 50));
        })
      : null;

    const t = setInterval(() => api.recentAlerts().then(setAlerts).catch(() => {}), 10_000);
    return () => { handle?.close(); clearInterval(t); };
  }, []);

  const top    = alerts.slice(0, limit);
  const unacked = alerts.filter(a => !a.is_acknowledged).length;

  return (
    <div className="glass rounded-xl flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center justify-between flex-shrink-0">
        <span className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-1.5">
          <ShieldAlert size={14} className="text-red-500" /> Security Alerts
        </span>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-xs text-red-500 dark:text-red-400">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" /> live
          </span>
          {unacked > 0 && (
            <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 px-2 py-0.5 rounded-full font-medium">
              {unacked} new
            </span>
          )}
        </div>
      </div>

      {/* Feed */}
      <div className="overflow-y-auto flex-1 max-h-96">
        {top.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 p-4 text-center">No alerts</p>
        )}
        {top.map((a, i) => {
          const meta  = TYPE_META[a.type] ?? { label: a.type.replace(/_/g, " "), Icon: AlertTriangle };
          const style = SEV_STYLE[a.severity] ?? SEV_STYLE.low;
          const { Icon } = meta;

          return (
            <div
              key={a.id || i}
              className={`relative flex items-start gap-3 px-4 py-3 border-b dark:border-gray-700 last:border-0
                          hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors
                          ${a.is_acknowledged ? "opacity-50" : ""}`}
            >
              {/* Left accent bar */}
              <div className={`absolute left-0 top-2 bottom-2 w-0.5 rounded-full ${style.bar}`} />

              {/* Icon */}
              <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${style.iconBg}`}>
                <Icon size={13} />
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                  <span className="text-xs font-semibold text-gray-900 dark:text-white">{meta.label}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${style.badge}`}>
                    {SEV_LABEL[a.severity] ?? a.severity}
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-300 leading-snug line-clamp-2">{a.message}</p>
              </div>

              {/* Time */}
              <span className="flex-shrink-0 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                {a.created_at
                  ? new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                  : "now"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
