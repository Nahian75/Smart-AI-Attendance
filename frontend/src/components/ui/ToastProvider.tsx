"use client";
import { useEffect, useState, useCallback } from "react";
import {
  X, ShieldAlert, AlertTriangle, Clock, UserX, ShieldOff,
  HelpCircle, Eye, Package, Siren, Bell,
} from "lucide-react";
import { getSession } from "@/lib/auth";
import { connectAlertsWS } from "@/lib/websocket";

interface Toast {
  id: string;
  type: string;
  severity: "high" | "medium" | "low";
  message: string;
  entering: boolean;
}

const TYPE_META: Record<string, { label: string; Icon: React.ElementType }> = {
  intruder:          { label: "After-Hours Intruder",    Icon: Siren },
  blacklist:         { label: "Blocked Person",          Icon: UserX },
  after_hours:       { label: "Outside Shift Hours",     Icon: Clock },
  restricted_area:   { label: "Restricted Area Entry",  Icon: Eye },
  vip:               { label: "VIP Arrival",             Icon: Bell },
  loitering:         { label: "Extended Stay",           Icon: Clock },
  spoof_attempt:     { label: "Fake Face Attempt",       Icon: ShieldOff },
  unknown_person:    { label: "Unknown Person",          Icon: HelpCircle },
  masked_face:       { label: "Face Covering",           Icon: Eye },
  suspicious_object: { label: "Suspicious Object",       Icon: Package },
};

const SEV_STYLE: Record<string, { bar: string; iconBg: string; badge: string }> = {
  high: {
    bar:    "bg-red-500",
    iconBg: "bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400",
    badge:  "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
  },
  medium: {
    bar:    "bg-amber-400",
    iconBg: "bg-amber-100 dark:bg-amber-900/50 text-amber-600 dark:text-amber-400",
    badge:  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400",
  },
  low: {
    bar:    "bg-blue-400",
    iconBg: "bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400",
    badge:  "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
  },
};

const SEV_LABEL: Record<string, string> = {
  high: "Urgent", medium: "Attention", low: "Info",
};

export default function ToastProvider() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    // Mark as leaving (triggers exit animation via CSS)
    setToasts(prev => prev.map(t => t.id === id ? { ...t, entering: false } : t));
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 350);
  }, []);

  useEffect(() => {
    const s = getSession();
    if (!s) return;

    const handle = connectAlertsWS(s.tenantId, s.token, (raw) => {
      const p = raw as Record<string, string | null | undefined>;
      if (p.type === "ping") return;
      const alertType = p.alert_type ?? p.type;
      if (!alertType || alertType === "ping") return;

      const id = `${Date.now()}-${Math.random()}`;
      const severity = (p.severity as Toast["severity"]) ?? "medium";

      const toast: Toast = {
        id,
        type: alertType,
        severity,
        message: p.message ?? "",
        entering: false,
      };

      setToasts(prev => [toast, ...prev].slice(0, 5));

      // Trigger enter animation on next tick
      requestAnimationFrame(() => {
        setToasts(prev => prev.map(t => t.id === id ? { ...t, entering: true } : t));
      });

      // Auto-dismiss
      const delay = severity === "high" ? 8000 : 5000;
      setTimeout(() => dismiss(id), delay);
    });

    return () => handle.close();
  }, [dismiss]);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed top-4 right-4 z-[200] flex flex-col gap-2 w-80 pointer-events-none"
      aria-live="polite"
    >
      {toasts.map(t => {
        const meta  = TYPE_META[t.type] ?? { label: t.type.replace(/_/g, " "), Icon: AlertTriangle };
        const style = SEV_STYLE[t.severity] ?? SEV_STYLE.low;
        const { Icon } = meta;

        return (
          <div
            key={t.id}
            className="pointer-events-auto"
            style={{
              transform: t.entering ? "translateX(0)" : "translateX(110%)",
              opacity:   t.entering ? 1 : 0,
              transition: "transform 0.35s cubic-bezier(0.34,1.56,0.64,1), opacity 0.3s ease",
            }}
          >
            <div className="relative overflow-hidden rounded-xl shadow-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
              {/* Severity bar */}
              <div className={`absolute left-0 top-0 bottom-0 w-1 ${style.bar}`} />

              <div className="flex items-start gap-3 pl-4 pr-3 py-3">
                {/* Icon */}
                <div className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center ${style.iconBg}`}>
                  <Icon size={16} />
                </div>

                {/* Text */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                    <span className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
                      {meta.label}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${style.badge}`}>
                      {SEV_LABEL[t.severity] ?? t.severity}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-300 leading-snug line-clamp-2">
                    {t.message}
                  </p>
                </div>

                {/* Dismiss */}
                <button
                  onClick={() => dismiss(t.id)}
                  className="flex-shrink-0 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>

              {/* Progress bar (auto-dismiss timer) */}
              <div
                className={`h-0.5 ${style.bar} opacity-40`}
                style={{
                  animation: `shrink ${t.severity === "high" ? 8 : 5}s linear forwards`,
                }}
              />
            </div>
          </div>
        );
      })}

      <style>{`
        @keyframes shrink {
          from { width: 100%; }
          to   { width: 0%; }
        }
      `}</style>
    </div>
  );
}
