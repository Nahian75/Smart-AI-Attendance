"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { saveSession } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setError("");
    try {
      const res = await api.login(email, password);
      saveSession(res.access_token, res.tenant_id, res.role);
      router.push("/dashboard");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("429") || msg.toLowerCase().includes("rate limit")) {
        setError("Too many attempts — please wait a moment and try again.");
      } else if (msg.includes("401") || msg.includes("403")) {
        setError("Invalid email or password.");
      } else {
        setError("Could not reach the server. Check your connection.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* ── Left branding panel ── */}
      <div className="hidden lg:flex w-1/2 flex-col justify-between p-12
                      bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 relative overflow-hidden">

        {/* Background glow orbs */}
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-indigo-500/15 rounded-full blur-3xl pointer-events-none" />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/20 border border-blue-400/30 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6 text-blue-400" stroke="currentColor" strokeWidth={1.5}>
              <circle cx="12" cy="12" r="3" fill="currentColor" />
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </div>
          <span className="text-white font-bold text-xl tracking-tight">
            Ocu<span className="text-blue-400">lus</span>
          </span>
        </div>

        {/* Hero text */}
        <div className="relative z-10 space-y-6">
          <div>
            <h1 className="text-5xl font-bold text-white leading-tight tracking-tight">
              Intelligent<br />
              <span className="text-blue-400">Vision</span><br />
              Secure Operation
            </h1>
            <p className="mt-4 text-slate-400 text-lg leading-relaxed max-w-sm">
              Real-time face recognition, behavioural analytics, and smart alerting — all in one unified platform.
            </p>
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2">
            {["Face Recognition", "Liveness Detection", "Bag Detection", "Live Alerts", "Shift Management"].map(f => (
              <span key={f}
                className="text-xs px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-slate-300">
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* Footer tagline */}
        <p className="relative z-10 text-slate-600 text-xs tracking-widest uppercase">
          Always Watching. Always Accurate.
        </p>
      </div>

      {/* ── Right login panel ── */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12
                      bg-gradient-to-br from-slate-50 via-blue-50/30 to-indigo-50/40
                      dark:from-slate-950 dark:via-blue-950/40 dark:to-indigo-950/30">

        {/* Mobile logo (shown only on small screens) */}
        <div className="flex items-center gap-2 mb-10 lg:hidden">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-white" stroke="currentColor" strokeWidth={1.5}>
              <circle cx="12" cy="12" r="3" fill="currentColor" />
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </div>
          <span className="font-bold text-xl text-gray-900 dark:text-white">
            Ocu<span className="text-blue-600">lus</span>
          </span>
        </div>

        <div className="w-full max-w-sm">
          {/* Header */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Welcome back</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Sign in to your Oculus workspace</p>
          </div>

          {/* Form card */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl shadow-black/5 dark:shadow-black/40
                          border border-gray-100 dark:border-white/[0.06] p-8 space-y-5">

            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={e => e.key === "Enter" && submit()}
                placeholder="you@company.com"
                className="w-full rounded-xl border border-gray-200 dark:border-white/[0.08]
                           bg-gray-50 dark:bg-white/[0.04]
                           text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600
                           px-4 py-3 text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/60
                           transition-all" />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={e => e.key === "Enter" && submit()}
                placeholder="••••••••"
                className="w-full rounded-xl border border-gray-200 dark:border-white/[0.08]
                           bg-gray-50 dark:bg-white/[0.04]
                           text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600
                           px-4 py-3 text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/60
                           transition-all" />
            </div>

            {error && (
              <div className="rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40
                              px-4 py-3 text-sm text-red-700 dark:text-red-400">
                {error}
              </div>
            )}

            <button
              onClick={submit}
              disabled={loading || !email || !password}
              className="w-full rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800
                         disabled:opacity-40 disabled:cursor-not-allowed
                         text-white font-medium py-3 text-sm
                         transition-all shadow-lg shadow-blue-600/25
                         flex items-center justify-center gap-2">
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Signing in…
                </>
              ) : (
                "Sign in to Oculus"
              )}
            </button>
          </div>

          {/* Footer */}
          <p className="text-center text-xs text-gray-400 dark:text-gray-600 mt-6">
            Oculus Intelligent Vision &mdash; v1.1
          </p>
        </div>
      </div>
    </div>
  );
}
