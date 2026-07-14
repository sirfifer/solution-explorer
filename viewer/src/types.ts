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
