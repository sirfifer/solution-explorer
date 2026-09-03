// Architecture data model - matches Python analyzer output

export interface Symbol {
  id: string;
  name: string;
  kind: string;
  file: string;
  line: number;
  end_line: number;
  code_preview: string;
  visibility: string;
  docstring: string | null;
  parent: string | null;
  dependencies: string[];
}

export interface FileInfo {
  path: string;
  language: string;
  lines: number;
  size_bytes: number;
  symbols: string[];
  imports: string[];
  exports: string[];
  module_doc: string | null;
}

export interface ComponentConfig {
  type: string;
  path: string;
  [key: string]: unknown;
}

export interface ComponentMetrics {
  files: number;
  lines: number;
  size_bytes: number;
  symbols: number;
  languages: Record<string, number>;
}

export interface ApiEndpoint {
  method: string;
  path: string;
}

export interface ComponentDoc {
  readme: string | null;
  claude_md: string | null;
  changelog: string | null;
  api_docs: string | null;
  architecture_notes: string | null;
  purpose: string | null;
  key_decisions: string[];
  patterns: string[];
  tech_stack: string[];
  env_vars: string[];
  api_endpoints: ApiEndpoint[];
}

export interface ExternalService {
  name: string;
  category: string;
}

export interface ComponentTesting {
  test_files: number;
  test_lines: number;
  unit_tests: number;
  integration_tests: number;
  e2e_tests: number;
  test_frameworks: string[];
  coverage_percent: number | null;
  coverage_source: string | null;
  has_ci_tests: boolean;
}

// Capabilities and data entities (optional, present only for v2 projections that
// ran the P5-1 capability pass and the P5-2 entity pass). All keys are additive:
// a dataset without them renders identically (every consumer uses optional
// access). Shapes match the derived arch dict exactly (see analyzer/derive/
// capabilities.py and entities.py to_dict).

// A single piece of evidence for a capability, entity, or access edge: the file
// and line where the fact was observed, plus the source line snippet.
export interface Evidence {
  file: string;
  line: number | null;
  snippet: string;
}

// A test file that textually references a capability's route path (api) or
// command name (cli). Groundwork for the L2 "test linkage is the proof bridge";
// the full linkage lens is P6-3. Rides in capability.detail.tests.
export interface CapabilityTestLink {
  file: string;
  line: number;
  confidence: "certain" | "inferred";
}

// The structured contract for a capability. Fields present depend on kind:
// api carries method/path/framework; cli carries command/framework/flags;
// event carries topic/direction; job carries name/framework/trigger. `symbol`
// is the defining symbol id where resolvable; `tests` is the L2 linkage.
export interface CapabilityDetail {
  // api
  method?: string;
  path?: string;
  // cli
  command?: string;
  flags?: string[];
  // event
  topic?: string;
  direction?: string;
  // job (name also used as the job label)
  name?: string;
  trigger?: string;
  // shared
  framework?: string | null;
  symbol?: string;
  tests?: CapabilityTestLink[];
  [key: string]: unknown;
}

// Something the system can be asked to do (P5-1). Kind is api (HTTP operation),
// cli (command with flags), event (queue topic), or job (scheduled/background
// task). Confidence is certain for parse-level api/cli facts, inferred for
// heuristic event/job facts (invariant I3).
export interface Capability {
  id: string;
  component_id: string | null;
  kind: "api" | "cli" | "event" | "job";
  name: string;
  detail: CapabilityDetail;
  evidence: Evidence[];
  confidence: "certain" | "inferred";
  // D6: true when every occurrence is under a test or fixture directory. Such
  // items are test scaffolding, not product surfaces, and rank behind product
  // capabilities in the default view (they are kept, never dropped).
  fixture?: boolean;
}

// A named field on a data entity, with its declared type where parseable.
export interface EntityField {
  name: string;
  type: string | null;
}

// A data entity the system knows about (P5-2): an ORM model, a physical table, a
// migration-declared table, or a standalone schema. Kind takes the most specific
// source by priority model > table > migration > schema. `table` is the physical
// table name where known; `symbol` the defining symbol id; `inferred` marks a
// partial extraction (for example CoreData).
export interface DataEntity {
  id: string;
  component_id: string | null;
  name: string;
  kind: "model" | "table" | "migration" | "schema";
  framework: string | null;
  fields: EntityField[];
  evidence: Evidence[];
  table?: string;
  symbol?: string;
  inferred?: boolean;
  // D6: true when every declaring file is under a test or fixture directory.
  // Kept for full accounting but ranked behind product entities in the default
  // view.
  fixture?: boolean;
}

// A read/write access edge from a component (accessor_id) to a data entity
// (entity_id). Confidence is certain for ORM-class usage, inferred for a
// table-name string reference (invariant I3).
export interface EntityAccess {
  accessor_id: string;
  entity_id: string;
  mode: "read" | "write";
  confidence: "certain" | "inferred";
  evidence: Evidence[];
}

// The trigger context of a rule (P5-5): where in the system the rule fires. A
// rule inside a capability's defining symbol records `capability` (the route or
// command this rule guards, the L6 -> L2 cross-link); otherwise it records the
// enclosing `symbol` id where resolvable. Both are optional and mutually
// exclusive in practice.
export interface RuleTrigger {
  symbol?: string;
  capability?: string;
}

// The structured detail of a rule (P5-5), riding in the rule's `detail` payload
// (the additive pattern capabilities/entities use). `anchor` names the detector
// that matched (guard_clause, formula, switch, if_elif_chain, sql_column,
// pydantic_validator, ...); `inputs`/`outputs` are the extracted identifier or
// field or branch-label names; `symbol` is the enclosing/defining symbol id;
// `framework` is the declaring framework where known; `field` is the constrained
// field for io rules; `entity` is the L3 Data-lens cross-link (the entity whose
// field an io rule constrains); `trigger` is the L2 Capability cross-link context.
export interface RuleDetail {
  anchor?: string;
  inputs?: string[];
  outputs?: string[];
  symbol?: string;
  framework?: string | null;
  field?: string;
  // The Data-lens (L3) cross-link: the data-entity id whose field this rule
  // constrains (io rules only, where resolvable).
  entity?: string;
  // The Capability-lens (L2) cross-link context: the capability or symbol this
  // rule fires under.
  trigger?: RuleTrigger;
  [key: string]: unknown;
}

