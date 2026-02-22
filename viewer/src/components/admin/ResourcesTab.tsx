import { useArchStore } from "../../store";
import type { AdminSummary } from "../../types";

interface ResourcesTabProps {
  adminData: AdminSummary | null;
  loading: boolean;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function usageBarColor(pct: number, dark: boolean): string {
  if (pct >= 80) return dark ? "bg-red-500/60" : "bg-red-300";
  if (pct >= 50) return dark ? "bg-amber-500/50" : "bg-amber-200";
  return dark ? "bg-emerald-500/40" : "bg-emerald-200";
}

function usageLabelColor(pct: number, dark: boolean): string {
  if (pct >= 80) return dark ? "text-red-400" : "text-red-600";
  if (pct >= 50) return dark ? "text-amber-400" : "text-amber-600";
  return dark ? "text-emerald-400" : "text-emerald-600";
}

export function ResourcesTab({ adminData, loading }: ResourcesTabProps) {
  const { darkMode, liveConfig } = useArchStore();

  if (loading && !adminData) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        Loading resource data...
      </div>
    );
  }

  const usage = adminData?.resource_usage;

  if (!usage) {
    return (
      <div className="p-4 space-y-4">
        <div className={`rounded-lg border p-4 text-center ${
          darkMode ? "border-zinc-800 bg-zinc-800/30" : "border-zinc-200 bg-zinc-50"
        }`}>
          <div className={`text-sm mb-1 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
            Resource Monitoring
          </div>
          <div className={`text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            {liveConfig?.backend_mode === "cloudflare" || liveConfig?.backend_mode === "hybrid"
              ? "Cloudflare resource usage data will be available once the backend infrastructure is deployed."
              : "Resource monitoring is available with the Cloudflare backend."}
          </div>
          {liveConfig?.worker_url && (
            <div className={`text-[10px] mt-2 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              Worker: {liveConfig.worker_url}
            </div>
          )}
        </div>
      </div>
    );
  }

  const metrics = [
    { label: "Worker Requests", period: "daily", value: usage.worker_requests, limit: usage.limits.worker_requests_per_day },
    { label: "D1 Reads", period: "daily", value: usage.d1_reads, limit: usage.limits.d1_reads_per_day },
    { label: "D1 Writes", period: "daily", value: usage.d1_writes, limit: usage.limits.d1_writes_per_day },
    { label: "R2 Reads", period: "monthly", value: usage.r2_reads, limit: usage.limits.r2_reads_per_month },
    { label: "R2 Writes", period: "monthly", value: usage.r2_writes, limit: usage.limits.r2_writes_per_month },
  ];

  return (
    <div className="p-4 space-y-5">
      <h3 className={`text-xs font-semibold ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
        Cloudflare Free Tier Usage
      </h3>

      <div className="space-y-3">
        {metrics.map((m) => {
          const pct = m.limit > 0 ? Math.min((m.value / m.limit) * 100, 100) : 0;
          return (
            <div key={m.label}>
              <div className="flex items-center justify-between mb-1">
                <span className={`text-[11px] ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
                  {m.label}{" "}
                  <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    ({m.period})
                  </span>
                </span>
                <span className={`text-[11px] font-medium ${usageLabelColor(pct, darkMode)}`}>
                  {pct.toFixed(0)}%
                </span>
              </div>
              <div className={`h-3 rounded overflow-hidden ${darkMode ? "bg-zinc-800" : "bg-zinc-100"}`}>
                {m.value > 0 && (
                  <div
                    className={`h-full rounded ${usageBarColor(pct, darkMode)}`}
                    style={{ width: `${Math.max(pct, 1)}%` }}
                  />
                )}
              </div>
              <div className={`text-[10px] mt-0.5 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                {formatNumber(m.value)} / {formatNumber(m.limit)}
              </div>
            </div>
          );
        })}
      </div>

      {liveConfig?.worker_url && (
        <div className={`rounded-lg border p-3 text-xs ${
          darkMode ? "border-zinc-800 bg-zinc-800/30" : "border-zinc-200 bg-zinc-50"
        }`}>
          <div className="flex items-center justify-between">
            <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>Worker</span>
            <span className={`font-medium truncate ml-4 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
              {liveConfig.worker_url}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
