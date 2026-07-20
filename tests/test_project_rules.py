"""Project knowledge layer: loader, gitattributes, provenance, enrichment (P6-12).

House style: real files, real stores, fail-before proofs, no mocks. The one
model boundary (the identify pass) is driven through the established injectable
``Invoker`` seam with a canned response, exactly as the Phase 7 passes are tested;
everything else runs deterministically with zero AI.

The card's accept criteria are encoded here:

  - loader precedence: a project rule overrides the built-in for the same path;
  - bad rules are rejected LOUDLY (stderr) and the rest of the file still loads;
  - ``.gitattributes`` Linguist overrides are honored and beaten by project rules;
  - gitignore glob semantics (``*.ext``, ``dir/**``, exact path, basename);
  - provenance is recorded per group and per sample path in build_inventory;
  - enrichment writes a valid rule for a real unknown on a real store and a
    second projection classifies it deterministically with zero AI;
  - human rules are never overwritten; the write round-trips through the loader;
  - the loader degrades gracefully when a rules file exists but PyYAML is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyzer.extract import extract_repo
from analyzer.project import rules as rules_mod
from analyzer.project.inventory import build_inventory, classify_row
from analyzer.project.rules import (
    PROJECT_RULES_RELPATH,
    compile_glob,
    load_repo_rules_raw,
    load_rule_set,
)
from analyzer.store import FactStore

# ---------------------------------------------------------------------------
# gitignore-style glob semantics
# ---------------------------------------------------------------------------

def test_glob_extension_matches_at_any_depth():
    rx = compile_glob("*.pdb")
    assert rx.search("app.pdb")
    assert rx.search("build/x/y/app.pdb")
    assert not rx.search("app.pdbx")
    assert not rx.search("app.txt")


def test_glob_double_star_directory_matches_contents():
    rx = compile_glob("coverage/**")
    assert rx.search("coverage/index.html")
    assert rx.search("coverage/a/b/c.html")
    assert not rx.search("coveragex/y")
    assert not rx.search("other/coverage/x")  # anchored: has a slash


def test_glob_exact_path_is_anchored():
    rx = compile_glob("src/config/legacy.txt")
    assert rx.search("src/config/legacy.txt")
    assert not rx.search("other/src/config/legacy.txt")


def test_glob_bare_name_matches_dir_and_contents():
    rx = compile_glob("node_modules")
    assert rx.search("node_modules")
    assert rx.search("node_modules/a/b.js")
    assert rx.search("packages/x/node_modules/dep.js")  # basename at any depth


def test_glob_empty_pattern_is_rejected():
    with pytest.raises(ValueError):
        compile_glob("   ")


# ---------------------------------------------------------------------------
# Loader precedence and loud rejection
# ---------------------------------------------------------------------------

def _write_rules(root: Path, body: str) -> Path:
    path = root / PROJECT_RULES_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_project_rule_overrides_builtin_for_the_same_path(tmp_path):
    # Fail-before: the built-in classifier calls a .log file build_test_output.
    assert classify_row("service.log", "excluded:unsupported_extension", ".log") == "build_test_output"
    # A project rule reclassifies that exact path to documentation.
    _write_rules(tmp_path, """
rules:
  - id: logs-are-docs-here
    pattern: '*.log'
    category: documentation
    source: human
""")
    rs = load_rule_set(tmp_path)
    rule = rs.match_project("service.log")
    assert rule is not None and rule.category == "documentation"

    rows = [{"path": "service.log", "disposition": "excluded:unsupported_extension", "reason": ".log"}]
    inv = build_inventory(rows, root=tmp_path)
    assert [g["id"] for g in inv["groups"]] == ["documentation"]
    assert inv["groups"][0]["rule_provenance"] == {"project:logs-are-docs-here": 1}


def test_bad_rule_is_rejected_loudly_and_the_rest_still_load(tmp_path, capsys):
    _write_rules(tmp_path, """