// AI enrichment overlay for a rule (LENS-DESIGN L6, Phase 7). The deterministic
// engine emits the mechanical `summary`; enrichment later adds a plain-language
// `statement` and, per invariant I5, a `stale` marker when the cited code has
// drifted from the statement's provenance. Optional and absent until Phase 7, so
// the viewer renders the mechanical summary now and a clearly-shaped slot for the
// statement that lights up when enrichment lands.
export interface RuleAIEnhance {
  statement?: string;
  stale?: boolean;
}

// A discrete unit of decision or constraint logic (P5-5, LENS-DESIGN L6). Kind
// is validation (an input/precondition check), calculation (a domain formula),
// policy (a permission gate or decision-table-shaped branch), or io (a declared
// field bound or format constraint). Confidence is certain for declared/schema-
// anchored facts, inferred for shape-matched ones (invariant I3). `summary` is a
// MECHANICAL rendering of the code (never a natural-language explanation, which
// is Phase 7 enrichment, invariant I1). Evidence drills to the exact lines.
export interface Rule {
  id: string;
  component_id: string | null;
  kind: "validation" | "calculation" | "policy" | "io";
  summary: string;
  detail: RuleDetail;
  evidence: Evidence[];
  confidence: "certain" | "inferred";
  // Phase 7 enrichment overlay (plain-language statement + staleness). Absent
  // until enrichment runs; the Rules lens renders a slot for it.
  ai_enhance?: RuleAIEnhance;
}

// AI enhancement data (optional, present only when AI assist has been run)
export interface ComponentAIEnhance {
  // Core fields
  help_text?: string;
  // One-line summary the tree renders. The projection also copies this up to the
  // top-level Component.description when the mechanical description is empty (D7),
  // so existing description surfaces render it without change.
  description?: string;
  architectural_role?: string;
  data_handled?: string;
  criticality?: "critical" | "important" | "supporting";
  testing_assessment?: string;
  // UI actions analysis
  actions_summary?: string;
  key_user_flows?: string[];
  // Deeper testing insight
  testing_gaps?: string[];
  testing_maturity?: "comprehensive" | "adequate" | "minimal" | "untested";
  // External services context
  external_services_assessment?: string;
  // Infrastructure context
  port_assessment?: string;
  // Codebase health
  complexity_assessment?: string;
  // Technology context
  tech_context?: string;
  // Enhancement metadata
  ai_enhanced_at?: string;
  ai_enhance_version?: number;
  // Set when the cited component digest no longer matches the current files.
  // Consumers must disclose this rather than rendering old prose as current.
  stale?: boolean;
}

export interface RelationshipAIEnhance {
  data_flow_description?: string;
  importance?: "primary" | "secondary" | "internal";
  ai_discovered?: boolean;
  authentication_detail?: string;
  payload_examples?: string[];
  error_handling?: string;
  sla_notes?: string;
  security_notes?: string;
  // Infrastructure context
  port_context?: string;
  // Enhancement metadata
  ai_enhanced_at?: string;
}

export interface AnalyzerObservation {
  category: "missing_relationship" | "misclassified_component" | "naming_issue"
          | "structural_suggestion" | "detection_gap" | "data_quality";
  component_id?: string;
  description: string;
  suggestion?: string;
  confidence: "high" | "medium" | "low";
}

export interface ArchitectureAIEnhance {
  summary?: string;
  data_flow_narrative?: string;
  component_groups?: Array<{ name: string; component_ids: string[] }>;
  // Changelog interpretation
  recent_changes_summary?: string;
  // Analyzer improvement observations
  observations?: AnalyzerObservation[];
  // Cross-cutting summaries
  tech_diversity?: string;
  test_health_summary?: string;
  // Enhancement metadata
  ai_enhanced_at?: string;
  ai_enhance_version?: number;
  derived_from_commit?: string;
  stale?: boolean;
}

// Live monitoring types

export interface ComponentStatus {
  level: "ok" | "warning" | "error" | "info";
  title: string;
  detail?: string;
  url?: string;
  category: string;
  updated_at: string;
}

export interface ArchitectureStatus {
  level: "ok" | "warning" | "error" | "info";
  title: string;
  detail?: string;
  url?: string;
  category: string;
  updated_at: string;
}

export interface StatusOverlay {
  components: Record<string, Record<string, ComponentStatus>>;
  architecture: Record<string, ArchitectureStatus>;
  updated_at: string;
  commit_sha: string;
}

export interface ComponentLiveStatus {
  statuses: Record<string, ComponentStatus>;
  last_updated?: string;
}

export interface LiveVersion {
  version: number;
  updated_at: string;
  commit_sha: string;
}

export interface LiveConfig {
  enabled: boolean;
  data_url: string;
  backend_mode: "github" | "cloudflare" | "hybrid";
  project_id?: string;
  worker_url?: string;
  polling: {
    default_interval_seconds: number;
    min_interval_seconds: number;
    idle_interval_seconds: number;
    adaptive: boolean;
    pause_when_hidden: boolean;
  };
  features: {
    activity_log: boolean;
    admin_dashboard: boolean;
    version_history: boolean;
    ci_status_overlay: boolean;
    realtime_ci_webhooks: boolean;
    realtime_push: boolean;
  };
}

export interface AdminSummaryRepo {
  name: string;
  last_update: string;
  version: number;
  component_count: number;
  status: "ok" | "stale" | "error";
  error_message?: string;
}

export interface AdminSummaryActivity {
  timestamp: string;
  commit_sha: string;
  commit_message: string;
  diff_summary: {
    components_added: number;
    components_removed: number;
    components_modified: number;
    relationships_changed: number;
    files_changed: number;
  };
}

export interface AdminSummary {
  repos: AdminSummaryRepo[];
  activity: AdminSummaryActivity[];
  daily_counts: Record<string, number>;
  generated_at: string;
  resource_usage?: {
    worker_requests: number;
    d1_reads: number;
    d1_writes: number;
    r2_reads: number;
    r2_writes: number;
    limits: {
      worker_requests_per_day: number;
      d1_reads_per_day: number;
      d1_writes_per_day: number;
      r2_reads_per_month: number;
      r2_writes_per_month: number;
    };
  };
}

