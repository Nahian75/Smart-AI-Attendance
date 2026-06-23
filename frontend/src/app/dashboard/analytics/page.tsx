"use client";
import { useEffect, useState } from "react";
import { Building2, Users, TrendingUp, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import DashboardShell from "@/components/ui/DashboardShell";

function currentWeekMonday(): string {
  const d = new Date();
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

export default function AnalyticsPage() {
  const [buildingOccupancy, setBuildingOccupancy] = useState<number>(0);
  const [departmentOccupancy, setDepartmentOccupancy] = useState<Record<string, number>>({});
  const [shiftCompliance, setShiftCompliance] = useState<import("@/types").ComplianceRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [occ, dept, compliance] = await Promise.all([
          api.occupancy(),
          api.departmentOccupancy(),
          api.shiftCompliance(currentWeekMonday()),
        ]);
        setBuildingOccupancy(occ.building);
        setDepartmentOccupancy(dept);
        setShiftCompliance(compliance);
      } catch {
        // silently ignore — stale data stays displayed
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const getComplianceClass = (pct: number) => {
    if (pct >= 90) return "bg-green-50 text-green-700";
    if (pct >= 70) return "bg-amber-50 text-amber-700";
    return "bg-red-50 text-red-700";
  };

  if (loading) {
    return (
      <DashboardShell>
        <h2 className="text-lg font-medium">Analytics</h2>
        <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-8 text-center text-gray-400 dark:text-gray-500">Loading...</div>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell>
      <h2 className="text-lg font-medium">Analytics</h2>

      {/* Building-wide occupancy */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Building2 size={16} /> Building occupancy
          </div>
          <span className="text-3xl font-bold text-green-600">{buildingOccupancy}</span>
        </div>
      </div>

      {/* Department breakdown */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {Object.entries(departmentOccupancy).map(([dept, count]) => (
          <div key={dept} className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <Users size={14} /> {dept.replace(/_/g, " ")}
              </div>
              <span className="text-2xl font-bold text-blue-600">{count}</span>
            </div>
          </div>
        ))}
        {Object.keys(departmentOccupancy).length === 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-8 text-center text-gray-400 dark:text-gray-500 text-sm col-span-2">
            No department data available
          </div>
        )}
      </div>

      {/* Shift compliance */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700">
        <div className="px-4 py-3 border-b dark:border-gray-700 flex items-center gap-2">
          <Calendar size={16} className="text-amber-500" />
          <span className="text-sm font-medium">Shift compliance — this week</span>
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
            {shiftCompliance.map((r) => (
              <tr key={r.employee_id} className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                <td className="px-4 py-2 font-medium">{r.name}</td>
                <td className="px-4 py-2 text-gray-500">{r.dept || "—"}</td>
                <td className="px-4 py-2 text-right text-green-700">{r.on_time}</td>
                <td className="px-4 py-2 text-right text-amber-700">{r.late}</td>
                <td className="px-4 py-2 text-right">
                  <span className={`px-1.5 py-0.5 rounded text-xs ${getComplianceClass(r.on_time_pct)}`}>
                    {r.on_time_pct}%
                  </span>
                </td>
              </tr>
            ))}
            {shiftCompliance.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-4 text-center text-gray-400 dark:text-gray-500">No data yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </DashboardShell>
  );
}