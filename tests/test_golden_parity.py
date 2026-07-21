"""Tests for the golden-corpus full-vs-incremental parity check (card G4).

Two layers, both hermetic by default:

  - the shared parity NORMALIZER (analyzer.parity): stripping the volatile
    fields and byte-comparing with list order preserved, which is what makes the
    check stronger than the G1 semantic diff;
  - the harness wiring in scripts/golden-corpus.py (_compare_projections,
    _pick_source_file) against synthetic projections.

The live cold-vs-warm and changed-file runs against the real corpora are proven
by the dedicated golden-corpus workflow and by one opt-in network test guarded
by GOLDEN_CORPUS_NETWORK, so the default suite stays fast and offline.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from analyzer.parity import (
    VOLATILE_KEYS,
    canonical,
    normalize_for_parity,
    strip_volatile,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "scripts" / "golden-corpus.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("golden_corpus", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gc = _load_harness()


def _projection(**overrides) -> dict:
    proj = {
        "name": "demo",
        "generated_at": "2026-01-01T00:00:00Z",
        "analyzer_version": "1.2.0",
        "root_path": "/some/machine/path",
        "changelog": [{"serial": 1}],
        "changelog_serial": 1,
        "components": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
        "relationships": [{"source": "a", "target": "b", "type": "calls"}],
        "stats": {"total_components": 2, "total_relationships": 1},
    }
    proj.update(overrides)
    return proj


# ---------------------------------------------------------------------------
# the shared normalizer (analyzer.parity)
# ---------------------------------------------------------------------------


def test_volatile_keys_are_the_expected_allowlist():
    assert set(VOLATILE_KEYS) == {
        "generated_at", "root_path", "analyzer_version", "changelog", "changelog_serial",
    }


def test_strip_volatile_removes_only_the_allowlist():
    stripped = strip_volatile(_projection())
    for key in VOLATILE_KEYS:
        assert key not in stripped
    assert stripped["components"]  # code facts survive
    assert stripped["stats"]["total_components"] == 2


def test_normalize_ignores_volatile_differences():
    # Two projections of the same tree that differ ONLY in the volatile fields
    # must normalize identically (that is the whole parity premise).
    a = _projection(generated_at="2026-01-01T00:00:00Z", root_path="/box-a",
                    analyzer_version="1.2.0", changelog=[{"serial": 5}], changelog_serial=5)
    b = _projection(generated_at="2029-09-09T09:09:09Z", root_path="/box-b",
                    analyzer_version="9.9.9", changelog=[{"serial": 1}], changelog_serial=1)
    assert normalize_for_parity(a) == normalize_for_parity(b)


def test_normalize_detects_a_real_field_difference():
    a = _projection()
    b = _projection(components=[{"id": "a", "name": "A"}])  # a component dropped
    assert normalize_for_parity(a) != normalize_for_parity(b)


def test_normalize_is_list_order_sensitive():
    # Stronger than the G1 by-id diff: a reordering of a list is a real byte
    # difference the parity check must not mask.
    a = _projection(relationships=[
        {"source": "a", "target": "b", "type": "calls"},
        {"source": "b", "target": "a", "type": "calls"},
    ])
    b = _projection(relationships=[
        {"source": "b", "target": "a", "type": "calls"},
        {"source": "a", "target": "b", "type": "calls"},
    ])
    assert normalize_for_parity(a) != normalize_for_parity(b)


def test_canonical_is_stable_and_key_order_independent():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical(a) == canonical(b)  # sorted keys
    assert canonical(a).endswith("\n")


# ---------------------------------------------------------------------------
# harness wiring
# ---------------------------------------------------------------------------


def test_compare_projections_none_when_only_volatile_differs(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_projection(generated_at="t1", root_path="/x")), encoding="utf-8")
    b.write_text(json.dumps(_projection(generated_at="t2", root_path="/y")), encoding="utf-8")
    assert gc._compare_projections(a, b) is None


def test_compare_projections_returns_diff_on_real_change(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_projection()), encoding="utf-8")
    b.write_text(
        json.dumps(_projection(relationships=[])),  # a relationship dropped
        encoding="utf-8",
    )
    diff = gc._compare_projections(a, b)
    assert diff is not None
    assert isinstance(diff, dict)


def test_pick_source_file_first_sorted_py_that_exists(tmp_path):
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "b.py").write_text("x = 1\n", encoding="utf-8")
    (src / "z.py").write_text("y = 2\n", encoding="utf-8")
    projection = tmp_path / "proj.json"
    projection.write_text(
        json.dumps({"files": [
            {"path": "z.py"}, {"path": "pkg/b.py"}, {"path": "readme.txt"},
        ]}),
        encoding="utf-8",
    )
    picked = gc._pick_source_file(projection, src)
    assert picked == src / "pkg" / "b.py"  # sorted: pkg/b.py before z.py


def test_pick_source_file_none_when_no_py_on_disk(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    projection = tmp_path / "proj.json"
    projection.write_text(
        json.dumps({"files": [{"path": "gone.py"}, {"path": "x.txt"}]}),
        encoding="utf-8",
    )
    assert gc._pick_source_file(projection, src) is None


# ---------------------------------------------------------------------------
# run_parity orchestration and exit code (hermetic: fetch + generation stubbed)
# ---------------------------------------------------------------------------


def _stub_harness(monkeypatch, tmp_path, generate):
    """Point run_parity at a temp tree with fetch/generation stubbed offline."""
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    monkeypatch.setattr(
        gc, "load_corpus",
        lambda name, golden_dir=None: {"name": name, "repo": "x", "commit": "a" * 40},
    )
    monkeypatch.setattr(
        gc, "fetch_corpus", lambda corpus, cache_dir=None, force=False: src
    )
    monkeypatch.setattr(gc, "_out_dir", lambda name, cache_dir=None: tmp_path / "out")
    monkeypatch.setattr(gc, "generate_projection", generate)
    return src


def test_run_parity_returns_zero_when_runs_match(tmp_path, monkeypatch):
    def generate(src, out_path, *, cold=True, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(_projection(generated_at="t")), encoding="utf-8")
        return out_path

    _stub_harness(monkeypatch, tmp_path, generate)
    assert gc.run_parity("demo", mutate=False) == 0


def test_run_parity_returns_one_on_divergence(tmp_path, monkeypatch, capsys):
    # The cold run and the warm run disagree on a real field, so parity fails and
    # the command exits 1 with a loud PARITY FAILURE (never papered over).
    def generate(src, out_path, *, cold=True, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        proj = _projection() if cold else _projection(relationships=[])
        out_path.write_text(json.dumps(proj), encoding="utf-8")
        return out_path

    _stub_harness(monkeypatch, tmp_path, generate)
    rc = gc.run_parity("demo", mutate=False)
    assert rc == 1
    assert "PARITY FAILURE" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# adversarial-review hardening (PR #77 findings)
# ---------------------------------------------------------------------------


def test_normalize_import_refuses_a_foreign_cached_module(monkeypatch, tmp_path):
    # Finding 1: the sys.path guard cannot beat an already-populated sys.modules
    # cache. Simulate a hosting process that imported a FOREIGN analyzer before
    # the harness loaded (both the package and its parity submodule are foreign,
    # which is what that scenario produces): the harness must refuse loudly
    # rather than silently compare with someone else's allowlist.
    import types

    foreign_dir = tmp_path / "elsewhere" / "analyzer"
    fake_pkg = types.ModuleType("analyzer")
    fake_pkg.__file__ = str(foreign_dir / "__init__.py")
    fake_pkg.__path__ = [str(foreign_dir)]
    fake_mod = types.ModuleType("analyzer.parity")
    fake_mod.__file__ = str(foreign_dir / "parity.py")
    fake_mod.normalize_for_parity = lambda p: "DECOY"
    fake_pkg.parity = fake_mod
    monkeypatch.setitem(sys.modules, "analyzer", fake_pkg)
    monkeypatch.setitem(sys.modules, "analyzer.parity", fake_mod)
    with pytest.raises(RuntimeError, match="outside this checkout"):
        gc._normalize_for_parity()


def test_normalize_import_accepts_this_checkout():
    fn = gc._normalize_for_parity()
    assert callable(fn)
    assert fn({"a": 1}) == fn({"a": 1})  # the real normalizer, working


def test_fetch_fast_path_restores_a_poisoned_tracked_file(tmp_path):
    # Finding 2: a hard kill between the parity mutation write and its finally
    # restore leaves a stray edit in a tracked file; the pin check alone would
    # then serve the poisoned tree to every later non-force run. The fast path
    # must restore tracked content while leaving untracked files (the analyzer
    # store) alone.
    cache = tmp_path / "cache"
    src = cache / "demo"
    src.mkdir(parents=True)

    def git(*args):
        subprocess.run(["git", "-C", str(src), *args], check=True,
                       capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (src / "app.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "app.py")
    git("commit", "-q", "-m", "pin")
    head = subprocess.run(
        ["git", "-C", str(src), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    # Poison a tracked file (the simulated interrupted mutation) and add an
    # untracked file (the simulated analyzer store) that must survive.
    (src / "app.py").write_text("x = 1\n# poisoned synthetic edit\n", encoding="utf-8")
    (src / "untracked-store.db").write_text("keep me", encoding="utf-8")

    corpus = {"name": "demo", "repo": "unused", "commit": head, "exclude": []}
    out = gc.fetch_corpus(corpus, cache_dir=cache)  # fast path: HEAD == pin
    assert out == src
    assert (src / "app.py").read_text(encoding="utf-8") == "x = 1\n"  # restored
    assert (src / "untracked-store.db").exists()  # untracked state untouched


# ---------------------------------------------------------------------------
# opt-in live parity against the real corpora
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("GOLDEN_CORPUS_NETWORK") != "1",
    reason="set GOLDEN_CORPUS_NETWORK=1 to run the live cold-vs-warm parity",
)
@pytest.mark.parametrize("corpus", ["flask", "fastapi"])
def test_live_parity_holds(corpus):
    res = subprocess.run(
        [sys.executable, str(HARNESS), "parity", corpus, "--force"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"parity failed:\n{res.stdout}\n{res.stderr}"
