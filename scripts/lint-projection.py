#!/usr/bin/env python3
"""Deterministic linter for a projected architecture dataset.

The analyzer's own tests prove the analyzer's units. The demo gates prove a
bundle is publishable. Neither one reads a finished projection end to end and
asks the flat question a reviewer asks: **is this artifact internally whole, and
does every claim in it point at something that actually exists?**

That is this script. It is a linter for our own output format, in the same
sense that a compiler lints source: no model, no judgement, no sampling of
opinion. Same bytes in, same report out. It is meant to run against a full
deterministic generation before anyone looks at the viewer, so that a UI defect
is never chased when the underlying data was already broken.

Four bands of checks, deliberately separated because they fail for different
reasons and carry different authority:

  parse.*   The artifact set exists, is UTF-8, and is JSON. Nothing else can be
            said until this passes, so a failure here stops the band.
  shape.*   Required keys with the right types on every record kind. Presence
            and type only. What a value MEANS is out of scope, the same line
            analyzer/contracts.py draws for postconditions, and for the same
            reason: validation creep toward content checks is the failure mode.
  ref.*     Referential integrity, which is the band that earns the script.
            Every id that one part of the artifact names must resolve in the
            part that owns it: relationship endpoints, the detail index against
            both the tree and the files on disk, every lens array's
            component_id, search entries, the front door's endpoint list.
            This is the "data is there but you cannot get to it" class, caught
            before a browser is opened.
  count.*   The numbers the artifact states about itself agree with the
            artifact. A stat that disagrees with its own payload is a defect
            even when both halves are individually well formed.

Then two bands that are about the map's relationship to the territory rather
than to itself:

  source.*  Accusability. Every file path and every file:line the map cites is
            checked against the real source tree: the file exists, the line is
            inside it, and (sampled) the symbol the map names is actually on
            the line it names. This is the light validation against source, not
            a re-derivation of the analysis. Skipped, loudly and by name, when
            the source tree is not available.
  census.*  Completeness heuristics. How complete does the map APPEAR: empty
            nodes, tree depth, unknown languages, per-lens population, coverage
            gaps, enrichment uniformity. These are reported as numbers always
            and enforced only where a threshold in the policy says so, because
            "thin" is a property of the subject as much as of the tool.

Stdlib only. It has to run wherever the artifact lands, including a CI job that
installed nothing, which is the same constraint scripts/validate-publication.py
works under. It imports one helper from the analyzer (the shard-filename
escape) when the analyzer happens to be importable, and falls back to a local
copy otherwise, so the encoding can never drift silently.

Exit codes: 0 clean, 1 errors found, 2 warnings found under --strict, 3 the
projection directory could not be read at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# The shard-filename escape. Imported from the analyzer so the linter cannot
# drift from the writer; the fallback keeps the script standalone where the
# package is not on the path (a bundle checked out on its own, a CI job that
# only downloaded the artifact).
try:  # pragma: no cover - exercised by whichever branch the environment takes
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from analyzer.project.naming import safe_component_id
except Exception:  # pragma: no cover
    def safe_component_id(comp_id: str) -> str:
        return comp_id.replace("/", "--").replace(":", "__")


# How many concrete examples to print per rule before collapsing into a count.
# A broken id scheme produces thousands of identical violations; the report has
# to stay readable without hiding the true scale, so every rule prints its cap
# and then says how many more there were.
EXAMPLE_CAP = 8

# Symbols whose declared line is opened and checked against the symbol's name.
# Reading every file for every symbol is affordable locally but pointless: the
# check is a spot check for a whole-file off-by-one or a stale shard, not a
# parser re-run. Sampling is a deterministic stride over sorted ids, so the same
# artifact always samples the same symbols.
DEFAULT_CONTENT_SAMPLE = 500

# Absolute-path prefixes that must not appear anywhere in a projection except
# the manifest's own root_path field. A leaked home directory is a determinism
# hazard and, for a published bundle, an information leak.
ABSOLUTE_PATH_RE = re.compile(r"(?:/Users/|/home/|/Volumes/|[A-Za-z]:\\\\Users\\\\)[^\"'\s]+")

# The record kinds a lens array can carry, and the field in each that names the
# component it belongs to. Adding a lens means adding a line here, and the
# ref band then covers it automatically.
LENS_COMPONENT_FIELDS = {
    "capabilities": ("component_id",),
    "ai_surface": ("component_id",),
    "rules": ("component_id",),
    "data_entities": ("component_id",),
    "entity_access": ("accessor_id",),
}

DEFAULT_POLICY: dict[str, Any] = {
    # "deterministic" expects no ai_enhance anywhere; "enriched" expects it on
    # every component. ``evaluation`` admits a deliberately partial overlay only
    # when a private publication sidecar tells the reader exactly that.  This is
    # not a relaxation of the public enriched gate: it is a separate posture for
    # human evaluation of a bounded canary.
    "profile": "deterministic",
    # A component with no files and no children renders as a dead end in the
    # viewer. A few are legitimate (a namespace folder); a lot is a defect.
    "max_empty_node_share": 0.10,
    # A flat tree on a large subject means the component deriver collapsed, and
    # it is the exact shape that makes the viewer look fine while being useless.
    "min_depth_over_components": [20, 2],
    "max_unknown_language_share": 0.50,
    # The coverage ledger's whole promise: every file accounted for exactly once.
    "max_unaccounted_files": 0,
    # A lens that silently loses its whole array still renders, empty. Naming
    # the lenses that must be populated turns that into a failure.
    "require_populated": [],
    "max_symbol_line_mismatch_share": 0.05,
    # Per-component ceilings, in the units a reader pays for.
    #
    # These exist because of a real failure, not a theory. On the private large-repository validation corpus
    # projection one component (src/vs/workbench) held 3,625 files and 47,339
    # symbols in a single 50 MB detail shard, and opening it pinned the browser
    # at 100% CPU and about 900 MB for over half an hour. Every earlier check
    # passed: the data was internally consistent, every id resolved, every
    # citation was real. It was simply unopenable.
    #
    # So the question this band asks is not "is the artifact correct" but "can
    # anyone actually use it". A component that cannot be opened is not a
    # rendering problem to fix downstream, it is a derivation that grouped too
    # much under one node, and the honest place to say so is here, before a
    # browser is ever pointed at it.
    "max_component_files": 1500,
    "max_component_symbols": 20000,
    "max_shard_bytes": 20_000_000,
    # The number that decides the verdict. max_shard_bytes above is only a cheap
    # prefilter that says "measure this one properly"; this is the budget for
    # what a reader actually waits for. 8 MB compressed is roughly a
    # photograph-heavy page, and private large-repository validation corpus's heaviest component lands at 4.4 MB.
    "max_shard_transfer_bytes": 8_000_000,
}

# Languages whose real parser emits a "method" kind (analyzer/parsers/*_ts.py and
# friends). A projection dominated by these and carrying no methods at all did
# not meet the parser it was supposed to meet.
METHOD_BEARING_LANGUAGES = {
    "cpp", "csharp", "go", "java", "ruby", "rust", "swift", "typescript",
    "javascript", "kotlin", "scala", "php",
}


@dataclass
class Finding:
    rule: str
    severity: str  # "error" | "warn" | "info"
    message: str
    where: str = ""

    def render(self) -> str:
        loc = f" [{self.where}]" if self.where else ""
        return f"{self.message}{loc}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    census: dict[str, Any] = field(default_factory=dict)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def error(self, rule: str, message: str, where: str = "") -> None:
        self.findings.append(Finding(rule, "error", message, where))

    def warn(self, rule: str, message: str, where: str = "") -> None:
        self.findings.append(Finding(rule, "warn", message, where))

    def info(self, rule: str, message: str, where: str = "") -> None:
        """Record something true and worth stating that nobody should act on.

        The third severity exists because of the absolute-path bands. A path the
        SUBJECT wrote into its own README is a real observation, and it is also
        something we will never fix, because fixing it would mean rewriting the
        subject's documentation so our copy no longer matches the real file. A
        finding that reappears on every run and is correctly ignored every time
        teaches people to ignore the whole report, which costs more than the
        finding is worth. So it is stated, and it is not a warning.
        """
        self.findings.append(Finding(rule, "info", message, where))

    def skip(self, rule_prefix: str, reason: str) -> None:
        """Record a band that could not run. A skipped check is never silent."""
        self.skipped.append((rule_prefix, reason))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "info"]


class Linter:
    """Loads a projection once, then runs every band against it."""

    def __init__(
        self,
        proj_dir: Path,
        src: Optional[Path],
        policy: dict,
        content_sample: int = DEFAULT_CONTENT_SAMPLE,
    ) -> None:
        self.dir = proj_dir
        self.src = src
        self.policy = policy
        self.content_sample = content_sample
        self.report = Report()
        self._subject_string_cache: dict[str, bool] = {}

        self.manifest: dict = {}
        self.ai_json: Optional[dict] = None
        self.search_manifest: Optional[dict] = None
        self.shards: dict[str, dict] = {}          # component id -> shard doc
        self.shard_files: dict[str, Path] = {}     # filename -> path on disk
        self.search_entries: list[dict] = []

        # Derived once, used by every later band.
        self.components: dict[str, dict] = {}      # id -> component
        self.depth: dict[str, int] = {}
        self.parent: dict[str, Optional[str]] = {}
        self._line_counts: dict[str, Optional[int]] = {}

    # ---------------------------------------------------------------- parse

    def _read_json(self, rel: str, required: bool) -> Optional[Any]:
        path = self.dir / rel
        if not path.is_file():
            if required:
                self.report.error("parse.missing", f"required artifact is absent: {rel}")
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self.report.error("parse.unreadable", f"{rel} could not be read as UTF-8: {exc}")
            return None
        if not text.strip():
            self.report.error("parse.empty", f"{rel} is empty")
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            self.report.error("parse.invalid_json", f"{rel} is not valid JSON: {exc}")
            return None

    def load(self) -> bool:
        """Read the artifact set. Returns False when nothing further can run."""
        manifest = self._read_json("manifest.json", required=True)
        if not isinstance(manifest, dict):
            if manifest is not None:
                self.report.error("parse.invalid_json", "manifest.json is not a JSON object")
            return False
        self.manifest = manifest

        self.ai_json = self._read_json("ai.json", required=True)
        if not (self.dir / "llms.txt").is_file():
            self.report.error("parse.missing", "required artifact is absent: llms.txt")

        # Sidecars are conditionally present: the manifest section is the claim,
        # the file on disk is the payload, and either half alone is a defect.
        for key, rel in (("coverage", "coverage.json"), ("activity", "activity.json")):
            claimed = key in self.manifest
            exists = (self.dir / rel).is_file()
            if claimed and not exists:
                self.report.error(
                    "parse.missing",
                    f"manifest carries a '{key}' section but {rel} is absent",
                )
            if exists:
                self._read_json(rel, required=False)
        for rel in ("sbom.json", "cra-readiness.json"):
            if (self.dir / rel).is_file():
                self._read_json(rel, required=False)

        data_dir = self.dir / "data"
        if data_dir.is_dir():
            for path in sorted(data_dir.glob("detail-*.json")):
                self.shard_files[path.name] = path
                doc = self._read_json(f"data/{path.name}", required=False)
                if isinstance(doc, dict):
                    self.shards[path.name] = doc
                elif doc is not None:
                    self.report.error(
                        "parse.invalid_json", f"data/{path.name} is not a JSON object"
                    )

        search_dir = self.dir / "search"
        if search_dir.is_dir():
            sm = self._read_json("search/manifest.json", required=False)
            if isinstance(sm, dict):
                self.search_manifest = sm
                for name in sm.get("shards") or []:
                    doc = self._read_json(f"search/{name}", required=False)
                    if isinstance(doc, list):
                        self.search_entries.extend(
                            e for e in doc if isinstance(e, dict)
                        )
                    elif doc is not None:
                        self.report.error(
                            "parse.invalid_json",
                            f"search/{name} is not a JSON array of entries",
                        )
        return True

    # ---------------------------------------------------------------- shape

    def _iter_tree(self) -> Iterator[tuple[dict, Optional[str], int]]:
        stack: list[tuple[Any, Optional[str], int]] = [
            (c, None, 0) for c in reversed(self.manifest.get("components") or [])
        ]
        while stack:
            comp, parent_id, depth = stack.pop()
            if not isinstance(comp, dict):
                continue
            yield comp, parent_id, depth
            children = comp.get("children")
            if isinstance(children, list):
                stack.extend(
                    (c, comp.get("id"), depth + 1) for c in reversed(children)
                )

    def check_shape(self) -> None:
        required_top = (
            ("name", str),
            ("components", list),
            ("relationships", list),
            ("stats", dict),
        )
        for key, kind in required_top:
            value = self.manifest.get(key)
            if value is None:
                self.report.error("shape.manifest", f"manifest is missing '{key}'")
            elif not isinstance(value, kind):
                self.report.error(
                    "shape.manifest",
                    f"manifest '{key}' is {type(value).__name__}, expected {kind.__name__}",
                )

        comp_required = {
            "id": str, "name": str, "type": str, "path": str,
            "children": list, "files": list, "metrics": dict,
        }
        seen = 0
        for comp, parent_id, depth in self._iter_tree():
            seen += 1
            cid = comp.get("id")
            label = cid if isinstance(cid, str) else f"<component #{seen}>"
            for key, kind in comp_required.items():
                value = comp.get(key)
                if value is None:
                    self.report.error("shape.component", f"missing '{key}'", label)
                elif not isinstance(value, kind):
                    self.report.error(
                        "shape.component",
                        f"'{key}' is {type(value).__name__}, expected {kind.__name__}",
                        label,
                    )
            if isinstance(cid, str) and not cid.strip():
                self.report.error("shape.component", "id is blank", f"depth {depth}")
            if isinstance(cid, str):
                if cid in self.components:
                    self.report.error(
                        "ref.duplicate_component_id",
                        f"component id appears more than once in the tree: {cid}",
                    )
                else:
                    self.components[cid] = comp
                    self.depth[cid] = depth
                    self.parent[cid] = parent_id

        for i, rel in enumerate(self.manifest.get("relationships") or []):
            if not isinstance(rel, dict):
                self.report.error("shape.relationship", f"relationship #{i} is not an object")
                continue
            for key in ("source", "target", "type"):
                if not isinstance(rel.get(key), str) or not rel[key]:
                    self.report.error(
                        "shape.relationship",
                        f"'{key}' is missing or not a non-empty string",
                        f"relationship #{i}",
                    )

        for name, doc in self.shards.items():
            for key in ("files", "symbols"):
                if not isinstance(doc.get(key), list):
                    self.report.error(
                        "shape.shard", f"'{key}' is missing or not a list", f"data/{name}"
                    )
            for j, f in enumerate(doc.get("files") or []):
                if not isinstance(f, dict) or not isinstance(f.get("path"), str):
                    self.report.error(
                        "shape.shard", f"file #{j} has no string 'path'", f"data/{name}"
                    )
                    break
            for j, s in enumerate(doc.get("symbols") or []):
                if not isinstance(s, dict) or not isinstance(s.get("id"), str):
                    self.report.error(
                        "shape.shard", f"symbol #{j} has no string 'id'", f"data/{name}"
                    )
                    break

        if self.search_manifest is not None:
            for key, kind in (("shards", list), ("total", int), ("by_kind", dict)):
                if not isinstance(self.search_manifest.get(key), kind):
                    self.report.error(
                        "shape.search",
                        f"'{key}' is missing or not {kind.__name__}",
                        "search/manifest.json",
                    )

    # ------------------------------------------------------------------ ref

    def check_references(self) -> None:
        ids = set(self.components)
        if not ids:
            self.report.error("ref.no_components", "the projection contains no components")
            return

        # Relationship endpoints. A dangling endpoint is an edge the viewer
        # draws to nothing, or drops silently, depending on the lens.
        for i, rel in enumerate(self.manifest.get("relationships") or []):
            if not isinstance(rel, dict):
                continue
            for end in ("source", "target"):
                value = rel.get(end)
                if isinstance(value, str) and value not in ids:
                    self.report.error(
                        "ref.relationship_endpoint",
                        f"{end} '{value}' does not resolve to any component",
                        f"relationship #{i} ({rel.get('type')})",
                    )

        # The detail index against the tree AND against the disk, in both
        # directions. An index entry with no shard is a tab that spins forever;
        # a shard with no index entry is data the viewer never asks for.
        index = self.manifest.get("component_detail_index")
        if index is None:
            self.report.warn(
                "ref.detail_index",
                "manifest has no component_detail_index (single-file mode?); "
                "shard checks skipped",
            )
        elif not isinstance(index, dict):
            self.report.error("shape.manifest", "component_detail_index is not an object")
        else:
            expected_files: dict[str, str] = {}
            for cid, counts in index.items():
                if cid not in ids:
                    self.report.error(
                        "ref.detail_index",
                        f"detail index names '{cid}', which is not a component in the tree",
                    )
                name = f"detail-{safe_component_id(cid)}.json"
                expected_files[name] = cid
                if name not in self.shard_files:
                    self.report.error(
                        "ref.detail_shard_missing",
                        f"no shard on disk for '{cid}' (expected data/{name})",
                    )
                    continue
                doc = self.shards.get(name) or {}
                if not isinstance(counts, dict):
                    self.report.error(
                        "shape.manifest", "detail index entry is not an object", cid
                    )
                    continue
                for key, arr in (("fileCount", "files"), ("symbolCount", "symbols")):
                    claimed = counts.get(key)
                    actual = len(doc.get(arr) or [])
                    if claimed != actual:
                        self.report.error(
                            "count.detail_index",
                            f"index claims {key}={claimed} but the shard holds {actual}",
                            cid,
                        )
            for name in self.shard_files:
                if name not in expected_files:
                    self.report.error(
                        "ref.detail_shard_orphan",
                        f"data/{name} is on disk but no component_detail_index entry "
                        f"names it (stale shard from a previous dataset?)",
                    )
            for cid in ids:
                if cid not in index:
                    self.report.error(
                        "ref.detail_index",
                        f"component '{cid}' has no component_detail_index entry",
                    )

        # A component's own file list against the shard that is supposed to
        # carry those files. write_detail_shards drops a path it cannot resolve
        # in the global file table, so a divergence here is a silent loss.
        for cid, comp in self.components.items():
            name = f"detail-{safe_component_id(cid)}.json"
            doc = self.shards.get(name)
            if doc is None:
                continue
            declared = [p for p in (comp.get("files") or []) if isinstance(p, str)]
            in_shard = {
                f.get("path") for f in (doc.get("files") or []) if isinstance(f, dict)
            }
            dropped = [p for p in declared if p not in in_shard]
            if dropped:
                self.report.error(
                    "ref.component_files",
                    f"{len(dropped)} file(s) the component declares are absent from its "
                    f"shard, first: {dropped[0]}",
                    cid,
                )
            extra = [p for p in in_shard if p not in set(declared)]
            if extra:
                self.report.error(
                    "ref.component_files",
                    f"{len(extra)} file(s) in the shard are not declared by the "
                    f"component, first: {sorted(extra)[0]}",
                    cid,
                )

        # Lens arrays. Each of these drives a lens or a panel; an unresolvable
        # component_id is a row the user can click that goes nowhere.
        for key, fields in LENS_COMPONENT_FIELDS.items():
            arr = self.manifest.get(key)
            if not isinstance(arr, list):
                continue
            for i, row in enumerate(arr):
                if not isinstance(row, dict):
                    self.report.error("shape.lens", f"{key}[{i}] is not an object")
                    continue
                for fld in fields:
                    value = row.get(fld)
                    if isinstance(value, str) and value not in ids:
                        self.report.error(
                            "ref.lens_component",
                            f"{key}[{i}].{fld} '{value}' does not resolve to a component",
                        )

        # entity_access points at data_entities, which is a second id space.
        entities = self.manifest.get("data_entities")
        if isinstance(entities, list):
            entity_ids = {
                e.get("id") for e in entities if isinstance(e, dict) and e.get("id")
            }
            for i, row in enumerate(self.manifest.get("entity_access") or []):
                if isinstance(row, dict):
                    eid = row.get("entity_id")
                    if isinstance(eid, str) and entity_ids and eid not in entity_ids:
                        self.report.error(
                            "ref.entity_access",
                            f"entity_access[{i}].entity_id '{eid}' is not a data entity",
                        )

        # concerns carry members, findings carry component_ids in detail.
        for i, concern in enumerate(self.manifest.get("concerns") or []):
            if not isinstance(concern, dict):
                continue
            for j, member in enumerate(concern.get("members") or []):
                if isinstance(member, dict):
                    cid = member.get("component_id")
                    if isinstance(cid, str) and cid not in ids:
                        self.report.error(
                            "ref.lens_component",
                            f"concerns[{i}].members[{j}].component_id '{cid}' "
                            f"does not resolve to a component",
                        )
        for i, finding in enumerate(self.manifest.get("findings") or []):
            if not isinstance(finding, dict):
                continue
            detail = finding.get("detail")
            cids = detail.get("component_ids") if isinstance(detail, dict) else None
            for cid in cids or []:
                if isinstance(cid, str) and cid not in ids:
                    self.report.error(
                        "ref.finding_component",
                        f"findings[{i}].detail.component_ids names '{cid}', "
                        f"which does not resolve to a component",
                    )

        # The changelog is cumulative history. A removal legitimately names an
        # id that is gone, and its tombstone also makes earlier add/modify
        # records for that same id valid history rather than dangling current
        # navigation. A never-tombstoned missing target remains an error.
        changelog = self.manifest.get("changelog") or []
        tombstones = {
            change.get("target_id")
            for entry in changelog if isinstance(entry, dict)
            for change in (entry.get("changes") or []) if isinstance(change, dict)
            if "removed" in (change.get("kind") or "")
            or "deleted" in (change.get("kind") or "")
        }
        for i, entry in enumerate(changelog):
            if not isinstance(entry, dict):
                continue
            for j, change in enumerate(entry.get("changes") or []):
                if not isinstance(change, dict):
                    continue
                kind = change.get("kind") or ""
                tid = change.get("target_id")
                if "removed" in kind or "deleted" in kind:
                    continue
                if tid in tombstones:
                    continue
                if not isinstance(tid, str) or not tid:
                    continue
                # A relationship change names an EDGE, whose id is
                # "source->target". Both halves are component ids and both must
                # resolve; treating the whole string as one id was the linter's
                # own bug on first run.
                targets = tid.split("->") if "->" in tid else [tid]
                for part in targets:
                    if part and part not in ids:
                        self.report.error(
                            "ref.changelog_target",
                            f"changelog[{i}].changes[{j}] ({kind}) targets '{part}'"
                            + (f" (from edge '{tid}')" if len(targets) > 1 else "")
                            + ", which does not resolve to a component",
                        )

        self._check_search(ids)
        self._check_front_door()

    def _check_search(self, ids: set[str]) -> None:
        if self.search_manifest is None:
            self.report.skip("ref.search", "no search/manifest.json in the projection")
            return
        declared = list(self.search_manifest.get("shards") or [])
        on_disk = sorted(p.name for p in (self.dir / "search").glob("search-*.json"))
        for name in declared:
            if name not in on_disk:
                self.report.error(
                    "ref.search_shard", f"search manifest lists {name}, which is not on disk"
                )
        for name in on_disk:
            if name not in declared:
                self.report.error(
                    "ref.search_shard",
                    f"search/{name} is on disk but the search manifest does not list it",
                )

        total = self.search_manifest.get("total")
        if isinstance(total, int) and total != len(self.search_entries):
            self.report.error(
                "count.search_total",
                f"search manifest claims total={total} but the shards hold "
                f"{len(self.search_entries)} entries",
            )
        by_kind = Counter(
            e.get("ref_kind") for e in self.search_entries if isinstance(e, dict)
        )
        claimed_kinds = self.search_manifest.get("by_kind")
        if isinstance(claimed_kinds, dict):
            for kind, claimed in claimed_kinds.items():
                if by_kind.get(kind, 0) != claimed:
                    self.report.error(
                        "count.search_by_kind",
                        f"search manifest claims {claimed} '{kind}' entries but the "
                        f"shards hold {by_kind.get(kind, 0)}",
                    )

        # Every search hit is a navigation target. One that does not resolve is
        # a result the user clicks into an empty view, which is the exact defect
        # shape that survives every data-only check.
        all_files = set()
        all_symbol_ids = set()
        for doc in self.shards.values():
            all_files.update(
                f.get("path") for f in (doc.get("files") or []) if isinstance(f, dict)
            )
            all_symbol_ids.update(
                s.get("id") for s in (doc.get("symbols") or []) if isinstance(s, dict)
            )
        for i, entry in enumerate(self.search_entries):
            kind, ref = entry.get("ref_kind"), entry.get("ref_id")
            comp = entry.get("component")
            if isinstance(comp, str) and comp and comp not in ids:
                self.report.error(
                    "ref.search_entry",
                    f"search entry #{i} attributes to component '{comp}', "
                    f"which does not resolve",
                )
            if not isinstance(ref, str):
                continue
            if kind == "component" and ref not in ids:
                self.report.error(
                    "ref.search_entry", f"search entry #{i} (component) names '{ref}', unresolved"
                )
            elif kind == "file" and all_files and ref not in all_files:
                self.report.error(
                    "ref.search_entry", f"search entry #{i} (file) names '{ref}', not in any shard"
                )
            elif kind == "symbol" and all_symbol_ids and ref not in all_symbol_ids:
                self.report.error(
                    "ref.search_entry",
                    f"search entry #{i} (symbol) names '{ref}', not in any shard",
                )

    def _check_front_door(self) -> None:
        if not isinstance(self.ai_json, dict):
            self.report.skip("ref.front_door", "ai.json absent or unreadable")
            return
        for e in self.ai_json.get("endpoints") or []:
            path = e.get("path") if isinstance(e, dict) else None
            if not isinstance(path, str) or "<" in path:
                continue
            if not (self.dir / path).exists():
                self.report.error(
                    "ref.front_door_endpoint",
                    f"ai.json advertises '{path}', which does not exist in the bundle",
                )
        sections = self.ai_json.get("manifest_sections")
        if isinstance(sections, list):
            for s in sections:
                if not isinstance(s, dict):
                    continue
                key, present = s.get("key"), s.get("present")
                if key is None or present is None:
                    continue
                actual = bool(self.manifest.get(key))
                # component_detail_index and the sidecars are injected late, so
                # the front door's flag is a claim about the finished artifact
                # and has to match the finished artifact.
                if bool(present) != actual:
                    self.report.error(
                        "ref.front_door_section",
                        f"ai.json claims manifest section '{key}' present={present} "
                        f"but the manifest says {actual}",
                    )

    # ---------------------------------------------------------------- count

    def check_counts(self) -> None:
        stats = self.manifest.get("stats")
        if not isinstance(stats, dict):
            return
        actual_components = len(self.components)
        claimed = stats.get("total_components")
        if isinstance(claimed, int) and claimed != actual_components:
            self.report.error(
                "count.stats_components",
                f"stats.total_components={claimed} but the tree holds {actual_components}",
            )
        claimed = stats.get("total_relationships")
        actual_rels = len(self.manifest.get("relationships") or [])
        if isinstance(claimed, int) and claimed != actual_rels:
            self.report.error(
                "count.stats_relationships",
                f"stats.total_relationships={claimed} but the manifest holds {actual_rels}",
            )

        if self.shards:
            files = set()
            symbols = set()
            for doc in self.shards.values():
                files.update(
                    f.get("path") for f in (doc.get("files") or []) if isinstance(f, dict)
                )
                symbols.update(
                    s.get("id") for s in (doc.get("symbols") or []) if isinstance(s, dict)
                )
            claimed = stats.get("total_files")
            if isinstance(claimed, int) and claimed != len(files):
                self.report.error(
                    "count.stats_files",
                    f"stats.total_files={claimed} but the shards hold {len(files)} "
                    f"distinct file paths",
                )
            claimed = stats.get("total_symbols")
            if isinstance(claimed, int) and claimed != len(symbols):
                self.report.error(
                    "count.stats_symbols",
                    f"stats.total_symbols={claimed} but the shards hold {len(symbols)} "
                    f"distinct symbol ids",
                )

        for cid, comp in self.components.items():
            metrics = comp.get("metrics")
            if not isinstance(metrics, dict):
                continue
            declared_files = comp.get("files")
            if isinstance(declared_files, list) and isinstance(metrics.get("files"), int):
                if metrics["files"] != len(declared_files):
                    self.report.error(
                        "count.component_metrics",
                        f"metrics.files={metrics['files']} but the component lists "
                        f"{len(declared_files)} files",
                        cid,
                    )

        coverage = self.manifest.get("coverage")
        if isinstance(coverage, dict):
            summary = coverage.get("summary")
            total = coverage.get("total")
            if isinstance(summary, dict) and isinstance(total, int):
                summed = sum(v for v in summary.values() if isinstance(v, int))
                if summed != total:
                    self.report.error(
                        "count.coverage_ledger",
                        f"coverage.total={total} but the disposition summary sums to "
                        f"{summed} ({total - summed} file(s) unaccounted)",
                    )

    # --------------------------------------------------------------- source

    def _iter_citations(self) -> Iterator[tuple[str, Optional[int], Optional[int], str]]:
        """Yield every (file, line, end_line, where) the artifact cites.

        A generic walk rather than a per-record-kind list, because the point is
        that EVERY citation is checkable, including the ones a lens added last
        week that nobody remembered to wire into a validator.
        """
        def walk(node: Any, path: str) -> Iterator[tuple[str, Optional[int], Optional[int], str]]:
            if isinstance(node, dict):
                fname = node.get("file")
                if isinstance(fname, str) and fname:
                    line = node.get("line")
                    end = node.get("end_line")
                    yield (
                        fname,
                        line if isinstance(line, int) else None,
                        end if isinstance(end, int) else None,
                        path,
                    )
                for k, v in node.items():
                    if isinstance(v, (dict, list)):
                        yield from walk(v, f"{path}.{k}" if path else k)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    if isinstance(v, (dict, list)):
                        yield from walk(v, f"{path}[{i}]")

        for key in (
            "relationships", "findings", "rules", "capabilities",
            "concerns", "data_entities", "entity_access",
        ):
            yield from walk(self.manifest.get(key), f"manifest.{key}")
        for name, doc in self.shards.items():
            yield from walk(doc.get("symbols"), f"data/{name}.symbols")

    def _lines_in(self, rel: str) -> Optional[int]:
        if rel in self._line_counts:
            return self._line_counts[rel]
        assert self.src is not None
        path = self.src / rel
        count: Optional[int] = None
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    count = sum(1 for _ in fh)
            except OSError:
                count = None
        self._line_counts[rel] = count
        return count

    def check_source(self) -> None:
        if self.src is None or not self.src.is_dir():
            self.report.skip(
                "source.*",
                "no source tree available (pass --src, or run where manifest.root_path exists); "
                "every accusability check was skipped",
            )
            return

        missing_paths: list[str] = []
        for cid, comp in self.components.items():
            p = comp.get("path")
            if isinstance(p, str) and p and p not in (".", "/"):
                # Some extractors create logical components from a source
                # declaration rather than a directory. Docker Compose services
                # are the current example: ``compose/<service>`` is a stable
                # navigation id, while the checked-out source anchor is the
                # compose file recorded in config_files. Accept that virtual
                # path only when it owns no files and every declared Compose
                # anchor is a real source file. A moved ordinary component, or
                # a logical component with a stale anchor, still fails.
                compose_anchors = [
                    config.get("path")
                    for config in (comp.get("config_files") or [])
                    if isinstance(config, dict)
                    and config.get("type") == "docker-compose-service"
                    and isinstance(config.get("path"), str)
                    and config.get("path")
                ]
                anchored_virtual_component = (
                    not (comp.get("files") or [])
                    and bool(compose_anchors)
                    and all((self.src / anchor).is_file() for anchor in compose_anchors)
                )
                if not (self.src / p).exists() and not anchored_virtual_component:
                    missing_paths.append(f"{cid} -> {p}")
        for example in missing_paths[:EXAMPLE_CAP]:
            self.report.error(
                "source.component_path", f"component path does not exist in source: {example}"
            )
        if len(missing_paths) > EXAMPLE_CAP:
            self.report.error(
                "source.component_path",
                f"...and {len(missing_paths) - EXAMPLE_CAP} more component paths absent from source",
            )

        missing_files: set[str] = set()
        for doc in self.shards.values():
            for f in doc.get("files") or []:
                if isinstance(f, dict) and isinstance(f.get("path"), str):
                    if not (self.src / f["path"]).is_file():
                        missing_files.add(f["path"])
        for example in sorted(missing_files)[:EXAMPLE_CAP]:
            self.report.error("source.file_missing", f"shard cites a file that does not exist: {example}")
        if len(missing_files) > EXAMPLE_CAP:
            self.report.error(
                "source.file_missing",
                f"...and {len(missing_files) - EXAMPLE_CAP} more cited files absent from source",
            )

        bad_file: dict[str, str] = {}
        bad_line: list[str] = []
        citations = 0
        for rel, line, end, where in self._iter_citations():
            citations += 1
            count = self._lines_in(rel)
            if count is None:
                bad_file.setdefault(rel, where)
                continue
            if line is not None and not (1 <= line <= max(count, 1)):
                bad_line.append(f"{rel}:{line} (file has {count} lines) at {where}")
            if end is not None and line is not None and end < line:
                bad_line.append(f"{rel}:{line}-{end} ends before it starts, at {where}")
        for rel, where in list(bad_file.items())[:EXAMPLE_CAP]:
            self.report.error(
                "source.citation_file", f"citation points at a file not in source: {rel} (from {where})"
            )
        if len(bad_file) > EXAMPLE_CAP:
            self.report.error(
                "source.citation_file",
                f"...and {len(bad_file) - EXAMPLE_CAP} more cited files absent from source",
            )
        for example in bad_line[:EXAMPLE_CAP]:
            self.report.error("source.citation_line", f"citation line is outside the file: {example}")
        if len(bad_line) > EXAMPLE_CAP:
            self.report.error(
                "source.citation_line",
                f"...and {len(bad_line) - EXAMPLE_CAP} more citations point outside their file",
            )
        self.report.census["citations_checked"] = citations

        self._check_symbol_lines()

    def _check_symbol_lines(self) -> None:
        """Spot check that a symbol's declared line actually names that symbol.

        Deliberately a rate, not a per-symbol assertion. A parser may anchor a
        decorated definition at the decorator, and a language may declare a name
        on a continuation line, so a handful of misses is normal and a MAJORITY
        of misses means the shard is stale or the line base is off by one.
        """
        assert self.src is not None
        symbols: list[dict] = []
        for doc in self.shards.values():
            for s in doc.get("symbols") or []:
                if (
                    isinstance(s, dict)
                    and isinstance(s.get("file"), str)
                    and isinstance(s.get("line"), int)
                    and isinstance(s.get("name"), str)
                ):
                    symbols.append(s)
        if not symbols:
            self.report.skip("source.symbol_line", "no symbols with file+line in the shards")
            return
        symbols.sort(key=lambda s: s.get("id") or "")
        stride = max(1, len(symbols) // max(1, self.content_sample))
        sample = symbols[::stride][: self.content_sample]

        checked = 0
        misses: list[str] = []
        for s in sample:
            path = self.src / s["file"]
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            start = max(1, s["line"])
            end = s.get("end_line") if isinstance(s.get("end_line"), int) else start
            window = "".join(lines[start - 1 : min(max(end, start), start + 2)])
            checked += 1
            if s["name"] not in window:
                misses.append(f"{s['name']} claimed at {s['file']}:{s['line']}")

        if not checked:
            self.report.skip("source.symbol_line", "no sampled symbol's file could be read")
            return
        share = len(misses) / checked
        self.report.census["symbol_line_sample"] = {
            "checked": checked, "misses": len(misses), "share": round(share, 4),
        }
        threshold = self.policy.get("max_symbol_line_mismatch_share", 1.0)
        if share > threshold:
            for example in misses[:EXAMPLE_CAP]:
                self.report.warn("source.symbol_line", f"symbol not found on its declared line: {example}")
            self.report.error(
                "source.symbol_line",
                f"{len(misses)}/{checked} sampled symbols ({share:.1%}) are not on the line "
                f"the map claims, over the {threshold:.0%} tolerance",
            )

    # --------------------------------------------------------------- census

    def check_census(self) -> None:
        census = self.report.census
        total = len(self.components)
        census["components"] = total
        census["relationships"] = len(self.manifest.get("relationships") or [])
        census["detail_shards"] = len(self.shard_files)
        if not total:
            return

        depths = Counter(self.depth.values())
        max_depth = max(self.depth.values()) if self.depth else 0
        census["max_depth"] = max_depth
        census["depth_histogram"] = {str(k): v for k, v in sorted(depths.items())}

        over, min_depth = self.policy.get("min_depth_over_components", [10**9, 0])
        if total >= over and max_depth < min_depth:
            self.report.error(
                "census.depth",
                f"{total} components but the tree is only {max_depth} level(s) deep; "
                f"policy expects at least {min_depth} above {over} components",
            )

        empty_nodes = [
            cid for cid, c in self.components.items()
            if not (c.get("files") or []) and not (c.get("children") or [])
        ]
        share = len(empty_nodes) / total
        census["empty_nodes"] = {"count": len(empty_nodes), "share": round(share, 4)}
        if share > self.policy.get("max_empty_node_share", 1.0):
            self.report.error(
                "census.empty_nodes",
                f"{len(empty_nodes)}/{total} components ({share:.1%}) have neither files nor "
                f"children, so they render as dead ends; policy allows "
                f"{self.policy['max_empty_node_share']:.0%}",
            )
            for cid in empty_nodes[:EXAMPLE_CAP]:
                self.report.warn("census.empty_nodes", "empty node", cid)

        unknown = [
            cid for cid, c in self.components.items()
            if (c.get("language") or "unknown") in ("unknown", "", None)
        ]
        share = len(unknown) / total
        census["unknown_language"] = {"count": len(unknown), "share": round(share, 4)}
        if share > self.policy.get("max_unknown_language_share", 1.0):
            self.report.error(
                "census.unknown_language",
                f"{len(unknown)}/{total} components ({share:.1%}) have no language",
            )

        no_description = sum(
            1 for c in self.components.values() if not (c.get("description") or "").strip()
        )
        census["no_description"] = {
            "count": no_description, "share": round(no_description / total, 4),
        }

        lens_counts = {}
        for key in (
            "capabilities", "rules", "findings", "concerns", "data_entities",
            "entity_access", "changelog", "repositories", "ai_surface",
        ):
            value = self.manifest.get(key)
            if isinstance(value, list):
                lens_counts[key] = len(value)
        census["lens_population"] = lens_counts
        for key in self.policy.get("require_populated", []):
            if lens_counts.get(key, 0) == 0:
                self.report.error(
                    "census.lens_empty",
                    f"policy requires '{key}' to be populated, and it is empty",
                )

        # Enrichment uniformity. A projection is either enriched or it is not;
        # a half-enriched one makes every surface that reports a posture lie,
        # which is the S3 defect class the front-door gate was built for.
        enriched = [cid for cid, c in self.components.items() if c.get("ai_enhance")]
        share = len(enriched) / total
        census["enriched"] = {"count": len(enriched), "share": round(share, 4)}
        profile = self.policy.get("profile", "deterministic")
        if profile == "deterministic" and enriched:
            self.report.error(
                "census.enrichment_profile",
                f"policy profile is 'deterministic' but {len(enriched)}/{total} components "
                f"carry ai_enhance; this run is not a clean deterministic baseline",
            )
        elif profile == "enriched" and 0 < share < 1.0:
            self.report.error(
                "census.enrichment_profile",
                f"enrichment is partial ({len(enriched)}/{total} components); a partial "
                f"posture makes every surface that reports enrichment state wrong",
            )
        elif profile == "enriched" and share == 0:
            self.report.error(
                "census.enrichment_profile",
                "policy profile is 'enriched' but no component carries ai_enhance",
            )
        elif profile == "evaluation":
            publication_path = self.dir / "publication.json"
            try:
                publication = json.loads(publication_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                publication = None
            banner = (
                ((publication or {}).get("header") or {}).get("banner", "")
                if isinstance(publication, dict) else ""
            )
            footer = (
                ((publication or {}).get("footer") or {}).get("always", [])
                if isinstance(publication, dict) else []
            )
            visibility = (
                ((publication or {}).get("access") or {}).get("visibility")
                if isinstance(publication, dict) else None
            )
            disclosure = " ".join(
                [banner, *(x for x in footer if isinstance(x, str))]
            ).lower()
            exact_scope = f"{len(enriched)} of {total}"
            if not 0 < share < 1.0:
                self.report.error(
                    "census.enrichment_profile",
                    "policy profile is 'evaluation' but enrichment is not a partial overlay",
                )
            elif (
                not isinstance(publication, dict)
                or publication.get("purpose") != "evaluation"
                or visibility not in {"private-preview", "internal"}
                or "partial" not in disclosure
                or exact_scope not in disclosure
            ):
                self.report.error(
                    "census.enrichment_profile",
                    "partial evaluation requires a non-public evaluation publication.json "
                    f"that says it is partial and discloses the exact component scope "
                    f"({exact_scope})",
                )

        self._check_component_weight()

        coverage = self.manifest.get("coverage")
        if isinstance(coverage, dict):
            summary = coverage.get("summary") or {}
            total_files = coverage.get("total")
            parsed = summary.get("parsed", 0) if isinstance(summary, dict) else 0
            census["coverage"] = {"total": total_files, "parsed": parsed}
            unaccounted = coverage.get("unaccounted")
            if isinstance(unaccounted, int):
                census["coverage"]["unaccounted"] = unaccounted
                if unaccounted > self.policy.get("max_unaccounted_files", 0):
                    self.report.error(
                        "census.coverage",
                        f"{unaccounted} file(s) are unaccounted for in the coverage ledger",
                    )

    def _check_component_weight(self) -> None:
        """Is any single component too heavy for a browser to open?

        Reported as an error rather than a warning, because the failure mode is
        not degraded, it is total: the tab locks and the reader loses the page.
        A demo where the most obvious thing to click is the thing that kills the
        browser is worse than a demo missing that component entirely.
        """
        index = self.manifest.get("component_detail_index")
        if not isinstance(index, dict):
            return

        max_files = self.policy.get("max_component_files")
        max_symbols = self.policy.get("max_component_symbols")
        max_bytes = self.policy.get("max_shard_bytes")
        max_wire = self.policy.get("max_shard_transfer_bytes")

        heaviest: list[tuple[int, str, int, int, int]] = []
        offenders: list[str] = []
        bulky: list[str] = []
        noted: list[str] = []
        for cid, counts in index.items():
            if not isinstance(counts, dict):
                continue
            files = counts.get("fileCount") or 0
            symbols = counts.get("symbolCount") or 0
            shard = self.shard_files.get(f"detail-{safe_component_id(cid)}.json")
            size = 0
            if shard is not None:
                try:
                    size = shard.stat().st_size
                except OSError:
                    size = 0
            heaviest.append((symbols, cid, files, symbols, size))

            reasons = []
            shape: list[str] = []
            # Bulk is a SHAPE signal, not a usability verdict. These two limits
            # were written when src/vs/workbench looked unopenable, and that
            # diagnosis was wrong: the lock-up was the Rules lens handing an
            # unbounded graph to layout, and with graphs bounded the same
            # component opens in 1.9s with all 47,339 symbols usable. What the
            # counts still say truthfully is that the deriver put 24% of this
            # subject's files under one node, which is worth knowing about the map
            # and is not a reason to refuse it.
            if max_files and files > max_files:
                shape.append(f"{files} files (soft limit {max_files})")
            if max_symbols and symbols > max_symbols:
                shape.append(f"{symbols} symbols (soft limit {max_symbols})")
            if shape:
                bulky.append(f"{cid}: {', '.join(shape)}")
            if max_bytes and size > max_bytes:
                # Raw bytes are a prefilter, not the finding. What a reader pays
                # is the COMPRESSED transfer, and JSON compresses about tenfold:
                # private large-repository validation corpus's src/vs/workbench shard is 48 MB on disk and 4.4 MB on
                # the wire, which is an ordinary web payload rather than a defect.
                # Measuring the raw number and calling it the cost overstated the
                # problem by an order of magnitude, so the expensive measurement
                # is taken only for the shards that trip the cheap one.
                wire = self._transfer_bytes(shard)
                if wire is not None and max_wire and wire <= max_wire:
                    noted.append(
                        f"{cid}: a {size / 1e6:.1f} MB shard, but {wire / 1e6:.1f} MB "
                        f"compressed, which is what a reader downloads"
                    )
                else:
                    shown = f"{wire / 1e6:.1f} MB compressed" if wire is not None else f"{size / 1e6:.1f} MB raw"
                    reasons.append(
                        f"a {size / 1e6:.1f} MB shard ({shown}, limit "
                        f"{(max_wire or max_bytes) / 1e6:.0f} MB over the wire)"
                    )
            if reasons:
                offenders.append(f"{cid}: {', '.join(reasons)}")

        heaviest.sort(reverse=True)
        self.report.census["heaviest_components"] = [
            {"id": cid, "files": files, "symbols": symbols, "shard_bytes": size}
            for _, cid, files, symbols, size in heaviest[:5]
        ]

        for note in noted[:EXAMPLE_CAP]:
            self.report.info("census.component_weight_transfer", note)

        for heavy in bulky[:EXAMPLE_CAP]:
            self.report.warn(
                "census.component_shape",
                f"one component carries an outsized share of the subject: {heavy}",
            )

        for offender in offenders[:EXAMPLE_CAP]:
            # Deliberately not "too heavy to open in a browser" any more. That
            # sentence was written when src/vs/workbench appeared unopenable, and
            # it was wrong: the lock-up was the Rules lens handing an unbounded
            # graph to layout, and with graphs bounded the same component opens in
            # 1.9s with all 47,339 symbols usable. A rule that keeps asserting a
            # disproven cause teaches the reader to discount the rule.
            self.report.error(
                "census.component_weight",
                f"component exceeds the weight budget: {offender}",
            )
        if len(offenders) > EXAMPLE_CAP:
            self.report.error(
                "census.component_weight",
                f"...and {len(offenders) - EXAMPLE_CAP} more components over the weight limits",
            )

    def check_parser_plausibility(self) -> None:
        """Did the projection meet the parser it was supposed to meet?

        This band exists because of a real incident and would have caught it in
        one line. A private large-repository validation corpus run was launched with an interpreter that had no
        tree-sitter installed, so every TypeScript file silently fell back to the
        regex parser. The result: 355,617 symbols instead of 153,231, all 28,501
        methods reclassified as plain functions, the detail directory doubled to
        310 MB, and the heaviest shard grown from 48 MB to 97 MB.

        The analyzer reported "Coverage: 100% of source analyzed, 0 gaps"
        throughout, and it was telling the truth as it understood it: every file
        WAS parsed. Nothing measured whether it was parsed WELL. That is the same
        shape as the two deepest defects this project has found, every surface
        passing its own check while the artifact as a whole is wrong.

        The signature is unmistakable and needs no parser identity recorded in the
        artifact, which is what makes it usable on projections that already exist:
        an object-oriented codebase that reports not one single method did not
        read its own classes.
        """
        stats = self.manifest.get("stats") or {}
        languages = stats.get("languages")
        if not isinstance(languages, dict):
            return

        oo_lines = sum(
            lines for lang, lines in languages.items()
            if lang in METHOD_BEARING_LANGUAGES and isinstance(lines, (int, float))
        )
        total_lines = sum(v for v in languages.values() if isinstance(v, (int, float)))
        if oo_lines < 20_000 or not total_lines:
            return  # too little of the subject is method-bearing to conclude anything

        kinds = Counter()
        for shard in self.shards.values():
            for sym in (shard.get("symbols") or []):
                kinds[sym.get("kind")] += 1
        callables = kinds["method"] + kinds["function"]
        classes = kinds["class"] + kinds["interface"] + kinds["struct"]
        if callables < 500 or classes < 200:
            return  # too little read to conclude anything

        # Methods PER CLASS, not methods outright. The first version of this band
        # tested for zero methods and missed the very incident it was written for:
        # the degraded private large-repository validation corpus run still produced 55 of them, from the handful of
        # files whose parser needs no tree-sitter. 55 methods against 14,744
        # classes is the real tell. A class with no members is a data holder, and
        # thousands in a row means nothing read the insides of a class.
        #
        # Calibrated against both projections of the same commit:
        #   tree-sitter    28,501 methods / 4,292 classes   = 6.6 per class
        #   regex fallback     55 methods / 14,744 classes  = 0.004 per class
        # The gap is three orders of magnitude, so the threshold does not need to
        # be delicate and a genuinely method-light codebase stays well clear.
        per_class = kinds["method"] / classes
        if per_class < 0.25:
            share = oo_lines / total_lines
            self.report.error(
                "census.parser_degraded",
                f"{kinds['method']} method symbols against {classes} classes "
                f"({per_class:.3f} per class) across {callables} callables, while "
                f"{share:.0%} of the subject ({oo_lines:,} lines) is in languages whose "
                f"parser emits methods. Classes whose bodies were never read look "
                f"exactly like this: check that tree-sitter is importable from the "
                f"interpreter that ran the analysis",
            )

    def _transfer_bytes(self, shard: Optional[Path]) -> Optional[int]:
        """What this shard actually costs to download, compressed.

        Every static host worth deploying to serves JSON compressed, so the size
        on disk is not the size a reader waits for. Measured rather than
        estimated, because compression ratio depends on the content: a shard full
        of repeated symbol scaffolding compresses far better than one full of
        prose, and guessing a ratio would put the whole judgement on a constant
        nobody checked.

        Returns None when it cannot be measured, and the caller then falls back
        to the raw size rather than assuming the generous answer.
        """
        if shard is None or not shard.is_file():
            return None
        try:
            total = 0
            compressor = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
            with shard.open("rb") as fh:
                while chunk := fh.read(1 << 20):
                    total += len(compressor.compress(chunk))
            total += len(compressor.flush())
            return total
        except (OSError, zlib.error):
            return None

    # -------------------------------------------------------------- hygiene

    def _written_by_the_subject(self, needle: str) -> bool:
        """True when this exact string also occurs in the subject's own source.

        The whole question in the absolute-path band is WHOSE path it is. A path
        under the generating machine's root is ours and is a real leak. A path
        that private large-repository validation corpus committed into its own test/unit/README.md is the subject's
        content, already public wherever the subject is public, and republishing
        it verbatim is what a faithful map does. Rewriting it would make our copy
        of a file disagree with the file.

        Provenance is settled by asking the source rather than by keeping a list
        of fields that are "allowed" to contain paths. A field allowlist rots the
        moment the deriver embeds subject text somewhere new; this cannot, because
        it tests the actual claim: does the subject say this too?

        `git grep` over a checkout is fast enough to run once per distinct
        finding. Without a source tree the answer is unknown, and unknown is
        reported as a leak, because assuming our own innocence is the wrong
        default.
        """
        if self.src is None or not self.src.is_dir():
            return False
        cached = self._subject_string_cache.get(needle)
        if cached is not None:
            return cached

        # A query string or trailing punctuation belongs to the surrounding
        # document, not to the path, and would defeat a fixed-string search.
        candidates = [needle]
        # The band scans the artifact as TEXT, so a Windows path arrives with its
        # JSON escaping intact: the file holds C:\\Users\\..., the string means
        # C:\Users\.... Searching the escaped form finds nothing and the
        # subject's own README gets reported as our leak, which is precisely the
        # misattribution this check exists to prevent.
        if "\\\\" in needle:
            candidates.append(needle.replace("\\\\", "\\"))
        for base in list(candidates):
            for cut in ("?", "#", "`"):
                if cut in base:
                    candidates.append(base.split(cut, 1)[0])
        candidates.extend(c[:40] for c in list(candidates))

        found = False
        for candidate in candidates:
            if len(candidate) < 12:
                continue
            try:
                proc = subprocess.run(
                    ["git", "-C", str(self.src), "grep", "-qFI", "--", candidate],
                    capture_output=True,
                    timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                break
            if proc.returncode == 0:
                found = True
                break
        self._subject_string_cache[needle] = found
        return found

    def check_hygiene(self) -> None:
        """Absolute paths leaking into a bundle that may be published."""
        root_path = self.manifest.get("root_path")
        leaks: list[str] = []
        for rel in ("manifest.json", "ai.json", "llms.txt"):
            path = self.dir / rel
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in ABSOLUTE_PATH_RE.finditer(text):
                found = match.group(0).rstrip(",")
                # root_path is the one field that is contractually a real
                # machine path, so it is reported once, as its own advisory.
                if isinstance(root_path, str) and found.startswith(root_path):
                    continue
                leaks.append(f"{rel}: {found}")
                if len(leaks) > EXAMPLE_CAP:
                    break
            # The generating machine's own root, repeated anywhere beyond the
            # one field that is allowed to carry it. Caught by literal match
            # rather than by the home-directory pattern, because a build root
            # under /opt or /srv leaks exactly as much and matches nothing.
            if isinstance(root_path, str) and root_path.startswith("/"):
                extra = text.count(root_path) - (1 if rel == "manifest.json" else 0)
                if extra > 0:
                    leaks.append(f"{rel}: the generating root path appears {extra} more time(s)")
        for leak in leaks[:EXAMPLE_CAP]:
            rel, _, found = leak.partition(": ")
            if self._written_by_the_subject(found):
                self.report.info(
                    "hygiene.subject_absolute_path",
                    f"the subject's own source carries this path, and the map "
                    f"republishes it verbatim: {leak}",
                )
            else:
                self.report.warn(
                    "hygiene.absolute_path",
                    f"absolute filesystem path in the artifact: {leak}",
                )
        if isinstance(root_path, str) and (
            root_path.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", root_path)
        ):
            self.report.warn(
                "hygiene.root_path",
                f"manifest.root_path carries the generating machine's path ({root_path}); "
                f"acceptable locally, an information leak in a published bundle",
            )

    # ------------------------------------------------------------------ run

    def run(self) -> Report:
        if not self.load():
            return self.report
        self.check_shape()
        self.check_references()
        self.check_counts()
        self.check_census()
        self.check_parser_plausibility()
        self.check_source()
        self.check_hygiene()
        return self.report


# Digits, quoted strings and paths are what vary BETWEEN instances of the same
# defect. Blanking them is how "component 'a/b' does not resolve" and
# "component 'x/y' does not resolve" collapse into one problem seen twice,
# while a genuinely different message stays its own problem.
_VARIABLE_PART_RE = re.compile(r"'[^']*'|\"[^\"]*\"|\b\d[\d,._]*\b|/[\w./+-]+")


def _fingerprint(rule: str, message: str) -> str:
    """A stable id for a KIND of problem, not for one sighting of it."""
    shape = _VARIABLE_PART_RE.sub("*", message).strip()
    digest = hashlib.sha1(f"{rule}|{shape}".encode()).hexdigest()[:12]
    return f"{rule}:{digest}"


def group_findings(rule: str, hits: list[Finding]) -> list[dict]:
    """Collapse instances of one problem into one finding that counts them.

    Returns one entry per DISTINCT problem, each carrying how many times it was
    seen and a few concrete examples. The examples matter as much as the count:
    a number tells you the scale, an example tells you what to go and look at.
    """
    buckets: dict[str, dict] = {}
    for hit in hits:
        fid = _fingerprint(rule, hit.message)
        bucket = buckets.get(fid)
        if bucket is None:
            buckets[fid] = {
                "id": fid,
                "rule": rule,
                "severity": hit.severity,
                # The first sighting supplies the human-readable title; later
                # ones only add to the count and the examples.
                "title": hit.message,
                "instances": 1,
                "examples": [hit.render()],
                # Whether this is a defect or a known gap is a judgement nobody
                # has made yet, and guessing would be worse than saying so.
                "nature": "unclassified",
            }
        else:
            bucket["instances"] += 1
            if len(bucket["examples"]) < 5:
                bucket["examples"].append(hit.render())
            if hit.severity == "error":
                bucket["severity"] = "error"
    return sorted(buckets.values(), key=lambda b: (-b["instances"], b["id"]))


def _case_message(rule: str, hits: list[Finding], groups: list[dict]) -> str:
    """Say the count AND the shape, because they are different facts."""
    instances = len(hits)
    distinct = len(groups)
    if distinct == 1:
        shape = f"{instances} instance(s) of 1 problem"
    else:
        shape = f"{instances} instance(s) across {distinct} distinct problems"
    return f"{shape}; largest: {groups[0]['title']}"


def publish_run(
    report: Report,
    proj_dir: Path,
    src: Optional[Path],
    runs_root: Path,
    started: str,
) -> Path:
    """Write this lint as a testboard run record.

    The same two files the crawl's reporter writes (scripts/testboard.py reads
    both), so a lint and a crawl appear side by side on one board and neither
    harness has to know the other exists. Written once at the end rather than
    streamed, because a lint is seconds of work: there is no meaningful "in
    progress" to watch, only a verdict to publish.
    """
    manifest = {}
    try:
        manifest = json.loads((proj_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    subject = manifest.get("name") or proj_dir.name

    ended = datetime.now(timezone.utc).isoformat()
    run_id = f"{started.replace(':', '-').replace('.', '-')}-lint-{subject}"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # One case per rule that fired, plus one for every band that stayed clean,
    # so a passing lint is not an empty page. A board that shows nothing when
    # everything is fine teaches people it is broken.
    #
    # Each case carries its FINDINGS, not just a verdict. This distinction is
    # the whole point of the accounting: a lint that checks 188,841 citations
    # and reports "1 failed" has told you almost nothing. What matters is how
    # many things were wrong, and whether those were one problem seen many
    # times or many separate problems. Fifty instances of one broken id scheme
    # and fifty unrelated defects both read as "50" until they are grouped, and
    # they call for completely different responses.
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in report.findings:
        by_rule[f.rule].append(f)
    cases = []
    all_findings = []
    for rule in sorted(by_rule):
        hits = by_rule[rule]
        # A rule that only ever produced noted items is a passing case. It ran,
        # it found something true, and there is nothing to do about it; calling
        # that "warned" would keep a permanently-clean run looking dirty.
        if any(f.severity == "error" for f in hits):
            worst = "failed"
        elif all(f.severity == "info" for f in hits):
            worst = "passed"
        else:
            worst = "warned"
        groups = group_findings(rule, hits)
        cases.append({
            "title": rule,
            "status": worst,
            "duration_ms": None,
            "coverage": [],
            "message": _case_message(rule, hits, groups),
            "instances": len(hits),
            "distinct": len(groups),
            "findings": groups,
        })
        all_findings.extend(groups)
    for prefix, reason in report.skipped:
        cases.append({
            "title": prefix, "status": "skipped", "duration_ms": None,
            "coverage": [], "message": reason,
        })
    if not cases:
        cases.append({
            "title": "all bands clean", "status": "passed", "duration_ms": None,
            "coverage": [], "message": None,
        })

    try:
        duration_ms = round(
            (datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() * 1000
        )
    except (TypeError, ValueError):
        duration_ms = None

    provenance = (manifest.get("activity") or {}).get("provenance") or {}
    record = {
        "testboard_version": 1,
        "id": run_id,
        "kind": "lint",
        "subject": subject,
        "status": "failed" if report.errors else "passed",
        "started_at": started,
        "ended_at": ended,
        "duration_ms": duration_ms,
        "data_dir": str(proj_dir),
        "base_url": None,
        "budget": "full artifact",
        "versions": {
            "viewer_version": None,
            "analyzer_version": None,
            "dataset": {
                "name": subject,
                "generated_at": manifest.get("generated_at"),
                "analyzer_version": manifest.get("analyzer_version"),
                "subject_sha": provenance.get("head"),
                "components": len(manifest.get("component_detail_index") or {}) or None,
            },
        },
        "total": len(cases),
        "completed": len(cases),
        "passed": sum(1 for c in cases if c["status"] == "passed"),
        "warned": sum(1 for c in cases if c["status"] == "warned"),
        "failed": sum(1 for c in cases if c["status"] == "failed"),
        "skipped": len(report.skipped),
        "error_count": len(report.errors),
        "warning_count": len(report.warnings),
        "current": None,
        "cases": cases,
        # The census IS the coverage claim for a lint: how much was looked at.
        "coverage": [f"{k}: {json.dumps(v)}" for k, v in report.census.items()],
        "source_checked": str(src) if src else None,
        # The accounting a reader actually needs from a run that checked
        # hundreds of thousands of things. "1 failed" describes the case list;
        # these describe the subject.
        "findings": all_findings,
        "finding_totals": {
            "instances": sum(f["instances"] for f in all_findings),
            "distinct": len(all_findings),
            "errors": sum(1 for f in all_findings if f["severity"] == "error"),
            "error_instances": sum(
                f["instances"] for f in all_findings if f["severity"] == "error"
            ),
            "warnings": sum(1 for f in all_findings if f["severity"] == "warn"),
            "warning_instances": sum(
                f["instances"] for f in all_findings if f["severity"] == "warn"
            ),
        },
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    with open(run_dir / "events.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": started, "type": "run_start", "subject": subject,
                             "total": len(cases)}) + "\n")
        for case in cases:
            fh.write(json.dumps({"ts": ended, "type": "case_end", **case}) + "\n")
        fh.write(json.dumps({"ts": ended, "type": "run_end", "status": record["status"],
                             "passed": record["passed"], "failed": record["failed"]}) + "\n")
    return run_dir


def render_text(report: Report, proj_dir: Path) -> str:
    lines = [f"projection lint: {proj_dir}", ""]

    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in report.findings:
        by_rule[f.rule].append(f)

    for severity, label in (("error", "ERRORS"), ("warn", "WARNINGS"), ("info", "NOTED")):
        rules = sorted(r for r, fs in by_rule.items() if any(f.severity == severity for f in fs))
        if not rules:
            continue
        lines.append(f"{label}")
        for rule in rules:
            hits = [f for f in by_rule[rule] if f.severity == severity]
            lines.append(f"  {rule} ({len(hits)})")
            for f in hits[:EXAMPLE_CAP]:
                lines.append(f"    - {f.render()}")
            if len(hits) > EXAMPLE_CAP:
                lines.append(f"    ...and {len(hits) - EXAMPLE_CAP} more")
        lines.append("")

    if report.skipped:
        lines.append("SKIPPED (not run, not passed)")
        for prefix, reason in report.skipped:
            lines.append(f"  {prefix}: {reason}")
        lines.append("")

    lines.append("CENSUS")
    for key, value in report.census.items():
        lines.append(f"  {key}: {json.dumps(value)}")
    lines.append("")

    verdict = "FAIL" if report.errors else ("PASS with warnings" if report.warnings else "PASS")
    # Noted items are counted but never change the verdict: they are things that
    # are true, stated, and correctly not acted on.
    noted = f", {len(report.infos)} noted" if report.infos else ""
    lines.append(
        f"OVERALL: {verdict} ({len(report.errors)} error(s), "
        f"{len(report.warnings)} warning(s){noted})"
    )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a projected architecture dataset for integrity, "
                    "accusability and apparent completeness."
    )
    parser.add_argument("projection", help="directory holding manifest.json (split mode)")
    parser.add_argument(
        "--src", default=None,
        help="source tree the projection describes; enables the source.* band. "
             "Defaults to manifest.root_path when that directory exists.",
    )
    parser.add_argument(
        "--policy", default=None,
        help="JSON file of policy overrides merged over the defaults",
    )
    parser.add_argument(
        "--profile", choices=("deterministic", "enriched", "evaluation"), default=None,
        help="shorthand for the policy's enrichment expectation",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="write the machine report here")
    parser.add_argument(
        "--content-sample", type=int, default=DEFAULT_CONTENT_SAMPLE,
        help=f"symbols to open and check against their declared line (default {DEFAULT_CONTENT_SAMPLE})",
    )
    parser.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    parser.add_argument("--quiet", action="store_true", help="suppress the text report")
    parser.add_argument(
        "--testboard", nargs="?", const="", default=None, metavar="DIR",
        help="publish this lint as a testboard run record so it shows on the "
             "dashboard (scripts/testboard.py). Defaults to <repo>/.testboard/runs, "
             "or the TESTBOARD_DIR environment variable, or DIR if given.",
    )
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc).isoformat()

    proj_dir = Path(args.projection).expanduser().resolve()
    if not proj_dir.is_dir():
        print(f"error: not a directory: {proj_dir}", file=sys.stderr)
        return 3

    policy = dict(DEFAULT_POLICY)
    if args.policy:
        try:
            policy.update(json.loads(Path(args.policy).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read policy {args.policy}: {exc}", file=sys.stderr)
            return 3
    if args.profile:
        policy["profile"] = args.profile

    src: Optional[Path] = None
    if args.src:
        src = Path(args.src).expanduser().resolve()
    else:
        try:
            manifest = json.loads((proj_dir / "manifest.json").read_text(encoding="utf-8"))
            candidate = manifest.get("root_path")
            if isinstance(candidate, str) and Path(candidate).is_dir():
                src = Path(candidate)
        except (OSError, json.JSONDecodeError):
            src = None

    linter = Linter(proj_dir, src, policy, content_sample=args.content_sample)
    report = linter.run()

    if not args.quiet:
        print(render_text(report, proj_dir))

    if args.json_out:
        doc = {
            "lint_version": 1,
            "projection": str(proj_dir),
            "source": str(src) if src else None,
            "policy": policy,
            "findings": [
                {"rule": f.rule, "severity": f.severity, "message": f.message, "where": f.where}
                for f in report.findings
            ],
            "skipped": [{"rule": r, "reason": why} for r, why in report.skipped],
            "census": report.census,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "noted": len(report.infos),
        }
        out = Path(args.json_out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.testboard is not None:
        runs_root = (
            Path(args.testboard).expanduser()
            if args.testboard
            else Path(os.environ.get("TESTBOARD_DIR")
                      or (Path(__file__).resolve().parent.parent / ".testboard" / "runs"))
        )
        try:
            run_dir = publish_run(report, proj_dir, src, runs_root, started)
            if not args.quiet:
                print(f"\ntestboard: published {run_dir.name}")
        except OSError as exc:
            # Observability must never turn a passing lint into a failing one.
            print(f"warning: could not publish to the testboard: {exc}", file=sys.stderr)

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
