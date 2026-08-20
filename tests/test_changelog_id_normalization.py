"""Regression coverage for changelog id normalization across composition changes.

The bug: ``analyzer/project/changelog.py::compute_diff_summary`` (and its
legacy mirror in ``analyzer/incremental.py``) diffed component ids as a plain
set difference. When a projection switches to the composed multi-repo path
(``analyzer/derive/multi.py::merge_architectures`` / ``analyzer/multi_repo.py``),
every id gains a ``repo_name/`` prefix, so the naive diff reported every
component as both removed (old, unprefixed id) and added (new, prefixed id).
On the live UnaMentis demo this produced 254 "component_added" and 256
"component_removed" entries with zero id overlap, even though only six
components actually changed. Relationships, compared as
``(source, target, type)`` tuples, inherited the same noise.

The fix normalizes ids before diffing (``analyzer/project/id_normalization.py``):

  * Step 1 (deterministic): the composed projection records its repository
    composition in ``repositories: [{"name": ...}]``. Comparing that field
    between the two projections tells us structurally -- not statistically --
    whether a prefix was introduced or dropped, and derives the exact
    transform.
  * Step 2: components matched this way are reported as a distinct
    ``component_reidentified`` change, never as "New component discovered".
    Pure re-identifications (nothing else about the component changed) are
    folded into one summary fact instead of N rows.
  * Step 3 (residual, ambiguity-guarded): components matched instead on
    ``(name, type)`` plus metrics/file-basename corroboration, only when
    unambiguous, are labelled ``confidence: "inferred"`` -- distinctly from
    Step 1's ``"deterministic"``.
  * Step 4: the same normalization applies to the relationship diff.

``test_migration_acceptance_sets`` below is built from two projections
recorded in a real mirror of the live UnaMentis demo (changelog serial 1, the
pre-migration state, and serial 2, the post-migration diff). The manifest
itself only stores the *current* (post-migration) architecture plus the
changelog *entries* describing each diff, not the full pre-migration
architecture dict, so the "old" side is reconstructed from serial 1's own
changelog entries: that scan ran with ``previous=None`` (an "initial" scan),
so its ``component_added`` list *is* the complete flat pre-migration
component set (id, name, type), and its ``relationship_added`` list is the
complete pre-migration relationship set. The "new" side is the current
component tree and relationship list, taken as-is. Both are trimmed to the
fields the diff logic actually reads (id/name/type/metrics/children,
source/target/type) -- see
``tests/fixtures/changelog_migration_old.json`` /
``changelog_migration_new.json`` and the generation notes in this docstring.

One caveat, spelled out rather than silently worked around: per-component
*metrics* for the pre-migration state are not recoverable from the changelog
record (a "component_added" entry only carries name/type/detail, not
metrics), so metrics are zeroed on both sides of the reconstructed fixture.
This is safe for this test's purpose -- the acceptance set below asserts
add/remove/reidentify/reclassify classification, and the real recorded
diff (relationships_removed 171 vs. the 168 this reconstruction yields, a
3-relationship gap consistent with incidental drift between when serial 1
was recorded and when the mirror was captured) is not part of the exact
assertion either, only its order-of-magnitude shrinkage is checked.
"""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.incremental import IncrementalAnalyzer
from analyzer.project.changelog import build_changelog_entry, compute_diff_summary

FIXTURES = Path(__file__).parent / "fixtures"

TRUE_REMOVALS = [
    "llama.cpp",
    "models/glm-asr-nano",
    "models/kyutai-pocket-ios",
    "server/management/data",
    "server/management/data/modules",
    "testresults.xcresult",
]

TRUE_ADDITIONS = [
    "unamentis/docs/research",
    "unamentis/docs/reviews",
    "unamentis/unamentis/__ui__/unamentis-launchscreen-storyboard/01J-lp-oVM",
]

# (old_id, new_id, what changed) -- verified against the reconstructed
# fixture directly; note the "scripts" direction runs old-name "Remote Log
# Server" -> new-name "scripts" (the reverse of a loosely-worded paraphrase
# one might expect), confirmed from the raw changelog serial-1/serial-2 data.
RECLASSIFICATIONS = {
    "scripts": "unamentis/scripts",
    "server/importers/docs": "unamentis/server/importers/docs",
    "server/importers/output": "unamentis/server/importers/output",
    "server/management/tests": "unamentis/server/management/tests",
    "unamentis-watch-app": "unamentis/unamentis-watch-app",
}

