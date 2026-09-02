"""T10: determination, iteration policy, and the Run Report.

No model is invoked anywhere. A single scripted invoker plays every phase, which
is what makes the full-pipeline end-to-end test possible for nothing.

The contracts:

  1. THE UNIVERSAL GATES ARE ANSWERED BY CODE. A counter answers "did every item
     reach a terminal state" exactly; asking a model spends budget for a less
     reliable answer, and a mechanical verdict cannot be talked out of.
  2. A FORCED ROUND MUST CARRY A REASONED TARGET. One with no target is not run,
     and the report says why. A checkbox round costs budget and teaches nothing.
  3. "NOT DONE" NEEDS AN ORDER THAT WOULD CHANGE THE RESULT. Without one the
     verdict is downgraded, because a run cannot refuse to finish forever while
     naming nothing that would finish it.
  4. A NO-GAIN ROUND IS RECORDED AS A NO-GAIN ROUND. It is the finding that earns
     dialling the policy back, not a failure to hide.
  5. THE RUN REPORT IS WRITTEN EVEN ON PARTIAL FAILURE, and has every section the
     design requires.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from types import SimpleNamespace

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.contract import (
    CONTRACT_KEY,
    ContractState,
    build_census,
    required_questions,
)
from analyzer.enrich.determine import (
    DeterminationOutcome,
    DeterminationPhase,
    IterationRound,
    _adjudication_digest,
    _normalize_run_analysis,
    _operations_digest,
    build_determination_prompt,
    evaluate_universal,
)
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.orientation import Criterion, universal_criteria
from analyzer.enrich.partition import flatten_components
from analyzer.enrich.pipeline import (
    IterationPolicy,
    LadderConfig,
    LadderPolicy,
    LedgerRow,
    build_phases,
    build_run_context,
    run_ladder,
    run_pipeline,
)
from analyzer.enrich.prompts import split_cached_prompt
from analyzer.enrich.runreport import REQUIRED_SECTIONS, build_report, render_markdown
from analyzer.enrich.workorder import WorkOrder
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
FIXED_CLOCK = lambda: "2026-08-21T00:00:00+00:00"  # noqa: E731


def test_determination_census_changes_only_the_uncached_tail():
    common = dict(
        criteria=universal_criteria(), adjudication={"checked": 1},
        synthesis={"tours": []}, brief={"subject": "fixture"},
        forced_round=False, rounds_so_far=[], budget_note="BUDGET: bounded",
    )
    first = build_determination_prompt(
        census={"total": 2, "grounded": 1}, **common
    )
    second = build_determination_prompt(
        census={"total": 2, "grounded": 2}, **common
    )
    first_prefix, first_tail = split_cached_prompt(first)
    second_prefix, second_tail = split_cached_prompt(second)
    assert first_prefix == second_prefix
    assert first_tail != second_tail
    assert '"grounded":1' in first_tail
    assert '"grounded":2' in second_tail


def test_bounded_canary_scope_is_stable_and_forbids_full_repo_claims():
    prompt = build_determination_prompt(
        criteria=universal_criteria(), census={"total": 2}, adjudication=None,
        synthesis=None, brief={"subject": "fixture"}, forced_round=False,
        rounds_so_far=[], budget_note="BUDGET: bounded",
        scope_note=(
            "This is a bounded validation canary. Judge the attempted slice at "
            "full quality and do not claim the full repository is complete."
        ),
    )
    prefix, tail = split_cached_prompt(prompt)
    assert "RUN SCOPE" in prefix
    assert "full repository is complete" in prefix
    assert "RUN SCOPE" not in tail


def test_determination_adjudication_changes_only_the_uncached_tail():
    common = dict(
        criteria=universal_criteria(), census={"total": 2, "grounded": 2},
        synthesis={"tours": []}, brief={"subject": "fixture"},
        forced_round=False, rounds_so_far=[], budget_note="BUDGET: bounded",
    )
    first = build_determination_prompt(
        adjudication={"checked": 1, "unsupported": 1}, **common,
    )
    second = build_determination_prompt(
        adjudication={"checked": 2, "unsupported": 0}, **common,
    )
    first_prefix, first_tail = split_cached_prompt(first)
    second_prefix, second_tail = split_cached_prompt(second)

    assert first_prefix == second_prefix
    assert first_tail != second_tail
    assert '"unsupported":1' in first_tail
    assert '"unsupported":0' in second_tail


def test_determination_receives_measured_operations_in_the_uncached_tail():
    common = dict(
        criteria=universal_criteria(), census={"total": 2}, adjudication=None,
        synthesis=None, brief={"subject": "fixture"}, forced_round=False,
        rounds_so_far=[], budget_note="BUDGET: bounded",
    )
    first = build_determination_prompt(
        operations={"totals": {"calls": 4, "tokens_out": 900}}, **common
    )
    second = build_determination_prompt(
        operations={"totals": {"calls": 6, "tokens_out": 1200}}, **common
    )
    first_prefix, first_tail = split_cached_prompt(first)
    second_prefix, second_tail = split_cached_prompt(second)

    assert first_prefix == second_prefix
    assert first_tail != second_tail
    assert "MEASURED RUN OPERATIONS" in first_tail
    assert '"calls":4' in first_tail
    assert "run_analysis is the learning channel" in first_prefix


def test_operations_digest_preserves_exact_totals_and_bounds_only_prompt_examples():
    rows = [
        LedgerRow(
            phase="p2_ladder", rung="2a", model="sonnet", targets=3,
            tokens_in=100, tokens_cached=80, tokens_cache_write=90,
            tokens_out=40, response_bytes=120, cost_usd=0.2,
            wall_seconds=2.5,
        ),
        LedgerRow(
            phase="p3_adjudication", rung="check", model="opus", targets=1,
            tokens_in=30, tokens_out=10, response_bytes=50, cost_usd=0.1,
            wall_seconds=1.0, retries=1, ok=False,
        ),
    ]
    findings = [
        {"target_kind": "component", "target_id": f"c{i}",
         "finding": f"mechanical rule {i}"}
        for i in range(41)
    ]
    ladder = SimpleNamespace(
        transitions=[{
            "state": "escalate", "target_kind": "component", "target_id": "c0",
            "failed": [{"trigger": "E2"}],
        }],
        parser_findings=findings,
    )
    digest = _operations_digest(SimpleNamespace(ledger=rows), ladder)

    assert digest["totals"] == {
        "calls": 2, "targets": 4, "tokens_in": 130, "tokens_cached": 80,
        "tokens_cache_write": 90, "tokens_out": 50, "response_bytes": 170,
        "cost_usd": 0.3, "wall_seconds": 3.5, "retries": 1, "failures": 1,
        "output_budget_violations": 0, "cache_read_write_ratio": 0.8889,
    }
    assert digest["escalation"] == {
        "climbed_targets": 1, "failure_records_by_trigger": {"E2": 1},
    }
    assert digest["parser_first"]["distinct_count"] == 41
    assert len(digest["parser_first"]["examples"]) == 40
    assert digest["parser_first"]["examples_are_bounded"] is True


def test_run_analysis_is_bounded_without_dropping_the_learning_channel():
    analysis = _normalize_run_analysis({
        "summary": "measured conclusion",
        "deterministic_transfers": [
            {"finding": f"f{i}", "basis": f"b{i}", "validation": f"v{i}"}
            for i in range(8)
        ],
        "improvements": [{"area": "routing", "recommendation": "test E2",
                          "basis": "three E2 climbs"}],
        "watch_next_run": [f"signal {i}" for i in range(8)],
    })

    assert analysis["status"] == "model-analyzed"
    assert analysis["summary"] == "measured conclusion"
    assert len(analysis["deterministic_transfers"]) == 5
    assert len(analysis["watch_next_run"]) == 5
    assert analysis["improvements"][0]["basis"] == "three E2 climbs"


def test_determination_digest_carries_supported_claims_needed_by_criteria():
    digest = _adjudication_digest({
        "checked": 2,
        "unsupported": 1,
        "spot_checks": [
            {
                "target_kind": "component", "target_id": "services/api",
                "question": "data_handled",
                "claim": "The README names the API's Postgres driver.",
                "supported": True,
            },
            {
                "target_kind": "component", "target_id": "root",
                "question": "place", "claim": "Unsupported gloss.",
                "supported": False, "reason": "No exact evidence.",
            },
        ],
    })

    assert digest["checked_claims"][0] == {
        "target_kind": "component",
        "target_id": "services/api",
        "question": "data_handled",
        "claim": "The README names the API's Postgres driver.",
        "supported": True,
    }
    assert digest["unsupported_examples"][0]["target_id"] == "root"


def test_determination_digest_names_each_independently_refuted_edge():
    digest = _adjudication_digest({
        "edges": {
            "pass": "verify-edges", "target_count": 2, "done": 2,
            "verdicts": {"confirmed": 1, "refuted": 1},
            "outcomes": [
                {"id": "a|b|uses", "status": "done", "verdict": "refuted"},
                {"id": "a|c|uses", "status": "done", "verdict": "confirmed"},
            ],
        },
    })
    assert digest["verification"]["edges"]["outcomes"][0] == {
        "id": "a|b|uses", "status": "done", "verdict": "refuted",
    }


def test_determination_receives_parser_owned_inventory_in_the_stable_prefix():
    prompt = build_determination_prompt(
        criteria=universal_criteria(), census={"total": 2}, adjudication=None,
        synthesis=None, brief={"subject": "fixture"}, forced_round=False,
        rounds_so_far=[], budget_note="BUDGET: bounded",
        mechanical_map={
            "stats": {"total_components": 2, "languages": {"python": 1}},
            "components": [{"id": "api", "type": "api-server", "language": "python"}],
            "relationships": [], "readme": "Layout: api",
        },
    )
    prefix, _ = split_cached_prompt(prompt)
    assert prefix is not None
    assert "THE MECHANICAL MAP INVENTORY" in prefix
    assert '"total_components":2' in prefix
    assert '"id":"api"' in prefix


# --- 1. the universal gates are answered by code ------------------------------


def _census_of(*states):
    return build_census(list(states))


def test_u1_is_answered_by_counting_not_by_asking():
    u1 = next(c for c in universal_criteria() if c.id == "u1")

    clean = _census_of(ContractState("component", "a", state="grounded"))
    verdict = evaluate_universal(u1, census=clean, adjudication=None)
    assert verdict.verdict == "met"

    stuck = _census_of(
        ContractState("component", "a", state="grounded"),
        ContractState("component", "b", state="escalate"),
    )
    verdict = evaluate_universal(u1, census=stuck, adjudication=None)
    assert verdict.verdict == "unmet"
    assert "still asking to climb" in verdict.reasoning
    assert "unfinished work rather than a gap" in verdict.reasoning


def test_u2_is_unknown_when_nothing_was_spot_checked_not_met():
    """A run that checked nothing agreed about nothing."""
    from analyzer.enrich.adjudicate import AdjudicationOutcome

    u2 = next(c for c in universal_criteria() if c.id == "u2")
    census = _census_of(*[
        ContractState("component", f"c{i}", state="grounded") for i in range(10)
    ])

    unchecked = evaluate_universal(u2, census=census, adjudication=AdjudicationOutcome())
    assert unchecked.verdict == "unknown"
    assert "is unmeasured" in unchecked.reasoning

    from analyzer.enrich.adjudicate import SpotCheck

    checked = AdjudicationOutcome(spot_checks=[
        SpotCheck("component", "c0", "purpose", "x", supported=True)
    ])
    assert evaluate_universal(u2, census=census, adjudication=checked).verdict == "met"


def test_u2_is_unmet_when_adjudication_disputes_too_much():
    from analyzer.enrich.adjudicate import AdjudicationOutcome, SpotCheck

    u2 = next(c for c in universal_criteria() if c.id == "u2")
    census = _census_of(*[
        ContractState("component", f"c{i}", state="grounded") for i in range(10)
    ])
    disputed = AdjudicationOutcome(spot_checks=[
        SpotCheck("component", f"c{i}", "purpose", "x", supported=(i > 4))
        for i in range(10)
    ])
    verdict = evaluate_universal(u2, census=census, adjudication=disputed)
    assert verdict.verdict == "unmet"
    assert "would not stand behind" in verdict.reasoning


def test_u3_rejects_an_honest_gap_with_no_reason():
    """A silence dressed as a disclosure."""
    from analyzer.enrich.contract import FailedQuestion

    u3 = next(c for c in universal_criteria() if c.id == "u3")

    good = ContractState("component", "a", state="honest_gap")
    good.failed.append(FailedQuestion("mechanism", "E1", "generated at build time"))
    assert evaluate_universal(u3, census=_census_of(good), adjudication=None).verdict == "met"

    bare = ContractState("component", "b", state="honest_gap")
    bare.failed.append(FailedQuestion("mechanism", "E1", ""))
    verdict = evaluate_universal(u3, census=_census_of(bare), adjudication=None)
    assert verdict.verdict == "unmet"
    assert "silence dressed as a disclosure" in verdict.reasoning

    generic = ContractState("component", "c", state="honest_gap")
    generic.failed.append(FailedQuestion(
        "mechanism", "E1", "no answer was produced for a required question"
    ))
    verdict = evaluate_universal(u3, census=_census_of(generic), adjudication=None)
    assert verdict.verdict == "unmet"
    assert "no specific reason" in verdict.reasoning


# --- the full pipeline, end to end, on canned responses -----------------------


class FullPipelineInvoker:
    """Plays every phase from one script. The whole engine, for nothing."""

    def __init__(self, world, *, verdict="done", target="deepen the boundary "
                 "descriptions on the two services that face outward",
                 orders=True, gap_component=None):
        self.world = world
        self.verdict = verdict
        self.target = target
        self.orders = orders
        self.gap_component = gap_component
        self.prompts = []
        self.judged = 0

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if "orienting an automated enrichment pipeline" in prompt:
            return self._ok({
                "identity": "A tiny polyglot solution exercising every supported "
                            "language in the analyzer.",
                "audience": "An engineer checking whether their stack is covered.",
                "what_matters": ["language coverage", "the service boundary"],
                "criteria": [{
                    "id": "s1",
                    "statement": "Every language present is named on the component "
                                 "that carries it.",
                    "why": "Language coverage is the point of this subject.",
                    "how_to_check": "Compare stats.languages to component languages.",
                }],
                "idiom_warnings": ["the ruby package is deliberately logic-free"],
            })
        if "deciding whether an automated map" in prompt:
            self.judged += 1
            body = {
                "verdict": self.verdict,
                "reasoning": "The census shows the map supports a reader orienting "
                             "and finding the service boundary. It does not yet "
                             "support reasoning about failure modes.",
                "criteria": [{
                    "criterion_id": "s1", "verdict": "met",
                    "evidence": ["every component carries a language claim"],
                    "reasoning": "the census grounded identity.language throughout",
                }],
                "run_analysis": {
                    "summary": "The measured ledger shows a clean bounded run; "
                               "the parser-first card is the transferable lesson.",
                    "deterministic_transfers": [{
                        "finding": "The fixture framework is inferable from its manifest.",
                        "basis": "The same parser-first card survived every rung.",
                        "validation": "Add a real manifest extraction regression.",
                    }],
                    "improvements": [{
                        "area": "parser",
                        "recommendation": "Teach extraction the repeated manifest rule.",
                        "basis": "The exit digest contains one distinct parser-first card.",
                    }],
                    "watch_next_run": ["Compare parser-first cards and escalation count."],
                },
                "improvement_target": self.target,
            }
            if self.orders:
                body["work_orders"] = [{
                    "scope": self.world["components"][:2],
                    "lens": "the outward-facing boundary",
                    "criteria": "each boundary component names its inbound protocol",
                    "expected_effect": "truth: the grounded fraction should rise",
                    "budget": {"max_cost_usd": 1.0, "max_targets": 4},
                }]
            return self._ok(body)
        if "architecture-level summary" in prompt:
            return self._ok({
                "summary": "A small polyglot system with a web tier and an api "
                           "service, plus supporting packages in five languages.",
                "data_flow_narrative": "A request enters the web tier and is "
                                       "forwarded over http to the api service.",
            })
        if "story spine" in prompt:
            return self._ok({
                "tours": [{
                    "id": "the-request-path",
                    "title": "The request path",
                    "description": "How a request crosses the service boundary.",
                    "steps": [
                        {"target": cid, "title": f"Stop at {cid}",
                         "narration": f"What {cid} contributes to the request path.",
                         "evidence": {"file": self.world["real_file"], "line": 1}}
                        for cid in self.world["components"][:3]
                    ],
                }],
                "lenses": [{
                    "name": "language coverage as a claim",
                    "observation": "every package asserts a language but only two "
                                   "assert a framework",
                    "why_it_matters": "the reader is evaluating stack coverage",
                    "confidence": "medium",
                    "work_order": {
                        "scope": self.world["components"][:2],
                        "lens": "framework detection on the quiet packages",
                        "criteria": "each package either names a framework or says "
                                    "it has none",
                        "expected_effect": "truth: framework identity verdicts",
                        "budget": {"max_cost_usd": 0.5, "max_targets": 4},
                    },
                }],
            })
        if "auditing whether claims" in prompt:
            body = json.loads(prompt[prompt.index("CLAIMS AND THEIR EVIDENCE:") + 26:]
                              .split("\n\nReturn the JSON")[0])
            return self._ok({"checks": [
                {"question": c["question"], "supported": True, "confidence": "high"}
                for c in body["claims"]
            ]})
        if "candidate components it might be describing" in prompt:
            candidates = json.loads(prompt[prompt.index("CANDIDATES:") + 11:]
                                    .split("\n\nReturn the JSON")[0])
            return self._ok({"choice": candidates[0]["id"], "distinctive": True,
                             "reason": "it names its own files"})
        if (
            "SCOPED WORK ORDER" in prompt
            or "COMPONENTS (produce" in prompt
            or "HIGHER RUNG" in prompt
            or "LAST rung" in prompt
        ):
            return self._ok(self._enrichment(prompt))
        # A verify pass. The edge and identity passes are BATCHED: one call
        # carries many independent items and answers each by its own id, so a
        # fake model has to speak that protocol or every item reads as
        # unanswered. Per-item calls were 99% of a real run's invocations.
        ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
        if "FINDINGS AND EVIDENCE:" in prompt:
            return self._ok({"verdicts": {
                i: {"verdict": "verified", "reason": "the evidence holds up"}
                for i in ids
            }})
        if "EDGES AND EVIDENCE:" in prompt:
            return self._ok({"verdicts": {
                i: {"status": "confirmed", "reason": "the evidence shows it"}
                for i in ids
            }})
        if "COMPONENTS AND FACTS:" in prompt:
            return self._ok({"components": {
                i: {
                    "fields": {f: {"status": "confirmed"} for f in
                               ("name", "type", "framework", "port")},
                    "prose_issues": [],
                }
                for i in ids
            }})
        return self._ok({
            "fields": {f: {"status": "confirmed"} for f in
                       ("name", "type", "framework", "port")},
            "prose_issues": [], "status": "confirmed", "confidence": "high",
            "reasoning": "matches the store", "verdict": "verified",
        })

    def _enrichment(self, prompt):
        relationship_call = "ENRICHMENT TASK: relationships" in prompt
        ids = [] if relationship_call else [
            cid for cid in self.world["components"] if f'"{cid}"' in prompt
        ]
        if "HIGHER RUNG" in prompt or "LAST rung" in prompt:
            # An escalation prompt names its items explicitly; answer only those,
            # the way a real higher rung would.
            ids = [
                cid for cid in self.world["components"]
                if f'"target_id": "{cid}"' in prompt
            ]
        components = {}
        for cid in ids:
            questions = list(required_questions(
                "component", self.world["facts_by_id"].get(cid, {})
            ))
            if cid == self.gap_component and "LAST rung" not in prompt:
                questions = [q for q in questions if q != "mechanism"]
            components[cid] = {
                "help_text": f"{cid} carries one clear job in this system, wired "
                             "to the components either side of it, and nothing "
                             "else owns that job.",
                "description": f"the {cid} package",
                "data_handled": "source facts and identifiers",
                "criticality": "supporting",
                CONTRACT_KEY: {
                    "parser_first": (
                        [f"{cid}'s language was inferable from its manifest"]
                        if cid == self.gap_component else []
                    ),
                    "answers": {
                        q: {"claim": f"{cid}: a specific answer for {q}",
                            "status": "answered",
                            "evidence": [{"kind": "file",
                                          "path": self.world["real_file"], "line": 1}]}
                        for q in questions
                    },
                    "self_state": "grounded",
                    "confusion": None,
                    "substitution_check": f"only {cid} owns its own files",
                },
            }
            if cid == self.gap_component and "LAST rung" in prompt:
                components[cid]["honest_gaps"] = [{
                    "question": "mechanism",
                    "why": "the dispatch table is generated at build time and no "
                           "source file in the repository contains it",
                }]
                components[cid][CONTRACT_KEY]["answers"]["mechanism"] = {
                    "claim": "", "status": "dropped",
                    "reason": "generated at build time",
                }
        relationship_work = relationship_call or '"target_kind": "relationship"' in prompt
        relationships = {
            key: {
                "data_flow_description": "identifiers and request payloads",
                "importance": "internal",
                CONTRACT_KEY: {
                    "parser_first": [],
                    "answers": {
                        q: {"claim": f"the edge: {q}", "status": "answered",
                            "evidence": [{"kind": "file",
                                          "path": self.world["real_file"], "line": 1}]}
                        for q in ("flow", "why")
                    },
                    "self_state": "grounded",
                },
            }
            for key in self.world["relationships"] if relationship_work and key in prompt
        }
        return {"components": components, "relationships": relationships}

    def _ok(self, body):
        return InvokeResult(
            ok=True, text=json.dumps(body), cost_usd=0.01,
            usage={"input_tokens": 1200, "output_tokens": 300},
        )


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    flat = [c for c in flatten_components(arch.get("components", [])) if c.get("id")]
    real_file = next(f["path"] for f in store.files() if f.get("lines"))
    store.close()
    return {
        "db": db, "run_dir": tmp_path / "run", "arch": arch,
        "components": [c["id"] for c in flat],
        "facts_by_id": {c["id"]: c for c in flat},
        "relationships": [
            f"{r.get('source','')}|{r.get('target','')}|{r.get('type','')}"
            for r in arch.get("relationships", [])
        ],
        "real_file": real_file,
    }


def _full_run(world, invoker, *, min_rounds=1, max_rounds=2, run_dir=None):
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT,
        run_dir=run_dir or world["run_dir"],
        policy=LadderPolicy(
            iteration=IterationPolicy(min_rounds=min_rounds, max_rounds=max_rounds)
        ),
    )
    return run_ladder(
        config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK
    )


def test_the_whole_pipeline_runs_end_to_end_and_writes_a_complete_report(world):
    invoker = FullPipelineInvoker(world, gap_component=world["components"][2])
    result = _full_run(world, invoker)

    assert [p.name for p in result.phases] == [
        "p1_orientation", "p2_ladder", "p3_adjudication",
        "p4_synthesis", "p5_determination",
    ]
    assert result.ok is True, f"failed phases: {result.failed_phases}"

    report_json = world["run_dir"] / "report.json"
    report_md = world["run_dir"] / "REPORT.md"
    assert report_json.is_file() and report_md.is_file()

    report = json.loads(report_json.read_text())
    for section in REQUIRED_SECTIONS:
        assert section in report, f"the Run Report is missing {section}"

    # Every section has real content, not just a key.
    assert report["identity"]["subject"] == "polyglot"
    assert report["ledger"], "the ledger must record what was invoked"
    assert report["census"]["by_state"]
    assert report["census"]["total"] > 0
    assert report["criteria"], "the criteria P1 set must be answered"
    assert report["determination"]["verdict"] in (
        "done", "done-with-reservations", "not-done"
    )
    assert report["determination"]["reasoning"]
    assert report["run_analysis"]["status"] == "model-analyzed"
    assert report["run_analysis"]["deterministic_transfers"]
    assert report["iterations"], "the forced round must be recorded"
    assert report["parser_findings"], "the parser-first findings must be carried"
    assert report["lessons"]

    markdown = report_md.read_text()
    assert "# Enrichment Run Report: polyglot" in markdown
    assert "## Item census" in markdown
    assert "## Criteria" in markdown
    assert "## Work ledger" in markdown
    assert "## Run analysis" in markdown
    assert "### Deterministic-transfer candidates" in markdown
    assert "API-equivalent" in markdown
    assert "not money spent" in markdown


def test_the_end_to_end_run_produces_every_terminal_state_including_a_gap(world):
    gap = world["components"][2]
    invoker = FullPipelineInvoker(world, gap_component=gap)
    _full_run(world, invoker)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    by_state = report["census"]["by_state"]
    assert by_state.get("grounded@sonnet", 0) > 0
    assert by_state.get("honest-gap", 0) == 1
    assert report["census"]["unresolved"] == []

    gap_items = [
        e for e in report["escalations"] if e["terminal"] == "honest-gap"
    ]
    assert gap_items and gap_items[0]["target_id"] == gap
    # The gap must be one the upper rungs actually WORKED, not one the terminal
    # sweep produced because nothing absorbed at 2b or 2c. Asserting only the
    # terminal state passes either way, which is how a broken escalation path
    # can hide behind a green test.
    assert gap_items[0]["climbed_from"] == ["sonnet:escalate", "opus:escalate"], (
        "the gapped item must have been attempted at every rung"
    )
    assert gap_items[0]["resolved_at"] == "fable"


def test_the_ledger_names_which_binding_did_each_piece_of_work(world):
    invoker = FullPipelineInvoker(world)
    result = _full_run(world, invoker)
    report = json.loads((world["run_dir"] / "report.json").read_text())

    phases = {row["phase"] for row in report["ledger"]}
    assert {"p1_orientation", "p2_ladder", "p3_adjudication", "p4_synthesis",
            "p5_determination"} <= phases
    models = {row["model"] for row in report["ledger"]}
    assert "anthropic-claude-cli:sonnet" in models   # rung 2a
    assert "anthropic-claude-cli:opus" in models     # adjudication
    assert "anthropic-claude-cli:fable" in models    # orientation, synthesis, P5
    assert report["identity"]["totals"]["cost_usd"] == round(result.total_cost_usd, 6)


# --- 2. a forced round must carry a reasoned target ---------------------------


def test_a_forced_round_with_no_target_is_not_run_and_says_why(world):
    """A checkbox round costs the run and teaches nothing."""
    invoker = FullPipelineInvoker(world, target="", orders=True)
    _full_run(world, invoker, min_rounds=1)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    rounds = report["iterations"]
    assert rounds, "the attempted round must still be recorded"
    assert rounds[0]["forced"] is True
    assert rounds[0]["ran"] is False
    assert "must carry a reasoned target" in rounds[0]["notes"][0]


def test_a_forced_round_with_a_target_runs_even_when_the_verdict_is_done(world):
    """The Wave 1 forced-iteration decision, made real."""
    invoker = FullPipelineInvoker(world, verdict="done", orders=True)
    _full_run(world, invoker, min_rounds=1)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    rounds = report["iterations"]
    assert len(rounds) == 1
    assert rounds[0]["forced"] is True
    assert rounds[0]["ran"] is True
    assert rounds[0]["target"]
    assert rounds[0]["work_orders"]


def test_min_rounds_zero_runs_no_round_when_the_verdict_is_done(world):
    invoker = FullPipelineInvoker(world, verdict="done")
    _full_run(world, invoker, min_rounds=0)
    report = json.loads((world["run_dir"] / "report.json").read_text())
    assert report["iterations"] == []


def test_the_round_cap_bounds_a_run_that_keeps_saying_not_done(world):
    invoker = FullPipelineInvoker(world, verdict="not-done", orders=True)
    _full_run(world, invoker, min_rounds=1, max_rounds=2)
    report = json.loads((world["run_dir"] / "report.json").read_text())
    assert len(report["iterations"]) <= 2


def test_claims_still_rejected_at_round_bound_are_quarantined_before_verdict(world):
    class RejectingJudge(FullPipelineInvoker):
        def __call__(self, prompt):
            if "auditing whether claims" in prompt:
                body = json.loads(
                    prompt[prompt.index("CLAIMS AND THEIR EVIDENCE:") + 26:]
                    .split("\n\nReturn the JSON")[0]
                )
                return self._ok({"checks": [
                    {
                        "question": claim["question"],
                        "supported": claim["question"] != "purpose",
                        "confidence": "high",
                        "reason": (
                            "the evidence does not carry this purpose clause"
                            if claim["question"] == "purpose" else ""
                        ),
                    }
                    for claim in body["claims"]
                ]})
            return super().__call__(prompt)

    invoker = RejectingJudge(world, verdict="done", orders=False)
    _full_run(world, invoker, min_rounds=0, max_rounds=0)
    report = json.loads((world["run_dir"] / "report.json").read_text())

    assert report["adjudication"]["unsupported"] == 0
    assert report["census"]["by_state"].get("honest-gap", 0) > 0
    assert any(
        "deterministically quarantined" in note
        for note in report["determination"]["notes"]
    )
    assert not any(
        "independently unsupported" in str(order.get("lens") or "")
        for order in report["work_orders"]
    ), "the round bound must not leave a cosmetic unexecuted repair order"


def test_final_quarantine_reaches_a_fixed_point_when_recheck_exposes_a_sibling(world):
    class LayeredRejectingJudge(FullPipelineInvoker):
        def __call__(self, prompt):
            if "auditing whether claims" in prompt:
                body = json.loads(
                    prompt[prompt.index("CLAIMS AND THEIR EVIDENCE:") + 26:]
                    .split("\n\nReturn the JSON")[0]
                )
                questions = {claim["question"] for claim in body["claims"]}
                rejected = "purpose" if "purpose" in questions else (
                    "mechanism" if "mechanism" in questions else None
                )
                return self._ok({"checks": [
                    {
                        "question": claim["question"],
                        "supported": claim["question"] != rejected,
                        "confidence": "high",
                        "reason": (
                            "the cited evidence does not carry this clause"
                            if claim["question"] == rejected else ""
                        ),
                    }
                    for claim in body["claims"]
                ]})
            return super().__call__(prompt)

    invoker = LayeredRejectingJudge(world, verdict="done", orders=False)
    _full_run(world, invoker, min_rounds=0, max_rounds=0)
    report = json.loads((world["run_dir"] / "report.json").read_text())

    assert report["adjudication"]["unsupported"] == 0
    note = next(
        note for note in report["determination"]["notes"]
        if "adjudication fixed point" in note
    )
    assert "quarantined 2" in note


def test_the_forced_round_prompt_asks_for_a_real_target_not_the_cheapest_one(world):
    invoker = FullPipelineInvoker(world)
    _full_run(world, invoker, min_rounds=1)
    prompt = next(p for p in invoker.prompts if "deciding whether an automated map" in p)
    assert "must carry out at least one improvement round" in prompt
    assert "not the cheapest thing to say" in prompt
    assert "A round with" in prompt and "no genuine target is worse than no round" in prompt


# --- 3. "not done" needs an order that would change the result ----------------


def test_not_done_without_an_executable_order_is_downgraded(world):
    """A run cannot refuse to finish while naming nothing that would finish it."""
    invoker = FullPipelineInvoker(world, verdict="not-done", orders=False, target="")
    _full_run(world, invoker, min_rounds=0, max_rounds=2)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    determination = report["determination"]
    assert determination["verdict"] == "done-with-reservations"
    assert any("downgraded" in n for n in determination["notes"])


def test_the_determination_prompt_forbids_look_again(world):
    invoker = FullPipelineInvoker(world)
    _full_run(world, invoker)
    prompt = next(p for p in invoker.prompts if "deciding whether an automated map" in p)
    assert '"not-done" is only a legal verdict' in prompt
    assert "are not work orders" in prompt
    assert "cannot change parser facts" in prompt
    assert "Never issue a work order" in prompt
    assert "cover every subject criterion you mark" in prompt
    assert "aggregate disagreement rate" in prompt


def test_an_unmet_criterion_qualifies_a_done_verdict(world):
    class UnmetInvoker(FullPipelineInvoker):
        def __call__(self, prompt):
            result = super().__call__(prompt)
            if "deciding whether an automated map" in prompt:
                body = json.loads(result.text)
                body["criteria"] = [{
                    "criterion_id": "s1", "verdict": "unmet",
                    "evidence": ["two packages name no language"],
                    "reasoning": "language coverage is incomplete",
                }]
                return InvokeResult(ok=True, text=json.dumps(body), cost_usd=0.01)
            return result

    _full_run(world, UnmetInvoker(world, verdict="done"), min_rounds=0)
    report = json.loads((world["run_dir"] / "report.json").read_text())
    assert report["determination"]["verdict"] == "done-with-reservations"
    assert any("qualified" in n for n in report["determination"]["notes"])


def test_an_unknown_criterion_qualifies_a_done_verdict(world):
    class UnknownInvoker(FullPipelineInvoker):
        def __call__(self, prompt):
            result = super().__call__(prompt)
            if "deciding whether an automated map" in prompt:
                body = json.loads(result.text)
                body["criteria"] = [{
                    "criterion_id": "s1", "verdict": "unknown",
                    "evidence": ["one sampled claim remains unsupported"],
                    "reasoning": "the universal quality claim is not settled",
                }]
                return InvokeResult(
                    ok=True, text=json.dumps(body), cost_usd=0.01
                )
            return result

    _full_run(world, UnknownInvoker(world, verdict="done"), min_rounds=0)
    report = json.loads((world["run_dir"] / "report.json").read_text())
    assert report["determination"]["verdict"] == "done-with-reservations"
    assert any("s1:unknown" in n for n in report["determination"]["notes"])


def test_model_criterion_id_alias_is_normalized_without_losing_the_verdict():
    outcome = DeterminationOutcome()
    criterion = Criterion(id="s4", statement="The vendored boundary is clear.")

    DeterminationPhase()._merge_verdicts(
        outcome,
        [criterion],
        {},
        {"criteria": [{
            "id": "s4",
            "verdict": "unmet",
            "evidence": ["the component entry remains an honest gap"],
            "reasoning": "The criterion was answered under the documented alias.",
        }]},
    )

    assert outcome.verdicts[0].criterion_id == "s4"
    assert outcome.verdicts[0].verdict == "unmet"
    assert any("normalized" in note for note in outcome.notes)


def test_conflicting_criterion_ids_fail_closed():
    outcome = DeterminationOutcome()
    criterion = Criterion(id="s4", statement="The vendored boundary is clear.")

    DeterminationPhase()._merge_verdicts(
        outcome,
        [criterion],
        {},
        {"criteria": [{
            "criterion_id": "s4", "id": "s5", "verdict": "met",
        }]},
    )

    assert outcome.verdicts[0].verdict == "unknown"
    assert any("disagreed" in note for note in outcome.notes)


def test_all_met_after_a_real_round_settles_done_and_retains_follow_up():
    outcome = DeterminationOutcome(
        verdict="not-done",
        verdicts=[SimpleNamespace(verdict="met") for _ in range(8)],
        rounds=[IterationRound(number=1, forced=True, ran=True)],
        pending_orders=[WorkOrder(
            scope=["api"], lens="Polish one residual claim.",
            criteria="The residual claim is supported.",
            expected_effect="truth: residual disagreement falls",
            budget={"max_cost_usd": 1.0, "max_targets": 1},
        )],
    )

    DeterminationPhase()._settle(outcome, census=None)

    assert outcome.verdict == "done"
    assert len(outcome.pending_orders) == 1
    assert any("predeclared criterion is met" in note for note in outcome.notes)


# --- 4. a no-gain round is recorded as one ------------------------------------


def test_a_round_that_changes_nothing_is_recorded_as_a_no_gain_round(world):
    """The finding that earns dialling the policy back, not a failure to hide."""
    invoker = FullPipelineInvoker(world, verdict="done", orders=True)
    _full_run(world, invoker, min_rounds=1)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    round_ = report["iterations"][0]
    # Everything was already grounded, so the order cannot move the census.
    assert round_["ran"] is True
    assert round_["gained"] is False
    assert round_["measured_delta"]["changed"] == 0
    assert any("no measurable gain" in n for n in round_["notes"])

    markdown = (world["run_dir"] / "REPORT.md").read_text()
    assert "no measurable gain" in markdown

    lesson_kinds = {lesson["kind"] for lesson in report["lessons"]}
    assert "forced-iteration" in lesson_kinds


def test_measured_and_perceived_deltas_are_kept_apart():
    round_ = IterationRound(number=1, forced=True, target="x")
    round_.measured_delta = {"changed": 0}
    round_.perceived_delta = "it feels much clearer now"
    data = round_.to_dict()
    assert data["gained"] is False, "judgment does not get a vote on the measurement"
    assert data["perceived_delta_is_judgment"] is True
    assert data["measured_delta"]["changed"] == 0


def test_a_rung_move_or_lower_disagreement_is_a_measured_gain():
    rung_move = IterationRound(number=1, forced=True)
    rung_move.measured_delta = {"changed": 0, "rung_moves": ["services/api"]}
    assert rung_move.gained is True

    quality = IterationRound(number=1, forced=True)
    quality.measured_delta = {
        "changed": 0,
        "rung_moves": [],
        "adjudication_disagreement_before": 0.333333,
        "adjudication_disagreement_after": 0.0,
    }
    assert quality.gained is True


def test_first_round_order_is_expanded_to_every_independently_failed_claim():
    """One forced round must repair the judge's list, not a convenient subset."""
    existing = WorkOrder(
        scope=["services/api"],
        lens="Repair the API purpose.",
        criteria="The API purpose is supported.",
        expected_effect="truth: API purpose disagreement falls",
        budget={"max_cost_usd": 0.5, "max_targets": 1},
    )
    outcome = DeterminationOutcome(pending_orders=[existing])
    adjudication = SimpleNamespace(unsupported=[
        SimpleNamespace(target_id="services/api", question="mechanism"),
        SimpleNamespace(target_id="root", question="place"),
    ])
    ctx = SimpleNamespace(policy=SimpleNamespace(max_work_orders=3))

    DeterminationPhase()._ensure_adjudication_repair(
        outcome, adjudication, ctx
    )

    assert len(outcome.pending_orders) == 1, "do not buy a duplicate target pass"
    order = outcome.pending_orders[0]
    assert order.scope == ["root", "services/api"]
    assert "root:place" in order.lens
    assert "services/api:mechanism" in order.lens
    assert "must not repeat any phrase" in order.lens
    assert "exact missing evidence" in order.lens
    assert order.max_targets == 2
    assert order.max_cost_usd == 2.0
    assert any("expanded its first-round scope" in note for note in outcome.notes)
    assert sum(
        "expanded its first-round scope" in note for note in outcome.notes
    ) == 1


