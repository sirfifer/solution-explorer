"""Fault-isolation proof for the derive driver (card R1).

Behavioral tests over the REAL extract -> derive path (no mocking of the unit
under test): a temp repo is written to disk, extracted into a fact store, and
derived. A fault is injected into a REAL derive pass (the pass function itself is
replaced with one that raises, exactly as a genuine bug in that pass would
behave), and we prove the run completes with a deterministic honest gap instead
of crashing, and that the honest gap reaches the on-disk projection the viewer
loads. A healthy run records no gaps and carries no gaps key (byte parity).

Fail-before context: before R1, derive_all called each pass as a bare statement,
so any pass raising propagated straight out and crashed the whole run. These
tests would fail (raise) against that pre-R1 code; they pass now because each
pass runs under per-unit isolation.
"""

from __future__ import annotations

import json

from analyzer.derive import capabilities as capabilities_pass
from analyzer.derive import derive_all
from analyzer.derive import pipeline as derive_pipeline
from analyzer.derive import relationships as rel_pass
from analyzer.extract import extract_repo
from analyzer.project.pipeline import project_monolith
from analyzer.store import FactStore


def _boom(*_args, **_kwargs):
    raise RuntimeError("injected pass fault")


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_repo(root):
    _write(root, "app/main.py", "def handler(req):\n    return {'ok': True}\n")
    _write(root, "app/db.py", "class User:\n    id = 0\n    name = ''\n")
    _write(root, "README.md", "# Sample\n\nA small sample application.\n")


def _extract(root) -> FactStore:
    (root / ".se").mkdir(parents=True, exist_ok=True)
    store = FactStore(str(root / ".se" / "index.db"))
    extract_repo(root, store)
    return store


def test_healthy_run_records_no_gaps_key(tmp_path):
    # Byte-parity guard: a clean run must not add the gaps key at all, so a
    # run with no gaps adds no bytes (the golden gate and byte-parity tests
    # depend on this).
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    _, arch = derive_all(store, "sample", root_path=str(tmp_path))
    assert "gaps" not in arch
    store.close()


def test_failing_relationships_pass_degrades_to_honest_gap(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    # Replace the REAL relationships pass with one that raises (a genuine bug in
    # that pass behaves identically). Pre-R1 this crashed the whole run.
    monkeypatch.setattr(rel_pass, "derive_relationships", _boom)
    _, arch = derive_all(store, "sample", root_path=str(tmp_path))  # must NOT raise
    gaps = arch.get("gaps", [])
    gap = next((g for g in gaps if g["producer"] == "derive.relationships"), None)
    assert gap is not None
    assert gap["stage"] == "derive"
    assert gap["status"] == "failed"
    assert gap["reason"] == "RuntimeError: injected pass fault"
    # The rest of the run still produced a whole architecture (not a fracture).
    assert arch["name"] == "sample"
    assert isinstance(arch["components"], list) and arch["components"]
    assert isinstance(arch["symbols"], list) and arch["symbols"]
    store.close()


def test_failing_capabilities_pass_also_isolated(tmp_path, monkeypatch):
    # A second, independent producer: proves the isolation is a driver-level
    # property, not a one-off around relationships.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(capabilities_pass, "derive_capabilities", _boom)
    _, arch = derive_all(store, "sample", root_path=str(tmp_path))  # must NOT raise
    producers = {g["producer"] for g in arch.get("gaps", [])}
    assert "derive.capabilities" in producers
    assert arch["components"]  # the run completed whole
    store.close()


def test_injected_gap_is_deterministic_across_runs(tmp_path, monkeypatch):
    # Same input, same gap: two fresh extractions of identical content with the
    # same injected fault must produce byte-identical gap records, so parity and
    # the golden gate hold even on a degraded run.
    monkeypatch.setattr(rel_pass, "derive_relationships", _boom)
    seen = []
    for i in range(2):
        root = tmp_path / f"run{i}"
        _build_repo(root)
        store = _extract(root)
        _, arch = derive_all(store, "sample", root_path=str(root))
        seen.append(arch.get("gaps"))
        store.close()
    assert seen[0] == seen[1]
    assert seen[0]  # non-empty


def test_output_contract_violation_surfaces_as_gap(tmp_path, monkeypatch):
    # The self-validating-output half: if the assembled result violates its
    # shape-and-completeness contract at handoff, that is a recorded honest gap,
    # not a crash. Inject a count inconsistency into the assembled arch.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    real_assemble = derive_pipeline._assemble

    def broken_assemble(d, root_name, root_path, desc):
        arch = real_assemble(d, root_name, root_path, desc)
        arch["stats"]["total_symbols"] = 999999  # now inconsistent with the array
        return arch

    monkeypatch.setattr(derive_pipeline, "_assemble", broken_assemble)
    _, arch = derive_all(store, "sample", root_path=str(tmp_path))  # must NOT raise
    producers = {g["producer"] for g in arch.get("gaps", [])}
    assert "derive.output-contract" in producers
    store.close()


def test_gap_reaches_the_monolith_projection(tmp_path, monkeypatch):
    # End-to-end: a derive-pass gap must ride through to the on-disk projection
    # the viewer loads (write_monolith copies every arch key), so the honest gap
    # is visible to a consumer, not lost between derive and projection.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(rel_pass, "derive_relationships", _boom)
    _, arch = derive_all(store, "sample", root_path=str(tmp_path))
    out = tmp_path / "architecture.json"
    project_monolith(
        arch, out, store=store, root=tmp_path,
        generated_at="2026-01-01T00:00:00Z", analyzer_version="1.2.0",
    )
    store.close()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert "gaps" in doc
    assert any(g["producer"] == "derive.relationships" for g in doc["gaps"])
