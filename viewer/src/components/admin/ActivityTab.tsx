import { useArchStore } from "../../store";
import { formatRelativeTime } from "../../utils/layout";
import type { AdminSummary } from "../../types";

interface ActivityTabProps {
  adminData: AdminSummary | null;
  loading: boolean;
}

export function ActivityTab({ adminData, loading }: ActivityTabProps) {
  const { darkMode } = useArchStore();

  if (loading && !adminData) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        Loading activity data...
      </div>
    );
  }

  const activities = adminData?.activity ?? [];

  if (activities.length === 0) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        No activity recorded yet
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="space-y-1">
        {activities.map((entry, i) => {
          const diff = entry.diff_summary;
          return (
            <div
              key={`${entry.commit_sha}-${i}`}
              className={`flex items-start gap-3 px-3 py-2.5 rounded-lg ${
                darkMode ? "hover:bg-zinc-800/50" : "hover:bg-zinc-50"
              }`}
            >
              {/* Time */}
              <span className={`text-[10px] shrink-0 w-16 pt-0.5 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                {formatRelativeTime(entry.timestamp)}
              </span>

              {/* Commit info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <code className={`text-[10px] px-1 py-0.5 rounded font-mono ${
                    darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"
                  }`}>
                    {entry.commit_sha.slice(0, 7)}
                  </code>
                  <span className={`text-xs truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                    {entry.commit_message}
                  </span>
                </div>

                {/* Diff badges */}
                <div className="flex items-center gap-1.5 mt-1">
                  {diff.components_added > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      darkMode ? "bg-emerald-500/15 text-emerald-400" : "bg-emerald-100 text-emerald-700"
                    }`}>
                      +{diff.components_added} added
                    </span>
                  )}
                  {diff.components_modified > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      darkMode ? "bg-amber-500/15 text-amber-400" : "bg-amber-100 text-amber-700"
                    }`}>
                      ~{diff.components_modified} modified
                    </span>
                  )}
                  {diff.components_removed > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      darkMode ? "bg-red-500/15 text-red-400" : "bg-red-100 text-red-700"
                    }`}>
                      -{diff.components_removed} removed
                    </span>
                  )}
                  {diff.files_changed > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-400"
                    }`}>
                      {diff.files_changed} files
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
