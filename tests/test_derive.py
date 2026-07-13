"""Tests for the Tier 3 derivation passes (P4-3).

All tests run the real pipeline (extract_repo into a FactStore, then
derive_all) against the committed parity fixtures or constructed temp repos.
The parity comparison encodes the ENUMERATED intended differences from the
P4-3 card Evidence; anything outside those classes fails the test, which is
exactly the "anything unexplained is a defect" rule.
"""

from __future__ import annotations

import copy
import json
import os

import pytest

from analyzer.derive import derive_all, derive_multi_from_config, source_read_audit
from analyzer.extract import extract_repo
from analyzer.parsers import PARSERS
from analyzer.store import FactStore, parse_symbol_id
from tests.test_engine_parity import normalize

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
MULTI_CONFIG = os.path.join(FIXTURES, "multi", "solution.json")

_PARITY_LANGS = ("python", "swift", "rust", "typescript", "javascript", "go", "ruby")
_TS = all(getattr(PARSERS.get(x), "_ts_available", False) for x in _PARITY_LANGS)
requires_ts = pytest.mark.skipif(
    not _TS, reason="parity snapshots are pinned to the tree-sitter tier")


def _extract_and_derive(root, name, **kw):
    store = FactStore(":memory:")
    extract_repo(root, store, **{k: v for k, v in kw.items() if k == "repo"})
    d, arch = derive_all(store, name, repo=kw.get("repo", "."))
    return store, d, arch


# ---------------------------------------------------------------------------
# Zero source reads (card item 4; TARGET 4.3 instrumentation assertion)
# ---------------------------------------------------------------------------

def test_derivation_reads_zero_source_files():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    with source_read_audit() as audit:
        derive_all(store, "polyglot")
    assert audit.count == 0, f"derivation read source files: {audit.paths[:10]}"


def test_the_audit_itself_detects_reads(tmp_path):
    # Guard self-test: a hook that cannot fire proves nothing. A real read
    # inside the audited block must be counted (and must raise under strict).
    p = tmp_path / "x.txt"
    p.write_text("hello")
    with source_read_audit() as audit:
        p.read_text()
    # read_text may route through Path.open internally, so one user-level
    # read can register more than once; what matters is that it registers.
    assert audit.count >= 1
    assert any(str(p) in q for q in audit.paths)
    with source_read_audit(strict=True) as audit:
        with pytest.raises(AssertionError):
            p.read_text()


# ---------------------------------------------------------------------------
# Evidence and confidence on every edge (card acceptance; invariant I3)
# ---------------------------------------------------------------------------

def test_every_edge_has_evidence_and_confidence():
    store, d, arch = _extract_and_derive(POLYGLOT, "polyglot")
    rels = arch["relationships"]
    assert rels, "fixture must produce at least one relationship"
    for r in rels:
        assert r.get("confidence") in ("certain", "inferred"), r
        assert r.get("evidence"), f"edge without evidence: {r}"
        for ev in r["evidence"]:
            assert ev.get("file"), f"evidence row without a file: {r}"
    # The same edges in the store carry the same contract.
    edges = store.edges()
    assert len(edges) == len(rels)
    for e in edges:
        assert e["confidence"] in ("certain", "inferred")
        assert e["evidence"], f"store edge without evidence: {e}"


def test_http_edge_evidence_points_at_the_real_call_site():
    _, _, arch = _extract_and_derive(POLYGLOT, "polyglot")
    http = [r for r in arch["relationships"] if r["type"] == "http"]
    assert len(http) == 1
    ev = http[0]["evidence"][0]
    assert ev["file"] == "services/web/src/client.ts"
    assert ev["line"] == 8  # const API_BASE = "http://api:8000";
    assert "8000" in ev["snippet"]