# --- 5. the report survives partial failure -----------------------------------


def test_a_report_is_written_even_when_the_determination_phase_fails(world):
    """A run with no report is a run nobody can audit."""

    class ExplodingP5(DeterminationPhase):
        def run(self, ctx):
            raise RuntimeError("the determination exploded")

    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(iteration=IterationPolicy(min_rounds=0, max_rounds=1)),
    )
    invoker = FullPipelineInvoker(world)
    phases = [p for p in build_phases(config.policy) if p.name != "p5_determination"]
    phases.append(ExplodingP5())

    result = run_ladder(
        config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK, phases=phases
    )

    assert "p5_determination" in result.failed_phases
    report_path = world["run_dir"] / "report.json"
    assert report_path.is_file(), "the report must survive a failed P5"
    report = json.loads(report_path.read_text())
    assert report["determination"]["verdict"] == "unknown"
    assert "nothing judged it" in report["determination"]["reasoning"]
    # The work that DID happen is still fully reported.
    assert report["census"]["total"] > 0
    assert report["ledger"]
    assert report["identity"]["totals"]["failed_phases"] == ["p5_determination"]


def test_a_report_from_a_run_where_nothing_ran_still_has_every_section(world):
    """The degenerate case: a report that says nothing happened, not no report."""
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(),
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: None, clock=FIXED_CLOCK
    )
    try:
        result = run_pipeline(ctx, [])
        report = build_report(ctx, result)
    finally:
        ctx.store.close()

    for section in REQUIRED_SECTIONS:
        assert section in report
    assert report["census"]["total"] == 0
    assert "enrichment did not run" in report["census"]["note"]
    assert report["determination"]["verdict"] == "unknown"
    markdown = render_markdown(report)
    assert "_No census: the ladder did not produce contract states._" in markdown
    assert "_Nothing was invoked._" in markdown


