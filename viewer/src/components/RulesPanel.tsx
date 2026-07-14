import { useMemo, useState } from "react";
import { useArchStore } from "../store";
import {
  groupRulesByKind,
  decisionTableFromRule,
  ruleEntityId,
  ruleCapabilityId,
  RULE_KIND_ORDER,
} from "../lenses";
import { getSourceUrl } from "../utils/sourceLinks";
import type { Rule, Component, Evidence } from "../types";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The Rules lens surface (P6-6, LENS-DESIGN.md L6). The landing view is a ranked
// panel (invariant I11): rules grouped by kind (policy, validation, calculation,
// io) with counts, each kind expandable; within a kind, rules group by owning
// component ranked by rule count, so "what does this component enforce" reads
// directly. Each entry shows the mechanical summary, an inferred marker when the
// rule was shape-matched, and evidence file:line links. Selecting a rule opens the
// focused view: the mechanical summary or, for a decision-shaped policy rule, a
// small two-column decision table; the plain-language statement slot (Phase 7);
// inputs/outputs; evidence; and the two cross-lens jumps (view in Data lens for a
// rule that governs an entity, view in Capability lens for a rule that guards a
// contract). Selecting also selects the rule's owning component (I12).

const KIND_LABEL: Record<Rule["kind"], string> = {
  policy: "Policy / decision",
  validation: "Validation",
  calculation: "Calculation",
  io: "IO constraint",
};

const KIND_COLORS: Record<Rule["kind"], { light: string; dark: string }> = {
  policy: { light: "bg-indigo-100 text-indigo-700", dark: "bg-indigo-900/40 text-indigo-300" },
  validation: { light: "bg-emerald-100 text-emerald-700", dark: "bg-emerald-900/40 text-emerald-300" },
  calculation: { light: "bg-amber-100 text-amber-700", dark: "bg-amber-900/40 text-amber-300" },
  io: { light: "bg-sky-100 text-sky-700", dark: "bg-sky-900/40 text-sky-300" },
};

// Flatten the component tree into an id -> name map for labeling owners.
function buildNameMap(components: Component[]): Record<string, string> {
  const map: Record<string, string> = {};
  const walk = (list: Component[]) => {
    for (const c of list) {
      map[c.id] = c.name;
      if (c.children.length > 0) walk(c.children);
    }
  };
  walk(components);
  return map;
}

