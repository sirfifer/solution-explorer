"""Data model for the software bill of materials (P10-1).

Three record shapes carry everything the SBOM surfaces, all plain dataclasses so
they serialize deterministically and stay easy to test:

  - ``Dependency``: one third-party package the repo declares or locks, with its
    declared constraint, resolved version when a lockfile provides one, pin
    status, direct-vs-transitive scope, a package URL when one is derivable, and
    the manifest evidence (file plus line where cheap).
  - ``Target``: a language target or SDK version the owner asked to surface
    separately (requires-python, node engines, swift-tools-version, the go
    directive, dotnet TargetFramework, ruby version), never buried in the
    dependency list.
  - ``ParseWarning``: a manifest that was found but could not be parsed. Loud, per
    the card: a parse failure is a warning plus a dependency-less record, never a
    silent drop.

Determinism (invariant I4): nothing here reads a clock or a random source. Pin
status and scope are classified from the manifest text alone (no package-manager
execution, no network). The collector sorts every list before it lands in the
projection, so byte output is stable across runs and PYTHONHASHSEED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "Dependency",
    "Target",
    "ParseWarning",
    "EcosystemResult",
    "PIN_EXACT",
    "PIN_RANGE",
    "PIN_UNPINNED",
    "SCOPE_DIRECT",
    "SCOPE_TRANSITIVE",
    "ORIGIN_SHIPPING",
    "ORIGIN_TEST",
]

# Pin-status vocabulary. exact-pinned is a single concrete version the build
# cannot drift from; range is any constraint that admits more than one version;
# unpinned is no version constraint at all (a bare name, a wildcard, or a
# git/path/url reference we cannot resolve to a version deterministically).
PIN_EXACT = "exact-pinned"
PIN_RANGE = "range"
PIN_UNPINNED = "unpinned"

# Scope vocabulary. direct is declared in a manifest the repo authored;
# transitive is pulled in only through a lockfile as a dependency of a
# dependency. A package that is both (declared directly and also depended on
# transitively) is reported as direct, because the honest answer to "did you
# choose this" is yes.
SCOPE_DIRECT = "direct"
SCOPE_TRANSITIVE = "transitive"

# Origin vocabulary (review finding 1). A shipping dependency comes from a
# manifest the product actually builds from; a test dependency comes from a
# manifest under a test/fixture/example path segment, which is not a shipping
# source. Test-origin dependencies are kept and accounted (never silently
# dropped) but ranked behind and excluded from the shipping counts and the
# default CycloneDX components (the keep-mark-rank-behind pattern).
ORIGIN_SHIPPING = "shipping"
ORIGIN_TEST = "test"


@dataclass
class Dependency:
    """One third-party package with its version, pin status, and evidence."""

    ecosystem: str
    name: str
    declared: Optional[str] = None
    version: Optional[str] = None
    pin_status: str = PIN_UNPINNED
    scope: str = SCOPE_DIRECT
    purl: Optional[str] = None
    evidence_file: str = ""
    evidence_line: Optional[int] = None
    origin: str = ORIGIN_SHIPPING

    def to_dict(self) -> dict:
        """Compact JSON shape for the projection's supply_chain section.

        ``id`` is a stable within-dataset key (ecosystem + name + version) the
        viewer uses for list rendering. Evidence rides as a nested object so the
        viewer can render a file:line link.
        """
        out: dict = {
            "id": self.key(),
            "ecosystem": self.ecosystem,
            "name": self.name,
            "pin_status": self.pin_status,
            "scope": self.scope,
            "evidence": {"file": self.evidence_file},
        }
        if self.declared is not None:
            out["declared"] = self.declared
        if self.version is not None:
            out["version"] = self.version
        if self.purl is not None:
            out["purl"] = self.purl
        if self.evidence_line is not None:
            out["evidence"]["line"] = self.evidence_line
        # origin rides only when non-default (test), so shipping rows stay compact.
        if self.origin != ORIGIN_SHIPPING:
            out["origin"] = self.origin
        return out

    def key(self) -> str:
        """The dedupe/render key: ecosystem, name, and resolved version."""
        return f"{self.ecosystem}:{self.name}@{self.version or ''}"


@dataclass
class Target:
    """A language target or SDK version, surfaced apart from the dependencies."""

    ecosystem: str
    kind: str
    label: str
    constraint: str
    evidence_file: str = ""
    evidence_line: Optional[int] = None
    origin: str = ORIGIN_SHIPPING

    def to_dict(self) -> dict:
        out: dict = {
            "ecosystem": self.ecosystem,
            "kind": self.kind,
            "label": self.label,
            "constraint": self.constraint,
            "evidence": {"file": self.evidence_file},
        }
        if self.evidence_line is not None:
            out["evidence"]["line"] = self.evidence_line
        if self.origin != ORIGIN_SHIPPING:
            out["origin"] = self.origin
        return out


@dataclass
class ParseWarning:
    """A found manifest that failed to parse. Loud, never silent."""

    ecosystem: str
    file: str
    error: str
    origin: str = ORIGIN_SHIPPING

    def to_dict(self) -> dict:
        out = {"ecosystem": self.ecosystem, "file": self.file, "error": self.error}
        if self.origin != ORIGIN_SHIPPING:
            out["origin"] = self.origin
        return out


@dataclass
class EcosystemResult:
    """What one ecosystem instance (an anchored manifest directory) yielded."""

    ecosystem: str
    manifests: list[str] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
