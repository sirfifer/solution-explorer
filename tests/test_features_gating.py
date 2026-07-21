"""Maturity-channel gating tests (card R3).

Two layers:

  - Unit tests of ``analyzer.features``: channel resolution precedence and
    validation, Rust-toolchain activation semantics, and the deterministic
    gate-provenance stamp (the determinism invariant: the default ``stable``
    channel, and any channel that activates no non-stable gate, stamp NOTHING).

  - End-to-end tests through the REAL projection pipeline over a real fixture
    store (no mocks of the emitters): a default run has no stamp and is
    byte-identical to an ``experimental`` run when no gate is registered (the
    true no-op proof), and an ``experimental`` run WITH a registered gate carries
    the additive provenance stamp and nothing else changes (self-explaining).

The exemplar gate is registered by the test, not shipped: no analyzer feature
currently needs partial visibility before it is done, so
``features.REGISTERED_GATES`` is empty by design (see the TASKS.md Gate
Inventory). These tests prove the mechanism end to end with their own gate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from analyzer import features as F
from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project import pipeline as pipe
from analyzer.store import FactStore

FIXED_TS = "2026-01-01T00:00:00Z"
FIXED_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
FIXED_SHA = "deadbeefcafe"

EXP_GATE = F.Gate(
    id="demo.experimental-surface",
    stability=F.EXPERIMENTAL,
    owner="r3-tests",
    expires="2099-01-01",
    summary="A test-only experimental surface proving the gate mechanism.",
)
BETA_GATE = F.Gate(
    id="demo.beta-surface",
    stability=F.BETA,
    owner="r3-tests",
    expires="2099-01-01",
    summary="A test-only beta surface.",
)
STABLE_GATE = F.Gate(
    id="demo.stable-surface",
    stability=F.STABLE,
    owner="r3-tests",
    expires="2099-01-01",
    summary="A stable surface (never stamped; part of the tool).",
)


# ---------------------------------------------------------------------------
# unit: channel resolution
# ---------------------------------------------------------------------------


def test_resolve_channel_default_is_stable():
    assert F.resolve_channel() == "stable"
    assert F.resolve_channel(None, None) == "stable"
    assert F.resolve_channel("", "") == "stable"


def test_resolve_channel_cli_wins_over_env():
    assert F.resolve_channel("stable", "experimental") == "stable"
    assert F.resolve_channel("beta", "experimental") == "beta"


def test_resolve_channel_env_used_when_no_cli():
    assert F.resolve_channel(None, "experimental") == "experimental"
    assert F.resolve_channel(None, "beta") == "beta"


def test_resolve_channel_rejects_bad_cli_and_env():
    with pytest.raises(ValueError, match="invalid --channel"):
        F.resolve_channel("bogus")
    with pytest.raises(ValueError, match="SOLUTION_EXPLORER_CHANNEL"):
        F.resolve_channel(None, "nightly")


def test_channel_level_ordering_and_unknown():
    assert F.channel_level("stable") == 0
    assert F.channel_level("beta") == 1
    assert F.channel_level("experimental") == 2
    with pytest.raises(ValueError, match="unknown channel"):
        F.channel_level("bogus")


# ---------------------------------------------------------------------------
# unit: activation semantics (Rust toolchain: channel >= feature level)
# ---------------------------------------------------------------------------


def test_is_active_matrix():
    # stable feature: always active
    assert F.is_active("stable", "stable")
    assert F.is_active("stable", "beta")
    assert F.is_active("stable", "experimental")
    # beta feature: active on beta and experimental, not stable
    assert not F.is_active("beta", "stable")
    assert F.is_active("beta", "beta")
    assert F.is_active("beta", "experimental")
    # experimental feature: active only on experimental
    assert not F.is_active("experimental", "stable")
    assert not F.is_active("experimental", "beta")
    assert F.is_active("experimental", "experimental")


def test_active_gates_excludes_stable_and_sorts():
    gates = [EXP_GATE, BETA_GATE, STABLE_GATE]
    # On experimental: both non-stable gates active, stable excluded, sorted by id.
    active = F.active_gates("experimental", gates)
    assert [g.id for g in active] == ["demo.beta-surface", "demo.experimental-surface"]
    # On beta: only the beta gate.
    assert [g.id for g in F.active_gates("beta", gates)] == ["demo.beta-surface"]
    # On stable: nothing (even the stable gate is never stamped).
    assert F.active_gates("stable", gates) == []


# ---------------------------------------------------------------------------
# unit: the determinism invariant, gate_provenance
# ---------------------------------------------------------------------------


def test_gate_provenance_stable_is_always_none():
    # The load-bearing rule: the default channel stamps nothing, even if gates
    # are registered. This is what keeps a default run byte-identical.
    assert F.gate_provenance("stable") is None
    assert F.gate_provenance("stable", [EXP_GATE, BETA_GATE, STABLE_GATE]) is None


def test_gate_provenance_none_when_no_nonstable_gate_active():
    # A non-default channel with an EMPTY registry activates nothing, so it still
    # stamps nothing and stays byte-identical to a default run.
    assert F.gate_provenance("experimental", []) is None
    assert F.gate_provenance("beta", []) is None
    # Beta channel does not activate an experimental-only gate.
    assert F.gate_provenance("beta", [EXP_GATE]) is None
    # A channel with only stable gates stamps nothing.
    assert F.gate_provenance("experimental", [STABLE_GATE]) is None


def test_gate_provenance_stamps_active_nonstable_gates_deterministically():
    stamp = F.gate_provenance("experimental", [EXP_GATE, BETA_GATE, STABLE_GATE])
    assert stamp == {
        "channel": "experimental",
        "active_gates": [
            {"id": "demo.beta-surface", "stability": "beta"},
            {"id": "demo.experimental-surface", "stability": "experimental"},
        ],
    }
    # The stamp carries only id + stability, never owner/expiry (governance lives
    # in TASKS.md, the stamp is a self-explaining marker).
    for g in stamp["active_gates"]:
        assert set(g.keys()) == {"id", "stability"}


def test_registered_gates_empty_by_design():
    # No analyzer feature needs a gate today; inventing one would be theater.
    assert F.REGISTERED_GATES == ()


def test_gate_rejects_bad_stability_at_construction():
    # A mistyped stability fails loud at construction (import), not at run time.
    with pytest.raises(ValueError, match="invalid gate stability"):
        F.Gate(id="g.typo", stability="experimentl", owner="o", expires="2099-01-01", summary="s")
    # The three valid stabilities all construct (a stable gate is declarable even
    # though it is never stamped).
    for s in (F.STABLE, F.BETA, F.EXPERIMENTAL):
        F.Gate(id=f"g.{s}", stability=s, owner="o", expires="2099-01-01", summary="s")


# ---------------------------------------------------------------------------
# end-to-end: through the real projection pipeline over a real fixture
# ---------------------------------------------------------------------------


def _build_repo(root):
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "main.py").write_text(
        "def handler(req):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (root / "app" / "db.py").write_text(
        "class User:\n    id = 0\n    name = ''\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Sample\n\nSmall app.\n", encoding="utf-8")


def _extract(root) -> FactStore:
    (root / ".se").mkdir(parents=True, exist_ok=True)
    store = FactStore(str(root / ".se" / "index.db"))
    extract_repo(root, store)
    return store


def _split_bytes(root, store, out, channel="stable") -> bytes:
    """Run a fully-deterministic split projection; return the manifest bytes."""
    _, arch = derive_all(store, "sample", root_path=str(root))
    pipe.project_split(
        arch, out, store=store, root=root,
        generated_at=FIXED_TS, analyzer_version="1.2.0",
        channel=channel, commit_sha=FIXED_SHA, now=FIXED_NOW,
    )
    return (out / "manifest.json").read_bytes()


def _monolith_doc(root, store, out_path, channel="stable") -> dict:
    _, arch = derive_all(store, "sample", root_path=str(root))
    pipe.project_monolith(
        arch, out_path, store=store, root=root,
        generated_at=FIXED_TS, analyzer_version="1.2.0",
        channel=channel, commit_sha=FIXED_SHA, now=FIXED_NOW,
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_default_channel_no_stamp_split_and_monolith(tmp_path):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    manifest = json.loads(_split_bytes(tmp_path, store, tmp_path / "out"))
    assert "gate_provenance" not in manifest
    doc = _monolith_doc(tmp_path, store, tmp_path / "architecture.json")
    assert "gate_provenance" not in doc
    store.close()


def test_experimental_empty_registry_is_byte_identical_to_default(tmp_path):
    # The true no-op proof over a real fixture: with no gate registered, the
    # experimental channel produces byte-identical output to the default channel.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    default_bytes = _split_bytes(tmp_path, store, tmp_path / "out-default", channel="stable")
    exp_bytes = _split_bytes(tmp_path, store, tmp_path / "out-exp", channel="experimental")
    assert default_bytes == exp_bytes
    assert b"gate_provenance" not in default_bytes
    store.close()


def test_experimental_with_registered_gate_stamps_and_only_adds_the_stamp(
    tmp_path, monkeypatch
):
    # Register a test gate, then the experimental channel activates it and the
    # projection carries the additive provenance stamp. The default-channel output
    # differs by EXACTLY that additive key (self-explaining, no other drift).
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    default_manifest = json.loads(
        _split_bytes(tmp_path, store, tmp_path / "out-default", channel="stable")
    )

    monkeypatch.setattr(F, "REGISTERED_GATES", (EXP_GATE,))
    exp_manifest = json.loads(
        _split_bytes(tmp_path, store, tmp_path / "out-exp", channel="experimental")
    )

    assert exp_manifest["gate_provenance"] == {
        "channel": "experimental",
        "active_gates": [
            {"id": "demo.experimental-surface", "stability": "experimental"}
        ],
    }
    # The ONLY difference from the default output is the additive stamp.
    stripped = dict(exp_manifest)
    stripped.pop("gate_provenance")
    assert stripped == default_manifest

    # The AI front door surfaces the stamp so a non-default dataset is
    # self-explaining to an agent.
    ai_json = json.loads((tmp_path / "out-exp" / "ai.json").read_text(encoding="utf-8"))
    assert ai_json["dataset"]["gate_provenance"]["channel"] == "experimental"
    # The default front door carries no gate provenance.
    ai_default = json.loads(
        (tmp_path / "out-default" / "ai.json").read_text(encoding="utf-8")
    )
    assert "gate_provenance" not in ai_default["dataset"]
    store.close()


def test_beta_channel_does_not_activate_experimental_gate_endtoend(tmp_path, monkeypatch):
    # A real channel gate: with only an experimental gate registered, the beta
    # channel activates nothing, so its output is byte-identical to the default.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    default_bytes = _split_bytes(tmp_path, store, tmp_path / "out-default", channel="stable")
    monkeypatch.setattr(F, "REGISTERED_GATES", (EXP_GATE,))
    beta_bytes = _split_bytes(tmp_path, store, tmp_path / "out-beta", channel="beta")
    assert beta_bytes == default_bytes
    assert b"gate_provenance" not in beta_bytes
    store.close()


def test_stable_channel_never_stamps_even_with_gate_registered(tmp_path, monkeypatch):
    # The determinism guard end to end: even with an experimental gate registered,
    # a stable run stamps nothing (the golden gate depends on this).
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(F, "REGISTERED_GATES", (EXP_GATE,))
    manifest = json.loads(_split_bytes(tmp_path, store, tmp_path / "out", channel="stable"))
    assert "gate_provenance" not in manifest
    store.close()
