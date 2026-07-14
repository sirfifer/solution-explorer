import { useState, useMemo, useCallback } from "react";
import { useArchStore } from "../store";
import type { CoverageRow } from "../types";

// Coverage badge and drill-in panel (P4-4; TARGET-ARCHITECTURE.md section 7,
// invariant I2; LENS-DESIGN.md I11 rank-don't-render).
//
// The badge shows percent parsed and counts per disposition, reading the summary
// straight from `architecture.coverage` (which the manifest carries inline).
// Clicking opens a panel that lists failures first, then exclusions grouped by
// rule ranked by count (I11). The full rows drill-in comes from
// `architecture.coverage.rows` (monolith) or a lazy fetch of coverage.json
// (split mode).
//
// Degradation:
//   - No coverage key and no repositories: legacy single-repo dataset. Render
//     nothing so old datasets look identical.
//   - No coverage key but repositories present: a multi-repo dataset whose
//     projection omits a unified ledger (P4-5 known limitation). Show a small
//     "coverage unavailable for this dataset" note instead of a fake percentage.

// A disposition is a "failure" when it is exactly `failed` or namespaced
// `failed:<error>`. Failures list first and expanded, per I11.
function isFailure(disposition: string): boolean {
  return disposition === "failed" || disposition.startsWith("failed:");
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

// Order the non-parsed dispositions: failures first (per I11), then the rest by
// count descending, ties broken by disposition name for determinism.
function orderGroups(
  summary: Record<string, number>,
  rowsByDisposition: Map<string, CoverageRow[]>,
): Group[] {
  const groups: Group[] = Object.entries(summary)
    .filter(([disposition]) => disposition !== "parsed")
    .map(([disposition, count]) => ({
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
  darkMode,
  defaultExpanded,
}: {
  group: Group;
  darkMode: boolean;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const failure = isFailure(group.disposition);
  const hasRows = group.rows.length > 0;

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
        <span
          className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase tracking-wider ${
            failure
              ? darkMode
                ? "bg-red-500/15 text-red-400"
                : "bg-red-100 text-red-700"
              : darkMode
                ? "bg-amber-500/15 text-amber-400"
                : "bg-amber-100 text-amber-700"
          }`}
        >
          {failure ? "failed" : "excluded"}
        </span>
        <span className={`flex-1 text-xs ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
          {dispositionLabel(group.disposition)}
        </span>
        <span className={`shrink-0 text-xs font-mono ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
          {group.count}
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

export function CoverageBadge() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const coverageRows = useArchStore((s) => s.coverageRows);
  const coverageRowsLoading = useArchStore((s) => s.coverageRowsLoading);
  const coverageRowsError = useArchStore((s) => s.coverageRowsError);
  const loadCoverageRows = useArchStore((s) => s.loadCoverageRows);

  const [open, setOpen] = useState(false);

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

  const groups = useMemo(
    () => (coverage ? orderGroups(coverage.summary, rowsByDisposition) : []),
    [coverage, rowsByDisposition],
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
  if (!coverage) {
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

  const percent = coverage.total > 0 ? Math.round((coverage.parsed / coverage.total) * 100) : 0;
  const nonParsed = Object.entries(coverage.summary).filter(([d]) => d !== "parsed");

  return (
    <div
      className={`px-4 py-2 text-xs shrink-0 ${
        darkMode
          ? "bg-emerald-950/20 border-b border-emerald-900/30 text-emerald-300"
          : "bg-emerald-50 border-b border-emerald-200 text-emerald-800"
      }`}
    >
      <button
        type="button"
        data-testid="coverage-badge"
        onClick={toggleOpen}
        aria-expanded={open}
        className="w-full flex items-center gap-2 text-left"
      >
        <span className="shrink-0">&#x1F4C1;</span>
        <span className="font-semibold shrink-0">Coverage {percent}% parsed</span>
        <span className={`shrink-0 ${darkMode ? "text-emerald-500" : "text-emerald-600"}`}>
          ({coverage.parsed}/{coverage.total} files)
        </span>
        <span className="flex-1 flex flex-wrap items-center gap-1.5 min-w-0">
          {nonParsed.map(([disposition, count]) => (
            <span
              key={disposition}
              className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                isFailure(disposition)
                  ? darkMode
                    ? "bg-red-500/15 text-red-400"
                    : "bg-red-100 text-red-700"
                  : darkMode
                    ? "bg-zinc-800 text-zinc-400"
                    : "bg-zinc-100 text-zinc-600"
              }`}
            >
              {count} {dispositionLabel(disposition).toLowerCase()}
            </span>
          ))}
        </span>
        <span className={`shrink-0 text-[10px] ${darkMode ? "text-emerald-500" : "text-emerald-600"}`}>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div data-testid="coverage-panel" className="mt-2 pt-2 border-t space-y-1.5 border-current/20">
          {nonParsed.length === 0 ? (
            <p className={`${darkMode ? "text-emerald-400" : "text-emerald-700"}`}>
              Every file under the scan root was parsed. Nothing excluded, nothing failed.
            </p>
          ) : (
            <>
              {groups.map((group) => (
                <CoverageGroup
                  key={group.disposition}
                  group={group}
                  darkMode={darkMode}
                  defaultExpanded={isFailure(group.disposition)}
                />
              ))}
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
            </>
          )}
        </div>
      )}
    </div>
  );
}
