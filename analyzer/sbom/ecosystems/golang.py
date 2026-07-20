"""Go modules ecosystem: go.mod (plus go.sum for checksum evidence).

go.mod carries the complete module graph: every ``require`` names a module and
its single resolved version (Go pins exactly, always), and a ``// indirect``
comment marks a transitive requirement. The ``go`` directive is the language
target. ``replace`` directives are APPLIED (review finding 6): a replaced module
reports the replacement target and version, with the original recorded in
evidence, so the SBOM never silently reports a pre-replacement module. go.sum,
when present, is noted as evidence but adds no new versions (it holds checksums
for the versions go.mod already names).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import (
    PIN_EXACT,
    PIN_UNPINNED,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    EcosystemResult,
    ParseWarning,
    Target,
)
from ..purl import build_purl
from ._common import join_rel, read_text

ECOSYSTEM = "golang"

_GO_DIRECTIVE = re.compile(r"^go\s+([0-9][0-9.]*)")
_TOOLCHAIN = re.compile(r"^toolchain\s+(\S+)")
# A require entry: module, version, optional `// indirect`. Works for the single
# `require x v1` form (after the leading `require ` is stripped) and block lines.
_REQUIRE = re.compile(r"^(\S+)\s+(\S+)(\s*//\s*indirect)?")
# A replace entry: `old [ver] => new [ver]`. The old version is optional.
_REPLACE = re.compile(r"^(\S+)(?:\s+(\S+))?\s+=>\s+(\S+)(?:\s+(\S+))?")


def is_anchored(filenames: set[str]) -> bool:
    return "go.mod" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root
    rel = join_rel(dirpath, "go.mod")
    result.manifests.append(rel)
    try:
        text = read_text(base / "go.mod")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return result
    if "go.sum" in filenames:
        result.manifests.append(join_rel(dirpath, "go.sum"))

    # Collect requires and replaces in one pass, then apply replaces at the end
    # (a replace can textually precede or follow its require).
    requires: list[tuple[str, str, bool, int]] = []  # name, version, indirect, line
    replaces: dict[str, tuple[str, str | None]] = {}  # old -> (new_target, new_version)

    block: str | None = None  # "require" or "replace" when inside a ( ) block
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        # Strip a trailing line comment except the meaningful `// indirect`.
        if not line or (line.startswith("//") and "indirect" not in line):
            continue

        m = _GO_DIRECTIVE.match(line)
        if m:
            result.targets.append(Target(
                ecosystem=ECOSYSTEM, kind="go", label="Go language version",
                constraint=m.group(1), evidence_file=rel, evidence_line=lineno,
            ))
            continue
        m = _TOOLCHAIN.match(line)
        if m:
            result.targets.append(Target(
                ecosystem=ECOSYSTEM, kind="go-toolchain", label="Go toolchain",
                constraint=m.group(1), evidence_file=rel, evidence_line=lineno,
            ))
            continue

        if line.startswith("require (") or line == "require (":
            block = "require"
            continue
        if line.startswith("replace (") or line == "replace (":
            block = "replace"
            continue
        if block is not None and line == ")":
            block = None
            continue

        # Single-line forms carry their keyword; block lines do not.
        if line.startswith("require "):
            _scan_require(line[len("require "):], lineno, requires)
        elif line.startswith("replace "):
            _scan_replace(line[len("replace "):], replaces)
        elif block == "require":
            _scan_require(line, lineno, requires)
        elif block == "replace":
            _scan_replace(line, replaces)

    for name, version, indirect, lineno in requires:
        _emit(result, rel, lineno, name, version, indirect, replaces)

    return result


def _scan_require(body: str, lineno: int, requires: list) -> None:
    m = _REQUIRE.match(body.strip())
    if not m or m.group(1).startswith("//"):
        return
    requires.append((m.group(1), m.group(2), bool(m.group(3)), lineno))


def _scan_replace(body: str, replaces: dict) -> None:
    m = _REPLACE.match(body.strip())
    if not m:
        return
    old = m.group(1)
    new_target = m.group(3)
    new_version = m.group(4)
    replaces[old] = (new_target, new_version)


def _emit(result, rel, lineno, name, version, indirect, replaces) -> None:
    if not name:
        return
    scope = SCOPE_TRANSITIVE if indirect else SCOPE_DIRECT
    replacement = replaces.get(name)
    if replacement is None:
        result.dependencies.append(Dependency(
            ecosystem=ECOSYSTEM, name=name, declared=version, version=version,
            pin_status=PIN_EXACT if version else PIN_UNPINNED, scope=scope,
            purl=build_purl(ECOSYSTEM, name, version), evidence_file=rel,
            evidence_line=lineno,
        ))
        return

    new_target, new_version = replacement
    # A local-path replacement (./fork or ../fork) has no resolvable version.
    is_local = new_target.startswith((".", "/"))
    resolved = None if is_local else new_version
    # The declared string records the full mapping (original => replacement) so the
    # replacement is never silent and the original module stays visible as evidence.
    declared = f"{name} {version} => {new_target} {new_version or ''}".strip()
    result.dependencies.append(Dependency(
        ecosystem=ECOSYSTEM, name=new_target, declared=declared,
        version=resolved,
        pin_status=PIN_UNPINNED if (is_local or not resolved) else PIN_EXACT,
        scope=scope,
        purl=None if is_local else build_purl(ECOSYSTEM, new_target, resolved),
        evidence_file=rel, evidence_line=lineno,
    ))
