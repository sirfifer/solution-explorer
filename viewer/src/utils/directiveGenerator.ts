/**
 * Directive generation (P6-9, LENS-DESIGN section 10).
 *
 * A directive is the export of a selection set plus its set-level annotation. It
 * is NOT a prose prompt paragraph, it is a STRUCTURED work order for an AI
 * executor: the intent stated once, an ordered member list with each member's
 * file, lines, and available evidence, the exemptions (members the user removed,
 * each with a required reason), and the acceptance criteria. Directives ride the
 * prompt-generator pipeline (copy to clipboard, hand to Claude Code) but become
 * the primary artifact.
 *
 * The output is markdown for a human reader AND a fenced, machine-readable JSON
 * block embedded in it so an AI executor (or the MCP surface) can parse the work
 * order deterministically. The JSON schema is versioned and documented below.
 */
import type {
  Architecture,
  SelectionSet,
  SetAnnotation,
  SetMember,
} from "../types";

// Stable, versioned schema id for the embedded JSON block. An AI executor keys
// on this to know the shape it is parsing. Bump the version on any breaking
// change to DirectiveModel.
export const DIRECTIVE_SCHEMA = "solution-explorer.directive/v1";

/** One member of the directive's ordered work list. */
export interface DirectiveMember {
  ref: string;
  kind: SetMember["kind"];
  component_id: string;
  label: string;
  file: string | null;
  line_start: number | null;
  line_end: number | null;
  // Human-readable evidence lines (clone class, concern signal, capability/rule
  // kind, component path). May be empty for a bare manual member.
  evidence: string[];
  // The per-member note from the set annotation, if any.
  note: string | null;
  // True when the member's owning component is no longer present in the current
  // architecture (an orphan). Kept in the directive, never dropped, so the
  // executor sees it and the human is not silently robbed of a member (P1-3).
  orphaned: boolean;
}

/** A member the user removed from the work order, with the required reason. */
export interface DirectiveExemption {
  ref: string;
  label: string;
  reason: string;
}

/**
 * The machine-readable work order. This is exactly what the fenced JSON block
 * carries, so an executor parses `members` to know the work and `exemptions` to
 * know what to leave alone.
 */
export interface DirectiveModel {
  schema: typeof DIRECTIVE_SCHEMA;
  generated_at: string;
  generator: string;
  set: { id: string; name: string; origin: string };
  intent: string;
  members: DirectiveMember[];
  exemptions: DirectiveExemption[];
  acceptance_criteria: string[];
}

export interface DirectiveOptions {
  // Member ref -> reason. A member listed here is exempt (moved out of the work
  // list into `exemptions`). A reason is required; an empty/blank reason is
  // treated as not-exempt so the export never carries an unjustified exemption.
  exemptions?: Record<string, string>;
  // Extra acceptance criteria typed by the user, one per line. Merged with the
  // origin-derived auto-suggestions, de-duplicated, order preserved.
  acceptanceCriteria?: string[];
}

/**
 * Auto-suggested acceptance criteria derived from the set's origin. A
 * concern-origin set suggests "all members share one implementation of the
 * concern"; a duplication finding suggests extraction; an orphan finding
 * suggests wiring-or-removal. Manual and search sets get none (the user states
 * their own). Returns an empty list when nothing sensible can be suggested.
 */
export function suggestAcceptanceCriteria(origin: string): string[] {
  if (origin.startsWith("concern:")) {
    // origin is the concern id, "concern:<kind>", so the bare kind is the suffix.
    const bare = origin.slice("concern:".length);
    switch (bare) {
      case "logging":
        return ["All members log through the same shared logger, with the level read from configuration."];
      case "auth":
        return ["All members enforce authorization through the same shared guard, with no bespoke checks."];
      case "caching":
        return ["All members read and write the cache through one shared caching layer."];
      case "configuration":
        return ["All members read configuration through one shared config surface, not ad hoc lookups."];
      case "persistence":
        return ["All members reach persistence through the same repository/data-access layer."];
      case "http-client":
        return ["All members make outbound HTTP calls through one shared client with shared retry and timeout policy."];
      default:
        return [`All members route ${bare} through a single shared implementation.`];
    }
  }
  if (origin.startsWith("finding:duplication")) {
    return ["The duplicated logic is extracted into one shared implementation and every member calls it."];
  }
  if (origin.startsWith("finding:orphan") || origin.startsWith("finding:unreferenced")) {
    return ["Each unreferenced member is either confirmed reachable (an extractor blind spot) or removed with a recorded justification."];
  }
  return [];
}

