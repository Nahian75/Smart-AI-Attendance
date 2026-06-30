"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ComplianceRow } from "@/types";

function getMonday(): string {
  const d = new Date();
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  d.setDate(diff);
  return d.toISOString().split("T")[0];
}

export default function ShiftComplianceTable() {
  const [rows, setRows] = useState<ComplianceRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.shiftCompliance(getMonday())
      .then(setRows)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="glass rounded-xl">
      <div className="px-4 py-3 border-b dark:border-gray-700 text-sm font-medium text-gray-900 dark:text-white">
        Shift compliance — this week
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-400 dark:text-gray-500 border-b dark:border-gray-700">
            <th className="text-left px-4 py-2">Employee</th>
            <th className="text-left px-4 py-2">Dept</th>
            <th className="text-right px-4 py-2">On-time</th>
            <th className="text-right px-4 py-2">Late</th>
            <th className="text-right px-4 py-2">%</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400 dark:text-gray-500">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-500" />
            </td></tr>
          )}
          {!loading && rows.map((r) => (
            <tr key={r.employee_id} className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
              <td className="px-4 py-2 font-medium text-gray-900 dark:text-white">{r.name}</td>
              <td className="px-4 py-2 text-gray-500 dark:text-gray-400">{r.dept || "—"}</td>
              <td className="px-4 py-2 text-right text-green-700 dark:text-green-400">{r.on_time}</td>
              <td className="px-4 py-2 text-right text-amber-700 dark:text-amber-400">{r.late}</td>
              <td className="px-4 py-2 text-right">
                <span className={`px-1.5 py-0.5 rounded text-xs ${
                  r.on_time_pct >= 90 ? "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                  : r.on_time_pct >= 70 ? "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400"
                  : "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400"}`}>
                  {r.on_time_pct}%
                </span>
              </td>
            </tr>
          ))}
          {!loading && rows.length === 0 && (
            <tr><td colSpan={5} className="px-4 py-4 text-center text-gray-400 dark:text-gray-500">No data yet</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
