// Cloudflare Worker environment bindings
export interface Env {
  DB: D1Database;
  BUCKET: R2Bucket;
  SETTINGS_KV: KVNamespace;
  INGEST_TOKEN: string;
  WEBHOOK_SECRET: string;
  WORKER_VERSION: string;
}

// Ingest request body (sent by GitHub Actions after R2 upload)
export interface IngestPayload {
  project_id: string;
  version: number;
  commit_sha: string;
  commit_message?: string;
  component_count: number;
  relationship_count: number;
  component_ids: string[];
  diff_summary?: {
    components_added: number;
    components_removed: number;
    components_modified: number;
    relationships_changed: number;
    files_changed: number;
  };
}

// Health endpoint response
export interface HealthResponse {
  worker_version: string;
  d1_status: "ok" | "error";
  r2_status: "ok" | "error";
  timestamp: string;
}

// Resource usage record (matches D1 resource_usage table)
export interface ResourceUsage {
  worker_requests: number;
  d1_reads: number;
  d1_writes: number;
  r2_reads: number;
  r2_writes: number;
}

// Cloudflare free tier daily/monthly limits
export const FREE_TIER_LIMITS = {
  worker_requests_per_day: 100_000,
  d1_reads_per_day: 5_000_000,
  d1_writes_per_day: 100_000,
  r2_reads_per_month: 10_000_000,
  r2_writes_per_month: 1_000_000,
} as const;

// 80% thresholds for self-throttling
export const USAGE_THRESHOLDS = {
  worker_requests_per_day: 80_000,
  d1_writes_per_day: 80_000,
} as const;