export interface UIAction {
  label: string;
  action_type: string;
  handler: string | null;
  file: string;
  line: number;
  target_view: string | null;
}

// Rationale / "colleague stand-in" data for the I13 rationale strip. All fields
// are optional and forward-compatible: git-activity fields (author, last_change,
// churn, commit, pr) are populated by the P5-4 git-activity pass when it lands;
// AI intent is read from ai_enhance today. The strip renders whatever is present
// and nothing when none is.
export interface RationaleInfo {
  author?: string;
  authors?: string[];
  last_change?: string;
  churn?: number;
  commit?: string;
  pr?: string;
}

export interface Component {
  id: string;
  name: string;
  type: string;
  path: string;
  language: string | null;
  framework: string | null;
  description: string | null;
  port: number | null;
  children: Component[];
  files: string[];
  entry_points: string[];
  config_files: ComponentConfig[];
  metrics: ComponentMetrics;
  docs: ComponentDoc;
  external_services?: ExternalService[];
  testing?: ComponentTesting;
  ai_enhance?: ComponentAIEnhance;
  live_status?: ComponentLiveStatus;
  actions?: UIAction[];
  // Rationale layer (I13); optional and populated by later passes. See RationaleInfo.
  rationale?: RationaleInfo;
  // Capabilities owned by this component (P5-1). Set only when non-empty; a
  // component with no capabilities carries no key. Gates the Capabilities tab.
  capabilities?: Capability[];
  // Data entities owned by this component (P5-2). Set only when non-empty; gates
  // the Data tab. The access edges themselves live at architecture.entity_access.
  data_entities?: DataEntity[];
  // Rules this component enforces (P5-5). Set only when non-empty; a component
  // with no rules carries no key. The flat index lives at architecture.rules.
  rules?: Rule[];
  // Concern id-references this component belongs to (P5-6 / P6-8). Set only when
  // non-empty; old datasets omit it. Slugs resolve against architecture.concerns.
  concerns?: string[];
  // Finding id-references touching this component (P5-6 / P6-8). Set only when
  // non-empty; the contextual findings badge derives its set from the finding
  // members (robust), so this ref list is advisory. Old datasets omit it.
  findings?: string[];
  // Architecture quality metrics (D3). Present only on a projection run with
  // --design-signals, and only for components the derivation knows; every other
  // dataset omits the key entirely and the Design lens does not appear.
  design?: ComponentDesign;
}

// Per-component design metrics (D1/D3). The ratios are NULLABLE on purpose and
// null means "not measurable here", never "zero": a component with no type
// declarations has no abstractness, and a component with no edges has no
// instability. Rendering a null as 0 would put a load-bearing module in the zone
// of pain on a number nobody measured, so every consumer must branch on null.
export interface ComponentDesign {
  // Distinct components that depend on this one (afferent coupling, Ca).
  fan_in: number;
  // Distinct components this one depends on (efferent coupling, Ce).
  fan_out: number;
  // Ce / (Ca + Ce). Low is load-bearing, high is volatile. Null when isolated.
  instability: number | null;
  // Abstract type declarations over all type declarations. Null when the
  // component declares no types, or is written in a language whose abstraction
  // the extractors cannot see (Python, C++, Ruby, JavaScript).
  abstractness: number | null;
  // |A + I - 1|. Null whenever either input is null.
  distance_main_sequence: number | null;
  // How many components transitively depend on this one.
  blast_radius: number;
  // Quintile per metric, "q1" lowest through "q5" highest. The "churn" key is
  // present only when the dataset carries git activity.
  bands: Record<string, string>;
}

// One architecture-level design finding, in the dual-audience shape (D2). The
// human surface renders `lead` first, `term` as a secondary chip, and `method`
// as the epistemic-class chip. The machine front door inverts that order.
// There is deliberately no severity and no cross-kind rank.
export interface DesignFinding {
  id: string;
  kind:
    | "cycle"
    | "zone_of_pain"
    | "zone_of_uselessness"
    | "stability_inversion"
    | "change_coupling"
    | "boundary_strength";
  // The plain-language consequence. This leads, always.
  lead: string;
  // The canonical term, for the practitioner who wants the literature.
  term: string;
  // The term's parenthetical gloss from the translation table; may be empty.
  term_detail?: string;
  // Which epistemic class the claim is in.
  method: "static-graph" | "git-history" | "static-graph+git-history";
  // Implicated component ids, for graph highlighting.
  targets: string[];
  // Implicated directed edges as [source, target] pairs.
  edges: string[][];
  evidence: DesignEvidence[];
  // Rank against this finding's OWN kind only. Never across kinds.
  rank_within_kind: number;
}

// A design finding's citation. Reuses the enrichment contract's evidence schema
// so the same no-AI validator checks it. Edge citations name source and target;
// file citations name a path.
export interface DesignEvidence {
  kind: "file" | "symbol" | "edge" | "manifest" | "doc";
  path: string | null;
  line: number | null;
  symbol: string | null;
  source?: string;
  target?: string;
  edge_type?: string;
}

// One component-pair seam, classified onto Clean Architecture's boundary
// anatomy. Strength rises left to right: convention only, then a version
// boundary, then a process, then a network contract.
export interface DesignBoundary {
  source: string;
  target: string;
  strength: "source" | "deployment" | "process" | "service";
}

// The architecture-level design signals block (D3). Optional: present only on a
// --design-signals run. Absence is what hides the Design lens.
export interface DesignSignals {
  version: number;
  // What this analysis cannot see, carried as DATA so the viewer, ai.json and
  // the MCP tools all render the same sentence instead of inventing three.
  method_caveat: string;
  has_activity: boolean;
  component_count: number;
  // The zone corners the findings were computed against, carried as data so
  // the scatter shades exactly those regions. Optional: datasets projected
  // before this key existed fall back to the viewer's mirrored constants.
  zone_thresholds?: {
    zone_of_pain_max_sum: number;
    zone_of_uselessness_min_sum: number;
  };
  finding_counts: Record<string, number>;
  findings: DesignFinding[];
  boundaries: DesignBoundary[];
}

