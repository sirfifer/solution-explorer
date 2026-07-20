"""P9-0 gate defects, wave B: symbol-reference edges, honest orphans, clone de-weighting.

Fail-before regression tests for the P9-0 gate defects D5, D4, and D8 plus the
two PR #53 review nits (comment-phantom string opener, quadratic string-span
rescan). Each test drives the REAL extract -> derive path on a real fixture tree
(no mocks of the unit under test); clone tests need the tree-sitter token stream
and skip loudly without it.

  D5   intra-module type usage becomes a component-to-component `uses` edge
  D4   the orphan finding is reframed `unreferenced` and collapses under D5
  D8   test-only clone clusters are de-weighted below mixed/product clusters
  nit-a a `#` comment holding a triple-quote no longer swallows real matches
  nit-b string spans are precomputed once and binary-searched (not rescanned)
"""

from __future__ import annotations

import time

import pytest

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.extract.frameworks import (
    StringMask,
    compute_string_spans,
    in_string_literal,
)
from analyzer.extract.signals import extract_signals
from analyzer.parsers import PARSERS
from analyzer.store import FactStore

_TS = getattr(PARSERS.get("python"), "_ts_available", False)


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _derive(root):
    store = FactStore(":memory:")
    extract_repo(str(root), store)
    return derive_all(store, root.name, root_path=str(root))


def _rels(arch, type_):
    return [r for r in arch["relationships"] if r["type"] == type_]


def _finding_ids(arch, kind):
    return {f["members"][0]["id"] for f in arch["findings"] if f["kind"] == kind}


# ---------------------------------------------------------------------------
# D5: intra-module type usage becomes a `uses` edge with evidence
# ---------------------------------------------------------------------------

def test_d5_swift_type_usage_draws_a_uses_edge(tmp_path):
    # An audio engine component defines AudioRecorder/AudioBuffer; a UI component
    # references them by type. Pre-fix there was no code-level edge between them
    # (only UI navigation was extracted); post-fix a `uses` edge carries the
    # reference sites as evidence.
    _write(tmp_path, "AudioEngine/AudioRecorder.swift",
           "import Foundation\nclass AudioRecorder {\n    func start() { print(1) }\n}\n")
    _write(tmp_path, "AudioEngine/AudioBuffer.swift",
           "import Foundation\nstruct AudioBuffer {\n    var size = 0\n}\n")
    _write(tmp_path, "UI/RecordView.swift",
           "import SwiftUI\nstruct RecordView {\n    func body() {\n"
           "        let r = AudioRecorder()\n        let b: AudioBuffer = AudioBuffer()\n"
           "        r.start()\n    }\n}\n")
    _write(tmp_path, "UI/RecordViewModel.swift",
           "import Foundation\nclass RecordViewModel {\n    var x = 1\n}\n")

    _, arch = _derive(tmp_path)
    uses = _rels(arch, "uses")
    edge = [r for r in uses if r["source"] == "ui" and r["target"] == "audioengine"]
    assert len(edge) == 1, f"expected one ui->audioengine uses edge, got: {uses}"
    ev_snippets = {e["snippet"] for e in edge[0]["evidence"]}
    assert {"AudioRecorder", "AudioBuffer"} <= ev_snippets
    assert all(e["file"] and e["line"] for e in edge[0]["evidence"])
    assert edge[0]["confidence"] == "inferred"


def test_d5_python_cross_module_class_usage_draws_a_uses_edge(tmp_path):
    _write(tmp_path, "core/engine.py",
           "class PricingEngine:\n    def price(self, x):\n        return x * 2\n")
    _write(tmp_path, "core/util.py", "def helper():\n    return 1\n")
    _write(tmp_path, "api/handler.py",
           "from core.engine import PricingEngine\n"
           "def handle(x):\n    e = PricingEngine()\n    return e.price(x)\n")
    _write(tmp_path, "api/routes.py", "def routes():\n    return []\n")

    _, arch = _derive(tmp_path)
    uses = _rels(arch, "uses")
    assert any(r["source"] == "api" and r["target"] == "core" for r in uses), uses


