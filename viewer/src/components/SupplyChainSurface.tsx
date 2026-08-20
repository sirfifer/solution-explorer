import { useEffect, useMemo, useState } from "react";
import { useArchStore } from "../store";
import type { SupplyChainDependency } from "../types";
import {
  dependenciesForEcosystem,
  ecosystemSummary,
  evidenceLabel,
  filterByScope,
} from "../supplyChain/model";
import { dataUrl } from "../utils/dataSource";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The supply chain surface (P10-1, VISION.md supply chain view).
//
// NOT a lens: a globally reachable overlay, opened from the SupplyChainEntry bar,
// available whenever the dataset carries a supply_chain section. Dense and
// factual per the no-theater rule: the language target/SDK versions called out at
// the top, then per-ecosystem dependency tables (name, version, pin status,
// direct/transitive, evidence link). No charts, no scores, no vulnerability
// claims. The scope note states plainly this is an inventory, not a security
// scan. Mobile-safe: rows wrap at narrow widths, the body scrolls, the page never
// scrolls horizontally.

type ScopeFilter = "all" | "direct" | "transitive";

function PinBadge({ status, darkMode }: { status: string; darkMode: boolean }) {
  const map: Record<string, { label: string; cls: string; tip: string }> = {
    "exact-pinned": {
      label: "pinned",
      cls: darkMode ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-100 text-emerald-700",
      tip: TOOLTIP_COPY.supplyChain.pinExact,
    },
    range: {
      label: "range",
      cls: darkMode ? "bg-sky-500/15 text-sky-300" : "bg-sky-100 text-sky-700",
      tip: TOOLTIP_COPY.supplyChain.pinRange,
    },
    unpinned: {
      label: "unpinned",
      cls: darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700",
      tip: TOOLTIP_COPY.supplyChain.pinUnpinned,
    },
  };
  const m = map[status] ?? {
    label: status,
    cls: darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-100 text-zinc-700",
    tip: status,
  };
  return (
    <Tooltip content={m.tip}>
      <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${m.cls}`}>
        {m.label}
      </span>
    </Tooltip>
  );
}

function ScopeBadge({ scope, darkMode }: { scope: string; darkMode: boolean }) {
  const direct = scope === "direct";
  return (
    <Tooltip content={direct ? TOOLTIP_COPY.supplyChain.direct : TOOLTIP_COPY.supplyChain.transitive}>
      <span
        className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${
          direct
            ? darkMode
              ? "bg-indigo-500/15 text-indigo-300"
              : "bg-indigo-100 text-indigo-700"
            : darkMode
              ? "bg-zinc-800 text-zinc-400"
              : "bg-zinc-100 text-zinc-500"
        }`}
      >
        {direct ? "direct" : "transitive"}
      </span>
    </Tooltip>
  );
}

