"use client";
import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { api } from "@/lib/api";

export default function HourlyChart({ date }: { date?: string }) {
  const [data, setData] = useState<{ hour: number; entries: number; exits: number }[]>([]);

  useEffect(() => {
    api.hourly(date).then(setData).catch(() => {});
  }, [date]);

  const active = data.filter((d) => d.entries > 0 || d.exits > 0);
  const display = active.length ? data.filter((d) => d.hour >= 6 && d.hour <= 22) : data.slice(7, 20);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4">
      <p className="text-sm font-medium mb-3 text-gray-900 dark:text-white">Hourly entry & exit</p>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={display} barSize={10}>
          <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "currentColor" }}
                 tickFormatter={(h: number) => `${h}:00`} />
          <YAxis tick={{ fontSize: 10, fill: "currentColor" }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ backgroundColor: "var(--tooltip-bg, #fff)", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }}
            formatter={(v: number, name: string) => [v, name === "entries" ? "Entries" : "Exits"]} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="entries" fill="#1D9E75" radius={[3, 3, 0, 0]} name="Entries" />
          <Bar dataKey="exits"   fill="#9FE1CB" radius={[3, 3, 0, 0]} name="Exits" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
