"""P9-0 gate defects, wave B: symbol-reference edges, honest orphans, clone de-weighting.

Fail-before regression tests for the P9-0 gate defects D5, D4, and D8 plus the
two PR #53 review nits (comment-phantom string opener, quadratic string-span
rescan) and the PR #55 adversarial-review findings 1-5 (qualified-access and
coincidental-name false edges, comment-content phantom references,
language-blind '#' handling, tautological equivalence test, silent
weak-language suppression). Each test drives the REAL extract -> derive path on
a real fixture tree (no mocks of the unit under test); clone tests need the
tree-sitter token stream and skip loudly without it.

  D5   intra-module type usage becomes a component-to-component `uses` edge
  D4   the orphan finding is reframed `unreferenced` and collapses under D5
  D8   test-only clone clusters are de-weighted below mixed/product clusters
  nit-a a `#` comment holding a triple-quote no longer swallows real matches
  nit-b string spans are precomputed once and binary-searched (not rescanned)
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.extract.frameworks import (
    StringMask,
    compute_string_spans,
    in_string_literal,
)
from analyzer.extract.references import extract_reference_signals
from analyzer.extract.signals import extract_signals
from analyzer.parsers import PARSERS
from analyzer.store import FactStore

_TS = getattr(PARSERS.get("python"), "_ts_available", False)


# FROZEN pre-mask oracle (PR #55 review finding 4): a byte-for-byte copy of the
# ORIGINAL wave-A in_string_literal byte scan (commit bad7762), kept here so the
# equivalence test compares the new span implementation against the OLD shipped
# semantics, not against itself. Do not "fix" or refactor this copy.
def _legacy_in_string_literal(content: str, pos: int) -> bool:
    if pos <= 0:
        return False
    length = len(content)
    i = 0
    while i < pos:
        if content.startswith('"""', i) or content.startswith("'''", i):
            q = content[i:i + 3]
            end = content.find(q, i + 3)
            if end == -1:
                return True
            close = end + 3
            if pos < close:
                return True
            i = close
            continue
        ch = content[i]
        if ch in "\"'`":
            j = i + 1
            while j < length:
                c = content[j]
                if c == "\\":
                    j += 2
                    continue
                if c == ch:
                    j += 1
                    break
                if c == "\n" and ch != "`":
                    break
                j += 1
            if pos < j:
                return True
            i = j
            continue
        i += 1
    return False


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


def test_d5_qualified_access_draws_no_edge_python(tmp_path):
    # PR #55 review finding 1 reproduction: `requests.Session()` names Session
    # only through the `requests.` qualifier, and a local `session` component
    # happens to define its own Session class. Pre-fix a false web->session
    # `uses` edge was drawn (single definer, no import check); post-fix the
    # qualified member is excluded at extraction AND the single-definer path
    # requires import evidence, so no edge exists.
    _write(tmp_path, "web/client.py",
           "import requests\ndef fetch():\n    s = requests.Session()\n    return s\n")
    _write(tmp_path, "web/other.py", "def o():\n    return 1\n")
    _write(tmp_path, "session/store.py", "class Session:\n    pass\n")
    _write(tmp_path, "session/aux.py", "def a():\n    return 2\n")

    _, arch = _derive(tmp_path)
    uses = _rels(arch, "uses")
    assert uses == [], f"requests.Session() must not edge to a local component: {uses}"


def test_d5_swift_common_platform_name_draws_no_edge(tmp_path):
    # PR #55 review finding 1 reproduction (Swift half): `Foundation.Timer()`
    # and a bare `Timer()` in a UI file, with a `models` component defining its
    # own Timer class. Swift has no per-name imports to rescue this, so the
    # common-platform-name exclusion must drop it: no ui->models edge.
    _write(tmp_path, "ui/ClockView.swift",
           "import Foundation\nstruct ClockView {\n    func body() {\n"
           "        let t1 = Foundation.Timer()\n        let t2 = Timer()\n    }\n}\n")
    _write(tmp_path, "ui/ClockAux.swift", "struct ClockAux {\n    var v = 0\n}\n")
    _write(tmp_path, "models/Timer.swift", "class Timer {\n    var x = 1\n}\n")
    _write(tmp_path, "models/ModelsAux.swift", "struct ModelsAux {\n    var v = 0\n}\n")

    d, arch = _derive(tmp_path)
    uses = _rels(arch, "uses")
    assert uses == [], f"a platform-common name must not fabricate an edge: {uses}"
    assert getattr(d, "_uses_common_name_dropped", 0) >= 1