INFRASTRUCTURE_WRAPPER = "repo:unamentis"


def _load_migration_fixture() -> tuple[dict, dict]:
    old = json.loads((FIXTURES / "changelog_migration_old.json").read_text())
    new = json.loads((FIXTURES / "changelog_migration_new.json").read_text())
    return old, new


def test_migration_acceptance_sets():
    """The exact classification the design's acceptance test specifies.

    6 true removals, 3 true additions, 1 infrastructure wrapper addition, 5
    visible reclassifications, and the remaining ~245 matched pairs folded
    into a single re-identification fact rather than 245 separate rows.
    """
    old, new = _load_migration_fixture()
    diff = compute_diff_summary(old, new)

    assert sorted(diff["components_removed"]) == sorted(TRUE_REMOVALS)
    assert sorted(diff["components_added"]) == sorted(TRUE_ADDITIONS)

    assert diff["components_infrastructure_added"] == [INFRASTRUCTURE_WRAPPER]
    assert diff["components_infrastructure_removed"] == []

    reidentified_by_old_id = {r["old_id"]: r for r in diff["components_reidentified"]}
    assert set(reidentified_by_old_id) == set(RECLASSIFICATIONS)
    for old_id, new_id in RECLASSIFICATIONS.items():
        entry = reidentified_by_old_id[old_id]
        assert entry["new_id"] == new_id
        assert entry["confidence"] == "deterministic"
        # Every reclassification must show a real difference -- it would not
        # be worth surfacing as a visible change otherwise.
        assert (
            entry["old_name"] != entry["new_name"]
            or entry["old_type"] != entry["new_type"]
        )

    # Every matched pair not individually listed above must be a pure,
    # foldable re-identification (name/type/metrics all unchanged): 256 old
    # ids - 6 true removals = 250 matched, minus the 5 visible
    # reclassifications = 245 folded.
    assert diff["components_reidentified_folded"] == {"deterministic": 245, "inferred": 0}

    # No same-id metrics-only modification is expected in this migration.
    assert diff["components_modified"] == []

    # Relationship noise shrinks sharply once endpoints are normalized (from
    # a naive 501 added / ~168-171 removed with zero overlap).
    assert diff["relationships_added"] < 450
    assert diff["relationships_removed"] < 100


def test_migration_changelog_entry_never_says_new_component_discovered():
    """Re-identified/reclassified components must never read as fresh adds."""
    old, new = _load_migration_fixture()
    diff = compute_diff_summary(old, new)
    entry = build_changelog_entry(diff, old, new, "full", 2)

    added_ids = {c["target_id"] for c in entry["changes"] if c["kind"] == "component_added"}
    assert added_ids == set(TRUE_ADDITIONS)
    for change in entry["changes"]:
        if change["kind"] == "component_added":
            assert change["detail"] == "New component discovered"

    reidentified_new_ids = {
        c["new_id"] for c in entry["changes"] if c["kind"] == "component_reidentified"
    }
    assert reidentified_new_ids == set(RECLASSIFICATIONS.values())
    assert reidentified_new_ids.isdisjoint(added_ids)

    # The 245 folded pure re-identifications are one summary row, not 245.
    bulk_rows = [c for c in entry["changes"] if c["kind"] == "component_reidentified_bulk"]
    assert len(bulk_rows) == 1
    assert bulk_rows[0]["count"] == 245
    assert bulk_rows[0]["confidence"] == "deterministic"
    assert "245 components re-identified under a new namespace" in bulk_rows[0]["detail"]

    infra_rows = [c for c in entry["changes"] if c["kind"] == "component_infrastructure_added"]
    assert len(infra_rows) == 1
    assert infra_rows[0]["target_id"] == INFRASTRUCTURE_WRAPPER
    assert "not a component of the analysed codebase" in infra_rows[0]["detail"]

    assert "254 components added" not in entry["summary"]
    assert "3 components added" in entry["summary"]
    assert "6 components removed" in entry["summary"]