// Aggregation node (P6-4). At a drill level, components that the hero filter
// would otherwise hide silently are grouped by type into a labeled, counted
// aggregate that the user can expand in place. This closes the silent-hiding
// gap (invariant I2 spirit): every child at a level is either a real node or a
// visible member of one of these aggregates.
export interface AggregateNode {
  // Stable id embedding the drill level and grouped type so expansion state
  // never leaks across levels: `__agg__<drillLevel|root>__<type>`.
  id: string;
  kind: "aggregate";
  // The component type grouped here (e.g. "module").
  aggregateType: string;
  // Human label, e.g. "12 modules".
  label: string;
  members: Component[];
  memberCount: number;
  // The drill level this aggregate belongs to (null at root, unused there).
  parentDrillLevel: string | null;
}

export interface Relationship {
  source: string;
  target: string;
  type: string;
  label: string | null;
  protocol: string | null;
  port: number | null;
  bidirectional: boolean;
  authentication?: string;
  data_format?: string;
  api_style?: string;
  endpoints?: Array<{ method: string; path: string }>;
  middleware?: string[];
  transport?: string;
  queue_name?: string;
  connection_pattern?: string;
  ai_enhance?: RelationshipAIEnhance;
  verdict?: {
    status: "confirmed" | "refuted" | "uncertain";
    reason?: string;
  };
  // Present only on viewer-side aggregated edges (S1 roll-up): edges between
  // descendants of visible nodes drawn at the visible level. `count` is how
  // many deep edges were folded in; `pairs` lists up to twelve of their real
  // endpoint ids for provenance display. Never emitted by the analyzer.
  rolled_up?: { count: number; pairs: Array<{ source: string; target: string }> };
}

// Coverage ledger (optional, present only for v2 single-repo projections).
// TARGET-ARCHITECTURE.md section 7 / invariant I2: every file under the scan
// root has exactly one disposition (parsed, excluded:<rule>, failed, binary).
// The manifest carries the summary; the full rows live in coverage.json (split
// mode) or inline in the monolithic architecture.json.
export interface CoverageRow {
  path: string;
  disposition: string;
  reason: string | null;
}

export interface Coverage {
  // Counts keyed by disposition string (e.g. "parsed", "binary",
  // "excluded:generated", "failed"). Ordinary huge excluded directories may
  // be represented by one bounded row, while recognized generated projections
  // are ledgered file by file so their contents remain exactly accountable.
  summary: Record<string, number>;
  total: number;
  parsed: number;
  // Full ledger rows. Present in coverage.json and the monolith; absent from the
  // manifest summary (fetched lazily by the panel in split mode).
  rows?: CoverageRow[];
  // Non-source inventory (P6-10). Present in coverage.json and the monolith,
  // absent from the manifest summary. Optional and versioned: an older dataset
  // without it degrades to exactly the pre-inventory coverage panel.
  inventory?: Inventory;
}

// Non-source inventory (P6-10; repo totality). The analyzer classifies every
// non-source ledger row into a category group, each carrying a plain-language
// explanation, a high-level recommendation, and bounded evidence, all computed
// deterministically without any AI. The viewer ranks the groups by count and
// bytes and names the dominant group when non-source dwarfs source.
export interface InventoryGroupFlags {
  security_sensitive: boolean;
  likely_unwanted: boolean;
  gitignore_candidate: boolean;
}

export interface InventoryExtension {
  ext: string;
  count: number;
}

export interface InventoryTopDirectory {
  dir: string;
  count: number;
}

export interface InventoryGroup {
  id: string;
  label: string;
  explanation: string;
  recommendation: string;
  count: number;
  // Total bytes when the tree was available to stat, else null. Directory rows
  // (one row standing for a pruned subtree) contribute no bytes.
  bytes: number | null;
  // How many of this group's rows are pruned-directory rows, each standing in
  // for everything beneath it rather than a single file.
  directory_rows: number;
  extensions: InventoryExtension[];
  top_directories: InventoryTopDirectory[];
  // A bounded sample of member paths. The complete enumeration lives in the
  // coverage ledger rows; this is enough to see what the group holds.
  samples: string[];
  flags: InventoryGroupFlags;
  // Project knowledge layer provenance (P6-12). Present only when a non-built-in
  // source classified at least one row in the group; absent on old datasets and
  // rule-free repos (additive). rule_provenance maps a source to how many rows it
  // classified ("builtin", "gitattributes", or "project:<rule-id>");
  // sample_provenance aligns with samples so a row taught by a project rule shows
  // a marker.
  rule_provenance?: Record<string, number>;
  sample_provenance?: string[];
}

export interface InventoryDominant {
  id: string;
  count: number;
  share: number;
}

export interface Inventory {
  version: number;
  // Non-source rows classified into groups (the NON-SOURCE ACCOUNTED family).
  non_source_total: number;
  // Source gaps (failed, oversized) not classified here; they live in the
  // coverage gaps family. Carried so the panel can be honest about scope.
  source_gap_total: number;
  groups: InventoryGroup[];
  // The dominant group when it is more than half of all non-source rows, else
  // null. The viewer turns this into the disproportion cue.
  dominant: InventoryDominant | null;
}

// Git-activity data (optional, present only when the P5-4 activity pass read git
// history). Language-agnostic, derived entirely from git log. The manifest
// carries the lightweight summary; the full data lives in activity.json (split
// mode) or inline under architecture.activity (monolith). The Activity lens
// (P6-5) consumes it; presence gates the lens and old datasets omit it entirely.
export interface ActivityAuthor {
  author_key: string;
  author_name: string;
  commits: number;
  share: number;
}

export interface ActivityProvenance {
  git: boolean;
  shallow: boolean;
  head: string | null;
  commits: number;
  first_commit: string | null;
  last_commit: string | null;
}

// A component ranked in the hotspot list, with its knowledge map. hotspot_score
// is change frequency times size (commit_count times lines, summed over member
// files); knowledge_island marks a top-author share >= 95%; bus_factor is the
// fewest authors covering >= 50% of commits.
export interface ActivityComponent {
  id: string;
  name: string;
  files: number;
  commit_count: number;
  lines_added: number;
  lines_removed: number;
  churn: number;
  lines: number;
  hotspot_score: number;
  first_seen: string | null;
  last_modified: string | null;
  author_count: number;
  top_author_share: number;
  knowledge_island: boolean;
  bus_factor: number;
  authors: ActivityAuthor[];
}

