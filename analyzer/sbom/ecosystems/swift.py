"""Swift Package Manager ecosystem: Package.swift plus Package.resolved.

Package.swift is Swift source; direct dependencies are read with regexes over its
``.package(url:...)`` declarations (the deterministic shapes SPM accepts: from,
exact, branch, revision, and range constraints). Package.resolved (a JSON pin
file) supplies resolved versions and the full resolved set including transitives.
``swift-tools-version`` from the manifest's first line surfaces as a target.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..models import (
    PIN_EXACT,
    PIN_RANGE,
    PIN_UNPINNED,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    EcosystemResult,
    ParseWarning,
    Target,
)
from ..purl import build_purl
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "swift"

_TOOLS_VERSION = re.compile(r"//\s*swift-tools-version:\s*([0-9][0-9.]*)")
# A .package(...) call; we capture the url and the whole argument tail so the
# constraint shape (from/exact/branch/range) can be classified.
_PACKAGE = re.compile(r"\.package\s*\(([^)]*)\)", re.DOTALL)
_URL = re.compile(r'url:\s*"([^"]+)"')
_EXACT = re.compile(r'(?:exact:|\.exact\()\s*"([^"]+)"')
_FROM = re.compile(r'from:\s*"([^"]+)"')
_BRANCH = re.compile(r'(?:branch:|\.branch\()\s*"([^"]+)"')
_REVISION = re.compile(r'(?:revision:|\.revision\()\s*"([^"]+)"')


def is_anchored(filenames: set[str]) -> bool:
    return "Package.swift" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root
    rel = join_rel(dirpath, "Package.swift")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Package.swift")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return result
    lines = text.splitlines()

    tv = _TOOLS_VERSION.search(text)
    if tv:
        result.targets.append(Target(
            ecosystem=ECOSYSTEM, kind="swift-tools", label="Swift tools version",
            constraint=tv.group(1), evidence_file=rel,
            evidence_line=find_line(lines, "swift-tools-version"),
        ))

    resolved, resolved_rel = _read_resolved(base, dirpath, filenames, result)

    direct_ids: set[str] = set()
    for m in _PACKAGE.finditer(text):
        args = m.group(1)
        url_m = _URL.search(args)
        if not url_m:
            continue
        url = url_m.group(1)
        name = _identity_from_url(url)
        direct_ids.add(name)
        declared, pin = _classify_swift(args)
        version = resolved.get(name)
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=declared, version=version,
            pin_status=pin, scope=SCOPE_DIRECT,
            purl=build_purl(ECOSYSTEM, _purl_path(url), version), evidence_file=rel,
            evidence_line=find_line(lines, url),
        ))

    if resolved_rel is not None:
        for name in sorted(resolved):
            if name in direct_ids:
                continue
            version = resolved[name]
            result.dependencies.append(Dependency(
                ecosystem=ECOSYSTEM, name=name, declared=None, version=version,
                pin_status=PIN_EXACT if version else PIN_UNPINNED,
                scope=SCOPE_TRANSITIVE,
                purl=build_purl(ECOSYSTEM, name, version), evidence_file=resolved_rel,
            ))

    return result


def _classify_swift(args: str):
    """Return ``(declared, pin_status)`` for one .package() call's arguments."""
    m = _EXACT.search(args)
    if m:
        return m.group(1), PIN_EXACT
    m = _FROM.search(args)
    if m:
        # from: is a >= up to the next major: a range.
        return f"from: {m.group(1)}", PIN_RANGE
    m = _BRANCH.search(args)
    if m:
        return f"branch: {m.group(1)}", PIN_UNPINNED
    m = _REVISION.search(args)
    if m:
        # A pinned commit revision is an exact, immutable pin.
        return f"revision: {m.group(1)}", PIN_EXACT
    if ".." in args:
        return "range", PIN_RANGE
    return None, PIN_UNPINNED


def _identity_from_url(url: str) -> str:
    """The SPM package identity: the last path component, minus a .git suffix."""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    return tail.lower()


def _purl_path(url: str) -> str:
    """host/owner/repo for the swift purl, from a git URL (best effort)."""
    stripped = re.sub(r"^\w+://", "", url)
    stripped = re.sub(r"^git@", "", stripped).replace(":", "/")
    if stripped.endswith(".git"):
        stripped = stripped[:-4]
    return stripped.rstrip("/")


def _read_resolved(base: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    if "Package.resolved" not in filenames:
        return {}, None
    rel = join_rel(dirpath, "Package.resolved")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Package.resolved")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return {}, rel
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid JSON: {exc}"))
        return {}, rel
    resolved: dict[str, str] = {}
    # v2/v3: top-level "pins"; v1: "object": {"pins": [...]}.
    pins = data.get("pins")
    if pins is None and isinstance(data.get("object"), dict):
        pins = data["object"].get("pins")
    for pin in pins or []:
        if not isinstance(pin, dict):
            continue
        # v2/v3 use "identity"; v1 uses "package".
        identity = pin.get("identity") or pin.get("package")
        state = pin.get("state") if isinstance(pin.get("state"), dict) else {}
        version = state.get("version")
        if isinstance(identity, str) and isinstance(version, str):
            resolved[identity.lower()] = version
    return resolved, rel
