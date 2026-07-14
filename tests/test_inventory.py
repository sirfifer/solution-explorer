"""Non-source inventory classifier and projection (P6-10; repo totality).

These tests encode the card's accept criteria:

  - a synthesized xcresult-heavy tree makes the build/test-output group carry
    the cleanup recommendation and dominate the ranking;
  - product assets read as expected-here, not a problem;
  - a .md under docs/ classifies as documentation while a .md under prompts/ or
    .claude/ classifies as agent content (context, not extension alone);
  - a .pem flags security_sensitive;
  - an unrecognized non-source file lands in a loud unknown group, never a
    silent "other";
  - the projection carries the inventory section, and an old dataset without any
    non-source rows degrades to exactly the pre-inventory coverage output.

The classifier is a pure function, so the context rules are asserted directly.
The fail-before proof for the context rules is explicit: classifying by
extension alone (the ``_ext_only`` stand-in below) puts docs and prompts in the
same bucket, which the context assertions reject.
"""

from __future__ import annotations

import os
from pathlib import Path

import json

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project.coverage import build_coverage
from analyzer.project.inventory import (
    INVENTORY_VERSION,
    build_inventory,
    classify_row,
)
from analyzer.project.pipeline import project_split
from analyzer.store import FactStore


# ---------------------------------------------------------------------------
# Classifier: context rules (path + extension together, never extension alone)
# ---------------------------------------------------------------------------

def test_markdown_context_decides_documentation_vs_agent_content():
    # The same .md extension classifies differently by its directory context.
    assert classify_row("docs/guide.md", "excluded:unsupported_extension", None) == "documentation"
    assert classify_row("prompts/system.md", "excluded:unsupported_extension", None) == "agent_content"
    assert classify_row(".claude/skills/x.md", "excluded:skipped_directory", ".claude") == "agent_content"
    assert classify_row("App/CLAUDE.md", "excluded:unsupported_extension", None) == "agent_content"
    assert classify_row("some/where/x.instructions.md", "excluded:unsupported_extension", None) == "agent_content"


def _ext_only(path: str) -> str:
    """A deliberately wrong classifier that looks at the extension only.

    This is the fail-before stand-in: extension alone cannot separate a docs
    .md from a prompts .md, so the context assertions above would fail if the
    real classifier behaved like this.
    """
    ext = os.path.splitext(path)[1].lower()
    return "documentation" if ext in {".md", ".txt"} else "unknown"


def test_fail_before_extension_only_cannot_separate_docs_from_prompts():
    # Proof that the context rules carry weight: extension alone collapses docs
    # and prompts into one bucket, which is exactly what classify_row must not do.
    assert _ext_only("docs/guide.md") == _ext_only("prompts/system.md")
    assert classify_row("docs/guide.md", "excluded:unsupported_extension", None) != classify_row(
        "prompts/system.md", "excluded:unsupported_extension", None
    )


def test_pem_flags_security_sensitive():
    assert classify_row("certs/server.pem", "excluded:unsupported_extension", ".pem") == "secrets"
    assert classify_row("keys/id_rsa", "excluded:unsupported_extension", "id_rsa") == "secrets"
    assert classify_row("app/.env.production", "excluded:unsupported_extension", None) == "secrets"


def test_unknown_is_loud_never_silent_other():
    # An unrecognized non-source extension lands in unknown, and unknown is a
    # real category with an explanation, not a silent "other".
    assert classify_row("weird/thing.qwerty", "excluded:unsupported_extension", ".qwerty") == "unknown"
    assert classify_row("noext_binary", "binary", "null_byte") == "unknown"


def test_build_and_ide_and_vendor_context_rules():
    assert classify_row("TestResults.xcresult/Data/x.bin", "binary", "null_byte") == "build_test_output"
    assert classify_row("App/.build", "excluded:skipped_directory", ".build") == "build_test_output"
    assert classify_row("out.log", "excluded:unsupported_extension", ".log") == "build_test_output"
    assert classify_row("App.xcodeproj/project.pbxproj", "excluded:unsupported_extension", None) == "ide_metadata"
    assert classify_row("node_modules", "excluded:vendored_repo", "node_modules") == "vendored"
    assert classify_row(".DS_Store", "binary", "skip_extension:.DS_Store") == "os_cruft"


