"""Deterministic id normalization for changelog diffing across composition changes.

The changelog diff (``analyzer/project/changelog.py`` and its legacy mirror
``analyzer/incremental.py``) compares component ids as plain strings. When a
projection switches between the plain single-repo shape and the composed
multi-repo shape (``analyzer/derive/multi.py::merge_architectures`` /
``analyzer/multi_repo.py``), every id under a composed repo gains a
``<repo_name>/`` prefix (and a ``repo:<repo_name>`` wrapper component is
introduced). A naive set difference on ids then reports every component as
both removed (old, unprefixed id) and added (new, prefixed id), even though
almost nothing about the component actually changed.

This module fixes that in two stages, both applied *before* any set
difference runs:

Step 1 -- deterministic normalization. The composed projection records its
repository composition in ``repositories: [{"name": ...}]``. Comparing that
list between the previous and current projections tells us, structurally
(not statistically), whether a prefix was added or removed and which prefix
it was. ``composition_transform`` derives that transform. When composition is
unchanged it returns ``None`` and diffing must be byte-identical to today.

Step 2 (partial) / Step 3 -- residual inference. After deterministic
normalization there may still be unmatched removed/added pairs (a component
renamed at the same time it was reprefixed, for instance). ``name`` survives
prefixing (``_prefix_components`` in ``analyzer/derive/multi.py`` and
``analyzer/multi_repo.py`` deliberately does not rewrite it), so
``infer_reidentification_matches`` attempts a secondary match on
``(name, type)``, corroborated by metrics closeness and file-basename
overlap, and accepts a match only when it is unambiguous. Under-matching
(leaving a real add + a real remove) is preferred over mis-matching.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple, Optional

__all__ = [
    "CompositionTransform",
    "composition_transform",
    "infer_reidentification_matches",
]


def _repo_names(arch: Optional[dict]) -> set[str]:
    if not arch:
        return set()
    return {
        r.get("name")
        for r in (arch.get("repositories") or [])
        if r.get("name")
    }


class CompositionTransform(NamedTuple):
    """A structural id-namespace transform derived from repository composition.

    ``old_key``/``new_key`` map a raw id from that side into a canonical form
    comparable across both sides. ``wrapper_ids_added``/``wrapper_ids_removed``
    are the ``repo:<name>`` container ids introduced or dropped by the
    composition change itself -- these are composition infrastructure, not
    components of the analysed codebase, and the changelog reports them as
    such rather than as ordinary component adds/removes or re-identifications.
    """

    old_key: Callable[[str], str]
    new_key: Callable[[str], str]
    wrapper_ids_added: frozenset
    wrapper_ids_removed: frozenset


def composition_transform(
    old_arch: Optional[dict], new_arch: Optional[dict]
) -> Optional[CompositionTransform]:
    """Derive the id-namespace transform between two projections' compositions.

    Returns ``None`` when the repository composition (the *set* of repo
    names) is unchanged between ``old_arch`` and ``new_arch`` -- including
    when neither side is composed at all -- so callers can take a no-op fast
    path that reproduces today's behaviour exactly.

    When composition changed, the transform strips the newly-introduced (or
    newly-dropped) repo prefix, but only when doing so is unambiguous: a
    single repo joining or leaving composition against a previously-plain (or
    now-plain) other side. A multi-repo composition change that does not
    reduce to that unambiguous case is left unnormalized for those repos --
    their components correctly surface as genuine adds/removes rather than
    guessed re-identifications (this is deliberately conservative; residual
    matching in ``infer_reidentification_matches`` can still recover
    unambiguous cases from name/type/metrics evidence).
    """
    old_names = _repo_names(old_arch)
    new_names = _repo_names(new_arch)
    if old_names == new_names:
        return None

    added_repos = new_names - old_names
    removed_repos = old_names - new_names

    # Plain -> composed: the old side had no composition at all, and exactly
    # one repo was newly composed, so that repo's prefix stands for the
    # entirety of the old plain projection.
    strip_new_prefix = None
    if not old_names and len(added_repos) == 1:
        strip_new_prefix = f"{next(iter(added_repos))}/"

    # Composed -> plain: the new side dropped composition entirely, and
    # exactly one repo was removed, so its prefix stands for the entirety of
    # the new plain projection.
    strip_old_prefix = None
    if not new_names and len(removed_repos) == 1:
        strip_old_prefix = f"{next(iter(removed_repos))}/"

    def old_key(cid: str) -> str:
        if strip_old_prefix and cid.startswith(strip_old_prefix):
            return cid[len(strip_old_prefix):]
        return cid

    def new_key(cid: str) -> str:
        if strip_new_prefix and cid.startswith(strip_new_prefix):
            return cid[len(strip_new_prefix):]
        return cid

    return CompositionTransform(
        old_key=old_key,
        new_key=new_key,
        wrapper_ids_added=frozenset(f"repo:{r}" for r in added_repos),
        wrapper_ids_removed=frozenset(f"repo:{r}" for r in removed_repos),
    )


# ---------------------------------------------------------------------------
# Step 3: residual (name, type) matching, corroborated and ambiguity-guarded
# ---------------------------------------------------------------------------

# Required score margin of the best candidate over the runner-up before an
# ambiguous (name, type) group is allowed to resolve to a match. Chosen to be
# comfortably above noise: a coin-flip corroboration signal (score 0 for
# every candidate, e.g. no metrics or files to compare) never clears it, so a
# same-named group with no corroborating evidence stays unmatched.
MATCH_MARGIN = 0.15


def _basenames(files: Optional[list]) -> set:
    return {str(f).rsplit("/", 1)[-1] for f in (files or [])}


def _metrics_similarity(m1: dict, m2: dict) -> Optional[float]:
    keys = [
        k for k in (set(m1) & set(m2))
        if isinstance(m1.get(k), (int, float)) and isinstance(m2.get(k), (int, float))
        and not isinstance(m1.get(k), bool) and not isinstance(m2.get(k), bool)
    ]
    if not keys:
        return None
    total = 0.0
    for k in keys:
        a, b = m1[k], m2[k]
        denom = max(abs(a), abs(b), 1)
        total += 1.0 - min(abs(a - b) / denom, 1.0)
    return total / len(keys)


def _file_overlap(files1: Optional[list], files2: Optional[list]) -> Optional[float]:
    b1, b2 = _basenames(files1), _basenames(files2)
    if not b1 or not b2:
        return None
    union = len(b1 | b2)
    if not union:
        return None
    return len(b1 & b2) / union


def _pair_score(
    old_metrics: Optional[dict], new_metrics: Optional[dict],
    old_files: Optional[list], new_files: Optional[list],
) -> float:
    """Corroboration score in [0, 1] for a candidate (removed, added) pair.

    Combines metrics closeness and file-basename overlap when available.
    Returns 0.0 (no corroborating signal) rather than a fabricated tie-break
    when neither is available -- callers require a clear margin to accept a
    match, so an all-zero group correctly stays unmatched.
    """
    sims = []
    ms = _metrics_similarity(old_metrics or {}, new_metrics or {})
    if ms is not None:
        sims.append(ms)
    fo = _file_overlap(old_files, new_files)
    if fo is not None:
        sims.append(fo)
    if not sims:
        return 0.0
    return sum(sims) / len(sims)


class ReidentificationMatch(NamedTuple):
    old_id: str
    new_id: str
    score: Optional[float]  # None for name/type-unique matches (no scoring needed)


def infer_reidentification_matches(
    removed_ids: list,
    added_ids: list,
    old_info: dict,
    new_info: dict,
    old_metrics: dict,
    new_metrics: dict,
    old_files: dict,
    new_files: dict,
) -> tuple:
    """Step 3: match residual removed/added components by (name, type).

    ``old_info``/``new_info`` map id -> {"name", "type"}. ``old_metrics``/
    ``new_metrics`` map id -> metrics dict. ``old_files``/``new_files`` map id
    -> list of file paths (basenames are compared, so full paths are fine).

    Returns ``(matches, matched_removed_ids, matched_added_ids)``.

    Matching rule: components are grouped by ``(name, type)`` on each side.
    - A group with exactly one removed and one added component is an
      unambiguous match by construction (name/type alone identifies it) --
      matched regardless of corroboration.
    - A group with more than one candidate on either side is ambiguous by
      name/type alone (``name`` is not unique in general -- many components
      are named "tests"). It is corroborated with metrics/file-basename
      scoring, and a pair is accepted only when it is each other's strict
      best match AND the margin over the runner-up on both sides clears
      ``MATCH_MARGIN``. Anything short of that is left unmatched: a real add
      plus a real remove is a safer outcome than a wrong match.
    """
    by_key_removed: dict = {}
    by_key_added: dict = {}
    for rid in removed_ids:
        info = old_info.get(rid, {})
        by_key_removed.setdefault((info.get("name"), info.get("type")), []).append(rid)
    for aid in added_ids:
        info = new_info.get(aid, {})
        by_key_added.setdefault((info.get("name"), info.get("type")), []).append(aid)

    matches: list = []
    matched_removed: set = set()
    matched_added: set = set()

    for key, r_group in by_key_removed.items():
        a_group = by_key_added.get(key)
        if not a_group:
            continue

        if len(r_group) == 1 and len(a_group) == 1:
            matches.append(ReidentificationMatch(r_group[0], a_group[0], None))
            matched_removed.add(r_group[0])
            matched_added.add(a_group[0])
            continue

        scores = {
            (r, a): _pair_score(
                old_metrics.get(r), new_metrics.get(a),
                old_files.get(r), new_files.get(a),
            )
            for r in r_group for a in a_group
        }

        for r in r_group:
            ranked = sorted(a_group, key=lambda a: scores[(r, a)], reverse=True)
            best = ranked[0]
            if len(ranked) > 1 and (scores[(r, best)] - scores[(r, ranked[1])]) < MATCH_MARGIN:
                continue

            ranked_from_a = sorted(r_group, key=lambda rr: scores[(rr, best)], reverse=True)
            if ranked_from_a[0] != r:
                continue
            if len(ranked_from_a) > 1 and (
                scores[(r, best)] - scores[(ranked_from_a[1], best)]
            ) < MATCH_MARGIN:
                continue

            if r in matched_removed or best in matched_added:
                continue
            matches.append(ReidentificationMatch(r, best, scores[(r, best)]))
            matched_removed.add(r)
            matched_added.add(best)

    return matches, matched_removed, matched_added
