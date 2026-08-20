import { useEffect } from "react";
import { useArchStore } from "../store";
import { formatNumber, getHeatColor } from "../utils/layout";
import type { ActivityComponent, ActivityAuthor } from "../types";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The Activity lens surface (P6-5, LENS-DESIGN.md L5). The landing view is the
// ranked hotspot list (invariant I11: "look here first"); selecting a hotspot
// focuses it, revealing its per-file detail, knowledge map, and change coupling
// ("what changes with this"). The graph beside it is the spatial complement with
// heat rings. Coupling is only ever reached from a focused component, never as a
// standalone hairball.

function HeatBar({ t }: { t: number }) {
  return (
    <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
      <div
        className="h-full rounded-full"
        style={{ width: `${Math.max(3, Math.round(t * 100))}%`, backgroundColor: getHeatColor(t) }}
      />
    </div>
  );
}

function KnowledgeBadges({ c, darkMode }: { c: ActivityComponent; darkMode: boolean }) {
  const chip = darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600";
  const risk = darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700";
  return (
    <div className="flex flex-wrap items-center gap-1 text-[10px]">
      {c.knowledge_island && (
        <Tooltip content={TOOLTIP_COPY.activity.knowledgeIsland}>
          <span className={`px-1.5 py-0.5 rounded ${risk}`}>
            {"\u{1F512}"} island
          </span>
        </Tooltip>
      )}
      <Tooltip content={TOOLTIP_COPY.activity.busFactor}>
        <span className={`px-1.5 py-0.5 rounded ${c.bus_factor <= 1 ? risk : chip}`}>
          bus {c.bus_factor}
        </span>
      </Tooltip>
      <Tooltip content={TOOLTIP_COPY.activity.authorCount}>
        <span className={`px-1.5 py-0.5 rounded ${chip}`}>
          {c.author_count} author{c.author_count !== 1 ? "s" : ""}
        </span>
      </Tooltip>
    </div>
  );
}