function isExempt(ref: string, options: DirectiveOptions): string | null {
  const reason = options.exemptions?.[ref];
  if (typeof reason === "string" && reason.trim().length > 0) return reason.trim();
  return null;
}

// Resolve extra evidence lines for a member from the architecture: the owning
// component's path, plus any capabilities or rules the analyzer attributed to it.
// The member already carries origin-specific evidence (clone class, concern
// signal); this adds cross-lens facts (I15 evidence) when the member carries a
// resolvable componentId.
function resolveArchitectureEvidence(
  member: SetMember,
  architecture: Architecture,
): { lines: string[]; orphaned: boolean } {
  const lines: string[] = [];
  const comp = findComponent(architecture.components, member.componentId);
  if (!comp) {
    return { lines, orphaned: true };
  }
  if (comp.path && comp.path !== member.file) {
    lines.push(`component: ${comp.name} (\`${comp.path}\`)`);
  }
  const caps = (architecture.capabilities ?? []).filter(
    (c) => c.component_id === member.componentId,
  );
  for (const c of caps.slice(0, 3)) {
    lines.push(`capability: ${c.kind} ${c.name}`);
  }
  const rules = (architecture.rules ?? []).filter(
    (r) => r.component_id === member.componentId,
  );
  for (const r of rules.slice(0, 3)) {
    lines.push(`rule: ${r.kind} ${r.summary}`);
  }
  return { lines, orphaned: false };
}

function findComponent(
  components: Architecture["components"],
  id: string,
): Architecture["components"][number] | null {
  for (const comp of components) {
    if (comp.id === id) return comp;
    const found = findComponent(comp.children, id);
    if (found) return found;
  }
  return null;
}

/**
 * Build the structured directive model from a set, its annotation, and the
 * architecture. Exempt members are moved into `exemptions`; the rest become the
 * ordered work list, each carrying its file, lines, and evidence. Acceptance
 * criteria combine the origin auto-suggestions with the user's free text.
 */
export function buildDirectiveModel(
  set: SelectionSet,
  annotation: SetAnnotation | null,
  architecture: Architecture,
  options: DirectiveOptions = {},
  now: () => string = () => new Date().toISOString(),
): DirectiveModel {
  const noteByRef = new Map<string, string>();
  for (const n of annotation?.memberNotes ?? []) {
    if (n.note.trim().length > 0) noteByRef.set(n.memberRef, n.note.trim());
  }

  const members: DirectiveMember[] = [];
  const exemptions: DirectiveExemption[] = [];

  for (const m of set.members) {
    const reason = isExempt(m.ref, options);
    if (reason) {
      exemptions.push({ ref: m.ref, label: m.label, reason });
      continue;
    }
    const arch = resolveArchitectureEvidence(m, architecture);
    const evidence = [...(m.evidence ?? []), ...arch.lines];
    members.push({
      ref: m.ref,
      kind: m.kind,
      component_id: m.componentId,
      label: m.label,
      file: m.file ?? null,
      line_start: m.lineStart ?? null,
      line_end: m.lineEnd ?? null,
      evidence,
      note: noteByRef.get(m.ref) ?? null,
      orphaned: arch.orphaned,
    });
  }

  const auto = suggestAcceptanceCriteria(set.origin);
  const free = (options.acceptanceCriteria ?? [])
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const acceptance_criteria: string[] = [];
  for (const c of [...auto, ...free]) {
    if (!acceptance_criteria.includes(c)) acceptance_criteria.push(c);
  }

  return {
    schema: DIRECTIVE_SCHEMA,
    generated_at: now(),
    generator: "solution-explorer viewer (P6-9 directive)",
    set: { id: set.id, name: set.name, origin: set.origin },
    intent: (annotation?.intent ?? "").trim(),
    members,
    exemptions,
    acceptance_criteria,
  };
}