def test_d5_swift_common_name_counts_when_file_has_another_tie(tmp_path):
    # The common-name exclusion applies ONLY when the file shows no other
    # relationship with the resolved component: here the same file also uses the
    # target's distinctive AudioClock type, so its Timer reference to the same
    # component is corroborated and the edge carries both names.
    _write(tmp_path, "engine/Timer.swift", "class Timer {\n    var x = 1\n}\n")
    _write(tmp_path, "engine/AudioClock.swift", "class AudioClock {\n    var y = 2\n}\n")
    _write(tmp_path, "ui/View.swift",
           "struct View1 {\n    func body() {\n"
           "        let c = AudioClock()\n        let t = Timer()\n    }\n}\n")
    _write(tmp_path, "ui/Aux.swift", "struct UIAux {\n    var v = 0\n}\n")

    _, arch = _derive(tmp_path)
    edge = [r for r in _rels(arch, "uses")
            if r["source"] == "ui" and r["target"] == "engine"]
    assert len(edge) == 1, f"corroborated common name must count: {_rels(arch, 'uses')}"
    assert "AudioClock" in edge[0]["label"] and "Timer" in edge[0]["label"]


def test_d5_single_definer_without_import_draws_no_edge_python(tmp_path):
    # Finding 1b: a bare `Session()` call in a Python file (no qualifier, no
    # import of the defining component). Python HAS per-name imports, so the
    # absence of any import tying the file to the definer means no edge, even
    # though exactly one component defines Session.
    _write(tmp_path, "web/client.py", "def fetch():\n    s = Session()\n    return s\n")
    _write(tmp_path, "web/other.py", "def o():\n    return 1\n")
    _write(tmp_path, "session/store.py", "class Session:\n    pass\n")
    _write(tmp_path, "session/aux.py", "def a():\n    return 2\n")

    d, arch = _derive(tmp_path)
    assert _rels(arch, "uses") == []
    assert getattr(d, "_uses_unimported_dropped", 0) >= 1


def test_d5_commented_out_code_is_not_a_reference(tmp_path):
    # PR #55 review finding 2 locking test: `# x = Config()` is commented-out
    # code, not usage. The comment content is masked, so no reference signal and
    # no edge.
    src = "def f():\n    # x = Config()\n    return 1\n"
    refs = extract_reference_signals(src, "python", StringMask(src, "python"))
    assert refs == [], f"commented-out code must not be a reference: {refs}"

    _write(tmp_path, "cfg/config.py", "class Config:\n    pass\n")
    _write(tmp_path, "cfg/aux.py", "def a():\n    return 1\n")
    _write(tmp_path, "user/main.py", "def f():\n    # x = Config()\n    return 1\n")
    _write(tmp_path, "user/aux.py", "def b():\n    return 2\n")
    _, arch = _derive(tmp_path)
    assert _rels(arch, "uses") == []


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


