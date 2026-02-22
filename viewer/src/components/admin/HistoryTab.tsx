import { useMemo } from "react";
import { useArchStore } from "../../store";
import type { AdminSummary } from "../../types";

interface HistoryTabProps {
  adminData: AdminSummary | null;
  loading: boolean;
}

export function HistoryTab({ adminData, loading }: HistoryTabProps) {
  const { darkMode } = useArchStore();

  const { days, maxCount } = useMemo(() => {
    const counts = adminData?.daily_counts ?? {};
    const entries = Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
    const max = entries.reduce((m, [, v]) => Math.max(m, v), 0);
    return { days: entries, maxCount: max };
  }, [adminData]);

  if (loading && !adminData) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        Loading history data...
      </div>
    );
  }

  if (days.length === 0) {
    return (
      <div className={`flex items-center justify-center py-12 text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        No update history available
      </div>
    );
  }

  const totalUpdates = days.reduce((sum, [, count]) => sum + count, 0);

  return (
    <div className="p-4 space-y-4">
      {/* Stats summary */}
      <div className="flex items-center gap-4">
        <div className={`text-xs ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
          <span className={`font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{totalUpdates}</span> total updates
        </div>
        <div className={`text-xs ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
          <span className={`font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{days.length}</span> days tracked
        </div>
        {adminData?.generated_at && (
          <div className={`text-xs ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
            as of {new Date(adminData.generated_at).toLocaleDateString()}
          </div>
        )}
      </div>

      {/* Bar chart */}
      <div className="space-y-1">
        {days.map(([date, count]) => {
          const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
          const dayLabel = new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
          return (
            <div key={date} className="flex items-center gap-2 text-[10px]">
              <span className={`w-24 text-right shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                {dayLabel}
              </span>
              <div className={`flex-1 h-4 rounded overflow-hidden ${darkMode ? "bg-zinc-800" : "bg-zinc-100"}`}>
                {count > 0 && (
                  <div
                    className={`h-full rounded ${darkMode ? "bg-blue-500/40" : "bg-blue-200"}`}
                    style={{ width: `${pct}%` }}
                  />
                )}
              </div>
              <span className={`w-6 text-right shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
