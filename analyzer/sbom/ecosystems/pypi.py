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
    PIN_UNPINNED,
    SCOPE_DIRECT,
    SCOPE_TRANSITIVE,
    Dependency,
    EcosystemResult,
    ParseWarning,
    Target,
)
from ..purl import build_purl, classify_pin, exact_version
from . import _toml
from ._common import find_line, join_rel, read_text

ECOSYSTEM = "pypi"

# How deep to follow requirements `-r`/`-R` includes before giving up (cycle and
# runaway guard). Real requirement trees are shallow; 16 is generous.
_MAX_INCLUDE_DEPTH = 16

# A VCS editable line: `-e git+https://host/x.git@ref#egg=name`. The egg name (or
# the repo tail) is the package name, and the ref after @ (when present) pins it.
_EDITABLE_VCS = re.compile(r"^(?:-e|--editable)\s+(.+)$")
_EGG_NAME = re.compile(r"[#&]egg=([A-Za-z0-9._-]+)")

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

    visited: set = set()
    for filename in sorted(f for f in filenames if _is_requirements(f)):
        _parse_requirements(root, join_rel(dirpath, filename), result, direct, visited=visited)

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
    _record_dep(
        name, constraint, version, rel, find_line(lines, name),
        direct, unpinned=unpinned,
    )


def _record_at_line(name, constraint, rel, lineno, direct, *, unpinned=False, version=None):
    _record_dep(name, constraint, version, rel, lineno, direct, unpinned=unpinned)


def _record_dep(name, constraint, version, rel, lineno, direct, *, unpinned=False):
    """Record one direct dependency, recovering an exact version when pinned.

    When no version is supplied but the constraint is an exact `==`/`===`/bare
    pin, the concrete version is recovered (review finding 5) so an exact
    requirements.txt line carries a resolved version and a versioned purl.
    """
    if not name or name in direct:
        return
    pin = PIN_UNPINNED if unpinned else classify_pin(ECOSYSTEM, constraint)
    # Recover a resolved version only when the pin is genuinely exact (`==2.3.0`),
    # never from a bare poetry value that is really a caret range (finding 5).
    if version is None and pin == PIN_EXACT:
        version = exact_version(constraint)
    direct[name] = Dependency(
        ecosystem=ECOSYSTEM, name=name, declared=constraint, version=version,
        pin_status=pin, scope=SCOPE_DIRECT,
        purl=build_purl(ECOSYSTEM, name, version), evidence_file=rel,
        evidence_line=lineno,
    )


def _parse_requirements(
    root: Path,
    rel_path: str,
    result: EcosystemResult,
    direct: dict,
    *,
    visited: set | None = None,
    depth: int = 0,
) -> None:
    """Parse one requirements file, following `-r` includes and `-e` editables.

    ``rel_path`` is the file's path relative to the scan ``root``.
    ``-r``/``--requirement`` includes are followed relative to the including file
    (review finding 7), bounded by ``_MAX_INCLUDE_DEPTH`` and de-duplicated via
    ``visited`` so a cycle cannot loop. A missing include target is a loud
    warning, never a silent drop. ``-e``/``--editable`` VCS lines are recorded as
    components pinned to their ref (or unpinned with the URL as evidence); a local
    ``-e .`` editable is the project itself and is skipped.
    """
    if visited is None:
        visited = set()
    if rel_path in visited:
        return
    visited.add(rel_path)
    result.manifests.append(rel_path)
    try:
        text = read_text(root / rel_path)
    except OSError as exc:
        result.warnings.append(ParseWarning(ECOSYSTEM, rel_path, f"unreadable: {exc}"))
        return
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # `-r other.txt` / `--requirement other.txt`: follow the include.
        inc = re.match(r"^(?:-r|--requirement)[=\s]+(\S+)", line)
        if inc:
            _follow_include(root, rel_path, inc.group(1), result, direct, visited, depth)
            continue

        # `-e`/`--editable` VCS editable: record as a component.
        edit = _EDITABLE_VCS.match(line)
        if edit:
            _record_editable(edit.group(1).strip(), rel_path, lineno, direct)
            continue

        # Any other option line (-c, --hash, --index-url, ...): not a package.
        if line.startswith("-"):
            continue

        # Drop an inline comment and any environment marker.
        line = line.split(" #", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        # A direct URL requirement (name @ url): record unpinned.
        if "@" in line and line.split("@", 1)[0].strip() and " " in line:
            name = line.split("@", 1)[0].strip()
            if name:
                _record_at_line(name, None, rel_path, lineno, direct, unpinned=True)
            continue
        m = _REQ.match(line)
        if not m:
            continue
        name = m.group(1)
        constraint = m.group(2).strip()
        _record_at_line(name, constraint or None, rel_path, lineno, direct)


def _follow_include(root, including_rel, target, result, direct, visited, depth):
    """Resolve and parse a `-r` include relative to the including file."""
    import posixpath

    if depth >= _MAX_INCLUDE_DEPTH:
        result.warnings.append(ParseWarning(
            ECOSYSTEM, including_rel,
            f"requirements include depth limit reached at '{target}'",
        ))
        return
    # The include is relative to the including file's own directory.
    target = target.replace("\\", "/")
    including_dir = posixpath.dirname(including_rel)
    joined = posixpath.normpath(posixpath.join(including_dir, target))
    # Never escape the scan root; a leading .. is clamped to root-relative.
    joined = joined.lstrip("/").lstrip("./") if joined.startswith(("/", "./")) else joined
    while joined.startswith("../"):
        joined = joined[3:]
    inc_path = root / joined
    if not inc_path.is_file():
        result.warnings.append(ParseWarning(
            ECOSYSTEM, including_rel,
            f"requirements include not found: '{target}'",
        ))
        return
    _parse_requirements(root, joined, result, direct, visited=visited, depth=depth + 1)


def _record_editable(spec: str, rel: str, lineno: int, direct: dict) -> None:
    """Record a `-e`/`--editable` requirement.

    A VCS editable (``git+https://.../x.git@ref#egg=name``) becomes a component
    named by its egg or repo tail, pinned to the ref after ``@`` when present. A
    local editable (``-e .`` or ``-e ./pkg``) is the project itself, not a
    third-party dependency, so it is skipped.
    """
    core = spec.split(" #", 1)[0].strip()
    is_vcs = bool(re.match(r"^(?:git|hg|svn|bzr)\+", core)) or core.startswith(
        ("git+", "https://", "http://")
    )
    if not is_vcs:
        # A local path editable is the project being built, not a dependency.
        return
    egg = _EGG_NAME.search(core)
    url_no_frag = core.split("#", 1)[0]
    # A ref after the LAST @ (but not the scheme's `git@host`) pins the checkout.
    ref = None
    body = re.sub(r"^\w+\+", "", url_no_frag)
    if "@" in body.rsplit("/", 1)[-1]:
        ref = body.rsplit("@", 1)[1]
    if egg:
        name = egg.group(1)
    else:
        tail = url_no_frag.rstrip("/").rsplit("/", 1)[-1]
        name = re.sub(r"\.git$", "", tail).split("@", 1)[0]
    if not name or name in direct:
        return
    direct[name] = Dependency(
        ecosystem=ECOSYSTEM, name=name, declared=core, version=ref,
        pin_status=PIN_EXACT if ref else PIN_UNPINNED, scope=SCOPE_DIRECT,
        purl=build_purl(ECOSYSTEM, name, ref), evidence_file=rel, evidence_line=lineno,
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
