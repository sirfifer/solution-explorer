"""Repository identity is a release contract across the enrichment pipeline."""

from __future__ import annotations

import json
from types import SimpleNamespace

from analyzer.enrich.determine import (
    _subject_identity_verdict,
    build_determination_prompt,
)
from analyzer.enrich.engine import (
    InvokeResult,
    _enhance_architecture,
    _select_update_targets,
)
from analyzer.enrich.orientation import (
    Criterion,
    build_orientation_prompt,
    universal_criteria,
)
from analyzer.enrich.prompts import build_architecture_prompt
from analyzer.enrich.subject_identity import (
    CANONICAL_MODE,
    DECLARED_VARIANT_MODE,
    SUBJECT_IDENTITY_CONTRACT_VERSION,
    build_subject_identity,
    subject_identity_errors,
)

IDENTITY_BAD_SUMMARY = (
    "This is a fork of unrelated-upstream (canonical product's open-source codebase) heavily "
    "extended with AI capabilities. It is distinguished from upstream canonical product."
)


def test_canonical_snapshot_is_the_fail_closed_default():
    identity = build_subject_identity({
        "name": "canonical-product",
        "repository": "https://example.invalid/canonical-product.git",
        "default_branch": "main",
    }, commit_sha="474a349a")

    assert identity["mode"] == CANONICAL_MODE
    assert identity["repository"] == "https://example.invalid/canonical-product.git"
    assert "Package and product names" in identity["meaning"]


def test_variant_requires_an_explicit_complete_operator_declaration():
    implicit = build_subject_identity({
        "name": "product",
        "subject_representation": {
            "kind": "fork", "description": "Customer-maintained fork",
        },
    })
    explicit = build_subject_identity({
        "name": "product",
        "subject_representation": {
            "explicit": True,
            "kind": "fork",
            "description": "Customer-maintained fork of the public product",
        },
    })

    assert implicit["mode"] == CANONICAL_MODE
    assert explicit["mode"] == DECLARED_VARIANT_MODE
    assert explicit["variant_kind"] == "fork"


def test_identity_failure_is_rejected_but_a_vendored_child_fork_is_not():
    identity = build_subject_identity({"name": "canonical-product"})

    assert subject_identity_errors({"summary": IDENTITY_BAD_SUMMARY}, identity)
    assert not subject_identity_errors({
        "summary": (
            "canonical product contains a vendored fork of an autocomplete "
            "parser alongside its editor and workbench components."
        ),
        "data_flow_narrative": "The workbench sends commands to editor services.",
    }, identity)


def test_explicit_variant_declaration_permits_the_declared_relationship():
    identity = build_subject_identity({
        "name": "customer-product",
        "subject_representation": {
            "explicit": True,
            "kind": "fork",
            "description": "Customer fork maintained from the public repository",
        },
    })

    assert not subject_identity_errors({"summary": "This is a fork of product."}, identity)


def test_architecture_prompt_receives_repository_and_snapshot_semantics():
    facts = SimpleNamespace(arch={
        "name": "canonical-product", "components": [], "relationships": [], "stats": {},
    })
    identity = build_subject_identity({
        "name": "canonical-product",
        "repository": "https://example.invalid/canonical-product.git",
    }, commit_sha="474a349a")

    prompt = build_architecture_prompt(facts, subject_identity=identity)

    assert "https://example.invalid/canonical-product.git" in prompt
    assert "474a349a" in prompt
    assert "local clone/worktree is only the acquisition mechanism" in prompt
    assert "internal package/product name" in prompt


def test_orientation_and_universal_release_bar_share_the_identity_contract():
    identity = build_subject_identity({
        "name": "canonical-product",
        "repository": "https://example.invalid/canonical-product.git",
    }, commit_sha="474a349a")
    prompt = build_orientation_prompt(
        name="canonical-product", description="", stats={}, readme="",
        top_components=[], ranking_note="structure only",
        subject_identity=identity,
    )

    assert "AUTHORITATIVE SUBJECT IDENTITY" in prompt
    assert "release constraint" in prompt
    assert any(criterion.id == "u4" for criterion in universal_criteria())


