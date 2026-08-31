"""Tier bindings: the ladder is a structure, not a vendor.

The rungs are defined by the kind of work they do. Which source and which model
runs each one is configuration. These tests pin four properties:

  1. TODAY IS UNCHANGED. The default bindings are the Claude models on the
     `claude` CLI that the owner's subscription runs, and the CLI builds exactly
     the argv it built before.
  2. A BINDING IS A SOURCE PLUS AN OPTIONAL MODEL. Unpinned is a first-class
     option, not a missing value: it means the source routes the call itself.
  3. PROVIDERS ARE REGISTERED, NOT HARDCODED. Adding a source is a registration,
     and nothing above models.py knows a vendor name.
  4. AN UNKNOWN SOURCE FAILS AT CONFIGURATION TIME. Not when a rung finally
     invokes, by which point the run has already spent everything below it.
"""

from __future__ import annotations

import pytest

from analyzer.enrich.engine import ClaudeCliInvoker, InvokeResult
from analyzer.enrich.enhance_cli import _parse_phase_cache, _parse_phase_models
from analyzer.enrich.models import (
    ANTHROPIC_CLAUDE_CLI,
    DEFAULT_SOURCE,
    ModelSpec,
    build_invoker,
    known_sources,
    register_provider,
)
from analyzer.enrich.pipeline import DEFAULT_MODELS, LadderPolicy, resolve_models

# --- 1. today is unchanged ----------------------------------------------------


def test_the_default_bindings_are_todays_claude_models_on_todays_transport():
    policy = LadderPolicy()
    assert policy.model_for("p2a_bulk") == ModelSpec(ANTHROPIC_CLAUDE_CLI, "sonnet")
    assert policy.model_for("p2b_escalated") == ModelSpec(ANTHROPIC_CLAUDE_CLI, "opus")
    assert policy.model_for("p2c_residue") == ModelSpec(ANTHROPIC_CLAUDE_CLI, "fable")
    assert policy.model_for("p3_adjudication") == ModelSpec(ANTHROPIC_CLAUDE_CLI, "opus")
    # Every default binding is pinned: nothing routes by accident.
    assert all(spec.pinned for spec in DEFAULT_MODELS.values())
    assert all(spec.source == DEFAULT_SOURCE for spec in DEFAULT_MODELS.values())


def test_a_pinned_binding_builds_the_same_cli_call_it_always_did(monkeypatch):
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = '{"result": "{}", "total_cost_usd": 0.0, "usage": {}}'
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FakeProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)
    ClaudeCliInvoker(model="sonnet")("a prompt")
    session = seen["argv"][seen["argv"].index("--session-id") + 1]
    assert session
    assert seen["argv"][1:] == [
        "-p", "--output-format", "json",
        "--tools", "", "--setting-sources", "user",
        "--effort", "low",
        "--session-id", session,
        "--model", "sonnet",
    ]


def test_effort_is_always_passed_and_never_inherited(monkeypatch):
    """The flag that was missing on 2026-08-25, asserted on the argv itself.

    ``--setting-sources user`` keeps the PROJECT's settings out of a call while
    leaving the operator's own settings.json free to choose the reasoning
    budget. That is how a 173-partition batch run inherited an interactive
    session's "xhigh": two thirds of every billed output token went to
    thinking, and 35% of completed partitions truncated at the shared ceiling.
    There is no code path that omits the flag, so an unstated effort is the
    documented default rather than whatever the machine happens to be set to.
    """
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = '{"result": "{}", "total_cost_usd": 0.0, "usage": {}}'
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FakeProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)

    ClaudeCliInvoker(model="sonnet")("a prompt")
    assert "--effort" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--effort") + 1] == "low"

    ClaudeCliInvoker(model="opus", effort="high")("a prompt")
    assert seen["argv"][seen["argv"].index("--effort") + 1] == "high"

    # An unpinned binding still pins its effort: routing the model is a
    # deliberate option, inheriting the reasoning budget never is.
    ClaudeCliInvoker(model=None)("a prompt")
    assert "--effort" in seen["argv"]


def test_cli_arms_the_provider_cost_backstop(monkeypatch):
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = '{"result": "{}", "total_cost_usd": 0.0, "usage": {}}'
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FakeProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)
    ClaudeCliInvoker(model="sonnet", max_budget_usd=0.375)("a prompt")
    index = seen["argv"].index("--max-budget-usd")
    assert seen["argv"][index + 1] == "0.375000"


