"""Solution manifest loader (``solution-explorer.solution/v1``).

The manifest is one human-authored YAML file that names a solution and lists its
member repositories. It replaces the legacy multi-repo ``--config`` JSON
(MULTI-REPO-DESIGN.md decision 2). Schema (one file):

    schema: solution-explorer.solution/v1     # required, exact
    name: UnaMentis                           # required, non-empty
    members:                                  # required, non-empty list
      - path: ../unamentis                    # local path (analyzed in M1)
        label: UnaMentis Server               # optional display label
        slug: server                          # optional; derived if absent
      - path: ../unamentis-ios
        label: UnaMentis iOS
      - url: https://github.com/org/web.git   # git URL member
        ref: main                             # optional pinned ref
        label: Web Client

A member needs EITHER a ``path`` (analyzed by the engine now) OR a ``url``
(parsed and stored, but NOT resolved in M1: remote clone is out of scope, so a
url-only member appears in the member index marked unresolved with a loud note).
A member with a ``path`` is analyzed; ``url``/``ref`` on the same member are
recorded as remote-origin metadata but the local path wins.

LOUD INDIVIDUAL REJECTION, exactly like the rules loader: a member that is
malformed (missing both path and url, bad slug, duplicate slug, wrong types) is
rejected loudly on stderr, named, and skipped; the rest of the solution still
composes. A structurally broken file (not a mapping, wrong schema string, no
usable members) is a hard error.

GRACEFUL DEGRADATION: PyYAML is the declared ``rules`` extra. When it is not
installed the loader emits one loud stderr line and exits non-zero (a solution
run cannot proceed without reading its manifest), mirroring the rules loader's
optional-import discipline but escalating because the manifest is mandatory input
rather than an optional overlay.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # PyYAML is the declared ``rules`` extra (see pyproject.toml).
    import yaml as _yaml
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    _yaml = None

__all__ = [
    "SOLUTION_SCHEMA",
    "Solution",
    "SolutionMember",
    "SolutionManifestError",
    "load_solution_manifest",
    "slugify",
]

# The exact schema discriminator the manifest must declare.
SOLUTION_SCHEMA = "solution-explorer.solution/v1"


class SolutionManifestError(Exception):
    """A structural failure that prevents the solution from composing at all."""


@dataclass
class SolutionMember:
    """One member repository, already validated.

    ``resolved`` is True when the member has a local ``path`` the engine can
    analyze in M1. A url-only member is parsed and stored (``url``/``ref`` kept)
    but ``resolved`` is False and ``unresolved_reason`` explains why.
    """

    slug: str
    label: str
    path: Optional[str] = None
    url: Optional[str] = None
    ref: Optional[str] = None
    resolved: bool = False
    unresolved_reason: Optional[str] = None


@dataclass
class Solution:
    """A loaded solution manifest: a name and an ordered member list."""

    name: str
    members: list[SolutionMember] = field(default_factory=list)
    manifest_path: Optional[Path] = None

    @property
    def resolved_members(self) -> list[SolutionMember]:
        return [m for m in self.members if m.resolved]


def slugify(value: str) -> str:
    """Reduce a label or path to a filesystem-safe, URL-safe directory slug.

    Lowercase, non-alphanumeric runs collapse to single hyphens, leading and
    trailing hyphens are stripped. Empty input yields an empty string so the
    caller can fall back to another source.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug


def _default_warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def _member_slug(entry: dict, warn: Callable[[str], None]) -> Optional[str]:
    """Derive a slug for a member from explicit slug, else label, else path/url."""
    explicit = entry.get("slug")
    if explicit is not None:
        if not isinstance(explicit, str) or not slugify(explicit):
            raise ValueError(f"slug {explicit!r} is not a usable string")
        # An explicit slug is honored verbatim after safety-slugifying it; warn
        # if slugifying changed it so the author can align the manifest.
        safe = slugify(explicit)
        if safe != explicit:
            warn(
                f"member slug '{explicit}' contains characters unsafe for a "
                f"directory name; using '{safe}'"
            )
        return safe
    # Prefer the path basename (the repo directory name is the natural, stable,
    # filesystem-safe slug, matching the folder-name convention), then the label,
    # then the url. Explicit slug above always wins.
    for source in (entry.get("path"), entry.get("label"), entry.get("url")):
        if isinstance(source, str):
            candidate = slugify(Path(source).name if source else "")
            if not candidate:
                candidate = slugify(source)
            if candidate:
                return candidate
    return None