def test_the_rendered_report_states_the_cost_denomination_on_the_page(world):
    invoker = FullPipelineInvoker(world)
    _full_run(world, invoker)
    markdown = (world["run_dir"] / "REPORT.md").read_text()
    assert "API-equivalent units reported by the `claude` CLI" in markdown
    assert "metered" in markdown
    assert "They are not money spent." in markdown


def test_a_dry_run_of_the_whole_pipeline_invokes_nothing(world):
    invoker = FullPipelineInvoker(world)
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(), dry_run=True,
    )
    result = run_ladder(config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK)

    assert invoker.prompts == []
    assert result.ledger == []
    assert (world["run_dir"] / "report.json").is_file()
    report = json.loads((world["run_dir"] / "report.json").read_text())
    assert report["identity"]["dry_run"] is True
    assert report["ledger"] == []


# --- defects the reference report exposed, now pinned -------------------------


def test_a_declared_honest_gap_keeps_its_reason_on_the_contract_state(world):
    """u3 must pass for a WELL-BEHAVED gap, and bite only on a bare one.

    The terminal rung declaring a gap closes the question. Dropping the failed
    entry with it discarded the reason, which made a properly declared gap
    indistinguishable from one nobody could explain, and the universal gate then
    marked the good case unmet. The reason is the whole value of an honest gap.
    """
    gap = world["components"][2]
    invoker = FullPipelineInvoker(world, gap_component=gap)
    _full_run(world, invoker, min_rounds=0)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    u3 = next(c for c in report["criteria"] if c["criterion_id"] == "u3")
    assert u3["verdict"] == "met", u3["reasoning"]

    item = next(i for i in report["census"]["items"] if i["target_id"] == gap)
    assert item["state"] == "honest_gap"
    assert item["failed"], "the gap must keep the question it could not answer"
    assert "generated at build time" in item["failed"][0]["note"]


