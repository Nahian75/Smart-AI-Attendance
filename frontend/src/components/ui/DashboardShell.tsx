"use client";
import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  ScanEye, BarChart3, Users, Video, ShieldAlert, LogOut,
  TrendingUp, FileText, KeyRound, X, Eye, EyeOff, Settings, Clock, Film,
} from "lucide-react";
import { clearSession } from "@/lib/auth";
import { useRole, ROLE_LABELS, ROLE_COLORS } from "@/lib/rbac";
import { api } from "@/lib/api";
import ThemeToggle from "@/components/ui/ThemeToggle";

const NAV = [
  { label: "Overview",        icon: BarChart3,   href: "/dashboard" },
  { label: "Employees",       icon: Users,        href: "/dashboard/employees" },
  { label: "Cameras",         icon: Video,        href: "/dashboard/cameras" },
  { label: "Detection Log",   icon: Film,         href: "/dashboard/detection-log" },
  { label: "Alerts",          icon: ShieldAlert,  href: "/dashboard/alerts" },
  { label: "Security Alerts", icon: ShieldAlert,  href: "/dashboard/security-alerts" },
  { label: "Analytics",       icon: TrendingUp,   href: "/dashboard/analytics" },
  { label: "Shifts",          icon: Clock,        href: "/dashboard/shifts" },
  { label: "Reports",         icon: FileText,     href: "/dashboard/reports" },
];

// ── Change-password modal ─────────────────────────────────────────────────────
function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent]     = useState("");
  const [next, setNext]           = useState("");
  const [confirm, setConfirm]     = useState("");
  const [showCur, setShowCur]     = useState(false);
  const [showNew, setShowNew]     = useState(false);
  const [busy, setBusy]           = useState(false);
  const [error, setError]         = useState("");
  const [success, setSuccess]     = useState(false);

  async function submit() {
    setError("");
    if (next.length < 8) { setError("New password must be at least 8 characters."); return; }
    if (next !== confirm)  { setError("New passwords do not match."); return; }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setSuccess(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Failed to change password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <KeyRound size={16} className="text-blue-600" /> Change Password
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {success ? (
            <div className="text-center py-4">
              <div className="text-green-600 dark:text-green-400 font-medium mb-1">Password changed successfully.</div>
              <p className="text-sm text-gray-500 dark:text-gray-400">You will need to log in again on other devices.</p>
              <button onClick={onClose}
                className="mt-4 px-5 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
                Close
              </button>
            </div>
          ) : (
            <>
              <PwField label="Current password" value={current} onChange={setCurrent} show={showCur} onToggle={() => setShowCur(v => !v)} />
              <PwField label="New password" value={next} onChange={setNext} show={showNew} onToggle={() => setShowNew(v => !v)}
                hint="Minimum 8 characters" />
              <PwField label="Confirm new password" value={confirm} onChange={setConfirm} show={showNew} onToggle={() => setShowNew(v => !v)} />

              {error && (
                <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{error}</p>
              )}

              <div className="flex gap-2 pt-1">
                <button onClick={onClose}
                  className="flex-1 border dark:border-gray-600 rounded-lg py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                  Cancel
                </button>
                <button onClick={submit} disabled={busy || !current || !next || !confirm}
                  className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                  {busy ? "Saving…" : "Change Password"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function PwField({ label, value, onChange, show, onToggle, hint }: {
  label: string; value: string; onChange: (v: string) => void;
  show: boolean; onToggle: () => void; hint?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full border dark:border-gray-600 rounded-lg px-3 py-2 text-sm pr-10
                     bg-white dark:bg-gray-700 text-gray-900 dark:text-white
                     focus:outline-none focus:ring-2 focus:ring-blue-500"
          autoComplete="new-password"
        />
        <button type="button" onClick={onToggle}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
      {hint && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{hint}</p>}
    </div>
  );
}

// ── Shell ─────────────────────────────────────────────────────────────────────
export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const router   = useRouter();
  const pathname = usePathname();
  const [showPwModal, setShowPwModal] = useState(false);
  const { role, can } = useRole();

  const roleLabel = ROLE_LABELS[role] ?? role;
  const roleColor = ROLE_COLORS[role] ?? ROLE_COLORS.viewer;

  function isActive(href: string) {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  }

  return (
    <div className="flex min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* ── Sidebar ── */}
      <aside className="w-52 bg-white dark:bg-gray-800 border-r dark:border-gray-700 p-3 flex flex-col gap-0.5 flex-shrink-0">
        <div className="flex items-center gap-2 px-2 py-3 mb-1 font-semibold text-gray-900 dark:text-white">
          <ScanEye className="text-blue-600" size={20} />
          <span className="font-bold tracking-tight">
            Arg<span className="text-blue-600">us</span>
          </span>
        </div>

        {/* Role badge */}
        <div className="px-2 mb-2">
          <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${roleColor}`}>
            {roleLabel}
          </span>
        </div>

        {/* Nav links */}
        {NAV.map((n) => (
          <button key={n.label} onClick={() => router.push(n.href)}
            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm w-full text-left transition-colors ${
              isActive(n.href)
                ? "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium"
                : "text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"
            }`}>
            <n.icon size={15} />
            {n.label}
          </button>
        ))}

        {/* Admin link — only visible to admin+ */}
        {can("admin") && (
          <button onClick={() => router.push("/dashboard/admin")}
            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm w-full text-left transition-colors ${
              isActive("/dashboard/admin")
                ? "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium"
                : "text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"
            }`}>
            <Settings size={15} />
            Admin
          </button>
        )}

        {/* Footer */}
        <div className="mt-auto pt-2 border-t dark:border-gray-700 space-y-0.5">
          <button onClick={() => setShowPwModal(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-gray-400
                       hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg w-full transition-colors">
            <KeyRound size={15} /> Change Password
          </button>

          <div className="px-3 py-1.5 flex items-center justify-between">
            <span className="text-xs text-gray-400 dark:text-gray-500">Theme</span>
            <ThemeToggle />
          </div>

          <button onClick={() => { clearSession(); router.push("/login"); }}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-gray-400
                       hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg w-full transition-colors">
            <LogOut size={15} /> Sign out
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 p-6 overflow-y-auto space-y-4">
        {children}
      </main>

      {showPwModal && <ChangePasswordModal onClose={() => setShowPwModal(false)} />}
    </div>
  );
}