def test_legacy_engine_matches_new_engine_on_a_composition_migration():
    """The legacy/current-engine equivalence must hold for composed projections too.

    ``tests/test_project.py::test_changelog_equivalent_to_current_behavior``
    covers the plain (non-composed) case only. This closes that gap for the
    id-normalization path specifically, since the two engines share the fix
    via delegation (see analyzer/incremental.py) rather than a hand-kept
    duplicate.
    """
    old, new = _load_migration_fixture()

    diff_new_engine = compute_diff_summary(old, new)
    entry_new_engine = build_changelog_entry(diff_new_engine, old, new, "full", 2)

    ia = object.__new__(IncrementalAnalyzer)
    ia.head_sha = ""
    diff_legacy = ia.compute_diff_summary(old, new)
    entry_legacy = ia.build_changelog_entry(diff_legacy, old, new, "full", 2)

    assert diff_new_engine == diff_legacy
    for key in ("serial", "commit_sha", "scan_type", "summary", "changes"):
        assert entry_new_engine[key] == entry_legacy[key], f"changelog field {key} diverged"


# ---------------------------------------------------------------------------
# No-op fast path: composition unchanged must be byte-identical to the
# pre-normalization behavior, including *not* running Step 3 residual
# inference (an unrelated rename in an ordinary single-repo scan must stay a
# plain add + remove, not a guessed re-identification).
# ---------------------------------------------------------------------------

def test_no_composition_change_does_not_infer_reidentification():
    old = {
        "components": [
            {"id": "tests", "name": "tests", "type": "module", "metrics": {}, "children": []},
        ],
        "relationships": [],
    }
    new = {
        "components": [
            {"id": "specs", "name": "tests", "type": "module", "metrics": {}, "children": []},
        ],
        "relationships": [],
    }
    diff = compute_diff_summary(old, new)

    assert diff["components_added"] == ["specs"]
    assert diff["components_removed"] == ["tests"]
    assert diff["components_reidentified"] == []
    assert diff["components_reidentified_folded"] == {"deterministic": 0, "inferred": 0}


def test_no_composition_change_is_identical_with_and_without_repositories_key():
    """An absent ``repositories`` key and an empty list must behave the same."""
    base = {
        "components": [
            {"id": "a", "name": "A", "type": "module", "metrics": {"lines": 1}, "children": []},
        ],
        "relationships": [],
    }
    old_a = dict(base)
    new_a = {**base, "components": [
        {"id": "a", "name": "A", "type": "module", "metrics": {"lines": 2}, "children": []},
    ]}
    old_b = {**old_a, "repositories": []}
    new_b = {**new_a, "repositories": []}

    assert compute_diff_summary(old_a, new_a) == compute_diff_summary(old_b, new_b)


# ---------------------------------------------------------------------------
# Step 3: residual (name, type) matching, ambiguity-guarded
# ---------------------------------------------------------------------------

def test_step3_matches_unambiguous_rename_during_migration():
    """A component renamed at the same moment it is reprefixed is still caught.

    Its id does not survive Step 1's deterministic strip (the id itself
    changed, not just gained a prefix), but its (name, type) is unique on
    both sides, so Step 3 recovers it -- labelled "inferred", not
    "deterministic".
    """
    old = {
        "components": [
            {
                "id": "old-widgets", "name": "Widget Factory", "type": "module",
                "metrics": {"lines": 100}, "files": ["widgets/factory.py"], "children": [],
            },
        ],
        "relationships": [],
    }
    new = {
        "repositories": [{"name": "svc"}],
        "components": [
            {
                "id": "repo:svc", "name": "svc", "type": "repository", "metrics": {}, "children": [
                    {
                        # id gains the composition prefix *and* is renamed at
                        # the same time, so its post-strip canonical key
                        # ("new-widgets") does not equal the old id
                        # ("old-widgets") -- Step 1 cannot match it, only
                        # Step 3's (name, type) + metrics corroboration can.
                        # Metrics also shift slightly, which is why this pair
                        # surfaces as a visible reidentification rather than
                        # folding into the silent bulk count.
                        "id": "svc/new-widgets", "name": "Widget Factory", "type": "module",
                        "metrics": {"lines": 110}, "files": ["svc/widgets/factory.py"],
                        "children": [],
                    },
                ],
            },
        ],
        "relationships": [],
    }
    diff = compute_diff_summary(old, new)

    assert diff["components_added"] == []
    assert diff["components_removed"] == []
    assert len(diff["components_reidentified"]) == 1
    match = diff["components_reidentified"][0]
    assert match["old_id"] == "old-widgets"
    assert match["new_id"] == "svc/new-widgets"
    assert match["confidence"] == "inferred"


