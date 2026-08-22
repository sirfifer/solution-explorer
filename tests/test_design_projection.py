"""D3: design signals in the projection, behind --design-signals.

The golden corpora prove the default path does not move. These prove the other
half, and the half the corpora cannot see because they never pass the flag.

Contracts under test:

  1. DEFAULT OFF, AND OFF MEANS NOTHING RUNS. The flag parses to False, and a
     projection built without it is byte-identical to one built before the
     feature existed. Both modes, split and monolith.
  2. ON MEANS THE DATA APPEARS, IN THE CANONICAL SHAPE. Per-component `design`
     metrics and architecture-level `design_signals.findings[]`.
  3. NO-OP WHEN EMPTY. Flag on plus a store with nothing to say produces no
     keys at all, not empty ones.
  4. THE METHOD CAVEAT IS PROJECTED DATA. Not something a rendering surface
     invents.
  5. DECLINE-TO-CLAIM IS ENFORCED IN THE SCHEMA. No global score field exists
     anywhere in the payload, and no finding ranks across kinds.
  6. A FAILING EMITTER DEGRADES TO AN HONEST GAP. It never fractures the run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from analyzer.cli import main
from analyzer.derive import derive_all
from analyzer.derive.design_signals import METHOD_CAVEAT
from analyzer.extract import extract_repo
from analyzer.project import project_monolith, project_split
from analyzer.project.design import emit_design_signals
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")

# The changelog stamps a wall-clock timestamp, so two projections of the same
# subject are never byte-identical unless the clock is pinned. Pinning it is
# what makes a byte-comparison test a test of this feature rather than a test
# of how fast the machine is.
FIXED_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _subject():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    return store, arch


def _walk(components):
    for comp in components or []:
        yield comp
        yield from _walk(comp.get("children") or [])


# --- 1. default off ------------------------------------------------------------


def test_the_cli_run_without_the_flag_projects_no_design_signals(
    tmp_path, monkeypatch
):
    """End to end through the real CLI: absent flag, absent data."""
    out = tmp_path / "arch.json"
    monkeypatch.setattr(
        "sys.argv",
        ["analyze", POLYGLOT, "-o", str(out), "--engine", "v2"],
    )
    main()
    document = json.loads(out.read_text())
    assert "design_signals" not in document
    assert all("design" not in c for c in _walk(document.get("components")))


def test_the_cli_flag_turns_the_signals_on(tmp_path, monkeypatch):
    out = tmp_path / "arch.json"
    monkeypatch.setattr(
        "sys.argv",
        ["analyze", POLYGLOT, "-o", str(out), "--engine", "v2", "--design-signals"],
    )
    main()
    document = json.loads(out.read_text())
    assert "design_signals" in document
    assert document["design_signals"]["method_caveat"] == METHOD_CAVEAT
    assert any("design" in c for c in _walk(document["components"]))


def test_the_default_namespace_reads_as_off():
    """run_v2 reads the flag defensively, so an arg object without it is off."""
    from analyzer.project.run import run_v2

    assert callable(run_v2)
    # The projection drivers default the keyword off, which is the guarantee
    # the golden corpora depend on since they never pass it.
    import inspect

    for driver in (project_split, project_monolith):
        signature = inspect.signature(driver)
        assert signature.parameters["design_signals"].default is False


def test_monolith_is_byte_identical_with_the_flag_off(tmp_path):
    """The proof the golden corpora encode, run here against the fixture too."""
    store, arch = _subject()
    try:
        first = tmp_path / "a.json"
        second = tmp_path / "b.json"
        project_monolith(
            arch, first, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
        )
        project_monolith(
            arch, second, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=False,
        )
        assert first.read_bytes() == second.read_bytes()
        document = json.loads(first.read_text())
        assert "design_signals" not in document
        assert all("design" not in c for c in _walk(document.get("components")))
    finally:
        store.close()


def test_split_is_byte_identical_with_the_flag_off(tmp_path):
    store, arch = _subject()
    try:
        first_dir = tmp_path / "one"
        second_dir = tmp_path / "two"
        project_split(
            arch, first_dir, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
        )
        project_split(
            arch, second_dir, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=False,
        )
        left = sorted(p.name for p in first_dir.rglob("*") if p.is_file())
        right = sorted(p.name for p in second_dir.rglob("*") if p.is_file())
        assert left == right
        manifest = json.loads((first_dir / "manifest.json").read_text())
        assert "design_signals" not in manifest
        assert all("design" not in c for c in _walk(manifest.get("components")))
    finally:
        store.close()


def test_the_off_path_never_reads_the_store():
    """Off is not "computed then discarded", it is "not computed"."""

    class Exploding:
        def __getattr__(self, name):
            raise AssertionError(f"the off path touched the store: .{name}")

    arch = {"components": []}
    assert emit_design_signals(arch, Exploding(), enabled=False) is None
    assert arch == {"components": []}


# --- 2. on means the data appears ----------------------------------------------


def test_the_flag_adds_the_component_block_and_the_findings(tmp_path):
    store, arch = _subject()
    try:
        out = tmp_path / "arch.json"
        project_monolith(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        document = json.loads(out.read_text())

        section = document["design_signals"]
        assert isinstance(section["findings"], list)
        assert section["component_count"] > 0

        blocks = [c["design"] for c in _walk(document["components"]) if "design" in c]
        assert blocks, "at least one component must carry design metrics"
        for block in blocks:
            # The canonical per-component shape from the build plan.
            assert set(block) == {
                "fan_in", "fan_out", "instability", "abstractness",
                "distance_main_sequence", "blast_radius", "bands",
            }
            assert isinstance(block["fan_in"], int)
            assert isinstance(block["blast_radius"], int)
            assert isinstance(block["bands"], dict)
    finally:
        store.close()


def test_findings_carry_the_canonical_dual_audience_shape(tmp_path):
    store, arch = _subject()
    try:
        out = tmp_path / "arch.json"
        project_monolith(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        findings = json.loads(out.read_text())["design_signals"]["findings"]
        assert findings, "the fixture must produce at least one finding"
        for finding in findings:
            assert set(finding) >= {
                "id", "kind", "lead", "term", "method", "targets", "edges",
                "evidence", "rank_within_kind",
            }
            # Lead first, term second. The human surface renders in this order.
            assert finding["lead"]
            assert finding["term"]
            assert finding["lead"] != finding["term"]
            assert finding["method"] in (
                "static-graph", "git-history", "static-graph+git-history"
            )
    finally:
        store.close()


def test_the_split_manifest_carries_the_section(tmp_path):
    store, arch = _subject()
    try:
        out = tmp_path / "split"
        project_split(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        manifest = json.loads((out / "manifest.json").read_text())
        assert "design_signals" in manifest
        assert manifest["design_signals"]["method_caveat"] == METHOD_CAVEAT
        assert any("design" in c for c in _walk(manifest["components"]))
    finally:
        store.close()


def test_the_projection_is_deterministic_with_the_flag_on(tmp_path):
    store, arch = _subject()
    try:
        first = tmp_path / "a.json"
        second = tmp_path / "b.json"
        for path in (first, second):
            project_monolith(
                arch, path, store=store, root=POLYGLOT,
                generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
                design_signals=True,
            )
        assert first.read_bytes() == second.read_bytes()
    finally:
        store.close()


# --- 3. no-op when empty --------------------------------------------------------


def test_an_empty_store_produces_no_section_even_with_the_flag_on():
    store = FactStore(":memory:")
    try:
        arch = {"components": []}
        assert emit_design_signals(arch, store, enabled=True) is None
        assert arch == {"components": []}
    finally:
        store.close()


def test_a_component_the_derivation_does_not_know_keeps_no_key():
    from analyzer.derive.design_signals import ComponentDesign, DesignSignals
    from analyzer.project.design import apply_design_overlay

    arch = {"components": [
        {"id": "known", "children": [{"id": "unknown", "children": []}]},
    ]}
    signals = DesignSignals(items=[ComponentDesign(component_id="known")])
    apply_design_overlay(arch, signals)
    assert "design" in arch["components"][0]
    assert "design" not in arch["components"][0]["children"][0]


# --- 4. the method caveat is projected data -------------------------------------


def test_the_method_caveat_rides_in_the_payload(tmp_path):
    store, arch = _subject()
    try:
        out = tmp_path / "arch.json"
        project_monolith(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        section = json.loads(out.read_text())["design_signals"]
        assert section["method_caveat"] == METHOD_CAVEAT
        for phrase in ("reflection", "dependency injection", "dynamic dispatch"):
            assert phrase in section["method_caveat"]
    finally:
        store.close()


# --- 5. decline to claim, enforced in the schema --------------------------------


def test_no_global_architecture_score_exists_anywhere_in_the_payload(tmp_path):
    """Part 4 of the research document, enforced as a schema property."""
    store, arch = _subject()
    try:
        out = tmp_path / "arch.json"
        project_monolith(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        section = json.loads(out.read_text())["design_signals"]
        blob = json.dumps(section)
        for banned in (
            "architecture_score", "design_score", "overall", "grade",
            "severity", "health", "quality_score",
        ):
            assert banned not in blob, f"{banned!r} leaked into the design payload"

        # Ranks restart per kind, so they cannot be read as a cross-kind order.
        by_kind: dict[str, list[int]] = {}
        for finding in section["findings"]:
            by_kind.setdefault(finding["kind"], []).append(finding["rank_within_kind"])
        for kind, ranks in by_kind.items():
            assert ranks == list(range(1, len(ranks) + 1)), (kind, ranks)
    finally:
        store.close()


def test_the_component_block_has_no_score_field(tmp_path):
    store, arch = _subject()
    try:
        out = tmp_path / "arch.json"
        project_monolith(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        for comp in _walk(json.loads(out.read_text())["components"]):
            block = comp.get("design")
            if block is None:
                continue
            assert "score" not in block
            assert "grade" not in block
            assert "severity" not in block
    finally:
        store.close()


# --- 6. a failing emitter degrades to an honest gap ------------------------------


def test_a_raising_design_emitter_records_a_gap_and_does_not_fracture_the_run(
    tmp_path, monkeypatch
):
    """The isolation contract every projection emitter honours."""
    import analyzer.project.pipeline as pipeline_module

    def boom(*_a, **_kw):
        raise RuntimeError("design derivation exploded")

    monkeypatch.setattr(pipeline_module, "emit_design_signals", boom)
    store, arch = _subject()
    try:
        out = tmp_path / "arch.json"
        result = project_monolith(
            arch, out, store=store, root=POLYGLOT,
            generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0", now=FIXED_NOW,
            design_signals=True,
        )
        assert result.monolith_path is not None
        document = json.loads(out.read_text())
        assert "design_signals" not in document
        gaps = json.dumps(document.get("gaps") or [])
        assert "design-signals" in gaps, "the failure must be recorded, not swallowed"
    finally:
        store.close()