def test_the_gate_still_bites_on_a_gap_with_no_reason():
    """Fail-before contrast: the fix must not have turned u3 into a rubber stamp."""
    from analyzer.enrich.contract import FailedQuestion

    u3 = next(c for c in universal_criteria() if c.id == "u3")
    bare = ContractState("component", "b", state="honest_gap")
    bare.failed.append(FailedQuestion("mechanism", "E1", "   "))
    verdict = evaluate_universal(u3, census=_census_of(bare), adjudication=None)
    assert verdict.verdict == "unmet"


def test_one_capability_card_per_finding_naming_every_rung_that_raised_it(world):
    """Each rung asks the parser-first question, so the same finding arrives thrice.

    Listing it three times would inflate the number a reader uses to judge how
    much the parser is actually missing.
    """
    gap = world["components"][2]
    invoker = FullPipelineInvoker(world, gap_component=gap)
    _full_run(world, invoker, min_rounds=0)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    findings = report["parser_findings"]
    assert len(findings) == 1
    assert findings[0]["target_id"] == gap
    assert findings[0]["raised_at_rungs"] == ["sonnet", "opus", "fable"]


def test_an_item_touched_twice_is_not_reported_as_an_escalation(world):
    """Having history is not the same as having climbed.

    A work order re-enriching a grounded component accumulates history. Counting
    that as an escalation would report ordinary re-enrichment as the bulk rung
    struggling.
    """
    invoker = FullPipelineInvoker(world, verdict="done", orders=True)
    _full_run(world, invoker, min_rounds=1)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    for entry in report["escalations"]:
        climbed = any(":escalate" in h for h in entry["climbed_from"])
        assert climbed or entry["terminal"] == "honest-gap", (
            f"{entry['target_id']} is listed as an escalation but never escalated"
        )


