"""Collect the supply chain by walking the repository for manifests (P10-1).

This is the deterministic, text-only heart of the SBOM. It walks the scan root
(pruning heavy vendored and build directories so it never descends into
node_modules or a git checkout), groups the manifest-shaped files by directory,
and asks each registered ecosystem whether a directory anchors an instance of it.
Every found manifest is accounted: a manifest that parses contributes its
dependencies and targets; a manifest that fails to parse contributes a loud
warning (never a silent drop). Nothing here runs a package manager or touches the
network.

The aggregated result is shaped two ways downstream: a viewer-native compact
supply_chain section (``to_section``) and a CycloneDX document (built in
``cyclonedx.py`` from the same dependency and target lists). Determinism
(invariant I4): the walk is sorted, dependencies are deduped and ranked with a
total order, and no clock or random source is read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .ecosystems import ECOSYSTEM_LABELS, ECOSYSTEM_MODULES
from .models import (
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


@dataclass
class SupplyChain:
    """The aggregated supply chain: dependencies, targets, warnings, vendored."""

    dependencies: list[Dependency] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    # ecosystem id -> sorted list of manifest paths that anchored/were read.
    manifests: dict[str, list[str]] = field(default_factory=dict)
    # Vendored directory references from the coverage inventory (P6-10 seam).
    vendored: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.dependencies and not self.targets and not self.warnings

    def ecosystems(self) -> list[str]:
        """The ecosystem ids present, in registry order."""
        present = {d.ecosystem for d in self.dependencies}
        present |= {t.ecosystem for t in self.targets}
        present |= set(self.manifests)
        order = [m.ECOSYSTEM for m in ECOSYSTEM_MODULES]
        return [e for e in order if e in present]

    def to_section(self) -> dict:
        """The compact, viewer-native supply_chain section for the projection."""
        eco_blocks = []
        for eco in self.ecosystems():
            deps = [d for d in self.dependencies if d.ecosystem == eco]
            pin_counts: dict[str, int] = {}
            for d in deps:
                pin_counts[d.pin_status] = pin_counts.get(d.pin_status, 0) + 1
            eco_blocks.append({
                "id": eco,
                "label": ECOSYSTEM_LABELS.get(eco, eco),
                "manifests": self.manifests.get(eco, []),
                "dependency_count": len(deps),
                "direct_count": sum(1 for d in deps if d.scope == SCOPE_DIRECT),
                "transitive_count": sum(1 for d in deps if d.scope == SCOPE_TRANSITIVE),
                "pin_counts": pin_counts,
            })

        direct = sum(1 for d in self.dependencies if d.scope == SCOPE_DIRECT)
        transitive = len(self.dependencies) - direct
        pin_totals: dict[str, int] = {}
        for d in self.dependencies:
            pin_totals[d.pin_status] = pin_totals.get(d.pin_status, 0) + 1

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
            "ecosystems": eco_blocks,
            "targets": [t.to_dict() for t in self.targets],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "warnings": [w.to_dict() for w in self.warnings],
            "counts": {
                "ecosystems": len(eco_blocks),
                "dependencies": len(self.dependencies),
                "direct": direct,
                "transitive": transitive,
                "targets": len(self.targets),
                "warnings": len(self.warnings),
                "vendored": len(self.vendored),
                "pin_status": pin_totals,
            },
        }
        if self.vendored:
            section["vendored"] = self.vendored
        return section


def _scope_rank(scope: str) -> int:
    return 0 if scope == SCOPE_DIRECT else 1


def _dedupe_and_rank(deps: list[Dependency]) -> list[Dependency]:
    """Collapse duplicates and return a totally-ordered dependency list.

    Duplicates (same ecosystem, name, and resolved version) can arise across a
    monorepo's several manifests. They merge into one record, preferring the
    direct scope (the honest answer to "did you choose this" is yes) and the
    lexicographically smallest evidence file so the pick is stable. Distinct
    versions of the same package stay separate: an SBOM records each version.

    Ranking (I11): grouped by ecosystem, then direct before transitive, then by
    name and version, so the surface reads direct-first within each ecosystem.
    """
    merged: dict[tuple, Dependency] = {}
    for dep in deps:
        key = (dep.ecosystem, dep.name, dep.version)
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
    manifests: dict[str, set[str]] = {}

    for dirpath in sorted(by_dir):
        fileset = by_dir[dirpath]
        for module in ECOSYSTEM_MODULES:
            if not module.is_anchored(fileset):
                continue
            result = module.collect(root, dirpath, fileset)
            all_deps.extend(result.dependencies)
            supply.targets.extend(result.targets)
            supply.warnings.extend(result.warnings)
            manifests.setdefault(module.ECOSYSTEM, set()).update(result.manifests)

    supply.dependencies = _dedupe_and_rank(all_deps)
    supply.targets.sort(key=lambda t: (t.ecosystem, t.kind, t.constraint, t.evidence_file))
    supply.warnings.sort(key=lambda w: (w.ecosystem, w.file, w.error))
    supply.manifests = {eco: sorted(paths) for eco, paths in manifests.items()}
    supply.vendored = _vendored_from_coverage(coverage)

    if supply.is_empty() and not supply.vendored:
        return None
    return supply


def _gather_candidates(root: Path) -> dict[str, set[str]]:
    """Return ``{relative_dir: {manifest_basenames}}`` under the pruned walk."""
    by_dir: dict[str, set[str]] = {}
    for current, dirs, files in os.walk(root):
        # Prune in place (and sort for a deterministic descent).
        dirs[:] = sorted(d for d in dirs if d not in _PRUNE_DIRS)
        candidates = {f for f in files if _is_candidate(f)}
        if not candidates:
            continue
        rel = os.path.relpath(current, root)
        rel = "" if rel == "." else rel.replace(os.sep, "/")
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