rules:
  - id: good
    pattern: '*.qzz'
    category: data
    source: ai-enrichment
  - id: bad-category
    pattern: '*.zzz'
    category: not_a_category
    source: ai-enrichment
  - id: bad-glob
    pattern: ''
    category: data
    source: human
  - id: bad-source
    pattern: '*.aaa'
    category: data
    source: robot
""")
    rs = load_rule_set(tmp_path)
    err = capsys.readouterr().err
    # The good rule survives; the three bad rules are named on stderr and skipped.
    assert [r.id for r in rs.project_rules] == ["good"]
    assert "bad-category" in err and "unknown category" in err
    assert "bad-glob" in err
    assert "bad-source" in err and "invalid source" in err


def test_repo_rule_beats_org_slot_later_source_wins(tmp_path):
    # The loader accepts an ordered list of sources (org slot then repo). A repo
    # rule for the same path must win over an org rule (later source wins).
    org = tmp_path / "org-rules.yml"
    org.write_text("""
rules:
  - id: org-classify
    pattern: '*.dat'
    category: data
    source: human
""", encoding="utf-8")
    _write_rules(tmp_path, """
rules:
  - id: repo-classify
    pattern: '*.dat'
    category: archive
    source: human
""")
    rs = load_rule_set(tmp_path, extra_sources=(org,))
    winner = rs.match_project("payload.dat")
    assert winner is not None and winner.id == "repo-classify" and winner.category == "archive"


def test_within_a_file_first_matching_rule_wins(tmp_path):
    _write_rules(tmp_path, """
rules:
  - id: first
    pattern: '*.dat'
    category: data
    source: human
  - id: second
    pattern: '*.dat'
    category: archive
    source: human
""")
    rs = load_rule_set(tmp_path)
    assert rs.match_project("x.dat").id == "first"


# ---------------------------------------------------------------------------
# .gitattributes Linguist honoring and precedence
# ---------------------------------------------------------------------------

def test_gitattributes_linguist_overrides_are_honored(tmp_path):
    (tmp_path / ".gitattributes").write_text(
        "docs/generated/** linguist-generated\n"
        "thirdparty/** linguist-vendored\n"
        "handbook/** linguist-documentation\n"
        "keep/** -linguist-vendored\n"        # unset form: ignored
        "off/** linguist-generated=false\n",  # false form: ignored
        encoding="utf-8",
    )
    rs = load_rule_set(tmp_path)
    assert rs.match_gitattributes("docs/generated/api.html") == "build_test_output"
    assert rs.match_gitattributes("thirdparty/lib.min.js") == "vendored"
    assert rs.match_gitattributes("handbook/intro.md") == "documentation"
    assert rs.match_gitattributes("keep/x") is None
    assert rs.match_gitattributes("off/x") is None


def test_project_rule_beats_gitattributes_beats_builtin(tmp_path):
    # The same path is claimable by all three tiers; project wins, then
    # gitattributes, then the built-in. Proven by classifying one path per tier.
    (tmp_path / ".gitattributes").write_text("assets/** linguist-vendored\n", encoding="utf-8")
    _write_rules(tmp_path, """
rules:
  - id: assets-are-product
    pattern: 'assets/hero.png'
    category: product_assets
    source: human
""")
    rows = [
        # project rule claims this exact file
        {"path": "assets/hero.png", "disposition": "binary", "reason": "skip_extension:.png"},
        # gitattributes claims the rest of assets/
        {"path": "assets/vendor.js", "disposition": "excluded:unsupported_extension", "reason": ".js"},
        # neither: falls to the built-in (a .DS_Store is os_cruft)
        {"path": ".DS_Store", "disposition": "binary", "reason": "skip_extension:.DS_Store"},
    ]
    inv = build_inventory(rows, root=tmp_path)
    by_id = {g["id"]: g for g in inv["groups"]}
    assert by_id["product_assets"]["rule_provenance"] == {"project:assets-are-product": 1}
    assert by_id["vendored"]["rule_provenance"] == {"gitattributes": 1}
    # The built-in os_cruft group carries no provenance key (all builtin).
    assert "rule_provenance" not in by_id["os_cruft"]


# ---------------------------------------------------------------------------
# Provenance in build_inventory (per group and per sample path)
# ---------------------------------------------------------------------------

def test_provenance_recorded_per_group_and_per_sample(tmp_path):
    _write_rules(tmp_path, """
