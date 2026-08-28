"""No regression, proven rather than asserted: --ladder defaults off.

The build plan's third ground rule is that the pipeline is opt-in and that with
it off the behaviour is what it was. The golden corpora prove the PROJECTION does
not move. These prove the other half: that the enhance path itself is unchanged
when the flag is absent, and that no phase of the ladder can run without it.

  1. The default parse produces ladder=False and nothing else about the existing
     flags changed.
  2. Without --ladder, main() reaches run_enhance with exactly the config it
     always built, and never touches the pipeline.
  3. With --ladder, run_enhance is never called at all: the ladder is a separate
     top-level path, not a mode of the bulk pass.
  4. Every phase in the registry is implemented. A NotBuiltPhase reaching a real
     run would report "skipped" and could be mistaken for a phase that had
     nothing to do.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from analyzer.enrich import enhance_cli
from analyzer.enrich.engine import EnhanceConfig, EnhanceReport
from analyzer.enrich.pipeline import (
    PHASE_ORDER,
    LadderPolicy,
    NotBuiltPhase,
    build_phases,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


# --- 1. the defaults ----------------------------------------------------------


def test_the_ladder_defaults_off():
    args = enhance_cli.build_parser().parse_args([])
    assert args.ladder is False
    assert args.run_dir is None
    assert args.phase_model is None
    assert args.model_source is None
    assert args.min_rounds is None
    assert args.max_rounds is None
    assert args.spot_check_fraction is None
    assert args.max_spot_checks is None


def test_the_existing_flags_keep_their_defaults():
    """A new flag must not have moved an old one."""
    args = enhance_cli.build_parser().parse_args([])
    assert args.root == "."
    assert args.store is None
    assert args.update is False
    assert args.dry_run is False
    assert args.threshold == 85.0
    assert args.max_partitions is None
    assert args.max_lines == 50_000
    assert args.max_components == 30
    assert args.min_components == 5
    assert args.max_parallel == 4
    assert args.report is None
    assert args.retry_attempts is None
    # The parser leaves this unspecified so the classic path can retain its
    # historical $10 default while a quality-first ladder does not silently
    # stop halfway through a subject projected above $10.
    assert args.max_cost_usd is None


# --- 2 and 3. the two paths never cross ---------------------------------------


@pytest.fixture
def store(tmp_path):
    from analyzer.derive import derive_all
    from analyzer.extract import extract_repo
    from analyzer.store import FactStore

    db = tmp_path / "index.db"
    fact_store = FactStore(str(db))
    extract_repo(POLYGLOT, fact_store)
    derive_all(fact_store, "polyglot", root_path=POLYGLOT)
    fact_store.commit()
    fact_store.close()
    return db


def test_without_the_flag_main_reaches_run_enhance_with_the_usual_config(
    store, monkeypatch, tmp_path
):
    seen = {}

    def fake_run_enhance(config: EnhanceConfig):
        seen["config"] = config
        return EnhanceReport(mode="update", dry_run=True, partition_count=0)

    def fail_ladder(*args, **kwargs):
        raise AssertionError("the ladder must not run without --ladder")

    monkeypatch.setattr(enhance_cli, "run_enhance", fake_run_enhance)
    monkeypatch.setattr("analyzer.enrich.pipeline.run_ladder", fail_ladder)

    code = enhance_cli.main([
        POLYGLOT, "--store", str(store), "--update", "--dry-run",
    ])

    assert code == 0
    config = seen["config"]
    assert isinstance(config, EnhanceConfig)
    assert config.store_path == Path(str(store)).resolve()
    assert config.root == Path(POLYGLOT).resolve()
    assert config.update is True
    assert config.dry_run is True
    assert config.threshold == 85.0
    assert config.model == "sonnet"
    assert config.max_cost_usd == 10.0
    # Nothing about the ladder leaked into the bulk config.
    assert not hasattr(config, "ladder")
    assert not hasattr(config, "policy")


def test_with_the_flag_run_enhance_is_never_called(store, monkeypatch, tmp_path):
    """The ladder is a separate top-level path, not a mode of the bulk pass."""
    called = {"ladder": 0}

    def fail_enhance(*args, **kwargs):
        raise AssertionError("run_enhance must not run under --ladder")

    class FakeResult:
        phases: list = []
        ledger: list = []
        notes: list = []
        total_cost_usd = 0.0
        ceiling_hit = False
        failed_phases: list = []
        ok = True

    def fake_run_ladder(config, **kwargs):
        called["ladder"] += 1
        called["config"] = config
        return FakeResult()

    monkeypatch.setattr(enhance_cli, "run_enhance", fail_enhance)
    monkeypatch.setattr("analyzer.enrich.pipeline.run_ladder", fake_run_ladder)

    code = enhance_cli.main([
        POLYGLOT, "--store", str(store), "--ladder",
        "--run-dir", str(tmp_path / "run"),
        "--retry-attempts", "1",
        "--spot-check-fraction", "1.0",
        "--max-spot-checks", "12",
    ])

    assert code == 0
    assert called["ladder"] == 1
    assert called["config"].policy.iteration.min_rounds == 1
    assert called["config"].policy.retry_attempts == 1
    assert called["config"].policy.spot_check_fraction == 1.0
    assert called["config"].policy.max_spot_checks == 12


def test_an_unknown_binding_stops_the_run_before_anything_happens(
    store, monkeypatch, tmp_path
):
    def fail_ladder(*args, **kwargs):
        raise AssertionError("the run must not start with an invalid binding")

    monkeypatch.setattr("analyzer.enrich.pipeline.run_ladder", fail_ladder)
    code = enhance_cli.main([
        POLYGLOT, "--store", str(store), "--ladder",
        "--phase-model", "p2a_bulk=no-such-lab:m",
    ])
    assert code == 2


# --- 4. no phase is still a placeholder ---------------------------------------


def test_every_phase_in_the_canonical_order_is_implemented():
    """A NotBuiltPhase reports 'skipped', which reads like a phase with no work."""
    phases = build_phases(LadderPolicy())
    unbuilt = [p.name for p in phases if isinstance(p, NotBuiltPhase)]
    assert unbuilt == [], f"still placeholders: {unbuilt}"
    assert [p.name for p in phases] == [
        name for name in PHASE_ORDER if name != "p0_context"
    ]
