"""T6: final adjudication. Scripted responses, no model invoked.

What is under test:

  1. THE VERIFY PASSES ACTUALLY RUN. verify_identity, verify_edges and
     verify_findings have existed, been tested, and never been invoked by
     anything. P3 wires them, and their spend lands on the shared budget and in
     the run ledger because they receive a metered invoker.
  2. GROUNDING SPOT-CHECKS ASK THE QUESTION THE VALIDATOR CANNOT. The citation is
     real; does it support the claim? An unsupported verdict is recorded, not
     smoothed over.
  3. THE DISAGREEMENT RATE IS HONEST. Nothing sampled means undefined, not zero.
     A run that checked nothing agreed about nothing.
  4. THE SUBSTITUTION TEST IS APPLIED INDEPENDENTLY. A self-assessment of
     distinctiveness is the assessment a tier has no incentive to fail.
  5. IT REWRITES NOTHING. Component payloads are byte-identical before and after.
  6. SAMPLING IS STRATIFIED AND DETERMINISTIC.
"""

from __future__ import annotations

import copy
import json
import os

import pytest

from analyzer.derive import derive_all
from analyzer.derive.importance import ComponentImportance, ImportanceRanking
from analyzer.enrich.adjudicate import (
    GROUNDING_TARGET_KIND,
    AdjudicationOutcome,
    AdjudicationPhase,
    SpotCheck,
    SubstitutionCheck,
    build_digest,
    sample_by_importance,
)
from analyzer.enrich.contract import ContractState
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.ladder import CONTRACT_TARGET_KIND
from analyzer.enrich.pipeline import (
    LadderConfig,
    LadderPolicy,
    build_run_context,
    run_pipeline,
)
from analyzer.enrich.provenance import stamp_enrichment
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
FIXED_CLOCK = lambda: "2026-08-21T00:00:00+00:00"  # noqa: E731


# --- a store that already has a finished ladder run in it ---------------------


@pytest.fixture
def enriched(tmp_path):
    """A store carrying grounded contract states and component payloads."""
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    from analyzer.enrich.digest import DigestIndex
    from analyzer.enrich.partition import flatten_components

    index = DigestIndex.from_store(store)
    real_file = next(f["path"] for f in store.files() if f.get("lines"))
    comps = [c for c in flatten_components(arch.get("components", [])) if c.get("id")]
    for comp in comps:
        cid = comp["id"]
        stamp_enrichment(
            store, "component", cid,
            {
                "help_text": f"{cid} does a specific job nothing else in this "
                             "system does, and it is wired to its neighbours.",
                "data_handled": "records", "criticality": "supporting",
                "ai_enhanced_at": FIXED_CLOCK(), "ai_enhance_version": 2,
            },
            digest_index=index, commit_sha=None, clock=FIXED_CLOCK,
        )
        state = ContractState("component", cid, state="grounded", rung="sonnet")
        row = dict(state.to_dict())
        row["answers"] = {
            "purpose": {
                "claim": f"{cid} owns the request lifecycle for its area.",
                "status": "answered",
                "evidence": [{"kind": "file", "path": real_file, "line": 1}],
            },
            "place": {
                "claim": f"{cid} is imported by the service layer.",
                "status": "answered",
                "evidence": [{"kind": "file", "path": real_file, "line": 2}],
            },
        }
        stamp_enrichment(
            store, CONTRACT_TARGET_KIND, f"component:{cid}", row,
            digest_index=index, commit_sha=None, clock=FIXED_CLOCK,
        )
    store.commit()
    store.close()
    return {"db": db, "run_dir": tmp_path / "run", "components": [c["id"] for c in comps]}