def test_d5_reference_inside_a_string_is_not_a_use(tmp_path):
    # A type NAME appearing only inside a string literal or comment is not a
    # reference, so it never resolves to a uses edge.
    _write(tmp_path, "engine/widget.py",
           "class Widget:\n    def go(self):\n        return 2\n")
    _write(tmp_path, "engine/more.py", "def m():\n    return 1\n")
    _write(tmp_path, "client/log.py",
           'def log():\n    msg = "Widget failed to start"  # Widget note\n    return msg\n')
    _write(tmp_path, "client/other.py", "def o():\n    return 0\n")

    _, arch = _derive(tmp_path)
    uses = [r for r in _rels(arch, "uses")
            if r["source"] == "client" and r["target"] == "engine"]
    assert uses == [], f"a string/comment mention must not be a use, got: {uses}"


def test_d5_ambiguous_name_is_dropped_not_guessed(tmp_path):
    # Two components each define a `Config` type; a third references `Config`
    # with no disambiguating import. The reference is dropped, never guessed onto
    # an arbitrary target, and the drop is counted.
    _write(tmp_path, "alpha/config.py", "class Config:\n    a = 1\n")
    _write(tmp_path, "alpha/x.py", "def ax():\n    return 1\n")
    _write(tmp_path, "beta/config.py", "class Config:\n    b = 2\n")
    _write(tmp_path, "beta/y.py", "def by():\n    return 2\n")
    _write(tmp_path, "user/use.py", "def u():\n    c = Config()\n    return c\n")
    _write(tmp_path, "user/z.py", "def uz():\n    return 3\n")

    d, arch = _derive(tmp_path)
    uses = [r for r in _rels(arch, "uses") if r["source"] == "user"]
    assert uses == [], f"an ambiguous name must not be guessed into an edge: {uses}"
    assert getattr(d, "_uses_ambiguous_dropped", 0) >= 1


# ---------------------------------------------------------------------------
# D4: orphan reframed `unreferenced`, collapses under D5, honest about maturity
# ---------------------------------------------------------------------------

def test_d4_ios_shaped_orphan_collapse(tmp_path):
    # Three "engine" components each define a type; a UI component references all
    # three. Pre-fix each engine was an orphan finding (dead-code claim); post-fix
    # every engine has an incoming `uses` edge and NONE is a finding.
    for name, typ in (("Audio", "AudioService"), ("Curriculum", "CurriculumStore"),
                      ("Config", "ConfigProvider")):
        low = name.lower()
        _write(tmp_path, f"{low}/{typ}.swift",
               f"import Foundation\nclass {typ} {{\n    func run() {{ print(1) }}\n}}\n")
        _write(tmp_path, f"{low}/{low}extra.swift",
               f"import Foundation\nstruct {name}Aux {{\n    var v = 0\n}}\n")
    _write(tmp_path, "ui/RootView.swift",
           "import SwiftUI\nstruct RootView {\n    func body() {\n"
           "        let a = AudioService()\n        let c = CurriculumStore()\n"
           "        let g = ConfigProvider()\n        a.run(); c.run(); g.run()\n    }\n}\n")
    _write(tmp_path, "ui/RootViewModel.swift",
           "import Foundation\nclass RootViewModel {\n    var x = 1\n}\n")

    _, arch = _derive(tmp_path)
    unreferenced = _finding_ids(arch, "unreferenced")
    for engine in ("audio", "curriculum", "config"):
        assert engine not in unreferenced, (
            f"{engine} must collapse (it has an incoming uses edge); "
            f"unreferenced={sorted(unreferenced)}"
        )
    # And the edges that caused the collapse really exist.
    targets = {r["target"] for r in _rels(arch, "uses") if r["source"] == "ui"}
    assert {"audio", "curriculum", "config"} <= targets, targets


