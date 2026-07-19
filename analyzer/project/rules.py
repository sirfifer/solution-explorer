"""Project knowledge layer for the non-source inventory (P6-12).

The product self-matures per project. When an AI pass identifies what an unknown
artifact is, that knowledge becomes a permanent, deterministic, project-local
rule stored in ``.solution-explorer/rules/inventory.yml`` inside the analyzed
repo. Rules are DATA: no AI runs at parse or query time (invariant I9). The
unknown bucket trends to zero per project without any core-product change.

This module is the deterministic LOADER and MATCHER. It reads three ordered
sources and returns them ready for a first-match-wins evaluation:

  1. built-ins        (the ordered rules in ``inventory.classify_row``);
  2. an org-level slot (scaffolded empty here: the loader accepts an ordered
     list of rule files, only the repo one is wired today);
  3. repo rules       (``.solution-explorer/rules/inventory.yml``).

Later sources win for matching paths, so a repo rule beats an org rule beats a
built-in. Precedence across the whole classification is: project rules beat
``.gitattributes`` Linguist overrides beat built-ins.

RULE SCHEMA (one mapping per entry under a top-level ``rules:`` list):

    - id:             stable slug (required, unique per file)
      pattern:        gitignore-style glob (required)
      category:       a known CATEGORY_META id (required; unknown is rejected)
      label:          optional group-label override
      explanation:    optional group-explanation override
      recommendation: optional group-recommendation override
      flags:          optional partial flags override (security_sensitive,
                      likely_unwanted, gitignore_candidate)
      source:         "ai-enrichment" | "human" (required)
      added:          ISO date the rule was added (optional)
      evidence:       list of repo paths that motivated the rule (optional)
      contribute:     bool; scaffold for the future upstream-contribution path,
                      no behavior yet (optional, default false)

Bad rules (unknown category, invalid glob, missing required fields, unknown
source) are rejected LOUDLY on stderr, naming the rule and the problem, and
skipped individually. The rest of the file still loads. Determinism: rule
application order is file order, and the first matching project rule wins.

KISS bound: one YAML file, one loader, gitignore-glob semantics. The parser-rules
tier (a tree-sitter ``.scm`` envelope for reclassifying SOURCE, not just
non-source) is the documented NEXT tier of this folder and is deliberately not
built here.

GRACEFUL DEGRADATION: PyYAML is not installed in the minimal CI lane (the
``architecture-viz.yml`` generate job runs ``analyze.py`` with no extras). When a
rules file exists but PyYAML is unavailable, the loader emits one loud stderr
warning and skips the project rules entirely. It never crashes and never
silently drops a file that has rules the user expects to apply.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .inventory import CATEGORY_META

try:  # PyYAML is optional (see the module docstring on the minimal CI lane).
    import yaml as _yaml
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    _yaml = None

__all__ = [
    "PROJECT_RULES_RELPATH",
    "RULE_SOURCES",
    "InventoryRule",
    "RuleSet",
    "load_rule_set",
    "load_repo_rules_raw",
    "compile_glob",
]

# Where the repo-level rule file lives, relative to the scan root. Sits under the
# same ``.solution-explorer/`` directory as the fact store, so a project's learned
# knowledge travels next to its index.
PROJECT_RULES_RELPATH = Path(".solution-explorer") / "rules" / "inventory.yml"

# Valid rule sources. "human" rules are authored by a person and are NEVER
# overwritten or edited by the enrichment writer; "ai-enrichment" rules are the
# machine-learned knowledge.
RULE_SOURCES = frozenset({"ai-enrichment", "human"})

# The Linguist attributes we honor from ``.gitattributes`` and the inventory
# category each maps to (the existing GitHub-ecosystem standard).
_LINGUIST_MAP = {
    "linguist-vendored": "vendored",
    "linguist-documentation": "documentation",
    "linguist-generated": "build_test_output",
}


# ---------------------------------------------------------------------------
# gitignore-style glob compilation
# ---------------------------------------------------------------------------
# The semantics a .gitignore user expects, reduced to the pieces this tool
# needs (KISS): ``*`` matches within a path segment, ``**`` matches across
# segments, ``?`` matches a single non-slash char, a pattern WITHOUT a slash
# matches the basename at any depth, a pattern WITH a slash (or a leading slash)
# is anchored to the repo root, and a pattern that matches a directory also
# matches everything beneath it.

def _translate(pattern: str) -> str:
    """Translate a normalized glob body to a regex fragment (no anchors)."""
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # ``**`` spans path segments. ``**/`` matches zero or more leading
                # segments so ``a/**/b`` matches ``a/b`` and ``a/x/y/b``.
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                else:
                    out.append(".*")
                    i += 2
            else:
                # ``*`` stays within one segment (does not cross a slash).
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def compile_glob(pattern: str) -> re.Pattern:
    """Compile a gitignore-style ``pattern`` into an anchored regex.

    Raises ``ValueError`` on an empty pattern so a bad rule is rejected loudly
    rather than matching everything.
    """
    pat = pattern.replace("\\", "/").strip()
    if not pat:
        raise ValueError("empty pattern")
    anchored = pat.startswith("/")
    if anchored:
        pat = pat[1:]
    # A trailing slash names a directory explicitly; we match the dir and its
    # contents either way, so it is a no-op beyond stripping it here.
    if pat.endswith("/"):
        pat = pat[:-1]
    if not pat:
        raise ValueError("pattern is only slashes")
    has_slash = "/" in pat
    body = _translate(pat)
    if anchored or has_slash:
        prefix = "^"
    else:
        # No slash: match the basename at any depth (the gitignore default).
        prefix = r"(?:^|.*/)"
    # A directory match also covers everything beneath it, so a bare ``build``
    # matches ``build`` and ``build/x/y``.
    return re.compile(prefix + body + r"(?:/.*)?$")


# ---------------------------------------------------------------------------
# Rule model
# ---------------------------------------------------------------------------

@dataclass
class InventoryRule:
    """One project rule, already validated and with its glob compiled."""

    id: str
    pattern: str
    category: str
    source: str
    added: Optional[str] = None
    label: Optional[str] = None
    explanation: Optional[str] = None
    recommendation: Optional[str] = None
    flags: Optional[dict] = None
    evidence: tuple = ()
    contribute: bool = False
    origin_file: Optional[str] = None
    _regex: re.Pattern = field(default=None, repr=False, compare=False)

    def matches(self, path: str) -> bool:
        return self._regex is not None and self._regex.search(path.replace("\\", "/")) is not None


def _coerce_flags(raw) -> Optional[dict]:
    """A partial flags override: only the three known boolean keys are kept."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("flags must be a mapping of boolean overrides")
    known = {"security_sensitive", "likely_unwanted", "gitignore_candidate"}
    out: dict = {}
    for key, value in raw.items():
        if key not in known:
            raise ValueError(f"unknown flag '{key}'")
        if not isinstance(value, bool):
            raise ValueError(f"flag '{key}' must be a boolean")
        out[key] = value
    return out or None


