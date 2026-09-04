"""The fact store: a thin, deterministic wrapper over stdlib sqlite3.

SQLite is durable truth (TARGET-ARCHITECTURE.md 4.2, invariant I7: the store is
a file, no server). This module opens the database in WAL mode, applies the
schema from schema.py, writes each entity type, and reads them back in a
deterministic order so projections are reproducible (invariant I4).

It also carries the thin query surface the projection and MCP tiers build on:
lookup by name / path / kind over FTS, and bounded-depth edge traversal via a
recursive CTE (the CTE fallback in 4.2, no rustworkx dependency at this tier).

No imports from scanner.py or incremental.py. Standard library only.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

from . import __version__ as store_version
from .schema import MIGRATIONS, SCHEMA_VERSION, schema_statements

__all__ = ["FactStore", "fts5_available"]


def fts5_available() -> bool:
    """Return True if this SQLite build can create FTS5 virtual tables."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE __probe USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def _dumps(value: Any) -> Optional[str]:
    """Deterministic JSON for stored blobs (sorted keys, compact)."""
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _loads(text: Optional[str]) -> Any:
    return json.loads(text) if text else None


class FactStore:
    """Read/write access to a v2 fact-store database file.

    Use as a context manager or call :meth:`close` explicitly. Passing
    ``":memory:"`` gives an ephemeral store for tests.
    """

    def __init__(self, path: str | Path = ":memory:", *, with_fts: Optional[bool] = None, read_only: bool = False):
        self.path = str(path)
        if read_only:
            # Presentation/export readers must never create tables, migrate a
            # schema, or switch the canonical database's journal mode.
            self._conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA query_only = ON")
            self.with_fts = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'fts_docs'"
            ).fetchone() is not None
            return
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            # WAL is durable and concurrent-read friendly; harmless in-memory
            # (SQLite ignores it), so we only set it for on-disk stores.
            self._conn.execute("PRAGMA journal_mode = WAL")
        self.with_fts = fts5_available() if with_fts is None else with_fts
        self._create_schema()

    # -- lifecycle ---------------------------------------------------------

    def _create_schema(self) -> None:
        """Create tables if absent and apply version-gap migrations.

        A cold store gets every table from ``schema_statements`` in one shot and
        is stamped at the current ``SCHEMA_VERSION``. A warm store at an older
        version runs each migration script in ``schema.MIGRATIONS`` from its
        recorded version up to the current one, in order, then bumps its
        ``schema_version`` (P5-4 added the migration path; before it any version
        mismatch raised). A store from a newer code version than this one is a
        hard error: we will not silently truncate future data.
        """
        self._conn.executescript(schema_statements(with_fts=self.with_fts))
        existing = self.get_meta("schema_version")
        if existing is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
            self.set_meta("store_version", store_version)
        else:
            ev = int(existing)
            if ev > SCHEMA_VERSION:
                raise ValueError(
                    f"store schema_version {ev} is newer than code "
                    f"SCHEMA_VERSION {SCHEMA_VERSION}; upgrade the analyzer"
                )
            if ev < SCHEMA_VERSION:
                for target in range(ev + 1, SCHEMA_VERSION + 1):
                    ddl = MIGRATIONS.get(target)
                    if ddl:
                        self._conn.executescript(ddl)
                self.set_meta("schema_version", str(SCHEMA_VERSION))
        self._conn.commit()

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> FactStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- meta --------------------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    # -- writers -----------------------------------------------------------

    def add_file(
        self,
        path: str,
        language: Optional[str] = None,
        lines: Optional[int] = None,
        size_bytes: Optional[int] = None,
        content_hash: Optional[str] = None,
        parse_status: Optional[str] = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO files(path, language, lines, size_bytes, content_hash, parse_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (path, language, lines, size_bytes, content_hash, parse_status),
        )
        return int(cur.lastrowid)

    def add_symbol(
        self,
        symbol_id: str,
        file_id: int,
        name: str,
        kind: Optional[str] = None,
        parent_id: Optional[str] = None,
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        visibility: Optional[str] = None,
        docstring: Optional[str] = None,
        code_preview: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO symbols(id, file_id, name, kind, parent_id, line, end_line, "
            "visibility, docstring, code_preview) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol_id, file_id, name, kind, parent_id, line, end_line,
             visibility, docstring, code_preview),
        )
        if self.with_fts:
            self._conn.execute(
                "INSERT INTO fts_docs(ref_kind, ref_id, name, path, body) "
                "VALUES ('symbol', ?, ?, ?, ?)",
                (symbol_id, name, "", docstring or ""),
            )

    def add_signal(
        self, file_id: int, kind: str, value: Any = None, line: Optional[int] = None
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO signals(file_id, kind, value_json, line) VALUES (?, ?, ?, ?)",
            (file_id, kind, _dumps(value), line),
        )
        return int(cur.lastrowid)

    def add_component(
        self,
        component_id: str,
        name: str,
        type: Optional[str] = None,
        path: Optional[str] = None,
        parent_id: Optional[str] = None,
        role: Optional[str] = None,
        meta: Any = None,
        description: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO components(id, name, type, path, parent_id, role, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (component_id, name, type, path, parent_id, role, _dumps(meta)),
        )
        if self.with_fts:
            self._conn.execute(
                "INSERT INTO fts_docs(ref_kind, ref_id, name, path, body) "
                "VALUES ('component', ?, ?, ?, ?)",
                (component_id, name, path or "", description or ""),
            )

    def link_component_file(self, component_id: str, file_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO component_files(component_id, file_id) VALUES (?, ?)",
            (component_id, file_id),
        )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        type: str,
        evidence: Any = None,
        confidence: Optional[str] = None,
        origin: Optional[str] = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO edges(source_id, target_id, type, evidence_json, confidence, origin) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, target_id, type, _dumps(evidence), confidence, origin),
        )
        return int(cur.lastrowid)

    def add_capability(
        self,
        capability_id: str,
        component_id: Optional[str],
        kind: str,
        name: Optional[str] = None,
        detail: Any = None,
        evidence: Any = None,
        confidence: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO capabilities(id, component_id, kind, name, detail_json, "
            "evidence_json, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (capability_id, component_id, kind, name, _dumps(detail),
             _dumps(evidence), confidence),
        )

    def add_data_entity(
        self,
        entity_id: str,
        component_id: Optional[str],
        name: str,
        kind: Optional[str] = None,
        fields: Any = None,
        evidence: Any = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO data_entities(id, component_id, name, kind, fields_json, evidence_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entity_id, component_id, name, kind, _dumps(fields), _dumps(evidence)),
        )

    def add_entity_access(
        self,
        accessor_id: str,
        entity_id: str,
        mode: Optional[str] = None,
        evidence: Any = None,
        confidence: Optional[str] = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO entity_access(accessor_id, entity_id, mode, evidence_json, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            (accessor_id, entity_id, mode, _dumps(evidence), confidence),
        )
        return int(cur.lastrowid)

    def add_rule(
        self,
        rule_id: str,
        component_id: Optional[str],
        kind: str,
        summary: Optional[str] = None,
        detail: Any = None,
        evidence: Any = None,
        confidence: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO rules(id, component_id, kind, summary, detail_json, "
            "evidence_json, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rule_id, component_id, kind, summary, _dumps(detail),
             _dumps(evidence), confidence),
        )

    def add_concern(
        self,
        concern_id: str,
        kind: str,
        title: Optional[str] = None,
        basis: Optional[str] = None,
        members: Any = None,
        detail: Any = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO concerns(id, kind, title, basis, members_json, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (concern_id, kind, title, basis, _dumps(members), _dumps(detail)),
        )

    def add_finding(
        self,
        finding_id: str,
        kind: str,
        summary: Optional[str] = None,
        members: Any = None,
        evidence: Any = None,
        confidence: Optional[str] = None,
        verification_status: str = "unverified",
        rank_score: float = 0.0,
        detail: Any = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO findings(id, kind, summary, members_json, evidence_json, "
            "confidence, verification_status, rank_score, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (finding_id, kind, summary, _dumps(members), _dumps(evidence),
             confidence, verification_status, float(rank_score), _dumps(detail)),
        )

    def add_enrichment(
        self,
        target_kind: str,
        target_id: str,
        payload: Any,
        derived_from_hash: Optional[str] = None,
        commit_sha: Optional[str] = None,
        created_at: Optional[str] = None,
        help_text: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO enrichment(target_kind, target_id, payload_json, "
            "derived_from_hash, commit_sha, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(target_kind, target_id) DO UPDATE SET "
            "payload_json = excluded.payload_json, "
            "derived_from_hash = excluded.derived_from_hash, "
            "commit_sha = excluded.commit_sha, created_at = excluded.created_at",
            (target_kind, target_id, _dumps(payload), derived_from_hash,
             commit_sha, created_at),
        )
        if self.with_fts:
            # The enrichment row is an upsert, so the FTS entry must be
            # replaced, not appended: re-enriching the same target would
            # otherwise accumulate duplicate and outdated search hits. The
            # delete also covers a re-enrichment that drops help_text.
            ref = f"{target_kind}:{target_id}"
            self._conn.execute(
                "DELETE FROM fts_docs WHERE ref_kind = 'enrichment' AND ref_id = ?",
                (ref,),
            )
            if help_text:
                self._conn.execute(
                    "INSERT INTO fts_docs(ref_kind, ref_id, name, path, body) "
                    "VALUES ('enrichment', ?, ?, '', ?)",
                    (ref, "", help_text),
                )

    def set_finding_verification(self, finding_id: str, status: str) -> None:
        """Update a finding's verification_status in place (P7-4 sub-pass 3).

        Additive helper. Note the derivation ``_flush`` rewrites the findings
        table every run and resets rows to 'unverified', so this is a
        same-session convenience for direct readers; the durable, provenance-
        stamped record of a verdict is the enrichment overlay (see
        analyzer/enrich/verdicts.py). A no-op when the finding id is absent.
        """
        self._conn.execute(
            "UPDATE findings SET verification_status = ? WHERE id = ?",
            (status, finding_id),
        )

    def delete_enrichment(self, target_kind: str, target_id: str) -> None:
        """Delete an enrichment row (and its FTS entry) if present.

        Used when a Phase 7 pass supersedes a prior verdict: a declared intent
        that is now satisfied removes its stale violation finding rather than
        leaving stale data (no silent anything).
        """
        self._conn.execute(
            "DELETE FROM enrichment WHERE target_kind = ? AND target_id = ?",
            (target_kind, target_id),
        )
        if self.with_fts:
            ref = f"{target_kind}:{target_id}"
            self._conn.execute(
                "DELETE FROM fts_docs WHERE ref_kind = 'enrichment' AND ref_id = ?",
                (ref,),
            )

    def add_coverage(self, path: str, disposition: str, reason: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO coverage(path, disposition, reason) VALUES (?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET disposition = excluded.disposition, "
            "reason = excluded.reason",
            (path, disposition, reason),
        )

    def cache_facts(self, content_hash: str, parser_version: str, facts: Any) -> None:
        self._conn.execute(
            "INSERT INTO extraction_cache(content_hash, parser_version, facts_json) "
            "VALUES (?, ?, ?) ON CONFLICT(content_hash, parser_version) DO UPDATE SET "
            "facts_json = excluded.facts_json",
            (content_hash, parser_version, _dumps(facts)),
        )

    def get_cached_facts(self, content_hash: str, parser_version: str) -> Any:
        row = self._conn.execute(
            "SELECT facts_json FROM extraction_cache WHERE content_hash = ? AND parser_version = ?",
            (content_hash, parser_version),
        ).fetchone()
        return _loads(row["facts_json"]) if row else None

    def cached_facts_by_hash(self) -> dict[str, Any]:
        """Map content_hash -> cached facts dict, for Tier 3 derivation reads.

        Facts are content-addressed, so one entry per content hash within a
        single analysis (only one parser tier is active per run). Derivation
        joins this to the ``files`` table on ``content_hash`` to recover a
        file's imports, module doc, and raw content without touching the disk
        (TARGET-ARCHITECTURE.md 4.3). Deterministic: rows are read in
        (content_hash, parser_version) order so a later duplicate never wins
        nondeterministically. Additive read helper only; schema is FROZEN.
        """
        rows = self._conn.execute(
            "SELECT content_hash, parser_version, facts_json FROM extraction_cache "
            "ORDER BY content_hash, parser_version"
        ).fetchall()
        out: dict[str, Any] = {}
        for r in rows:
            out.setdefault(r["content_hash"], _loads(r["facts_json"]))
        return out

    # -- deterministic readers --------------------------------------------
    #
    # Every read that a projection depends on sorts by a stable natural key so
    # repeated runs over the same store are byte-identical.

    def files(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM files ORDER BY path"
        ).fetchall()
        return [dict(r) for r in rows]

    def symbols(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM symbols ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def signals(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM signals ORDER BY file_id, kind, line, id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["value"] = _loads(d.pop("value_json"))
            out.append(d)
        return out

    def components(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM components ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["meta"] = _loads(d.pop("meta_json"))
            out.append(d)
        return out

    def component_files(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT cf.component_id, f.path FROM component_files cf "
            "JOIN files f ON f.id = cf.file_id ORDER BY cf.component_id, f.path"
        ).fetchall()
        return [dict(r) for r in rows]

    def edges(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM edges ORDER BY source_id, target_id, type, id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["evidence"] = _loads(d.pop("evidence_json"))
            out.append(d)
        return out

    def capabilities(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM capabilities ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = _loads(d.pop("detail_json"))
            d["evidence"] = _loads(d.pop("evidence_json"))
            out.append(d)
        return out

    def data_entities(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM data_entities ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["fields"] = _loads(d.pop("fields_json"))
            d["evidence"] = _loads(d.pop("evidence_json"))
            out.append(d)
        return out

    def entity_access(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM entity_access ORDER BY accessor_id, entity_id, mode, id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["evidence"] = _loads(d.pop("evidence_json"))
            out.append(d)
        return out

    def rules(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM rules ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = _loads(d.pop("detail_json"))
            d["evidence"] = _loads(d.pop("evidence_json"))
            out.append(d)
        return out

    def concerns(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM concerns ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["members"] = _loads(d.pop("members_json"))
            d["detail"] = _loads(d.pop("detail_json"))
            out.append(d)
        return out

    def findings(self) -> list[dict]:
        # Ranked surface (invariant I11): highest rank_score first, id as the
        # deterministic tie-break so repeated reads are byte-identical (I4).
        rows = self._conn.execute(
            "SELECT * FROM findings ORDER BY rank_score DESC, id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["members"] = _loads(d.pop("members_json"))
            d["evidence"] = _loads(d.pop("evidence_json"))
            d["detail"] = _loads(d.pop("detail_json"))
            out.append(d)
        return out

    def enrichment(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM enrichment ORDER BY target_kind, target_id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = _loads(d.pop("payload_json"))
            out.append(d)
        return out

    def coverage(self, disposition: Optional[str] = None) -> list[dict]:
        if disposition is not None:
            rows = self._conn.execute(
                "SELECT * FROM coverage WHERE disposition = ? ORDER BY path",
                (disposition,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM coverage ORDER BY path"
            ).fetchall()
        return [dict(r) for r in rows]

    def coverage_summary(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT disposition, COUNT(*) AS n FROM coverage "
            "GROUP BY disposition ORDER BY disposition"
        ).fetchall()
        return {r["disposition"]: r["n"] for r in rows}

    # -- query surface (thin) ---------------------------------------------

    def lookup_by_name(self, name: str) -> list[dict]:
        """Exact-name lookup across symbols and components, deterministic."""
        rows = self._conn.execute(
            "SELECT 'symbol' AS ref_kind, id AS ref_id, name FROM symbols WHERE name = ? "
            "UNION ALL "
            "SELECT 'component' AS ref_kind, id AS ref_id, name FROM components WHERE name = ? "
            "ORDER BY ref_kind, ref_id",
            (name, name),
        ).fetchall()
        return [dict(r) for r in rows]

    def lookup_by_path(self, path: str) -> list[dict]:
        """Lookup files and components by exact repo-relative path."""
        rows = self._conn.execute(
            "SELECT 'file' AS ref_kind, path FROM files WHERE path = ? "
            "UNION ALL "
            "SELECT 'component' AS ref_kind, path FROM components WHERE path = ? "
            "ORDER BY ref_kind",
            (path, path),
        ).fetchall()
        return [dict(r) for r in rows]

    def symbols_by_kind(self, kind: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM symbols WHERE kind = ? ORDER BY id", (kind,)
        ).fetchall()
        return [dict(r) for r in rows]

    def components_by_type(self, type: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM components WHERE type = ? ORDER BY id", (type,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search(
        self, query: str, ref_kind: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        """FTS5 search over names, paths, and free text. Ranked by bm25.

        Returns rows of {ref_kind, ref_id, name, path}. Requires an FTS build;
        raises RuntimeError otherwise so the caller can fall back explicitly
        rather than silently returning nothing (invariant: no silent anything).
        """
        if not self.with_fts:
            raise RuntimeError("FTS5 is unavailable in this SQLite build")
        sql = (
            "SELECT ref_kind, ref_id, name, path FROM fts_docs "
            "WHERE fts_docs MATCH ?"
        )
        params: list[Any] = [query]
        if ref_kind is not None:
            sql += " AND ref_kind = ?"
            params.append(ref_kind)
        sql += " ORDER BY bm25(fts_docs), ref_kind, ref_id LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def traverse(
        self, start_id: str, direction: str = "out", max_depth: int = 3
    ) -> list[dict]:
        """Bounded-depth edge traversal via a recursive CTE.

        direction 'out' follows source->target (callees / dependencies);
        'in' follows target->source (callers / dependents). Returns reachable
        node ids with their minimum depth, excluding the start, ordered by
        (depth, id) for determinism.
        """
        if direction not in ("out", "in"):
            raise ValueError("direction must be 'out' or 'in'")
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if direction == "out":
            step = "SELECT e.target_id AS node, r.depth + 1 FROM edges e " \
                   "JOIN reach r ON e.source_id = r.node WHERE r.depth < ?"
        else:
            step = "SELECT e.source_id AS node, r.depth + 1 FROM edges e " \
                   "JOIN reach r ON e.target_id = r.node WHERE r.depth < ?"
        sql = (
            "WITH RECURSIVE reach(node, depth) AS ("
            "  SELECT ?, 0 "
            "  UNION "
            f"  {step}"
            ") "
            "SELECT node, MIN(depth) AS depth FROM reach WHERE node <> ? "
            "GROUP BY node ORDER BY depth, node"
        )
        rows = self._conn.execute(sql, (start_id, max_depth, start_id)).fetchall()
        return [{"id": r["node"], "depth": r["depth"]} for r in rows]

    # -- git activity (schema v2, P5-4) ------------------------------------
    #
    # All merges are additive: each commit contributes independently, so
    # processing a commit range and adding to existing counts equals a full
    # reprocess (invariant I6, cache-by-range). first_seen/last_modified fold
    # with MIN/MAX. Callers accumulate per-range deltas in memory and write once.

    def merge_file_activity(self, rows: Iterable[tuple]) -> None:
        """Upsert (path, commit_count, lines_added, lines_removed, first_seen,
        last_modified); counts add, first_seen folds MIN, last_modified MAX."""
        self._conn.executemany(
            "INSERT INTO file_activity(path, commit_count, lines_added, "
            "lines_removed, first_seen, last_modified) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "commit_count = commit_count + excluded.commit_count, "
            "lines_added = lines_added + excluded.lines_added, "
            "lines_removed = lines_removed + excluded.lines_removed, "
            "first_seen = MIN(first_seen, excluded.first_seen), "
            "last_modified = MAX(last_modified, excluded.last_modified)",
            rows,
        )

    def merge_file_activity_periods(self, rows: Iterable[tuple]) -> None:
        """Upsert (path, period, commit_count, lines_added, lines_removed)."""
        self._conn.executemany(
            "INSERT INTO file_activity_period(path, period, commit_count, "
            "lines_added, lines_removed) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(path, period) DO UPDATE SET "
            "commit_count = commit_count + excluded.commit_count, "
            "lines_added = lines_added + excluded.lines_added, "
            "lines_removed = lines_removed + excluded.lines_removed",
            rows,
        )

    def merge_file_authors(self, rows: Iterable[tuple]) -> None:
        """Upsert (path, author_key, author_name, commit_count, lines_added,
        lines_removed); counts add, author_name updates to the latest seen."""
        self._conn.executemany(
            "INSERT INTO file_author(path, author_key, author_name, "
            "commit_count, lines_added, lines_removed) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path, author_key) DO UPDATE SET "
            "author_name = excluded.author_name, "
            "commit_count = commit_count + excluded.commit_count, "
            "lines_added = lines_added + excluded.lines_added, "
            "lines_removed = lines_removed + excluded.lines_removed",
            rows,
        )

    def merge_cochange_pairs(self, rows: Iterable[tuple]) -> None:
        """Upsert (path_a, path_b, cochange_count) with path_a < path_b."""
        self._conn.executemany(
            "INSERT INTO cochange_pair(path_a, path_b, cochange_count) "
            "VALUES (?, ?, ?) ON CONFLICT(path_a, path_b) DO UPDATE SET "
            "cochange_count = cochange_count + excluded.cochange_count",
            rows,
        )

    def clear_activity(self) -> None:
        """Drop all git-activity rows and provenance (a full reprocess).

        Used when the recorded HEAD is not an ancestor of the new HEAD
        (rebase / force-push / shallow-boundary shift), where an additive merge
        would double-count. A cold store's tables are already empty (no-op).
        """
        self._conn.execute("DELETE FROM file_activity")
        self._conn.execute("DELETE FROM file_activity_period")
        self._conn.execute("DELETE FROM file_author")
        self._conn.execute("DELETE FROM cochange_pair")
        self._conn.execute(
            "DELETE FROM meta WHERE key LIKE 'activity_%'"
        )

    def file_activity(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM file_activity ORDER BY path"
        ).fetchall()
        return [dict(r) for r in rows]

    def file_activity_periods(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM file_activity_period ORDER BY path, period"
        ).fetchall()
        return [dict(r) for r in rows]

    def file_authors(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM file_author ORDER BY path, author_key"
        ).fetchall()
        return [dict(r) for r in rows]

    def cochange_pairs(self, min_support: int = 1) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM cochange_pair WHERE cochange_count >= ? "
            "ORDER BY path_a, path_b",
            (min_support,),
        ).fetchall()
        return [dict(r) for r in rows]

    def has_activity(self) -> bool:
        """True if the store carries any git-activity rows."""
        row = self._conn.execute(
            "SELECT 1 FROM file_activity LIMIT 1"
        ).fetchone()
        return row is not None

    def apply_activity_renames(self, mapping: dict[str, str]) -> None:
        """Migrate already-stored activity rows from old paths to new paths.

        Used on an incremental (fast-forward) run when a rename happened inside
        the newly processed commit range: history accumulated under the old path
        must move to the current path so an incremental run matches a full
        reprocess (which canonicalizes the whole history to current names). Rows
        are pulled into memory, remapped, deleted, and re-merged through the
        additive helpers, so a collision with an existing new-path row folds
        correctly. Self-pairs that a co-change remap collapses are dropped.
        """
        mapping = {o: n for o, n in mapping.items() if o != n}
        if not mapping:
            return
        old_paths = set(mapping)

        def remap(p: str) -> str:
            return mapping.get(p, p)

        # file_activity
        rows = [dict(r) for r in self._conn.execute("SELECT * FROM file_activity")]
        moved = [r for r in rows if r["path"] in old_paths]
        for r in moved:
            self._conn.execute("DELETE FROM file_activity WHERE path = ?", (r["path"],))
        self.merge_file_activity(
            (remap(r["path"]), r["commit_count"], r["lines_added"],
             r["lines_removed"], r["first_seen"], r["last_modified"]) for r in moved
        )

        # file_activity_period
        rows = [dict(r) for r in self._conn.execute("SELECT * FROM file_activity_period")]
        moved = [r for r in rows if r["path"] in old_paths]
        for r in moved:
            self._conn.execute(
                "DELETE FROM file_activity_period WHERE path = ? AND period = ?",
                (r["path"], r["period"]),
            )
        self.merge_file_activity_periods(
            (remap(r["path"]), r["period"], r["commit_count"],
             r["lines_added"], r["lines_removed"]) for r in moved
        )

        # file_author
        rows = [dict(r) for r in self._conn.execute("SELECT * FROM file_author")]
        moved = [r for r in rows if r["path"] in old_paths]
        for r in moved:
            self._conn.execute(
                "DELETE FROM file_author WHERE path = ? AND author_key = ?",
                (r["path"], r["author_key"]),
            )
        self.merge_file_authors(
            (remap(r["path"]), r["author_key"], r["author_name"],
             r["commit_count"], r["lines_added"], r["lines_removed"]) for r in moved
        )

        # cochange_pair: remap both endpoints, re-sort, drop self-pairs
        rows = [dict(r) for r in self._conn.execute("SELECT * FROM cochange_pair")]
        moved = [r for r in rows if r["path_a"] in old_paths or r["path_b"] in old_paths]
        for r in moved:
            self._conn.execute(
                "DELETE FROM cochange_pair WHERE path_a = ? AND path_b = ?",
                (r["path_a"], r["path_b"]),
            )
        new_pairs = []
        for r in moved:
            a, b = remap(r["path_a"]), remap(r["path_b"])
            if a == b:
                continue
            lo, hi = (a, b) if a < b else (b, a)
            new_pairs.append((lo, hi, r["cochange_count"]))
        self.merge_cochange_pairs(new_pairs)

    # -- extraction reset (additive helper for the Tier 1 runner) ----------

    def clear_extraction_facts(self) -> None:
        """Delete the rows Tier 1 owns, keeping the extraction cache.

        Extraction is content-addressed and idempotent: a re-run rebuilds
        ``files``, ``symbols``, ``signals``, and ``coverage`` from the cache
        (no re-parse for unchanged files, invariant I6) rather than appending
        duplicates. The extraction_cache is left intact (it is the incremental
        baseline). Symbols and signals are deleted before files to respect the
        FK.

        ``component_files`` is cleared too: on a WARM store (P4-6) it was
        populated by the previous run's Tier 3 flush and its ``file_id`` FK
        would otherwise block ``DELETE FROM files`` when extraction reassigns
        file ids. Derivation's ``_flush`` rebuilds ``component_files`` (and
        ``components``/``edges``) from scratch on the same run, and extraction
        always precedes derivation, so clearing it here is safe and keeps a
        warm re-extraction from stranding memberships that point at stale file
        ids. On a cold (fresh) store the table is empty and this is a no-op.
        """
        self._conn.execute("DELETE FROM symbols")
        self._conn.execute("DELETE FROM signals")
        self._conn.execute("DELETE FROM coverage")
        self._conn.execute("DELETE FROM component_files")
        self._conn.execute("DELETE FROM files")
        if self.with_fts:
            self._conn.execute("DELETE FROM fts_docs WHERE ref_kind = 'symbol'")
        self._conn.commit()

    # -- bulk load helper --------------------------------------------------

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    def add_files_bulk(self, rows: Iterable[tuple]) -> None:
        self._conn.executemany(
            "INSERT INTO files(path, language, lines, size_bytes, content_hash, parse_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
