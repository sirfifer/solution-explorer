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
  // "excluded:node_modules", "failed"). This is the pruned-directory reading of
  // I2: an excluded directory is a single row/count whose rule explains
  // everything beneath it; failed/binary/oversize are per file.
  summary: Record<string, number>;
  total: number;
  parsed: number;
  // Full ledger rows. Present in coverage.json and the monolith; absent from the
  // manifest summary (fetched lazily by the panel in split mode).
  rows?: CoverageRow[];
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
  total_size_bytes: number;
  languages: Record<string, number>;
  total_symbols: number;
  total_components: number;
  total_relationships: number;
}

export interface RepositoryInfo {
  name: string;
  repository?: string | null;
  default_branch?: string | null;
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
  component_detail_index?: Record<string, { symbolCount: number; fileCount: number }>;
  live_status?: {
    statuses?: Record<string, ArchitectureStatus>;
    monitored_branch?: string;
    last_commit_sha?: string;
    last_updated?: string;
  };
  changelog?: ChangelogEntry[];
  changelog_serial?: number;
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

// Navigation state
export type ViewMode = "graph" | "tree" | "list";
export type Panel = "tree" | "detail" | "review" | null;

export interface BreadcrumbItem {
  id: string;
  name: string;
  type: string;
}
