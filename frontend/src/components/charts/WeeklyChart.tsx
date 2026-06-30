"use client";
import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import { api } from "@/lib/api";

export default function WeeklyChart() {
  const [data, setData] = useState<{ date: string; rate: number }[]>([]);
  useEffect(() => {
    api.weekly().then(setData).catch(() => {});
  }, []);
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-sm font-medium mb-3 text-gray-900 dark:text-white">Weekly attendance rate</p>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data}>
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "currentColor" }}
                 tickFormatter={(d) => new Date(d).toLocaleDateString([], { weekday: "short" })} />
          <YAxis tick={{ fontSize: 11, fill: "currentColor" }} domain={[0, 100]} />
          <Tooltip
            contentStyle={{ backgroundColor: "var(--tooltip-bg, #fff)", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
          <Bar dataKey="rate" fill="#1D9E75" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
