-- D1 schema for solution-explorer-api

CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  commit_sha TEXT NOT NULL,
  component_count INTEGER NOT NULL DEFAULT 0,
  relationship_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_versions_project
  ON versions(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS patches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  commit_sha TEXT NOT NULL,
  commit_message TEXT NOT NULL DEFAULT '',
  components_added INTEGER NOT NULL DEFAULT 0,
  components_removed INTEGER NOT NULL DEFAULT 0,
  components_modified INTEGER NOT NULL DEFAULT 0,
  relationships_changed INTEGER NOT NULL DEFAULT 0,
  files_changed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_patches_project
  ON patches(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS health (
  project_id TEXT PRIMARY KEY,
  last_update TEXT NOT NULL,
  version INTEGER NOT NULL,
  component_count INTEGER NOT NULL DEFAULT 0,
  relationship_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ok',
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS resource_usage (
  project_id TEXT NOT NULL,
  date TEXT NOT NULL,
  worker_requests INTEGER NOT NULL DEFAULT 0,
  d1_reads INTEGER NOT NULL DEFAULT 0,
  d1_writes INTEGER NOT NULL DEFAULT 0,
  r2_reads INTEGER NOT NULL DEFAULT 0,
  r2_writes INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (project_id, date)
);
CREATE INDEX IF NOT EXISTS idx_resource_usage_date
  ON resource_usage(project_id, date DESC);
