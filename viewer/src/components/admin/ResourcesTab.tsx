import { useArchStore } from "../../store";
import type { AdminSummary } from "../../types";

interface ResourcesTabProps {
  adminData: AdminSummary | null;
  loading: boolean;
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