// A co-change pair. component_coupling pairs are cross-component by construction
// (same-component pairs are excluded by the projection). a < b.
export interface ActivityCoupling {
  a: string;
  b: string;
  cochange_count: number;
}

export interface ActivityFile {
  commit_count: number;
  lines_added: number;
  lines_removed: number;
  churn: number;
  lines: number;
  hotspot_score: number;
  first_seen: string | null;
  last_modified: string | null;
  component_ids: string[];
  authors: ActivityAuthor[];
}

// The full activity dataset (activity.json in split mode; inline under
// architecture.activity in monolith mode). Distinguished from the manifest
// summary by the presence of the `components` array.
export interface ActivityData {
  provenance: ActivityProvenance;
  components: ActivityComponent[];
  component_coupling: ActivityCoupling[];
  file_coupling: ActivityCoupling[];
  files: Record<string, ActivityFile>;
}

// The lightweight slice that rides in the manifest. Its presence alone gates the
// Activity lens (no activity.json fetch needed to decide availability).
export interface ActivityManifestSummary {
  provenance: ActivityProvenance;
  top_hotspots: Array<{
    id: string;
    name: string;
    hotspot_score: number;
    commit_count: number;
    knowledge_island: boolean;
    bus_factor: number;
  }>;
  component_count: number;
  coupling_count: number;
}

export interface ArchitectureStats {
  total_files: number;
  total_lines: number;
  // Line-class taxonomy (owner line-count policy, 2026-08-17): every counted
  // line in exactly one class, summing to total_lines. Absent on datasets
  // projected before the taxonomy shipped; the header then shows the plain
  // total.
  lines_by_class?: { code: number; data: number; docs: number; config: number };
  total_size_bytes: number;
  languages: Record<string, number>;
  total_symbols: number;
  total_components: number;
  // Path-level components only (excludes derived UI-flow nodes); informational.
  total_path_components?: number;
  total_relationships: number;
}

// ---------------------------------------------------------------------------
// Supply chain / SBOM (P10-1). The compact, viewer-native section the projection
// carries in the manifest (and monolith); the full CycloneDX 1.5 document lives
// beside it in sbom.json. Optional: a dataset with no manifests omits the whole
// section and the supply chain surface does not appear.
// ---------------------------------------------------------------------------

// A file:line evidence pointer into a manifest. line is present where cheap.
export interface SupplyChainEvidence {
  file: string;
  line?: number;
}

export type PinStatus = "exact-pinned" | "range" | "unpinned";
export type DependencyScope = "direct" | "transitive";

export interface SupplyChainDependency {
  id: string;
  ecosystem: string;
  name: string;
  declared?: string;
  version?: string;
  pin_status: PinStatus;
  scope: DependencyScope;
  purl?: string;
  evidence: SupplyChainEvidence;
}

// A language runtime or SDK version the repo targets, surfaced apart from the
// packages (requires-python, node engines, swift-tools-version, go directive,
// dotnet TargetFramework, ruby version).
export interface SupplyChainTarget {
  ecosystem: string;
  kind: string;
  label: string;
  constraint: string;
  evidence: SupplyChainEvidence;
}

export interface SupplyChainEcosystem {
  id: string;
  label: string;
  manifests: string[];
  dependency_count: number;
  direct_count: number;
  transitive_count: number;
  pin_counts: Record<string, number>;
}

export interface SupplyChainWarning {
  ecosystem: string;
  file: string;
  error: string;
}

export interface SupplyChainVendored {
  path: string;
  file_count?: number | null;
  evidence: SupplyChainEvidence;
}

// Test/fixture-origin records: dependencies declared by manifests under a
// test/fixture/example path segment. Kept and accounted, excluded from the
// shipping counts and the CycloneDX components (P10-1 finding 1).
export interface SupplyChainFixtureBlock {
  note: string;
  ecosystems: SupplyChainEcosystem[];
  targets: SupplyChainTarget[];
  dependencies: SupplyChainDependency[];
  warnings: SupplyChainWarning[];
}

export interface SupplyChain {
  version: number;
  sbom_endpoint: string;
  sbom_format: string;
  scope_note: string;
  ecosystems: SupplyChainEcosystem[];
  targets: SupplyChainTarget[];
  dependencies: SupplyChainDependency[];
  warnings: SupplyChainWarning[];
  vendored?: SupplyChainVendored[];
  // Test/fixture dependencies, present only when the repo has fixture manifests.
  fixture?: SupplyChainFixtureBlock;
  counts: {
    ecosystems: number;
    dependencies: number;
    direct: number;
    transitive: number;
    targets: number;
    warnings: number;
    vendored: number;
    pin_status: Record<string, number>;
    fixture: {
      ecosystems: number;
      dependencies: number;
      targets: number;
      warnings: number;
    };
  };
}

export interface RepositoryInfo {
  name: string;
  repository?: string | null;
  default_branch?: string | null;
}

// Honest-gap record for one producer unit (card R1). When a derive pass, an
// emitter, or another producer cannot hand off a whole result, it records one of
// these instead of crashing the run. `status` mirrors the coverage-ledger
// disposition vocabulary ("failed"). Deterministic (same input, same gap).
export interface ProducerGap {
  producer: string;
  stage: string;
  status: string;
  reason: string;
}

// Human-entry projections. These are deterministic, bounded views over the
// same stable ids the Workbench uses; the viewer never derives architectural
// claims from display geometry.
export interface OrientationTarget {
  lens?: string;
  semantic_level?: "system" | "domain" | "component";
  tour_id?: string | null;
  surface?: string;
}

export interface OrientationNode {
  id: string;
  label: string;
  role: string;
  member_count: number;
  stable_targets: string[];
  target_truncated: boolean;
  statement_kind: "deterministic_grouping";
}

export interface OrientationEdge {
  source: string;
  target: string;
  relationship_count: number;
  evidence_pairs: [string, string][];
}