# ---------------------------------------------------------------------------
# Parity with the P4-1 snapshot, enumerated differences only (card item 6)
# ---------------------------------------------------------------------------
#
# Enumerated difference classes (each masked below with its justification;
# the full narrative lives in the P4-3 card Evidence):
#   D1 symbol identity: frozen-grammar ids replace legacy file:name:line
#      (ids and parent fields are compared structurally, not byte-wise).
#   D2 nested symbols: methods with parent references are NEW rows; old
#      symbols must all still be present by (file, name).
#   D3 edge metadata: evidence/confidence/origin are new optional keys.
#   D4 testing correction: the old engine classified fixture files as tests
#      because the fixture lives under the host repo's tests/ directory, and
#      found the host's CI config by walking above the scan root; the new
#      root-bounded pass emits {} on these fixtures (P2-2 item 3).
#   D5 metrics/stats symbol counts follow D2.

_JUSTIFIED_COMPONENT_KEYS = {"testing"}          # D4
_JUSTIFIED_REL_KEYS = {"evidence", "confidence", "origin"}  # D3


def _mask(arch: dict) -> dict:
    a = copy.deepcopy(arch)

    def mask_comp(c):
        for k in _JUSTIFIED_COMPONENT_KEYS:
            c.pop(k, None)
        c.get("metrics", {}).pop("symbols", None)  # D5
        for ch in c.get("children", []):
            mask_comp(ch)

    for c in a.get("components", []):
        mask_comp(c)
    for r in a.get("relationships", []):
        for k in _JUSTIFIED_REL_KEYS:
            r.pop(k, None)
    for f in a.get("files", []):
        f.pop("symbols", None)  # D1/D2: compared structurally below
    a.pop("symbols", None)      # D1/D2
    a.get("stats", {}).pop("total_symbols", None)           # D5
    a.get("stats", {}).pop("total_symbols_detected", None)  # D5
    return a


def _symbol_keys(arch: dict, legacy: bool) -> set:
    out = set()
    for s in arch["symbols"]:
        out.add((s["file"], s["name"]))
    return out


@requires_ts
def test_polyglot_diff_vs_snapshot_is_only_enumerated_differences():
    _, _, arch = _extract_and_derive(POLYGLOT, "polyglot")
    new = normalize(arch)
    with open(os.path.join(FIXTURES, "parity", "polyglot.snapshot.json")) as f:
        old = json.load(f)

    # Everything outside the enumerated classes must be byte-identical.
    assert json.dumps(_mask(old), sort_keys=True, default=str) == \
           json.dumps(_mask(new), sort_keys=True, default=str)

    # D1: every new id round-trips through the frozen grammar.
    for s in new["symbols"]:
        parsed = parse_symbol_id(s["id"])
        assert s["id"] == parsed.encode()

    # D2: old symbols all survive by (file, name); every new-only symbol is a
    # parent-linked nested symbol.
    old_keys = _symbol_keys(old, legacy=True)
    new_by_key = {}
    for s in new["symbols"]:
        new_by_key.setdefault((s["file"], s["name"]), []).append(s)
    missing = old_keys - set(new_by_key)
    assert not missing, f"symbols lost vs snapshot: {missing}"
    extras = set(new_by_key) - old_keys
    for key in extras:
        assert all(s["parent"] for s in new_by_key[key]), (
            f"unexplained non-nested extra symbol: {key}")

    # D4: the corrected testing block is {} on these fixtures (no in-root CI
    # or test files), where the snapshot froze the host-repo false positive.
    def walk(cs):
        for c in cs:
            yield c
            yield from walk(c.get("children", []))
    for c in walk(new["components"]):
        assert c["testing"] == {}, f"unexpected testing content: {c['id']}"
    old_root = next(iter(old["components"]))
    assert old_root["testing"].get("has_ci_tests") is True  # the frozen false positive


