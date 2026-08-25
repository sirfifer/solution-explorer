"""Tests for AI surface detection (analyzer/project/ai_surface.py).

The detector's one job is an inventory an owner can trust: every kind of AI
evidence it claims to cover, it must actually find, and a codebase with no AI
must yield an empty array rather than noise. So the fixture here plants one of
each evidence class and the assertions name them one by one; the polyglot
fixture (no AI) is the negative control.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _plant_fixture(root: Path) -> None:
    """A tiny repo carrying one signal of every evidence class."""
    (root / "app").mkdir(parents=True)
    (root / ".github").mkdir()

    # dependency evidence (npm manifest, parsed by the SBOM collector)
    (root / "package.json").write_text(json.dumps({
        "name": "planted", "version": "1.0.0",
        "dependencies": {
            "openai": "4.0.0",                      # provider_sdk
            "@modelcontextprotocol/sdk": "1.0.0",   # mcp
            "litellm": "1.0.0",                     # gateway
            "langchain": "0.3.0",                   # agent_framework
            "chromadb": "1.9.0",                    # vector_store
            "express": "4.18.0",                    # non-AI control
        },
    }, indent=2), encoding="utf-8")

    # import evidence (python)
    (root / "app" / "llm.py").write_text(
        "import anthropic\n"
        "import flask\n"                            # non-AI control
        "client = anthropic.Anthropic()\n",
        encoding="utf-8",
    )

    # content evidence: host, compat path, model id, env var
    (root / "app" / "config.py").write_text(
        'BASE = "https://api.openai.com/v1"\n'
        'COMPAT = "http://localhost:11434/v1/chat/completions"\n'
        'MODEL = "claude-sonnet-5"\n'
        'KEY_NAME = "ANTHROPIC_API_KEY"\n',
        encoding="utf-8",
    )

    # path evidence
    (root / ".mcp.json").write_text('{"mcpServers": {}}\n', encoding="utf-8")
    (root / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
    (root / ".github" / "copilot-instructions.md").write_text("# copilot\n", encoding="utf-8")

    # something ordinary so the repo derives components normally
    (root / "app" / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")


@pytest.fixture(scope="module")
def planted(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("planted-repo")
    out = tmp_path_factory.mktemp("planted-out")
    _plant_fixture(root)
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "analyze.py"), str(root),
         "-o", str(out / "arch"), "--split", "--engine", "v2",
         "--store", str(out / "index.db")],
        check=True, capture_output=True, text=True, cwd=REPO_ROOT,
    )
    manifest = json.loads((out / "arch" / "manifest.json").read_text(encoding="utf-8"))
    return manifest


def _by_kind(manifest: dict) -> dict:
    out: dict[str, list] = {}
    for item in manifest.get("ai_surface") or []:
        out.setdefault(item["kind"], []).append(item)
    return out


def test_every_planted_evidence_class_is_found(planted):
    kinds = _by_kind(planted)
    names = {(i["kind"], i["name"]) for i in planted.get("ai_surface") or []}

    # dependencies
    assert ("provider_sdk", "openai") in names
    assert ("mcp", "mcp-sdk") in names
    assert ("gateway", "litellm") in names
    assert ("agent_framework", "langchain") in names
    assert ("vector_store", "chroma") in names
    # imports
    assert ("provider_sdk", "anthropic") in names
    # content
    assert ("provider_endpoint", "openai") in names
    assert ("openai_compat", "openai-wire-protocol") in names
    assert any(k == "model_id" and n.startswith("claude-") for k, n in names)
    assert ("ai_env", "ANTHROPIC_API_KEY") in names
    # paths
    assert ("mcp", "mcp-config") in names
    config_names = {i["name"] for i in kinds.get("assistant_config", [])}
    assert {"claude-instructions", "copilot-instructions"} <= config_names


def test_non_ai_packages_are_not_swept_in(planted):
    names = {i["name"] for i in planted.get("ai_surface") or []}
    assert "express" not in names
    assert "flask" not in names


def test_evidence_carries_file_and_dependency_detail(planted):
    items = {(i["kind"], i["name"]): i for i in planted["ai_surface"]}
    openai = items[("provider_sdk", "openai")]
    assert any(e["file"] == "package.json" for e in openai["evidence"])
    assert openai["detail"].get("version") == "4.0.0"
    assert openai["detail"].get("ecosystem") == "npm"

    endpoint = items[("provider_endpoint", "openai")]
    ev = endpoint["evidence"][0]
    assert ev["file"] == "app/config.py" and ev.get("line") == 1


def test_emission_is_deterministic(planted):
    """Sorted ids, content-derived, no timestamps (invariant I4)."""
    items = planted["ai_surface"]
    ids = [i["id"] for i in items]
    assert ids == sorted(ids)
    assert all(i["id"].startswith("ai:") for i in items)
    text = json.dumps(items)
    assert "generated_at" not in text


def test_a_codebase_with_no_ai_yields_an_empty_array(tmp_path):
    """Empty is a real answer, and it must be empty rather than absent or noisy."""
    root = tmp_path / "clean"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "out"
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "analyze.py"), str(root),
         "-o", str(out / "arch"), "--split", "--engine", "v2",
         "--store", str(out / "index.db")],
        check=True, capture_output=True, text=True, cwd=REPO_ROOT,
    )
    manifest = json.loads((out / "arch" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("ai_surface") == []


def test_items_resolve_to_real_components(planted):
    """The linter's ref band will enforce this forever; prove it holds at birth."""
    ids = set()

    def walk(c):
        ids.add(c.get("id") or "")
        for ch in c.get("children") or []:
            walk(ch)

    for c in planted.get("components") or []:
        walk(c)
    for item in planted["ai_surface"]:
        assert item["component_id"] in ids, item["id"]
