"""Tests for scripts/demo-site.py (N3, the demo-program harness).

Hermetic: no test in this file talks to the network. `fetch_corpus`'s
shallow-to-full repair is exercised against a local temp git repo (a plain
directory used as a "remote" via a filesystem path, which `git` treats like
any other remote without any network I/O). Everything that would otherwise
touch `~/dev/.demo-corpus` or `demos/registry|runs|hub` is redirected to a
per-test tmp_path via the autouse `_isolated_dirs` fixture, the same pattern
tests/test_golden_corpus.py uses for GOLDEN_DIR/CACHE_DIR.

Module-loading note: scripts/demo-site.py uses `@dataclass` (GateResult).
Loading a module via `importlib.util.spec_from_file_location` +
`exec_module` WITHOUT first registering it in `sys.modules` makes
`dataclasses._is_type`'s introspection crash (it looks the module up in
`sys.modules` by name), so `_load_module` below registers before executing.
tests/test_golden_corpus.py does not need this because golden-corpus.py has
no dataclasses.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "scripts" / "demo-site.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("demo_site", HARNESS)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ds = _load_module()


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    """Redirect every module-level path constant into a per-test tmp_path so
    no test can read or write the real demos/ tree or the real corpus cache."""
    registry_dir = tmp_path / "registry"
    runs_dir = tmp_path / "runs"
    hub_dir = tmp_path / "hub"
    corpus_dir = tmp_path / "corpus"
    for d in (registry_dir, runs_dir, hub_dir, corpus_dir):
        d.mkdir()
    monkeypatch.setattr(ds, "REGISTRY_DIR", registry_dir)
    monkeypatch.setattr(ds, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(ds, "HUB_DIR", hub_dir)
    monkeypatch.setattr(ds, "CORPUS_DIR", corpus_dir)
    return registry_dir, runs_dir, hub_dir, corpus_dir


def _write_registry(registry_dir: Path, slug: str = "demo1", **overrides) -> dict:
    doc = {
        "slug": slug,
        "subject": {
            "name": "Demo One", "repo": "https://example.com/demo1.git",
            "license": "MIT", "governance": "corporate",
        },
        "track": "published",
        "policy": {"follow": "default-branch", "pin": None, "exclude": [], "history": "full"},
        "hosting": {"cf_project": slug, "url": f"https://{slug}.example.com"},
        "cadence": "weekly",
        "budget": {"max_cost_usd": 5.0, "max_wall_minutes": 45},
        "gates": {"coverage": "complete", "max_detect_only_line_share": 0.25, "min_enrichment_score": 85},
        "consent": {"required": False, "state": "n/a", "contacted": None},
    }
    doc.update(overrides)
    (registry_dir / f"{slug}.json").write_text(json.dumps(doc), encoding="utf-8")
    return doc


def _write_report(runs_dir: Path, slug: str, date: str, *, status: str = "ok") -> None:
    d = runs_dir / slug / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps({"status": status, "date": date}), encoding="utf-8")


def _init_local_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)


def _commit(path: Path, name: str, content: str) -> None:
    (path / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", f"write {name}={content}"], check=True)


def _log_count(repo: Path) -> int:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return len(out.splitlines()) if out else 0


# ---------------------------------------------------------------------------
# Registry loading and schema validation
# ---------------------------------------------------------------------------


def test_load_registry_valid(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    doc = ds.load_registry("demo1", registry_dir)
    assert doc["slug"] == "demo1"
    assert doc["subject"]["name"] == "Demo One"
    assert doc["policy"]["history"] == "full"


def test_load_registry_missing_file_raises(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    with pytest.raises(FileNotFoundError):
        ds.load_registry("nope", registry_dir)


def test_load_registry_defaults_history_to_full_when_absent(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    doc = _write_registry(registry_dir, slug="demo1")
    del doc["policy"]["history"]
    (registry_dir / "demo1.json").write_text(json.dumps(doc), encoding="utf-8")
    loaded = ds.load_registry("demo1", registry_dir)
    assert loaded["policy"]["history"] == "full"


def test_load_registry_missing_required_key_raises(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    doc = _write_registry(registry_dir, slug="demo1")
    del doc["hosting"]["cf_project"]
    (registry_dir / "demo1.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="hosting.cf_project"):
        ds.load_registry("demo1", registry_dir)


def test_load_registry_slug_mismatch_raises(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    doc = _write_registry(registry_dir, slug="demo1")
    doc["slug"] = "other"
    (registry_dir / "demo1.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        ds.load_registry("demo1", registry_dir)


def test_validate_registry_bad_follow_value():
    errors = ds.validate_registry({
        "slug": "x", "subject": {}, "track": "published",
        "policy": {"follow": "whenever", "pin": None, "exclude": [], "history": "full"},
        "hosting": {}, "cadence": "weekly", "budget": {}, "gates": {}, "consent": {},
    })
    assert any("policy.follow" in e for e in errors)


def test_validate_registry_pinned_without_pin_is_an_error():
    errors = ds.validate_registry({
        "slug": "x", "subject": {}, "track": "published",
        "policy": {"follow": "pinned", "pin": None, "exclude": [], "history": "full"},
        "hosting": {}, "cadence": "weekly", "budget": {}, "gates": {}, "consent": {},
    })
    assert any("pinned" in e for e in errors)


def test_validate_registry_unknown_cadence_is_an_error():
    errors = ds.validate_registry({
        "slug": "x", "subject": {}, "track": "published",
        "policy": {"follow": "default-branch", "pin": None, "exclude": [], "history": "full"},
        "hosting": {}, "cadence": "fortnightly", "budget": {}, "gates": {}, "consent": {},
    })
    assert any("cadence" in e for e in errors)


def test_real_vscode_registry_entry_loads_and_validates():
    """The committed demos/registry/vscode.json must itself be a valid entry."""
    doc = ds.load_registry("vscode", REPO_ROOT / "demos" / "registry")
    assert doc["slug"] == "vscode"
    assert doc["policy"]["follow"] == "default-branch"
    assert doc["policy"]["history"] == "full"
    assert doc["gates"]["min_enrichment_score"] == 85
    assert doc["consent"]["required"] is False


def test_list_registry_and_iter_registry(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="bbb")
    _write_registry(registry_dir, slug="aaa")
    assert ds.list_registry(registry_dir) == ["aaa", "bbb"]
    corpora = ds.iter_registry(registry_dir)
    assert [c["slug"] for c in corpora] == ["aaa", "bbb"]


# ---------------------------------------------------------------------------
# Cadence / due calculation
# ---------------------------------------------------------------------------


def test_cadence_period_seconds_known_values():
    assert ds.cadence_period_seconds("daily") == 86_400
    assert ds.cadence_period_seconds("weekly") == 7 * 86_400
    assert ds.cadence_period_seconds("monthly") == 30 * 86_400


def test_cadence_period_seconds_unknown_raises():
    with pytest.raises(ValueError):
        ds.cadence_period_seconds("fortnightly")


def test_is_due_true_when_never_run(_isolated_dirs):
    registry_dir, runs_dir, *_ = _isolated_dirs
    corpus = _write_registry(registry_dir)
    assert ds.is_due(corpus, runs_dir) is True


def test_is_due_false_within_cadence(_isolated_dirs):
    registry_dir, runs_dir, *_ = _isolated_dirs
    corpus = _write_registry(registry_dir, cadence="weekly")
    today = datetime.now(timezone.utc).date().isoformat()
    _write_report(runs_dir, corpus["slug"], today, status="ok")
    assert ds.is_due(corpus, runs_dir) is False


def test_is_due_true_after_cadence_elapsed(_isolated_dirs):
    registry_dir, runs_dir, *_ = _isolated_dirs
    corpus = _write_registry(registry_dir, cadence="weekly")
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    _write_report(runs_dir, corpus["slug"], old_date, status="ok")
    assert ds.is_due(corpus, runs_dir) is True


def test_is_due_ignores_a_run_that_did_not_succeed(_isolated_dirs):
    registry_dir, runs_dir, *_ = _isolated_dirs
    corpus = _write_registry(registry_dir, cadence="weekly")
    today = datetime.now(timezone.utc).date().isoformat()
    _write_report(runs_dir, corpus["slug"], today, status="incomplete")
    assert ds.is_due(corpus, runs_dir) is True


# ---------------------------------------------------------------------------
# Finding fingerprint: stable, and sensitive to every input
# ---------------------------------------------------------------------------


def test_fingerprint_format():
    fp = ds.finding_fingerprint("vscode", "coverage_ledger_complete", "3 files unaccounted")
    assert fp.startswith("demo-finding:vscode:coverage_ledger_complete:")
    digest = fp.rsplit(":", 1)[-1]
    assert len(digest) == 12


def test_fingerprint_stable_across_calls():
    a = ds.finding_fingerprint("vscode", "coverage_ledger_complete", "3 files unaccounted")
    b = ds.finding_fingerprint("vscode", "coverage_ledger_complete", "3 files unaccounted")
    assert a == b


def test_fingerprint_differs_by_slug():
    a = ds.finding_fingerprint("vscode", "check", "detail")
    b = ds.finding_fingerprint("kubernetes", "check", "detail")
    assert a != b


def test_fingerprint_differs_by_check():
    a = ds.finding_fingerprint("vscode", "check_a", "detail")
    b = ds.finding_fingerprint("vscode", "check_b", "detail")
    assert a != b


def test_fingerprint_differs_by_detail():
    a = ds.finding_fingerprint("vscode", "check", "detail A")
    b = ds.finding_fingerprint("vscode", "check", "detail B")
    assert a != b


# ---------------------------------------------------------------------------
# validate: NOT_IMPLEMENTED strictness
# ---------------------------------------------------------------------------


def test_overall_ok_all_pass_is_ok():
    results = [ds.GateResult("a", "PASS"), ds.GateResult("b", "PASS")]
    assert ds.overall_ok(results, False) is True


def test_overall_ok_strict_blocks_on_not_implemented():
    results = [ds.GateResult("a", "PASS"), ds.GateResult("b", "NOT_IMPLEMENTED")]
    assert ds.overall_ok(results, False) is False


def test_overall_ok_allow_unimplemented_tolerates_not_implemented():
    results = [ds.GateResult("a", "PASS"), ds.GateResult("b", "NOT_IMPLEMENTED")]
    assert ds.overall_ok(results, True) is True


def test_overall_ok_fail_blocks_even_with_allow_unimplemented():
    results = [ds.GateResult("a", "PASS"), ds.GateResult("b", "FAIL")]
    assert ds.overall_ok(results, False) is False
    assert ds.overall_ok(results, True) is False


def test_overall_ok_skip_blocks_even_with_allow_unimplemented():
    results = [ds.GateResult("a", "PASS"), ds.GateResult("b", "SKIP")]
    assert ds.overall_ok(results, False) is False
    assert ds.overall_ok(results, True) is False


def test_cmd_validate_strict_default_exits_nonzero_on_not_implemented(_isolated_dirs, monkeypatch):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    fixed = [ds.GateResult("a", "PASS", "ok"), ds.GateResult("b", "NOT_IMPLEMENTED", "no instrument")]
    monkeypatch.setattr(ds, "run_gates", lambda corpus, corpus_dir=None: fixed)

    rc = ds.main(["validate", "demo1"])
    assert rc == 1


def test_cmd_validate_allow_unimplemented_exits_zero(_isolated_dirs, monkeypatch):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    fixed = [ds.GateResult("a", "PASS", "ok"), ds.GateResult("b", "NOT_IMPLEMENTED", "no instrument")]
    monkeypatch.setattr(ds, "run_gates", lambda corpus, corpus_dir=None: fixed)

    rc = ds.main(["validate", "demo1", "--allow-unimplemented"])
    assert rc == 0


def test_cmd_validate_never_downgrades_a_real_fail(_isolated_dirs, monkeypatch):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    fixed = [ds.GateResult("a", "FAIL", "really failed"), ds.GateResult("b", "NOT_IMPLEMENTED", "no instrument")]
    monkeypatch.setattr(ds, "run_gates", lambda corpus, corpus_dir=None: fixed)

    assert ds.main(["validate", "demo1"]) == 1
    assert ds.main(["validate", "demo1", "--allow-unimplemented"]) == 1


def test_gate_classification_audit_is_always_not_implemented():
    """DEMO-PROGRAM.md 5.3's instrument does not exist, so this gate can never
    legitimately report anything else."""
    assert ds.gate_classification_accuracy_audit().state == "NOT_IMPLEMENTED"


def test_license_review_gate_fails_without_a_review_block():
    assert ds.gate_license_review_recorded({"track": "published"}).state == "FAIL"


def test_license_review_gate_fails_when_the_record_file_is_absent():
    r = ds.gate_license_review_recorded({
        "track": "published",
        "license_review": {
            "reviewer": "somebody", "date": "2026-08-20", "spdx": "MIT",
            "record": "docs/publication/license-reviews/does-not-exist.md",
            "countersigned_by_owner": True,
        },
    })
    assert r.state == "FAIL"
    assert "does not exist" in r.detail


def test_license_review_gate_fails_a_published_demo_without_owner_countersignature():
    """The legal sign-off is the owner's to give. A review signed only by the
    tool that wants to publish is not the check 6.1 asks for."""
    r = ds.gate_license_review_recorded({
        "track": "published",
        "license_review": {
            "reviewer": "Claude (Opus 5), N3", "date": "2026-08-20", "spdx": "MIT",
            "record": "docs/publication/license-reviews/vscode.md",
            "countersigned_by_owner": False,
        },
    })
    assert r.state == "FAIL"
    assert "countersigned" in r.detail


def test_license_review_gate_passes_when_recorded_and_countersigned():
    r = ds.gate_license_review_recorded({
        "track": "published",
        "license_review": {
            "reviewer": "Claude (Opus 5), N3", "date": "2026-08-20", "spdx": "MIT",
            "record": "docs/publication/license-reviews/vscode.md",
            "countersigned_by_owner": True,
        },
    })
    assert r.state == "PASS"


# ---------------------------------------------------------------------------
# Individual gate mechanics (synthetic fixtures, no analyzer run needed)
# ---------------------------------------------------------------------------


def test_gate_consent_triage_not_required_passes():
    r = ds.gate_consent_triage({"required": False, "state": "n/a", "contacted": None})
    assert r.state == "PASS"


def test_gate_consent_triage_required_and_uncleared_fails():
    r = ds.gate_consent_triage({"required": True, "state": None, "contacted": None})
    assert r.state == "FAIL"


def test_gate_consent_triage_required_and_cleared_passes():
    r = ds.gate_consent_triage({"required": True, "state": "approved", "contacted": "2026-08-01"})
    assert r.state == "PASS"


def test_gate_split_projection_skips_without_manifest(tmp_path):
    assert ds.gate_split_projection(tmp_path / "architecture").state == "SKIP"


def test_gate_split_projection_fails_without_shards(tmp_path):
    arch = tmp_path / "architecture"
    arch.mkdir()
    (arch / "manifest.json").write_text("{}", encoding="utf-8")
    assert ds.gate_split_projection(arch).state == "FAIL"


def test_gate_split_projection_passes_with_shards(tmp_path):
    arch = tmp_path / "architecture"
    data = arch / "data"
    data.mkdir(parents=True)
    (arch / "manifest.json").write_text("{}", encoding="utf-8")
    (data / "detail-x.json").write_text("{}", encoding="utf-8")
    assert ds.gate_split_projection(arch).state == "PASS"


def test_gate_detect_only_share_pass_under_limit(tmp_path):
    arch = tmp_path / "architecture"
    arch.mkdir()
    manifest = {"stats": {"languages": {"typescript": 900, "kotlin": 100}}}
    (arch / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    r = ds.gate_detect_only_share(arch, {"max_detect_only_line_share": 0.25})
    assert r.state == "PASS"


def test_gate_detect_only_share_fail_over_limit(tmp_path):
    arch = tmp_path / "architecture"
    arch.mkdir()
    manifest = {"stats": {"languages": {"typescript": 500, "kotlin": 500}}}
    (arch / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    r = ds.gate_detect_only_share(arch, {"max_detect_only_line_share": 0.25})
    assert r.state == "FAIL"


def test_gate_front_door_agrees_catches_s3_mismatch(tmp_path):
    arch = tmp_path / "architecture"
    arch.mkdir()
    manifest = {"components": [{"id": "c1", "ai_enhance": {"description": "x"}}]}
    (arch / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    ai_json = {"dataset": {"enriched": False}, "endpoints": []}
    (arch / "ai.json").write_text(json.dumps(ai_json), encoding="utf-8")
    r = ds.gate_front_door_agrees(arch)
    assert r.state == "FAIL"
    assert "S3" in r.detail


def test_gate_front_door_agrees_passes_when_consistent(tmp_path):
    arch = tmp_path / "architecture"
    arch.mkdir()
    manifest = {"components": [{"id": "c1"}]}
    (arch / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    ai_json = {"dataset": {"enriched": False}, "endpoints": []}
    (arch / "ai.json").write_text(json.dumps(ai_json), encoding="utf-8")
    r = ds.gate_front_door_agrees(arch)
    assert r.state == "PASS"


def test_gate_coverage_complete_skips_without_store(tmp_path):
    r = ds.gate_coverage_complete(tmp_path / "missing.db", tmp_path)
    assert r.state == "SKIP"


def test_gate_coverage_complete_pass_then_fail_on_unaccounted_file(tmp_path):
    from analyzer.store import FactStore

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n", encoding="utf-8")
    (src / "b.py").write_text("y = 2\n", encoding="utf-8")

    store_path = tmp_path / "index.db"
    fs = FactStore(str(store_path))
    fs.add_coverage("a.py", "parsed")
    fs.add_coverage("b.py", "parsed")
    fs.commit()
    fs.close()

    assert ds.gate_coverage_complete(store_path, src).state == "PASS"

    (src / "c.py").write_text("z = 3\n", encoding="utf-8")
    r2 = ds.gate_coverage_complete(store_path, src)
    assert r2.state == "FAIL"
    assert "c.py" in r2.detail


# ---------------------------------------------------------------------------
# deploy: refuses to run without DEMO_DEPLOY_ALLOW
# ---------------------------------------------------------------------------

def _make_bundle(slug: str, *, gate: bool = True, viewer: bool = True, license: bool = True) -> Path:
    """Build a minimally-valid deployable bundle, or one deliberately missing a part."""
    bundle = ds._bundle_dir(slug)
    bundle.mkdir(parents=True, exist_ok=True)
    if viewer:
        (bundle / "index.html").write_text("<!doctype html><title>demo</title>")
    if gate:
        (bundle / "functions").mkdir(parents=True, exist_ok=True)
        (bundle / "functions" / "_middleware.js").write_text("export function onRequest(){}")
    if license:
        (bundle / "UPSTREAM-LICENSE.txt").write_text("MIT License\n")
    return bundle




def test_deploy_dry_run_when_env_not_set(_isolated_dirs, monkeypatch, capsys):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    _make_bundle("demo1")
    monkeypatch.delenv(ds.DEMO_DEPLOY_ALLOW_ENV, raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called on a dry run")
    monkeypatch.setattr(ds.subprocess, "run", _boom)

    rc = ds.main(["deploy", "demo1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert ds.DEMO_DEPLOY_ALLOW_ENV in out


def test_deploy_runs_when_env_is_set(_isolated_dirs, monkeypatch):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    _make_bundle("demo1")
    monkeypatch.setenv(ds.DEMO_DEPLOY_ALLOW_ENV, "1")

    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(ds.subprocess, "run", _fake_run)

    rc = ds.main(["deploy", "demo1"])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0][:3] == ["wrangler", "pages", "deploy"]
    assert "--project-name" in calls[0]


def test_deploy_dry_run_flag_wins_even_when_env_is_set(_isolated_dirs, monkeypatch):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    _make_bundle("demo1")
    monkeypatch.setenv(ds.DEMO_DEPLOY_ALLOW_ENV, "1")

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called when --dry-run is passed")
    monkeypatch.setattr(ds.subprocess, "run", _boom)

    rc = ds.main(["deploy", "demo1", "--dry-run"])
    assert rc == 0


def test_deploy_missing_bundle_errors_without_touching_subprocess(_isolated_dirs, monkeypatch):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    # No architecture/ directory created: nothing has been analyzed yet.
    monkeypatch.setenv(ds.DEMO_DEPLOY_ALLOW_ENV, "1")

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called with no bundle")
    monkeypatch.setattr(ds.subprocess, "run", _boom)

    rc = ds.main(["deploy", "demo1"])
    assert rc == 2


# ---------------------------------------------------------------------------
# fetch: ref resolution and the shallow-to-full repair path
# (local temp git repos only; no network)
# ---------------------------------------------------------------------------


def test_resolve_ref_pinned_needs_no_network():
    ref, desc = ds.resolve_ref("https://example.invalid/does-not-exist.git", {"follow": "pinned", "pin": "deadbeef"})
    assert ref == "deadbeef"
    assert desc == "pinned:deadbeef"


def test_resolve_ref_pinned_without_pin_raises():
    with pytest.raises(ValueError):
        ds.resolve_ref("https://example.invalid/x.git", {"follow": "pinned", "pin": None})


def test_resolve_ref_default_branch_local_repo(tmp_path):
    remote = tmp_path / "remote"
    _init_local_repo(remote)
    _commit(remote, "a.txt", "one")
    ref, desc = ds.resolve_ref(str(remote), {"follow": "default-branch"})
    assert ref == "main"
    assert desc == "default-branch:main"


def test_resolve_ref_latest_tag_local_repo(tmp_path):
    remote = tmp_path / "remote"
    _init_local_repo(remote)
    _commit(remote, "a.txt", "one")
    subprocess.run(["git", "-C", str(remote), "tag", "v1.0.0"], check=True)
    _commit(remote, "a.txt", "two")
    subprocess.run(["git", "-C", str(remote), "tag", "v1.1.0"], check=True)
    ref, desc = ds.resolve_ref(str(remote), {"follow": "latest-tag"})
    assert ref == "v1.1.0"
    assert desc == "latest-tag:v1.1.0"


def test_fetch_corpus_shallow_clone_is_shallow(tmp_path, _isolated_dirs):
    _, _, _, corpus_dir = _isolated_dirs
    remote = tmp_path / "remote"
    _init_local_repo(remote)
    _commit(remote, "a.txt", "one")
    _commit(remote, "a.txt", "two")
    _commit(remote, "a.txt", "three")

    corpus = {
        "slug": "shallowtest",
        "subject": {"repo": str(remote)},
        "policy": {"follow": "default-branch", "pin": None, "exclude": [], "history": "shallow"},
    }
    src, sha = ds.fetch_corpus(corpus, corpus_dir)
    assert ds._is_shallow(src) is True
    assert _log_count(src) == 1
    assert sha  # a real resolved SHA was recorded

    state = ds.read_fetch_state("shallowtest", corpus_dir)
    assert state["resolved_sha"] == sha
    assert state["resolved_ref"] == "default-branch:main"


def test_fetch_corpus_repairs_existing_shallow_clone_to_full(tmp_path, _isolated_dirs):
    """THE shallow-to-full repair path: an existing shallow corpus clone, under
    a registry entry now saying `policy.history: full`, must be deepened in
    place with `git fetch --unshallow` rather than left shallow or re-cloned."""
    _, _, _, corpus_dir = _isolated_dirs
    remote = tmp_path / "remote"
    _init_local_repo(remote)
    _commit(remote, "a.txt", "one")
    _commit(remote, "a.txt", "two")
    _commit(remote, "a.txt", "three")

    corpus = {
        "slug": "repairtest",
        "subject": {"repo": str(remote)},
        "policy": {"follow": "default-branch", "pin": None, "exclude": [], "history": "shallow"},
    }
    src1, sha1 = ds.fetch_corpus(corpus, corpus_dir)
    assert ds._is_shallow(src1) is True
    assert _log_count(src1) == 1

    corpus["policy"]["history"] = "full"
    src2, sha2 = ds.fetch_corpus(corpus, corpus_dir)

    assert src2 == src1  # the same clone was repaired, not thrown away
    assert sha2 == sha1  # same commit, just with full history now available
    assert ds._is_shallow(src2) is False
    assert _log_count(src2) == 3


def test_fetch_corpus_full_policy_is_never_reshallowed(tmp_path, _isolated_dirs):
    """The converse of the repair path is deliberately a no-op: a full clone
    under a 'shallow' policy is left full (see fetch_corpus's docstring)."""
    _, _, _, corpus_dir = _isolated_dirs
    remote = tmp_path / "remote"
    _init_local_repo(remote)
    _commit(remote, "a.txt", "one")
    _commit(remote, "a.txt", "two")

    corpus = {
        "slug": "fulltest",
        "subject": {"repo": str(remote)},
        "policy": {"follow": "default-branch", "pin": None, "exclude": [], "history": "full"},
    }
    src, _sha = ds.fetch_corpus(corpus, corpus_dir)
    assert ds._is_shallow(src) is False
    assert _log_count(src) == 2

    corpus["policy"]["history"] = "shallow"
    src2, _sha2 = ds.fetch_corpus(corpus, corpus_dir)
    assert ds._is_shallow(src2) is False
    assert _log_count(src2) == 2


def test_fetch_corpus_restores_a_dirty_tracked_file(tmp_path, _isolated_dirs):
    """The restore-dirty-tracked-files defence, carried over from
    golden-corpus.py's fetch_corpus: a stray edit to a tracked file left by an
    interrupted run must not survive into the next fetch."""
    _, _, _, corpus_dir = _isolated_dirs
    remote = tmp_path / "remote"
    _init_local_repo(remote)
    _commit(remote, "a.txt", "one")

    corpus = {
        "slug": "dirtytest",
        "subject": {"repo": str(remote)},
        "policy": {"follow": "default-branch", "pin": None, "exclude": [], "history": "full"},
    }
    src, _sha = ds.fetch_corpus(corpus, corpus_dir)
    (src / "a.txt").write_text("POISONED", encoding="utf-8")

    ds.fetch_corpus(corpus, corpus_dir)
    assert (src / "a.txt").read_text(encoding="utf-8") == "one"


# ---------------------------------------------------------------------------
# deploy: the obligations are refusals, not warnings
#
# These are the important tests in this file. The projection output directory is
# data, not a site: deploying it publishes raw JSON with no viewer and, decisive
# here, no functions/_middleware.js, so the preview gate is absent and the
# deployment is fully public. DISCLOSURE-POLICY.md step 3 forbids exactly that.
# DEMO_DEPLOY_ALLOW authorizes a deploy; it must never be able to authorize an
# unsafe one.
# ---------------------------------------------------------------------------


def test_deploy_refuses_a_bundle_with_no_preview_gate(_isolated_dirs, monkeypatch, capsys):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    _make_bundle("demo1", gate=False)
    monkeypatch.setenv(ds.DEMO_DEPLOY_ALLOW_ENV, "1")

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called for an ungated bundle")
    monkeypatch.setattr(ds.subprocess, "run", _boom)

    rc = ds.main(["deploy", "demo1"])
    assert rc == 2
    assert "_middleware.js" in capsys.readouterr().err


def test_deploy_refuses_raw_projection_data_as_a_bundle(_isolated_dirs, monkeypatch, capsys):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    # What `analyze` produces: data, no index.html, no functions/.
    bundle = ds._bundle_dir("demo1")
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text("{}")
    monkeypatch.setenv(ds.DEMO_DEPLOY_ALLOW_ENV, "1")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: pytest.fail("must not deploy"))

    rc = ds.main(["deploy", "demo1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "index.html" in err
    assert "_middleware.js" in err


def test_deploy_refuses_a_bundle_without_the_upstream_license(_isolated_dirs, monkeypatch, capsys):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    _make_bundle("demo1", license=False)
    monkeypatch.setenv(ds.DEMO_DEPLOY_ALLOW_ENV, "1")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: pytest.fail("must not deploy"))

    rc = ds.main(["deploy", "demo1"])
    assert rc == 2
    assert "license" in capsys.readouterr().err.lower()


def test_bundle_safety_errors_is_empty_for_a_complete_bundle(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    _write_registry(registry_dir, slug="demo1")
    bundle = _make_bundle("demo1")
    assert ds.bundle_safety_errors(bundle) == []


def test_assemble_bundle_ships_gate_and_license_and_notice(_isolated_dirs, monkeypatch):
    """A no-build assembly still performs every obligation step."""
    registry_dir, *_ = _isolated_dirs
    corpus = _write_registry(registry_dir, slug="demo1")

    # A projection to bundle.
    arch = ds._arch_dir("demo1")
    arch.mkdir(parents=True)
    (arch / "manifest.json").write_text("{}")

    # An upstream checkout carrying a license and a notice.
    src = ds._src_dir("demo1")
    src.mkdir(parents=True)
    (src / "LICENSE.txt").write_text("MIT License\n")
    (src / "ThirdPartyNotices.txt").write_text("third party\n")

    # A prebuilt viewer dist, so no npm run.
    dist = tmp_dist = ds.VIEWER_DIR / "dist"
    created = not dist.exists()
    if created:
        dist.mkdir(parents=True)
    index = dist / "index.html"
    had_index = index.exists()
    if not had_index:
        index.write_text("<!doctype html>")
    try:
        bundle = ds.assemble_bundle(corpus, build=False)
        assert (bundle / "index.html").is_file()
        assert (bundle / "functions" / "_middleware.js").is_file()
        assert (bundle / "UPSTREAM-LICENSE.txt").read_text().startswith("MIT")
        assert (bundle / "ThirdPartyNotices.txt").is_file()
        assert ds.bundle_safety_errors(bundle) == []
    finally:
        if not had_index and index.exists():
            index.unlink()
        if created and tmp_dist.exists():
            tmp_dist.rmdir()


def test_assemble_bundle_refuses_when_the_upstream_license_is_missing(_isolated_dirs):
    registry_dir, *_ = _isolated_dirs
    corpus = _write_registry(registry_dir, slug="demo1")
    arch = ds._arch_dir("demo1")
    arch.mkdir(parents=True)
    (arch / "manifest.json").write_text("{}")
    ds._src_dir("demo1").mkdir(parents=True)  # no LICENSE in it

    dist = ds.VIEWER_DIR / "dist"
    created = not dist.exists()
    if created:
        dist.mkdir(parents=True)
    index = dist / "index.html"
    had_index = index.exists()
    if not had_index:
        index.write_text("<!doctype html>")
    try:
        with pytest.raises(RuntimeError, match="license"):
            ds.assemble_bundle(corpus, build=False)
    finally:
        if not had_index and index.exists():
            index.unlink()
        if created and dist.exists():
            dist.rmdir()


# ---------------------------------------------------------------------------
# detect-only share: the denominator is code lines, not all counted lines
# ---------------------------------------------------------------------------


def _manifest_with_languages(arch_dir: Path, languages: dict) -> None:
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / "manifest.json").write_text(json.dumps({"stats": {"languages": languages}}))


def test_detect_only_share_excludes_json_and_markdown_from_the_denominator(_isolated_dirs):
    """The VS Code shape: mostly TypeScript, ~18% JSON, a sliver of unparsed code.

    Counting JSON and Markdown as detect-only "languages" turns 0.1% into 21.9%
    and puts a healthy subject three points from failing the theater gate for
    having documentation.
    """
    arch = ds._arch_dir("demo1")
    _manifest_with_languages(arch, {
        "typescript": 3_773_731,   # full parse
        "json": 898_236,           # not code at all
        "markdown": 66_006,        # not code at all
        "css": 83_939,             # not code at all
        "shell": 3_622,            # code, detect-only
        "c": 30,                   # code, detect-only
        "dart": 19,                # code, detect-only
    })
    r = ds.gate_detect_only_share(arch, {"max_detect_only_line_share": 0.25})
    assert r.state == "PASS"
    # 3671 / 3777402 == 0.097%, not the 21.9% an all-lines denominator gives.
    assert "0.10%" in r.detail
    assert "3,671" in r.detail


def test_detect_only_share_still_fails_a_genuinely_unparseable_subject(_isolated_dirs):
    """The gate must keep its teeth: a real Kotlin/Java monorepo should trip it."""
    arch = ds._arch_dir("demo1")
    _manifest_with_languages(arch, {
        "kotlin": 800_000,      # code, detect-only
        "typescript": 100_000,  # code, full parse
        "json": 5_000_000,      # must not rescue the score by inflating the denominator
    })
    r = ds.gate_detect_only_share(arch, {"max_detect_only_line_share": 0.25})
    assert r.state == "FAIL"


def test_code_languages_and_full_parse_langs_come_from_the_analyzer(_isolated_dirs):
    """Both sets are read from analyzer/, never copied, so they cannot drift."""
    from analyzer.constants import CODE_LANGUAGES as canon_code
    from analyzer.parsers import PARSERS as canon_parsers
    assert ds.CODE_LANGUAGES == frozenset(canon_code)
    assert ds.FULL_PARSE_LANGS == frozenset(canon_parsers)