class ScriptedAdjudicator:
    """Answers each adjudication prompt shape; records what it was asked."""

    def __init__(self, *, unsupported_questions=(), not_distinctive=False,
                 verify_ok=True):
        self.unsupported = set(unsupported_questions)
        self.not_distinctive = not_distinctive
        self.verify_ok = verify_ok
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if "auditing whether claims" in prompt:
            body = json.loads(prompt[prompt.index("CLAIMS AND THEIR EVIDENCE:") + 26:]
                              .split("\n\nReturn the JSON")[0])
            checks = []
            for claim in body["claims"]:
                bad = claim["question"] in self.unsupported
                checks.append({
                    "question": claim["question"],
                    "supported": not bad,
                    "confidence": "high",
                    "reason": "the cited line does not mention this" if bad else "",
                })
            return InvokeResult(ok=True, text=json.dumps({"checks": checks}),
                                cost_usd=0.001, usage={"input_tokens": 400, "output_tokens": 30})
        if "candidate components it might be describing" in prompt:
            candidates = json.loads(prompt[prompt.index("CANDIDATES:") + 11:]
                                    .split("\n\nReturn the JSON")[0])
            if self.not_distinctive:
                return InvokeResult(ok=True, cost_usd=0.001, text=json.dumps(
                    {"choice": None, "distinctive": False,
                     "reason": "this would fit any of them"}))
            return InvokeResult(ok=True, cost_usd=0.001, text=json.dumps(
                {"choice": candidates[0]["id"], "distinctive": True, "reason": "clear"}))
        # A verify pass prompt.
        if not self.verify_ok:
            return InvokeResult(ok=False, text="", error="unavailable")
        return InvokeResult(ok=True, cost_usd=0.001, text=json.dumps({
            "fields": {
                "name": {"status": "confirmed"}, "type": {"status": "confirmed"},
                "framework": {"status": "confirmed"}, "port": {"status": "confirmed"},
            },
            "prose_issues": [],
            "status": "confirmed", "confidence": "high", "reasoning": "matches",
            "verdict": "verified",
        }))


def _adjudicate(enriched, invoker, *, dry_run=False, policy=None):
    config = LadderConfig(
        store_path=enriched["db"], root=POLYGLOT, run_dir=enriched["run_dir"],
        policy=policy or LadderPolicy(), dry_run=dry_run,
    )
    ctx = build_run_context(config, invoker_factory=lambda spec: invoker,
                            clock=FIXED_CLOCK)
    try:
        run_pipeline(ctx, [AdjudicationPhase()])
        return ctx.results["p3_adjudication"], ctx
    finally:
        ctx.store.close()


# --- 1. the verify passes actually run ----------------------------------------


def test_the_phase_seven_verify_passes_are_finally_invoked(enriched):
    invoker = ScriptedAdjudicator()
    result, ctx = _adjudicate(enriched, invoker)

    outcome = result.data["adjudication"]
    assert outcome.identity, "verify_identity produced no report"
    assert outcome.identity["pass"] == "verify-identity"
    assert outcome.edges["pass"] == "verify-edges"
    assert outcome.findings["pass"] == "verify-findings"
    assert any("verify identity" in n for n in outcome.notes)


def test_verify_pass_spend_lands_on_the_shared_budget_and_in_the_ledger(enriched):
    """The reason the passes are wired rather than shelled out to."""
    invoker = ScriptedAdjudicator()
    _, ctx = _adjudicate(enriched, invoker)

    rungs = {row.rung for row in ctx.ledger}
    assert "verify-identity" in rungs
    assert "grounding-spot-check" in rungs
    assert ctx.budget.spent > 0
    assert all(row.phase == "p3_adjudication" for row in ctx.ledger)
    # Every call is metered against the binding that made it.
    assert all(row.model == "anthropic-claude-cli:opus" for row in ctx.ledger)