def test_d4_weak_language_component_is_deranked_with_caveat(tmp_path):
    # PR #55 review finding 5: a substantial Ruby component (no reference
    # extractor for Ruby yet) with no incoming edge is NOT silently dropped (the
    # blind spot must stay visible) but is heavily de-ranked and its summary
    # carries an explicit weak-extractor caveat.
    _write(tmp_path, "legacy/service.rb",
           "class LegacyService\n"
           "  def a; 1; end\n  def b; 2; end\n  def c; 3; end\n"
           "  def d; 4; end\n  def e; 5; end\n  def f; 6; end\n"
           "end\n")
    _write(tmp_path, "legacy/helper.rb",
           "module LegacyHelper\n  def self.h; 0; end\nend\n")
    # An unreferenced Python component too, so the weak one has a mature peer to
    # rank against.
    _write(tmp_path, "island/main.py", "class Island:\n    def run(self):\n        return 1\n")
    _write(tmp_path, "island/x.py", "def x():\n    return 1\n")

    _, arch = _derive(tmp_path)
    by_id = {f["members"][0]["id"]: f for f in arch["findings"]
             if f["kind"] == "unreferenced"}
    assert "legacy" in by_id, (
        "a weak-language component must stay visible (finding 5), got "
        f"{sorted(by_id)}"
    )
    weak = by_id["legacy"]
    assert weak["detail"]["reference_extractor"] == "weak"
    assert weak["detail"]["weak_extractor_derank"] is True
    assert "blind spot" in weak["summary"] and "ruby" in weak["summary"]
    assert "island" in by_id, "the mature-language peer should also surface"
    mature = by_id["island"]
    assert mature["detail"]["weak_extractor_derank"] is False
    assert weak["rank_score"] < mature["rank_score"], (
        "the weak-extractor finding must rank below the mature one"
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


def test_nit_a_triple_quote_after_hash_opens_no_string_phantom():
    # Python: the '#' comment is masked as ONE span to end-of-line, so the
    # triple quote inside it opens no string and line 2 is code.
    content = 'x = 1  # example: """not a docstring\ny = 2\n'
    spans = compute_string_spans(content, "python")
    assert spans == [(7, 36)], spans  # exactly the comment (to the newline), nothing after
    mask = StringMask(content, "python")
    assert not mask.in_string(content.index("y = 2"))
    # A real (uncommented) triple quote still opens a span: [6, 17) covers the
    # opening quotes, "hello", and the closing quotes.
    real = 'doc = """hello"""\n'
    assert compute_string_spans(real, "python") == [(6, 17)]


def test_finding3_hash_handling_is_language_gated():
    # PR #55 review finding 3 reproductions: '#' is CODE in Swift and TS/JS, so
    # the comment rule must not apply there (it would un-mask real strings
    # relative to the pre-guard scanner).
    swift_raw = 'let r = #"http://localhost"#\n'
    # The raw-string content must still be masked for swift (no '#' comment).
    mask = StringMask(swift_raw, "swift")
    assert mask.in_string(swift_raw.index("http")), "swift raw string must stay masked"

    ts = 'class Foo { #count = 0; url = "http://api"; }\n'
    mask = StringMask(ts, "typescript")
    assert mask.in_string(ts.index("http")), "ts string after #field must stay masked"
    assert not mask.in_string(ts.index("count")), "#count is code, not a comment"

    # And in a hash-comment language the same '#' IS a comment.
    py = '# count = 0\nurl = "http://api"\n'
    mask = StringMask(py, "python")
    assert mask.in_string(py.index("count")), "python '#' comment must be masked"
    assert mask.in_string(py.index("http")), "the string literal is masked too"


# ---------------------------------------------------------------------------
# nit-b: precomputed spans + binary search match the OLD byte-scan semantics
# (frozen oracle, PR #55 review finding 4) and are faster than rescanning from
# offset 0 per match on a match-heavy file.
# ---------------------------------------------------------------------------

def _match_heavy_content(n: int) -> str:
    # Alternating string literals and code anchors, so there are many match
    # positions and many string spans on one file. No comments: byte-identical
    # to the legacy scan by construction.
    lines = []
    for i in range(n):
        lines.append(f's{i} = "value number {i} here"')
        lines.append(f"call_{i}(requests.get(url_{i}))")
    return "\n".join(lines) + "\n"


def test_nit_b_mask_matches_frozen_legacy_oracle():
    # The oracle is the FROZEN wave-A byte scan pinned at the top of this file,
    # not the current implementation (finding 4: the old test compared the new
    # code to itself). Cases:
    # 1. The reviewer's divergence cases, which must now AGREE because '#'
    #    handling is language-gated (finding 3).
    swift_raw = 'let r = #"http://localhost"#\nlet x = 1\n'
    ts = 'class Foo { #count = 0; url = "http://api"; }\nconst y = 2\n'
    for content, lang in ((swift_raw, "swift"), (ts, "typescript"), (ts, "javascript")):
        mask = StringMask(content, lang)
        for pos in range(len(content)):
            assert mask.in_string(pos) == _legacy_in_string_literal(content, pos), (
                f"divergence from legacy oracle at {pos} in {lang}: {content[pos-5:pos+5]!r}"
            )
    # 2. Comment-free python: byte-identical to the oracle at every offset.
    content = _match_heavy_content(50)
    mask = StringMask(content, "python")
    spans = compute_string_spans(content, "python")
    from analyzer.extract.frameworks import pos_in_spans
    for pos in range(0, len(content), 3):
        expected = _legacy_in_string_literal(content, pos)
        assert mask.in_string(pos) == expected
        assert pos_in_spans(spans, pos) == expected
        assert in_string_literal(content, pos) == expected  # default: no language
    # 3. The default-language wrapper is oracle-identical even ON the reviewer's
    #    divergence content (no language means no comment handling at all).
    for content in (swift_raw, ts, 'x = 1  # d """\ny = 2\n'):
        for pos in range(len(content)):
            assert in_string_literal(content, pos) == _legacy_in_string_literal(content, pos)


def test_nit_b_real_python_file_matches_oracle_outside_comments():
    # A REAL repo file (comment- and string-heavy). The one intentional
    # difference from the legacy scan is finding 2: python '#' comments are now
    # masked. So: strip comments (replace their bytes with spaces) and the
    # oracle over the sanitized text must agree with the new mask over the RAW
    # text at every position outside a comment; inside comments the new mask is
    # asserted True explicitly (the intentional new behavior).
    analyzer_dir = Path(__file__).resolve().parent.parent / "analyzer"
    for rel in ("extract/facts.py", "derive/testing.py"):
        content = (analyzer_dir / rel).read_text(encoding="utf-8")
        spans = compute_string_spans(content, "python")
        comment_spans = [(s, e) for s, e in spans if content[s] == "#"]
        assert comment_spans, f"{rel} should be a comment-bearing real file"

        sanitized = list(content)
        for s, e in comment_spans:
            for i in range(s, e):
                if sanitized[i] != "\n":
                    sanitized[i] = " "
        sanitized = "".join(sanitized)

        mask = StringMask(content, "python")

        def in_comment(pos: int, _spans=comment_spans) -> bool:
            return any(s < pos < e for s, e in _spans)

        for pos in range(0, len(content), 3):
            if in_comment(pos):
                assert mask.in_string(pos), (
                    f"{rel}: comment content must be masked at {pos}"
                )
            else:
                assert mask.in_string(pos) == _legacy_in_string_literal(sanitized, pos), (
                    f"{rel}: string-scan divergence from legacy oracle at {pos}: "
                    f"{content[max(0, pos - 10):pos + 10]!r}"
                )


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

def test_d5_swift_static_member_access_draws_a_uses_edge(tmp_path):
    # The dominant singleton shape in iOS code: AudioHub.shared.play(). The
    # ctor/annotation patterns miss it, which is why the real core engines
    # still read unreferenced after the first wave (dogfood finding on the
    # iOS demo). Static member access on a distinctive name now counts; the
    # qualified-access exclusion still kills names PRECEDED by a dot, so
    # Foundation.Timer stays dead.
    _write(tmp_path, "AudioHub/AudioHub.swift",
           "import Foundation\nclass AudioHub {\n    static let shared = AudioHub()\n"
           "    func play() { print(1) }\n}\n")
    _write(tmp_path, "AudioHub/Mixer.swift",
           "import Foundation\nstruct Mixer { var gain = 1 }\n")
    _write(tmp_path, "UI/PlayerView.swift",
           "import SwiftUI\nstruct PlayerView {\n    func body() {\n"
           "        AudioHub.shared.play()\n"
           "        let t = Foundation.Timer.scheduledTimer\n        print(t)\n    }\n}\n")
    _write(tmp_path, "UI/PlayerModel.swift",
           "import Foundation\nclass PlayerModel { var x = 1 }\n")

    _, arch = _derive(tmp_path)
    uses = _rels(arch, "uses")
    edge = [r for r in uses if r["source"] == "ui" and r["target"] == "audiohub"]
    assert len(edge) == 1, f"expected one ui->audiohub uses edge, got: {uses}"
    snippets = {e["snippet"] for e in edge[0]["evidence"]}
    assert "AudioHub" in snippets
    assert "Timer" not in snippets, "Foundation.Timer must stay excluded (dot-qualified)"


def test_d5_swift_common_name_static_access_still_needs_corroboration(tmp_path):
    # Session.shared where Session is on the common platform-name list must
    # not edge without another tie to the resolved component.
    _write(tmp_path, "Core/Session.swift",
           "import Foundation\nclass Session {\n    static let shared = Session()\n}\n")
    _write(tmp_path, "Core/Support.swift",
           "import Foundation\nstruct Support { var x = 1 }\n")
    _write(tmp_path, "Net/Client.swift",
           "import Foundation\nclass Client {\n    func go() { _ = Session.shared }\n}\n")
    _write(tmp_path, "Net/Helper.swift",
           "import Foundation\nstruct Helper { var y = 2 }\n")

    _, arch = _derive(tmp_path)
    uses = _rels(arch, "uses")
    assert not [r for r in uses if r["source"] == "net" and r["target"] == "core"], (
        f"a common platform name without corroboration must not edge: {uses}"
    )
