import { useState, useMemo, useCallback, type ReactNode } from "react";
import { useArchStore } from "../store";
import type { CoverageRow } from "../types";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY, dispositionTooltip } from "../utils/tooltipCopy";
import { InventoryPanel } from "./InventoryPanel";

// Coverage badge and drill-in panel (P4-4; TARGET-ARCHITECTURE.md section 7,
// invariant I2; LENS-DESIGN.md I11 rank-don't-render).
//
// Coverage semantics classify every ledger disposition into three families, so
// the percent means "how much of your source did we analyze" and never gets
// diluted by files that contain no code:
//
//   - SOURCE ANALYZED  (parsed): the numerator, and the good part of the
//     denominator.
//   - SOURCE GAPS  (failed, excluded:max_file_size, and any other exclusion of
//     analyzable source): loud, amber, counted against the percent.
//   - NON-SOURCE ACCOUNTED  (binary, unsupported extensions, empty files, pruned
//     directories, vendored repos): never in the denominator; recorded so
//     nothing is silently missing, and shown as reassurance, not alarm.
//
// So a repo of all-source parsed files plus 6,047 images reads "100% of source
// analyzed" with "6,047 non-source files accounted for", not "10% parsed". The
// old total-based percent (parsed / total) is gone.
//
// Degradation:
//   - No coverage key and no repositories: legacy single-repo dataset. Render
//     nothing so old datasets look identical.
//   - No coverage key but repositories present: a multi-repo dataset whose
//     projection omits a unified ledger (P4-5 known limitation). Show a small
//     "coverage unavailable for this dataset" note instead of a fake percentage.

export type CoverageFamily = "analyzed" | "gap" | "nonsource";

// The dispositions that are non-source: recorded for completeness, never counted
// against coverage. Everything else that is not `parsed` is a source gap (loud),
// including any future excluded rule, per "exceptions as loud exceptions".
const NON_SOURCE_DISPOSITIONS = new Set([
  "binary",
  "excluded:unsupported_extension",
  "excluded:empty_file",
  "excluded:skipped_directory",
  "excluded:vendored_repo",
]);

// Classify a disposition into one of the three families. `parsed` is analyzed;
// the known non-source rules are non-source; `failed`/`failed:*`,
// `excluded:max_file_size`, and any unrecognized exclusion are source gaps.
export function classifyDisposition(disposition: string): CoverageFamily {
  if (disposition === "parsed") return "analyzed";
  if (NON_SOURCE_DISPOSITIONS.has(disposition)) return "nonsource";
  return "gap";
}

// A disposition is a "failure" when it is exactly `failed` or namespaced
// `failed:<error>`. Failures list first within the gaps family, per I11.
function isFailure(disposition: string): boolean {
  return disposition === "failed" || disposition.startsWith("failed:");
}

export interface CoverageFamilies {
  analyzed: number;
  gap: number;
  nonsource: number;
  // The percent's denominator: analyzed source plus source gaps only.
  sourceTotal: number;
  // Analyzed source over the source total, 0 to 100. 100 when there is no source.
  percent: number;
  perFamily: Record<CoverageFamily, Array<{ disposition: string; count: number }>>;
}

// Reduce a disposition->count summary into the three families and the source
// percent. This is the whole of the new coverage math and is unit-tested
// directly (the old parsed/total math must fail these tests).
export function computeCoverageFamilies(summary: Record<string, number>): CoverageFamilies {
  let analyzed = 0;
  let gap = 0;
  let nonsource = 0;
  const perFamily: CoverageFamilies["perFamily"] = { analyzed: [], gap: [], nonsource: [] };

  for (const [disposition, count] of Object.entries(summary)) {
    const family = classifyDisposition(disposition);
    perFamily[family].push({ disposition, count });
    if (family === "analyzed") analyzed += count;
    else if (family === "gap") gap += count;
    else nonsource += count;
  }

  const sourceTotal = analyzed + gap;
  const percent = sourceTotal > 0 ? (analyzed / sourceTotal) * 100 : 100;
  return { analyzed, gap, nonsource, sourceTotal, percent, perFamily };
}