def test_d4_unreferenced_finding_is_honestly_framed(tmp_path):
    # A genuinely-unreferenced Swift component (mature reference extractor) still
    # surfaces, but as `unreferenced` with honest copy and counter-evidence.
    _write(tmp_path, "island/Island.swift",
           "import Foundation\nclass Island {\n    func f() { print(1) }\n}\n")
    _write(tmp_path, "island/IslandAux.swift",
           "import Foundation\nstruct IslandAux {\n    var v = 0\n}\n")
    _write(tmp_path, "app/Main.swift",
           "import Foundation\nclass Main {\n    func go() { print(2) }\n}\n")
    _write(tmp_path, "app/MainAux.swift",
           "import Foundation\nstruct MainAux {\n    var v = 1\n}\n")

    _, arch = _derive(tmp_path)
    finding = next((f for f in arch["findings"]
                    if f["kind"] == "unreferenced"
                    and f["members"][0]["id"] == "island"), None)
    assert finding is not None, "island should surface as unreferenced"
    assert "detected" in finding["summary"] and "orphan" not in finding["summary"].lower()
    assert finding["detail"]["reference_extractor"] == "mature"
    assert finding["detail"]["symbols"] >= 1
    assert "churn_commits" in finding["detail"]
    assert "blind spot" in finding["detail"]["note"]


def test_d4_weak_language_component_is_suppressed(tmp_path):
    # A substantial Ruby component (no reference extractor for Ruby yet) with no
    # incoming edge is SUPPRESSED rather than falsely reported as dead code.
    # Pre-fix (as a plain orphan) it surfaced; post-fix it does not.
    _write(tmp_path, "legacy/service.rb",
           "class LegacyService\n"
           "  def a; 1; end\n  def b; 2; end\n  def c; 3; end\n"
           "  def d; 4; end\n  def e; 5; end\n  def f; 6; end\n"
           "end\n")
    _write(tmp_path, "legacy/helper.rb",
           "module LegacyHelper\n  def self.h; 0; end\nend\n")
    # A referenced Python component so the repo is not all-orphan.
    _write(tmp_path, "app/main.py", "class App:\n    def run(self):\n        return 1\n")
    _write(tmp_path, "app/x.py", "def x():\n    return 1\n")

    _, arch = _derive(tmp_path)
    unreferenced = _finding_ids(arch, "unreferenced")
    assert "legacy" not in unreferenced, (
        "a substantial weak-language component must be suppressed, not called "
        f"dead code; unreferenced={sorted(unreferenced)}"
    )


# ---------------------------------------------------------------------------
# D8: test-only clone clusters are de-weighted below mixed/product clusters
# ---------------------------------------------------------------------------

_CLONE_BODY_A = '''\
def process_alpha(items, config):
    total = 0
    result = []
    for item in items:
        value = item.get("amount", 0)
        if value > config.limit:
            total += value
            result.append(item.id)
        else:
            total -= value
    return total, result
'''

_CLONE_BODY_B = '''\
def compute_total(rows, rate):
    running = 0
    seen = set()
    for row in rows:
        key = row.get("key")
        if key not in seen:
            seen.add(key)
            running += row.get("weight", 1) * rate
    return running
'''

_FILLER_A = "def touch_a(x):\n    return x + 1\n"
_FILLER_B = "def touch_b(y):\n    return y - 1\n"


@pytest.mark.skipif(not _TS, reason="clone fingerprinting needs the tree-sitter token stream")
def test_d8_test_only_clone_is_deweighted_below_mixed(tmp_path):
    # A MIXED clone: the same body in a product file and a test file (kept full
    # weight). A TEST-ONLY clone: the same (different) body duplicated across two
    # test files (de-weighted). The test-only duplication must rank strictly
    # below the mixed one and carry the test_only marker.
    _write(tmp_path, "prod_a/svc.py", _CLONE_BODY_A)
    _write(tmp_path, "prod_a/extra.py", _FILLER_A)
    _write(tmp_path, "tests/mixed_test.py", _CLONE_BODY_A)   # mixed: product + test
    _write(tmp_path, "tests/helper_one_test.py", _CLONE_BODY_B)
    _write(tmp_path, "tests/helper_two_test.py", _CLONE_BODY_B)  # test-only pair

    _, arch = _derive(tmp_path)
    dups = [f for f in arch["findings"] if f["kind"] == "duplication"]
    mixed = [f for f in dups if not f["detail"]["test_only"]]
    test_only = [f for f in dups if f["detail"]["test_only"]]
    assert mixed, f"a mixed clone should keep full weight; findings: {dups}"
    assert test_only, f"a test-only clone should be marked; findings: {dups}"
    assert "test code only" in test_only[0]["summary"]
    assert max(f["rank_score"] for f in test_only) < min(f["rank_score"] for f in mixed), (
        "test-only clone must rank below the mixed clone"
    )


