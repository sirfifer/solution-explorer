import { useEffect, useState } from "react";
import { useArchStore } from "../store";
import type { Finding, Concern } from "../types";
import {
  filterFindingsByKind,
  findingKinds,
  evidenceLabel,
} from "../findings/model";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The Findings and Concerns surface (P6-8, LENS-DESIGN.md sections 8, 9, 10).
//
// NOT a lens: a globally reachable ranked overlay, opened from the FindingsEntry
// bar or a contextual detail-panel badge, available whenever the dataset carries
// findings or concerns. Findings are ranked by rank_score (invariant I11);
// every finding carries evidence, confidence, a VISIBLE verification-status
// marker, and the three I15 action affordances (open members, annotate the set,
// export directive). An unverified finding is marked and never presented as
// established fact (the DeepWiki lesson).

// Copy a generated directive's markdown to the clipboard, falling back to a
// popup window when the Clipboard API is unavailable (mirrors the review-panel
// export). Returns whether the clipboard write succeeded.
async function copyDirectiveMarkdown(markdown: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(markdown);
    return true;
  } catch {
    const w = window.open("", "_blank", "width=700,height=600");
    if (w) {
      w.document.write(
        `<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">${markdown.replace(/</g, "&lt;")}</pre>`,
      );
    }
    return false;
  }
}

function KindBadge({ kind, darkMode }: { kind: string; darkMode: boolean }) {
  const map: Record<string, string> = {
    duplication: darkMode ? "bg-violet-500/15 text-violet-300" : "bg-violet-100 text-violet-700",
    orphan: darkMode ? "bg-sky-500/15 text-sky-300" : "bg-sky-100 text-sky-700",
    unreferenced: darkMode ? "bg-sky-500/15 text-sky-300" : "bg-sky-100 text-sky-700",
    inconsistency: darkMode ? "bg-rose-500/15 text-rose-300" : "bg-rose-100 text-rose-700",
    cra_readiness: darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700",
  };
  const cls = map[kind] ?? (darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-100 text-zinc-700");
  const copy = (TOOLTIP_COPY.findings.kind as Record<string, string>)[kind];
  return (
    <Tooltip content={copy ?? `Finding kind: ${kind}.`}>
      <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase tracking-wider ${cls}`}>
        {kind}
      </span>
    </Tooltip>
  );
}

// The verification-status marker (I15). An unverified finding is labeled
// unverified and explicitly "not confirmed", never presented as fact.
function VerificationBadge({ status, darkMode }: { status: string; darkMode: boolean }) {
  if (status === "verified") {
    return (
      <Tooltip content={TOOLTIP_COPY.findings.verification.verified}>
        <span
          className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-100 text-emerald-700"}`}
        >
          {"✓"} verified
        </span>
      </Tooltip>
    );
  }
  if (status === "refuted") {
    return (
      <Tooltip content={TOOLTIP_COPY.findings.verification.refuted}>
        <span
          className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-red-500/15 text-red-300" : "bg-red-100 text-red-700"}`}
        >
          {"✗"} refuted
        </span>
      </Tooltip>
    );
  }
  // Default and explicit "unverified": marked, never presented as established fact.
  return (
    <Tooltip content={TOOLTIP_COPY.findings.verification.unverified}>
      <span
        className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700"}`}
      >
        {"⚠"} unverified · not confirmed
      </span>
    </Tooltip>
  );
}

