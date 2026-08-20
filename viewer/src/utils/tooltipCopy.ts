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
      "excluded:generated":
        "This tool's own emitted architecture dataset committed into the tree. Machine output, not source.",
      "excluded:gitignored":
        "Excluded by the repo's .gitignore, so it exists only on this workstation and never reaches the central repo. Not source.",
      "excluded:tool_state":
        "This tool's own state directory, .solution-explorer. Accounted as one row and never scanned as source.",
      unknownExcluded:
        "Excluded by a rule. Treated as a gap until confirmed to be non-source.",
    },
  },

  // The non-source inventory (P6-10). Reached from the coverage drill-in's
  // NON-SOURCE ACCOUNTED family. Every line explains itself in plain language.
  inventory: {
    explore:
      "Open the non-source inventory: what every non-source file is, why it is probably here, and what to do about it.",
    group: "A category of non-source files, ranked by how many there are.",
    recommendation: "A high-level suggestion for this whole group. No AI required.",
    count: "How many non-source files fell into this category.",
    bytes: "Total size of this group's files on disk, when the tree was available to measure.",
    securitySensitive:
      "Shaped like a certificate, key, or credential. Verify none of these are real secrets.",
    likelyUnwanted: "Probably should not be in version control. See the recommendation.",
    gitignoreCandidate: "Not yet covered by .gitignore, and probably should be.",
    directoryRows:
      "One row here stands for a whole pruned directory, not a single file. Its full contents are not enumerated.",
    dominant:
      "This one group is most of your non-source files. When it dwarfs your source, that is itself worth a look.",
    sample:
      "A sample of this group's files. Open any path to jump to it. The complete list is in the coverage ledger.",
    projectRule:
      "Classified by a rule this project taught itself. The tool learned what this is and remembers it deterministically, no AI at read time.",
    projectRuleRow:
      "This file was classified by a rule this project taught itself, not a built-in guess.",
  },

  // The findings entry bar and each finding's badges.
  findings: {
    entry:
      "Correlations the system noticed on its own: duplication, orphans, inconsistencies. Ranked, evidenced, and checkable.",
    kind: {
      duplication: "Near-duplicate code the system found. A candidate for consolidation.",
      orphan: "Not reachable from any entry point. Possibly dead code.",
      unreferenced: "No reference detected by the current extractors. Often an extractor blind spot rather than dead code; check the symbol and churn counts.",
      inconsistency: "Members of one concern that follow different patterns.",
      cra_readiness: "A repo-observable EU CRA readiness gap: an expected artifact (SECURITY.md, disclosure contact, SBOM, update config, or support statement) is absent. Not a conformity assessment; see cra-readiness.json for the full checklist and scope.",
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

  // The supply chain surface and SBOM (P10-1). Every line explains itself; the
  // scope note states plainly this is an inventory, not a security scan.
  supplyChain: {
    entry:
      "Open the supply chain: every dependency this repo declares or locks, with versions and pin status.",
    scopeNote:
      "An inventory of dependencies and versions. Not a vulnerability scan: no security claim is made.",
    ecosystem: "A package ecosystem the repo uses, with its dependency and pin counts.",
    target:
      "A language runtime or SDK version this repo targets, called out separately from the packages.",
    pinExact: "Locked to one exact version. The build cannot drift.",
    pinRange: "A version range. An update can move within it.",
    pinUnpinned: "No version constraint. The resolved version can change freely.",
    direct: "Declared directly in a manifest this repo authored.",
    transitive: "Pulled in only as a dependency of a dependency, through a lockfile.",
    version: "The resolved version from a lockfile, when one is present.",
    declared: "The version constraint as written in the manifest.",
    sbomLink: "The full CycloneDX 1.5 SBOM document for interchange with other tooling.",
    // Not "from the coverage inventory": vendored entries here come from the
    // supply-chain pass directly and can be non-empty even when the dataset
    // carries no coverage ledger at all, so the copy must not point the
    // reader at a drill-down that may not exist (O4).
    vendored: "Third-party code checked into this repo.",
    warning: "A manifest that was found but could not be parsed. Its dependencies are missing here.",
    fixture:
      "Dependencies from manifests under test or fixture directories. Accounted here but not counted as shipping dependencies.",
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
  "inventory.explore",
  "inventory.group",
  "inventory.recommendation",
  "inventory.securitySensitive",
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
  "supplyChain.entry",
  "supplyChain.scopeNote",
  "supplyChain.pinStatus",
  "supplyChain.scope",
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
