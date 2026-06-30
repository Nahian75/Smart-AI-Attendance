"use client";
import { useEffect, useState } from "react";
import { Building2, MapPin } from "lucide-react";
import { api } from "@/lib/api";

interface OccupancyData { building: number; zones: Record<string, number> }

export default function OccupancyCards() {
  const [data, setData] = useState<OccupancyData>({ building: 0, zones: {} });
  const [error, setError] = useState(false);

  useEffect(() => {
    const load = () => api.occupancy().then((d) => { setData(d); setError(false); }).catch(() => setError(true));
    load();
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, []);

  if (error) return (
    <div className="glass rounded-xl p-4 text-center text-xs text-gray-400 dark:text-gray-500">
      Occupancy unavailable
    </div>
  );

  return (
    <div className="space-y-2">
      <div className="glass rounded-xl p-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <Building2 size={16} /> Building occupancy
        </div>
        <span className="text-2xl font-medium text-green-600 dark:text-green-400">{data.building}</span>
      </div>
      {Object.entries(data.zones).map(([zone, count]) => (
        <div key={zone} className="glass rounded-xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <MapPin size={13} /> {zone.replace(/_/g, " ")}
          </div>
          <span className="text-lg font-medium text-gray-900 dark:text-white">{count}</span>
        </div>
      ))}
    </div>
  );
}