// A file:line evidence link with a GitHub source jump, mirroring the DetailPanel
// EvidenceLinks pattern so every rule drills to its exact lines (L6).
function EvidenceLinks({ evidence }: { evidence: Evidence[] }) {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  if (!evidence || evidence.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5">
      {evidence.map((ev, i) => {
        const link = architecture ? getSourceUrl(architecture, ev.file, ev.line ?? undefined) : null;
        const label = `${ev.file}${ev.line != null ? `:${ev.line}` : ""}`;
        return (
          <li key={`${ev.file}:${ev.line}:${i}`} className="flex items-center gap-1">
            <span className={`font-mono text-[10px] truncate ${darkMode ? "text-zinc-500" : "text-zinc-400"}`} title={label}>
              {label}
            </span>
            {link && (
              <Tooltip content={TOOLTIP_COPY.evidence.link} position="bottom">
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className={`shrink-0 inline-flex items-center ${darkMode ? "text-zinc-600 hover:text-blue-400" : "text-zinc-400 hover:text-blue-500"} transition-colors`}
                  aria-label={TOOLTIP_COPY.evidence.link}
                >
                  <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M4.5 1.5H2a.5.5 0 00-.5.5v8a.5.5 0 00.5.5h8a.5.5 0 00.5-.5V7.5M7 1.5h3.5V5M6 6l4.5-4.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </a>
              </Tooltip>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function InferredMarker({ darkMode }: { darkMode: boolean }) {
  return (
    <Tooltip content={TOOLTIP_COPY.rules.inferred}>
      <span
        className={`text-[9px] px-1 py-0.5 rounded uppercase tracking-wide ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-500"}`}
      >
        inferred
      </span>
    </Tooltip>
  );
}

// The Phase 7 plain-language statement slot (LENS-DESIGN L6, invariant I5). When
// enrichment has run, render the statement and, if the cited code has drifted, a
// staleness marker. Until then, render a clearly-shaped, muted placeholder so the
// slot is visibly present and lights up when statements land.
function StatementSlot({ rule, darkMode }: { rule: Rule; darkMode: boolean }) {
  const statement = rule.ai_enhance?.statement;
  const stale = rule.ai_enhance?.stale;
  if (statement) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            In plain language
          </div>
          {stale && (
            <Tooltip content={TOOLTIP_COPY.rules.stale} focusable>
              <span
                className={`text-[9px] px-1 py-0.5 rounded uppercase tracking-wide ${darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700"}`}
              >
                stale
              </span>
            </Tooltip>
          )}
        </div>
        <p className={`text-xs leading-relaxed ${stale ? (darkMode ? "text-zinc-500" : "text-zinc-400") : darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
          {statement}
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        In plain language
      </div>
      <p className={`text-[11px] italic ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
        A plain-language statement is generated by AI enrichment (Phase 7). Until then, the mechanical summary above is the source of truth.
      </p>
    </div>
  );
}

// The focused rule view: statement slot, decision table or mechanical summary,
// inputs/outputs, confidence, evidence, and the two cross-lens jumps.
function FocusedRule({ rule }: { rule: Rule }) {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const clearRule = useArchStore((s) => s.clearRule);
  const selectComponent = useArchStore((s) => s.selectComponent);
  const viewRuleInDataLens = useArchStore((s) => s.viewRuleInDataLens);
  const viewRuleInCapabilityLens = useArchStore((s) => s.viewRuleInCapabilityLens);

  const nameMap = useMemo(() => buildNameMap(architecture?.components ?? []), [architecture]);
  const owner = rule.component_id ? (nameMap[rule.component_id] ?? rule.component_id) : null;
  const table = decisionTableFromRule(rule);
  const entityId = ruleEntityId(rule);
  const capabilityId = ruleCapabilityId(rule);
  const colors = KIND_COLORS[rule.kind];
  const inputs = rule.detail.inputs ?? [];
  const outputs = rule.detail.outputs ?? [];

  return (
    <>
      <div className="px-3 pt-2.5">
        <button
          onClick={() => {
            clearRule();
            selectComponent(null);
          }}
          className={`text-[11px] flex items-center gap-1 rounded px-1.5 py-0.5 ${darkMode ? "text-zinc-400 hover:bg-zinc-900" : "text-zinc-500 hover:bg-white"}`}
        >
          {"‹"} Rules
        </button>
      </div>

      <div className="px-4 pt-2 pb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Tooltip content={TOOLTIP_COPY.rules.kind} focusable>
            <span className={`text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wide ${darkMode ? colors.dark : colors.light}`}>
              {rule.kind}
            </span>
          </Tooltip>
          {rule.confidence === "inferred" && <InferredMarker darkMode={darkMode} />}
        </div>
        {owner && (
          <p className={`mt-1 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            enforced in {owner}
          </p>
        )}
      </div>

      {/* Mechanical summary or decision table (L6): render branching AS A TABLE. */}
      <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
        <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {table ? "Decision table" : "Mechanical summary"}
        </div>
        {table ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] border-collapse">
              <thead>
                <tr className={darkMode ? "text-zinc-500" : "text-zinc-400"}>
                  <th className={`text-left font-medium py-1 pr-2 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
                    Case
                  </th>
                  <th className={`text-left font-medium py-1 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
                    Matches when
                  </th>
                </tr>
              </thead>
              <tbody>
                {table.branches.map((branch, i) => (
                  <tr key={`${branch}-${i}`}>
                    <td className={`font-mono py-1 pr-2 align-top ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                      {branch}
                    </td>
                    <td className={`font-mono py-1 align-top ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                      {table.subject} == {branch}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={`font-mono text-[11px] leading-relaxed break-words ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
            {rule.summary}
          </p>
        )}
      </div>

      {/* Plain-language statement slot (Phase 7, I5). */}
      <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <StatementSlot rule={rule} darkMode={darkMode} />
      </div>

      {/* Cross-lens jumps (L6): what governs this data, what guards this contract. */}
      {(entityId || capabilityId) && (
        <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-1.5`}>
          <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Related
          </div>
          {entityId && (
            <button
              onClick={() => viewRuleInDataLens(rule.id)}
              className={`w-full text-left text-[11px] rounded px-2 py-1.5 flex items-center gap-1.5 ${darkMode ? "bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20" : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"}`}
              title={entityId}
            >
              {"\u{1F5C4}"} View in Data lens {"→"}
            </button>
          )}
          {capabilityId && (
            <button
              onClick={() => viewRuleInCapabilityLens(rule.id)}
              className={`w-full text-left text-[11px] rounded px-2 py-1.5 flex items-center gap-1.5 ${darkMode ? "bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20" : "bg-cyan-50 text-cyan-700 hover:bg-cyan-100"}`}
              title={capabilityId}
            >
              {"\u{1F6E0}"} View in Capability lens {"→"}
            </button>
          )}
        </div>
      )}

      {/* Inputs and outputs (the data elements the rule reads and constrains). */}
      {(inputs.length > 0 || outputs.length > 0) && (
        <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
          {inputs.length > 0 && (
            <div>
              <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                Inputs ({inputs.length})
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {inputs.map((v, i) => (
                  <span key={`${v}-${i}`} className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>
                    {v}
                  </span>
                ))}
              </div>
            </div>
          )}
          {outputs.length > 0 && (
            <div>
              <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                Outputs ({outputs.length})
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {outputs.map((v, i) => (
                  <span key={`${v}-${i}`} className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>
                    {v}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Evidence: every rule drills to its exact lines (L6). */}
      <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          Evidence
        </div>
        <EvidenceLinks evidence={rule.evidence} />
      </div>
    </>
  );
}

// One rule row in the landing view: mechanical summary, inferred marker, evidence.
function RuleRow({ rule, selected }: { rule: Rule; selected: boolean }) {
  const darkMode = useArchStore((s) => s.darkMode);
  const selectRule = useArchStore((s) => s.selectRule);
  const entityId = ruleEntityId(rule);
  const capabilityId = ruleCapabilityId(rule);
  return (
    <li>
      <button
        onClick={() => selectRule(rule.id)}
        className={`w-full text-left rounded-lg px-2.5 py-1.5 transition-colors ${
          selected
            ? darkMode ? "bg-indigo-500/15 ring-1 ring-indigo-500/40" : "bg-indigo-50 ring-1 ring-indigo-300"
            : darkMode ? "hover:bg-zinc-900" : "hover:bg-white"
        }`}
      >
        <div className="flex items-start gap-1.5">
          <span className={`flex-1 text-[11px] font-mono leading-snug break-words ${darkMode ? "text-zinc-200" : "text-zinc-800"}`} title={rule.id}>
            {rule.summary}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-1.5 flex-wrap">
          {rule.confidence === "inferred" && <InferredMarker darkMode={darkMode} />}
          {entityId && (
            <Tooltip content={TOOLTIP_COPY.rules.dataTag}>
              <span className={`text-[9px] px-1 py-0.5 rounded ${darkMode ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-100 text-emerald-700"}`}>
                data
              </span>
            </Tooltip>
          )}
          {capabilityId && (
            <Tooltip content={TOOLTIP_COPY.rules.contractTag}>
              <span className={`text-[9px] px-1 py-0.5 rounded ${darkMode ? "bg-cyan-500/15 text-cyan-300" : "bg-cyan-100 text-cyan-700"}`}>
                contract
              </span>
            </Tooltip>
          )}
        </div>
        <EvidenceLinks evidence={rule.evidence} />
      </button>
    </li>
  );
}

export function RulesPanel() {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const selectedRuleId = useArchStore((s) => s.selectedRuleId);
  const getRules = useArchStore((s) => s.getRules);

  const rules = getRules();
  const groups = useMemo(() => groupRulesByKind(rules), [rules]);
  const nameMap = useMemo(() => buildNameMap(architecture?.components ?? []), [architecture]);

  const focused = selectedRuleId ? rules.find((r) => r.id === selectedRuleId) : null;

  // Which kind groups are collapsed. Default: all expanded so the reader sees the
  // whole surface at once (I11 landing).
  const [collapsed, setCollapsed] = useState<Set<Rule["kind"]>>(new Set());
  const toggle = (kind: Rule["kind"]) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  const containerClass = `hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
    darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
  }`;

  const header = (
    <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
      <div className="flex items-center gap-1.5">
        <span>{"⚖️"}</span>
        <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Rules</h2>
      </div>
      <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        {rules.length} rule{rules.length === 1 ? "" : "s"} the system enforces
      </p>
    </div>
  );

  if (focused) {
    return (
      <div className={containerClass}>
        {header}
        <div className="flex-1 overflow-y-auto">
          <FocusedRule rule={focused} />
        </div>
      </div>
    );
  }

  return (
    <div className={containerClass}>
      {header}
      <div className={`px-4 py-2.5 text-[11px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
        Grouped by kind; within a kind, by the component that enforces the most.
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-3">
        {groups.length === 0 && (
          <div className={`text-xs text-center py-6 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            No rules in this dataset.
          </div>
        )}
        {groups.map((group) => {
          const isCollapsed = collapsed.has(group.kind);
          return (
            <div key={group.kind}>
              <button
                onClick={() => toggle(group.kind)}
                className={`w-full flex items-center justify-between px-2 py-1 rounded ${darkMode ? "hover:bg-zinc-900" : "hover:bg-white"}`}
              >
                <span className={`text-[11px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
                  {KIND_LABEL[group.kind]} ({group.count})
                </span>
                <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                  {isCollapsed ? "▸" : "▾"}
                </span>
              </button>
              {!isCollapsed && (
                <div className="mt-1 space-y-2">
                  {group.components.map((cg) => {
                    const owner = cg.componentId ? (nameMap[cg.componentId] ?? cg.componentId) : "unowned";
                    return (
                      <div key={cg.componentId || "__unowned__"}>
                        <div className={`px-2 py-0.5 text-[10px] flex items-center justify-between ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                          <span className="truncate" title={owner}>{owner}</span>
                          <Tooltip content={TOOLTIP_COPY.rules.ownerCount} focusable>
                            <span className={`shrink-0 tabular-nums px-1 rounded ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}>
                              {cg.count}
                            </span>
                          </Tooltip>
                        </div>
                        <ul className="space-y-1">
                          {cg.items.map((rule) => (
                            <RuleRow key={rule.id} rule={rule} selected={rule.id === selectedRuleId} />
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className={`px-4 py-2 border-t shrink-0 text-[10px] ${darkMode ? "border-zinc-800 text-zinc-600" : "border-zinc-200 text-zinc-400"}`}>
        Ranked {RULE_KIND_ORDER.map((k) => KIND_LABEL[k]).join(" · ")}; select a rule to audit it.
      </div>
    </div>
  );
}
