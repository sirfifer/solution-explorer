import { useArchStore } from "../../store";
import { formatRelativeTime } from "../../utils/layout";
import type { AdminSummary } from "../../types";

interface HealthTabProps {
  adminData: AdminSummary | null;
  loading: boolean;
}

export function HealthTab({ adminData, loading }: HealthTabProps) {
  const { darkMode, liveConfig, liveMonitorStatus, architecture } = useArchStore();

  // The currently-loaded architecture already carries its own authoritative
  // stats.total_components. When the live admin summary reports a different
  // count for the same repo, showing both numbers as if they agreed would be
  // exactly the silent self-contradiction a reviewer once had to catch by
  // hand (comprehension-study finding). This only compares when there is
  // exactly one repo in the summary, since that is the population
  // stats.total_components describes; multi-repo per-repo breakdowns are not
  // a matching population and are left uncompared.
  const loadedTotal = architecture?.stats?.total_components;
  const componentCountMismatch =
    adminData?.repos?.length === 1 &&
    typeof loadedTotal === "number" &&
    loadedTotal !== adminData.repos[0].component_count;

  if (loading && !adminData) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        Loading health data...
      </div>
    );
  }

  const statusColor = (status: string) => {
    switch (status) {
      case "ok": return darkMode ? "text-emerald-400" : "text-emerald-600";
      case "stale": return darkMode ? "text-amber-400" : "text-amber-600";
      case "error": return darkMode ? "text-red-400" : "text-red-600";
      default: return darkMode ? "text-zinc-400" : "text-zinc-500";
    }
  };

  const statusBg = (status: string) => {
    switch (status) {
      case "ok": return darkMode ? "bg-emerald-500/15" : "bg-emerald-100";
      case "stale": return darkMode ? "bg-amber-500/15" : "bg-amber-100";
      case "error": return darkMode ? "bg-red-500/15" : "bg-red-100";
      default: return darkMode ? "bg-zinc-800" : "bg-zinc-100";
    }
  };

  const monitorStatusLabel: Record<string, string> = {
    idle: "Idle",
    polling: "Polling",
    updating: "Updating",
    error: "Error",
    paused: "Paused",
  };

  return (
    <div className="p-4 space-y-5">
      {/* Repo status table */}
      <div>
        <h3 className={`text-xs font-semibold mb-2 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
          Repositories
        </h3>
        {adminData?.repos && adminData.repos.length > 0 ? (
          <div className={`rounded-lg border overflow-hidden ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
            <table className="w-full text-xs">
              <thead>
                <tr className={darkMode ? "bg-zinc-800/50" : "bg-zinc-50"}>
                  <th className={`text-left px-3 py-2 font-medium ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>Name</th>
                  <th className={`text-left px-3 py-2 font-medium ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>Last Update</th>
                  <th className={`text-right px-3 py-2 font-medium ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>Version</th>
                  <th className={`text-right px-3 py-2 font-medium ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>Components</th>
                  <th className={`text-right px-3 py-2 font-medium ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>Status</th>
                </tr>
              </thead>
              <tbody>
                {adminData.repos.map((repo) => (
                  <tr key={repo.name} className={`border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
                    <td className={`px-3 py-2 font-medium ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{repo.name}</td>
                    <td className={`px-3 py-2 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
                      {formatRelativeTime(repo.last_update)}
                    </td>
                    <td className={`px-3 py-2 text-right ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>v{repo.version}</td>
                    <td className={`px-3 py-2 text-right ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
                      {repo.component_count}
                      {componentCountMismatch && (
                        <span
                          title={`The currently loaded architecture reports ${loadedTotal} components, not ${repo.component_count}. This dashboard's number came from a separate live data file and disagrees with what you are viewing.`}
                          className={`ml-1 ${darkMode ? "text-amber-400" : "text-amber-600"}`}
                        >
                          ⚠
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${statusColor(repo.status)} ${statusBg(repo.status)}`}>
                        {repo.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {componentCountMismatch && (
              <div className={`px-3 py-2 text-[11px] border-t ${darkMode ? "border-zinc-800 bg-amber-500/10 text-amber-300" : "border-zinc-200 bg-amber-50 text-amber-700"}`}>
                Component count mismatch: the loaded architecture reports {loadedTotal} components, but this live summary reports {adminData.repos[0].component_count}. The two were generated separately and may reflect different data.
              </div>
            )}
          </div>
        ) : (
          <div className={`text-xs py-4 text-center ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            No repository data available
          </div>
        )}
      </div>

      {/* Connection info */}
      <div>
        <h3 className={`text-xs font-semibold mb-2 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
          Connection
        </h3>
        <div className={`rounded-lg border p-3 space-y-2 ${darkMode ? "border-zinc-800 bg-zinc-800/30" : "border-zinc-200 bg-zinc-50"}`}>
          <div className="flex items-center justify-between text-xs">
            <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>Monitor Status</span>
            <span className={`font-medium ${
              liveMonitorStatus === "error"
                ? darkMode ? "text-red-400" : "text-red-600"
                : liveMonitorStatus === "polling"
                  ? darkMode ? "text-emerald-400" : "text-emerald-600"
                  : darkMode ? "text-zinc-300" : "text-zinc-700"
            }`}>
              {monitorStatusLabel[liveMonitorStatus] || liveMonitorStatus}
            </span>
          </div>
          {liveConfig && (
            <>
              <div className="flex items-center justify-between text-xs">
                <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>Backend Mode</span>
                <span className={`font-medium ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{liveConfig.backend_mode}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>Data URL</span>
                <span className={`font-medium truncate ml-4 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{liveConfig.data_url}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>Polling Interval</span>
                <span className={`font-medium ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{liveConfig.polling.default_interval_seconds}s</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* GitHub mode note */}
      {liveConfig?.backend_mode === "github" && (
        <div className={`rounded-lg border p-3 text-xs ${
          darkMode
            ? "border-zinc-700 bg-zinc-800/50 text-zinc-400"
            : "border-zinc-200 bg-zinc-50 text-zinc-500"
        }`}>
          <span className={`font-medium ${darkMode ? "text-zinc-300" : "text-zinc-600"}`}>GitHub Pages mode</span>
          {" "}&mdash; Data served from GitHub Pages with ~10 minute CDN cache.
          Polling interval should be set accordingly.
        </div>
      )}
    </div>
  );
}
