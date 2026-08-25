"""Tests for the usage accounting (scripts/usage-budget.py).

The point of this tool is to answer "how much of my week did that spend", and
the only way it can be wrong in a way that matters is by getting the WEIGHTING
wrong: treating a million Fable tokens as if they were a million Haiku tokens,
or counting a cache read at full price. Those are the cases here.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "usage_budget", REPO_ROOT / "scripts" / "usage-budget.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ub = _load()


def test_models_are_not_priced_alike():
    """The whole reason this file exists.

    A run that spends its tokens on Fable and one that spends them on Haiku are
    not the same amount of a weekly allowance, and a tool that reported them as
    equal would give exactly the wrong pacing advice.
    """
    one_million_out = {"calls": 1, "input_tokens": 0, "output_tokens": 1_000_000}
    fable, _, _ = ub.api_equivalent_usd({"anthropic-claude-cli:fable": one_million_out})
    haiku, _, _ = ub.api_equivalent_usd({"anthropic-claude-cli:haiku": one_million_out})
    assert fable == pytest.approx(50.0)
    assert haiku == pytest.approx(5.0)
    assert fable == pytest.approx(haiku * 10)


def test_output_costs_five_times_input():
    """Published rates put output at 5x input on every model in the ladder."""
    m = "anthropic-claude-cli:opus"
    inp, _, _ = ub.api_equivalent_usd({m: {"calls": 1, "input_tokens": 1_000_000, "output_tokens": 0}})
    out, _, _ = ub.api_equivalent_usd({m: {"calls": 1, "input_tokens": 0, "output_tokens": 1_000_000}})
    assert inp == pytest.approx(5.0)
    assert out == pytest.approx(25.0)


def test_a_cache_read_is_not_a_fresh_read():
    """Cache reads are ~a tenth of fresh input.

    The enrichment ladder sends a large stable prefix to every partition, so a
    well-cached run and a badly-cached one do identical work at very different
    cost. Folding cache reads in at full price would overstate a cached run
    several-fold and make the pacing advice useless.
    """
    m = "anthropic-claude-cli:sonnet"
    fresh, _, _ = ub.api_equivalent_usd({m: {"calls": 1, "input_tokens": 1_000_000}})
    cached, _, _ = ub.api_equivalent_usd({m: {"calls": 1, "cache_read_input_tokens": 1_000_000}})
    assert cached == pytest.approx(fresh * ub.CACHE_READ_MULTIPLIER)
    assert cached < fresh


def test_a_cache_write_costs_more_than_a_fresh_read():
    """Writing the cache is ~1.25x, which is why caching only pays on reuse."""
    m = "anthropic-claude-cli:sonnet"
    fresh, _, _ = ub.api_equivalent_usd({m: {"calls": 1, "input_tokens": 1_000_000}})
    written, _, _ = ub.api_equivalent_usd({m: {"calls": 1, "cache_creation_input_tokens": 1_000_000}})
    assert written == pytest.approx(fresh * ub.CACHE_WRITE_MULTIPLIER)
    assert written > fresh


def test_an_unrecognised_model_is_not_free():
    """A binding nobody anticipated must not silently count as zero.

    Reporting an unknown rung at no cost is the failure mode that would let a
    whole ladder phase disappear from the account, so it falls back to the CLI's
    own reported figure and says which rows were priced that way.
    """
    usage = {"some-future-model": {"calls": 2, "input_tokens": 5_000, "cost_usd": 7.25}}
    total, rows, unknown = ub.api_equivalent_usd(usage)
    assert total == pytest.approx(7.25)
    assert unknown == ["some-future-model"]
    assert "unrecognised" in rows[0]["priced_from"]


def test_the_ladders_real_shape_is_priced_per_rung():
    """A mixed run prices each rung at its own rate, not at a blended one."""
    usage = {
        "anthropic-claude-cli:sonnet": {"calls": 57, "input_tokens": 2_000_000, "output_tokens": 400_000},
        "anthropic-claude-cli:opus": {"calls": 6, "input_tokens": 300_000, "output_tokens": 90_000},
        "anthropic-claude-cli:fable": {"calls": 4, "input_tokens": 100_000, "output_tokens": 40_000},
    }
    total, rows, unknown = ub.api_equivalent_usd(usage)
    assert not unknown
    by_model = {r["model"].rsplit(":", 1)[1]: r["api_equivalent_usd"] for r in rows}
    assert by_model["sonnet"] == pytest.approx(2 * 3.0 + 0.4 * 15.0)
    assert by_model["opus"] == pytest.approx(0.3 * 5.0 + 0.09 * 25.0)
    assert by_model["fable"] == pytest.approx(0.1 * 10.0 + 0.04 * 50.0)
    assert total == pytest.approx(sum(by_model.values()))


def test_an_old_report_without_the_account_degrades_to_the_ledger(tmp_path):
    """Reports written before per-model accounting still yield something true."""
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "total_cost_usd": 3.5,
        "ledger": [
            {"model": "anthropic-claude-cli:sonnet", "cost_usd": 2.0},
            {"model": "anthropic-claude-cli:sonnet", "cost_usd": 1.5},
        ],
    }), encoding="utf-8")
    usage, reported = ub._read_usage(report)
    assert reported == pytest.approx(3.5)
    assert usage["anthropic-claude-cli:sonnet"]["calls"] == 2


def test_an_uncalibrated_allowance_is_declared_not_hidden():
    """The one assumption in the tool must never read as a measurement."""
    cfg = ub._load_config()
    assert "weekly_allowance_api_equivalent_usd" in cfg
    if not cfg.get("calibrated"):
        assert "placeholder" in cfg.get("basis", "").lower()