def test_an_unpinned_binding_omits_the_model_flag_so_the_source_routes(monkeypatch):
    """Unpinned is a real option on the provider that ships, not just on a router."""
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = '{"result": "{}", "total_cost_usd": 0.0, "usage": {}}'
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FakeProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)
    ClaudeCliInvoker(model=None)("a prompt")
    assert "--model" not in seen["argv"]
    session = seen["argv"][seen["argv"].index("--session-id") + 1]
    assert session
    assert seen["argv"][1:] == [
        "-p", "--output-format", "json",
        "--tools", "", "--setting-sources", "user",
        "--effort", "low",
        "--session-id", session,
    ]


def test_cache_policy_is_an_explicit_isolated_child_environment(monkeypatch):
    seen = []

    class FakeProc:
        returncode = 0
        stdout = '{"result": "{}", "total_cost_usd": 0.0, "usage": {}}'
        stderr = ""

    def fake_run(argv, **kwargs):
        seen.append(kwargs["env"])
        return FakeProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)
    # Ambient settings must not silently override a recorded run policy.
    monkeypatch.setenv("ENABLE_PROMPT_CACHING_1H", "1")
    monkeypatch.setenv("DISABLE_PROMPT_CACHING_SONNET", "1")

    ClaudeCliInvoker(model="sonnet", cache_policy="5m")("prompt")
    ClaudeCliInvoker(model="sonnet", cache_policy="off")("prompt")
    ClaudeCliInvoker(model="sonnet", cache_policy="provider-default")("prompt")

    assert seen[0]["FORCE_PROMPT_CACHING_5M"] == "1"
    assert "ENABLE_PROMPT_CACHING_1H" not in seen[0]
    assert seen[1]["DISABLE_PROMPT_CACHING"] == "1"
    assert "FORCE_PROMPT_CACHING_5M" not in seen[1]
    assert all(
        key not in seen[2]
        for key in (
            "FORCE_PROMPT_CACHING_5M", "ENABLE_PROMPT_CACHING_1H",
            "DISABLE_PROMPT_CACHING", "DISABLE_PROMPT_CACHING_SONNET",
        )
    )


def test_adaptive_cache_policy_is_per_work_shape_not_per_model():
    policy = LadderPolicy()
    assert policy.cache_policy_for(
        "p2a_bulk", phase="p2_ladder", rung="2a"
    ) == "off"
    assert policy.cache_policy_for(
        "p3_adjudication", phase="p3_adjudication",
        rung="substitution-check",
    ) == "5m"
    assert policy.cache_policy_for(
        "p3_adjudication", phase="p3_adjudication", rung="verify-edges"
    ) == "off"
    assert policy.cache_policy_for(
        "p5_determination", phase="p5_determination"
    ) == "5m"

    forced = LadderPolicy(cache_policy="off")
    assert forced.cache_policy_for(
        "p5_determination", phase="p5_determination"
    ) == "off"

    overridden = LadderPolicy(cache_policy_overrides={"verify-edges": "5m"})
    assert overridden.cache_policy_for(
        "p3_adjudication", phase="p3_adjudication", rung="verify-edges"
    ) == "5m"


def test_phase_cache_parser_rejects_unknown_policy():
    parsed, errors = _parse_phase_cache([
        "verify-edges=5m", "p2a_bulk=off", "bad=forever"
    ])
    assert parsed == {"verify-edges": "5m", "p2a_bulk": "off"}
    assert len(errors) == 1
    assert "forever" in errors[0]


# --- 2. a binding is a source plus an optional model --------------------------


def test_every_accepted_binding_form_parses():
    assert ModelSpec.parse("sonnet") == ModelSpec(DEFAULT_SOURCE, "sonnet")
    assert ModelSpec.parse("openrouter:anthropic/claude-opus-5") == ModelSpec(
        "openrouter", "anthropic/claude-opus-5"
    )
    assert ModelSpec.parse("openrouter:auto") == ModelSpec("openrouter", None)
    assert ModelSpec.parse({"source": "some-lab", "model": "m-1"}) == ModelSpec(
        "some-lab", "m-1"
    )
    assert ModelSpec.parse({"source": "some-lab", "model": None}) == ModelSpec(
        "some-lab", None
    )
    assert ModelSpec.parse(ModelSpec("x", "y")) == ModelSpec("x", "y")


def test_a_bare_model_name_still_means_the_default_source():
    """Existing flags and registry entries must not silently repoint."""
    assert ModelSpec.parse("opus").source == DEFAULT_SOURCE
    assert resolve_models({"p2a_bulk": "haiku"})["p2a_bulk"] == ModelSpec(
        DEFAULT_SOURCE, "haiku"
    )