# ---------------------------------------------------------------------------
# Determinism (invariant I4): uses edges are byte-stable across runs
# ---------------------------------------------------------------------------

def test_d5_uses_edges_are_deterministic(tmp_path):
    _write(tmp_path, "core/engine.py",
           "class PricingEngine:\n    def price(self, x):\n        return x\n")
    _write(tmp_path, "core/util.py", "def helper():\n    return 1\n")
    _write(tmp_path, "api/h.py",
           "from core.engine import PricingEngine\n"
           "def handle(x):\n    return PricingEngine()\n")
    _write(tmp_path, "api/r.py", "def routes():\n    return []\n")

    def uses_signature():
        _, arch = _derive(tmp_path)
        return [
            (r["source"], r["target"], r["label"],
             tuple((e["file"], e["line"], e["snippet"]) for e in r["evidence"]))
            for r in _rels(arch, "uses")
        ]

    assert uses_signature() == uses_signature()


# ---------------------------------------------------------------------------
# nit-a: a '#' comment holding a triple-quote does not swallow real matches
# ---------------------------------------------------------------------------

def test_nit_a_comment_phantom_does_not_suppress_real_usage():
    # The PR #53 reproduction: an unquoted '#' comment on a line contains a lone
    # triple-quote. Pre-fix that opened a never-closed phantom string that made
    # everything after it read as "inside a string", suppressing the real
    # @shared_task below. Post-fix the '#' comment is a comment, so the real job
    # is detected.
    src = (
        "from celery import shared_task\n"
        '# doc note: a task decorator looks like """@app.task"""\n'
        "@shared_task\n"
        "def process_payment():\n"
        "    return True\n"
    )
    py = PARSERS.get("python")
    sigs = extract_signals(src, "python", py)
    jobs = [s for s in sigs if s.kind == "job"]
    assert jobs, "the real @shared_task after a '#'-comment triple-quote must be detected"
    assert jobs[0].value.get("framework") == "celery"


def test_nit_a_triple_quote_after_hash_opens_no_span():
    content = 'x = 1  # example: """not a docstring\ny = 2\n'
    assert compute_string_spans(content) == []
    # A real (uncommented) triple quote still opens a span: [6, 17) covers the
    # opening quotes, "hello", and the closing quotes.
    real = 'doc = """hello"""\n'
    assert compute_string_spans(real) == [(6, 17)]


# ---------------------------------------------------------------------------
# nit-b: precomputed spans + binary search match the old semantics and are
# faster than rescanning from offset 0 per match on a match-heavy file.
# ---------------------------------------------------------------------------

def _match_heavy_content(n: int) -> str:
    # Alternating string literals and code anchors, so there are many match
    # positions and many string spans on one file.
    lines = []
    for i in range(n):
        lines.append(f's{i} = "value number {i} here"')
        lines.append(f"call_{i}(requests.get(url_{i}))")
    return "\n".join(lines) + "\n"


def test_nit_b_mask_matches_old_semantics():
    content = _match_heavy_content(50)
    mask = StringMask(content)
    spans = compute_string_spans(content)
    # Check every character offset: the mask, the span helper, and the
    # single-shot wrapper must all agree.
    for pos in range(0, len(content), 3):
        expected = in_string_literal(content, pos)
        assert mask.in_string(pos) == expected
        from analyzer.extract.frameworks import pos_in_spans
        assert pos_in_spans(spans, pos) == expected


def test_nit_b_shared_mask_is_faster_than_per_match_rescan():
    content = _match_heavy_content(400)
    positions = list(range(0, len(content), 7))

    t0 = time.perf_counter()
    for pos in positions:
        in_string_literal(content, pos)  # rescans from 0 each call (old shape)
    old = time.perf_counter() - t0

    t0 = time.perf_counter()
    mask = StringMask(content)  # one scan
    for pos in positions:
        mask.in_string(pos)      # binary search
    new = time.perf_counter() - t0

    assert new < old, f"shared mask ({new:.4f}s) should beat per-match rescan ({old:.4f}s)"
