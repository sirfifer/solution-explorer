import { useState, useMemo } from "react";
import { useArchStore } from "../store";
import type { Component, ComponentStatus } from "../types";
import { getWorstStatusLevel, type StatusLevel } from "../utils/status";

const CATEGORY_ICONS: Record<string, string> = {
  ci: "\u2699\uFE0F",
  security: "\uD83D\uDD12",
  deploy: "\uD83D\uDE80",
  test: "\uD83E\uDDEA",
  quality: "\u2728",
};

function getCategoryIcon(category: string): string {
  return CATEGORY_ICONS[category] || "\u26A0\uFE0F";
}

interface StatusGroup {
  category: string;
  icon: string;
  worstLevel: StatusLevel;
  errorCount: number;
  warningCount: number;
  infoCount: number;
  affectedComponents: Array<{ id: string; name: string }>;
}

function walkComponents(components: Component[], callback: (comp: Component) => void): void {
  for (const comp of components) {
    callback(comp);
    walkComponents(comp.children, callback);
  }
}

function collectStatusGroups(components: Component[]): StatusGroup[] {
  const groupMap = new Map<string, StatusGroup>();

  walkComponents(components, (comp) => {
    const statuses = comp.live_status?.statuses;
    if (!statuses) return;

    for (const status of Object.values(statuses)) {
      if (status.level === "ok") continue;

      const category = status.category.split(":")[0] || status.category;

      let group = groupMap.get(category);
      if (!group) {
        group = {
          category,
          icon: getCategoryIcon(category),
          worstLevel: "ok",
          errorCount: 0,
          warningCount: 0,
          infoCount: 0,
          affectedComponents: [],
        };
        groupMap.set(category, group);
      }

      if (status.level === "error") group.errorCount++;
      else if (status.level === "warning") group.warningCount++;
      else if (status.level === "info") group.infoCount++;

      if (!group.affectedComponents.some((c) => c.id === comp.id)) {
        group.affectedComponents.push({ id: comp.id, name: comp.name });
      }
    }
  });

  for (const group of groupMap.values()) {
    if (group.errorCount > 0) group.worstLevel = "error";
    else if (group.warningCount > 0) group.worstLevel = "warning";
    else if (group.infoCount > 0) group.worstLevel = "info";
  }

  const levelOrder: Record<string, number> = { error: 0, warning: 1, info: 2, ok: 3 };
  return Array.from(groupMap.values()).sort(
    (a, b) => (levelOrder[a.worstLevel] ?? 3) - (levelOrder[b.worstLevel] ?? 3)
  );
}

function getBannerColors(worstLevel: StatusLevel, darkMode: boolean): string {
  switch (worstLevel) {
    case "error":
      return darkMode
        ? "bg-red-950/20 border-b border-red-800/30 text-red-300"
        : "bg-red-50 border-b border-red-200 text-red-700";
    case "warning":
      return darkMode
        ? "bg-amber-950/20 border-b border-amber-800/30 text-amber-300"
        : "bg-amber-50 border-b border-amber-200 text-amber-700";
    default:
      return darkMode
        ? "bg-blue-950/20 border-b border-blue-800/30 text-blue-300"
        : "bg-blue-50 border-b border-blue-200 text-blue-700";
  }
}

export function StatusDashboard() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const navigateToComponent = useArchStore((s) => s.navigateToComponent);
  const [dismissed, setDismissed] = useState(false);

  const groups = useMemo(() => {
    if (!architecture) return [];
    return collectStatusGroups(architecture.components);
  }, [architecture]);

  if (dismissed || groups.length === 0) return null;

  const totalIssues = groups.reduce(
    (sum, g) => sum + g.errorCount + g.warningCount + g.infoCount,
    0
  );

  const worstOverall = groups[0]?.worstLevel ?? "info";

  return (
    <div className={`flex flex-col gap-1.5 px-4 py-2 text-xs shrink-0 ${getBannerColors(worstOverall, darkMode)}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="shrink-0">{"\u26A0\uFE0F"}</span>
          <span className="font-medium">
            {totalIssues} status {totalIssues === 1 ? "issue" : "issues"} detected
          </span>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className={`shrink-0 p-0.5 rounded ${
            darkMode ? "hover:bg-red-900/40 text-red-500" : "hover:bg-red-100 text-red-400"
          }`}
          title="Dismiss"
        >
          &#x2715;
        </button>
      </div>

      <div className="flex flex-wrap gap-3">
        {groups.map((group) => (
          <div key={group.category} className="flex items-center gap-1.5">
            <span>{group.icon}</span>
            <span className="font-medium">{group.category}:</span>
            {group.errorCount > 0 && (
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
                darkMode ? "bg-red-900/40 text-red-300" : "bg-red-100 text-red-700"
              }`}>
                {group.errorCount} error{group.errorCount !== 1 ? "s" : ""}
              </span>
            )}
            {group.warningCount > 0 && (
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
                darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700"
              }`}>
                {group.warningCount} warning{group.warningCount !== 1 ? "s" : ""}
              </span>
            )}
            {group.infoCount > 0 && (
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
                darkMode ? "bg-blue-900/40 text-blue-300" : "bg-blue-100 text-blue-700"
              }`}>
                {group.infoCount} info
              </span>
            )}
            {group.affectedComponents.map((comp) => (
              <button
                key={comp.id}
                onClick={() => navigateToComponent(comp.id)}
                className={`px-1.5 py-0.5 rounded text-[10px] underline-offset-2 hover:underline ${
                  darkMode ? "text-zinc-400 hover:text-zinc-200" : "text-zinc-500 hover:text-zinc-700"
                }`}
              >
                {comp.name}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