@requires_ts
def test_multi_diff_vs_snapshot_is_only_enumerated_differences():
    arch = derive_multi_from_config(MULTI_CONFIG)
    new = normalize(arch)
    with open(os.path.join(FIXTURES, "parity", "multi.snapshot.json")) as f:
        old = json.load(f)

    assert json.dumps(_mask(old), sort_keys=True, default=str) == \
           json.dumps(_mask(new), sort_keys=True, default=str)

    # D1 multi-repo form: the repo segment carries the repo name instead of
    # the old string-prefix hack; display file paths keep the prefix.
    for s in new["symbols"]:
        parsed = parse_symbol_id(s["id"])
        assert parsed.repo in ("backend", "frontend")
        assert s["file"].startswith(parsed.repo + "/")

    old_keys = _symbol_keys(old, legacy=True)
    new_keys = _symbol_keys(new, legacy=False)
    assert old_keys <= new_keys


@requires_ts
def test_derivation_is_deterministic():
    _, _, a1 = _extract_and_derive(POLYGLOT, "polyglot")
    _, _, a2 = _extract_and_derive(POLYGLOT, "polyglot")
    assert json.dumps(normalize(a1), sort_keys=True, default=str) == \
           json.dumps(normalize(a2), sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Symbol re-keying to authoritative components (card item 5)
# ---------------------------------------------------------------------------

@requires_ts
def test_symbols_are_rekeyed_to_discovered_components():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)

    # Extraction's nearest-marker resolver keys client.ts symbols to the
    # marker directory services/web (package.json), because it cannot see
    # the intermediate module component services/web/src.
    def client_components():
        return {
            parse_symbol_id(s["id"]).component
            for s in store.symbols()
            if parse_symbol_id(s["id"]).file == "services/web/src/client.ts"
        }

    assert client_components() == {"services/web"}

    derive_all(store, "polyglot")

    # Discovery is authoritative: the owning component is the deeper module.
    assert client_components() == {"services/web/src"}

    # Parent references were remapped through the same table.
    rows = {r["id"]: r for r in store.symbols()}
    for r in rows.values():
        if r["parent_id"]:
            assert r["parent_id"] in rows, f"dangling parent after re-key: {r['id']}"

    # FTS rows follow the re-keyed ids (search returns current ids only).
    if store.with_fts:
        hits = store.search("getUser", ref_kind="symbol")
        assert hits, "expected an FTS hit for a re-keyed symbol"
        for h in hits:
            assert h["ref_id"] in rows, "FTS row still points at a stale symbol id"


# ---------------------------------------------------------------------------
# Root-bounded CI/test detection (P2-2 item 3 port; difference class D4)
# ---------------------------------------------------------------------------

def test_ci_detection_is_bounded_to_the_scan_root(tmp_path):
    # Host repo with CI lives ABOVE the scan root; the scanned project has
    # none. The old engine walked up and reported the host's CI as the
    # project's (the false positive frozen in the parity snapshot, where
    # has_ci_tests is True for a fixture with no CI config).
    host = tmp_path / "host"
    wf = host / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("jobs:\n  t:\n    steps:\n      - run: pytest\n")
    inner = host / "inner"
    inner.mkdir()
    (inner / "main.py").write_text("x = 1\n")

    store = FactStore(":memory:")
    extract_repo(inner, store)
    _, arch = derive_all(store, "inner")
    root = arch["components"][0]
    assert root["testing"] == {}, (
        "CI detection escaped the scan root and found the host repo's CI")

    # Positive control: the same config INSIDE the root is detected.
    store2 = FactStore(":memory:")
    extract_repo(host, store2)
    _, arch2 = derive_all(store2, "host")
    root2 = arch2["components"][0]
    assert root2["testing"].get("has_ci_tests") is True


def test_test_files_are_classified_within_root_only(tmp_path):
    # A project under a directory literally named "tests" (like our fixtures)
    # must not have every file counted as a test file.
    project = tmp_path / "tests" / "proj"
    project.mkdir(parents=True)
    (project / "app.py").write_text("def run():\n    return 1\n")
    (project / "test_app.py").write_text("def test_run():\n    assert True\n")

    store = FactStore(":memory:")
    extract_repo(project, store)
    _, arch = derive_all(store, "proj")
    testing = arch["components"][0]["testing"]
    # Only the genuinely test-named file counts, not app.py via the absolute
    # path's "tests" ancestor outside the root.
    assert testing["test_files"] == 1
    assert testing["unit_tests"] == 1