def test_an_issued_but_unexecuted_order_is_marked_as_such(world):
    """An order the run knew would help and did not run is real information."""
    invoker = FullPipelineInvoker(world, verdict="done", orders=True)
    _full_run(world, invoker, min_rounds=1)

    report = json.loads((world["run_dir"] / "report.json").read_text())
    orders = report["work_orders"]
    assert orders
    assert any(o["executed"] for o in orders), "at least one order ran"
    assert any(not o["executed"] for o in orders), (
        "the P4 lens order was never executed and must say so"
    )
    markdown = (world["run_dir"] / "REPORT.md").read_text()
    assert "| Executed |" in markdown


def test_the_committed_reference_report_matches_what_the_engine_produces(world):
    """The fixture under tests/fixtures is the reference, and it must stay true.

    Regenerated by the same full-pipeline mock run. Two fields are normalized
    because they vary by machine: the absolute repo root and the commit sha.
    """
    reference_dir = os.path.join(FIXTURES, "enrichment-run")
    reference = json.loads(open(os.path.join(reference_dir, "report.json")).read())

    invoker = FullPipelineInvoker(world, gap_component=world["components"][2])
    _full_run(world, invoker, min_rounds=1, max_rounds=2)
    produced = json.loads((world["run_dir"] / "report.json").read_text())
    produced["identity"]["root"] = reference["identity"]["root"]
    produced["identity"]["commit"] = reference["identity"]["commit"]

    # Deliberate regeneration, which is what the assertion message asks for. An
    # env-gated path rather than a hand-edit, so the fixture can only ever be
    # replaced by something this pipeline actually produced.
    #     REGENERATE_REFERENCE_REPORT=1 pytest tests/test_enrich_determination.py -k reference
    if os.environ.get("REGENERATE_REFERENCE_REPORT") == "1":
        shutil.copy(
            world["run_dir"] / "report.json",
            os.path.join(reference_dir, "report.json"),
        )
        shutil.copy(
            world["run_dir"] / "REPORT.md",
            os.path.join(reference_dir, "REPORT.md"),
        )
        pytest.skip("reference report regenerated from this run")

    # Wall-clock seconds are the one genuinely non-deterministic field, and it
    # now appears twice: once per ledger row, and once per model in the
    # accounting section, which is derived from those same rows.
    for report in (reference, produced):
        for row in report["ledger"]:
            row["wall_seconds"] = 0.0
        accounting = report.get("accounting") or {}
        for bucket in accounting.get("by_model") or []:
            bucket["wall_seconds"] = 0.0
            if accounting.get("totals"):
                accounting["totals"]["wall_seconds"] = 0.0
            if report.get("audit"):
                report["audit"]["run_dir"] = "<run-dir>"

    assert produced == reference, (
        "the committed reference report no longer matches what the engine "
        "produces; regenerate it deliberately rather than editing it by hand"
    )