rules:
  - id: qzz-data
    pattern: '*.qzz'
    category: data
    source: ai-enrichment
""")
    rows = [
        {"path": "a.qzz", "disposition": "excluded:unsupported_extension", "reason": ".qzz"},
        {"path": "b.csv", "disposition": "excluded:unsupported_extension", "reason": ".csv"},
    ]
    inv = build_inventory(rows, root=tmp_path)
    data = next(g for g in inv["groups"] if g["id"] == "data")
    # a.qzz classified by the project rule, b.csv by the built-in (both are data).
    assert data["rule_provenance"] == {"builtin": 1, "project:qzz-data": 1}
    prov_by_path = dict(zip(data["samples"], data["sample_provenance"]))
    assert prov_by_path["a.qzz"] == "project:qzz-data"
    assert prov_by_path["b.csv"] == "builtin"


def test_no_rules_means_no_provenance_keys_old_dataset_parity(tmp_path):
    # A repo with no rules and no gitattributes emits exactly the pre-P6-12 shape:
    # no rule_provenance / sample_provenance keys anywhere.
    rows = [{"path": "logo.png", "disposition": "binary", "reason": "skip_extension:.png"}]
    inv = build_inventory(rows, root=tmp_path)
    assert "rule_provenance" not in inv["groups"][0]
    assert "sample_provenance" not in inv["groups"][0]


def test_rule_overrides_group_label_and_recommendation(tmp_path):
    _write_rules(tmp_path, """
rules:
  - id: fixtures-are-data
    pattern: 'fixtures/**'
    category: data
    label: Test fixtures
    recommendation: Keep. These are golden inputs the tests pin.
    flags:
      likely_unwanted: false
    source: human
""")
    rows = [{"path": "fixtures/golden.bin", "disposition": "binary", "reason": "null_byte"}]
    inv = build_inventory(rows, root=tmp_path)
    g = inv["groups"][0]
    assert g["label"] == "Test fixtures"
    assert g["recommendation"].startswith("Keep. These are golden inputs")
    assert g["flags"]["likely_unwanted"] is False


# ---------------------------------------------------------------------------
# Graceful degradation when PyYAML is unavailable
# ---------------------------------------------------------------------------

def test_loader_degrades_loudly_without_pyyaml(tmp_path, capsys, monkeypatch):
    _write_rules(tmp_path, """
rules:
  - id: qzz-data
    pattern: '*.qzz'
    category: data
    source: ai-enrichment
""")
    # Simulate the minimal CI lane: PyYAML not importable.
    monkeypatch.setattr(rules_mod, "_yaml", None)
    rs = load_rule_set(tmp_path)
    err = capsys.readouterr().err
    assert rs.project_rules == []           # rules skipped, not applied
    assert "PyYAML is not installed" in err  # loud, not silent
    # And build_inventory does not crash: the .qzz stays unknown (built-in).
    rows = [{"path": "a.qzz", "disposition": "excluded:unsupported_extension", "reason": ".qzz"}]
    inv = build_inventory(rows, root=tmp_path, ruleset=rs)
    assert inv["groups"][0]["id"] == "unknown"


# ---------------------------------------------------------------------------
# Enrichment writes rules: pure writer round-trip + identify pass on a real store
# ---------------------------------------------------------------------------

def test_writer_round_trips_through_the_loader(tmp_path):
    from analyzer.enrich.rules_writer import write_inventory_rules

    result = write_inventory_rules(
        tmp_path,
        [
            {"pattern": "*.qzz", "category": "data", "explanation": "Custom blobs.",
             "evidence": ["weird.qzz"]},
            {"pattern": "bad", "category": "not_real"},  # rejected, not written
        ],
        added="2026-07-19",
    )
    assert result.changed is True
    assert len(result.written) == 1
    assert any("not_real" in r for r in result.rejected)
    # The file the writer produced loads cleanly and classifies the unknown.
    loaded = load_repo_rules_raw(tmp_path)
    assert [r.pattern for r in loaded] == ["*.qzz"]
    assert loaded[0].source == "ai-enrichment" and loaded[0].added == "2026-07-19"


def test_writer_dedupes_and_never_overwrites_human_rules(tmp_path):
    from analyzer.enrich.rules_writer import write_inventory_rules

    _write_rules(tmp_path, """