export interface OrientationProjection {
  schema: "syscorpus.orientation/v1";
  subject: {
    id: string;
    name: string;
    kind: string;
    repository?: string | null;
    default_branch?: string | null;
    generated_at?: string | null;
    analyzer_version?: string | null;
  };
  orientation: {
    deterministic_statement: string;
    interpreted_statement?: {
      text: string;
      status: "interpreted";
      provenance: { derived_from_commit?: string | null; stale: boolean };
    } | null;
    default_path: { kind: "tour" | "question"; id: string };
  };
  deployment_posture?: {
    status: "evidence_tiered";
    method_caveat: string;
    items: Array<{
      id: string;
      label: string;
      posture: "standalone" | "optional" | "on_device" | "direct_to_provider";
      detail?: string;
      statement_kind: "repository_claim" | "observed_source_reference";
      evidence: Record<string, unknown>;
    }>;
  } | null;
  portrait: {
    semantic_level: "system";
    method: string;
    nodes: OrientationNode[];
    edges: OrientationEdge[];
  };
  question_routes: Array<{
    id: string;
    label: string;
    target: OrientationTarget;
    available: boolean;
  }>;
  trust: {
    source_coverage: {
      status: "unavailable" | "complete" | "has_gaps";
      percent: number | null;
      analyzed?: number;
      gaps?: number;
      inventory_total?: number;
      excluded?: number;
      binary?: number;
      target: string;
    };
    interpretation: { status: "present" | "stale" | "absent"; component_count: number; total_components: number };
    producer_gaps: number;
    producer_gap_status?: Record<string, number>;
    findings: { total: number; unverified: number; refuted?: number };
    direct_dependencies: number;
  };
  launch_targets: Record<string, OrientationTarget & { mode: "overview" | "workbench" }>;
}

export interface SupportProjection {
  schema: "syscorpus.support/v1";
  method_caveat: string;
  configuration: Array<{
    key: string;
    component_id: string;
    component_name: string;
    kind: "environment_variable" | "configuration_file";
    evidence: Record<string, unknown>;
  }>;
  external_dependencies: Array<{
    name: string;
    category: string;
    protocol?: string | null;
    port?: number | null;
    authentication?: string | null;
    component_id: string;
    component_name: string;
    evidence: Record<string, unknown>;
  }>;
  entry_points: Array<{
    id: string;
    name: string;
    kind: string;
    component_id: string | null;
    component_name: string | null;
    confidence: string;
    evidence: unknown[];
  }>;
  data_handled: Array<{
    id: string;
    name: string;
    kind: string;
    component_id: string | null;
    confidence: string;
    evidence: unknown[];
  }>;
  attention: Array<{
    component_id: string;
    component_name: string;
    attention_score: number;
    reasons: string[];
  }>;
  counts: Record<string, number>;
}

export interface SecurityProjection {
  schema: "syscorpus.security/v1";
  method_caveat: string;
  mechanisms: Array<{
    source: string;
    target: string;
    mechanism: string;
    confidence: string;
    evidence: Record<string, unknown>;
  }>;
  credential_configuration: Array<{
    key: string;
    component_id: string;
    component_name: string;
    claim: string;
    confidence: string;
    evidence: Record<string, unknown>;
  }>;
  communication_boundaries: Array<{
    source: string;
    source_name: string;
    target: string;
    target_name: string;
    type: string;
    protocol: string;
    port?: number | null;
    authentication?: string | null;
    transport_state: "encrypted_observed" | "cleartext_label_observed" | "not_observable";
    evidence: Record<string, unknown>;
  }>;
  sensitive_data_leads: Array<{
    entity_id: string;
    entity_name: string;
    component_id: string | null;
    matched_terms: string[];
    confidence: "inferred";
    evidence: unknown[];
  }>;
  findings: Array<{
    id: string;
    kind: string;
    summary: string;
    confidence?: string | null;
    verification_status: string;
    evidence: unknown[];
  }>;
  not_observable: string[];
  counts: Record<string, number>;
}

export interface Architecture {
  name: string;
  description: string;
  repository: string | null;
  default_branch?: string;
  generated_at: string;
  analyzer_version: string;
  root_path: string;
  components: Component[];
  relationships: Relationship[];
  symbols: Symbol[];
  files: FileInfo[];
  stats: ArchitectureStats;
  repositories?: RepositoryInfo[];
  ai_enhance?: ArchitectureAIEnhance;
  // Coverage ledger summary (optional; v2 single-repo projections only). Multi-
  // repo projections omit it and are detected via `repositories` for the
  // "coverage unavailable for this dataset" message. Old datasets omit it and
  // degrade silently.
  coverage?: Coverage;
  // Git-activity data (optional; P5-4). Manifest summary in split mode, full
  // ActivityData inline in monolith mode. Presence gates the Activity lens
  // (P6-5); old datasets omit it and the lens does not appear.
  activity?: ActivityManifestSummary | ActivityData;
  // Flat capability index (P5-1). Optional; old datasets omit it. The per-
  // component `capabilities` key is the primary consumer for the Capabilities
  // tab; this index is the whole-system list used by the Capability lens (P6-3).
  capabilities?: Capability[];
  // Flat data-entity index (P5-2). Optional; old datasets omit it.
  data_entities?: DataEntity[];
  // Flat entity-access edge index (P5-2). Optional; old datasets omit it. The
  // Data tab reads this both directions: what a component touches, and who else
  // touches an entity this component owns.
  entity_access?: EntityAccess[];
  // Flat rule index (P5-5). Optional; old datasets omit it. Presence gates the
  // Rules lens (P6-6). The per-component `rules` key is the per-component slice;
  // this index is the whole-system list the Rules lens ranks.
  rules?: Rule[];
  // Ranked correlation findings and cross-cutting concerns (P5-6). Optional; old
  // datasets and multi-repo projections omit them. Consumed by set creation
  // (P6-9) and the findings/concerns surfaces (P6-8).
  findings?: Finding[];
  concerns?: Concern[];
  // Guided walkthroughs (P6-7, LENS-DESIGN L7). Optional projection-level artifact:
  // an ordered list of code-anchored tours, each a sequence of highlighted
  // locations plus narration. The viewer ships the PLAYER; authoring/generation is
  // enrichment work (Phase 7). Old datasets omit the key and the Tours entry point
  // does not appear (degrades like coverage/activity/findings).
  tours?: Tour[];
  // Supply chain / SBOM summary (P10-1). Optional; old datasets and repos with
  // no manifests omit it and the supply chain surface does not appear. The full
  // CycloneDX document is sbom.json beside the manifest.
  supply_chain?: SupplyChain;
  // Architecture quality signals (D3). Optional, and present only on a run with
  // --design-signals. Presence gates the Design lens; every other dataset omits
  // the key and the lens does not appear, exactly like coverage and activity.
  design_signals?: DesignSignals;
  orientation?: OrientationProjection;
  support?: SupportProjection;
  security?: SecurityProjection;
  component_detail_index?: Record<string, { symbolCount: number; fileCount: number }>;
  live_status?: {
    statuses?: Record<string, ArchitectureStatus>;
    monitored_branch?: string;
    last_commit_sha?: string;
    last_updated?: string;
  };
  changelog?: ChangelogEntry[];
  changelog_serial?: number;
  // Producer honest gaps (card R1). Optional and omitted entirely on a healthy
  // run (a run with no gaps adds no bytes, preserving byte parity), so old
  // datasets and clean runs have no key. When present, each entry names a
  // producer that could not hand off a complete result and why; the viewer can
  // surface these as honest gaps and otherwise degrades around them.
  gaps?: ProducerGap[];
  // Maturity-gate provenance (card R3). Optional and present ONLY on a
  // non-default-channel run that activated a non-stable gate, so a default
  // projection omits it entirely and byte parity holds. When present it names the
  // resolved channel and the active experimental/beta gates that shaped the
  // output; the viewer must not require it (degrade-by-absence).
  gate_provenance?: {
    channel: string;
    active_gates: { id: string; stability: string }[];
  };
}