def _build_rule(entry: dict, origin: str) -> InventoryRule:
    """Validate one raw mapping into an InventoryRule or raise ValueError.

    Every problem raises with a readable message so the loader can name the rule
    and the reason on stderr.
    """
    if not isinstance(entry, dict):
        raise ValueError(f"rule must be a mapping, got {type(entry).__name__}")
    rid = entry.get("id")
    if not rid or not isinstance(rid, str):
        raise ValueError("rule is missing a non-empty string 'id'")
    pattern = entry.get("pattern")
    if not pattern or not isinstance(pattern, str):
        raise ValueError(f"rule '{rid}' is missing a non-empty string 'pattern'")
    category = entry.get("category")
    if category not in CATEGORY_META:
        raise ValueError(
            f"rule '{rid}' has unknown category '{category}'; "
            f"must be one of {sorted(CATEGORY_META)}"
        )
    source = entry.get("source")
    if source not in RULE_SOURCES:
        raise ValueError(
            f"rule '{rid}' has invalid source '{source}'; must be one of {sorted(RULE_SOURCES)}"
        )
    regex = compile_glob(pattern)  # raises ValueError on a bad glob
    evidence = entry.get("evidence") or []
    if not isinstance(evidence, list):
        raise ValueError(f"rule '{rid}' evidence must be a list of paths")
    contribute = entry.get("contribute", False)
    if not isinstance(contribute, bool):
        raise ValueError(f"rule '{rid}' contribute must be a boolean")
    return InventoryRule(
        id=rid,
        pattern=pattern,
        category=category,
        source=source,
        added=entry.get("added"),
        label=entry.get("label"),
        explanation=entry.get("explanation"),
        recommendation=entry.get("recommendation"),
        flags=_coerce_flags(entry.get("flags")),
        evidence=tuple(str(p) for p in evidence),
        contribute=contribute,
        origin_file=origin,
        _regex=regex,
    )


def _default_warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def _load_one_file(path: Path, warn: Callable[[str], None]) -> list[InventoryRule]:
    """Load and validate one rule file. Bad rules are skipped loudly, not fatal."""
    if _yaml is None:
        warn(
            f"project rules file {path} exists but PyYAML is not installed; "
            f"project rules skipped. Install the package with its dependencies "
            f"to apply learned inventory rules."
        )
        return []
    try:
        raw = _yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, _yaml.YAMLError) as exc:  # type: ignore[union-attr]
        warn(f"cannot read project rules file {path}: {exc}; skipping the whole file")
        return []
    if raw is None:
        return []
    if isinstance(raw, dict):
        entries = raw.get("rules", [])
    elif isinstance(raw, list):
        entries = raw
    else:
        warn(
            f"project rules file {path} must be a mapping with a 'rules' list "
            f"(or a bare list); got {type(raw).__name__}; skipping the whole file"
        )
        return []
    if not isinstance(entries, list):
        warn(f"project rules file {path}: 'rules' must be a list; skipping the whole file")
        return []

    rules: list[InventoryRule] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        try:
            rule = _build_rule(entry, str(path))
        except ValueError as exc:
            warn(f"project rules file {path}: rejecting rule[{i}]: {exc}")
            continue
        if rule.id in seen:
            warn(f"project rules file {path}: duplicate rule id '{rule.id}'; keeping the first")
            continue
        seen.add(rule.id)
        rules.append(rule)
    return rules


