"""Package URL (purl) construction and per-ecosystem version-pin classification.

Two deterministic, text-only concerns live here so the ecosystem parsers stay
focused on reading their file format:

  - ``build_purl``: a package URL (https://github.com/package-url/purl-spec) for a
    dependency when one is derivable. purl is the SBOM interchange identifier
    (``pkg:npm/left-pad@1.3.0``, ``pkg:pypi/requests@2.31.0``). Names are
    normalized per the ecosystem's rules: npm and pypi lowercase (and pypi
    collapses underscores to hyphens per PEP 503), scoped npm namespaces are
    percent-encoded. When no version is resolved the purl carries just the name
    (still a valid identifier).
  - ``classify_pin``: map a declared version constraint to exact-pinned / range /
    unpinned using the SEMANTICS OF THAT ECOSYSTEM, because a bare ``1.2.3`` means
    an exact pin in npm but a caret range in Cargo. Getting this per-ecosystem is
    the difference between an honest pin report and a misleading one.

No network, no package-manager execution: classification reads the constraint
string only.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from .models import PIN_EXACT, PIN_RANGE, PIN_UNPINNED

__all__ = ["build_purl", "classify_pin", "normalize_name", "exact_version"]

# A constraint that names no version at all: empty, a wildcard, or a "give me
# whatever is newest" tag. Common to every ecosystem.
_UNPINNED_TOKENS = frozenset({"", "*", "x", "latest", "any", "*.*.*"})

# A reference that resolves through a VCS or the filesystem rather than a version
# range. We cannot pin these to a version deterministically, so they read as
# unpinned regardless of the ecosystem. Matched as a prefix on the raw constraint.
_NON_VERSION_PREFIXES = (
    "git+", "git:", "github:", "gitlab:", "bitbucket:", "file:", "link:",
    "path:", "http://", "https://", "workspace:", "npm:", "portal:",
)


def normalize_name(ecosystem: str, name: str) -> str:
    """Normalize a package name for its purl per the purl-spec ecosystem rules.

    npm and pypi are case-insensitive and lowercased; pypi additionally
    normalizes runs of ``_``, ``-``, and ``.`` to a single hyphen (PEP 503).
    nuget lowercases. Everything else is left verbatim, because module paths
    (golang) and pod names are case-sensitive.
    """
    if ecosystem in ("npm", "nuget"):
        return name.lower()
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", name).lower()
    return name


def build_purl(ecosystem: str, name: str, version: str | None) -> str | None:
    """Return a package URL for the dependency, or None when not derivable.

    The version, when present, is appended as ``@<version>``. Scoped npm names
    (``@scope/pkg``) split into a percent-encoded namespace and a name, per the
    purl npm rules. An empty name yields no purl.
    """
    if not name:
        return None
    norm = normalize_name(ecosystem, name)
    ver = f"@{quote(version, safe='')}" if version else ""

    if ecosystem == "npm" and norm.startswith("@") and "/" in norm:
        scope, _, pkg = norm.partition("/")
        # The leading @ is part of the namespace and must be percent-encoded
        # (%40) so the purl parses; the name segment keeps its own encoding.
        ns = quote(scope, safe="")
        return f"pkg:npm/{ns}/{quote(pkg, safe='')}{ver}"

    if ecosystem in ("npm", "pypi", "cargo", "gem", "nuget", "cocoapods"):
        return f"pkg:{ecosystem}/{quote(norm, safe='')}{ver}"

    if ecosystem == "golang":
        # A go module path is the purl namespace + name; keep the slashes so the
        # host and path segments survive (pkg:golang/github.com/gorilla/mux).
        return f"pkg:golang/{quote(norm, safe='/')}{ver}"

    if ecosystem == "swift":
        # A Swift package is identified by its source location. The caller passes
        # the repository path (host/owner/repo) as the name when it has one.
        return f"pkg:swift/{quote(norm, safe='/')}{ver}"

    return None


def classify_pin(ecosystem: str, constraint: str | None) -> str:
    """Classify a declared constraint as exact-pinned, range, or unpinned.

    ``constraint`` is the version string exactly as the manifest declares it. A
    missing or wildcard constraint is unpinned; a VCS/path/url reference is
    unpinned (no deterministic version). Otherwise the ecosystem's own syntax
    decides: a bare ``1.2.3`` is exact in npm/pypi-loose/nuget but a caret range
    in Cargo, so each family is handled explicitly.
    """
    if constraint is None:
        return PIN_UNPINNED
    raw = constraint.strip()
    lowered = raw.lower()
    if lowered in _UNPINNED_TOKENS:
        return PIN_UNPINNED
    if any(lowered.startswith(p) for p in _NON_VERSION_PREFIXES):
        return PIN_UNPINNED

    if ecosystem in ("npm", "cocoapods"):
        return _classify_semver(raw, bare_is_exact=True)
    if ecosystem == "cargo":
        # Cargo treats a bare "1.2.3" as "^1.2.3" (a caret range); only an
        # explicit "=1.2.3" is an exact pin.
        return _classify_semver(raw, bare_is_exact=False)
    if ecosystem == "pypi":
        return _classify_pypi(raw)
    if ecosystem == "gem":
        return _classify_ruby(raw)
    if ecosystem == "golang":
        # go.mod requirements are always a single resolved version (vX.Y.Z);
        # the module graph is fully pinned by construction.
        return PIN_EXACT if re.match(r"^v?\d", raw) else PIN_UNPINNED
    if ecosystem == "nuget":
        # NuGet version semantics (review finding 8): a plain `1.0.0` is a
        # FLOATING MINIMUM (>=1.0.0), not an exact pin, so it is a range. Only a
        # bracketed single version `[1.0.0]` pins exactly. Intervals `[1.0,2.0)`
        # and floating wildcards `1.*` are ranges. A committed packages.lock.json
        # is what pins the actual resolved version; the declared constraint's
        # tightness is what this classifies.
        if raw.startswith("[") and raw.endswith("]") and "," not in raw:
            return PIN_EXACT
        return PIN_RANGE

    # Unknown ecosystem: fall back to the loose-semver reading.
    return _classify_semver(raw, bare_is_exact=True)


# Operators that make any constraint a range in a semver-family ecosystem.
_SEMVER_RANGE_OPS = ("^", "~", ">", "<", "||", " - ", " ")


def _has_wildcard_component(raw: str) -> bool:
    """Whether ``raw`` uses x/X/* as a VERSION COMPONENT (a wildcard range).

    A wildcard is only a wildcard when it stands as a whole dotted component of
    the numeric version (a bare ``x``, or ``1.x``, or ``1.2.x``), never as a
    letter inside a build or pre-release tag. This is the review-finding-4 fix:
    the old substring test fired on ``1.0.0-linux`` and ``1.0.0-exp.1`` and every
    version whose tag merely CONTAINS an x. The pre-release (after ``-``) and
    build metadata (after ``+``) are stripped before the component check.
    """
    main = re.split(r"[-+]", raw, maxsplit=1)[0]
    return any(comp in ("x", "X", "*") for comp in main.split("."))


def _classify_semver(raw: str, *, bare_is_exact: bool) -> str:
    if raw.startswith("="):
        return PIN_EXACT
    if any(op in raw for op in _SEMVER_RANGE_OPS):
        return PIN_RANGE
    if _has_wildcard_component(raw):
        return PIN_RANGE
    # A bare version with no operator: exact in npm-family, caret range in cargo.
    return PIN_EXACT if bare_is_exact else PIN_RANGE


# A single exact-version specifier (==1.2.3 / ===1.2.3, or a bare 1.2.3), used to
# recover a resolved version from a manifest that pins exactly without a lockfile
# (review finding 5: requirements.txt `requests==2.31.0`). Returns the version
# string, or None when the constraint is a range/wildcard/empty.
_EXACT_SPEC = re.compile(r"^\s*(?:===|==)?\s*(\d[\w.\-+]*)\s*$")


def exact_version(constraint: str | None) -> str | None:
    """Return the concrete version an exact specifier names, else None.

    ``==1.2.3`` and ``===1.2.3`` and a bare ``1.2.3`` all yield ``1.2.3``.
    Anything with a range operator, a comma, or a wildcard component yields None,
    so a resolved version is only recovered when the pin is genuinely exact.
    """
    if not constraint:
        return None
    raw = constraint.strip()
    if "," in raw or any(op in raw for op in ("^", "~", ">", "<", "*", "!", " ")):
        return None
    m = _EXACT_SPEC.match(raw)
    if not m:
        return None
    version = m.group(1)
    if _has_wildcard_component(version):
        return None
    return version


def _classify_pypi(raw: str) -> str:
    # PEP 508 / PEP 440 specifiers. === and == are exact; every other operator
    # (and any comma-joined set) admits a range. Poetry's caret/tilde and a bare
    # value also read as a range under the poetry syntax the parser passes here.
    if "," in raw:
        return PIN_RANGE
    if raw.startswith("==="):
        return PIN_EXACT
    if raw.startswith("=="):
        # "==1.2.*" is a range; a concrete "==1.2.3" is exact.
        return PIN_RANGE if "*" in raw else PIN_EXACT
    if raw[0] in "<>~^!":
        return PIN_RANGE
    if "*" in raw:
        return PIN_RANGE
    # A bare "1.2.3" declared as a poetry dependency is a caret range; a bare
    # value never means an exact pin in the specifier grammar.
    return PIN_RANGE


def _classify_ruby(raw: str) -> str:
    # RubyGems requirements. "= 1.2.3" is exact; "~>", ">=", comparison operators,
    # and comma-joined sets are ranges; a bare "1.2.3" is exact.
    if "," in raw:
        return PIN_RANGE
    if raw.startswith("~>") or raw[0] in "<>":
        return PIN_RANGE
    if raw.startswith("="):
        return PIN_EXACT
    return PIN_EXACT if re.match(r"^\d", raw) else PIN_UNPINNED
