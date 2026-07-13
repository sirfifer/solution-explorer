"""SQLite schema for the v2 fact store (TARGET-ARCHITECTURE.md section 4.2).

The store is the system of record (invariant O6): extraction writes facts,
derivation joins over them, and projection reads them. This module owns the
DDL and the schema version. Standard-library ``sqlite3`` only, no ORM. The
store package must not import from scanner.py or incremental.py; it is the new
engine's dependency-free foundation.

Every table that a projection reads has a deterministic natural sort key
(id or path). Read helpers in db.py order by that key so two runs over the
same store emit byte-identical projections (invariant I4, risk mitigation in
WORK-PLAN-2.md section 7).
"""

from __future__ import annotations

# Bump only with a recorded decision and a migration. The grammar in ids.py
# freezes at P4-1; this schema version tracks the physical layout.
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Core tables. Foreign keys are declared for documentation and optional
# enforcement; db.py enables PRAGMA foreign_keys per connection.
# ---------------------------------------------------------------------------

_CORE_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,
    language      TEXT,
    lines         INTEGER,
    size_bytes    INTEGER,
    content_hash  TEXT,
    parse_status  TEXT
);

CREATE TABLE IF NOT EXISTS symbols (
    id           TEXT PRIMARY KEY,
    file_id      INTEGER NOT NULL REFERENCES files(id),
    name         TEXT NOT NULL,
    kind         TEXT,
    parent_id    TEXT REFERENCES symbols(id),
    line         INTEGER,
    end_line     INTEGER,
    visibility   TEXT,
    docstring    TEXT,
    code_preview TEXT
);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_id);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);

CREATE TABLE IF NOT EXISTS signals (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id),
    kind       TEXT NOT NULL,
    value_json TEXT,
    line       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_signals_file ON signals(file_id);
CREATE INDEX IF NOT EXISTS idx_signals_kind ON signals(kind);

CREATE TABLE IF NOT EXISTS components (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    type      TEXT,
    path      TEXT,
    parent_id TEXT REFERENCES components(id),
    role      TEXT,
    meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_components_parent ON components(parent_id);
CREATE INDEX IF NOT EXISTS idx_components_type ON components(type);
CREATE INDEX IF NOT EXISTS idx_components_path ON components(path);

CREATE TABLE IF NOT EXISTS component_files (
    component_id TEXT NOT NULL REFERENCES components(id),
    file_id      INTEGER NOT NULL REFERENCES files(id),
    PRIMARY KEY (component_id, file_id)
);
CREATE INDEX IF NOT EXISTS idx_component_files_file ON component_files(file_id);

CREATE TABLE IF NOT EXISTS edges (
    id            INTEGER PRIMARY KEY,
    source_id     TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    type          TEXT NOT NULL,
    evidence_json TEXT,
    confidence    TEXT,
    origin        TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);

CREATE TABLE IF NOT EXISTS capabilities (
    id            TEXT PRIMARY KEY,
    component_id  TEXT REFERENCES components(id),
    kind          TEXT NOT NULL,
    name          TEXT,
    detail_json   TEXT,
    evidence_json TEXT,
    confidence    TEXT
);
CREATE INDEX IF NOT EXISTS idx_capabilities_component ON capabilities(component_id);
CREATE INDEX IF NOT EXISTS idx_capabilities_kind ON capabilities(kind);

CREATE TABLE IF NOT EXISTS data_entities (
    id            TEXT PRIMARY KEY,
    component_id  TEXT REFERENCES components(id),
    name          TEXT NOT NULL,
    kind          TEXT,
    fields_json   TEXT,
    evidence_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_data_entities_component ON data_entities(component_id);

CREATE TABLE IF NOT EXISTS entity_access (
    id            INTEGER PRIMARY KEY,
    accessor_id   TEXT NOT NULL,
    entity_id     TEXT NOT NULL REFERENCES data_entities(id),
    mode          TEXT,
    evidence_json TEXT,
    confidence    TEXT
);
CREATE INDEX IF NOT EXISTS idx_entity_access_entity ON entity_access(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_access_accessor ON entity_access(accessor_id);

CREATE TABLE IF NOT EXISTS enrichment (
    id                INTEGER PRIMARY KEY,
    target_kind       TEXT NOT NULL,
    target_id         TEXT NOT NULL,
    payload_json      TEXT,
    derived_from_hash TEXT,
    commit_sha        TEXT,
    created_at        TEXT,
    UNIQUE (target_kind, target_id)
);

CREATE TABLE IF NOT EXISTS coverage (
    path        TEXT PRIMARY KEY,
    disposition TEXT NOT NULL,
    reason      TEXT
);
CREATE INDEX IF NOT EXISTS idx_coverage_disposition ON coverage(disposition);

CREATE TABLE IF NOT EXISTS extraction_cache (
    content_hash   TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    facts_json     TEXT,
    PRIMARY KEY (content_hash, parser_version)
);
"""

# ---------------------------------------------------------------------------
# FTS5 virtual tables. One unified index keeps se_search simple: every row
# carries its ref_kind and ref_id (UNINDEXED, stored so they can be filtered
# and returned) plus the searchable name, path, and free-text body. Populated
# from symbol names + docstrings, component names + descriptions, and
# enrichment help text (TARGET-ARCHITECTURE.md 4.2).
# ---------------------------------------------------------------------------

_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts_docs USING fts5 (
    ref_kind UNINDEXED,
    ref_id   UNINDEXED,
    name,
    path,
    body,
    tokenize = 'unicode61'
);
"""

FTS_AVAILABLE_PROBE = "CREATE VIRTUAL TABLE temp.__fts_probe USING fts5(x);"


def schema_statements(with_fts: bool = True) -> str:
    """Return the full DDL script. FTS can be omitted if the build lacks it."""
    return _CORE_DDL + (_FTS_DDL if with_fts else "")
