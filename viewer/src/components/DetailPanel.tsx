import { useState, useMemo } from "react";
import type { Component, FileInfo, Symbol as ArchSymbol } from "../types";
import { useArchStore } from "../store";
import {
  getTypeColors,
  getLanguageColor,
  formatBytes,
  formatNumber,
  TYPE_META,
} from "../utils/layout";
import { CodePreview } from "./CodePreview";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { Tooltip, TechTooltip } from "./Tooltip";
import { getTechRef, TYPE_DESCRIPTIONS, SYMBOL_KIND_DESCRIPTIONS } from "../utils/techDocs";

type Tab = "overview" | "docs" | "files" | "symbols" | "relationships";

export function DetailPanel() {
  const {
    detailItem,
    architecture,
    darkMode,
    closeDetail,
    drillInto,
    getComponentFiles,
    getComponentSymbols,
    showDetail,
  } = useArchStore();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  if (!detailItem || !architecture) {
    return (
      <div className={`h-full flex items-center justify-center ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        <div className="text-center px-6">
          <div className="text-3xl mb-3">&#x1F50D;</div>
          <p className="text-sm">Select a component to view details</p>
          <p className="text-xs mt-1 opacity-60">Click on a node in the graph or tree</p>
        </div>
      </div>
    );
  }

  if (detailItem.type === "component") {
    return (
      <ComponentDetail
        component={detailItem.data as Component}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        expandedSymbol={expandedSymbol}
        setExpandedSymbol={setExpandedSymbol}
      />
    );
  }

  if (detailItem.type === "file") {
    return <FileDetail file={detailItem.data as FileInfo} />;
  }

  if (detailItem.type === "symbol") {
    return <SymbolDetail symbol={detailItem.data as ArchSymbol} />;
  }

  return null;
}

function ComponentDetail({
  component,
  activeTab,
  setActiveTab,
  expandedSymbol,
  setExpandedSymbol,
}: {
  component: Component;
  activeTab: Tab;
  setActiveTab: (t: Tab) => void;
  expandedSymbol: string | null;
  setExpandedSymbol: (s: string | null) => void;
}) {
  const {
    architecture,
    darkMode,
    closeDetail,
    drillInto,
    getComponentFiles,
    getComponentSymbols,
    showDetail,
  } = useArchStore();
  const colors = getTypeColors(component.type, darkMode);
  const files = useMemo(() => getComponentFiles(component.id), [component.id, getComponentFiles]);
  const symbols = useMemo(() => getComponentSymbols(component.id), [component.id, getComponentSymbols]);
  const relationships = useMemo(
    () =>
      architecture?.relationships.filter(
        (r) => r.source === component.id || r.target === component.id,
      ) || [],
    [architecture, component.id],
  );

  const docs = component.docs;
  const hasDocContent = docs && (docs.readme || docs.claude_md || docs.changelog ||
    docs.architecture_notes || docs.api_docs || docs.api_endpoints?.length ||
    docs.env_vars?.length || docs.patterns?.length);

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "overview", label: "Overview" },
    ...(hasDocContent ? [{ key: "docs" as Tab, label: "Docs" }] : []),
    { key: "files", label: "Files", count: files.length },
    { key: "symbols", label: "Symbols", count: symbols.length },
    { key: "relationships", label: "Links", count: relationships.length },
  ];

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className={`px-4 pt-4 pb-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className={`font-bold text-lg ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {component.name}
            </h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <Tooltip content={TYPE_DESCRIPTIONS[component.type] || component.type}>
                <span className={`text-xs px-2 py-0.5 rounded-full ${colors.badge}`}>
                  {TYPE_META[component.type]?.icon && <span className="mr-1">{TYPE_META[component.type].icon}</span>}
                  {TYPE_META[component.type]?.label || component.type}
                </span>
              </Tooltip>
              {component.framework && (() => {
                const ref = getTechRef(component.framework);
                return ref ? (
                  <TechTooltip name={component.framework} description={ref.description} url={ref.url}>
                    <span className={`text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                      {component.framework}
                    </span>
                  </TechTooltip>
                ) : (
                  <span className={`text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {component.framework}
                  </span>
                );
              })()}
              {component.port && (
                <Tooltip content="The network port this service listens on.">
                  <span className={`text-xs font-mono ${darkMode ? "text-blue-400" : "text-blue-600"}`}>
                    :{component.port}
                  </span>
                </Tooltip>
              )}
            </div>
          </div>
          <button
            onClick={closeDetail}
            className={`p-1 rounded-lg transition-colors ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-100 text-zinc-400"}`}
          >
            &#x2715;
          </button>
        </div>

        {component.path && (
          <p className={`text-xs mt-2 font-mono ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            {component.path}
          </p>
        )}

        {(docs?.purpose || component.description) && (
          <p className={`text-sm mt-2 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
            {docs?.purpose || component.description}
          </p>
        )}

        {/* Tech stack + patterns quick badges */}
        {docs && (docs.tech_stack?.length > 0 || docs.patterns?.length > 0) && (
          <div className="flex flex-wrap gap-1 mt-2">
            {docs.tech_stack?.map((t, i) => {
              const ref = getTechRef(t);
              const badge = (
                <span className={`
                  text-[10px] px-1.5 py-0.5 rounded
                  ${darkMode ? "bg-cyan-900/30 text-cyan-400" : "bg-cyan-50 text-cyan-700"}
                `}>
                  {t}
                </span>
              );
              return ref ? (
                <TechTooltip key={`t-${i}`} name={t} description={ref.description} url={ref.url}>
                  {badge}
                </TechTooltip>
              ) : (
                <span key={`t-${i}`}>{badge}</span>
              );
            })}
            {docs.patterns?.map((p, i) => (
              <Tooltip key={`p-${i}`} content={`Design pattern: ${p}`}>
                <span className={`
                  text-[10px] px-1.5 py-0.5 rounded
                  ${darkMode ? "bg-violet-900/30 text-violet-400" : "bg-violet-50 text-violet-700"}
                `}>
                  {p}
                </span>
              </Tooltip>
            ))}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className={`flex border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              flex-1 px-3 py-2 text-xs font-medium transition-colors
              ${activeTab === tab.key
                ? darkMode
                  ? "border-b-2 border-blue-500 text-blue-400"
                  : "border-b-2 border-blue-500 text-blue-600"
                : darkMode
                  ? "text-zinc-500 hover:text-zinc-300"
                  : "text-zinc-400 hover:text-zinc-600"
              }
            `}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className={`ml-1 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "overview" && (
          <OverviewTab component={component} files={files} symbols={symbols} />
        )}
        {activeTab === "docs" && (
          <DocsTab component={component} />
        )}
        {activeTab === "files" && (
          <FilesTab files={files} componentId={component.id} />
        )}
        {activeTab === "symbols" && (
          <SymbolsTab
            symbols={symbols}
            expandedSymbol={expandedSymbol}
            setExpandedSymbol={setExpandedSymbol}
            componentId={component.id}
          />
        )}
        {activeTab === "relationships" && (
          <RelationshipsTab componentId={component.id} relationships={relationships} />
        )}
      </div>

      {/* Drill-down button */}
      {(component.children.length > 0 || component.files.length > 0) && (
        <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <button
            onClick={() => drillInto(component)}
            className={`
              w-full py-2 rounded-lg text-sm font-medium transition-colors
              ${darkMode
                ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                : "bg-zinc-100 hover:bg-zinc-200 text-zinc-700"
              }
            `}
          >
            Drill into {component.name} &darr;
          </button>
        </div>
      )}
    </div>
  );
}

function OverviewTab({
  component,
  files,
  symbols,
}: {
  component: Component;
  files: FileInfo[];
  symbols: ArchSymbol[];
}) {
  const { darkMode } = useArchStore();
  const metrics = component.metrics;
  const docs = component.docs;

  // Language breakdown
  const langBreakdown = Object.entries(metrics?.languages || {}).sort(
    ([, a], [, b]) => b - a,
  );
  const totalLines = metrics?.lines || 0;

  // Symbols with docstrings (documented)
  const documentedSymbols = symbols.filter(s => s.docstring);

  return (
    <div className="p-4 space-y-4">
      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="Files" value={formatNumber(metrics?.files || 0)} darkMode={darkMode} />
        <StatCard label="Lines" value={formatNumber(metrics?.lines || 0)} darkMode={darkMode} />
        <StatCard label="Symbols" value={formatNumber(metrics?.symbols || 0)} darkMode={darkMode} />
        <StatCard label="Size" value={formatBytes(metrics?.size_bytes || 0)} darkMode={darkMode} />
      </div>

      {/* External Services */}
      {component.external_services && component.external_services.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            External Services ({component.external_services.length})
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {component.external_services.map((svc, i) => {
              const categoryColors: Record<string, string> = {
                ai: darkMode ? "bg-violet-900/40 text-violet-300 border-violet-700/50" : "bg-violet-50 text-violet-700 border-violet-200",
                speech: darkMode ? "bg-cyan-900/40 text-cyan-300 border-cyan-700/50" : "bg-cyan-50 text-cyan-700 border-cyan-200",
                payments: darkMode ? "bg-emerald-900/40 text-emerald-300 border-emerald-700/50" : "bg-emerald-50 text-emerald-700 border-emerald-200",
                communications: darkMode ? "bg-blue-900/40 text-blue-300 border-blue-700/50" : "bg-blue-50 text-blue-700 border-blue-200",
                email: darkMode ? "bg-amber-900/40 text-amber-300 border-amber-700/50" : "bg-amber-50 text-amber-700 border-amber-200",
                devtools: darkMode ? "bg-zinc-800 text-zinc-300 border-zinc-700" : "bg-zinc-100 text-zinc-600 border-zinc-200",
                backend: darkMode ? "bg-orange-900/40 text-orange-300 border-orange-700/50" : "bg-orange-50 text-orange-700 border-orange-200",
                database: darkMode ? "bg-rose-900/40 text-rose-300 border-rose-700/50" : "bg-rose-50 text-rose-700 border-rose-200",
              };
              const colors = categoryColors[svc.category] || (darkMode ? "bg-zinc-800 text-zinc-300 border-zinc-700" : "bg-zinc-100 text-zinc-600 border-zinc-200");
              return (
                <Tooltip key={i} content={`External ${svc.category} service`}>
                  <span className={`text-xs px-2 py-1 rounded-md border ${colors}`}>
                    {svc.name}
                  </span>
                </Tooltip>
              );
            })}
          </div>
        </div>
      )}

      {/* API Endpoints */}
      {docs?.api_endpoints && docs.api_endpoints.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            API Endpoints ({docs.api_endpoints.length})
          </h4>
          <div className="space-y-1">
            {docs.api_endpoints.map((ep, i) => (
              <div key={i} className={`
                flex items-center gap-2 px-2 py-1.5 rounded-md font-mono text-xs
                ${darkMode ? "bg-zinc-800/50" : "bg-zinc-50"}
              `}>
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold
                  ${ep.method === "GET" ? (darkMode ? "bg-green-900/40 text-green-400" : "bg-green-100 text-green-700") :
                    ep.method === "POST" ? (darkMode ? "bg-blue-900/40 text-blue-400" : "bg-blue-100 text-blue-700") :
                    ep.method === "DELETE" ? (darkMode ? "bg-red-900/40 text-red-400" : "bg-red-100 text-red-700") :
                    (darkMode ? "bg-yellow-900/40 text-yellow-400" : "bg-yellow-100 text-yellow-700")}
                `}>
                  {ep.method}
                </span>
                <span className={darkMode ? "text-zinc-300" : "text-zinc-600"}>{ep.path}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Environment Variables */}
      {docs?.env_vars && docs.env_vars.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Environment Variables ({docs.env_vars.length})
          </h4>
          <div className="flex flex-wrap gap-1">
            {docs.env_vars.map((v, i) => (
              <span key={i} className={`
                font-mono text-[10px] px-1.5 py-0.5 rounded
                ${darkMode ? "bg-amber-900/30 text-amber-300" : "bg-amber-50 text-amber-700"}
              `}>
                {v}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Documented symbols preview */}
      {documentedSymbols.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Documented Symbols ({documentedSymbols.length})
          </h4>
          <div className="space-y-1">
            {documentedSymbols.slice(0, 8).map((sym) => (
              <div key={sym.id} className={`px-2 py-1.5 rounded-md ${darkMode ? "bg-zinc-800/50" : "bg-zinc-50"}`}>
                <div className={`text-xs font-mono ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                  <span className={`${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>{sym.kind}</span> {sym.name}
                </div>
                {sym.docstring && (
                  <p className={`text-[10px] mt-0.5 leading-snug ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {sym.docstring.split("\n")[0]}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Language breakdown */}
      {langBreakdown.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Languages
          </h4>
          <div className="space-y-2">
            {langBreakdown.map(([lang, lines]) => (
              <div key={lang} className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: getLanguageColor(lang) }}
                />
                <span className={`text-sm flex-1 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                  {lang}
                </span>
                <span className={`text-xs tabular-nums ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                  {formatNumber(lines)} lines
                </span>
                <div className={`w-16 h-1.5 rounded-full overflow-hidden ${darkMode ? "bg-zinc-800" : "bg-zinc-200"}`}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(100, (lines / totalLines) * 100)}%`,
                      backgroundColor: getLanguageColor(lang),
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Children */}
      {component.children.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Sub-components ({component.children.length})
          </h4>
          <div className="space-y-1">
            {component.children.map((child) => (
              <ChildRow key={child.id} component={child} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DocsTab({ component }: { component: Component }) {
  const { darkMode } = useArchStore();
  const docs = component.docs;
  const [docSection, setDocSection] = useState<string>("readme");

  if (!docs) {
    return (
      <div className={`text-center py-8 text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        No documentation found for this component
      </div>
    );
  }

  // Build sections from available docs
  const sections: { key: string; label: string; content: string }[] = [];
  if (docs.readme) sections.push({ key: "readme", label: "README", content: docs.readme });
  if (docs.claude_md) sections.push({ key: "claude_md", label: "CLAUDE.md", content: docs.claude_md });
  if (docs.architecture_notes) sections.push({ key: "arch", label: "Architecture", content: docs.architecture_notes });
  if (docs.api_docs) sections.push({ key: "api", label: "API Docs", content: docs.api_docs });
  if (docs.changelog) sections.push({ key: "changelog", label: "Changelog", content: docs.changelog });

  if (sections.length === 0) {
    return (
      <div className={`text-center py-8 text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        No documentation files found
      </div>
    );
  }

  const activeSection = sections.find(s => s.key === docSection) || sections[0];

  return (
    <div className="flex flex-col h-full">
      {/* Doc section tabs */}
      {sections.length > 1 && (
        <div className={`flex gap-1 px-3 pt-2 pb-1 flex-wrap ${darkMode ? "border-b border-zinc-800" : "border-b border-zinc-100"}`}>
          {sections.map((sec) => (
            <button
              key={sec.key}
              onClick={() => setDocSection(sec.key)}
              className={`
                px-2 py-1 rounded text-[10px] font-medium transition-colors
                ${sec.key === activeSection.key
                  ? darkMode
                    ? "bg-blue-900/40 text-blue-300"
                    : "bg-blue-100 text-blue-700"
                  : darkMode
                    ? "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                    : "text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
                }
              `}
            >
              {sec.label}
            </button>
          ))}
        </div>
      )}

      {/* Doc content */}
      <div className="flex-1 overflow-y-auto p-4">
        <MarkdownRenderer content={activeSection.content} darkMode={darkMode} />
      </div>
    </div>
  );
}

function StatCard({ label, value, darkMode }: { label: string; value: string; darkMode: boolean }) {
  return (
    <div className={`px-3 py-2 rounded-lg ${darkMode ? "bg-zinc-800/50" : "bg-zinc-50"}`}>
      <div className={`text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
        {value}
      </div>
    </div>
  );
}

function ChildRow({ component }: { component: Component }) {
  const { darkMode, selectComponent, drillInto } = useArchStore();
  const colors = getTypeColors(component.type, darkMode);

  return (
    <button
      className={`
        w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm
        ${darkMode ? "hover:bg-zinc-800/50 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}
      `}
      onClick={() => selectComponent(component.id)}
      onDoubleClick={() => drillInto(component)}
    >
      <span className={`text-[9px] px-1 py-0.5 rounded ${colors.badge}`}>
        {TYPE_META[component.type]?.icon || component.type.slice(0, 3)}
      </span>
      <span className="truncate flex-1">{component.name}</span>
      {component.docs?.purpose && (
        <span className={`text-[10px] truncate max-w-[120px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {component.docs.purpose}
        </span>
      )}
      {component.metrics?.files > 0 && (
        <span className={`text-xs shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {component.metrics.files}f
        </span>
      )}
    </button>
  );
}

function FilesTab({ files, componentId }: { files: FileInfo[]; componentId: string }) {
  const { darkMode, showDetail, reviewMode, setAnnotatingTarget, annotations } = useArchStore();
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!filter) return files;
    const q = filter.toLowerCase();
    return files.filter((f) => f.path.toLowerCase().includes(q));
  }, [files, filter]);

  // Group by directory
  const grouped = useMemo(() => {
    const groups: Record<string, FileInfo[]> = {};
    for (const f of filtered) {
      const dir = f.path.split("/").slice(0, -1).join("/") || ".";
      (groups[dir] ??= []).push(f);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  return (
    <div className="p-3">
      <input
        type="text"
        placeholder="Filter files..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className={`
          w-full px-3 py-2 rounded-lg text-sm mb-3 outline-none
          ${darkMode
            ? "bg-zinc-800 text-zinc-200 placeholder-zinc-600 focus:ring-1 focus:ring-blue-500"
            : "bg-zinc-100 text-zinc-800 placeholder-zinc-400 focus:ring-1 focus:ring-blue-500"
          }
        `}
      />
      <div className="space-y-3">
        {grouped.map(([dir, dirFiles]) => (
          <div key={dir}>
            <div className={`text-[10px] font-mono px-2 py-1 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              {dir}
            </div>
            {dirFiles.map((f) => {
              const name = f.path.split("/").pop() || f.path;
              return (
                <button
                  key={f.path}
                  className={`
                    w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-sm
                    ${darkMode ? "hover:bg-zinc-800/50" : "hover:bg-zinc-100"}
                  `}
                  onClick={() => showDetail("file", f)}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: getLanguageColor(f.language) }}
                  />
                  <span className={`truncate flex-1 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                    {name}
                  </span>
                  {f.module_doc && (
                    <span className={`text-[9px] ${darkMode ? "text-green-600" : "text-green-500"}`} title={f.module_doc.split("\n")[0]}>
                      doc
                    </span>
                  )}
                  <span className={`text-[10px] tabular-nums ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    {f.lines}
                  </span>
                  {reviewMode && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setAnnotatingTarget({ type: "file", id: f.path, name: f.path, componentId });
                      }}
                      className={`shrink-0 w-5 h-5 flex items-center justify-center rounded text-[10px]
                        ${annotations.some((a) => a.targetType === "file" && a.targetId === f.path)
                          ? "bg-blue-500 text-white"
                          : darkMode ? "text-zinc-600 hover:text-blue-400 hover:bg-zinc-800" : "text-zinc-400 hover:text-blue-500 hover:bg-zinc-100"
                        }`}
                      title="Add review feedback"
                    >
                      {"\u270E"}
                    </button>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function SymbolsTab({
  symbols,
  expandedSymbol,
  setExpandedSymbol,
  componentId,
}: {
  symbols: ArchSymbol[];
  expandedSymbol: string | null;
  setExpandedSymbol: (s: string | null) => void;
  componentId: string;
}) {
  const { darkMode, reviewMode, setAnnotatingTarget, annotations } = useArchStore();
  const [filter, setFilter] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("all");

  const kinds = useMemo(() => {
    const set = new Set(symbols.map((s) => s.kind));
    return ["all", ...Array.from(set).sort()];
  }, [symbols]);

  const filtered = useMemo(() => {
    let result = symbols;
    if (kindFilter !== "all") {
      result = result.filter((s) => s.kind === kindFilter);
    }
    if (filter) {
      const q = filter.toLowerCase();
      result = result.filter((s) => s.name.toLowerCase().includes(q));
    }
    return result;
  }, [symbols, filter, kindFilter]);

  const kindIcons: Record<string, string> = {
    class: "C",
    struct: "S",
    enum: "E",
    protocol: "P",
    trait: "T",
    interface: "I",
    function: "f",
    type: "t",
    component: "R",
    impl: "i",
    extension: "x",
  };

  return (
    <div className="p-3">
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Filter symbols..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className={`
            flex-1 px-3 py-2 rounded-lg text-sm outline-none
            ${darkMode
              ? "bg-zinc-800 text-zinc-200 placeholder-zinc-600 focus:ring-1 focus:ring-blue-500"
              : "bg-zinc-100 text-zinc-800 placeholder-zinc-400 focus:ring-1 focus:ring-blue-500"
            }
          `}
        />
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          className={`
            px-2 py-2 rounded-lg text-sm outline-none
            ${darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-100 text-zinc-700"}
          `}
        >
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        {filtered.slice(0, 100).map((sym) => (
          <div key={sym.id}>
            <button
              className={`
                w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-sm
                ${darkMode ? "hover:bg-zinc-800/50" : "hover:bg-zinc-100"}
              `}
              onClick={() =>
                setExpandedSymbol(expandedSymbol === sym.id ? null : sym.id)
              }
            >
              <Tooltip content={SYMBOL_KIND_DESCRIPTIONS[sym.kind] || `Symbol kind: ${sym.kind}`}>
                <span
                  className={`
                    w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold shrink-0
                    ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-200 text-zinc-600"}
                  `}
                >
                  {kindIcons[sym.kind] || sym.kind[0]}
                </span>
              </Tooltip>
              <span className={`truncate flex-1 font-mono ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                {sym.name}
              </span>
              {sym.docstring && (
                <span className={`text-[9px] ${darkMode ? "text-green-600" : "text-green-500"}`}>doc</span>
              )}
              <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                L{sym.line}
              </span>
            </button>
            {expandedSymbol === sym.id && (
              <div className="ml-7 mt-1 mb-2">
                {sym.docstring && (
                  <div className={`
                    text-xs mb-2 px-2 py-1.5 rounded border-l-2
                    ${darkMode ? "border-blue-700 bg-blue-900/10 text-zinc-400" : "border-blue-300 bg-blue-50 text-zinc-600"}
                  `}>
                    {sym.docstring}
                  </div>
                )}
                <CodePreview code={sym.code_preview} language={sym.file.split(".").pop() || ""} />
                <div className={`flex items-center justify-between mt-1`}>
                  <div className={`text-[10px] font-mono ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    {sym.file}:{sym.line}
                  </div>
                  {reviewMode && (
                    <button
                      onClick={() => setAnnotatingTarget({ type: "symbol", id: sym.id, name: sym.name, componentId })}
                      className={`text-[10px] px-2 py-0.5 rounded flex items-center gap-1
                        ${annotations.some((a) => a.targetType === "symbol" && a.targetId === sym.id)
                          ? darkMode ? "bg-blue-500/20 text-blue-300" : "bg-blue-100 text-blue-600"
                          : darkMode ? "text-zinc-500 hover:text-blue-400 hover:bg-zinc-800" : "text-zinc-400 hover:text-blue-500 hover:bg-zinc-100"
                        }`}
                      title="Add review feedback for this symbol"
                    >
                      {"\u270E"} Feedback
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {filtered.length > 100 && (
          <div className={`text-xs text-center py-2 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            Showing 100 of {filtered.length} symbols
          </div>
        )}
      </div>
    </div>
  );
}

function RelationshipsTab({
  componentId,
  relationships,
}: {
  componentId: string;
  relationships: { source: string; target: string; type: string; label: string | null; port: number | null }[];
}) {
  const { darkMode, selectComponent, getComponentById } = useArchStore();

  const incoming = relationships.filter((r) => r.target === componentId);
  const outgoing = relationships.filter((r) => r.source === componentId);

  const RelRow = ({ rel, direction }: { rel: typeof relationships[0]; direction: "in" | "out" }) => {
    const otherId = direction === "in" ? rel.source : rel.target;
    const other = getComponentById(otherId);
    const typeColors: Record<string, string> = {
      import: darkMode ? "text-zinc-400" : "text-zinc-600",
      http: darkMode ? "text-blue-400" : "text-blue-600",
      websocket: darkMode ? "text-violet-400" : "text-violet-600",
      grpc: darkMode ? "text-emerald-400" : "text-emerald-600",
      ffi: darkMode ? "text-amber-400" : "text-amber-600",
    };

    return (
      <button
        className={`
          w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm
          ${darkMode ? "hover:bg-zinc-800/50" : "hover:bg-zinc-100"}
        `}
        onClick={() => selectComponent(otherId)}
      >
        <span className={`text-xs ${direction === "in" ? "text-emerald-400" : "text-blue-400"}`}>
          {direction === "in" ? "\u2190" : "\u2192"}
        </span>
        <span className={`flex-1 truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
          {other?.name || otherId}
        </span>
        <span className={`text-[10px] ${typeColors[rel.type] || ""}`}>
          {rel.type}
        </span>
        {rel.port && (
          <span className={`text-[10px] font-mono ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            :{rel.port}
          </span>
        )}
      </button>
    );
  };

  return (
    <div className="p-3 space-y-4">
      {outgoing.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Outgoing ({outgoing.length})
          </h4>
          <div className="space-y-1">
            {outgoing.map((rel, i) => (
              <RelRow key={i} rel={rel} direction="out" />
            ))}
          </div>
        </div>
      )}
      {incoming.length > 0 && (
        <div>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Incoming ({incoming.length})
          </h4>
          <div className="space-y-1">
            {incoming.map((rel, i) => (
              <RelRow key={i} rel={rel} direction="in" />
            ))}
          </div>
        </div>
      )}
      {incoming.length === 0 && outgoing.length === 0 && (
        <div className={`text-center py-8 text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          No relationships detected
        </div>
      )}
    </div>
  );
}

function FileDetail({ file }: { file: FileInfo }) {
  const { darkMode, closeDetail, architecture } = useArchStore();
  const symbols = useMemo(
    () => architecture?.symbols.filter((s) => file.symbols.includes(s.id)) || [],
    [architecture, file],
  );

  return (
    <div className="h-full flex flex-col">
      <div className={`px-4 pt-4 pb-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className={`font-bold text-lg ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {file.path.split("/").pop()}
            </h2>
            <p className={`text-xs font-mono mt-1 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              {file.path}
            </p>
          </div>
          <button
            onClick={closeDetail}
            className={`p-1 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-100 text-zinc-400"}`}
          >
            &#x2715;
          </button>
        </div>
        <div className="flex gap-4 mt-3">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: getLanguageColor(file.language) }} />
            <span className={`text-sm ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{file.language}</span>
          </div>
          <span className={`text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>{formatNumber(file.lines)} lines</span>
          <span className={`text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>{formatBytes(file.size_bytes)}</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* File-level documentation */}
        {file.module_doc && (
          <div>
            <h4 className={`text-xs font-semibold uppercase mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              File Documentation
            </h4>
            <div className={`
              text-xs px-3 py-2 rounded-lg border-l-2
              ${darkMode ? "border-blue-700 bg-blue-900/10 text-zinc-400" : "border-blue-300 bg-blue-50 text-zinc-600"}
            `}>
              {file.module_doc}
            </div>
          </div>
        )}

        {symbols.length > 0 && (
          <div>
            <h4 className={`text-xs font-semibold uppercase mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Symbols ({symbols.length})
            </h4>
            {symbols.map((sym) => (
              <div key={sym.id} className="mb-3">
                <div className={`text-sm font-mono mb-1 ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                  <span className={`${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>{sym.kind}</span>{" "}
                  {sym.name}
                  <span className={`ml-2 text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>L{sym.line}</span>
                </div>
                {sym.docstring && (
                  <div className={`
                    text-xs mb-1.5 px-2 py-1 rounded border-l-2
                    ${darkMode ? "border-green-700 bg-green-900/10 text-zinc-400" : "border-green-300 bg-green-50 text-zinc-600"}
                  `}>
                    {sym.docstring}
                  </div>
                )}
                <CodePreview code={sym.code_preview} language={file.language} />
              </div>
            ))}
          </div>
        )}
        {file.imports.length > 0 && (
          <div>
            <h4 className={`text-xs font-semibold uppercase mb-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Imports ({file.imports.length})
            </h4>
            <div className="flex flex-wrap gap-1">
              {file.imports.map((imp) => (
                <span
                  key={imp}
                  className={`text-xs px-2 py-1 rounded-md font-mono ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}
                >
                  {imp}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SymbolDetail({ symbol }: { symbol: ArchSymbol }) {
  const { darkMode, closeDetail } = useArchStore();

  return (
    <div className="h-full flex flex-col">
      <div className={`px-4 pt-4 pb-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className={`font-bold text-lg font-mono ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {symbol.name}
            </h2>
            <div className="flex gap-2 mt-1">
              <span className={`text-xs px-2 py-0.5 rounded-full ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}>
                {symbol.kind}
              </span>
              <span className={`text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                {symbol.visibility}
              </span>
            </div>
          </div>
          <button
            onClick={closeDetail}
            className={`p-1 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-100 text-zinc-400"}`}
          >
            &#x2715;
          </button>
        </div>
        <p className={`text-xs font-mono mt-2 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {symbol.file}:{symbol.line}-{symbol.end_line}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {symbol.docstring && (
          <div className={`
            text-sm mb-3 px-3 py-2 rounded-lg border-l-2
            ${darkMode ? "border-blue-700 bg-blue-900/10 text-zinc-300" : "border-blue-300 bg-blue-50 text-zinc-700"}
          `}>
            {symbol.docstring}
          </div>
        )}
        <CodePreview code={symbol.code_preview} language={symbol.file.split(".").pop() || ""} />
      </div>
    </div>
  );
}