def test_step3_refuses_ambiguous_same_name_group():
    """Two removed components share (name, type) with one added: must NOT match.

    This is the "many components are called tests" case from the design.
    With no corroborating metrics/file evidence to break the tie, both
    removed components must stay genuinely removed and the added component
    must stay genuinely added -- under-matching, not a guess.
    """
    old = {
        "components": [
            {"id": "moduleA/tests", "name": "tests", "type": "module", "metrics": {}, "children": []},
            {"id": "moduleB/tests", "name": "tests", "type": "module", "metrics": {}, "children": []},
        ],
        "relationships": [],
    }
    new = {
        "repositories": [{"name": "svc"}],
        "components": [
            {"id": "repo:svc", "name": "svc", "type": "repository", "metrics": {}, "children": [
                {"id": "svc/moduleC/tests", "name": "tests", "type": "module", "metrics": {}, "children": []},
            ]},
        ],
        "relationships": [],
    }
    diff = compute_diff_summary(old, new)

    assert sorted(diff["components_removed"]) == ["moduleA/tests", "moduleB/tests"]
    assert diff["components_added"] == ["svc/moduleC/tests"]
    assert diff["components_reidentified"] == []


def test_step3_accepts_ambiguous_group_when_corroboration_gives_a_clear_margin():
    """Same (name, type) pair on both sides, disambiguated by strong metrics/file evidence."""
    old = {
        "components": [
            {
                "id": "moduleA/tests", "name": "tests", "type": "module",
                "metrics": {"lines": 500, "files": 20}, "files": ["moduleA/tests/test_a.py"],
                "children": [],
            },
            {
                "id": "moduleB/tests", "name": "tests", "type": "module",
                "metrics": {"lines": 5, "files": 1}, "files": ["moduleB/tests/test_b.py"],
                "children": [],
            },
        ],
        "relationships": [],
    }
    new = {
        "repositories": [{"name": "svc"}],
        "components": [
            {"id": "repo:svc", "name": "svc", "type": "repository", "metrics": {}, "children": [
                # Note the path is moduleC, not moduleA: the post-strip
                # canonical key ("moduleC/tests") does not literally match
                # either old id, so Step 1 cannot resolve this and it is
                # genuinely ambiguous by (name, type) alone until metrics/
                # file-basename corroboration breaks the tie in moduleA's
                # favor.
                {
                    "id": "svc/moduleC/tests", "name": "tests", "type": "module",
                    "metrics": {"lines": 505, "files": 20}, "files": ["svc/moduleA/tests/test_a.py"],
                    "children": [],
                },
            ]},
        ],
        "relationships": [],
    }
    diff = compute_diff_summary(old, new)

    assert diff["components_removed"] == ["moduleB/tests"]
    assert diff["components_added"] == []
    assert len(diff["components_reidentified"]) == 1
    match = diff["components_reidentified"][0]
    assert match["old_id"] == "moduleA/tests"
    assert match["new_id"] == "svc/moduleC/tests"
    assert match["confidence"] == "inferred"


# ---------------------------------------------------------------------------
# Symmetric direction: composed -> plain (decomposition), and infrastructure
# removal.
# ---------------------------------------------------------------------------

def test_composed_to_plain_decomposition_normalizes_and_reports_infra_removed():
    old = {
        "repositories": [{"name": "svc"}],
        "components": [
            {"id": "repo:svc", "name": "svc", "type": "repository", "metrics": {}, "children": [
                {"id": "svc/api", "name": "api", "type": "module", "metrics": {"lines": 10}, "children": []},
            ]},
        ],
        "relationships": [{"source": "svc/api", "target": "svc/api", "type": "import"}],
    }
    new = {
        "components": [
            {"id": "api", "name": "api", "type": "module", "metrics": {"lines": 12}, "children": []},
        ],
        "relationships": [{"source": "api", "target": "api", "type": "import"}],
    }
    diff = compute_diff_summary(old, new)

    assert diff["components_added"] == []
    assert diff["components_removed"] == []
    assert diff["components_infrastructure_removed"] == ["repo:svc"]
    assert diff["components_infrastructure_added"] == []
    # id changed (prefix dropped) but metrics also changed -> visible, not folded.
    assert len(diff["components_reidentified"]) == 1
    match = diff["components_reidentified"][0]
    assert match["old_id"] == "svc/api"
    assert match["new_id"] == "api"
    assert match["confidence"] == "deterministic"
    # The relationship between the same (re-identified) component on both
    # sides is not spuriously reported as churn.
    assert diff["relationships_added"] == 0
    assert diff["relationships_removed"] == 0
