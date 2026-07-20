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
    # top_versions is the top-level install per name (the direct dep's version);
    # all_pairs is every distinct (name, version) present, so genuinely-installed
    # multiple versions of one package all survive (review finding 2).
    lock_name, top_versions, all_pairs = _read_lockfile(root, dirpath, filenames, result)
    lock_rel = join_rel(dirpath, lock_name) if lock_name else None

    for name in sorted(direct_declared):
        declared = direct_declared[name]
        version = top_versions.get(name)
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=declared, version=version,
            pin_status=classify_pin(ECOSYSTEM, declared), scope=SCOPE_DIRECT,
            purl=build_purl(ECOSYSTEM, name, version), evidence_file=pkg_rel,
            evidence_line=find_line(lines, f'"{name}"'),
        ))

    # Transitives: every distinct (name, version) the lockfile carries that is
    # not the exact direct pair already emitted above. A package that is direct at
    # one version AND present at another (nested) version surfaces both.
    if lock_rel is not None:
        for name, version in sorted(all_pairs):
            if name in direct_declared and top_versions.get(name) == version:
                continue
            result.dependencies.append(Dependency(
                ecosystem=ECOSYSTEM, name=name, declared=None, version=version,
                pin_status=PIN_EXACT if version else classify_pin(ECOSYSTEM, None),
                scope=SCOPE_TRANSITIVE,
                purl=build_purl(ECOSYSTEM, name, version), evidence_file=lock_rel,
            ))

    return result


def _read_lockfile(root: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    """Return ``(lockfile_name, top_versions, all_pairs)`` for the first lock.

    ``top_versions`` maps a package name to its TOP-LEVEL installed version (the
    version a direct dependency resolves to); ``all_pairs`` is the set of every
    distinct ``(name, version)`` present, so multiple installed versions of one
    package all survive to the collector (review finding 2). Returns
    ``(None, {}, set())`` when no lockfile sits beside package.json. A lockfile
    that cannot be parsed produces a loud warning and empty maps, so direct
    dependencies still list (without resolved versions) rather than vanishing.
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
            return lock_name, {}, set()
        try:
            if lock_name in ("package-lock.json", "npm-shrinkwrap.json"):
                top, pairs = _parse_npm_lock(text)
            elif lock_name == "yarn.lock":
                top, pairs = _parse_yarn_lock(text)
            else:
                top, pairs = _parse_pnpm_lock(text, lock_rel, result)
            return lock_name, top, pairs
        except (json.JSONDecodeError, ValueError) as exc:
            result.warnings.append(ParseWarning(ECOSYSTEM, lock_rel, f"invalid lockfile: {exc}"))
            return lock_name, {}, set()
    return None, {}, set()


def _name_from_lock_key(key: str) -> str:
    """The package name from a v2/v3 ``packages`` key (``node_modules/<name>``).

    Nested installs key on the full path (``node_modules/a/node_modules/b``); the
    installed name is the segment after the LAST ``node_modules/``.
    """
    if "node_modules/" in key:
        return key.rsplit("node_modules/", 1)[-1]
    return key


def _parse_npm_lock(text: str):
    data = json.loads(text)
    top: dict[str, str] = {}
    pairs: set[tuple[str, str]] = set()
    # v2/v3: the flat ``packages`` map. The root package is the "" key (skip it).
    packages = data.get("packages")
    if isinstance(packages, dict) and any(k for k in packages):
        for key, entry in packages.items():
            if not key or not isinstance(entry, dict):
                continue
            name = _name_from_lock_key(key)
            version = entry.get("version")
            if not name or not isinstance(version, str):
                continue
            pairs.add((name, version))
            # A top-level install is keyed exactly node_modules/<name> (one
            # occurrence of node_modules/); it is the direct dep's version.
            if key.count("node_modules/") == 1:
                top[name] = version
        return top, pairs
    # v1: the recursive ``dependencies`` tree. Top-level entries are direct.
    _walk_v1(data.get("dependencies"), top, pairs, is_top=True)
    return top, pairs


def _walk_v1(deps, top: dict, pairs: set, *, is_top: bool) -> None:
    if not isinstance(deps, dict):
        return
    for name, entry in deps.items():
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if isinstance(version, str):
            pairs.add((name, version))
            if is_top and name not in top:
                top[name] = version
        _walk_v1(entry.get("dependencies"), top, pairs, is_top=False)


# A yarn.lock header line lists one or more "name@range" specs; the following
# indented block carries a `version "x.y.z"` line.
_YARN_HEADER = re.compile(r'^"?(@?[^@\s"]+(?:/[^@\s"]+)?)@')
_YARN_VERSION = re.compile(r'^\s+version:?\s+"?([^"\s]+)"?')


def _parse_yarn_lock(text: str):
    # yarn.lock has no top-level/nested distinction, so the first version seen per
    # name is treated as its top version and every (name, version) is a pair.
    top: dict[str, str] = {}
    pairs: set[tuple[str, str]] = set()
    current: str | None = None
    for line in text.splitlines():
        if line and not line[0].isspace() and not line.startswith("#"):
            m = _YARN_HEADER.match(line.strip())
            current = m.group(1) if m else None
        elif current is not None:
            m = _YARN_VERSION.match(line)
            if m:
                pairs.add((current, m.group(1)))
                top.setdefault(current, m.group(1))
                current = None
    return top, pairs


# pnpm-lock.yaml packages keys come in two shapes:
#   v9  : `pkg@version:` or `/pkg@version:` (name may be scoped @scope/name)
#   v5/6: `/pkg/version:` or `/@scope/name/version:` (slash-separated)
# Peer suffixes like `(react@18)` are stripped by stopping at `(`.
_PNPM_KEY_AT = re.compile(r"^\s{2}'?/?(@?[^@'/\s][^@'\s]*?)@([^():'\s]+)")
_PNPM_KEY_SLASH = re.compile(r"^\s{2}'?/(@?[^/'\s]+(?:/[^/'\s]+)?)/([0-9][^:()'\s]*)")


def _parse_pnpm_lock(text: str, lock_rel: str, result: EcosystemResult):
    top: dict[str, str] = {}
    pairs: set[tuple[str, str]] = set()
    in_packages = False
    # Detect the lockfile format so an unrecognized older format warns loudly
    # instead of parsing to garbage (review finding 3).
    fmt = None  # "at" (v9) or "slash" (v5/6), decided by the first matching key.
    saw_package_line = False
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("packages:"):
            in_packages = True
            continue
        if in_packages and stripped and not stripped[0].isspace():
            in_packages = False
        if not in_packages or not stripped:
            continue
        # Only two-space-indented mapping keys are package entries.
        if not re.match(r"^\s{2}\S", line):
            continue
        saw_package_line = True
        if fmt is None:
            fmt = "slash" if _PNPM_KEY_SLASH.match(line) else "at"
        m = (_PNPM_KEY_SLASH if fmt == "slash" else _PNPM_KEY_AT).match(line)
        if m:
            name, version = m.group(1), m.group(2)
            pairs.add((name, version))
            top.setdefault(name, version)
    if saw_package_line and not pairs:
        # We entered the packages section but matched no key in either shape: an
        # unknown lockfile format. Warn rather than silently return nothing.
        result.warnings.append(ParseWarning(
            ECOSYSTEM, lock_rel,
            "unrecognized pnpm-lock.yaml package key format; no dependencies parsed",
        ))
    return top, pairs
