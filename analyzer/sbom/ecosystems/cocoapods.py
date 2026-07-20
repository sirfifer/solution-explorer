"""CocoaPods ecosystem: Podfile plus Podfile.lock.

Direct pods come from the Podfile's ``pod`` declarations; resolved versions and
the transitive closure come from Podfile.lock's ``PODS:`` section. Subspec names
(``Alamofire/Core``) collapse to their root pod. CocoaPods has no separate
language target.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import (
    PIN_EXACT,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    EcosystemResult,
    ParseWarning,
)
from ..purl import build_purl, classify_pin
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "cocoapods"

_POD = re.compile(r"""^\s*pod\s+["']([^"']+)["']\s*(?:,\s*["']([^"']+)["'])?""")
# A top-level Podfile.lock PODS entry: two-space indent, "- Name (version)".
_LOCK_POD = re.compile(r"^  - ([^\s(/]+)(?:/\S+)?\s*\(([^)]+)\)")


def is_anchored(filenames: set[str]) -> bool:
    return "Podfile" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root
    rel = join_rel(dirpath, "Podfile")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Podfile")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return result
    lines = text.splitlines()

    direct: dict[str, str | None] = {}
    for raw in lines:
        m = _POD.match(raw)
        if m:
            name = m.group(1).split("/", 1)[0]
            direct.setdefault(name, m.group(2))

    lock_rel, resolved = _read_lock(base, dirpath, filenames, result)

    for name in sorted(direct):
        constraint = direct[name]
        version = resolved.get(name)
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=constraint, version=version,
            pin_status=classify_pin(ECOSYSTEM, constraint), scope=SCOPE_DIRECT,
            purl=build_purl(ECOSYSTEM, name, version), evidence_file=rel,
            evidence_line=find_line(lines, f"'{name}'") or find_line(lines, f'"{name}"'),
        ))

    if lock_rel is not None:
        for name in sorted(resolved):
            if name in direct:
                continue
            version = resolved[name]
            result.dependencies.append(Dependency(
                ecosystem=ECOSYSTEM, name=name, declared=None, version=version,
                pin_status=PIN_EXACT if version else classify_pin(ECOSYSTEM, None),
                scope=SCOPE_TRANSITIVE,
                purl=build_purl(ECOSYSTEM, name, version), evidence_file=lock_rel,
            ))

    return result


def _read_lock(base: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    if "Podfile.lock" not in filenames:
        return None, {}
    rel = join_rel(dirpath, "Podfile.lock")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Podfile.lock")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return rel, {}
    resolved: dict[str, str] = {}
    in_pods = False
    for raw in text.splitlines():
        if raw.rstrip() == "PODS:":
            in_pods = True
            continue
        if in_pods:
            if raw and not raw[0].isspace():
                in_pods = False
                continue
            m = _LOCK_POD.match(raw)
            if m:
                # Root pod name (subspecs collapse to their parent).
                resolved.setdefault(m.group(1), m.group(2))
    return rel, resolved
