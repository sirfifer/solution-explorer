import { useEffect } from "react";
import type { Component, ActivityComponent } from "../types";
import { useArchStore } from "../store";
import { ROLE_META, getRoleBadgeColors, formatRelativeTime } from "../utils/layout";

// The rationale layer (invariant I13): the "colleague stand-in" context a reader
// with no colleague to ask would want. It surfaces whatever of ownership, last
// change, churn, originating commit/PR, and AI intent the dataset carries, and
// renders nothing when none is present, so it degrades cleanly on datasets
// without the git-activity pass (P5-4) or without AI enrichment.

export interface RationaleView {
  author?: string;
  lastChange?: string;
  churn?: number;
  commit?: string;
  pr?: string;
  role?: string;
  hasAiIntent?: boolean;
  aiEnhancedAt?: string;
}

export function buildRationale(
  component: Component,
  activity?: ActivityComponent | null,
): RationaleView | null {
  const r = component.rationale;
  const ai = component.ai_enhance;
  const view: RationaleView = {};

  if (r?.author) view.author = r.author;
  else if (r?.authors && r.authors.length > 0) view.author = r.authors[0];
  if (r?.last_change) view.lastChange = r.last_change;
  if (typeof r?.churn === "number") view.churn = r.churn;
  if (r?.commit) view.commit = r.commit;
  if (r?.pr) view.pr = r.pr;

  // Git-activity data (P5-4) fills in author, last change, and churn wherever the
  // explicit rationale did not already carry them, so the "how alive is this,
  // who touched it" strip is populated for every element when activity exists
  // (I13). The lead author is the top contributor by commit share.
  if (activity) {
    if (view.author === undefined && activity.authors.length > 0) {
      view.author = activity.authors[0].author_name;
    }
    if (view.lastChange === undefined && activity.last_modified) {
      view.lastChange = formatRelativeTime(activity.last_modified);
    }
    if (view.churn === undefined && typeof activity.churn === "number") {
      view.churn = activity.churn;
    }
  }

  if (ai?.architectural_role) view.role = ai.architectural_role;
  if (ai?.help_text) view.hasAiIntent = true;
  if (ai?.ai_enhanced_at) view.aiEnhancedAt = ai.ai_enhanced_at;

  const hasAny =
    view.author !== undefined ||
    view.lastChange !== undefined ||
    view.churn !== undefined ||
    view.commit !== undefined ||
    view.pr !== undefined ||
    view.role !== undefined ||
    view.hasAiIntent === true;

  return hasAny ? view : null;
}

export function RationaleStrip({ component }: { component: Component }) {
  const darkMode = useArchStore((s) => s.darkMode);
  const archHasActivity = useArchStore((s) => s.architecture?.activity != null);
  const activityData = useArchStore((s) => s.activityData);
  const loadActivity = useArchStore((s) => s.loadActivity);

  // Pull git-activity data into the strip for every element when the dataset
  // carries it (I13), independent of the active lens. Lazy and guarded, so it
  // fetches at most once and is a no-op when there is no activity data.
  useEffect(() => {
    if (archHasActivity) void loadActivity();
  }, [archHasActivity, loadActivity]);

  const activityComponent = activityData?.components.find((c) => c.id === component.id) ?? null;
  const r = buildRationale(component, activityComponent);
  if (!r) return null;

  const chip = darkMode
    ? "bg-zinc-800/60 text-zinc-400 border-zinc-700/50"
    : "bg-zinc-100 text-zinc-600 border-zinc-200";
  const roleMeta = r.role ? ROLE_META[r.role] : null;

  return (
    <div
      className={`px-4 py-2 flex flex-wrap items-center gap-1.5 text-[10px] border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}
      aria-label="Rationale"
    >
      <span className={`uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        Why / who
      </span>

      {roleMeta && r.role && (
        <span className={`px-1.5 py-0.5 rounded-full font-medium border-0 ${getRoleBadgeColors(r.role, darkMode)}`}>
          {roleMeta.icon} {roleMeta.label}
        </span>
      )}
      {r.hasAiIntent && (
        <span className={`px-1.5 py-0.5 rounded border ${chip}`} title="AI-written intent is available in the AI Insights tab">
          {"\u2728"} AI intent
        </span>
      )}
      {r.author && (
        <span className={`px-1.5 py-0.5 rounded border ${chip}`}>by {r.author}</span>
      )}
      {r.lastChange && (
        <span className={`px-1.5 py-0.5 rounded border ${chip}`}>changed {r.lastChange}</span>
      )}
      {r.churn !== undefined && (
        <span className={`px-1.5 py-0.5 rounded border ${chip}`} title="Change frequency">
          churn {r.churn}
        </span>
      )}
      {r.commit && (
        <span className={`px-1.5 py-0.5 rounded border font-mono ${chip}`}>{r.commit.slice(0, 7)}</span>
      )}
      {r.pr && (
        <span className={`px-1.5 py-0.5 rounded border ${chip}`}>PR {r.pr}</span>
      )}
    </div>
  );
}
