"""The no-AI evidence validator: does this citation point at something real?

The completeness contract's grounding rule (``ENRICHMENT-ENGINE.md`` section 4.2)
is "a claim without evidence you can point at is not an answer". This module is
what makes that rule enforceable by code rather than by good intentions: every
citation a tier writes is checked mechanically against the store and the repo
root, so an unsupported claim is structurally detectable.

What it can and cannot do, stated plainly because the difference matters:

* It CAN prove a citation is fake. The file is not in the index, the line is past
  the end of the file, the named symbol does not appear there, the edge is not in
  the graph. These are the failures that turn a confident sentence into an E2.
* It CANNOT judge whether real evidence actually SUPPORTS the claim it is
  attached to. That is sufficiency, it stays judgment, and the design says so
  (section 4.5). Adjudication spot-checks it and the disagreement rate is a run
  metric.

Converting the first half into a check is most of the value. The calibration
measured 83 of 99 components scoring exactly 85.0 on a form scorer while nothing
checked truth; a citation that points nowhere is exactly the failure a form
scorer waves through.

**The store is the authority, not the filesystem.** A path is valid when the
analyzer indexed it. Checking the working tree instead would accept a citation to
a file the analysis never saw (a gitignored artifact, a build output, something
created after the scan), which is precisely the class of confident-but-groundless
claim this exists to catch. The filesystem is consulted only for evidence kinds
the store does not model, and only under the repo root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "EVIDENCE_KINDS",
    "CITABLE_FACTS",
    "EvidenceCheck",
    "EvidenceValidator",
    "normalize_path",
]

# The evidence kinds a tier may cite (build plan, canonical data shapes).
# "fact" cites the analyzer's OWN fact block for a component: the counts and
# attributes the deterministic pass produced and the prompt hands over. Without
# it a claim taken straight from those facts is unciteable, because a file or an
# edge cannot carry a statement about seventeen of them. On the 2026-08-25
# unamentis-ios cycle that gap produced a 64.1% grounding disagreement rate
# whose largest cause was TRUE claims with no legal way to cite their source,
# and it drove ungrounded (E2) escalations to a more expensive tier that could
# not fix them either.
EVIDENCE_KINDS = ("file", "symbol", "edge", "manifest", "doc", "fact")

# The analyzer-derived fields a claim may cite. An allow-list, so "fact"
# evidence cannot become a free-text escape hatch that grounds anything.
CITABLE_FACTS = (
    # Every name here MUST be a key StoreFacts.component_facts() actually
    # emits; the vocabulary conformance test pins that. The original list
    # said "line_count" while the fact block emits "lines", so a model
    # following the prompt failed validation mechanically: the v2 build
    # measured 8 terminal failures in exactly this class, and the
    # cross-session review caught the mismatch surviving into this branch.
    "file_count", "lines", "inbound_edges", "outbound_edges",
    "language", "framework", "port", "type", "capabilities",
    "data_entities", "external_services", "action_count", "ai_surface",
    "has_testing_data", "testing", "path", "existing_description",
    "capability_count", "data_entity_count",
    "same_language_component_count", "same_type_component_count",
    "system_relationship_count", "system_capability_count",
    "system_capability_component_count", "system_max_inbound_edges",
    "system_max_outbound_edges", "files", "edges", "config_files",
    "documentation",
)


@dataclass
class EvidenceCheck:
    """The verdict on one citation."""

    ok: bool
    kind: str
    reason: Optional[str] = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "kind": self.kind, "reason": self.reason}


def normalize_path(raw: Any, root: Optional[Path] = None) -> str:
    """Normalize a cited path to the repo-relative form the store indexes by.

    Tiers cite paths inconsistently: with a leading ``./``, with a leading slash,
    with backslashes on a Windows-authored doc, or as an absolute path inside the
    root. All of those name the same file, and rejecting them would report a
    citation as fake when it is merely differently spelled, which teaches the
    ladder the wrong lesson and inflates the ungrounded rate.
    """
    if not isinstance(raw, str):
        return ""
    text = raw.strip().replace("\\", "/")
    if not text:
        return ""
    if root is not None:
        try:
            candidate = Path(text)
            if candidate.is_absolute():
                text = str(candidate.relative_to(root))
        except (ValueError, OSError):
            pass
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


class EvidenceValidator:
    """Check citations against one store and repo root. Pure code, no AI.

    Built once per run and reused: the indexes are read from the store up front,
    so validating thousands of citations costs one pass over the store rather
    than one query per citation.
    """

    def __init__(self, store, root: Optional[Path] = None) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self._lines_by_path: dict[str, Optional[int]] = {}
        self._symbols_by_path: dict[str, set[str]] = {}
        # Where a symbol is USED, as opposed to where it is defined. The parser
        # already records this as a `symbol_reference` signal per file, so the
        # index costs one more pass over the store and no filesystem reads.
        self._references_by_path: dict[str, set[str]] = {}
        self._symbol_names: set[str] = set()
        # Component fact blocks, injected by the caller that builds them. Empty
        # when absent, which makes every "fact" citation fail closed rather
        # than pass unchecked.
        self._facts_by_id: dict[str, dict] = {}
        self._edges: set[tuple[str, str, str]] = set()
        self._edge_pairs: set[tuple[str, str]] = set()
        if store is not None:
            self._load(store)

    def _load(self, store) -> None:
        file_paths: dict[int, str] = {}
        for row in store.files():
            path = normalize_path(row.get("path"), self.root)
            if not path:
                continue
            file_paths[row.get("id")] = path
            raw_lines = row.get("lines")
            try:
                self._lines_by_path[path] = int(raw_lines) if raw_lines is not None else None
            except (TypeError, ValueError):
                self._lines_by_path[path] = None
        for row in store.symbols():
            name = (row.get("name") or "").strip()
            if not name:
                continue
            self._symbol_names.add(name)
            path = file_paths.get(row.get("file_id"))
            if path:
                self._symbols_by_path.setdefault(path, set()).add(name)
        for row in store.signals():
            if (row.get("kind") or "") != "symbol_reference":
                continue
            path = file_paths.get(row.get("file_id"))
            if not path:
                continue
            value = row.get("value")
            name = ""
            if isinstance(value, dict):
                name = str(value.get("name") or "").strip()
            elif value is not None:
                name = str(value).strip()
            if name:
                self._references_by_path.setdefault(path, set()).add(name)
        for row in store.edges():
            source = row.get("source_id") or ""
            target = row.get("target_id") or ""
            kind = row.get("type") or ""
            self._edges.add((source, target, kind))
            self._edge_pairs.add((source, target))

    def attach_facts(self, facts_by_id: dict) -> None:
        """Give the validator the fact blocks the prompts were built from."""
        self._facts_by_id = dict(facts_by_id or {})

    # --- individual checks ----------------------------------------------------

    def knows_file(self, path: str) -> bool:
        return normalize_path(path, self.root) in self._lines_by_path

    def check(self, item: Any) -> EvidenceCheck:
        """Validate one evidence item. Never raises: a malformed item is a failure."""
        if not isinstance(item, dict):
            return EvidenceCheck(False, "unknown", "evidence item is not an object")
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in EVIDENCE_KINDS:
            return EvidenceCheck(
                False,
                kind or "unknown",
                f"unknown evidence kind {kind!r}; expected one of "
                + ", ".join(EVIDENCE_KINDS),
            )
        if kind == "edge":
            return self._check_edge(item)
        if kind == "fact":
            return self._check_fact(item)
        return self._check_path_evidence(kind, item)

    def _check_edge(self, item: dict) -> EvidenceCheck:
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        edge_type = str(item.get("edge_type") or item.get("type") or "").strip()
        if not source or not target:
            return EvidenceCheck(
                False, "edge", "edge evidence needs both a source and a target"
            )
        if edge_type:
            if (source, target, edge_type) in self._edges:
                return EvidenceCheck(True, "edge")
            if (source, target) in self._edge_pairs:
                return EvidenceCheck(
                    False,
                    "edge",
                    f"no {edge_type!r} edge from {source!r} to {target!r}, "
                    "though the two are connected by another edge type",
                )
            return EvidenceCheck(
                False, "edge", f"no edge from {source!r} to {target!r} in the graph"
            )
        if (source, target) in self._edge_pairs:
            return EvidenceCheck(True, "edge")
        return EvidenceCheck(
            False, "edge", f"no edge from {source!r} to {target!r} in the graph"
        )

    def _check_path_evidence(self, kind: str, item: dict) -> EvidenceCheck:
        raw_path = item.get("path")
        path = normalize_path(raw_path, self.root)
        if not path:
            return EvidenceCheck(False, kind, f"{kind} evidence has no path")

        known = path in self._lines_by_path
        if not known:
            # A doc or manifest may sit outside the indexed code (a README the
            # scanner classified as content, for instance), so fall back to the
            # working tree for those two kinds only, and only under the root.
            if kind in ("doc", "manifest") and self._exists_under_root(path):
                return self._check_line(kind, path, item, total_lines=None)
            return EvidenceCheck(
                False, kind, f"{path} is not in the analyzed file set"
            )

        total_lines = self._lines_by_path.get(path)
        line_check = self._check_line(kind, path, item, total_lines=total_lines)
        if not line_check.ok:
            return line_check
        if kind == "symbol":
            return self._check_symbol(path, item)
        return line_check

    def _exists_under_root(self, path: str) -> bool:
        if self.root is None:
            return False
        try:
            candidate = (self.root / path).resolve()
            candidate.relative_to(self.root)
        except (ValueError, OSError):
            return False
        return candidate.exists()

    def _check_line(
        self, kind: str, path: str, item: dict, *, total_lines: Optional[int]
    ) -> EvidenceCheck:
        raw_line = item.get("line")
        if raw_line is None:
            return EvidenceCheck(True, kind, detail={"path": path})
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            return EvidenceCheck(False, kind, f"line {raw_line!r} is not a number")
        if line < 1:
            return EvidenceCheck(False, kind, f"line {line} is not a positive line number")
        if total_lines is not None and line > total_lines:
            return EvidenceCheck(
                False,
                kind,
                f"line {line} is past the end of {path} ({total_lines} lines)",
            )
        return EvidenceCheck(True, kind, detail={"path": path, "line": line})

    def _check_fact(self, item: dict) -> EvidenceCheck:
        """Validate a citation of the analyzer's own fact block.

        The validator's job here is the same as for a file citation: confirm
        the thing pointed at exists and is what the analyzer actually produced.
        Whether the CLAIM matches the value stays with adjudication, which can
        read the prose; a component whose fact block says file_count 0 while
        the claim says eighteen files is a real disagreement and must remain
        findable rather than being waved through by a citation that checks out.
        """
        component = str(item.get("component") or item.get("id") or "").strip()
        field = str(item.get("field") or "").strip()
        if not component or not field:
            return EvidenceCheck(
                False, "fact", "fact evidence needs both a component and a field"
            )
        if field not in CITABLE_FACTS:
            return EvidenceCheck(
                False, "fact",
                f"{field!r} is not an analyzer-derived fact; citable facts are "
                + ", ".join(CITABLE_FACTS),
            )
        facts = self._facts_by_id.get(component)
        if facts is None:
            return EvidenceCheck(
                False, "fact", f"no component {component!r} in the analyzed set"
            )
        if field not in facts:
            return EvidenceCheck(
                False, "fact",
                f"the analyzer produced no {field!r} for {component!r}",
            )
        return EvidenceCheck(
            True, "fact",
            detail={"component": component, "field": field, "value": facts[field]},
        )

    def _check_symbol(self, path: str, item: dict) -> EvidenceCheck:
        """Accept a symbol the cited file DEFINES or demonstrably REFERENCES.

        The enrichment task is mostly about relationships: "X uses Y". The
        natural citation, and the one the prompt invites, is Y at its use site
        inside X. Accepting only definitions rejected 1,162 of 1,270 symbol
        citations in the 2026-08-25 run, all with the same reason, which drove
        the relationship escalation rate to 47% where the true figure is 12%
        and sent roughly a third of the graph to the most expensive rung for no
        reason at all.

        This is not a loosened check. A citation still has to name a symbol the
        parser saw in that exact file; a symbol that exists elsewhere in the
        index, or nowhere, is still refused. What changes is that "seen" now
        includes the use site, and ``site`` records which kind of sighting it
        was so a reader can still tell a definition from a reference.
        """
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            return EvidenceCheck(False, "symbol", "symbol evidence has no symbol name")
        if symbol in self._symbols_by_path.get(path, ()):
            return EvidenceCheck(
                True,
                "symbol",
                detail={"path": path, "symbol": symbol, "site": "defined"},
            )
        if symbol in self._references_by_path.get(path, ()):
            return EvidenceCheck(
                True,
                "symbol",
                detail={"path": path, "symbol": symbol, "site": "referenced"},
            )
        if symbol in self._symbol_names:
            return EvidenceCheck(
                False,
                "symbol",
                f"symbol {symbol!r} exists in the index but is neither defined "
                f"nor referenced in {path}",
            )
        return EvidenceCheck(
            False, "symbol", f"symbol {symbol!r} is not in the symbol index"
        )

    # --- batch ----------------------------------------------------------------

    def validate_all(self, items: Any) -> list[EvidenceCheck]:
        """Validate a list of evidence items; a non-list reads as no evidence."""
        if not isinstance(items, list):
            return []
        return [self.check(item) for item in items]

    def any_valid(self, items: Any) -> bool:
        """True when at least one citation checks out.

        One good citation grounds a claim. Requiring every citation to be perfect
        would punish a tier for adding a second, weaker pointer alongside a solid
        one, which is the opposite of the behaviour the contract wants to teach.
        """
        return any(check.ok for check in self.validate_all(items))

    def failures(self, items: Any) -> list[EvidenceCheck]:
        return [check for check in self.validate_all(items) if not check.ok]
