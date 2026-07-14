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
#
# Version history:
#   1  P4-1: initial v2 fact-store layout.
#   2  P5-4: git-activity tables (file_activity, file_activity_period,
#            file_author, cochange_pair) for the Activity lens (LENS-DESIGN L5).
#            Additive; see MIGRATIONS below.
#   3  P5-5: rules table (typed rule entities) for the Rules lens (LENS-DESIGN
#            L6). Additive; see MIGRATIONS below.
#   4  P5-6: correlation tables (concerns, findings) for the Concerns and
#            Findings surfaces (LENS-DESIGN section 9). Additive; see MIGRATIONS.
SCHEMA_VERSION = 4

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
# Git-activity tables (schema v2, P5-4; LENS-DESIGN.md L5). Language-agnostic,
# derived from git history, cached by commit range. Keyed by repo-relative git
# path (not files.id): git history references deleted and renamed paths that are
# not in the current files table, and files.id is reassigned each extraction
# run, so a durable, path-keyed identity is required. These tables survive
# clear_extraction_facts; the activity extraction pass owns their lifecycle
# (extraction-adjacent, reads git, invariant I6 cache-by-range). Every read a
# projection depends on sorts by a natural key for byte-determinism (I4).
# ---------------------------------------------------------------------------

_ACTIVITY_DDL = """
CREATE TABLE IF NOT EXISTS file_activity (
    path          TEXT PRIMARY KEY,
    commit_count  INTEGER NOT NULL DEFAULT 0,
    lines_added   INTEGER NOT NULL DEFAULT 0,
    lines_removed INTEGER NOT NULL DEFAULT 0,
    first_seen    TEXT,
    last_modified TEXT
);

CREATE TABLE IF NOT EXISTS file_activity_period (
    path          TEXT NOT NULL,
    period        TEXT NOT NULL,   -- calendar bucket, YYYY-MM (deterministic)
    commit_count  INTEGER NOT NULL DEFAULT 0,
    lines_added   INTEGER NOT NULL DEFAULT 0,
    lines_removed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (path, period)
);

CREATE TABLE IF NOT EXISTS file_author (
    path          TEXT NOT NULL,
    author_key    TEXT NOT NULL,   -- lowercased email, the identity
    author_name   TEXT,            -- display name
    commit_count  INTEGER NOT NULL DEFAULT 0,
    lines_added   INTEGER NOT NULL DEFAULT 0,
    lines_removed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (path, author_key)
);
CREATE INDEX IF NOT EXISTS idx_file_author_path ON file_author(path);

CREATE TABLE IF NOT EXISTS cochange_pair (
    path_a         TEXT NOT NULL,  -- path_a < path_b (lexicographic)
    path_b         TEXT NOT NULL,
    cochange_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (path_a, path_b)
);
CREATE INDEX IF NOT EXISTS idx_cochange_a ON cochange_pair(path_a);
CREATE INDEX IF NOT EXISTS idx_cochange_b ON cochange_pair(path_b);
"""

# ---------------------------------------------------------------------------
# Rules table (schema v3, P5-5; LENS-DESIGN.md L6). Typed rule entities are
# derived (Tier 3) from `rule` signals the extraction tier emits. A rule is a
# discrete unit of decision or constraint logic, kinded validation | calculation
# | policy | io, with a MECHANICAL summary (condition text and outcome, never a
# natural-language explanation: that is Phase 7 enrichment, invariant I1). The
# inputs/outputs, anchor, framework, enclosing-symbol, trigger-capability,
# entity-link and constrained-field detail rides in detail_json (the additive
# payload-column pattern capabilities/data_entities use). Ids are content-derived
# so a re-derive is idempotent; the deterministic reader in db.py sorts by id (I4).
# ---------------------------------------------------------------------------

_RULES_DDL = """
CREATE TABLE IF NOT EXISTS rules (
    id            TEXT PRIMARY KEY,
    component_id  TEXT REFERENCES components(id),
    kind          TEXT NOT NULL,     -- validation | calculation | policy | io
    summary       TEXT,              -- mechanical condition + outcome
    detail_json   TEXT,              -- inputs, outputs, anchor, framework, trigger, symbol, entity, field
    evidence_json TEXT,
    confidence    TEXT
);
CREATE INDEX IF NOT EXISTS idx_rules_component ON rules(component_id);
CREATE INDEX IF NOT EXISTS idx_rules_kind ON rules(kind);
"""

# ---------------------------------------------------------------------------
# Correlation tables (schema v4, P5-6; LENS-DESIGN.md section 9). Concerns are
# cross-cutting membership sets orthogonal to the containment hierarchy
# (logging, auth, persistence, http-client, caching, configuration, plus
# clone-derived concerns); findings are typed, ranked, evidenced correlations
# (duplication clusters, orphans, inconsistency candidates). Both are DERIVED
# (Tier 3) from stored signals, edges, and imports, never from a source re-read
# (invariant I1). Members and per-member evidence ride in *_json payload columns
# (the additive pattern capabilities/rules use); component references are soft
# ids, not FKs, so the derivation flush order stays trivial. Findings default to
# verification_status='unverified' (P7-4 flips it, invariant I15) and carry a
# deterministic rank_score (I11). Ids are content-derived so a re-derive is
# idempotent; the deterministic readers in db.py sort by id (concerns) and by
# rank_score desc then id (findings) for byte-determinism (I4).
# ---------------------------------------------------------------------------

_CORRELATIONS_DDL = """
CREATE TABLE IF NOT EXISTS concerns (
    id           TEXT PRIMARY KEY,   -- slug: concern:logging, concern:clone-<hash>
    kind         TEXT NOT NULL,      -- logging|auth|persistence|http-client|caching|configuration|clone
    title        TEXT,               -- mechanical title (AI naming is P7-4)
    basis        TEXT,               -- mechanical detection basis
    members_json TEXT,               -- [{component_id, files:[...], evidence:[...]}]
    detail_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_concerns_kind ON concerns(kind);

CREATE TABLE IF NOT EXISTS findings (
    id                  TEXT PRIMARY KEY,  -- finding:duplication:<hash> | finding:orphan:<comp> | finding:inconsistency:<slug>-<hash>
    kind                TEXT NOT NULL,     -- duplication|orphan|inconsistency
    summary             TEXT,              -- mechanical summary
    members_json        TEXT,              -- [{kind, id, file, line_start, line_end, component_id}]
    evidence_json       TEXT,
    confidence          TEXT,              -- inferred (deterministic tier)
    verification_status TEXT NOT NULL,     -- 'unverified' until P7-4 verifies
    rank_score          REAL NOT NULL,     -- I11/I15 ranking input
    detail_json         TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_kind ON findings(kind);
CREATE INDEX IF NOT EXISTS idx_findings_rank ON findings(rank_score);
"""

# Migration registry: MIGRATIONS[v] is the DDL that upgrades a store at version
# v-1 to version v. Each script is idempotent (IF NOT EXISTS), so re-running is
# safe. A cold store gets every table from schema_statements in one shot; a warm
# store at an older version runs the gap scripts in order (db.py._create_schema).
MIGRATIONS: dict[int, str] = {
    2: _ACTIVITY_DDL,        # v1 -> v2: add the git-activity tables (P5-4)
    3: _RULES_DDL,           # v2 -> v3: add the rules table (P5-5)
    4: _CORRELATIONS_DDL,    # v3 -> v4: add the concerns + findings tables (P5-6)
}

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
    return (
        _CORE_DDL + _ACTIVITY_DDL + _RULES_DDL + _CORRELATIONS_DDL
        + (_FTS_DDL if with_fts else "")
    )