def _build_member(entry: dict, warn: Callable[[str], None]) -> SolutionMember:
    """Validate one raw member mapping into a SolutionMember or raise ValueError."""
    if not isinstance(entry, dict):
        raise ValueError(f"member must be a mapping, got {type(entry).__name__}")

    path = entry.get("path")
    url = entry.get("url")
    if path is not None and not isinstance(path, str):
        raise ValueError("member 'path' must be a string")
    if url is not None and not isinstance(url, str):
        raise ValueError("member 'url' must be a string")
    if not path and not url:
        raise ValueError("member has neither a 'path' nor a 'url'")

    ref = entry.get("ref")
    if ref is not None and not isinstance(ref, str):
        raise ValueError("member 'ref' must be a string")

    label = entry.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError("member 'label' must be a string")

    slug = _member_slug(entry, warn)
    if not slug:
        raise ValueError("member has no usable slug (add a 'slug', 'label', or 'path')")

    display = label or slug
    resolved = bool(path)
    unresolved_reason = None
    if not resolved:
        unresolved_reason = (
            "git URL members are parsed and stored but not analyzed in M1; "
            "remote clone is out of scope (MULTI-REPO-DESIGN.md). Provide a local "
            "'path' to include this member in the composition."
        )
    return SolutionMember(
        slug=slug,
        label=display,
        path=path,
        url=url,
        ref=ref,
        resolved=resolved,
        unresolved_reason=unresolved_reason,
    )


def load_solution_manifest(
    manifest_path,
    *,
    warn: Callable[[str], None] = _default_warn,
) -> Solution:
    """Load and validate a solution manifest file into a :class:`Solution`.

    Bad individual members are rejected loudly and skipped; a file that is
    structurally unusable (unreadable, not a mapping, wrong schema, or with no
    valid members left after rejection) raises :class:`SolutionManifestError`.
    """
    manifest_path = Path(manifest_path)
    if _yaml is None:
        raise SolutionManifestError(
            "PyYAML is required to read a solution manifest but is not installed. "
            "Install the package with its 'rules' extra (pip install "
            "'solution-explorer[rules]') to enable multi-repo solutions."
        )
    if not manifest_path.is_file():
        raise SolutionManifestError(f"solution manifest not found: {manifest_path}")

    try:
        raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, _yaml.YAMLError) as exc:  # type: ignore[union-attr]
        raise SolutionManifestError(
            f"cannot read solution manifest {manifest_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise SolutionManifestError(
            f"solution manifest {manifest_path} must be a YAML mapping; got "
            f"{type(raw).__name__ if raw is not None else 'empty file'}"
        )

    schema = raw.get("schema")
    if schema != SOLUTION_SCHEMA:
        raise SolutionManifestError(
            f"solution manifest {manifest_path} has schema {schema!r}; "
            f"expected {SOLUTION_SCHEMA!r}"
        )

    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise SolutionManifestError(
            f"solution manifest {manifest_path} is missing a non-empty string 'name'"
        )

    raw_members = raw.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise SolutionManifestError(
            f"solution manifest {manifest_path} must have a non-empty 'members' list"
        )

    members: list[SolutionMember] = []
    seen_slugs: set[str] = set()
    for i, entry in enumerate(raw_members):
        try:
            member = _build_member(entry, warn)
        except ValueError as exc:
            warn(f"solution manifest {manifest_path}: rejecting member[{i}]: {exc}")
            continue
        if member.slug in seen_slugs:
            warn(
                f"solution manifest {manifest_path}: duplicate member slug "
                f"'{member.slug}'; keeping the first"
            )
            continue
        seen_slugs.add(member.slug)
        members.append(member)

    if not members:
        raise SolutionManifestError(
            f"solution manifest {manifest_path} has no valid members after rejecting "
            f"malformed entries"
        )

    return Solution(name=name, members=members, manifest_path=manifest_path)