function AuthorShares({ authors, darkMode }: { authors: ActivityAuthor[]; darkMode: boolean }) {
  return (
    <div className="space-y-1.5">
      {authors.map((a) => (
        <div key={a.author_key} className="space-y-0.5">
          <div className="flex items-center justify-between text-[11px]">
            <span className={`truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`} title={a.author_key}>
              {a.author_name}
            </span>
            <span className={darkMode ? "text-zinc-500" : "text-zinc-400"}>
              {Math.round(a.share * 100)}% · {a.commits}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
            <div
              className={`h-full rounded-full ${darkMode ? "bg-blue-500/70" : "bg-blue-500/80"}`}
              style={{ width: `${Math.max(3, Math.round(a.share * 100))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionLabel({ children, darkMode }: { children: React.ReactNode; darkMode: boolean }) {
  return (
    <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
      {children}
    </div>
  );
}

// `mobile` (O10): see FlowPanel's comment on the same prop.
export function ActivityPanel({ mobile = false }: { mobile?: boolean } = {}) {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const activityData = useArchStore((s) => s.activityData);
  const activityLoading = useArchStore((s) => s.activityLoading);
  const activityError = useArchStore((s) => s.activityError);
  const selectedComponentId = useArchStore((s) => s.selectedComponentId);
  const loadActivity = useArchStore((s) => s.loadActivity);
  const getHotspots = useArchStore((s) => s.getHotspots);
  const getActivityComponent = useArchStore((s) => s.getActivityComponent);
  const getCouplingForComponent = useArchStore((s) => s.getCouplingForComponent);
  const getComponentActivityFiles = useArchStore((s) => s.getComponentActivityFiles);
  const navigateToComponent = useArchStore((s) => s.navigateToComponent);
  const selectComponent = useArchStore((s) => s.selectComponent);

  // Fetch the full activity data on first mount of the lens (lazy; guarded).
  useEffect(() => {
    if (architecture?.activity != null) void loadActivity();
  }, [architecture, loadActivity]);

  const containerClass = mobile
    ? `flex flex-col w-full h-full overflow-hidden ${darkMode ? "bg-zinc-950" : "bg-zinc-50"}`
    : `hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
        darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      }`;

  const provenance =
    activityData?.provenance ??
    (architecture?.activity && "provenance" in architecture.activity ? architecture.activity.provenance : null);

  const header = (
    <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
      <div className="flex items-center gap-1.5">
        <span>{"\u{1F525}"}</span>
        <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Activity</h2>
      </div>
      {provenance && (
        <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {formatNumber(provenance.commits)} commits from git history
          {provenance.shallow && (
            <span className={darkMode ? "text-amber-400" : "text-amber-600"}> · shallow clone (partial)</span>
          )}
        </p>
      )}
    </div>
  );

  let body: React.ReactNode;
  if (!activityData && activityLoading) {
    body = (
      <div className="flex-1 flex items-center justify-center">
        <div className={`animate-spin w-5 h-5 border-2 rounded-full ${darkMode ? "border-zinc-700 border-t-blue-500" : "border-zinc-300 border-t-blue-500"}`} />
      </div>
    );
  } else if (!activityData) {
    body = (
      <div className={`flex-1 flex items-center justify-center px-4 text-center text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        {activityError ? `Could not load activity data (${activityError}).` : "No activity data for this dataset."}
      </div>
    );
  } else {
    const focused = selectedComponentId ? getActivityComponent(selectedComponentId) : null;
    const focusedFiles = focused ? getComponentActivityFiles(focused.id) : [];
    const focusedFilePaths = new Set(focusedFiles.map((f) => f.path));
    // File-level co-change pairs touching this component's files. Cross-component
    // by construction upstream is not guaranteed here (a<b over all files), so
    // the partner file may belong to this same component; that is still useful
    // ("these two files always change together").
    const fileCoupling = focused
      ? (activityData?.file_coupling ?? [])
          .filter((p) => focusedFilePaths.has(p.a) || focusedFilePaths.has(p.b))
          .map((p) => {
            const anchorIsA = focusedFilePaths.has(p.a);
            const anchor = anchorIsA ? p.a : p.b;
            const partner = anchorIsA ? p.b : p.a;
            return { anchor, partner, count: p.cochange_count };
          })
          .sort((a, b) => b.count - a.count)
          .slice(0, 10)
      : [];
    body = focused ? (
      <FocusedView
        focused={focused}
        darkMode={darkMode}
        rank={getHotspots().findIndex((c) => c.id === focused.id) + 1}
        files={focusedFiles.slice(0, 8)}
        maxFileScore={focusedFiles.reduce((m, f) => Math.max(m, f.hotspot_score), 0)}
        coupling={getCouplingForComponent(focused.id)}
        fileCoupling={fileCoupling}
        onBack={() => selectComponent(null)}
      />
    ) : (
      <OverviewView
        hotspots={getHotspots()}
        darkMode={darkMode}
        onSelect={(id) => navigateToComponent(id)}
      />
    );
  }

  return (
    <div className={containerClass}>
      {header}
      {body}
    </div>
  );
}

function OverviewView({
  hotspots,
  darkMode,
  onSelect,
}: {
  hotspots: ActivityComponent[];
  darkMode: boolean;
  onSelect: (id: string) => void;
}) {
  const maxScore = hotspots.length > 0 ? hotspots[0].hotspot_score : 0;
  const islands = hotspots.filter((c) => c.knowledge_island).length;
  const soleOwner = hotspots.filter((c) => c.bus_factor <= 1).length;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className={`px-4 py-2.5 text-[11px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
        Ranked by hotspot score (change frequency times size). Where the action is.
        {(islands > 0 || soleOwner > 0) && (
          <span className={darkMode ? "text-zinc-500" : "text-zinc-400"}>
            {" "}
            {islands} knowledge island{islands !== 1 ? "s" : ""}, {soleOwner} with bus factor 1.
          </span>
        )}
      </div>
      <ol className="px-2 pb-4 space-y-1">
        {hotspots.map((c, i) => (
          <li key={c.id}>
            <button
              onClick={() => onSelect(c.id)}
              className={`w-full text-left rounded-lg px-2.5 py-2 transition-colors ${
                darkMode ? "hover:bg-zinc-900" : "hover:bg-white"
              }`}
            >
              <div className="flex items-baseline gap-2">
                <span className={`text-[10px] tabular-nums w-4 shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                  {i + 1}
                </span>
                <span className={`flex-1 text-xs font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`} title={c.id}>
                  {c.name}
                </span>
                <Tooltip content={TOOLTIP_COPY.activity.commitCount}>
                  <span className={`text-[10px] tabular-nums shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {formatNumber(c.commit_count)} commits
                  </span>
                </Tooltip>
              </div>
              <div className="mt-1.5 ml-6">
                <Tooltip content={TOOLTIP_COPY.activity.hotspotScore} position="bottom" className="block w-full">
                  <div className="w-full">
                    <HeatBar t={maxScore > 0 ? c.hotspot_score / maxScore : 0} />
                  </div>
                </Tooltip>
                <div className="mt-1.5">
                  <KnowledgeBadges c={c} darkMode={darkMode} />
                </div>
              </div>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

function FocusedView({
  focused,
  darkMode,
  rank,
  files,
  maxFileScore,
  coupling,
  fileCoupling,
  onBack,
}: {
  focused: ActivityComponent;
  darkMode: boolean;
  rank: number;
  files: Array<{ path: string; hotspot_score: number; commit_count: number; churn: number }>;
  maxFileScore: number;
  coupling: Array<{ partnerId: string; partnerName: string; count: number }>;
  fileCoupling: Array<{ anchor: string; partner: string; count: number }>;
  onBack: () => void;
}) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-3 pt-2.5">
        <button
          onClick={onBack}
          className={`text-[11px] flex items-center gap-1 rounded px-1.5 py-0.5 ${darkMode ? "text-zinc-400 hover:bg-zinc-900" : "text-zinc-500 hover:bg-white"}`}
        >
          {"‹"} Hotspots
        </button>
      </div>

      <div className="px-4 pt-2 pb-3">
        <div className="flex items-baseline gap-2">
          <h3 className={`text-sm font-bold truncate ${darkMode ? "text-zinc-100" : "text-zinc-900"}`} title={focused.id}>
            {focused.name}
          </h3>
          {rank > 0 && (
            <span className={`text-[10px] shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>hotspot #{rank}</span>
          )}
        </div>
        <p className={`mt-0.5 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {formatNumber(focused.commit_count)} commits · {formatNumber(focused.churn)} churn
          {(focused.lines_added > 0 || focused.lines_removed > 0) && (
            <span>
              {" "}(<span className={darkMode ? "text-emerald-500" : "text-emerald-600"}>+{formatNumber(focused.lines_added ?? 0)}</span>
              {" / "}
              <span className={darkMode ? "text-red-500" : "text-red-600"}>-{formatNumber(focused.lines_removed ?? 0)}</span>)
            </span>
          )}
          {" · "}{focused.files} file{focused.files !== 1 ? "s" : ""}
        </p>
        {focused.first_seen && (
          <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            First seen {new Date(focused.first_seen).toLocaleDateString()}
          </p>
        )}
      </div>

      {/* Knowledge map (who knows this, what is at risk) */}
      <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
        <SectionLabel darkMode={darkMode}>Who knows this</SectionLabel>
        <KnowledgeBadges c={focused} darkMode={darkMode} />
        <AuthorShares authors={focused.authors} darkMode={darkMode} />
      </div>

      {/* Per-file hotspot detail (drill-in from the hotspot) */}
      {files.length > 0 && (
        <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
          <SectionLabel darkMode={darkMode}>Hottest files</SectionLabel>
          <div className="space-y-2">
            {files.map((f) => (
              <div key={f.path} className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-[11px]">
                  <span className={`truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`} title={f.path}>
                    {f.path.split("/").pop()}
                  </span>
                  <span className={`shrink-0 tabular-nums ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {formatNumber(f.commit_count)}c
                  </span>
                </div>
                <HeatBar t={maxFileScore > 0 ? f.hotspot_score / maxFileScore : 0} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Change coupling: reached FROM this component, never standalone */}
      <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
        <SectionLabel darkMode={darkMode}>Changes with</SectionLabel>
        {coupling.length === 0 ? (
          <p className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            No cross-component coupling above the support floor.
          </p>
        ) : (
          <ul className="space-y-1">
            {coupling.slice(0, 10).map((p) => (
              <li key={p.partnerId} className="flex items-center justify-between gap-2 text-[11px]">
                <span className={`truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`} title={p.partnerId}>
                  {p.partnerName}
                </span>
                <Tooltip content={TOOLTIP_COPY.activity.couplingCount} focusable>
                  <span
                    className={`shrink-0 tabular-nums px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}
                  >
                    {p.count}
                  </span>
                </Tooltip>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* File-level co-change pairs (finer grain than the component coupling above) */}
      {fileCoupling.length > 0 && (
        <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
          <SectionLabel darkMode={darkMode}>Files that change together</SectionLabel>
          <ul className="space-y-1">
            {fileCoupling.map((p, i) => (
              <li key={`${p.anchor}:${p.partner}:${i}`} className="flex items-center justify-between gap-2 text-[11px]">
                <span className={`truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`} title={`${p.anchor} ↔ ${p.partner}`}>
                  {p.anchor.split("/").pop()} {"↔"} {p.partner.split("/").pop()}
                </span>
                <span
                  className={`shrink-0 tabular-nums px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}
                >
                  {p.count}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
