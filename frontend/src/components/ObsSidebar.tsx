import { useEffect, useState } from "react";
import { getObsStats } from "../api/client";
import type { ObsStats } from "../types/ops";

const SEV_COLORS: Record<string, string> = {
  critical: "text-red-400",
  high:     "text-orange-400",
  medium:   "text-yellow-400",
  low:      "text-green-400",
};

export default function ObsSidebar() {
  const [stats, setStats] = useState<ObsStats | null>(null);

  useEffect(() => {
    getObsStats().then(setStats).catch(() => {});
    const t = setInterval(
      () => getObsStats().then(setStats).catch(() => {}),
      30_000
    );
    return () => clearInterval(t);
  }, []);

  if (!stats || stats.total_runs === 0)
    return (
      <p className="text-xs text-gray-600 p-4 italic">No runs recorded yet.</p>
    );

  return (
    <div className="p-4 space-y-5 text-sm overflow-y-auto">
      <h2 className="font-bold text-gray-500 text-xs uppercase tracking-widest">
        Observability
      </h2>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        {(
          [
            ["Runs",         stats.total_runs],
            ["Avg latency",  `${stats.avg_latency_ms.toFixed(0)} ms`],
            ["P95 latency",  `${stats.p95_latency_ms.toFixed(0)} ms`],
            ["Mem hit rate", `${stats.memory_hit_rate.toFixed(0)}%`],
            ["Exec rate",    `${stats.exec_rate.toFixed(0)}%`],
            ["Avg revisions", stats.avg_revisions.toFixed(1)],
          ] as [string, string | number][]
        ).map(([label, val]) => (
          <div
            key={label}
            className="bg-gray-800 rounded-lg p-2.5 border border-gray-700"
          >
            <p className="text-xs text-gray-500">{label}</p>
            <p className="font-semibold text-gray-100 mt-0.5">{val}</p>
          </div>
        ))}
      </div>

      {/* Severity distribution */}
      <div>
        <p className="text-xs text-gray-500 mb-2 uppercase tracking-widest">
          Severity
        </p>
        <div className="space-y-1">
          {Object.entries(stats.severity_distribution).map(([k, v]) => (
            <div key={k} className="flex justify-between text-xs">
              <span className={`capitalize ${SEV_COLORS[k] ?? "text-gray-400"}`}>
                {k}
              </span>
              <span className="font-medium text-gray-300">{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Domain activation */}
      <div>
        <p className="text-xs text-gray-500 mb-2 uppercase tracking-widest">
          Domains
        </p>
        <div className="space-y-1">
          {Object.entries(stats.domain_activation).map(([k, v]) => (
            <div key={k} className="flex justify-between text-xs">
              <span className="capitalize text-gray-400">{k}</span>
              <span className="font-medium text-gray-300">{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
