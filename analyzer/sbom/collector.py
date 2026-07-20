"""Collect the supply chain by walking the repository for manifests (P10-1).

This is the deterministic, text-only heart of the SBOM. It walks the scan root
(pruning heavy vendored and build directories, and honoring .gitignore so it
never descends into node_modules or a git checkout or a workstation-local
ignored tree), groups the manifest-shaped files by directory, and asks each
registered ecosystem whether a directory anchors an instance of it. Every found
manifest is accounted: a manifest that parses contributes its dependencies and
targets; a manifest that fails to parse contributes a loud warning (never a
silent drop). Nothing here runs a package manager or touches the network.

Shipping vs test (review finding 1). A manifest under a test/fixture/example path
segment is not a shipping dependency source (it is a fixture the tests build
against). Those are KEPT and marked ``origin=test`` (never silently dropped), but
they are excluded by default from the shipping dependency counts, the shipping
ecosystem list, and the CycloneDX components: the keep-mark-rank-behind pattern.
The section carries them in a separate ``fixture`` block so nothing is hidden.

The aggregated result is shaped two ways downstream: a viewer-native compact
supply_chain section (``to_section``) and a CycloneDX document (built in
``cyclonedx.py`` from the shipping dependency and target lists). Determinism
(invariant I4): the walk is sorted, dependencies are deduped and ranked with a
total order, and no clock or random source is read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..utils import GitignoreMatcher
from .ecosystems import ECOSYSTEM_LABELS, ECOSYSTEM_MODULES
from .models import (
    ORIGIN_SHIPPING,
    ORIGIN_TEST,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    ParseWarning,
    Target,
)

__all__ = ["SupplyChain", "collect_supply_chain", "SUPPLY_CHAIN_VERSION"]

# Bump when the emitted supply_chain shape changes; the viewer reads this and an
# older dataset without the section degrades to no supply chain surface.
SUPPLY_CHAIN_VERSION = 1

# Directories never worth walking into for first-party manifests: version control,
# installed/vendored dependency trees, build output, and virtual environments. A
# manifest inside node_modules is a dependency's own manifest, not this repo's.
_PRUNE_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor", "Pods",
    ".build", "build", "dist", "target", "out", ".next", ".nuxt", ".output",
    ".venv", "venv", "env", ".env", "__pycache__", ".gradle", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".turbo", ".vercel",
    "DerivedData", ".idea", ".vscode", ".swiftpm", "third_party", "third-party",
    ".solution-explorer", ".yarn",
})

# Path segments that mark a manifest as a TEST/FIXTURE/EXAMPLE source rather than
# a shipping dependency source. Compared case-insensitively against each path
# component (review finding 1).
_FIXTURE_SEGMENTS = frozenset({
    "test", "tests", "testdata", "fixture", "fixtures",
    "example", "examples", "__tests__", "spec", "specs",
})

# The exact manifest basenames worth reading. Pattern-matched families
# (requirements*.txt, *.csproj) are handled separately in ``_is_candidate``.
_CANDIDATE_NAMES = frozenset({
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
    "pnpm-lock.yaml", "pyproject.toml", "poetry.lock", "Package.swift",
    "Package.resolved", "go.mod", "go.sum", "Gemfile", "Gemfile.lock",
    "Cargo.toml", "Cargo.lock", "Podfile", "Podfile.lock", "packages.lock.json",
})
_PROJECT_EXTS = (".csproj", ".fsproj", ".vbproj")


def _is_candidate(filename: str) -> bool:
    if filename in _CANDIDATE_NAMES:
        return True
    low = filename.lower()
    if low.startswith("requirements") and low.endswith(".txt"):
        return True
    return filename.endswith(_PROJECT_EXTS)


def _is_fixture_dir(dirpath: str) -> bool:
    """Whether a manifest directory is a test/fixture/example source."""
    parts = [p.lower() for p in dirpath.split("/") if p]
    return any(p in _FIXTURE_SEGMENTS for p in parts)


@dataclass
class SupplyChain:
    """The aggregated supply chain: dependencies, targets, warnings, vendored.

    Records carry an ``origin`` (shipping or test); the section and the CycloneDX
    document present the shipping records by default and the test-origin records
    in a separate, accounted-but-excluded block.
    """

    dependencies: list[Dependency] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    # ecosystem id -> sorted list of shipping manifest paths.
    manifests: dict[str, list[str]] = field(default_factory=dict)
    # ecosystem id -> sorted list of test/fixture manifest paths.
    fixture_manifests: dict[str, list[str]] = field(default_factory=dict)
    # Vendored directory references from the coverage inventory (P6-10 seam).
    vendored: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.dependencies and not self.targets and not self.warnings

    def shipping_dependencies(self) -> list[Dependency]:
        return [d for d in self.dependencies if d.origin == ORIGIN_SHIPPING]

    def fixture_dependencies(self) -> list[Dependency]:
        return [d for d in self.dependencies if d.origin == ORIGIN_TEST]

    def _ecosystems(self, deps, targets, manifests) -> list[str]:
        present = {d.ecosystem for d in deps}
        present |= {t.ecosystem for t in targets}
        present |= set(manifests)
        order = [m.ECOSYSTEM for m in ECOSYSTEM_MODULES]
        return [e for e in order if e in present]

    def ecosystems(self) -> list[str]:
        """The SHIPPING ecosystem ids present, in registry order."""
        return self._ecosystems(
            self.shipping_dependencies(),
            [t for t in self.targets if t.origin == ORIGIN_SHIPPING],
            self.manifests,
        )

    def _eco_blocks(self, deps, manifests) -> list[dict]:
        blocks = []
        for eco in self._ecosystems(deps, [], manifests):
            eco_deps = [d for d in deps if d.ecosystem == eco]
            pin_counts: dict[str, int] = {}
            for d in eco_deps:
                pin_counts[d.pin_status] = pin_counts.get(d.pin_status, 0) + 1
            blocks.append({
                "id": eco,
                "label": ECOSYSTEM_LABELS.get(eco, eco),
                "manifests": manifests.get(eco, []),
                "dependency_count": len(eco_deps),
                "direct_count": sum(1 for d in eco_deps if d.scope == SCOPE_DIRECT),
                "transitive_count": sum(1 for d in eco_deps if d.scope == SCOPE_TRANSITIVE),
                "pin_counts": pin_counts,
            })
        return blocks

    def to_section(self) -> dict:
        """The compact, viewer-native supply_chain section for the projection."""
        ship_deps = self.shipping_dependencies()
        ship_targets = [t for t in self.targets if t.origin == ORIGIN_SHIPPING]
        ship_warnings = [w for w in self.warnings if w.origin == ORIGIN_SHIPPING]
        fix_deps = self.fixture_dependencies()
        fix_targets = [t for t in self.targets if t.origin == ORIGIN_TEST]
        fix_warnings = [w for w in self.warnings if w.origin == ORIGIN_TEST]

        section = {
            "version": SUPPLY_CHAIN_VERSION,
            "sbom_endpoint": "sbom.json",
            "sbom_format": "CycloneDX 1.5",
            # The tool has no vulnerability scanner; this is a plain inventory. The
            # viewer shows this verbatim so no reader mistakes it for a security
            # posture claim (no-theater rule, VISION.md).
            "scope_note": (
                "Inventory of declared and locked dependencies with versions and "
                "pin status. Not a vulnerability scan: no security posture is "
                "claimed or implied."
            ),
            "ecosystems": self._eco_blocks(ship_deps, self.manifests),
            "targets": [t.to_dict() for t in ship_targets],
            "dependencies": [d.to_dict() for d in ship_deps],
            "warnings": [w.to_dict() for w in ship_warnings],
            "counts": self._counts(ship_deps, ship_targets, ship_warnings),
        }
        section["counts"]["fixture"] = {
            "ecosystems": len(self._ecosystems(fix_deps, fix_targets, self.fixture_manifests)),
            "dependencies": len(fix_deps),
            "targets": len(fix_targets),
            "warnings": len(fix_warnings),
        }
        # Test/fixture-origin records: kept and accounted, excluded from the
        # shipping numbers above, surfaced here so nothing is hidden (finding 1).
        if fix_deps or fix_targets or fix_warnings:
            section["fixture"] = {
                "note": (
                    "Dependencies declared by manifests under test, fixture, or "
                    "example directories. Accounted here but excluded from the "
                    "shipping counts and the CycloneDX components."
                ),
                "ecosystems": self._eco_blocks(fix_deps, self.fixture_manifests),
                "targets": [t.to_dict() for t in fix_targets],
                "dependencies": [d.to_dict() for d in fix_deps],
                "warnings": [w.to_dict() for w in fix_warnings],
            }
        if self.vendored:
            section["vendored"] = self.vendored
            section["counts"]["vendored"] = len(self.vendored)
        return section

    def _counts(self, deps, targets, warnings) -> dict:
        direct = sum(1 for d in deps if d.scope == SCOPE_DIRECT)
        pin_totals: dict[str, int] = {}
        for d in deps:
            pin_totals[d.pin_status] = pin_totals.get(d.pin_status, 0) + 1
        return {
            "ecosystems": len(self._ecosystems(deps, targets, self.manifests)),
            "dependencies": len(deps),
            "direct": direct,
            "transitive": len(deps) - direct,
            "targets": len(targets),
            "warnings": len(warnings),
            "vendored": len(self.vendored),
            "pin_status": pin_totals,
        }


def _scope_rank(scope: str) -> int:
    return 0 if scope == SCOPE_DIRECT else 1


def _dedupe_and_rank(deps: list[Dependency]) -> list[Dependency]:
    """Collapse duplicates and return a totally-ordered dependency list.

    Duplicates (same ecosystem, name, resolved version, AND origin) can arise
    across a monorepo's several manifests. They merge into one record, preferring
    the direct scope (the honest answer to "did you choose this" is yes) and the
    lexicographically smallest evidence file so the pick is stable. Distinct
    versions of the same package stay separate: an SBOM records each version. A
    shipping and a test-origin copy of the same package do NOT merge, so the
    shipping counts never absorb a fixture dependency.

    Ranking (I11): grouped by ecosystem, then direct before transitive, then by
    name and version, so the surface reads direct-first within each ecosystem.
    """
    merged: dict[tuple, Dependency] = {}
    for dep in deps:
        key = (dep.ecosystem, dep.name, dep.version, dep.origin)
        existing = merged.get(key)
        if existing is None:
            merged[key] = dep
            continue
        # Prefer a direct classification when either instance is direct.
        if existing.scope != SCOPE_DIRECT and dep.scope == SCOPE_DIRECT:
            existing.scope = SCOPE_DIRECT
            existing.declared = dep.declared
            existing.pin_status = dep.pin_status
        # Keep the smallest evidence path for a stable pointer.
        if (dep.evidence_file, dep.evidence_line or 0) < (
            existing.evidence_file, existing.evidence_line or 0
        ) and dep.scope == existing.scope:
            existing.evidence_file = dep.evidence_file
            existing.evidence_line = dep.evidence_line

    ordered = list(merged.values())
    ordered.sort(key=lambda d: (
        d.ecosystem, _scope_rank(d.scope), d.name.lower(), d.name, d.version or "",
    ))
    return ordered


def collect_supply_chain(root: Optional[Path], coverage: Optional[dict] = None) -> Optional[SupplyChain]:
    """Walk ``root`` for manifests and return the aggregated SupplyChain, or None.

    Returns None when ``root`` is None (a multi-repo projection assembled without
    a single tree; per-member SBOMs fall out of each member's own projection) or
    when the repository carries no manifests at all (nothing to show). ``coverage``
    is the projection's coverage dict; when it carries a non-source inventory with
    a vendored group, those directories are referenced as vendored components.
    """
    if root is None:
        return None
    root = Path(root)
    if not root.is_dir():
        return None

    by_dir = _gather_candidates(root)
    if not by_dir and not _has_vendored(coverage):
        return None

    supply = SupplyChain()
    all_deps: list[Dependency] = []
    ship_manifests: dict[str, set[str]] = {}
    fix_manifests: dict[str, set[str]] = {}

    for dirpath in sorted(by_dir):
        fileset = by_dir[dirpath]
        origin = ORIGIN_TEST if _is_fixture_dir(dirpath) else ORIGIN_SHIPPING
        for module in ECOSYSTEM_MODULES:
            if not module.is_anchored(fileset):
                continue
            result = module.collect(root, dirpath, fileset)
            # Tag every record from this instance with its origin.
            for dep in result.dependencies:
                dep.origin = origin
            for target in result.targets:
                target.origin = origin
            for warning in result.warnings:
                warning.origin = origin
            all_deps.extend(result.dependencies)
            supply.targets.extend(result.targets)
            supply.warnings.extend(result.warnings)
            bucket = fix_manifests if origin == ORIGIN_TEST else ship_manifests
            bucket.setdefault(module.ECOSYSTEM, set()).update(result.manifests)

    supply.dependencies = _dedupe_and_rank(all_deps)
    supply.targets.sort(key=lambda t: (t.origin, t.ecosystem, t.kind, t.constraint, t.evidence_file))
    supply.warnings.sort(key=lambda w: (w.origin, w.ecosystem, w.file, w.error))
    supply.manifests = {eco: sorted(paths) for eco, paths in ship_manifests.items()}
    supply.fixture_manifests = {eco: sorted(paths) for eco, paths in fix_manifests.items()}
    supply.vendored = _vendored_from_coverage(coverage)

    if supply.is_empty() and not supply.vendored:
        return None
    return supply


def _gather_candidates(root: Path) -> dict[str, set[str]]:
    """Return ``{relative_dir: {manifest_basenames}}`` under the pruned walk.

    Prunes the built-in heavy directories AND anything .gitignore ignores, so a
    gitignored (workstation-local) manifest or lockfile is not treated as a
    shipping source. This keeps the SBOM consistent with the enumerator, which
    (as of the analyzer-hygiene change) also honors .gitignore.
    """
    matcher = GitignoreMatcher(root)
    by_dir: dict[str, set[str]] = {}
    for current, dirs, files in os.walk(root):
        rel = os.path.relpath(current, root)
        rel = "" if rel == "." else rel.replace(os.sep, "/")

        # Prune in place (and sort for a deterministic descent): drop the built-in
        # heavy directories and anything .gitignore ignores.
        kept = []
        for name in dirs:
            if name in _PRUNE_DIRS:
                continue
            child = f"{rel}/{name}" if rel else name
            if matcher.match(child, is_dir=True) is not None:
                continue
            kept.append(name)
        dirs[:] = sorted(kept)

        candidates = set()
        for f in files:
            if not _is_candidate(f):
                continue
            child = f"{rel}/{f}" if rel else f
            if matcher.match(child, is_dir=False) is not None:
                continue  # a gitignored manifest is workstation-local, not shipping
            candidates.add(f)
        if candidates:
            by_dir[rel] = candidates
    return by_dir


def _has_vendored(coverage: Optional[dict]) -> bool:
    return bool(_vendored_from_coverage(coverage))


def _vendored_from_coverage(coverage: Optional[dict]) -> list[dict]:
    """Reference vendored directories from the coverage inventory (P6-10 seam).

    The inventory already classified checked-in third-party trees into a
    ``vendored`` group; we do not re-walk them. We surface each top directory it
    found as a vendored component with an evidence pointer, so the supply chain
    view lists code that ships in the repo but was written elsewhere.
    """
    if not isinstance(coverage, dict):
        return []
    inventory = coverage.get("inventory")
    if not isinstance(inventory, dict):
        return []
    for group in inventory.get("groups", []) or []:
        if isinstance(group, dict) and group.get("id") == "vendored":
            out = []
            for entry in group.get("top_directories", []) or []:
                if isinstance(entry, dict) and entry.get("dir"):
                    out.append({
                        "path": entry["dir"],
                        "file_count": entry.get("count"),
                        "evidence": {"file": entry["dir"]},
                    })
            return out
    return []
