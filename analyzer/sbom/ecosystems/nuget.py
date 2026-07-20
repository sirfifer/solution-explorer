""".NET / NuGet ecosystem: *.csproj PackageReference plus packages.lock.json.

Direct dependencies come from ``<PackageReference>`` elements in the project
files; when a ``packages.lock.json`` is present it is authoritative for resolved
versions and the direct-vs-transitive split (its entries carry a ``type`` of
Direct or Transitive). ``<TargetFramework>`` / ``<TargetFrameworks>`` surface as
targets.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

from ..models import (
    PIN_EXACT,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    EcosystemResult,
    ParseWarning,
    Target,
)
from ..purl import build_purl, classify_pin
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "nuget"

_PROJECT_EXTS = (".csproj", ".fsproj", ".vbproj")


def is_anchored(filenames: set[str]) -> bool:
    if any(f.endswith(_PROJECT_EXTS) for f in filenames):
        return True
    return "packages.lock.json" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root

    # The lock, when present, is authoritative for scope and resolved versions.
    lock_rel, lock = _read_lock(base, dirpath, filenames, result)

    # declared[name] -> (constraint, evidence_file, evidence_line) from project files.
    declared: dict[str, tuple[str | None, str, int | None]] = {}
    for filename in sorted(f for f in filenames if f.endswith(_PROJECT_EXTS)):
        _parse_project(base, dirpath, filename, result, declared)

    emitted: set[str] = set()

    # Prefer the lock's authoritative direct/transitive classification.
    for name in sorted(lock):
        entry = lock[name]
        version = entry.get("resolved")
        scope = SCOPE_DIRECT if entry.get("type", "").lower() == "direct" else SCOPE_TRANSITIVE
        decl = declared.get(name)
        constraint = decl[0] if decl else entry.get("requested")
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name,
            declared=constraint, version=version,
            pin_status=classify_pin(ECOSYSTEM, constraint) if scope == SCOPE_DIRECT
            else (PIN_EXACT if version else classify_pin(ECOSYSTEM, None)),
            scope=scope, purl=build_purl(ECOSYSTEM, name, version),
            evidence_file=decl[1] if decl else lock_rel,
            evidence_line=decl[2] if decl else None,
        ))
        emitted.add(name)

    # PackageReferences with no lock entry (a repo without a committed lock).
    for name in sorted(declared):
        if name in emitted:
            continue
        constraint, ev_file, ev_line = declared[name]
        pin = classify_pin(ECOSYSTEM, constraint)
        # A bare `Version="1.0.0"` is a FLOATING MINIMUM (review finding 8), so it
        # is a range with no truly-resolved version without a lock. Only a
        # bracketed exact `[1.0.0]` yields a concrete resolved version.
        version = constraint.strip("[]") if (pin == PIN_EXACT and constraint) else None
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=constraint, version=version,
            pin_status=pin, scope=SCOPE_DIRECT,
            purl=build_purl(ECOSYSTEM, name, version), evidence_file=ev_file,
            evidence_line=ev_line,
        ))

    return result


def _local(tag: str) -> str:
    """The local element name, dropping any ``{namespace}`` prefix."""
    return tag.rsplit("}", 1)[-1]


def _parse_project(base: Path, dirpath: str, filename: str, result: EcosystemResult, declared: dict) -> None:
    rel = join_rel(dirpath, filename)
    result.manifests.append(rel)
    try:
        text = read_text(base / filename)
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return
    try:
        rootel = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid XML: {exc}"))
        return
    lines = text.splitlines()

    for el in rootel.iter():
        tag = _local(el.tag)
        if tag in ("TargetFramework", "TargetFrameworks") and el.text and el.text.strip():
            for tfm in el.text.strip().split(";"):
                tfm = tfm.strip()
                if tfm:
                    result.targets.append(Target(
                        ecosystem=ECOSYSTEM, kind="dotnet", label="Target framework",
                        constraint=tfm, evidence_file=rel,
                        evidence_line=find_line(lines, tfm),
                    ))
        elif tag == "PackageReference":
            name = el.get("Include") or el.get("Update")
            if not name:
                continue
            version = el.get("Version")
            if version is None:
                # Version may be a child element rather than an attribute.
                for child in el:
                    if _local(child.tag) == "Version" and child.text:
                        version = child.text.strip()
                        break
            declared.setdefault(name, (version, rel, find_line(lines, f'"{name}"')))


def _read_lock(base: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    if "packages.lock.json" not in filenames:
        return None, {}
    rel = join_rel(dirpath, "packages.lock.json")
    result.manifests.append(rel)
    try:
        text = read_text(base / "packages.lock.json")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return rel, {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid JSON: {exc}"))
        return rel, {}
    merged: dict[str, dict] = {}
    frameworks = data.get("dependencies")
    if isinstance(frameworks, dict):
        for deps in frameworks.values():
            if not isinstance(deps, dict):
                continue
            for name, entry in deps.items():
                if not isinstance(entry, dict):
                    continue
                existing = merged.get(name)
                # A package may appear under several target frameworks; keep the
                # Direct classification if any framework declares it direct.
                if existing is None:
                    merged[name] = entry
                elif entry.get("type", "").lower() == "direct":
                    merged[name] = entry
    return rel, merged
