"""Go modules ecosystem: go.mod (plus go.sum for checksum evidence).

go.mod carries the complete module graph: every ``require`` names a module and
its single resolved version (Go pins exactly, always), and a ``// indirect``
comment marks a transitive requirement. The ``go`` directive is the language
target. go.sum, when present, is noted as evidence but adds no new versions (it
holds checksums for the versions go.mod already names).
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
    Target,
)
from ..purl import build_purl, classify_pin
from ._common import join_rel, read_text

ECOSYSTEM = "golang"

_GO_DIRECTIVE = re.compile(r"^go\s+([0-9][0-9.]*)")
_TOOLCHAIN = re.compile(r"^toolchain\s+(\S+)")
_REQUIRE_ONE = re.compile(r"^require\s+(\S+)\s+(\S+)(\s*//\s*indirect)?")
_REQUIRE_LINE = re.compile(r"^\s*(\S+)\s+(\S+)(\s*//\s*indirect)?")


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

    in_require_block = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
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

        if line.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue

        if in_require_block:
            rm = _REQUIRE_LINE.match(raw)
            if rm:
                _add(result, rel, lineno, rm)
        else:
            rm = _REQUIRE_ONE.match(line)
            if rm:
                _add(result, rel, lineno, rm)

    return result


def _add(result: EcosystemResult, rel: str, lineno: int, m: re.Match) -> None:
    name = m.group(1)
    version = m.group(2)
    indirect = bool(m.group(3))
    if not name or name.startswith("//"):
        return
    result.dependencies.append(Dependency(
        ecosystem=ECOSYSTEM, name=name, declared=version, version=version,
        pin_status=PIN_EXACT if version else classify_pin(ECOSYSTEM, version),
        scope=SCOPE_TRANSITIVE if indirect else SCOPE_DIRECT,
        purl=build_purl(ECOSYSTEM, name, version), evidence_file=rel, evidence_line=lineno,
    ))
