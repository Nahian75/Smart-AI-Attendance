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

const SEV_META: Record<string, { label: string; card: string; iconBg: string; badge: string; accent: string }> = {
  high: {
    label:  "Urgent",
    card:   "border-l-4 border-red-400 bg-white dark:bg-gray-800/80 border-t border-r border-b border-t-red-200 border-r-red-200 border-b-red-200 dark:border-t-red-800/40 dark:border-r-red-800/40 dark:border-b-red-800/40",
    iconBg: "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400",
    badge:  "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
    accent: "text-red-500",
  },
  medium: {
    label:  "Attention",
    card:   "border-l-4 border-amber-400 bg-white dark:bg-gray-800/80 border-t border-r border-b border-t-amber-200 border-r-amber-200 border-b-amber-200 dark:border-t-amber-800/40 dark:border-r-amber-800/40 dark:border-b-amber-800/40",
    iconBg: "bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400",
    badge:  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400",
    accent: "text-amber-500",
  },
  low: {
    label:  "Info",
    card:   "border-l-4 border-blue-300 bg-white dark:bg-gray-800/80 border-t border-r border-b border-t-blue-200 border-r-blue-200 border-b-blue-200 dark:border-t-blue-800/40 dark:border-r-blue-800/40 dark:border-b-blue-800/40",
    iconBg: "bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400",
    badge:  "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
    accent: "text-blue-500",
  },
};

function AlertCard({ a, onAck, canAck }: { a: AlertItem; onAck: (id: string) => void; canAck: boolean }) {
  const meta = TYPE_META[a.type] ?? { label: a.type.replace(/_/g, " "), Icon: AlertTriangle };
  const sev  = SEV_META[a.severity] ?? SEV_META.low;
  const { Icon } = meta;

  return (
    <div className={`flex flex-wrap sm:flex-nowrap gap-3 sm:gap-4 rounded-xl shadow-sm p-4 transition-opacity ${sev.card} ${a.is_acknowledged ? "opacity-55" : ""}`}>
      <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${sev.iconBg}`}>
        <Icon size={18} />
      </div>

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

      {a.snapshot_url && (
        <img
          src={a.snapshot_url.startsWith("http") ? a.snapshot_url : `${API_BASE}${a.snapshot_url}`}
          alt="snapshot"
          className="flex-shrink-0 w-14 h-14 rounded-lg object-cover border dark:border-gray-700"
          onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
        />
      )}

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

function Section({
  title, icon: Icon, accentClass, count, children,
}: {
  title: string;
  icon: React.ElementType;
  accentClass: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} className={accentClass} />
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">{title}</span>
        {count > 0 && (
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            accentClass.includes("red")
              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
              : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
          }`}>
            {count} pending
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

export default function SecurityAlertsPage() {
  const { can } = useRole();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [filter, setFilter] = useState<"all" | "unacked">("unacked");

  useEffect(() => {
    api.alerts(filter === "unacked").then(setAlerts).catch(() => {});
  }, [filter]);

  async function ack(id: string) {
    await api.acknowledgeAlert(id).catch(() => {});
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_acknowledged: true } : a));
  }

  const securityAlerts = alerts.filter(a => a.severity === "high" && a.type !== "loitering");
  const loiteringAlerts = alerts.filter(a => a.type === "loitering");
  const unackedSecurity = securityAlerts.filter(a => !a.is_acknowledged).length;
  const unackedLoitering = loiteringAlerts.filter(a => !a.is_acknowledged).length;

  return (
    <DashboardShell>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-red-100 dark:bg-red-900/40 flex items-center justify-center">
            <ShieldAlert size={18} className="text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-gray-900 dark:text-white leading-tight">Security Alerts</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {unackedSecurity + unackedLoitering > 0
                ? `${unackedSecurity + unackedLoitering} requiring attention`
                : "All clear"}
            </p>
          </div>
        </div>

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

      {/* Security incidents */}
      <Section title="Security Incidents" icon={AlertTriangle} accentClass="text-red-500" count={unackedSecurity}>
        {securityAlerts.length === 0 ? (
          <div className="glass rounded-xl p-8 flex flex-col items-center gap-3 text-gray-400 dark:text-gray-500">
            <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
              <ShieldAlert size={18} className="opacity-40" />
            </div>
            <p className="text-sm">No security incidents</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {securityAlerts.map(a => (
              <AlertCard key={a.id} a={a} onAck={ack} canAck={can("security")} />
            ))}
          </div>
        )}
      </Section>

      {/* Loitering */}
      <Section title="Loitering Monitoring" icon={Clock} accentClass="text-amber-500" count={unackedLoitering}>
        {loiteringAlerts.length === 0 ? (
          <div className="glass rounded-xl p-8 flex flex-col items-center gap-3 text-gray-400 dark:text-gray-500">
            <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
              <Clock size={18} className="opacity-40" />
            </div>
            <p className="text-sm">No loitering alerts</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {loiteringAlerts.map(a => (
              <AlertCard key={a.id} a={a} onAck={ack} canAck={can("security")} />
            ))}
          </div>
        )}
      </Section>
    </DashboardShell>
  );
}