// ---------------------------------------------------------------------------
// Correlations: concerns and findings (P5-6 extraction, P6-8 surface).
// LENS-DESIGN.md section 9. All deterministic derivations over the store,
// AI-verified before surfacing, never AI-invented (I1). A finding carries
// evidence, confidence, and a verification status; an unverified finding is
// marked and never presented as established fact (I15, the DeepWiki lesson).
// ---------------------------------------------------------------------------

// One member of a finding: a code fragment (duplication) or a whole component
// (orphan). File and line fields are present for fragment members; component
// members carry the component id and null line fields.
export interface FindingMember {
  id: string;
  kind: string; // "fragment" | "component"
  component_id?: string | null;
  file?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  symbol?: string | null;
}

// Evidence for a finding. Fragment evidence points at file:line(:symbol);
// orphan evidence describes the component (path, type, owned files).
export interface FindingEvidence {
  file?: string | null;
  line?: number | null;
  end_line?: number | null;
  symbol?: string | null;
  component_id?: string;
  path?: string;
  type?: string;
  files?: string[];
}

export interface Finding {
  id: string;
  kind: string; // "duplication" | "orphan" | "inconsistency"
  summary: string;
  members: FindingMember[];
  evidence: FindingEvidence[];
  confidence: string; // "inferred" today
  // "unverified" until the Phase 7 verification pass (P7-4) flips it. An
  // unverified finding is visibly marked and never presented as fact (I15).
  verification_status: string;
  rank_score: number;
  detail?: Record<string, unknown>;
}

export interface ConcernEvidence {
  file: string;
  line?: number | null;
  signal?: string;
}

export interface ConcernMember {
  component_id: string;
  evidence: ConcernEvidence[];
  files: string[];
  markers: string[];
}

