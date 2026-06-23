"use client";
import { useEffect, useState } from "react";
import { connectAttendanceWS } from "@/lib/websocket";
import { getSession } from "@/lib/auth";
import { api } from "@/lib/api";
import type { LiveEvent } from "@/types";

export default function LiveEventFeed() {
  const [events, setEvents] = useState<LiveEvent[]>([]);

  useEffect(() => {
    const s = getSession();
    if (!s) return;
    api.liveFeed().then(setEvents).catch(() => {});
    const handle = connectAttendanceWS(s.tenantId, s.token, (e) => {
      // Only show processed attendance events (have action + employee_name from backend)
      if (!e.action || e.action === "skip" || !e.employee_name) return;
      setEvents((prev) => [e, ...prev].slice(0, 50));
    });
    return () => handle.close();
  }, []);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700">
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
        {events.map((e, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2.5 border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
            <div className="w-8 h-8 rounded-full bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 flex items-center justify-center text-xs font-medium">
              {(e.employee_name || "?").split(" ").map((p: string) => p[0]).join("").toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate text-gray-900 dark:text-white">{e.employee_name || "Unknown"}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {e.action === "check_in" ? "Checked in" : "Checked out"}
                {e.is_late ? " — late" : ""} · {Math.round((e.confidence ?? 0) * 100)}%
              </p>
            </div>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