# ---------------------------------------------------------------------------
# SwiftUI flow from stored signals and content (card item 3)
# ---------------------------------------------------------------------------

SWIFT_APP = '''
import SwiftUI

@main
struct DemoApp: App {
    var body: some Scene {
        WindowGroup { MainView() }
    }
}

struct MainView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
    }
}
'''

SWIFT_HOME = '''
import SwiftUI

struct HomeView: View {
    @State private var showModal = false
    var body: some View {
        VStack {
            NavigationLink(destination: DetailView()) { Text("Go") }
            Button("Show") { showModal = true }
        }
        .sheet(isPresented: $showModal) { ComposeView() }
    }
}

struct DetailView: View { var body: some View { Text("detail") } }
struct ComposeView: View { var body: some View { Text("compose") } }
'''

SWIFT_SETTINGS = '''
import SwiftUI

struct SettingsView: View {
    var body: some View { Text("settings") }
}
'''

INFO_PLIST = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Demo</string>
</dict>
</plist>
'''


@pytest.fixture
def swift_app_repo(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "Info.plist").write_text(INFO_PLIST)
    (app / "DemoApp.swift").write_text(SWIFT_APP)
    (app / "HomeView.swift").write_text(SWIFT_HOME)
    (app / "SettingsView.swift").write_text(SWIFT_SETTINGS)
    return app


@requires_ts
def test_swiftui_flow_is_derived_from_the_store(swift_app_repo):
    store = FactStore(":memory:")
    extract_repo(swift_app_repo, store)
    with source_read_audit() as audit:
        d, arch = derive_all(store, "app")
    assert audit.count == 0, f"flow derivation read the disk: {audit.paths[:5]}"

    root = arch["components"][0]
    assert root["type"] == "ios-client"

    types = {r["type"] for r in arch["relationships"]}
    assert "tab" in types, "tab edges missing"
    assert "navigation" in types, "navigation edge missing"
    assert "modal" in types, "modal (sheet) edge missing"

    # Screens exist as children (tab container with tabs and nested screens).
    child_types = {c["type"] for c in root["children"]}
    assert "tab-container" in child_types

    # Flow edges carry evidence pointing at a real Swift file (card item 3).
    for r in arch["relationships"]:
        if r["type"] in ("tab", "navigation", "modal", "embed"):
            assert r["confidence"] == "inferred"
            assert r["evidence"], f"flow edge without evidence: {r}"
            assert r["evidence"][0]["file"].endswith(".swift")

    # The extraction tier recorded the raw ui_action signals (target_view)
    # that anchor these edges (P4-2 contract).
    targets = {
        (s["value"] or {}).get("target_view")
        for s in store.signals() if s["kind"] == "ui_action"
    }
    assert "DetailView" in targets
    assert "ComposeView" in targets


@requires_ts
def test_ui_actions_survive_via_store_content(swift_app_repo):
    store = FactStore(":memory:")
    extract_repo(swift_app_repo, store)
    _, arch = derive_all(store, "app")
    root = arch["components"][0]
    labels = {a["label"] for a in root["actions"]}
    assert "Show" in labels  # Button("Show") from HomeView.swift


# ---------------------------------------------------------------------------
# Derived rows land in the store (passes write only the store)
# ---------------------------------------------------------------------------

def test_components_and_edges_are_flushed_to_the_store():
    store, d, arch = _extract_and_derive(POLYGLOT, "polyglot")
    comps = store.components()
    assert {c["id"] for c in comps} >= {"root", "services/api", "services/web/src"}
    # component_files joins components to real file rows
    cf = store.component_files()
    assert any(c["component_id"] == "services/api" and c["path"].endswith("server.py")
               for c in cf)
    # a second derive run replaces, not duplicates
    derive_all(store, "polyglot")
    assert len(store.components()) == len(comps)
