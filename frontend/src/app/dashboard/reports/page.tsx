"use client";
import { useState } from "react";
import { Download } from "lucide-react";
import { api } from "@/lib/api";
import DashboardShell from "@/components/ui/DashboardShell";
import ShiftComplianceTable from "@/components/charts/ShiftComplianceTable";

export default function ReportsPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  return (
    <DashboardShell>
      <h2 className="text-lg font-medium mb-4">Reports</h2>
      <div className="glass rounded-xl p-4 mb-4">
        <p className="text-sm font-medium mb-3 text-gray-900 dark:text-white">Monthly attendance CSV export</p>
        <div className="flex items-center gap-3">
          <select value={year} onChange={(e) => setYear(+e.target.value)}
                  className="border dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
            {Array.from({ length: 5 }, (_, i) => now.getFullYear() - 2 + i).map((y) => <option key={y}>{y}</option>)}
          </select>
          <select value={month} onChange={(e) => setMonth(+e.target.value)}
                  className="border dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>{new Date(2025, m - 1).toLocaleString("default", { month: "long" })}</option>
            ))}
          </select>
          <a href={api.monthlyCsvUrl(year, month)}
             className="flex items-center gap-1.5 text-sm bg-brand text-white px-3 py-1.5 rounded-lg hover:bg-brand-dark" download>
            <Download size={14} /> Download CSV
          </a>
        </div>
      </div>
      <ShiftComplianceTable />
    </DashboardShell>
  );
}
