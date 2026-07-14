// Central tooltip copy for the v2-era surfaces (the tooltip sweep).
//
// One place for every context tooltip so the copy is auditable, testable, and
// consistent. Every string is written to the project rule: minimum words, fully
// conveyed, no jargon without its meaning, and no em or en dashes.
//
// Surfaces render these through the shared Tooltip component (see Tooltip.tsx),
// never a second tooltip system. The tooltip-presence test sweep imports
// TOOLTIP_COPY and asserts every leaf is non-empty, and enumerates the surfaces
// each group covers.

export const TOOLTIP_COPY = {
  // The lens switcher. Each option's tooltip is the lens's own one-line
  // description (pulled live from the lens definition), so this group only holds
  // the switcher control itself.
  lens: {
    switcher: "Change how you look at the code without losing your place.",
  },

  // The coverage badge and its drill-in panel. The three families and every
  // disposition each explain themselves in one line.
  coverage: {
    percent:
      "Parsed source divided by all analyzable source. Non-source files are not in this denominator.",
    nonSourceCount: "Non-source files recorded but never counted against coverage.",
    gapCount: "Analyzable source the analyzer did not parse. Each one is a real gap.",
    familyAnalyzed: "Source files the analyzer parsed successfully.",
    familyGaps:
      "Analyzable source the analyzer could not parse or was told to skip. Counted against the percent.",
    familyNonSource:
      "Files with no code to analyze. Recorded so nothing is silently missing. Never counted against the percent.",
    disposition: {
      parsed: "Parsed successfully into the model.",
      failed: "The parser hit an error on this file. A real gap in coverage.",
      "excluded:max_file_size":
        "Skipped for exceeding the size limit. This is analyzable source, so it counts against coverage.",
      binary:
        "Images, media, and other non-text files. Recorded so nothing is silently missing; they contain no code to analyze.",
      "excluded:unsupported_extension":
        "A file type the analyzer has no parser for. No code to analyze.",
      "excluded:empty_file": "An empty file. Nothing to analyze.",
      "excluded:skipped_directory":
        "Inside a pruned directory such as node_modules or .git. Not your source.",
      "excluded:vendored_repo": "Third-party code vendored into the tree. Not your source.",
      unknownExcluded:
        "Excluded by a rule. Treated as a gap until confirmed to be non-source.",
    },
  },

  // The findings entry bar and each finding's badges.
  findings: {
    entry:
      "Correlations the system noticed on its own: duplication, orphans, inconsistencies. Ranked, evidenced, and checkable.",
    kind: {
      duplication: "Near-duplicate code the system found. A candidate for consolidation.",
      orphan: "Not reachable from any entry point. Possibly dead code.",
      inconsistency: "Members of one concern that follow different patterns.",
    },
    verification: {
      verified: "Checked against its own evidence and it held up. Treat as fact.",
      refuted: "Checked and it failed its own evidence. Shown for transparency, not asserted.",
      unverified:
        "Automatically detected but not yet adversarially checked; treat as a lead, not a fact.",
    },
    confidence: "How strongly the signals support this finding.",
    rankScore: "Priority score. Higher means look here first.",
    memberCount: "How many code sites this finding spans.",
  },

  // Concern rows and their detection basis.
  concern: {
    row: "A cross-cutting concern: every place that touches one shared responsibility.",
    basis: "The signals that grouped these members: imports, API use, or naming.",
    slug: "Mechanical slug. A plain-language name lands with enrichment.",
    memberCount: "How many components belong to this concern.",
  },

  // Activity lens metrics.
  activity: {
    hotspotScore:
      "How often this changes times how big it is; where change is concentrated.",
    busFactor: "The fewest authors who wrote half the commits. Low means fragile knowledge.",
    knowledgeIsland:
      "One author holds almost all the history here. If they leave, the knowledge goes with them.",
    authorCount: "Distinct authors who have committed here.",
    commitCount: "Commits that touched this component.",
    couplingCount: "Commits that changed this component and the other one together.",
    churn: "Change volume: lines added plus lines removed.",
  },

  // Rules lens badges and markers.
  rules: {
    kind: "What kind of rule this is: policy, validation, calculation, or io constraint.",
    inferred: "Shape-matched, not declared. Read it as a strong guess, not certainty.",
    stale: "The cited code changed since this statement was written. It may be out of date.",
    ownerCount: "Rules of this kind enforced by this component.",
    dataTag: "This rule governs a data entity. Open it in the Data lens.",
    contractTag: "This rule guards a capability. Open it in the Capability lens.",
  },

  // Capability lens badges.
  capability: {
    kind: "What kind of capability: an API route, CLI command, event, or job.",
    tested: "A test exercises this capability's route or command.",
    untested: "No test references this capability. It is unproven.",
  },

  // Evidence file:line links, shared across surfaces.
  evidence: {
    link: "Opens the exact source lines this claim is based on.",
  },

  // Tours entry and stale markers.
  tours: {
    entry: "Guided walkthroughs of the codebase, one step at a time.",
    stale:
      "This walkthrough's anchored code has drifted since it was generated. Read it with care.",
  },

  // Directive export and exemption controls.
  directive: {
    export:
      "Copies a structured work order for an AI executor: the intent, members, files, lines, and acceptance criteria.",
    exemption: "Uncheck to leave a member out of the work order. A reason is required.",
    acceptance: "Conditions this directive must satisfy to be considered done.",
  },

  // The rationale strip fields (the colleague stand-in).
  rationale: {
    role: "The architectural role inferred for this element.",
    aiIntent: "AI-written intent for this element. Full text in the AI Insights tab.",
    author: "The lead author here, by share of commits.",
    lastChange: "When this element was last modified.",
    churn: "Change volume: lines added plus lines removed.",
    commit: "The most recent commit that touched this element.",
    pr: "The pull request that introduced this element.",
  },
} as const;

// The surfaces the sweep covers, named for the coverage assertion in the
// tooltip-presence test. Each entry is one named surface from the directive.
export const SWEPT_SURFACES = [
  "lens.switcher",
  "coverage.percent",
  "coverage.families",
  "coverage.dispositions",
  "findings.entry",
  "findings.kind",
  "findings.verification",
  "findings.confidence",
  "concern.row",
  "concern.basis",
  "activity.hotspotScore",
  "activity.busFactor",
  "activity.knowledgeIsland",
  "activity.couplingCount",
  "rules.kind",
  "rules.inferred",
  "capability.kind",
  "capability.tested",
  "evidence.link",
  "tours.stale",
  "directive.export",
  "directive.exemption",
  "rationale.fields",
] as const;

// A disposition's tooltip copy. Unknown strings never borrow the "parsed"
// copy: classifyDisposition counts every unrecognized disposition as a gap, so
// the fallback says exactly that (the copy and the math must agree).
export function dispositionTooltip(disposition: string): string {
  const known = TOOLTIP_COPY.coverage.disposition as Record<string, string>;
  if (known[disposition]) return known[disposition];
  if (disposition.startsWith("failed")) return known.failed;
  return known.unknownExcluded;
}
