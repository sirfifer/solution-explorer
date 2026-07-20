"""Ruby / Bundler ecosystem: Gemfile plus Gemfile.lock.

Direct gems come from the Gemfile's ``gem`` declarations; resolved versions and
the transitive closure come from Gemfile.lock's ``GEM`` specs section. The Ruby
version pinned by a ``ruby`` directive surfaces as a target.
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
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "gem"

_GEM = re.compile(r"""^\s*gem\s+["']([^"']+)["']\s*(?:,\s*(.*))?$""")
_RUBY = re.compile(r"""^\s*ruby\s+["']([^"']+)["']""")
# A Gemfile.lock spec line: four-space indent, name, version in parens. A deeper
# indent is a sub-dependency of the line above and repeats a name already listed.
_LOCK_SPEC = re.compile(r"^    (\S+) \(([^)]+)\)")


def is_anchored(filenames: set[str]) -> bool:
    return "Gemfile" in filenames


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root
    rel = join_rel(dirpath, "Gemfile")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Gemfile")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return result
    lines = text.splitlines()

    direct: dict[str, str | None] = {}
    for lineno, raw in enumerate(lines, start=1):
        rm = _RUBY.match(raw)
        if rm:
            result.targets.append(Target(
                ecosystem=ECOSYSTEM, kind="ruby", label="Ruby runtime",
                constraint=rm.group(1), evidence_file=rel, evidence_line=lineno,
            ))
            continue
        gm = _GEM.match(raw)
        if gm:
            name = gm.group(1)
            constraint = _first_version(gm.group(2))
            direct.setdefault(name, constraint)

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


def _first_version(tail: str | None) -> str | None:
    """The first quoted version requirement after a gem name, or None.

    A gem line may carry several requirements (``'>= 1.0', '< 2.0'``) and options
    (``require: false``). We keep the first version-shaped string as the declared
    constraint; options are ignored.
    """
    if not tail:
        return None
    parts = re.findall(r"""["']([^"']+)["']""", tail)
    for part in parts:
        if re.search(r"\d", part) or part.startswith(("~>", ">", "<", "=")):
            return part
    return None


def _read_lock(base: Path, dirpath: str, filenames: set[str], result: EcosystemResult):
    if "Gemfile.lock" not in filenames:
        return None, {}
    rel = join_rel(dirpath, "Gemfile.lock")
    result.manifests.append(rel)
    try:
        text = read_text(base / "Gemfile.lock")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return rel, {}
    resolved: dict[str, str] = {}
    in_specs = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped == "specs:":
            in_specs = True
            continue
        if in_specs:
            # A non-indented line (a new lock section header) ends the specs list.
            if raw and not raw[0].isspace():
                in_specs = False
                continue
            m = _LOCK_SPEC.match(raw)
            if m:
                resolved.setdefault(m.group(1), m.group(2))
    return rel, resolved
