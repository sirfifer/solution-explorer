"""Tests for P7-4: concern naming, intent conformance, finding verification.

The Claude invocation is mocked so these tests are hermetic and free; the real
bounded runs (a real concern name, a real intent violation, real finding
verdicts, with costs) are recorded in TASKS.md P7-4 Evidence.

Fixtures:
  - tests/fixtures/concerns: two services logging through different libraries,
    yielding one logging concern, an inconsistency finding, and orphan findings.
  - tests/fixtures/intents/audio_two: two independent audio pipeline packages
    (violates the single-audio-pipeline intent).
  - tests/fixtures/intents/audio_one: one audio pipeline package (satisfies it).
  - tests/fixtures/intents/solution-explorer-intents.json: the declared intent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.enrich import DigestIndex, apply_verdict_overlay, enrichment_staleness
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.intents import IntentFileError, load_intents
from analyzer.enrich.passes import (
    VerifyConfig,
    check_intents,
    name_concerns,
    verify_findings,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CONCERNS = os.path.join(FIXTURES, "concerns")
AUDIO_TWO = os.path.join(FIXTURES, "intents", "audio_two")
AUDIO_ONE = os.path.join(FIXTURES, "intents", "audio_one")
INTENTS_FILE = os.path.join(FIXTURES, "intents", "solution-explorer-intents.json")

FIXED_CLOCK = lambda: "2026-07-13T00:00:00+00:00"  # noqa: E731


def _build(tmp_path, src, name):
    db = tmp_path / f"{name}.db"
    store = FactStore(str(db))
    extract_repo(src, store)
    derive_all(store, name, root_path=src)
    store.commit()
    store.close()
    return db


# ---------------------------------------------------------------------------
# intents file loading
# ---------------------------------------------------------------------------

def test_load_intents_reads_declared_file():
    intents = load_intents(Path(INTENTS_FILE))
    assert len(intents) == 1
    assert intents[0].id == "single-audio-pipeline"
    assert "one audio pipeline" in intents[0].statement
    assert intents[0].scope == ["audio", "pipeline"]


def test_malformed_intents_file_raises(tmp_path):
    bad = tmp_path / "intents.json"
    bad.write_text('[{"statement": "no id here"}]', encoding="utf-8")
    with pytest.raises(IntentFileError):
        load_intents(bad)
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps([{"id": "a", "statement": "x"}, {"id": "a", "statement": "y"}]))
    with pytest.raises(IntentFileError):
        load_intents(dup)


# ---------------------------------------------------------------------------
# P7-4 sub-pass 1: concern naming
# ---------------------------------------------------------------------------

def _name_mock(name="Application Logging", desc="Shared logging concern."):
    def invoker(prompt):
        return InvokeResult(ok=True, text=json.dumps({"name": name, "description": desc}), cost_usd=0.01)
    return invoker


def test_concern_gets_domain_name_stamped_with_provenance(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS))
    report = name_concerns(cfg, invoker=_name_mock(), clock=FIXED_CLOCK)
    assert report.ok and report.done == 1

    store = FactStore(str(db))
    rows = [r for r in store.enrichment() if r["target_kind"] == "concern"]
    assert len(rows) == 1 and rows[0]["target_id"] == "concern:logging"
    assert rows[0]["payload"]["name"] == "Application Logging"
    # Provenance: digest matches the current concern digest.
    index = DigestIndex.from_store(store)
    assert rows[0]["derived_from_hash"] == index.for_target("concern", "concern:logging")
    assert rows[0]["derived_from_hash"] is not None
    store.close()


def test_concern_name_fills_projection_name_slot(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS))
    name_concerns(cfg, invoker=_name_mock("Structured Logging"), clock=FIXED_CLOCK)

    store = FactStore(str(db))
    _, arch = derive_all(store, "concerns", root_path=CONCERNS)
    apply_verdict_overlay(arch, store)
    concern = next(c for c in arch["concerns"] if c["id"] == "concern:logging")
    assert concern["name"] == "Structured Logging"  # the P6-8 name slot fills
    assert concern["title"] == "Logging"  # mechanical title still present
    store.close()


def test_concern_name_goes_stale_when_member_code_changes(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS))
    name_concerns(cfg, invoker=_name_mock(), clock=FIXED_CLOCK)

    store = FactStore(str(db))
    fresh = {r["target_id"]: r for r in enrichment_staleness(store) if r["target_kind"] == "concern"}
    assert fresh["concern:logging"]["stale"] is False
    store._conn.execute("UPDATE files SET content_hash = 'CHANGED' WHERE path = 'svc_a/app.py'")
    store.commit()
    stale = {r["target_id"]: r for r in enrichment_staleness(store) if r["target_kind"] == "concern"}
    assert stale["concern:logging"]["stale"] is True
    assert stale["concern:logging"]["payload"]["name"]  # name still served
    store.close()


# ---------------------------------------------------------------------------
# P7-4 sub-pass 2: intent conformance (the canonical fixture, both ways)
# ---------------------------------------------------------------------------

def _intent_mock():
    """A stand-in for the model's judgment that keys off the REAL store facts in
    the prompt: it counts audio-pipeline packages and reports a violation only
    when more than one is present. This exercises the real extract -> scope-facts
    -> prompt -> finding path; only the verdict itself is stubbed."""
    def invoker(prompt):
        marker = "INTENT AND AS-BUILT FACTS:"
        body = prompt[prompt.index(marker) + len(marker):].strip()
        obj, _ = json.JSONDecoder().raw_decode(body)
        comps = obj["as_built"]["components"]
        pipes = [
            c for c in comps
            if c.get("type") == "package"
            and "pipeline" in ((c.get("name") or "") + (c.get("id") or "")).lower()
        ]
        if len(pipes) > 1:
            return InvokeResult(ok=True, text=json.dumps({
                "satisfied": False, "confidence": "high",
                "reason": f"{len(pipes)} independent audio pipeline implementations",
                "violating_members": [{"component_id": c["id"], "why": "duplicate pipeline"} for c in pipes],
            }), cost_usd=0.01)
        return InvokeResult(ok=True, text=json.dumps({
            "satisfied": True, "confidence": "high",
            "reason": "a single audio pipeline is present", "violating_members": [],
        }), cost_usd=0.01)
    return invoker


def test_intent_violation_emitted_for_two_pipelines(tmp_path):
    db = _build(tmp_path, AUDIO_TWO, "audio_two")
    cfg = VerifyConfig(store_path=db, root=Path(AUDIO_TWO), intents_path=Path(INTENTS_FILE))
    report = check_intents(cfg, invoker=_intent_mock(), clock=FIXED_CLOCK)
    assert report.ok and report.tally() == {"violation": 1}

    store = FactStore(str(db))
    rows = [r for r in store.enrichment() if r["target_kind"] == "finding"]
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["kind"] == "intent-violation"
    assert payload["verification_status"] == "unverified"
    assert len(payload["members"]) == 2
    assert {m["component_id"] for m in payload["members"]} == {
        "services/pipeline_alpha", "services/pipeline_beta"
    }
    # The violation finding surfaces in the projection findings index.
    _, arch = derive_all(store, "audio_two", root_path=AUDIO_TWO)
    apply_verdict_overlay(arch, store)
    ids = {f["id"] for f in arch["findings"]}
    assert "finding:intent-violation:single-audio-pipeline" in ids
    store.close()


def test_no_violation_for_single_pipeline(tmp_path):
    db = _build(tmp_path, AUDIO_ONE, "audio_one")
    cfg = VerifyConfig(store_path=db, root=Path(AUDIO_ONE), intents_path=Path(INTENTS_FILE))
    report = check_intents(cfg, invoker=_intent_mock(), clock=FIXED_CLOCK)
    assert report.ok and report.tally() == {"satisfied": 1}
    store = FactStore(str(db))
    assert [r for r in store.enrichment() if r["target_kind"] == "finding"] == []
    store.close()


def test_satisfied_intent_clears_a_prior_violation(tmp_path):
    # First a violation is recorded, then a re-check that is now satisfied must
    # remove the stale violation finding (no silent stale data).
    db = _build(tmp_path, AUDIO_TWO, "audio_two")
    cfg = VerifyConfig(store_path=db, root=Path(AUDIO_TWO), intents_path=Path(INTENTS_FILE))
    check_intents(cfg, invoker=_intent_mock(), clock=FIXED_CLOCK)

    def now_satisfied(prompt):
        return InvokeResult(ok=True, text=json.dumps({
            "satisfied": True, "confidence": "high", "reason": "consolidated", "violating_members": [],
        }), cost_usd=0.01)

    check_intents(cfg, invoker=now_satisfied, clock=FIXED_CLOCK)
    store = FactStore(str(db))
    assert [r for r in store.enrichment() if r["target_kind"] == "finding"] == []
    store.close()


def test_no_intents_file_is_a_clean_noop(tmp_path):
    db = _build(tmp_path, AUDIO_ONE, "audio_one")
    # No intents file at the (fixture) root and none passed.
    cfg = VerifyConfig(store_path=db, root=Path(AUDIO_ONE), intents_path=None)
    report = check_intents(cfg, invoker=_intent_mock(), clock=FIXED_CLOCK)
    assert report.ok and report.target_count == 0
    assert any("no declared-intents file" in n for n in report.notes)


def test_intent_proposals_are_advisory_only(tmp_path):
    db = _build(tmp_path, AUDIO_TWO, "audio_two")
    cfg = VerifyConfig(
        store_path=db, root=Path(AUDIO_TWO), intents_path=Path(INTENTS_FILE),
        propose_intents=True,
    )

    def invoker(prompt):
        if "PROPOSING candidate" in prompt:
            return InvokeResult(ok=True, text=json.dumps({
                "candidates": [{"id": "one-pipeline", "statement": "single pipeline", "basis": "two pipelines seen"}]
            }), cost_usd=0.01)
        return _intent_mock()(prompt)

    report = check_intents(cfg, invoker=invoker, clock=FIXED_CLOCK)
    # Proposals land in the report only, never stored as intents or auto-adopted.
    assert report.extra["proposed_intents"][0]["id"] == "one-pipeline"
    store = FactStore(str(db))
    assert not any(r["target_kind"] == "intent" for r in store.enrichment())
    store.close()


# ---------------------------------------------------------------------------
# P7-4 sub-pass 3: adversarial finding verification
# ---------------------------------------------------------------------------

def _finding_verify_mock(mapping):
    """mapping: finding-id-substring -> (verdict, reason)."""
    def invoker(prompt):
        body = prompt[prompt.index("FINDING:") + len("FINDING:"):].strip()
        obj, _ = json.JSONDecoder().raw_decode(body)
        fid = obj["finding"]["id"]
        for sub, (verdict, reason) in mapping.items():
            if sub in fid:
                return InvokeResult(ok=True, text=json.dumps({"verdict": verdict, "reason": reason}), cost_usd=0.01)
        return InvokeResult(ok=True, text=json.dumps({"verdict": "uncertain", "reason": "thin"}), cost_usd=0.01)
    return invoker


def test_finding_verification_flips_status_and_survives_reprojection(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS))
    # Verify one finding, refute another, leave the rest uncertain.
    mock = _finding_verify_mock({
        "inconsistency": ("refuted", "the two loggers are intentional"),
        "unreferenced:svc_a": ("verified", "svc_a genuinely has no inbound edges"),
    })
    report = verify_findings(cfg, invoker=mock, clock=FIXED_CLOCK)
    assert report.ok
    tally = report.tally()
    assert tally.get("verified", 0) >= 1 and tally.get("refuted", 0) >= 1

    store = FactStore(str(db))
    # A fresh derive resets the findings table to unverified, but the overlay
    # (durable enrichment record) re-applies the verdicts at projection time.
    _, arch = derive_all(store, "concerns", root_path=CONCERNS)
    apply_verdict_overlay(arch, store)
    by_id = {f["id"]: f for f in arch["findings"]}
    verified = by_id["finding:unreferenced:svc_a"]
    assert verified["verification_status"] == "verified"
    inconsistency = next(f for f in arch["findings"] if f["kind"] == "inconsistency")
    assert inconsistency["verification_status"] == "refuted"
    # A refuted finding is retained and de-emphasized, never deleted.
    assert inconsistency["de_emphasized"] is True
    assert inconsistency["id"] in by_id
    store.close()


def test_uncertain_finding_stays_unverified(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS))
    report = verify_findings(cfg, invoker=_finding_verify_mock({}), clock=FIXED_CLOCK)
    assert report.ok
    store = FactStore(str(db))
    _, arch = derive_all(store, "concerns", root_path=CONCERNS)
    apply_verdict_overlay(arch, store)
    for f in arch["findings"]:
        assert f["verification_status"] == "unverified"  # uncertain never asserts
    store.close()


def test_invalid_finding_verdict_not_written(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS), max_targets=1)

    def bad(prompt):
        return InvokeResult(ok=True, text=json.dumps({"verdict": "yes", "reason": "x"}), cost_usd=0.01)

    report = verify_findings(cfg, invoker=bad, clock=FIXED_CLOCK)
    assert not report.ok
    store = FactStore(str(db))
    assert [r for r in store.enrichment() if r["target_kind"] == "finding-verdict"] == []
    store.close()


def test_finding_verification_dry_run_invokes_nothing(tmp_path):
    db = _build(tmp_path, CONCERNS, "concerns")
    cfg = VerifyConfig(store_path=db, root=Path(CONCERNS), dry_run=True)

    def explode(prompt):
        raise AssertionError("must not invoke on dry run")

    report = verify_findings(cfg, invoker=explode, clock=FIXED_CLOCK)
    assert report.dry_run and report.target_count > 0
    store = FactStore(str(db))
    assert [r for r in store.enrichment() if r["target_kind"] == "finding-verdict"] == []
    store.close()


def test_intent_violation_findings_are_also_verified(tmp_path):
    # sub-pass 3 covers intent-violation findings (from enrichment), not just the
    # deterministic table findings.
    db = _build(tmp_path, AUDIO_TWO, "audio_two")
    cfg = VerifyConfig(store_path=db, root=Path(AUDIO_TWO), intents_path=Path(INTENTS_FILE))
    check_intents(cfg, invoker=_intent_mock(), clock=FIXED_CLOCK)

    verify_findings(cfg, invoker=_finding_verify_mock({
        "intent-violation": ("verified", "two pipelines confirmed in the facts"),
    }), clock=FIXED_CLOCK)

    store = FactStore(str(db))
    vrows = {r["target_id"]: r for r in store.enrichment() if r["target_kind"] == "finding-verdict"}
    assert "finding:intent-violation:single-audio-pipeline" in vrows
    assert vrows["finding:intent-violation:single-audio-pipeline"]["payload"]["verification_status"] == "verified"
    store.close()