rules:
  - id: human-qzz
    pattern: '*.qzz'
    category: config
    source: human
""")
    result = write_inventory_rules(
        tmp_path,
        [
            {"pattern": "*.qzz", "category": "config"},  # exact dupe -> skipped
            {"pattern": "*.qzz", "category": "data"},    # contradicts human pattern -> protected
            {"pattern": "*.new", "category": "archive"}, # genuinely new -> written
        ],
        added="2026-07-19",
    )
    assert result.written and "*.new" in load_repo_rules_raw(tmp_path)[-1].pattern
    assert result.skipped_duplicate  # the (pattern, category) dupe
    assert "*.qzz" in result.skipped_human  # human pattern protected
    # The human rule is untouched and still first (it still wins).
    loaded = load_repo_rules_raw(tmp_path)
    assert loaded[0].id == "human-qzz" and loaded[0].source == "human"


def _build_store(repo: Path, db: Path) -> None:
    store = FactStore(str(db))
    extract_repo(repo, store)
    store.commit()
    store.close()


class _CannedInvoker:
    """Returns a fixed rules JSON, standing in for the model (the P7 seam)."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def __call__(self, prompt: str):
        from analyzer.enrich.engine import InvokeResult

        self.calls += 1
        return InvokeResult(ok=True, cost_usd=0.01, text=json.dumps(self.payload))


def test_identify_writes_a_rule_and_second_projection_classifies_with_zero_ai(tmp_path):
    from analyzer.enrich.identify import IdentifyConfig, collect_unknowns, identify_unknowns

    # A real repo with a genuinely unknown non-source file. The store lives OUTSIDE
    # the repo so its sqlite sidecar files do not become inventory rows.
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "telemetry.qzz").write_text("opaque blob", encoding="utf-8")
    db = tmp_path / "index.db"
    _build_store(repo, db)

    # Fail-before: the file is unknown to the deterministic classifier.
    store = FactStore(str(db))
    assert "telemetry.qzz" in collect_unknowns(store, repo)
    store.close()

    invoker = _CannedInvoker({"rules": [
        {"pattern": "*.qzz", "category": "data",
         "explanation": "Opaque telemetry blobs from the device.",
         "recommendation": "Keep, but store large captures outside the tree.",
         "evidence": ["telemetry.qzz"]},
    ]})
    report = identify_unknowns(
        IdentifyConfig(store_path=db, root=repo, added="2026-07-19"), invoker=invoker
    )
    assert invoker.calls == 1
    assert report.written == ["ai-data-qzz"]

    # The rule file the pass wrote loads and reclassifies the unknown, with NO AI.
    store = FactStore(str(db))
    inv = build_inventory(store.coverage(), root=repo)
    store.close()
    data = next(g for g in inv["groups"] if g["id"] == "data")
    assert data["rule_provenance"].get("project:ai-data-qzz") == 1
    # The unknown telemetry file is no longer unknown.
    store = FactStore(str(db))
    assert "telemetry.qzz" not in collect_unknowns(store, repo)
    store.close()


def test_identify_dry_run_invokes_nothing(tmp_path):
    from analyzer.enrich.identify import IdentifyConfig, identify_unknowns

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "mystery.qzz").write_text("blob", encoding="utf-8")
    db = tmp_path / "index.db"
    _build_store(repo, db)

    class _Exploding:
        def __call__(self, prompt: str):
            raise AssertionError("dry run must not invoke the model")

    report = identify_unknowns(
        IdentifyConfig(store_path=db, root=repo, dry_run=True), invoker=_Exploding()
    )
    assert report.dry_run is True
    assert report.written == []
    assert not (repo / PROJECT_RULES_RELPATH).exists()