def test_product_assets_and_localization_and_config():
    assert classify_row("Assets.xcassets/Icon.imageset/icon.png", "binary", "skip_extension:.png") == "product_assets"
    assert classify_row("ui/logo.svg", "excluded:unsupported_extension", ".svg") == "product_assets"
    assert classify_row("Base.lproj/Main.strings", "excluded:unsupported_extension", None) == "localization"
    assert classify_row("config/settings.plist", "excluded:unsupported_extension", ".plist") == "config"
    assert classify_row("package-lock.json", "excluded:unsupported_extension", None) == "lockfile"


# ---------------------------------------------------------------------------
# build_inventory: ranking, dominance, pruned-directory ruling, degradation
# ---------------------------------------------------------------------------

def _rows(*items):
    return [{"path": p, "disposition": d, "reason": r} for p, d, r in items]


def test_dominant_group_leads_and_carries_cleanup_recommendation():
    rows = _rows(
        *[(f"TestResults.xcresult/Data/blob{i}.bin", "binary", "null_byte") for i in range(30)],
        ("logo.png", "binary", "skip_extension:.png"),
        (".DS_Store", "binary", "skip_extension:.DS_Store"),
        ("certs/server.pem", "excluded:unsupported_extension", ".pem"),
    )
    inv = build_inventory(rows, root=None)
    assert inv is not None
    assert inv["version"] == INVENTORY_VERSION
    assert inv["non_source_total"] == 33
    # Ranked: build/test output leads by count (I11).
    assert inv["groups"][0]["id"] == "build_test_output"
    assert inv["dominant"] == {"id": "build_test_output", "count": 30, "share": round(30 / 33, 4)}
    top = inv["groups"][0]
    assert "remove" in top["recommendation"].lower() and ".gitignore" in top["recommendation"].lower()
    assert top["flags"]["likely_unwanted"] is True
    # The .pem group is flagged security_sensitive somewhere in the output.
    secrets = [g for g in inv["groups"] if g["id"] == "secrets"]
    assert secrets and secrets[0]["flags"]["security_sensitive"] is True


def test_product_assets_read_as_expected_not_a_problem():
    rows = _rows(
        ("a.png", "binary", "skip_extension:.png"),
        ("b.jpg", "binary", "skip_extension:.jpg"),
        ("c.woff2", "binary", "skip_extension:.woff2"),
    )
    inv = build_inventory(rows, root=None)
    assert inv is not None
    assets = inv["groups"][0]
    assert assets["id"] == "product_assets"
    assert assets["flags"]["likely_unwanted"] is False
    assert assets["flags"]["security_sensitive"] is False
    assert "keep" in assets["recommendation"].lower()


def test_pruned_directory_counts_as_one_row_never_fabricated():
    # A pruned node_modules is a single ledger row standing for everything
    # beneath it; the inventory counts it as one and records it as a directory
    # row, never inventing per-file counts.
    rows = _rows(("node_modules", "excluded:vendored_repo", "node_modules"))
    inv = build_inventory(rows, root=None)
    assert inv is not None
    vend = inv["groups"][0]
    assert vend["id"] == "vendored"
    assert vend["count"] == 1
    assert vend["directory_rows"] == 1
    assert vend["bytes"] is None  # directory rows contribute no bytes


def test_no_non_source_rows_returns_none_for_degradation():
    # Only parsed and source-gap rows: nothing for the inventory to classify, so
    # it returns None and the projection omits the section (old-dataset parity).
    rows = _rows(
        ("src/main.py", "parsed", ""),
        ("src/big.py", "excluded:max_file_size", "500000"),
        ("src/broken.py", "failed", "SyntaxError"),
    )
    assert build_inventory(rows, root=None) is None