function DependencyRow({ dep, darkMode }: { dep: SupplyChainDependency; darkMode: boolean }) {
  const openFileDeepLink = useArchStore((s) => s.openFileDeepLink);
  const closeSupplyChain = useArchStore((s) => s.closeSupplyChain);
  const linkCls = darkMode
    ? "text-blue-400 hover:text-blue-300 hover:underline"
    : "text-blue-600 hover:text-blue-700 hover:underline";

  const openEvidence = () => {
    closeSupplyChain();
    void openFileDeepLink(dep.evidence.file, dep.evidence.line ?? null);
  };

  return (
    <div
      className={`flex flex-wrap items-center gap-x-2 gap-y-1 px-2 py-1.5 rounded border ${
        darkMode ? "border-zinc-800 hover:bg-zinc-900/50" : "border-zinc-200 hover:bg-zinc-50"
      }`}
    >
      <span className={`font-mono text-xs font-medium min-w-0 break-all ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
        {dep.name}
      </span>
      {dep.version && (
        <Tooltip content={TOOLTIP_COPY.supplyChain.version}>
          <span className={`font-mono text-[11px] tabular-nums shrink-0 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
            {dep.version}
          </span>
        </Tooltip>
      )}
      {!dep.version && dep.declared && (
        <Tooltip content={TOOLTIP_COPY.supplyChain.declared}>
          <span className={`font-mono text-[11px] shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            {dep.declared}
          </span>
        </Tooltip>
      )}
      <PinBadge status={dep.pin_status} darkMode={darkMode} />
      <ScopeBadge scope={dep.scope} darkMode={darkMode} />
      <span className="flex-1" />
      <Tooltip content={TOOLTIP_COPY.evidence.link} position="bottom">
        <button
          type="button"
          onClick={openEvidence}
          className={`font-mono text-[10px] text-left truncate max-w-[55%] ${linkCls}`}
          aria-label={`Open ${evidenceLabel(dep.evidence)}`}
        >
          {evidenceLabel(dep.evidence)}
        </button>
      </Tooltip>
    </div>
  );
}

function FixtureSection({
  fixture,
  darkMode,
}: {
  fixture: NonNullable<import("../types").SupplyChain["fixture"]>;
  darkMode: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section data-testid="supply-chain-fixtures">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 text-left"
      >
        <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {expanded ? "▼" : "▶"}
        </span>
        <Tooltip content={TOOLTIP_COPY.supplyChain.fixture}>
          <h3 className={`text-[11px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Test and fixture dependencies
          </h3>
        </Tooltip>
        <span className={`text-[11px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {fixture.dependencies.length} deps {"·"} excluded from the counts above
        </span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-1">
          <p className={`text-[11px] ${darkMode ? "text-zinc-600" : "text-zinc-500"}`}>{fixture.note}</p>
          {fixture.dependencies.map((dep) => (
            <DependencyRow key={`fx-${dep.id}`} dep={dep} darkMode={darkMode} />
          ))}
        </div>
      )}
    </section>
  );
}

export function SupplyChainSurface() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const open = useArchStore((s) => s.supplyChainOpen);
  const closeSupplyChain = useArchStore((s) => s.closeSupplyChain);
  const [scope, setScope] = useState<ScopeFilter>("direct");

  // Escape closes the overlay.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeSupplyChain();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, closeSupplyChain]);

  const sc = architecture?.supply_chain ?? null;

  // Per-ecosystem, scope-filtered dependency lists (memoized). The projection
  // already ranked dependencies direct-before-transitive then by name.
  const perEcosystem = useMemo(() => {
    if (!sc) return [];
    return sc.ecosystems.map((eco) => ({
      eco,
      deps: filterByScope(dependenciesForEcosystem(sc, eco.id), scope),
    }));
  }, [sc, scope]);

  if (!open || !sc) return null;

  const panelCls = darkMode
    ? "bg-zinc-950 border-zinc-800 text-zinc-200"
    : "bg-white border-zinc-200 text-zinc-800";
  const chip = (active: boolean) =>
    `text-[11px] px-2 py-0.5 rounded-full font-medium ${
      active
        ? darkMode
          ? "bg-blue-500/20 text-blue-300"
          : "bg-blue-100 text-blue-700"
        : darkMode
          ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200"
    }`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[6vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Supply chain"
    >
      <div className="absolute inset-0 bg-black/50" onClick={closeSupplyChain} />
      <div className={`relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl border shadow-2xl ${panelCls}`}>
        {/* Header */}
        <div className={`shrink-0 px-4 pt-3 pb-2 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div className="flex items-center gap-2">
            <span>{"\u{1F4E6}"}</span>
            <h2 className="text-sm font-bold">Supply chain</h2>
            <span className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {sc.counts.dependencies} deps {"·"} {sc.counts.ecosystems} ecosystems
            </span>
            <a
              href={dataUrl(sc.sbom_endpoint)}
              target="_blank"
              rel="noopener noreferrer"
              className={`ml-auto text-[11px] px-2 py-1 rounded font-medium ${darkMode ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"}`}
              title={TOOLTIP_COPY.supplyChain.sbomLink}
            >
              {sc.sbom_format}
            </a>
            <button
              type="button"
              onClick={closeSupplyChain}
              className={`p-1 rounded ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
              title="Close (Esc)"
            >
              {"✕"}
            </button>
          </div>
          {/* No-theater scope note: this is an inventory, not a security scan. */}
          <Tooltip content={TOOLTIP_COPY.supplyChain.scopeNote}>
            <p className={`mt-1 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-500"}`} aria-label={TOOLTIP_COPY.supplyChain.scopeNote}>
              {sc.scope_note}
            </p>
          </Tooltip>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {/* Language targets / SDK versions, called out first (owner directive). */}
          {sc.targets.length > 0 && (
            <section data-testid="supply-chain-targets">
              <h3 className={`text-[11px] font-semibold uppercase tracking-wider mb-1.5 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                Language targets and SDK versions
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {sc.targets.map((t) => (
                  <Tooltip key={`${t.ecosystem}:${t.kind}:${t.constraint}`} content={TOOLTIP_COPY.supplyChain.target}>
                    <span className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg border ${darkMode ? "border-zinc-700 bg-zinc-900" : "border-zinc-200 bg-zinc-50"}`}>
                      <span className={darkMode ? "text-zinc-400" : "text-zinc-500"}>{t.label}</span>
                      <span className={`font-mono font-medium ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{t.constraint}</span>
                    </span>
                  </Tooltip>
                ))}
              </div>
            </section>
          )}

          {/* Scope filter for the dependency tables. */}
          <div className="flex items-center gap-1.5">
            <span className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>Show</span>
            <button type="button" className={chip(scope === "direct")} onClick={() => setScope("direct")}>
              direct ({sc.counts.direct})
            </button>
            <button type="button" className={chip(scope === "transitive")} onClick={() => setScope("transitive")}>
              transitive ({sc.counts.transitive})
            </button>
            <button type="button" className={chip(scope === "all")} onClick={() => setScope("all")}>
              all ({sc.counts.dependencies})
            </button>
          </div>

          {/* Per-ecosystem dependency tables. */}
          {perEcosystem.map(({ eco, deps }) => {
            const summary = ecosystemSummary(sc, eco.id);
            return (
              <section key={eco.id} data-testid={`supply-chain-ecosystem-${eco.id}`}>
                <div className="flex items-baseline gap-2 mb-1.5">
                  <Tooltip content={TOOLTIP_COPY.supplyChain.ecosystem}>
                    <h3 className={`text-sm font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                      {eco.label}
                    </h3>
                  </Tooltip>
                  <span className={`text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {summary?.direct_count ?? 0} direct {"·"} {summary?.transitive_count ?? 0} transitive
                  </span>
                </div>
                {deps.length === 0 ? (
                  <p className={`px-2 py-2 text-[11px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    No {scope === "all" ? "" : `${scope} `}dependencies in this ecosystem.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {deps.map((dep) => (
                      <DependencyRow key={dep.id} dep={dep} darkMode={darkMode} />
                    ))}
                  </div>
                )}
              </section>
            );
          })}

          {/* Vendored code checked into the tree, from the supply-chain pass. */}
          {sc.vendored && sc.vendored.length > 0 && (
            <section data-testid="supply-chain-vendored">
              <h3 className={`text-[11px] font-semibold uppercase tracking-wider mb-1.5 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                Vendored code
              </h3>
              <div className="space-y-1">
                {sc.vendored.map((v) => (
                  <Tooltip key={v.path} content={TOOLTIP_COPY.supplyChain.vendored}>
                    <div className={`flex items-center gap-2 px-2 py-1.5 rounded border text-[11px] ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
                      <span className="font-mono break-all">{v.path}</span>
                      {v.file_count != null && (
                        <span className={`ml-auto shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                          {v.file_count} files
                        </span>
                      )}
                    </div>
                  </Tooltip>
                ))}
              </div>
            </section>
          )}

          {/* Test/fixture dependencies: kept and accounted, ranked behind the
              shipping dependencies and excluded from the counts above (finding 1). */}
          {sc.fixture && sc.fixture.dependencies.length > 0 && (
            <FixtureSection fixture={sc.fixture} darkMode={darkMode} />
          )}

          {/* Parse warnings: a found manifest that could not be read. Loud. */}
          {sc.warnings.length > 0 && (
            <section data-testid="supply-chain-warnings">
              <h3 className={`text-[11px] font-semibold uppercase tracking-wider mb-1.5 ${darkMode ? "text-amber-400" : "text-amber-600"}`}>
                Parse warnings
              </h3>
              <div className="space-y-1">
                {sc.warnings.map((w) => (
                  <div
                    key={`${w.file}:${w.error}`}
                    className={`px-2 py-1.5 rounded border text-[11px] ${darkMode ? "border-amber-900/40 bg-amber-950/20 text-amber-200" : "border-amber-200 bg-amber-50 text-amber-800"}`}
                  >
                    <span className="font-mono break-all">{w.file}</span>
                    <span className={darkMode ? "text-amber-400/80" : "text-amber-600"}> {"·"} {w.error}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