def test_a_verify_pass_that_raises_does_not_sink_the_phase(enriched, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("the pass exploded")

    monkeypatch.setattr("analyzer.enrich.adjudicate.verify_edges", boom)
    result, _ = _adjudicate(enriched, ScriptedAdjudicator())
    outcome = result.data["adjudication"]
    assert result.status == "ok"
    assert any("verify edges raised and was skipped" in n for n in outcome.notes)
    # The other passes still ran.
    assert outcome.identity


# --- 2 and 3. grounding spot-checks and an honest disagreement rate -----------


def test_a_supported_claim_produces_no_disagreement(enriched):
    invoker = ScriptedAdjudicator()
    result, _ = _adjudicate(enriched, invoker)
    outcome = result.data["adjudication"]
    assert outcome.checked > 0
    assert outcome.unsupported == []
    assert outcome.disagreement_rate() == 0.0


def test_an_unsupported_claim_is_recorded_with_its_reason(enriched):
    """Real evidence that does not carry the claim is the finding this exists for."""
    invoker = ScriptedAdjudicator(unsupported_questions=("purpose",))
    result, _ = _adjudicate(enriched, invoker)
    outcome = result.data["adjudication"]

    assert outcome.unsupported
    bad = outcome.unsupported[0]
    assert bad.question == "purpose"
    assert bad.supported is False
    assert "does not mention" in bad.reason
    assert bad.claim, "the claim itself is recorded, so the report can quote it"
    assert outcome.disagreement_rate() > 0
    assert any("disagreement rate" in n for n in outcome.notes)


def test_the_spot_check_prompt_says_existence_is_already_settled(enriched):
    invoker = ScriptedAdjudicator()
    _adjudicate(enriched, invoker)
    prompt = next(p for p in invoker.prompts if "auditing whether claims" in p)
    assert "has ALREADY been verified to exist" in prompt
    assert "The only question is SUFFICIENCY" in prompt
    assert "supported: false is the useful answer" in prompt


def test_the_digest_carries_evidence_pointers_and_not_the_narrative():
    state = ContractState("component", "svc", state="grounded", rung="sonnet")
    digest = build_digest(state, {
        "purpose": {"claim": "it routes requests", "status": "answered",
                    "evidence": [{"kind": "file", "path": "a.py", "line": 3,
                                  "extra": "should be dropped"}]},
        "place": {"claim": "unsure", "status": "uncertain", "evidence": []},
    })
    assert digest["target_id"] == "svc"
    assert digest["grounded_at_rung"] == "sonnet"
    # Only answered claims are audited; an uncertain one already failed the
    # contract and is not adjudication's business.
    assert [c["question"] for c in digest["claims"]] == ["purpose"]
    evidence = digest["claims"][0]["evidence"][0]
    assert evidence == {"kind": "file", "path": "a.py", "line": 3}
    assert "help_text" not in json.dumps(digest)


def test_nothing_sampled_means_undefined_not_zero(tmp_path):
    """A run that checked nothing agreed about nothing."""
    outcome = AdjudicationOutcome()
    assert outcome.disagreement_rate() is None
    assert outcome.substitution_failure_rate() is None
    assert outcome.to_dict()["disagreement_rate"] is None

    outcome.spot_checks.append(SpotCheck("component", "a", "purpose", "x", supported=True))
    assert outcome.disagreement_rate() == 0.0


def test_a_store_with_no_grounded_items_says_the_rate_is_undefined(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    store.close()

    result, _ = _adjudicate(
        {"db": db, "run_dir": tmp_path / "run", "components": []},
        ScriptedAdjudicator(),
    )
    outcome = result.data["adjudication"]
    assert outcome.disagreement_rate() is None
    assert any("it is undefined" in n for n in outcome.notes)


# --- 4. the substitution test, independently ----------------------------------


def test_a_description_that_fits_everything_is_a_confirmed_e4(enriched):
    invoker = ScriptedAdjudicator(not_distinctive=True)
    result, _ = _adjudicate(enriched, invoker)
    outcome = result.data["adjudication"]

    assert outcome.substitution_checks
    check = outcome.substitution_checks[0]
    assert check.distinctive is False
    assert check.confirmed_failure is True
    assert outcome.substitution_failure_rate() == 1.0
    assert any("did not identify" in n for n in outcome.notes)


def test_choosing_the_wrong_sibling_is_also_a_confirmed_failure():
    assert SubstitutionCheck("a", distinctive=True, chose="b").confirmed_failure is True
    assert SubstitutionCheck("a", distinctive=True, chose="a").confirmed_failure is False
    assert SubstitutionCheck("a", distinctive=False, chose="a").confirmed_failure is True


def test_the_substitution_prompt_makes_null_the_right_answer_when_ambiguous(enriched):
    invoker = ScriptedAdjudicator()
    _adjudicate(enriched, invoker)
    prompt = next(p for p in invoker.prompts if "candidate components" in p)
    assert "Answer null" in prompt
    assert "That is not a failure to answer: it is the finding" in prompt


# --- 5. it rewrites nothing ---------------------------------------------------


def test_adjudication_does_not_edit_a_single_payload_the_ladder_wrote(enriched):
    store = FactStore(str(enriched["db"]))
    try:
        before = copy.deepcopy({
            (r["target_kind"], r["target_id"]): r["payload"]
            for r in store.enrichment()
            if r["target_kind"] in ("component", CONTRACT_TARGET_KIND)
        })
    finally:
        store.close()

    _adjudicate(enriched, ScriptedAdjudicator(unsupported_questions=("purpose",)))

    store = FactStore(str(enriched["db"]))
    try:
        after = {
            (r["target_kind"], r["target_id"]): r["payload"]
            for r in store.enrichment()
            if r["target_kind"] in ("component", CONTRACT_TARGET_KIND)
        }
        kinds = {r["target_kind"] for r in store.enrichment()}
    finally:
        store.close()

    assert after == before, "P3 must judge the work, never edit it"
    # Its own verdicts are written, in their own rows.
    assert GROUNDING_TARGET_KIND in kinds


def test_the_verdicts_are_written_beside_the_run_report(enriched):
    _adjudicate(enriched, ScriptedAdjudicator(unsupported_questions=("place",)))
    written = enriched["run_dir"] / "adjudication.json"
    assert written.is_file()
    data = json.loads(written.read_text())
    assert data["checked"] > 0
    assert data["disagreement_rate"] is not None
    assert data["spot_checks"]


# --- 6. sampling --------------------------------------------------------------


def _states(n):
    return [ContractState("component", f"c{i:03d}", state="grounded") for i in range(n)]


def _ranking(n):
    items = [
        ComponentImportance(f"c{i:03d}", score=1.0 - (i / n), band=(i * 5) // n + 1)
        for i in range(n)
    ]
    return ImportanceRanking(items=items)


def test_sampling_is_stratified_across_bands_not_just_the_top():
    """The interesting failure is a ladder weakest where nobody is looking."""
    states, ranking = _states(100), _ranking(100)
    picked = sample_by_importance(states, ranking, 20)

    assert len(picked) == 20
    bands = {ranking.band_for(s.target_id) for s in picked}
    assert bands == {1, 2, 3, 4, 5}, "every band must be represented"
    # And the top band gets the largest share.
    counts = {}
    for s in picked:
        b = ranking.band_for(s.target_id)
        counts[b] = counts.get(b, 0) + 1
    assert counts[1] == max(counts.values())


def test_sampling_is_deterministic():
    states, ranking = _states(50), _ranking(50)
    first = [s.target_id for s in sample_by_importance(states, ranking, 12)]
    second = [s.target_id for s in sample_by_importance(list(reversed(states)), ranking, 12)]
    assert first == second


def test_sampling_never_exceeds_its_quota_or_the_population():
    states, ranking = _states(7), _ranking(7)
    assert len(sample_by_importance(states, ranking, 3)) == 3
    assert len(sample_by_importance(states, ranking, 100)) == 7
    assert sample_by_importance(states, ranking, 0) == []
    assert sample_by_importance([], ranking, 5) == []


def test_a_small_subject_still_checks_at_least_one_claim(enriched):
    """Reporting 'nothing sampled' on a small subject is honest but useless."""
    policy = LadderPolicy(spot_check_fraction=0.001, max_spot_checks=25)
    result, _ = _adjudicate(enriched, ScriptedAdjudicator(), policy=policy)
    assert result.data["adjudication"].checked >= 1


def test_the_spot_check_cap_is_respected(enriched):
    policy = LadderPolicy(spot_check_fraction=1.0, max_spot_checks=2)
    result, _ = _adjudicate(enriched, ScriptedAdjudicator(), policy=policy)
    outcome = result.data["adjudication"]
    sampled_targets = {c.target_id for c in outcome.spot_checks}
    assert len(sampled_targets) <= 2


# --- dry run ------------------------------------------------------------------


def test_a_dry_run_plans_the_sample_and_invokes_nothing(enriched):
    invoker = ScriptedAdjudicator()
    result, ctx = _adjudicate(enriched, invoker, dry_run=True)
    assert invoker.prompts == []
    assert ctx.ledger == []
    outcome = result.data["adjudication"]
    assert outcome.plan_preview
    assert all("band" in entry for entry in outcome.plan_preview)
    assert any("Nothing invoked" in n for n in outcome.notes)