def test_identify_no_unknowns_is_a_clean_noop(tmp_path):
    from analyzer.enrich.identify import IdentifyConfig, identify_unknowns

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    db = tmp_path / "index.db"
    _build_store(repo, db)

    class _Exploding:
        def __call__(self, prompt: str):
            raise AssertionError("nothing to identify should not invoke the model")

    report = identify_unknowns(
        IdentifyConfig(store_path=db, root=repo), invoker=_Exploding()
    )
    assert report.written == []
    assert report.ok is True


# ---------------------------------------------------------------------------
# Adversarial-review fixes (PR #47)
# ---------------------------------------------------------------------------


def test_star_heavy_pattern_is_guarded_not_exponential():
    # ReDoS guard: pre-fix, x + 24 stars + y compiled to adjacent unbounded
    # quantifiers and took tens of seconds against a short non-matching path;
    # 40 stars hung indefinitely. Post-fix star runs collapse to the ** they
    # mean and the match is instant.
    import time

    from analyzer.project.rules import compile_glob

    rx = compile_glob("x" + "*" * 40 + "y")
    t0 = time.monotonic()
    assert rx.match("a/b/" + "c" * 30) is None
    assert time.monotonic() - t0 < 0.5, "star-heavy pattern must not backtrack"
    # And it still means what ** means.
    assert rx.match("xanythingy") or rx.match("x/deep/path/y") or rx.match("xy")


def test_absurd_patterns_are_rejected_loudly():
    import pytest as _pytest

    from analyzer.project.rules import compile_glob

    with _pytest.raises(ValueError):
        compile_glob("a" * 600)
    with _pytest.raises(ValueError):
        compile_glob("*a" * 40)


def test_writer_explicit_id_collision_gets_a_unique_id(tmp_path):
    # Pre-fix: a proposed rule carrying an id that collides with an existing
    # rule was appended as a duplicate, reported written, and then silently
    # dropped by the loader's keep-the-first rule on reload. Post-fix the
    # explicit id goes through the collision machinery and BOTH rules survive
    # a round trip.
    from analyzer.enrich.rules_writer import write_inventory_rules
    from analyzer.project.rules import load_repo_rules_raw

    root = tmp_path
    first = write_inventory_rules(
        root,
        [{"id": "myrule", "pattern": "*.ai", "category": "data",
          "source": "ai-enrichment"}],
    )
    assert "myrule" in first.written
    second = write_inventory_rules(
        root,
        [{"id": "myrule", "pattern": "*.psd", "category": "product_assets",
          "source": "ai-enrichment"}],
    )
    assert second.written, "the colliding proposal must still be written"
    new_id = second.written[0]
    assert new_id != "myrule", "the collision must mint a distinct id"

    rules = load_repo_rules_raw(root)
    ids = [r.id for r in rules]
    assert ids.count("myrule") == 1
    assert new_id in ids
    patterns = {r.id: r.pattern for r in rules}
    assert patterns["myrule"] == "*.ai"
    assert patterns[new_id] == "*.psd"


def test_writer_scaffolds_a_sidecar_gitignore_for_the_rules(tmp_path):
    # Knowledge travels with the repo: the writer scaffolds
    # .solution-explorer/.gitignore ignoring everything except rules/, so a
    # repo-level ".solution-explorer/" ignore no longer buries the learned
    # rules (dogfood finding). An existing sidecar is never overwritten.
    from analyzer.enrich.rules_writer import write_inventory_rules

    write_inventory_rules(
        tmp_path,
        [{"pattern": "*.xyz", "category": "data", "source": "ai-enrichment"}],
    )
    sidecar = tmp_path / ".solution-explorer" / ".gitignore"
    assert sidecar.exists()
    body = sidecar.read_text()
    assert "*" in body and "!rules/" in body and "!.gitignore" in body

    sidecar.write_text("# user edited\n")
    write_inventory_rules(
        tmp_path,
        [{"pattern": "*.abc", "category": "data", "source": "ai-enrichment"}],
    )
    assert sidecar.read_text() == "# user edited\n", "never overwrite a user sidecar"
