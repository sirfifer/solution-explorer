import { useEffect, useMemo, useState } from "react";
import { useArchStore } from "../store";
import type { InventoryGroup } from "../types";
import { Tooltip } from "./Tooltip";
import { VirtualList } from "./VirtualList";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";
import { computeCoverageFamilies } from "./CoverageBadge";

// The non-source inventory surface (P6-10; repo totality). Opened from the
// coverage drill-in's NON-SOURCE ACCOUNTED family, it answers for every
// non-source file what it is, why it is probably here, and what to do about it.
//
// Everything shown is computed by the analyzer deterministically, without any
// AI (invariants I1, I9). This component only ranks and renders: groups arrive
// pre-ranked by count and bytes (I11), and it names the dominant group when
// non-source dwarfs source, so a committed test-results bundle or a stray cache
// is one drill away, not buried in a flat count.
//
// Degradation: when the dataset carries no inventory (an older projection), the
// panel is never offered (the badge hides the affordance) and this component is
// not mounted.

// The disproportion threshold: non-source outnumbering source by more than this
// is called out in plain language. Matches the card's "more than 3x" cue.
const DISPROPORTION_RATIO = 3;

const SAMPLE_ROW_HEIGHT = 24;

function fmtCount(n: number): string {
  return n.toLocaleString("en-US");
}