// Format the source percent for display. No gaps reads exactly "100". With gaps,
// show one decimal, and never round up to a bare "100" while a real gap exists
// (so a single skipped file cannot masquerade as full coverage).
export function formatSourcePercent(fam: CoverageFamilies): string {
  if (fam.sourceTotal === 0 || fam.gap === 0) return "100";
  let rounded = Math.round(fam.percent * 10) / 10;
  if (rounded >= 100) rounded = 99.9;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

// Human label for a disposition string. `excluded:skipped_directory` becomes
// "Excluded: skipped directory"; `binary` becomes "Binary".
function dispositionLabel(disposition: string): string {
  const [head, ...rest] = disposition.split(":");
  const tail = rest.join(":").replace(/_/g, " ").trim();
  const headLabel = head.charAt(0).toUpperCase() + head.slice(1);
  return tail ? `${headLabel}: ${tail}` : headLabel;
}

interface Group {
  disposition: string;
  count: number;
  rows: CoverageRow[];
}

// Order the dispositions inside a family: failures first (per I11), then the
// rest by count descending, ties broken by disposition name for determinism.
function orderGroups(
  entries: Array<{ disposition: string; count: number }>,
  rowsByDisposition: Map<string, CoverageRow[]>,
): Group[] {
  const groups: Group[] = entries.map(({ disposition, count }) => ({
    disposition,
    count,
    rows: rowsByDisposition.get(disposition) ?? [],
  }));
  groups.sort((a, b) => {
    const af = isFailure(a.disposition);
    const bf = isFailure(b.disposition);
    if (af !== bf) return af ? -1 : 1;
    if (a.count !== b.count) return b.count - a.count;
    return a.disposition.localeCompare(b.disposition);
  });
  return groups;
}

function GroupRows({ rows, darkMode }: { rows: CoverageRow[]; darkMode: boolean }) {
  return (
    <ul className="mt-1 space-y-0.5">
      {rows.map((row) => (
        <li key={row.path} className="flex items-baseline gap-2 text-[11px]">
          <span className={`font-mono truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
            {row.path}
          </span>
          {row.reason && (
            <span className={`shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {row.reason}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function CoverageGroup({
  group,
  tone,
  darkMode,
  defaultExpanded,
}: {
  group: Group;
  tone: "gap" | "nonsource";
  darkMode: boolean;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const failure = isFailure(group.disposition);
  const hasRows = group.rows.length > 0;
  const chipCls =
    tone === "gap"
      ? failure
        ? darkMode
          ? "bg-red-500/15 text-red-400"
          : "bg-red-100 text-red-700"
        : darkMode
          ? "bg-amber-500/15 text-amber-400"
          : "bg-amber-100 text-amber-700"
      : darkMode
        ? "bg-zinc-800 text-zinc-400"
        : "bg-zinc-100 text-zinc-600";

  return (
    <div className={`rounded-md border ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        disabled={!hasRows}
        className={`w-full flex items-center gap-2 px-2 py-1.5 text-left ${
          hasRows ? "cursor-pointer" : "cursor-default"
        } ${darkMode ? "hover:bg-zinc-800/60" : "hover:bg-zinc-50"}`}
      >
        <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase tracking-wider ${chipCls}`}>
          {tone === "gap" ? (failure ? "failed" : "excluded") : "non-source"}
        </span>
        <Tooltip content={dispositionTooltip(group.disposition)}>
          <span className={`flex-1 text-xs ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
            {dispositionLabel(group.disposition)}
          </span>
        </Tooltip>
        <span className={`shrink-0 text-xs font-mono ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
          {fmt(group.count)}
        </span>
        {hasRows && (
          <span className={`shrink-0 text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {expanded ? "▲" : "▼"}
          </span>
        )}
      </button>
      {expanded && hasRows && (
        <div className="px-2 pb-2">
          <GroupRows rows={group.rows} darkMode={darkMode} />
        </div>
      )}
    </div>
  );
}

// One of the three family sections in the drill-in panel: a labeled, explained
// header with the family count, and the per-disposition groups beneath it.
function FamilySection({
  title,
  tooltip,
  explanation,
  count,
  tone,
  groups,
  darkMode,
  defaultExpandGroups,
  footer,
}: {
  title: string;
  tooltip: string;
  explanation: string;
  count: number;
  tone: "analyzed" | "gap" | "nonsource";
  groups: Group[];
  darkMode: boolean;
  defaultExpandGroups: boolean;
  footer?: ReactNode;
}) {
  const dot =
    tone === "analyzed"
      ? darkMode ? "text-emerald-400" : "text-emerald-600"
      : tone === "gap"
        ? darkMode ? "text-amber-400" : "text-amber-600"
        : darkMode ? "text-zinc-500" : "text-zinc-400";
  return (
    <div className="space-y-1">
      <div className="flex items-baseline gap-2">
        <Tooltip content={tooltip} focusable>
          <span className={`text-[11px] font-semibold uppercase tracking-wider ${dot}`}>{title}</span>
        </Tooltip>
        <Tooltip content={tooltip} focusable>
          <span className={`text-xs font-mono ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{fmt(count)}</span>
        </Tooltip>
      </div>
      <p className={`text-[11px] leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{explanation}</p>
      {tone !== "analyzed" && groups.length > 0 && (
        <div className="space-y-1 pt-0.5">
          {groups.map((group) => (
            <CoverageGroup
              key={group.disposition}
              group={group}
              tone={tone === "gap" ? "gap" : "nonsource"}
              darkMode={darkMode}
              defaultExpanded={defaultExpandGroups && isFailure(group.disposition)}
            />
          ))}
        </div>
      )}
      {footer}
    </div>
  );
}

export function CoverageBadge() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const coverageRows = useArchStore((s) => s.coverageRows);
  const coverageRowsLoading = useArchStore((s) => s.coverageRowsLoading);
  const coverageRowsError = useArchStore((s) => s.coverageRowsError);
  const loadCoverageRows = useArchStore((s) => s.loadCoverageRows);
  const coverageInventory = useArchStore((s) => s.coverageInventory);

  const [open, setOpen] = useState(false);
  const [inventoryOpen, setInventoryOpen] = useState(false);

  const coverage = architecture?.coverage ?? null;

  const rowsByDisposition = useMemo(() => {
    const map = new Map<string, CoverageRow[]>();
    for (const row of coverageRows ?? []) {
      const list = map.get(row.disposition);
      if (list) list.push(row);
      else map.set(row.disposition, [row]);
    }
    return map;
  }, [coverageRows]);

  const families = useMemo(
    () => (coverage ? computeCoverageFamilies(coverage.summary) : null),
    [coverage],
  );

  const gapGroups = useMemo(
    () => (families ? orderGroups(families.perFamily.gap, rowsByDisposition) : []),
    [families, rowsByDisposition],
  );
  const nonSourceGroups = useMemo(
    () => (families ? orderGroups(families.perFamily.nonsource, rowsByDisposition) : []),
    [families, rowsByDisposition],
  );

  const toggleOpen = useCallback(() => {
    setOpen((wasOpen) => {
      const next = !wasOpen;
      if (next) void loadCoverageRows();
      return next;
    });
  }, [loadCoverageRows]);

  // Nothing to show for a legacy single-repo dataset (no coverage, no
  // repositories): degrade silently so old datasets render unchanged.
  if (!coverage || !families) {
    const multiRepo = (architecture?.repositories?.length ?? 0) > 0;
    if (!multiRepo) return null;
    return (
      <div
        data-testid="coverage-unavailable"
        className={`px-4 py-1.5 text-[11px] shrink-0 ${
          darkMode
            ? "bg-zinc-900 border-b border-zinc-800 text-zinc-500"
            : "bg-zinc-50 border-b border-zinc-200 text-zinc-500"
        }`}
      >
        Coverage unavailable for this dataset
      </div>
    );
  }

  const hasGaps = families.gap > 0;
  const percentStr = formatSourcePercent(families);
  const tone = hasGaps
    ? darkMode
      ? "bg-amber-950/20 border-b border-amber-900/30 text-amber-200"
      : "bg-amber-50 border-b border-amber-200 text-amber-900"
    : darkMode
      ? "bg-emerald-950/20 border-b border-emerald-900/30 text-emerald-300"
      : "bg-emerald-50 border-b border-emerald-200 text-emerald-800";

  const hasInventory = (coverageInventory?.groups?.length ?? 0) > 0;
  const inventoryFooter = hasInventory ? (
    <Tooltip content={TOOLTIP_COPY.inventory.explore}>
      <button
        type="button"
        data-testid="inventory-explore"
        onClick={() => setInventoryOpen(true)}
        className={`mt-1.5 w-full flex items-center justify-center gap-1 rounded-md border px-2 py-1.5 text-[11px] font-medium ${
          darkMode
            ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800/60"
            : "border-zinc-300 text-zinc-700 hover:bg-zinc-50"
        }`}
      >
        Explore inventory
        <span aria-hidden>{"→"}</span>
      </button>
    </Tooltip>
  ) : null;

  return (
    <>
    <div className={`px-4 py-2 text-xs shrink-0 ${tone}`}>
      <button
        type="button"
        data-testid="coverage-badge"
        onClick={toggleOpen}
        aria-expanded={open}
        className="w-full flex items-center gap-2 text-left"
      >
        <span className="shrink-0">{hasGaps ? "⚠️" : "✅"}</span>
        <Tooltip content={TOOLTIP_COPY.coverage.percent}>
          <span className="font-semibold shrink-0" data-testid="coverage-headline">
            {percentStr}% of source analyzed
          </span>
        </Tooltip>

        {hasGaps ? (
          <Tooltip content={TOOLTIP_COPY.coverage.gapCount}>
            <span
              data-testid="coverage-gap-count"
              className={`shrink-0 text-[11px] font-medium ${darkMode ? "text-amber-300" : "text-amber-700"}`}
            >
              {fmt(families.gap)} file{families.gap !== 1 ? "s" : ""} skipped
            </span>
          </Tooltip>
        ) : (
          families.nonsource > 0 && (
            <Tooltip content={TOOLTIP_COPY.coverage.nonSourceCount}>
              <span
                data-testid="coverage-nonsource-count"
                className={`shrink-0 ${darkMode ? "text-emerald-500" : "text-emerald-600"}`}
              >
                {fmt(families.nonsource)} non-source file{families.nonsource !== 1 ? "s" : ""} accounted for
              </span>
            </Tooltip>
          )
        )}

        {/* When gaps exist, still surface the non-source reassurance count quietly. */}
        {hasGaps && families.nonsource > 0 && (
          <Tooltip content={TOOLTIP_COPY.coverage.nonSourceCount}>
            <span
              data-testid="coverage-nonsource-count"
              className={`shrink-0 text-[10px] ${darkMode ? "text-amber-400/70" : "text-amber-600/80"}`}
            >
              {fmt(families.nonsource)} non-source accounted for
            </span>
          </Tooltip>
        )}

        <span className="flex-1" />
        <span className={`shrink-0 text-[10px] ${hasGaps ? (darkMode ? "text-amber-400" : "text-amber-600") : darkMode ? "text-emerald-500" : "text-emerald-600"}`}>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div data-testid="coverage-panel" className="mt-2 pt-2 border-t space-y-3 border-current/20">
          <FamilySection
            title="Source analyzed"
            tooltip={TOOLTIP_COPY.coverage.familyAnalyzed}
            explanation={TOOLTIP_COPY.coverage.familyAnalyzed}
            count={families.analyzed}
            tone="analyzed"
            groups={[]}
            darkMode={darkMode}
            defaultExpandGroups={false}
          />
          <FamilySection
            title="Source gaps"
            tooltip={TOOLTIP_COPY.coverage.familyGaps}
            explanation={TOOLTIP_COPY.coverage.familyGaps}
            count={families.gap}
            tone="gap"
            groups={gapGroups}
            darkMode={darkMode}
            defaultExpandGroups
          />
          <FamilySection
            title="Non-source accounted"
            tooltip={TOOLTIP_COPY.coverage.familyNonSource}
            explanation={TOOLTIP_COPY.coverage.familyNonSource}
            count={families.nonsource}
            tone="nonsource"
            groups={nonSourceGroups}
            darkMode={darkMode}
            defaultExpandGroups={false}
            footer={inventoryFooter}
          />
          {coverageRowsLoading && (
            <p className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Loading file list...
            </p>
          )}
          {coverageRowsError && (
            <p className={`text-[11px] ${darkMode ? "text-amber-400" : "text-amber-600"}`}>
              Could not load the full file list ({coverageRowsError}). Counts per rule are shown above.
            </p>
          )}
        </div>
      )}
    </div>
    <InventoryPanel open={inventoryOpen} onClose={() => setInventoryOpen(false)} />
    </>
  );
}
