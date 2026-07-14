"""P5-6 correlation extraction: clones, orphans, concerns, findings.

Behavioral tests over the REAL extract -> derive path (no mocking of the unit
under test): a temp repo is written to disk, extracted into a fact store, and
derived, then the emitted concerns and findings are asserted. The fixtures cover
the four proofs the P5-6 card requires: a copied-then-renamed clone across two
components, an exact clone, an orphan component, two divergent logger libraries,
and a noise repo that must produce no cluster.
"""

from __future__ import annotations

import json
import time

import pytest

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.extract.clones import MIN_FRAGMENT_TOKENS
from analyzer.parsers import PARSERS
from analyzer.store import FactStore

_TS = getattr(PARSERS.get("python"), "_ts_available", False)
pytestmark = pytest.mark.skipif(
    not _TS, reason="clone fingerprinting needs the tree-sitter token stream"
)

# A substantial function body: well over MIN_FRAGMENT_TOKENS normalized tokens.
_ORIGINAL = '''\
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

# Same structure, every identifier renamed: a type-2 (renamed) clone. Its
# normalized token sequence is identical to _ORIGINAL, so they share a norm_hash.
_RENAMED = '''\
def process_beta(records, settings):
    accum = 0
    output = []
    for record in records:
        amount = record.get("amount", 0)
        if amount > settings.limit:
            accum += amount
            output.append(record.id)
        else:
            accum -= amount
    return accum, output
'''

# A different, self-contained function, duplicated BYTE-FOR-BYTE into two files:
# a type-1 (exact) clone.
_EXACT = '''\
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

# A substantial but structurally distinct function, so it is a fragment (proves
# the component has code) but is NOT a clone of anything else in the fixture.
_UNIQUE = '''\
def summarize(entries):
    counts = {}
    while entries:
        head = entries.pop()
        name = head.category.upper()
        counts[name] = counts.get(name, 0) + head.weight
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return ranked[:5]
'''

# Filler so a directory forms a component (needs 2+ code files) without adding a
# clone: distinct bodies, each below the fragment threshold.
_FILLER_A = "def touch_a(x):\n    return x + 1\n"
_FILLER_B = "def touch_b(y):\n    return y - 1\n"

# A trivial-idiom file: many one-line getters, each far below the token
# threshold. Duplicated across two files, it must NOT produce a cluster.
_IDIOMS = "".join(
    f"def get_{n}(self):\n    return self._{n}\n\n" for n in
    ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")
)


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_repo(root):
    # alpha + beta: the renamed clone across two components.
    _write(root, "alpha/service.py", _ORIGINAL)
    _write(root, "alpha/extra.py", _FILLER_A)
    _write(root, "beta/service.py", _RENAMED)
    _write(root, "beta/extra.py", _FILLER_B)
    # The exact clone across two more components.
    _write(root, "calc_one/totals.py", _EXACT)
    _write(root, "calc_one/extra.py", _FILLER_A)
    _write(root, "calc_two/totals.py", _EXACT)
    _write(root, "calc_two/extra.py", _FILLER_B)
    # An orphan leaf component: real code, nobody references it, no capability,
    # and structurally unique so it does not join a clone cluster.
    _write(root, "orphanage/dead.py", _UNIQUE)
    _write(root, "orphanage/more.py", _FILLER_A)
    # Two components importing DIFFERENT logger libraries.
    _write(root, "logx/mod.py", "import structlog\n\n" + _FILLER_A)
    _write(root, "logx/other.py", _FILLER_B)
    _write(root, "logy/mod.py", "import loguru\n\n" + _FILLER_B)
    _write(root, "logy/other.py", _FILLER_A)


def _derive(root):
    (root / ".se").mkdir(exist_ok=True)
    store = FactStore(str(root / ".se" / "index.db"))
    extract_repo(root, store)
    d, arch = derive_all(store, root.name, root_path=str(root))
    store.close()
    return d, arch


def _findings_by_kind(arch, kind):
    return [f for f in arch["findings"] if f["kind"] == kind]


# ---------------------------------------------------------------------------
# Clone clusters
# ---------------------------------------------------------------------------