// Human-readable byte size. Null renders nothing (bytes were not measurable).
function fmtBytes(bytes: number | null): string | null {
  if (bytes == null) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  const rounded = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[i]}`;
}

function FlagBadge({
  label,
  tooltip,
  tone,
  darkMode,
}: {
  label: string;
  tooltip: string;
  tone: "danger" | "warn" | "info";
  darkMode: boolean;
}) {
  const cls =
    tone === "danger"
      ? darkMode
        ? "bg-red-500/15 text-red-300"
        : "bg-red-100 text-red-700"
      : tone === "warn"
        ? darkMode
          ? "bg-amber-500/15 text-amber-300"
          : "bg-amber-100 text-amber-700"
        : darkMode
          ? "bg-blue-500/15 text-blue-300"
          : "bg-blue-100 text-blue-700";
  return (
    <Tooltip content={tooltip}>
      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
        {label}
      </span>
    </Tooltip>
  );
}

function GroupCard({
  group,
  darkMode,
  isDominant,
}: {
  group: InventoryGroup;
  darkMode: boolean;
  isDominant: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const openFileDeepLink = useArchStore((s) => s.openFileDeepLink);
  const bytesLabel = fmtBytes(group.bytes);
  const hasSamples = group.samples.length > 0;
  // Project knowledge layer (P6-12): how many rows a project rule (one this
  // project taught itself) classified. Drives the "learned" marker on the group
  // and the per-row markers. Additive: absent on old datasets, so undefined here.
  const learnedCount = Object.entries(group.rule_provenance ?? {}).reduce(
    (sum, [source, count]) => (source.startsWith("project:") ? sum + count : sum),
    0,
  );
  const sampleProvenance = group.sample_provenance ?? [];

  return (
    <div
      data-testid="inventory-group"
      data-group-id={group.id}
      className={`rounded-lg border ${darkMode ? "border-zinc-800 bg-zinc-900/40" : "border-zinc-200 bg-white"}`}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className={`w-full flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-left ${
          darkMode ? "hover:bg-zinc-800/40" : "hover:bg-zinc-50"
        }`}
      >
        <Tooltip content={TOOLTIP_COPY.inventory.group}>
          <span className={`text-sm font-semibold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
            {group.label}
          </span>
        </Tooltip>
        <Tooltip content={TOOLTIP_COPY.inventory.count}>
          <span className={`text-xs font-mono ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
            {fmtCount(group.count)} file{group.count !== 1 ? "s" : ""}
          </span>
        </Tooltip>
        {bytesLabel && (
          <Tooltip content={TOOLTIP_COPY.inventory.bytes}>
            <span className={`text-xs font-mono ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {bytesLabel}
            </span>
          </Tooltip>
        )}
        {isDominant && (
          <Tooltip content={TOOLTIP_COPY.inventory.dominant}>
            <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${darkMode ? "bg-zinc-700 text-zinc-200" : "bg-zinc-800 text-white"}`}>
              dominant
            </span>
          </Tooltip>
        )}
        {learnedCount > 0 && (
          <Tooltip content={TOOLTIP_COPY.inventory.projectRule}>
            <span
              data-testid="inventory-learned"
              className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                darkMode ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-100 text-emerald-700"
              }`}
            >
              learned
            </span>
          </Tooltip>
        )}
        {group.flags.security_sensitive && (
          <FlagBadge label="security" tooltip={TOOLTIP_COPY.inventory.securitySensitive} tone="danger" darkMode={darkMode} />
        )}
        {group.flags.likely_unwanted && (
          <FlagBadge label="likely unwanted" tooltip={TOOLTIP_COPY.inventory.likelyUnwanted} tone="warn" darkMode={darkMode} />
        )}
        {group.flags.gitignore_candidate && (
          <FlagBadge label="gitignore?" tooltip={TOOLTIP_COPY.inventory.gitignoreCandidate} tone="info" darkMode={darkMode} />
        )}
        <span className="flex-1" />
        <span className={`shrink-0 text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      <div className="px-3 pb-3 space-y-2">
        <p className={`text-[12px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
          {group.explanation}
        </p>
        <Tooltip content={TOOLTIP_COPY.inventory.recommendation}>
          <p
            data-testid="inventory-recommendation"
            className={`text-[12px] leading-relaxed rounded-md px-2 py-1.5 ${
              group.flags.security_sensitive
                ? darkMode ? "bg-red-500/10 text-red-200" : "bg-red-50 text-red-800"
                : group.flags.likely_unwanted
                  ? darkMode ? "bg-amber-500/10 text-amber-200" : "bg-amber-50 text-amber-800"
                  : darkMode ? "bg-zinc-800/60 text-zinc-300" : "bg-zinc-100 text-zinc-700"
            }`}
          >
            <span className="font-semibold">Recommendation. </span>
            {group.recommendation}
          </p>
        </Tooltip>

        {group.directory_rows > 0 && (
          <Tooltip content={TOOLTIP_COPY.inventory.directoryRows}>
            <p className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>
              {fmtCount(group.directory_rows)} of these{" "}
              {group.directory_rows === 1 ? "is a pruned directory" : "are pruned directories"}, each standing
              in for everything beneath it.
            </p>
          </Tooltip>
        )}

        {expanded && (
          <div className="space-y-2 pt-1">
            {group.extensions.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {group.extensions.map((e) => (
                  <span
                    key={e.ext}
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}
                  >
                    {e.ext} {fmtCount(e.count)}
                  </span>
                ))}
              </div>
            )}
            {group.top_directories.length > 0 && (
              <ul className="space-y-0.5">
                {group.top_directories.map((d) => (
                  <li key={d.dir} className="flex items-baseline justify-between gap-2 text-[11px]">
                    <span className={`font-mono truncate ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{d.dir}</span>
                    <span className={`shrink-0 font-mono ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>{fmtCount(d.count)}</span>
                  </li>
                ))}
              </ul>
            )}
            {hasSamples && (
              <div>
                <Tooltip content={TOOLTIP_COPY.inventory.sample} focusable>
                  <p className={`text-[10px] uppercase tracking-wider font-semibold mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    Files
                  </p>
                </Tooltip>
                <VirtualList
                  items={group.samples}
                  rowHeight={SAMPLE_ROW_HEIGHT}
                  className="max-h-56 rounded border border-current/10"
                  getKey={(path) => path}
                  renderRow={(path, index) => {
                    const learned = (sampleProvenance[index] ?? "").startsWith("project:");
                    return (
                      <button
                        type="button"
                        onClick={() => void openFileDeepLink(path, null)}
                        title={path}
                        className={`w-full h-full flex items-center gap-1.5 px-2 text-left text-[11px] font-mono ${
                          darkMode ? "text-zinc-300 hover:bg-zinc-800/60" : "text-zinc-700 hover:bg-zinc-50"
                        }`}
                      >
                        {learned && (
                          <Tooltip content={TOOLTIP_COPY.inventory.projectRuleRow} focusable>
                            <span
                              data-testid="inventory-row-learned"
                              aria-label="Classified by a learned project rule"
                              className={`shrink-0 h-1.5 w-1.5 rounded-full ${darkMode ? "bg-emerald-400" : "bg-emerald-500"}`}
                            />
                          </Tooltip>
                        )}
                        <span className="truncate">{path}</span>
                      </button>
                    );
                  }}
                />
                {group.count > group.samples.length && (
                  <p className={`text-[10px] mt-1 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    Showing {fmtCount(group.samples.length)} of {fmtCount(group.count)}. The complete list is in the
                    coverage ledger.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function InventoryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const darkMode = useArchStore((s) => s.darkMode);
  const inventory = useArchStore((s) => s.coverageInventory);
  const architecture = useArchStore((s) => s.architecture);
  const loading = useArchStore((s) => s.coverageRowsLoading);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Source analyzed count, for the disproportion cue. Reuse the coverage math so
  // "source" here means exactly what the badge's percent means.
  const sourceAnalyzed = useMemo(() => {
    const summary = architecture?.coverage?.summary;
    if (!summary) return 0;
    return computeCoverageFamilies(summary).analyzed;
  }, [architecture]);

  if (!open) return null;

  const panelCls = darkMode
    ? "bg-zinc-950 border-zinc-800 text-zinc-200"
    : "bg-white border-zinc-200 text-zinc-800";

  const groups = inventory?.groups ?? [];
  const dominantId = inventory?.dominant?.id ?? null;
  const nonSourceTotal = inventory?.non_source_total ?? 0;
  // The cue only fires when at least one source file was analyzed: with zero
  // analyzed source the ratio is undefined and "N to 1" would be misleading.
  const disproportionate =
    dominantId != null &&
    sourceAnalyzed > 0 &&
    nonSourceTotal > sourceAnalyzed * DISPROPORTION_RATIO;
  const dominantGroup = dominantId ? groups.find((g) => g.id === dominantId) ?? null : null;

  return (
    <div
      data-testid="inventory-panel"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[6vh] px-3"
      role="dialog"
      aria-modal="true"
      aria-label="Non-source inventory"
    >
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className={`relative w-full max-w-2xl max-h-[86vh] flex flex-col rounded-2xl border shadow-2xl ${panelCls}`}>
        <div className={`shrink-0 px-4 pt-3 pb-2 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div className="flex items-center gap-2">
            <span aria-hidden>{"\u{1F4E6}"}</span>
            <h2 className="text-sm font-bold">Non-source inventory</h2>
            <span className={`text-xs font-mono ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {fmtCount(nonSourceTotal)} file{nonSourceTotal !== 1 ? "s" : ""}
            </span>
            <button
              type="button"
              onClick={onClose}
              className={`ml-auto p-1 rounded ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
              title="Close (Esc)"
              aria-label="Close inventory"
            >
              {"✕"}
            </button>
          </div>
          <p className={`mt-1 text-[11px] leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>
            Every file that reached the repository but is not analyzable source, grouped by what it is, with a
            recommendation for each group.
          </p>
        </div>

        <div className="overflow-y-auto px-4 py-3 space-y-2">
          {disproportionate && dominantGroup && (
            <div
              data-testid="inventory-disproportion"
              className={`rounded-lg px-3 py-2 text-[12px] leading-relaxed ${
                darkMode ? "bg-amber-500/10 text-amber-200 border border-amber-900/40" : "bg-amber-50 text-amber-900 border border-amber-200"
              }`}
            >
              Non-source files outnumber your analyzed source by more than {DISPROPORTION_RATIO} to 1.
              Most of them, {fmtCount(dominantGroup.count)} of {fmtCount(nonSourceTotal)}, are{" "}
              <span className="font-semibold">{dominantGroup.label.toLowerCase()}</span>. {dominantGroup.recommendation}
            </div>
          )}

          {loading && groups.length === 0 && (
            <p className={`text-[12px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>Loading inventory...</p>
          )}

          {!loading && groups.length === 0 && (
            <p className={`text-[12px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              No non-source files to report for this dataset.
            </p>
          )}

          {groups.map((group) => (
            <GroupCard key={group.id} group={group} darkMode={darkMode} isDominant={group.id === dominantId} />
          ))}
        </div>
      </div>
    </div>
  );
}