export interface Concern {
  id: string;
  kind: string;
  // The mechanical title (e.g. "Logging"). The Phase 7 (P7-4) plain-language
  // name is a separate, currently-absent slot the surface shapes but leaves empty.
  title: string;
  basis: string; // mechanical detection basis
  members: ConcernMember[];
  detail?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Tours: code-anchored guided walkthroughs (P6-7, LENS-DESIGN.md section 4, L7).
// The projection contract the viewer's tour player reads. Tours are generated by
// the enrichment pipeline (candidate tours per capability/scenario plus an
// onboarding path), human-editable, and keyed to stable ids (I4/I12). They detect
// their own staleness via content-hash provenance (I5). The store table and the
// enrichment-side generation are the analyzer follow-up; this is the data-first
// landing, mirroring how activity and rules arrived from the other direction.
// ---------------------------------------------------------------------------

// A single piece of evidence a tour step points at: an exact file (and optional
// line) so "show me the code" jumps to the proof (I14).
export interface TourStepEvidence {
  file: string;
  line?: number | null;
}

// One step of a tour: a highlighted location plus its narration. `target` is a
// stable id (a component id, a file path, or a symbol id, I12) that the player
// selects on stable identity as it walks the tour.
export interface TourStep {
  target: string;
  title: string;
  narration: string;
  evidence?: TourStepEvidence;
  statement_kind?: "authored_interpretation" | "verified_claim";
  verification_status?: "unverified" | "verified" | "refuted";
}

// Provenance for staleness detection (I5). `derived_from_commit` records the
// commit the tour was generated against; `stale` is set by the enrichment
// pipeline (or verification pass) when the anchored code has drifted since. The
// player shows a stale marker so a walkthrough is never silently served as
// current when its anchors moved.
export interface TourProvenance {
  derived_from_commit?: string;
  stale?: boolean;
}

// A guided walkthrough: an ordered sequence of steps with a title and summary.
export interface Tour {
  id: string;
  title: string;
  description: string;
  steps: TourStep[];
  provenance?: TourProvenance;
  statement_kind?: "authored_interpretation" | "verified_claim";
  verification_status?: "unverified" | "verified" | "refuted";
}

// Changelog types for architecture change notifications
export interface ChangelogChange {
  kind: "component_added" | "component_removed" | "component_modified"
      | "relationship_added" | "relationship_removed";
  target_id: string;
  target_name: string;
  target_type: string;
  detail: string;
  source_id?: string;
  source_name?: string;
  dest_id?: string;
  dest_name?: string;
}

export interface ChangelogEntry {
  serial: number;
  timestamp: string;
  commit_sha?: string;
  scan_type: "initial" | "full" | "incremental";
  summary: string;
  changes: ChangelogChange[];
}

// Review annotations
export type AnnotationTarget =
  | "component"            // whole-component feedback
  | "component-name"       // the display name
  | "component-type"       // the type badge
  | "component-framework"  // framework label
  | "component-port"       // port display
  | "component-purpose"    // purpose/description line
  | "component-pattern"    // a specific pattern badge
  | "file"                 // file-level feedback
  | "symbol";              // symbol-level feedback

export interface AnnotationTargetContext {
  componentPath?: string;
  nameSource?: string;
  typeValue?: string;
  frameworkValue?: string;
  portValue?: number;
  purposeValue?: string;
  patternValue?: string;
  configFiles?: string[];
}

export interface Annotation {
  id: string;
  componentId: string;
  targetType: AnnotationTarget;
  targetId: string;
  targetName: string;
  text: string;
  createdAt: string;
  targetContext?: AnnotationTargetContext;
}

// Selection sets and set-level review actions (P6-9, LENS-DESIGN section 10).
// A set is an addressable, nameable collection of members keyed on STABLE
// identity, created from a finding, a concern, a search, or manual multi-select.
// Sets and their annotations persist alongside single-element annotations.

// Where a set came from. `finding:<id>` / `concern:<id>` / `search:<query>` /
// `manual`. Drives the auto-suggested acceptance criteria in a directive.
export type SetOrigin = string;

export interface SetMember {
  // The grain of the referent. Navigation and evidence resolution use this.
  kind: "component" | "file" | "symbol";
  // Stable identity within the architecture (I4/I12): a component id, a file
  // path, or a symbol id. Never an order-derived key.
  ref: string;
  // The owning component id (equals ref for component members), so a member can
  // always be navigated to and its evidence resolved.
  componentId: string;
  // Human label shown in the set list and the directive.
  label: string;
  // Optional evidence carried from the origin so the directive can cite the
  // exact site without re-deriving it.
  file?: string;
  lineStart?: number | null;
  lineEnd?: number | null;
  // Free-form evidence lines (clone class, concern signal, capability/rule kind)
  // for the directive's per-member evidence block.
  evidence?: string[];
}

export interface SelectionSet {
  id: string;
  name: string;
  origin: SetOrigin;
  members: SetMember[];
  createdAt: string;
}

export interface SetMemberNote {
  memberRef: string; // matches SetMember.ref
  note: string;
}

export interface SetAnnotation {
  setId: string;
  // The shared intent, stated once for the whole set (LENS-DESIGN section 10).
  intent: string;
  // Optional per-member notes, keyed by member ref.
  memberNotes: SetMemberNote[];
}

// Multi-repo solution manifest (MULTI-REPO-DESIGN.md, M1). The root
// manifest.json of a COMPOSED solution carries kind === SOLUTION_MANIFEST_KIND
// and a member index instead of a component graph. Each resolved member is a
// standalone projection under members/<slug>/.
export const SOLUTION_MANIFEST_KIND = "solution-explorer-solution";

export interface SolutionMemberCoverage {
  summary: Record<string, number>;
  families: {
    analyzed: number;
    gap: number;
    nonsource: number;
    source_total: number;
  };
  source_percent: string;
  has_gaps: boolean;
}

export interface SolutionMember {
  slug: string;
  label: string;
  resolved: boolean;
  path?: string;
  url?: string;
  ref?: string;
  projection?: string;
  unresolved_reason?: string;
  error?: string;
  stats?: {
    total_components: number;
    total_files: number;
    total_lines: number;
    total_symbols: number;
    total_relationships: number;
  };
  coverage?: SolutionMemberCoverage;
}

export interface SolutionManifest {
  schema: string;
  kind: typeof SOLUTION_MANIFEST_KIND;
  name: string;
  generated_at: string;
  analyzer_version: string;
  members: SolutionMember[];
  summary: {
    member_count: number;
    composed_count: number;
    unresolved_count: number;
    error_count: number;
    total_source_files: number;
    total_source_analyzed: number;
    total_nonsource_files: number;
    total_files: number;
    total_lines: number;
    members_with_gaps: string[];
  };
}

// ---------------------------------------------------------------------------
// Publication metadata (publication.json sidecar). Design authority:
// docs/publication/PUBLICATION-METADATA.md and publication.schema.json in this
// repo. This is PUBLISHING metadata, not analysis data: it never influences
// extraction, enrichment, or scoring, only the presentation layer. It is
// OPTIONAL. When the sidecar is absent or invalid the viewer renders exactly as
// today (design rule 2), so every consumer treats a null publication as "not
// present" and falls back to the folder-derived architecture.name.
//
// Shape mirrors publication.schema.json (draft-07). Fields the schema marks
// required for a valid file are non-optional here; the runtime validator in
// utils/publication.ts rejects a file that does not carry them, so a Publication
// value in the store is always structurally valid.
// ---------------------------------------------------------------------------

export interface PublicationPublisher {
  name: string;
  contact: string;
  url?: string;
}

export interface PublicationSubject {
  name: string;
  repo_url?: string;
  license?: string;
  commit: string;
  snapshot_date: string;
  affiliation: "owner" | "maintainer" | "contributor" | "none";
}

export interface PublicationHeader {
  banner: string;
  front_page?: string[];
}

export interface PublicationFooterContent {
  always: string[];
  front_page?: string[];
}

export interface PublicationAccess {
  visibility: "public" | "private-preview" | "internal";
  gate?: string | null;
}

export interface PublicationGeneratedBy {
  tool: string;
  version: string;
}

export interface Publication {
  publication_version: 1;
  publisher: PublicationPublisher;
  subject: PublicationSubject;
  purpose: "demo" | "documentation" | "internal" | "evaluation" | "other";
  update_policy: "snapshot" | "periodic" | "continuous";
  header: PublicationHeader;
  footer: PublicationFooterContent;
  context?: string[];
  // Required by the schema but may be an empty array.
  disclaimers: string[];
  access: PublicationAccess;
  generated_by: PublicationGeneratedBy;
}

// Navigation state
export type ViewMode = "graph" | "tree" | "list";
export type Panel = "tree" | "detail" | "review" | null;

export interface BreadcrumbItem {
  id: string;
  name: string;
  type: string;
}