def test_renamed_clone_across_two_components_forms_one_cluster(tmp_path):
    _build_repo(tmp_path)
    _, arch = _derive(tmp_path)
    dup = _findings_by_kind(arch, "duplication")
    # Find the cluster that includes alpha/service.py and beta/service.py.
    hit = [
        f for f in dup
        if {"alpha/service.py", "beta/service.py"} <= {m["file"] for m in f["members"]}
    ]
    assert len(hit) == 1, "the renamed clone should form exactly one cluster"
    finding = hit[0]
    assert finding["detail"]["clone_class"] == "renamed"
    # Per-member file + line-range evidence (I3).
    files = {m["file"] for m in finding["members"]}
    assert files == {"alpha/service.py", "beta/service.py"}
    for m in finding["members"]:
        assert m["line_start"] and m["line_end"] and m["line_end"] >= m["line_start"]
    assert len(finding["detail"]["component_ids"]) == 2
    assert finding["confidence"] == "inferred"
    assert finding["verification_status"] == "unverified"
    assert isinstance(finding["rank_score"], (int, float))


def test_exact_clone_classifies_exact(tmp_path):
    _build_repo(tmp_path)
    _, arch = _derive(tmp_path)
    dup = _findings_by_kind(arch, "duplication")
    hit = [
        f for f in dup
        if {"calc_one/totals.py", "calc_two/totals.py"} <= {m["file"] for m in f["members"]}
    ]
    assert len(hit) == 1
    assert hit[0]["detail"]["clone_class"] == "exact"


def test_noise_idioms_produce_no_cluster(tmp_path):
    # A repo of only trivial one-line getters, duplicated across two files. Every
    # getter is far below MIN_FRAGMENT_TOKENS, so no fragment is emitted and no
    # cluster forms: the thresholds keep idioms out of the results.
    _write(tmp_path, "pkg/a.py", _IDIOMS)
    _write(tmp_path, "pkg/b.py", _IDIOMS)
    _, arch = _derive(tmp_path)
    assert _findings_by_kind(arch, "duplication") == []


def test_min_fragment_threshold_is_enforced(tmp_path):
    # Directly assert the extractor drops sub-threshold fragments: a file of only
    # tiny getters yields zero clone_fragment signals.
    _write(tmp_path, "pkg/a.py", _IDIOMS)
    _write(tmp_path, "pkg/b.py", _FILLER_A)
    (tmp_path / ".se").mkdir(exist_ok=True)
    store = FactStore(str(tmp_path / ".se" / "index.db"))
    extract_repo(tmp_path, store)
    frags = [s for s in store.signals() if s["kind"] == "clone_fragment"]
    store.close()
    assert frags == []
    assert MIN_FRAGMENT_TOKENS >= 40  # documents the recorded threshold


# ---------------------------------------------------------------------------
# Orphans
# ---------------------------------------------------------------------------

def test_orphan_component_surfaces_as_finding(tmp_path):
    _build_repo(tmp_path)
    _, arch = _derive(tmp_path)
    orphans = _findings_by_kind(arch, "orphan")
    ids = {f["members"][0]["id"] for f in orphans}
    assert "orphanage" in ids, f"orphanage should be an orphan; got {sorted(ids)}"
    orphan = next(f for f in orphans if f["members"][0]["id"] == "orphanage")
    assert orphan["confidence"] == "inferred"
    assert orphan["verification_status"] == "unverified"
    assert orphan["evidence"][0]["path"] is not None or orphan["evidence"][0]["files"]


# ---------------------------------------------------------------------------
# Concerns + inconsistency
# ---------------------------------------------------------------------------

def test_two_logger_libraries_join_logging_concern_and_flag_inconsistency(tmp_path):
    _build_repo(tmp_path)
    _, arch = _derive(tmp_path)
    logging = [c for c in arch["concerns"] if c["id"] == "concern:logging"]
    assert len(logging) == 1
    members = {m["component_id"] for m in logging[0]["members"]}
    assert {"logx", "logy"} <= members
    libs = set()
    for m in logging[0]["members"]:
        libs |= set(m["markers"])
    assert {"structlog", "loguru"} <= libs

    incon = _findings_by_kind(arch, "inconsistency")
    assert len(incon) >= 1
    log_incon = [f for f in incon if f["detail"]["concern_id"] == "concern:logging"]
    assert len(log_incon) == 1
    assert set(log_incon[0]["detail"]["libraries"]) >= {"structlog", "loguru"}
    assert log_incon[0]["verification_status"] == "unverified"
    assert log_incon[0]["confidence"] == "inferred"


