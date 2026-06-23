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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-8 w-96 shadow-sm">
        <h1 className="text-2xl font-bold tracking-tight mb-1">
          <span className="text-gray-900 dark:text-white">Arg</span><span className="text-blue-600">us</span>
        </h1>
        <p className="text-xs font-medium tracking-widest uppercase text-gray-400 dark:text-gray-500 mb-6">
          AI Attendance Platform
        </p>
        <input className="w-full border dark:border-gray-600 rounded-lg px-3 py-2 mb-3 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400"
               value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
        <input className="w-full border dark:border-gray-600 rounded-lg px-3 py-2 mb-4 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400" type="password"
               value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        <button onClick={submit} disabled={loading}
                className="w-full bg-brand text-white rounded-lg py-2 text-sm font-medium hover:bg-brand-dark disabled:opacity-50">
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </div>
    </div>
  );
}
