"use client";
import { useEffect, useState } from "react";
import { connectAttendanceWS } from "@/lib/websocket";
import { getSession } from "@/lib/auth";
import { api } from "@/lib/api";
import type { LiveEvent } from "@/types";

function eventLabel(e: LiveEvent): { label: string; sub: string; color: string } {
  // Processed backend event (check_in / check_out)
  if (e.action && e.action !== "skip") {
    const late = e.is_late ? " — late" : "";
    const conf = e.confidence != null ? ` · ${Math.round(e.confidence * 100)}%` : "";
    return {
      label: e.employee_name || "Unknown",
      sub: `${e.action === "check_in" ? "Checked in" : "Checked out"}${late}${conf}`,
      color: e.is_late
        ? "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400"
        : "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400",
    };
  }
  // Raw edge recognition (before backend confirms check_in/check_out)
  if (e.type === "recognition") {
    return {
      label: e.employee_name || e.employee_id || "Employee",
      sub: `Detected · conf ${Math.round((e.confidence ?? 0) * 100)}%`,
      color: "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
    };
  }
  // Raw edge event — unknown person
  if (e.type === "unknown_person") {
    return {
      label: "Unknown Person",
      sub: `Unrecognised face · conf ${Math.round((e.confidence ?? 0) * 100)}%`,
      color: "bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400",
    };
  }
  // Raw edge event — spoof attempt
  if (e.type === "spoof_attempt") {
    return {
      label: "Spoof Attempt",
      sub: `Liveness check failed · score ${((e.spoof_score ?? 0)).toFixed(2)}`,
      color: "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400",
    };
  }
  return { label: "Event", sub: e.type ?? "", color: "bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-300" };
}

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").toUpperCase().slice(0, 2);
}

export default function LiveEventFeed() {
  const [events, setEvents] = useState<LiveEvent[]>([]);

  useEffect(() => {
    const s = getSession();
    if (!s) return;

    // Load last 50 processed events from Redis cache
    api.liveFeed().then(setEvents).catch(() => {});

    const handle = connectAttendanceWS(s.tenantId, s.token, (e) => {
      if (e.type === "ping") return;
      if (e.action === "skip") return;
      // Accept backend-processed events (check_in / check_out) and all raw edge
      // events (recognition, unknown_person, spoof_attempt) so the feed updates
      // immediately on detection without waiting for the DB round-trip.
      const RAW_TYPES = new Set(["recognition", "unknown_person", "spoof_attempt"]);
      if (!e.action && !RAW_TYPES.has(e.type ?? "")) return;
      setEvents((prev) => [e, ...prev].slice(0, 50));
    });

    return () => handle.close();
  }, []);

  return (
    <div className="glass rounded-xl">
      <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900 dark:text-white">Live feed</span>
        <span className="flex items-center gap-1.5 text-xs text-brand">
          <span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" /> real-time
        </span>
      </div>
      <div className="max-h-96 overflow-y-auto">
        {events.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 p-4">Waiting for events…</p>
        )}
        {events.map((e, i) => {
          const { label, sub, color } = eventLabel(e);
          return (
            <div
              key={i}
              className="flex items-center gap-3 px-4 py-2.5 border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium flex-shrink-0 ${color}`}>
                {initials(label)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate text-gray-900 dark:text-white">{label}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{sub}</p>
              </div>
              <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                {e.timestamp
                  ? new Date(typeof e.timestamp === "number" ? e.timestamp * 1000 : e.timestamp)
                      .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                  : "now"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