function FindingRow({ finding, darkMode }: { finding: Finding; darkMode: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const openFileDeepLink = useArchStore((s) => s.openFileDeepLink);
  const navigateToComponent = useArchStore((s) => s.navigateToComponent);
  const closeFindingsSurface = useArchStore((s) => s.closeFindingsSurface);
  const annotateFindingSet = useArchStore((s) => s.annotateFindingSet);
  const exportDirectiveForFinding = useArchStore((s) => s.exportDirectiveForFinding);

  // Navigate to a member's exact location (I15 open members). File members use
  // the file/line deep link; component members drill to the component.
  const openMember = (m: Finding["members"][number]) => {
    closeFindingsSurface();
    if (m.file) {
      void openFileDeepLink(m.file, m.line_start ?? null);
    } else if (m.component_id) {
      navigateToComponent(m.component_id);
    }
  };

  const openFirstMember = () => {
    if (finding.members.length > 0) openMember(finding.members[0]);
  };

  // Export a structured directive (P6-9) built from this finding's members. The
  // set is created (or reused) from the finding, then rendered to markdown with
  // an embedded machine-readable JSON work order and copied to the clipboard.
  const exportDirective = async () => {
    const result = exportDirectiveForFinding(finding.id);
    if (!result) return;
    const ok = await copyDirectiveMarkdown(result.markdown);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  const rowBg = darkMode ? "border-zinc-800 hover:bg-zinc-900/60" : "border-zinc-200 hover:bg-zinc-50";
  const linkCls = darkMode
    ? "text-blue-400 hover:text-blue-300 hover:underline"
    : "text-blue-600 hover:text-blue-700 hover:underline";
  const btn = darkMode
    ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
    : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200";

  return (
    <div className={`rounded-lg border ${rowBg}`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full text-left px-3 py-2.5"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <KindBadge kind={finding.kind} darkMode={darkMode} />
          <VerificationBadge status={finding.verification_status} darkMode={darkMode} />
          <Tooltip content={TOOLTIP_COPY.findings.confidence}>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}`}>
              {finding.confidence}
            </span>
          </Tooltip>
          <span className="ml-auto flex items-center">
            <Tooltip content={TOOLTIP_COPY.findings.rankScore}>
              <span className={`text-[10px] tabular-nums shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                {finding.rank_score.toFixed(0)}
              </span>
            </Tooltip>
          </span>
        </div>
        <div className={`mt-1.5 flex items-start gap-1.5 text-xs ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
          <span className={`shrink-0 mt-0.5 text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {expanded ? "▼" : "▶"}
          </span>
          <span className="flex-1">{finding.summary}</span>
          <Tooltip content={TOOLTIP_COPY.findings.memberCount}>
            <span className={`shrink-0 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {finding.members.length} member{finding.members.length !== 1 ? "s" : ""}
            </span>
          </Tooltip>
        </div>
      </button>

      {expanded && (
        <div className={`px-3 pb-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          {/* Member list with file:line evidence links (I15 "where exactly") */}
          <ul className="mt-2 space-y-1">
            {finding.members.map((m) => (
              <li key={m.id} className="flex items-baseline gap-2 text-[11px]">
                <Tooltip content={TOOLTIP_COPY.evidence.link} position="bottom">
                  <button
                    type="button"
                    onClick={() => openMember(m)}
                    className={`font-mono text-left truncate ${linkCls}`}
                    aria-label={`Open ${m.file ?? m.component_id ?? m.id}`}
                  >
                    {m.file
                      ? evidenceLabel({ file: m.file, line: m.line_start })
                      : (m.component_id ?? m.id)}
                  </button>
                </Tooltip>
                {m.symbol && (
                  <span className={`shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>{m.symbol}</span>
                )}
              </li>
            ))}
          </ul>

          {/* I15 action affordances */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={openFirstMember}
              className={`text-[11px] px-2 py-1 rounded font-medium ${btn}`}
              title="Navigate to the first member's location"
            >
              Open members
            </button>
            <button
              type="button"
              onClick={() => annotateFindingSet(finding)}
              className={`text-[11px] px-2 py-1 rounded font-medium ${btn}`}
              title="Build a selection set from this finding's members and open the set annotation flow in the review panel"
            >
              Annotate the set
            </button>
            <Tooltip content={TOOLTIP_COPY.directive.export} position="bottom">
              <button
                type="button"
                onClick={() => void exportDirective()}
                className={`text-[11px] px-2 py-1 rounded font-medium ${copied ? (darkMode ? "bg-emerald-600/20 text-emerald-300" : "bg-emerald-100 text-emerald-700") : btn}`}
              >
                {copied ? "Copied directive" : "Export directive"}
              </button>
            </Tooltip>
          </div>
        </div>
      )}
    </div>
  );
}

function ConcernRow({ concern, darkMode }: { concern: Concern; darkMode: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const navigateToComponent = useArchStore((s) => s.navigateToComponent);
  const closeFindingsSurface = useArchStore((s) => s.closeFindingsSurface);
  const annotateConcernSet = useArchStore((s) => s.annotateConcernSet);
  const exportDirectiveForConcern = useArchStore((s) => s.exportDirectiveForConcern);

  const openMember = (componentId: string) => {
    closeFindingsSurface();
    navigateToComponent(componentId);
  };

  // The same I15 affordances as a finding row, built from the concern's members
  // (createSetFromConcern under the hood).
  const exportDirective = async () => {
    const result = exportDirectiveForConcern(concern.id);
    if (!result) return;
    const ok = await copyDirectiveMarkdown(result.markdown);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  const rowBg = darkMode ? "border-zinc-800 hover:bg-zinc-900/60" : "border-zinc-200 hover:bg-zinc-50";
  const linkCls = darkMode
    ? "text-blue-400 hover:text-blue-300 hover:underline"
    : "text-blue-600 hover:text-blue-700 hover:underline";
  const btn = darkMode
    ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
    : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200";

  return (
    <div className={`rounded-lg border ${rowBg}`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full text-left px-3 py-2.5"
      >
        <div className="flex items-center gap-2">
          <span className={`shrink-0 text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {expanded ? "▼" : "▶"}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              {/* Mechanical name; the Phase 7 plain-language slot sits beside it. */}
              <Tooltip content={TOOLTIP_COPY.concern.row}>
                <span className={`text-sm font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                  {concern.title}
                </span>
              </Tooltip>
              <Tooltip content={TOOLTIP_COPY.concern.slug}>
                <span className={`font-mono text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                  {concern.id}
                </span>
              </Tooltip>
              {/* Plain-language name slot (P7-4), shaped but empty until enrichment fills it. */}
            </div>
            <Tooltip content={TOOLTIP_COPY.concern.basis}>
              <div className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                {concern.basis}
              </div>
            </Tooltip>
          </div>
          <Tooltip content={TOOLTIP_COPY.concern.memberCount}>
            <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded tabular-nums ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}>
              {concern.members.length} member{concern.members.length !== 1 ? "s" : ""}
            </span>
          </Tooltip>
        </div>
      </button>

      {expanded && (
        <div className={`px-3 pb-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <ul className="mt-2 space-y-1.5">
            {concern.members.map((m) => (
              <li key={m.component_id} className="text-[11px]">
                <button
                  type="button"
                  onClick={() => openMember(m.component_id)}
                  className={`font-mono text-left ${linkCls}`}
                  title={`Open ${m.component_id}`}
                >
                  {m.component_id}
                </button>
                {m.evidence.length > 0 && (
                  <div className={`ml-2 mt-0.5 space-y-0.5 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {m.evidence.slice(0, 4).map((e, i) => (
                      <div key={`${e.file}:${e.line}:${i}`} className="font-mono truncate">
                        {evidenceLabel({ file: e.file, line: e.line })}
                        {e.signal ? ` · ${e.signal}` : ""}
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>

          {/* I15 action affordances, same as a finding row (via createSetFromConcern) */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => annotateConcernSet(concern)}
              className={`text-[11px] px-2 py-1 rounded font-medium ${btn}`}
              title="Build a selection set from this concern's members and open the set annotation flow in the review panel"
            >
              Annotate the set
            </button>
            <button
              type="button"
              onClick={() => void exportDirective()}
              className={`text-[11px] px-2 py-1 rounded font-medium ${copied ? (darkMode ? "bg-emerald-600/20 text-emerald-300" : "bg-emerald-100 text-emerald-700") : btn}`}
              title="Build a selection set from this concern and copy a structured work-order directive (markdown plus machine-readable JSON) for an AI executor"
            >
              {copied ? "Copied directive" : "Export directive"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FindingsSurface() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const surface = useArchStore((s) => s.findingsSurface);
  const getFindings = useArchStore((s) => s.getFindings);
  const getConcerns = useArchStore((s) => s.getConcerns);
  const getFindingsForComponent = useArchStore((s) => s.getFindingsForComponent);
  const getComponentById = useArchStore((s) => s.getComponentById);
  const setFindingsSurfaceTab = useArchStore((s) => s.setFindingsSurfaceTab);
  const setFindingsKindFilter = useArchStore((s) => s.setFindingsKindFilter);
  const closeFindingsSurface = useArchStore((s) => s.closeFindingsSurface);

  // Escape closes the overlay.
  useEffect(() => {
    if (!surface.open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeFindingsSurface();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [surface.open, closeFindingsSurface]);

  if (!surface.open || !architecture) return null;

  const allFindings = getFindings();
  const concerns = getConcerns();
  const elementName = surface.elementFilter
    ? getComponentById(surface.elementFilter)?.name ?? surface.elementFilter
    : null;
  const baseFindings = surface.elementFilter
    ? getFindingsForComponent(surface.elementFilter)
    : allFindings;
  const kinds = findingKinds(baseFindings);
  const shownFindings = filterFindingsByKind(baseFindings, surface.kindFilter);

  const panelCls = darkMode
    ? "bg-zinc-950 border-zinc-800 text-zinc-200"
    : "bg-white border-zinc-200 text-zinc-800";
  const tabBtn = (active: boolean) =>
    `px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
      active
        ? darkMode
          ? "border-blue-400 text-zinc-100"
          : "border-blue-500 text-zinc-900"
        : darkMode
          ? "border-transparent text-zinc-500 hover:text-zinc-300"
          : "border-transparent text-zinc-400 hover:text-zinc-600"
    }`;

  return (
    <div
      data-testid="findings-surface"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[6vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Findings and concerns"
    >
      <div className="absolute inset-0 bg-black/50" onClick={closeFindingsSurface} />
      <div className={`relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl border shadow-2xl ${panelCls}`}>
        {/* Header + tabs */}
        <div className={`shrink-0 px-4 pt-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div className="flex items-center gap-2">
            <span>{"\u{1F50E}"}</span>
            <h2 className="text-sm font-bold">What the system noticed</h2>
            <button
              type="button"
              onClick={closeFindingsSurface}
              className={`ml-auto p-1 rounded ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
              title="Close (Esc)"
            >
              {"✕"}
            </button>
          </div>
          <div className="mt-2 flex items-center gap-1">
            <button
              type="button"
              data-testid="findings-tab"
              className={tabBtn(surface.tab === "findings")}
              onClick={() => setFindingsSurfaceTab("findings")}
            >
              Findings ({allFindings.length})
            </button>
            <button
              type="button"
              data-testid="concerns-tab"
              className={tabBtn(surface.tab === "concerns")}
              onClick={() => setFindingsSurfaceTab("concerns")}
            >
              Concerns ({concerns.length})
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {surface.tab === "findings" ? (
            <>
              {elementName && (
                <div className={`flex items-center gap-2 px-2 py-1.5 rounded-lg text-[11px] ${darkMode ? "bg-zinc-900 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}>
                  <span>Filtered to <span className="font-semibold">{elementName}</span></span>
                  <button
                    type="button"
                    onClick={() => useArchStore.getState().openFindingsSurface({ elementFilter: null })}
                    className={`ml-auto ${darkMode ? "text-blue-400 hover:underline" : "text-blue-600 hover:underline"}`}
                  >
                    Show all
                  </button>
                </div>
              )}

              {/* Kind filter (I11: ranked and filterable) */}
              {kinds.length > 1 && (
                <div className="flex flex-wrap items-center gap-1.5 px-1">
                  <FilterChip
                    label={`all (${baseFindings.length})`}
                    active={!surface.kindFilter || surface.kindFilter === "all"}
                    onClick={() => setFindingsKindFilter(null)}
                    darkMode={darkMode}
                  />
                  {kinds.map((k) => (
                    <FilterChip
                      key={k}
                      label={`${k} (${baseFindings.filter((f) => f.kind === k).length})`}
                      active={surface.kindFilter === k}
                      onClick={() => setFindingsKindFilter(k)}
                      darkMode={darkMode}
                    />
                  ))}
                </div>
              )}

              {shownFindings.length === 0 ? (
                <p className={`px-2 py-6 text-center text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                  No findings for this filter.
                </p>
              ) : (
                shownFindings.map((f) => <FindingRow key={f.id} finding={f} darkMode={darkMode} />)
              )}
            </>
          ) : concerns.length === 0 ? (
            <p className={`px-2 py-6 text-center text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              No concerns for this dataset.
            </p>
          ) : (
            concerns.map((c) => <ConcernRow key={c.id} concern={c} darkMode={darkMode} />)
          )}
        </div>
      </div>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
  darkMode,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  darkMode: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${
        active
          ? darkMode
            ? "bg-blue-500/20 text-blue-300"
            : "bg-blue-100 text-blue-700"
          : darkMode
            ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
            : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200"
      }`}
    >
      {label}
    </button>
  );
}
