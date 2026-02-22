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

// AI enhancement data (optional, present only when AI assist has been run)
export interface ComponentAIEnhance {
  help_text?: string;
  architectural_role?: string;
  data_handled?: string;
  criticality?: "critical" | "important" | "supporting";
}

export interface RelationshipAIEnhance {
  data_flow_description?: string;
  importance?: "primary" | "secondary" | "internal";
  ai_discovered?: boolean;
}

export interface ArchitectureAIEnhance {
  summary?: string;
  data_flow_narrative?: string;
  component_groups?: Array<{ name: string; component_ids: string[] }>;
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
  ai_enhance?: ComponentAIEnhance;
  live_status?: ComponentLiveStatus;
}

export interface Relationship {
  source: string;
  target: string;
  type: string;
  label: string | null;
  protocol: string | null;
  port: number | null;
  bidirectional: boolean;
  ai_enhance?: RelationshipAIEnhance;
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
}

export interface Architecture {
  name: string;
  description: string;
  repository: string | null;
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
  component_detail_index?: Record<string, { symbolCount: number; fileCount: number }>;
  live_status?: {
    statuses?: Record<string, ArchitectureStatus>;
    monitored_branch?: string;
    last_commit_sha?: string;
    last_updated?: string;
  };
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
