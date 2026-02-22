import type { ComponentStatus } from "../types";

export type StatusLevel = "ok" | "warning" | "error" | "info";

export function getWorstStatusLevel(statuses: Record<string, ComponentStatus>): StatusLevel {
  let worst: StatusLevel = "ok";
  for (const status of Object.values(statuses)) {
    if (status.level === "error") return "error";
    if (status.level === "warning") worst = "warning";
    if (status.level === "info" && worst === "ok") worst = "info";
  }
  return worst;
}

export function getStatusSummary(statuses: Record<string, ComponentStatus>): string {
  const counts = { error: 0, warning: 0, info: 0 };
  for (const status of Object.values(statuses)) {
    if (status.level in counts) {
      counts[status.level as keyof typeof counts]++;
    }
  }
  const parts: string[] = [];
  if (counts.error > 0) parts.push(`${counts.error} error${counts.error !== 1 ? "s" : ""}`);
  if (counts.warning > 0) parts.push(`${counts.warning} warning${counts.warning !== 1 ? "s" : ""}`);
  if (counts.info > 0) parts.push(`${counts.info} info`);
  return parts.join(", ") || "All OK";
}

export function getStatusDotClasses(level: StatusLevel): string {
  switch (level) {
    case "error": return "bg-red-500 animate-pulse";
    case "warning": return "bg-amber-500";
    case "info": return "bg-blue-500";
    default: return "bg-green-500";
  }
}
