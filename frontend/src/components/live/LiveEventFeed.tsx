"use client";
import { useEffect, useState } from "react";
import { LogIn, LogOut, Eye, ShieldOff, HelpCircle, Activity } from "lucide-react";
import { connectAttendanceWS } from "@/lib/websocket";
import { getSession } from "@/lib/auth";
import { api } from "@/lib/api";
import type { LiveEvent } from "@/types";

interface DisplayEvent {
  key: string;
  icon: React.ElementType;
  iconColor: string;
  label: string;
  sub: string;
  time: string;
  pulse?: boolean;
}

function formatOt(sec: number): string {
  if (sec >= 3600) return `+${Math.round(sec / 3600)}h OT`;
  if (sec >= 60)   return `+${Math.round(sec / 60)} min OT`;
  return `+${sec}s OT`;
}

function toDisplay(e: LiveEvent, idx: number): DisplayEvent | null {
  const time = e.timestamp
    ? new Date(typeof e.timestamp === "number" ? e.timestamp * 1000 : e.timestamp)
        .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "now";

  // ── Backend check_in ────────────────────────────────────────────────────
  if (e.action === "check_in") {
    const parts: string[] = [];
    if (e.is_late && e.late_by_min)
      parts.push(`${e.late_by_min} min late`);
    else
      parts.push("on time");
    const conf = e.confidence != null ? ` · ${Math.round(e.confidence * 100)}%` : "";
    return {
      key: `ci-${idx}-${time}`,
      icon: LogIn,
      iconColor: e.is_late
        ? "bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400"
        : "bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400",
      label: e.employee_name || "Employee",
      sub: `Checked in · ${parts.join(", ")}${conf}`,
      time,
    };
  }

  // ── Backend check_out ───────────────────────────────────────────────────
  if (e.action === "check_out") {
    const parts: string[] = [];
    if (e.overtime_seconds && e.overtime_seconds > 0)
      parts.push(formatOt(e.overtime_seconds));
    else if (e.is_early_leave && e.early_by_min)
      parts.push(`left ${e.early_by_min} min early`);
    const conf = e.confidence != null ? ` · ${Math.round(e.confidence * 100)}%` : "";
    return {
      key: `co-${idx}-${time}`,
      icon: LogOut,
      iconColor: "bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400",
      label: e.employee_name || "Employee",
      sub: `Checked out${parts.length ? " · " + parts.join(", ") : ""}${conf}`,
      time,
    };
  }

  // ── Raw edge: recognition (pending backend confirmation) ────────────────
  if (e.type === "recognition") {
    return {
      key: `rec-${idx}-${time}`,
      icon: Eye,
      iconColor: "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400",
      label: e.employee_name || e.employee_id?.slice(0, 8) || "Employee",
      sub: `Detected · ${Math.round((e.confidence ?? 0) * 100)}% match`,
      time,
      pulse: true,
    };
  }

  // ── Raw edge: unknown person ─────────────────────────────────────────────
  if (e.type === "unknown_person") {
    return {
      key: `unk-${idx}-${time}`,
      icon: HelpCircle,
      iconColor: "bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400",
      label: "Unknown Person",
      sub: `Unrecognised face · ${Math.round((e.confidence ?? 0) * 100)}% best`,
      time,
    };
  }

  // ── Raw edge: spoof attempt ──────────────────────────────────────────────
  if (e.type === "spoof_attempt") {
    return {
      key: `sp-${idx}-${time}`,
      icon: ShieldOff,
      iconColor: "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400",
      label: "Spoof Attempt",
      sub: `Liveness failed · score ${(e.spoof_score ?? 0).toFixed(2)}`,
      time,
    };
  }

  return null;
}

function initials(name: string) {
  return name.split(" ").filter(Boolean).map(p => p[0]).join("").toUpperCase().slice(0, 2);
}

export default function LiveEventFeed() {
  const [events, setEvents] = useState<LiveEvent[]>([]);

  useEffect(() => {
    const s = getSession();
    if (!s) return;

    api.liveFeed().then(setEvents).catch(() => {});

    const RAW_TYPES = new Set(["recognition", "unknown_person", "spoof_attempt"]);

    const handle = connectAttendanceWS(s.tenantId, s.token, (e) => {
      if (e.type === "ping") return;
      if (e.action === "skip") return;
      if (!e.action && !RAW_TYPES.has(e.type ?? "")) return;
      setEvents(prev => [e, ...prev].slice(0, 60));
    });

    return () => handle.close();
  }, []);

  const displayed = events
    .map((e, i) => toDisplay(e, i))
    .filter((d): d is DisplayEvent => d !== null);

  return (
    <div className="glass rounded-xl flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center justify-between flex-shrink-0">
        <span className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-1.5">
          <Activity size={14} className="text-blue-500" /> Live Feed
        </span>
        <span className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          real-time
        </span>
      </div>

      {/* Event list */}
      <div className="overflow-y-auto flex-1 max-h-96">
        {displayed.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 p-4 text-center">
            Waiting for events…
          </p>
        )}
        {displayed.map(d => {
          const Icon = d.icon;
          return (
            <div
              key={d.key}
              className="flex items-center gap-3 px-4 py-2.5 border-b dark:border-gray-700 last:border-0
                         hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              {/* Icon circle */}
              <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${d.iconColor}`}>
                <Icon size={15} />
              </div>

              {/* Name + sub */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate flex items-center gap-1">
                  {d.label}
                  {d.pulse && (
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse flex-shrink-0" />
                  )}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{d.sub}</p>
              </div>

              {/* Time */}
              <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                {d.time}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