# ---------------------------------------------------------------------------
# .gitattributes (Linguist honoring)
# ---------------------------------------------------------------------------

@dataclass
class _GitAttrRule:
    regex: re.Pattern
    category: str
    pattern: str


def _parse_gitattributes(root: Path, warn: Callable[[str], None]) -> list[_GitAttrRule]:
    """Parse the Linguist overrides we honor from ``<root>/.gitattributes``.

    Each non-comment line is ``pattern attr [attr...]``. We honor the SET forms
    ``linguist-vendored`` and ``linguist-vendored=true`` and IGNORE the unset
    forms ``-linguist-vendored`` and ``linguist-vendored=false`` (KISS). Later
    lines override earlier ones for the same path (gitattributes semantics), so
    matching takes the LAST matching rule.
    """
    path = root / ".gitattributes"
    if not path.is_file():
        return []
    rules: list[_GitAttrRule] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        pattern, attrs = parts[0], parts[1:]
        category: Optional[str] = None
        for attr in attrs:
            name, _, value = attr.partition("=")
            if name.startswith("-"):
                continue  # explicit unset, ignored
            if value.lower() == "false":
                continue  # attr=false, ignored
            mapped = _LINGUIST_MAP.get(name)
            if mapped is not None:
                category = mapped
        if category is None:
            continue
        try:
            regex = compile_glob(pattern)
        except ValueError as exc:
            warn(f".gitattributes: skipping pattern '{pattern}': {exc}")
            continue
        rules.append(_GitAttrRule(regex=regex, category=category, pattern=pattern))
    return rules


# ---------------------------------------------------------------------------
# The combined rule set (project rules + gitattributes), first-match-wins
# ---------------------------------------------------------------------------

@dataclass
class RuleSet:
    """Project rules and gitattributes overrides for one repo, ready to match.

    ``project_rules`` are already ordered highest-precedence-first (repo before
    org, file order within a source) so the first matching rule wins.
    ``gitattr_rules`` are in file order; the LAST matching one wins.
    """

    project_rules: list[InventoryRule] = field(default_factory=list)
    gitattr_rules: list[_GitAttrRule] = field(default_factory=list)

    def match_project(self, path: str) -> Optional[InventoryRule]:
        norm = path.replace("\\", "/")
        for rule in self.project_rules:
            if rule.matches(norm):
                return rule
        return None

    def match_gitattributes(self, path: str) -> Optional[str]:
        norm = path.replace("\\", "/")
        chosen: Optional[str] = None
        for rule in self.gitattr_rules:
            if rule.regex.search(norm):
                chosen = rule.category  # last match wins
        return chosen

    def is_empty(self) -> bool:
        return not self.project_rules and not self.gitattr_rules


def load_rule_set(
    root: Optional[Path],
    *,
    extra_sources: tuple[Optional[Path], ...] = (),
    warn: Callable[[str], None] = _default_warn,
) -> RuleSet:
    """Load the ordered rule sources for ``root`` into a RuleSet.

    Source order low-to-high precedence: an org-level slot (scaffolded empty via
    ``extra_sources``; pass org file paths to wire it later) then the repo file
    ``<root>/.solution-explorer/rules/inventory.yml``. Higher precedence is
    placed FIRST in ``project_rules`` so a first-match evaluation lets the repo
    rule win. Returns an empty RuleSet when ``root`` is None so a store-only
    re-projection still works.
    """
    if root is None:
        return RuleSet()
    root = Path(root)

    # Low-to-high precedence sources. ``extra_sources`` is the org slot: empty by
    # default (scaffolded), so today only the repo file contributes rules.
    ordered_sources: list[Optional[Path]] = list(extra_sources)
    ordered_sources.append(root / PROJECT_RULES_RELPATH)

    per_source: list[list[InventoryRule]] = []
    for source in ordered_sources:
        if source is None or not Path(source).is_file():
            per_source.append([])
            continue
        per_source.append(_load_one_file(Path(source), warn))

    # First-match-wins with higher precedence first: reverse the source order.
    project_rules: list[InventoryRule] = []
    for rules in reversed(per_source):
        project_rules.extend(rules)

    gitattr_rules = _parse_gitattributes(root, warn)
    return RuleSet(project_rules=project_rules, gitattr_rules=gitattr_rules)


def load_repo_rules_raw(
    root: Path, *, warn: Callable[[str], None] = _default_warn
) -> list[InventoryRule]:
    """Load only the repo-level rule file (for the enrichment writer's dedupe).

    Returns the validated repo rules in file order. Unlike ``load_rule_set`` this
    does not fold in the org slot or gitattributes; the writer needs the exact
    repo-file contents to dedupe against and to protect human rules.
    """
    path = Path(root) / PROJECT_RULES_RELPATH
    if not path.is_file():
        return []
    return _load_one_file(path, warn)