def test_concern_slugs_are_mechanical(tmp_path):
    _build_repo(tmp_path)
    _, arch = _derive(tmp_path)
    for c in arch["concerns"]:
        assert c["id"].startswith("concern:")
        assert c["kind"] in {
            "logging", "auth", "persistence", "http-client", "caching",
            "configuration", "clone",
        }


# ---------------------------------------------------------------------------
# Findings surface invariants (I11, I15)
# ---------------------------------------------------------------------------

def test_findings_are_ranked_and_carry_the_verification_field(tmp_path):
    _build_repo(tmp_path)
    _, arch = _derive(tmp_path)
    findings = arch["findings"]
    assert findings, "the fixture should produce findings"
    scores = [f["rank_score"] for f in findings]
    assert scores == sorted(scores, reverse=True), "findings must be rank-ordered (I11)"
    for f in findings:
        assert f["verification_status"] == "unverified"  # P7-4 flips it (I15)
        assert f["confidence"] == "inferred"
        assert f["members"]
        assert "evidence" in f


def test_correlation_derivation_is_deterministic(tmp_path):
    _build_repo(tmp_path)
    _, arch1 = _derive(tmp_path)
    _, arch2 = _derive(tmp_path)
    assert json.dumps(arch1["concerns"], sort_keys=True) == json.dumps(arch2["concerns"], sort_keys=True)
    assert json.dumps(arch1["findings"], sort_keys=True) == json.dumps(arch2["findings"], sort_keys=True)


def test_findings_round_trip_through_the_store_rank_ordered(tmp_path):
    _build_repo(tmp_path)
    (tmp_path / ".se").mkdir(exist_ok=True)
    store = FactStore(str(tmp_path / ".se" / "index.db"))
    extract_repo(tmp_path, store)
    derive_all(store, tmp_path.name, root_path=str(tmp_path))
    stored = store.findings()
    concerns = store.concerns()
    store.close()
    assert stored
    ranks = [f["rank_score"] for f in stored]
    assert ranks == sorted(ranks, reverse=True)
    assert all(f["verification_status"] == "unverified" for f in stored)
    assert any(c["id"] == "concern:logging" for c in concerns)


# ---------------------------------------------------------------------------
# Projection backward compatibility
# ---------------------------------------------------------------------------

def test_projection_carries_optional_correlation_keys(tmp_path):
    from analyzer.project.pipeline import project_monolith

    _build_repo(tmp_path)
    (tmp_path / ".se").mkdir(exist_ok=True)
    store = FactStore(str(tmp_path / ".se" / "index.db"))
    extract_repo(tmp_path, store)
    _, arch = derive_all(store, tmp_path.name, root_path=str(tmp_path))
    out = tmp_path / "architecture.json"
    project_monolith(arch, out, store=store, root=tmp_path,
                     generated_at="X", analyzer_version="Y")
    store.close()

    doc = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(doc["concerns"], list) and doc["concerns"]
    assert isinstance(doc["findings"], list) and doc["findings"]

    # Per-component references are optional: a component that belongs to no
    # concern and no finding carries neither key (old viewers see nothing new).
    def walk(comps):
        for c in comps:
            if not c.get("concerns"):
                assert "concerns" not in c
            if not c.get("findings"):
                assert "findings" not in c
            walk(c.get("children", []))

    walk(doc["components"])


def test_perf_self_derive_completes_in_seconds(tmp_path):
    # A generated repo of 40 files with a mix of clones proves the clustering
    # cost is bounded (seconds, not minutes) at a realistic fragment count.
    for i in range(20):
        body = _ORIGINAL.replace("process_alpha", f"proc_{i}")
        _write(tmp_path, f"mod_{i}/a.py", body)
        _write(tmp_path, f"mod_{i}/b.py", _EXACT.replace("compute_total", f"total_{i % 3}"))
    t0 = time.time()
    _, arch = _derive(tmp_path)
    elapsed = time.time() - t0
    assert elapsed < 30.0, f"correlation derive took {elapsed:.1f}s"
    assert _findings_by_kind(arch, "duplication")