/**
 * Render the directive as markdown with the machine-readable JSON block embedded
 * at the end. The human sections read top to bottom; the fenced ```json block is
 * the canonical, parseable work order for an AI executor.
 */
export function renderDirectiveMarkdown(
  model: DirectiveModel,
  architectureName: string,
): string {
  const lines: string[] = [];

  lines.push(`# Directive: ${model.set.name}`);
  lines.push("");
  lines.push(`Architecture: ${architectureName}`);
  lines.push(`Set origin: ${model.set.origin}`);
  lines.push(`Members in scope: ${model.members.length}` + (model.exemptions.length > 0 ? ` (plus ${model.exemptions.length} exempt)` : ""));
  lines.push("");

  lines.push("## Intent");
  lines.push("");
  lines.push(model.intent.length > 0 ? model.intent : "_No intent stated. State the shared intent before executing this directive._");
  lines.push("");

  lines.push("## Members");
  lines.push("");
  if (model.members.length === 0) {
    lines.push("_No members in scope. Every member is exempt._");
    lines.push("");
  } else {
    let i = 0;
    for (const m of model.members) {
      i++;
      const loc = m.file
        ? m.line_start != null
          ? `\`${m.file}:${m.line_start}${m.line_end != null && m.line_end !== m.line_start ? `-${m.line_end}` : ""}\``
          : `\`${m.file}\``
        : "_no file location_";
      lines.push(`### ${i}. ${m.label}${m.orphaned ? " (orphaned)" : ""}`);
      lines.push(`- Location: ${loc}`);
      lines.push(`- Kind: ${m.kind} | Component: \`${m.component_id}\``);
      if (m.orphaned) {
        lines.push("- Note: this member's component is no longer present in the current architecture. Confirm it still exists before acting.");
      }
      if (m.evidence.length > 0) {
        lines.push("- Evidence:");
        for (const e of m.evidence) lines.push(`  - ${e}`);
      }
      if (m.note) {
        lines.push(`- Member note: ${m.note}`);
      }
      lines.push("");
    }
  }

  if (model.exemptions.length > 0) {
    lines.push("## Exemptions");
    lines.push("");
    lines.push("These members are deliberately left untouched. Do not change them.");
    lines.push("");
    for (const e of model.exemptions) {
      lines.push(`- **${e.label}** (\`${e.ref}\`): ${e.reason}`);
    }
    lines.push("");
  }

  lines.push("## Acceptance criteria");
  lines.push("");
  if (model.acceptance_criteria.length === 0) {
    lines.push("_None stated. Add the conditions this directive must satisfy to be considered done._");
  } else {
    for (const c of model.acceptance_criteria) lines.push(`- ${c}`);
  }
  lines.push("");

  lines.push("## Machine-readable work order");
  lines.push("");
  lines.push(`The block below is the canonical directive for an AI executor. Schema \`${model.schema}\`: \`intent\` (string), \`members\` (each with \`ref\`, \`kind\`, \`component_id\`, \`label\`, \`file\`, \`line_start\`, \`line_end\`, \`evidence\`, \`note\`, \`orphaned\`), \`exemptions\` (each with \`ref\`, \`label\`, \`reason\`), and \`acceptance_criteria\` (string list).`);
  lines.push("");
  lines.push("```json");
  lines.push(JSON.stringify(model, null, 2));
  lines.push("```");
  lines.push("");
  lines.push("Generated by solution-explorer architecture viewer.");

  return lines.join("\n");
}

/**
 * Convenience: build the model and render it in one call. Returns both the
 * markdown (for copy/download) and the model (for callers that want the JSON).
 */
export function generateDirective(
  set: SelectionSet,
  annotation: SetAnnotation | null,
  architecture: Architecture,
  options: DirectiveOptions = {},
): { markdown: string; model: DirectiveModel } {
  const model = buildDirectiveModel(set, annotation, architecture, options);
  return { markdown: renderDirectiveMarkdown(model, architecture.name), model };
}