def test_ranking_is_deterministic_regardless_of_row_order():
    base = _rows(
        ("a.png", "binary", "skip_extension:.png"),
        ("b.png", "binary", "skip_extension:.png"),
        ("readme.txt", "excluded:unsupported_extension", ".txt"),
        ("x.qwerty", "excluded:unsupported_extension", ".qwerty"),
    )
    inv1 = build_inventory(base, root=None)
    inv2 = build_inventory(list(reversed(base)), root=None)
    assert [g["id"] for g in inv1["groups"]] == [g["id"] for g in inv2["groups"]]


# ---------------------------------------------------------------------------
# Projection: inventory present in build_coverage, bytes when tree is available
# ---------------------------------------------------------------------------

def _tree_with_noise(tmp: Path) -> Path:
    (tmp / "src").mkdir()
    (tmp / "src" / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    xc = tmp / "TestResults.xcresult" / "Data"
    xc.mkdir(parents=True)
    for i in range(12):
        (xc / f"blob{i}.bin").write_bytes(b"\x00\x01\x02\x03")
    (tmp / ".DS_Store").write_bytes(b"\x00")
    (tmp / "certs").mkdir()
    (tmp / "certs" / "server.pem").write_text("PRIVATE KEY", encoding="utf-8")
    (tmp / "logo.png").write_bytes(b"\x89PNG\r\n")
    return tmp


def test_build_coverage_embeds_inventory_with_bytes(tmp_path):
    root = _tree_with_noise(tmp_path)
    store = FactStore(":memory:")
    extract_repo(root, store)
    coverage = build_coverage(store, root=root)
    assert coverage is not None
    inv = coverage["inventory"]
    assert inv["version"] == INVENTORY_VERSION
    assert inv["dominant"]["id"] == "build_test_output"
    top = inv["groups"][0]
    assert top["id"] == "build_test_output"
    # Bytes are populated when the tree is available to stat.
    assert top["bytes"] is not None and top["bytes"] > 0
    # Samples are bounded and drillable paths.
    assert all("TestResults.xcresult" in p for p in top["samples"] if p.startswith("TestResults"))


def test_build_coverage_without_root_omits_bytes_but_keeps_inventory(tmp_path):
    root = _tree_with_noise(tmp_path)
    store = FactStore(":memory:")
    extract_repo(root, store)
    # Re-projection from the store alone (no tree): inventory still classifies,
    # bytes are simply absent.
    coverage = build_coverage(store, root=None)
    inv = coverage["inventory"]
    assert inv["dominant"]["id"] == "build_test_output"
    assert inv["groups"][0]["bytes"] is None


def test_source_only_tree_has_no_inventory_section(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    store = FactStore(":memory:")
    extract_repo(tmp_path, store)
    coverage = build_coverage(store, root=tmp_path)
    # A pure-source tree has no non-source rows, so no inventory key is emitted
    # and the coverage output is exactly the pre-inventory shape.
    assert coverage is not None
    assert "inventory" not in coverage


def test_split_projection_writes_inventory_into_coverage_json(tmp_path):
    # The viewer fetches coverage.json; prove the inventory rides in it on disk.
    repo = tmp_path / "repo"
    repo.mkdir()
    root = _tree_with_noise(repo)
    store = FactStore(":memory:")
    extract_repo(root, store)
    _, arch = derive_all(store, root.name, root_path=str(root))
    out = tmp_path / "site"
    project_split(arch, out, store=store, root=root, generated_at="2025-01-01T00:00:00Z")
    data = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    assert "inventory" in data
    assert data["inventory"]["dominant"]["id"] == "build_test_output"


def test_gitignore_candidate_suppressed_when_already_ignored(tmp_path):
    root = _tree_with_noise(tmp_path)
    (root / ".gitignore").write_text("TestResults.xcresult/\n.DS_Store\n", encoding="utf-8")
    store = FactStore(":memory:")
    extract_repo(root, store)
    coverage = build_coverage(store, root=root)
    inv = coverage["inventory"]
    build = [g for g in inv["groups"] if g["id"] == "build_test_output"][0]
    cruft = [g for g in inv["groups"] if g["id"] == "os_cruft"][0]
    # Both are already covered by .gitignore, so we do not nag to add them again.
    assert build["flags"]["gitignore_candidate"] is False
    assert cruft["flags"]["gitignore_candidate"] is False
