"""npm / Node.js ecosystem: package.json plus a lockfile.

Direct dependencies (with their declared constraints) come from package.json;
resolved versions and the transitive closure come from the lockfile when one is
present (package-lock.json / npm-shrinkwrap.json, yarn.lock, or pnpm-lock.yaml).
A direct dependency is reported direct even when the lockfile also lists it as a
transitive of something else. Node engine constraints surface as targets.

The lockfiles are parsed deterministically from their own text: package-lock is
JSON (stdlib), yarn.lock and pnpm-lock are read with small line scanners so the
zero-dependency analyzer core needs no YAML library.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

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

ECOSYSTEM = "npm"

# Lockfiles in resolution priority: the first present in the anchor directory
# supplies resolved versions and the transitive set.
_LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")

# The package.json dependency maps that count as directly declared. peer
# dependencies are intentionally excluded: they are a compatibility contract, not
# something this package installs.
_DIRECT_FIELDS = ("dependencies", "devDependencies", "optionalDependencies")


def is_anchored(filenames: set[str]) -> bool:
    return "package.json" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    pkg_rel = join_rel(dirpath, "package.json")
    result.manifests.append(pkg_rel)
    try:
        text = read_text(root / dirpath / "package.json") if dirpath else read_text(root / "package.json")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, pkg_rel, f"unreadable: {exc}"))
        return result
    try:
        pkg = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, pkg_rel, f"invalid JSON: {exc}"))
        return result
    if not isinstance(pkg, dict):
        result.warnings.append(ParseWarning(ECOSYSTEM, pkg_rel, "top level is not an object"))
        return result

    lines = text.splitlines()

    # Node/npm engine constraints, surfaced as targets rather than dependencies.
    engines = pkg.get("engines")
    if isinstance(engines, dict):
        for engine_key, kind, label in (
            ("node", "node", "Node.js engine"),
            ("npm", "npm", "npm engine"),
        ):
            constraint = engines.get(engine_key)
            if isinstance(constraint, str) and constraint.strip():
                result.targets.append(Target(
                    ecosystem=ECOSYSTEM, kind=kind, label=label,
                    constraint=constraint.strip(), evidence_file=pkg_rel,
                    evidence_line=find_line(lines, f'"{engine_key}"'),
                ))

    # Direct dependencies with their declared constraints.
    direct_declared: dict[str, str] = {}
    for field in _DIRECT_FIELDS:
        block = pkg.get(field)
        if not isinstance(block, dict):
            continue
        for name, constraint in block.items():
            if not isinstance(name, str):
                continue
            constraint_str = constraint if isinstance(constraint, str) else ""
            # A name may appear in more than one field; first declaration wins,
            # so the ordering of _DIRECT_FIELDS is the tie-break.
            direct_declared.setdefault(name, constraint_str)

    # Resolve versions and the transitive set from the first present lockfile.
    lock_name, resolved = _read_lockfile(root, dirpath, filenames, result)
    lock_rel = join_rel(dirpath, lock_name) if lock_name else None

    for name in sorted(direct_declared):
        declared = direct_declared[name]
        version = resolved.get(name)
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=declared, version=version,
            pin_status=classify_pin(ECOSYSTEM, declared), scope=SCOPE_DIRECT,
            purl=build_purl(ECOSYSTEM, name, version), evidence_file=pkg_rel,
            evidence_line=find_line(lines, f'"{name}"'),
        ))

    # Transitives: everything the lockfile resolved that is not a direct dep.
    if lock_rel is not None:
        for name in sorted(resolved):
            if name in direct_declared:
                continue
            version = resolved[name]
            result.dependencies.append(Dependency(
                ecosystem=ECOSYSTEM, name=name, declared=None, version=version,
                pin_status=PIN_EXACT if version else classify_pin(ECOSYSTEM, None),
                scope=SCOPE_TRANSITIVE,
                purl=build_purl(ECOSYSTEM, name, version), evidence_file=lock_rel,
            ))

    return result


def _read_lockfile(root: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    """Return ``(lockfile_name, {name: version})`` for the first present lock.

    Returns ``(None, {})`` when no lockfile sits beside package.json. A lockfile
    that cannot be parsed produces a loud warning and an empty resolution map, so
    direct dependencies still list (without resolved versions) rather than
    vanishing.
    """
    for lock_name in _LOCKFILES:
        if lock_name not in filenames:
            continue
        lock_rel = join_rel(dirpath, lock_name)
        result.manifests.append(lock_rel)
        path = root / dirpath / lock_name if dirpath else root / lock_name
        try:
            text = read_text(path)
        except OSError as exc:
            result.warnings.append(ParseWarning(ECOSYSTEM, lock_rel, f"unreadable: {exc}"))
            return lock_name, {}
        try:
            if lock_name in ("package-lock.json", "npm-shrinkwrap.json"):
                return lock_name, _parse_npm_lock(text)
            if lock_name == "yarn.lock":
                return lock_name, _parse_yarn_lock(text)
            return lock_name, _parse_pnpm_lock(text)
        except (json.JSONDecodeError, ValueError) as exc:
            result.warnings.append(ParseWarning(ECOSYSTEM, lock_rel, f"invalid lockfile: {exc}"))
            return lock_name, {}
    return None, {}


def _name_from_lock_key(key: str) -> str:
    """The package name from a v2/v3 ``packages`` key (``node_modules/<name>``).

    Nested installs key on the full path (``node_modules/a/node_modules/b``); the
    installed name is the segment after the LAST ``node_modules/``.
    """
    if "node_modules/" in key:
        return key.rsplit("node_modules/", 1)[-1]
    return key


def _parse_npm_lock(text: str) -> dict[str, str]:
    data = json.loads(text)
    resolved: dict[str, str] = {}
    # v2/v3: the flat ``packages`` map. The root package is the "" key (skip it).
    packages = data.get("packages")
    if isinstance(packages, dict):
        for key, entry in packages.items():
            if not key or not isinstance(entry, dict):
                continue
            name = _name_from_lock_key(key)
            version = entry.get("version")
            if name and isinstance(version, str):
                # A top-level install (key exactly node_modules/<name>) is the
                # authoritative version; do not let a nested copy overwrite it.
                is_top = key.count("node_modules/") == 1
                if is_top or name not in resolved:
                    resolved[name] = version
        if resolved:
            return resolved
    # v1: the recursive ``dependencies`` tree.
    _walk_v1(data.get("dependencies"), resolved)
    return resolved


def _walk_v1(deps, resolved: dict[str, str]) -> None:
    if not isinstance(deps, dict):
        return
    for name, entry in deps.items():
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if isinstance(version, str) and name not in resolved:
            resolved[name] = version
        _walk_v1(entry.get("dependencies"), resolved)


# A yarn.lock header line lists one or more "name@range" specs; the following
# indented block carries a `version "x.y.z"` line.
_YARN_HEADER = re.compile(r'^"?(@?[^@\s"]+(?:/[^@\s"]+)?)@')
_YARN_VERSION = re.compile(r'^\s+version:?\s+"?([^"\s]+)"?')


def _parse_yarn_lock(text: str) -> dict[str, str]:
    resolved: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if line and not line[0].isspace() and not line.startswith("#"):
            m = _YARN_HEADER.match(line.strip())
            current = m.group(1) if m else None
        elif current is not None:
            m = _YARN_VERSION.match(line)
            if m:
                resolved.setdefault(current, m.group(1))
                current = None
    return resolved


# A pnpm-lock.yaml packages key is `/name@version:` or `name@version:` (v9). The
# name may be scoped (@scope/name). Peer-suffixes like `(react@18)` are stripped.
_PNPM_KEY = re.compile(r"^\s{2}'?/?(@?[^@'\s]+(?:/[^@'\s]+)?)@([^():'\s]+)")


def _parse_pnpm_lock(text: str) -> dict[str, str]:
    resolved: dict[str, str] = {}
    in_packages = False
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("packages:"):
            in_packages = True
            continue
        if in_packages and stripped and not stripped[0].isspace():
            # A new top-level YAML block ends the packages section.
            in_packages = False
        if not in_packages:
            continue
        m = _PNPM_KEY.match(line)
        if m:
            resolved.setdefault(m.group(1), m.group(2))
    return resolved
