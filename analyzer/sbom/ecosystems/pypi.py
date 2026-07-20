"""Python / PyPI ecosystem: pyproject.toml, requirements*.txt, poetry.lock.

Direct dependencies come from three deterministic sources, any or all of which a
Python project may carry:

  - PEP 621 ``[project].dependencies`` and ``[project.optional-dependencies]``
    (PEP 508 requirement strings);
  - Poetry's ``[tool.poetry.dependencies]`` and group dependencies;
  - ``requirements*.txt`` pinned or constrained lists.

Resolved versions and the transitive closure come from ``poetry.lock`` when it is
present. ``requires-python`` surfaces as a target, never as a dependency. Names
are PEP 503 normalized for the purl (lowercase, ``_`` and ``.`` to ``-``).
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
from . import _toml
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "pypi"

# A PEP 508 requirement: a name, optional extras, a version specifier, and an
# optional environment marker. We keep the name and the specifier; markers and
# extras do not change what package is depended on.
_REQ = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$"
)


def is_anchored(filenames: set[str]) -> bool:
    if "pyproject.toml" in filenames:
        return True
    return any(_is_requirements(f) for f in filenames)


def _is_requirements(filename: str) -> bool:
    low = filename.lower()
    return low.startswith("requirements") and low.endswith(".txt")


def collect(root: Path, dirpath: str, filenames: set[str]) -> EcosystemResult:
    result = EcosystemResult(ecosystem=ECOSYSTEM)
    base = root / dirpath if dirpath else root

    # A name may be declared in more than one place (pyproject and a requirements
    # file); the first declaration wins so we never double-count a direct dep.
    direct: dict[str, Dependency] = {}

    if "pyproject.toml" in filenames:
        _parse_pyproject(base, dirpath, result, direct)

    for filename in sorted(f for f in filenames if _is_requirements(f)):
        _parse_requirements(base, dirpath, filename, result, direct)

    # poetry.lock supplies resolved versions and the transitive set.
    resolved: dict[str, str] = {}
    lock_rel: str | None = None
    if "poetry.lock" in filenames:
        lock_rel, resolved = _parse_poetry_lock(base, dirpath, result)

    for name in sorted(direct):
        dep = direct[name]
        version = resolved.get(_canon(name))
        if version is not None:
            dep.version = version
            dep.purl = build_purl(ECOSYSTEM, name, version)
        result.dependencies.append(dep)

    if lock_rel is not None:
        direct_canon = {_canon(n) for n in direct}
        for canon in sorted(resolved):
            if canon in direct_canon:
                continue
            version = resolved[canon]
            result.dependencies.append(Dependency(
                ecosystem=ECOSYSTEM, name=canon, declared=None, version=version,
                pin_status=PIN_EXACT if version else classify_pin(ECOSYSTEM, None),
                scope=SCOPE_TRANSITIVE,
                purl=build_purl(ECOSYSTEM, canon, version), evidence_file=lock_rel,
            ))

    return result


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_pyproject(base: Path, dirpath: str, result: EcosystemResult, direct: dict) -> None:
    rel = join_rel(dirpath, "pyproject.toml")
    result.manifests.append(rel)
    try:
        text = read_text(base / "pyproject.toml")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return
    try:
        data = _toml.load(text)
    except _toml.TomlUnavailable as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, str(exc)))
        return
    except _toml.TomlError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid TOML: {exc}"))
        return

    lines = text.splitlines()
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    poetry = (
        data.get("tool", {}).get("poetry", {})
        if isinstance(data.get("tool"), dict)
        else {}
    )

    # requires-python target (PEP 621), or the poetry python constraint.
    requires_python = project.get("requires-python")
    if isinstance(requires_python, str) and requires_python.strip():
        result.targets.append(Target(
            ecosystem=ECOSYSTEM, kind="python", label="Python runtime",
            constraint=requires_python.strip(), evidence_file=rel,
            evidence_line=find_line(lines, "requires-python"),
        ))
    elif isinstance(poetry.get("dependencies"), dict):
        py = poetry["dependencies"].get("python")
        if isinstance(py, str) and py.strip():
            result.targets.append(Target(
                ecosystem=ECOSYSTEM, kind="python", label="Python runtime",
                constraint=py.strip(), evidence_file=rel,
                evidence_line=find_line(lines, "python"),
            ))

    # PEP 621 dependencies (a list of PEP 508 strings).
    for spec in project.get("dependencies", []) or []:
        if isinstance(spec, str):
            _add_pep508(spec, rel, lines, direct)
    # PEP 621 optional-dependencies (a dict of extra name -> list of specs).
    opt = project.get("optional-dependencies")
    if isinstance(opt, dict):
        for specs in opt.values():
            for spec in specs or []:
                if isinstance(spec, str):
                    _add_pep508(spec, rel, lines, direct)

    # Poetry dependencies (a dict of name -> constraint or table). python is the
    # runtime target, handled above, not a package.
    _add_poetry_deps(poetry.get("dependencies"), rel, lines, direct)
    groups = poetry.get("group")
    if isinstance(groups, dict):
        for group in groups.values():
            if isinstance(group, dict):
                _add_poetry_deps(group.get("dependencies"), rel, lines, direct)


def _add_pep508(spec: str, rel: str, lines: list[str], direct: dict) -> None:
    # Strip an environment marker; it constrains WHEN a dep applies, not which.
    core = spec.split(";", 1)[0].strip()
    if not core:
        return
    # A direct URL reference (name @ url) has no version constraint.
    if "@" in core:
        name = core.split("@", 1)[0].strip()
        url = core.split("@", 1)[1].strip()
        _record(name, url, None, rel, lines, direct, unpinned=True)
        return
    m = _REQ.match(core)
    if not m:
        return
    name = m.group(1)
    constraint = m.group(2).strip()
    _record(name, constraint or None, None, rel, lines, direct)


def _add_poetry_deps(deps, rel: str, lines: list[str], direct: dict) -> None:
    if not isinstance(deps, dict):
        return
    for name, value in deps.items():
        if name == "python":
            continue
        if isinstance(value, str):
            _record(name, value, None, rel, lines, direct)
        elif isinstance(value, dict):
            constraint = value.get("version")
            if isinstance(constraint, str):
                _record(name, constraint, None, rel, lines, direct)
            else:
                # A git/path poetry dependency: no version, unpinned.
                ref = value.get("git") or value.get("path") or value.get("url") or ""
                _record(name, ref or None, None, rel, lines, direct, unpinned=True)


def _record(name, constraint, version, rel, lines, direct, *, unpinned=False):
    if not name or name in direct:
        return
    from ..models import PIN_UNPINNED

    pin = PIN_UNPINNED if unpinned else classify_pin(ECOSYSTEM, constraint)
    direct[name] = Dependency(
        ecosystem=ECOSYSTEM, name=name, declared=constraint, version=version,
        pin_status=pin, scope=SCOPE_DIRECT,
        purl=build_purl(ECOSYSTEM, name, None), evidence_file=rel,
        evidence_line=find_line(lines, name),
    )


def _parse_requirements(base: Path, dirpath: str, filename: str, result: EcosystemResult, direct: dict) -> None:
    rel = join_rel(dirpath, filename)
    result.manifests.append(rel)
    try:
        text = read_text(base / filename)
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            # Blank, comment, or an option line (-r, -e, --hash); not a package.
            continue
        # Drop an inline comment and any environment marker.
        line = line.split(" #", 1)[0].split(";", 1)[0].strip()
        if not line or "@" in line and line.split("@", 1)[0].strip() and " " in line:
            # A direct URL requirement (name @ url): record unpinned.
            name = line.split("@", 1)[0].strip()
            if name:
                _record_at_line(name, None, rel, lineno, direct, unpinned=True)
            continue
        m = _REQ.match(line)
        if not m:
            continue
        name = m.group(1)
        constraint = m.group(2).strip()
        _record_at_line(name, constraint or None, rel, lineno, direct)


def _record_at_line(name, constraint, rel, lineno, direct, *, unpinned=False):
    if not name or name in direct:
        return
    from ..models import PIN_UNPINNED

    pin = PIN_UNPINNED if unpinned else classify_pin(ECOSYSTEM, constraint)
    direct[name] = Dependency(
        ecosystem=ECOSYSTEM, name=name, declared=constraint, version=None,
        pin_status=pin, scope=SCOPE_DIRECT,
        purl=build_purl(ECOSYSTEM, name, None), evidence_file=rel, evidence_line=lineno,
    )


def _parse_poetry_lock(base: Path, dirpath: str, result: EcosystemResult):
    rel = join_rel(dirpath, "poetry.lock")
    result.manifests.append(rel)
    try:
        text = read_text(base / "poetry.lock")
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"unreadable: {exc}"))
        return rel, {}
    try:
        data = _toml.load(text)
    except _toml.TomlUnavailable as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, str(exc)))
        return rel, {}
    except _toml.TomlError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel, f"invalid TOML: {exc}"))
        return rel, {}
    resolved: dict[str, str] = {}
    for pkg in data.get("package", []) or []:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name")
        version = pkg.get("version")
        if isinstance(name, str) and isinstance(version, str):
            resolved[_canon(name)] = version
    return rel, resolved