def test_final_review_sees_the_actual_narrative_and_identity_contract():
    prompt = build_determination_prompt(
        criteria=[], census={}, adjudication=None, synthesis=None, brief=None,
        forced_round=False, rounds_so_far=[], budget_note="BUDGET: none",
        subject_identity=build_subject_identity({
            "name": "canonical-product",
            "repository": "https://example.invalid/canonical-product.git",
        }, commit_sha="474a349a"),
        architecture_narrative={"summary": IDENTITY_BAD_SUMMARY},
    )

    assert "THE ACTUAL PUBLISHED ARCHITECTURE NARRATIVE YOU MUST REVIEW" in prompt
    assert IDENTITY_BAD_SUMMARY in prompt
    assert "Repository identity is a publication fact" in prompt


def test_final_review_mechanically_fails_the_identity_regression(tmp_path):
    class Store:
        def enrichment(self):
            return [{
                "target_kind": "architecture",
                "commit_sha": "474a349a",
                "payload": {
                    "summary": IDENTITY_BAD_SUMMARY,
                    "data_flow_narrative": "Requests flow through editor services.",
                },
            }]

    ctx = SimpleNamespace(
        arch={
            "name": "canonical-product",
            "repository": "https://example.invalid/canonical-product.git",
        },
        root=tmp_path,
        commit_sha="474a349a",
        store=Store(),
    )
    criterion = Criterion(id="u4", statement="Subject identity is truthful.")

    verdict = _subject_identity_verdict(ctx, criterion)

    assert verdict.verdict == "unmet"
    assert any("unsupported subject-identity claim" in item for item in verdict.evidence)


def test_architecture_pass_repairs_an_identity_violation_before_writing():
    class Scorer:
        @staticmethod
        def validate_observation(_observation, _index):
            return []

    class Invoker:
        def __init__(self):
            self.prompts = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            summary = (
                IDENTITY_BAD_SUMMARY
                if len(self.prompts) == 1
                else "canonical product is represented at the analyzed repository snapshot."
            )
            return InvokeResult(ok=True, text=json.dumps({
                "summary": summary,
                "data_flow_narrative": "Requests flow through editor services.",
            }))

    facts = SimpleNamespace(arch={
        "name": "canonical-product", "components": [], "relationships": [], "stats": {},
    })
    invoker = Invoker()
    identity = build_subject_identity({
        "name": "canonical-product",
        "repository": "https://example.invalid/canonical-product.git",
    }, commit_sha="474a349a")

    payload, _cost, errors = _enhance_architecture(
        facts, Scorer(), invoker, lambda: "now", subject_identity=identity
    )

    assert not errors
    assert payload["summary"].startswith("canonical product is represented")
    assert len(invoker.prompts) == 2
    assert "unsupported subject-identity claim" in invoker.prompts[1]


def test_update_migrates_a_digest_fresh_legacy_architecture_row():
    class Store:
        def enrichment(self):
            return [{
                "target_kind": "architecture",
                "target_id": "@architecture",
                "derived_from_hash": "same",
                "payload": {
                    "summary": "A useful but legacy summary.",
                    "data_flow_narrative": "Requests flow through services.",
                },
            }]

    class Index:
        architecture = "same"

        @staticmethod
        def for_target(_kind, _target):
            return "same"

    targets, regenerate = _select_update_targets(
        Store(), {"name": "sample", "components": [], "relationships": []}, Index()
    )

    assert targets == set()
    assert regenerate is True


def test_update_keeps_a_contract_current_truthful_architecture_row():
    class Store:
        def enrichment(self):
            return [{
                "target_kind": "architecture",
                "target_id": "@architecture",
                "derived_from_hash": "same",
                "payload": {
                    "summary": "The analyzed sample repository provides an API.",
                    "data_flow_narrative": "Requests flow through services.",
                    "subject_identity_contract_version": (
                        SUBJECT_IDENTITY_CONTRACT_VERSION
                    ),
                },
            }]

    class Index:
        architecture = "same"

        @staticmethod
        def for_target(_kind, _target):
            return "same"

    targets, regenerate = _select_update_targets(
        Store(), {"name": "sample", "components": [], "relationships": []}, Index()
    )

    assert targets == set()
    assert regenerate is False