def test_unpinned_is_a_state_not_a_missing_value():
    spec = ModelSpec.parse("openrouter:auto")
    assert spec.pinned is False
    assert spec.model is None
    assert spec.label == "openrouter:auto"
    assert spec.to_dict() == {
        "source": "openrouter",
        "model": None,
        "pinned": False,
        "effort": "low",
    }


def test_a_binding_label_is_what_the_ledger_records():
    """The Run Report has to say which lab and which model did each piece of work."""
    assert ModelSpec(ANTHROPIC_CLAUDE_CLI, "opus").label == "anthropic-claude-cli:opus"
    assert ModelSpec("openrouter", None).label == "openrouter:auto"


def test_rebinding_one_rung_leaves_the_others_alone():
    models = resolve_models({"p2a_bulk": "openrouter:auto"})
    assert models["p2a_bulk"] == ModelSpec("openrouter", None)
    assert models["p2b_escalated"] == DEFAULT_MODELS["p2b_escalated"]


def test_a_default_source_can_be_set_for_every_rung_at_once():
    models = resolve_models(
        {"p2a_bulk": "big-model", "p2b_escalated": "bigger-model"},
        default_source="some-aggregator",
    )
    assert models["p2a_bulk"] == ModelSpec("some-aggregator", "big-model")
    assert models["p2b_escalated"] == ModelSpec("some-aggregator", "bigger-model")


# --- 3. providers are registered, not hardcoded -------------------------------


def test_a_new_source_is_a_registration_not_a_refactor():
    calls = []

    def fake_builder(spec):
        def invoke(prompt):
            calls.append(spec)
            return InvokeResult(ok=True, text="{}", cost_usd=0.01)

        return invoke

    register_provider("test-aggregator", fake_builder)
    try:
        assert "test-aggregator" in known_sources()
        invoker = build_invoker("test-aggregator:auto")
        result = invoker("prompt")
        assert result.ok is True
        assert calls == [ModelSpec("test-aggregator", None)]
    finally:
        from analyzer.enrich import models as models_module

        models_module._PROVIDERS.pop("test-aggregator", None)


def test_the_ladder_ledgers_the_source_it_actually_used():
    from pathlib import Path

    from analyzer.enrich.pipeline import BudgetMeter, RunContext

    built = []

    def factory(spec):
        built.append(spec)
        return lambda prompt: InvokeResult(ok=True, text="{}", cost_usd=0.02)

    ctx = RunContext(
        store=None, root=Path("/x"), store_path=Path("/x/i.db"), arch={},
        facts=None, index=None,
        policy=LadderPolicy(models=resolve_models({"p2a_bulk": "openrouter:auto"})),
        budget=BudgetMeter(), invoker_factory=factory, run_dir=Path("/x/run"),
    )
    ctx.invoker("p2a_bulk", phase="p2_ladder", rung="2a")("prompt")

    assert built == [ModelSpec("openrouter", None)]
    assert ctx.ledger[-1].model == "openrouter:auto"


# --- 4. an unknown source fails at configuration time -------------------------


def test_building_an_invoker_for_an_unregistered_source_raises():
    with pytest.raises(ValueError) as excinfo:
        build_invoker("no-such-lab:some-model")
    assert "unknown model source" in str(excinfo.value)
    assert ANTHROPIC_CLAUDE_CLI in str(excinfo.value)


def test_the_cli_rejects_an_unknown_source_before_the_run_starts():
    """Fail-before contrast: caught here, not when a rung first tries to invoke."""
    models, errors = _parse_phase_models(["p2b_escalated=no-such-lab:m"])
    assert errors and "unknown source" in errors[0]
    # And the binding is not applied, so a rejected run cannot half-configure.
    assert models["p2b_escalated"] == DEFAULT_MODELS["p2b_escalated"]

    _, source_errors = _parse_phase_models([], "no-such-lab")
    assert source_errors and "unknown source" in source_errors[0]


def test_the_cli_still_rejects_an_unknown_rung_key():
    _, errors = _parse_phase_models(["p9_imaginary=sonnet"])
    assert errors and "unknown key" in errors[0]


def test_the_cli_accepts_a_registered_source_with_an_unpinned_model():
    models, errors = _parse_phase_models(
        [f"p2a_bulk={ANTHROPIC_CLAUDE_CLI}:auto"]
    )
    assert errors == []
    assert models["p2a_bulk"] == ModelSpec(ANTHROPIC_CLAUDE_CLI, None)
