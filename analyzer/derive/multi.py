"""Multi-repo derivation: per-repo extract+derive stores, merged architecture.

Mirrors ``MultiRepoOrchestrator._merge`` (the old engine) over the new
pipeline: each repository is extracted into its own store and derived with the
repo segment of the frozen symbol-ID grammar set to the repo name, then the
per-repo architectures are merged under ``repo:<name>`` container components
with prefixed component and file paths, exactly the shape the viewer already
renders.

Difference from the old engine, enumerated for the P4-7 gate: symbol identity
in multi-repo mode uses the grammar's repo segment (for example
``backend svc app/server.py Foo``) instead of the old in-place string-prefix
hack (``backend/app/server.py:Foo:12``). The display ``file`` field on merged
symbols and files keeps the ``<repo>/`` prefix for viewer compatibility.

Local-path repositories only: cloning remote URLs stays with the old
orchestrator until the P4-7 cutover wires the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..store import FactStore
from .pipeline import derive_all


def derive_multi_from_config(config_path) -> dict:
    """Run extract+derive per repo from a solution.json and merge the results."""
    from ..extract import extract_repo

    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_dir = config_path.parent

    solution_name = config.get("solution", "Solution")
    description = config.get("description", "")

    architectures: list[tuple[str, dict]] = []
    for repo_def in config.get("repositories", []):
        name = repo_def["name"]
        repo_path = Path(repo_def["path"])
        if not repo_path.is_absolute():
            repo_path = (config_dir / repo_path).resolve()
        store = FactStore(":memory:")
        extract_repo(repo_path, store, repo=name)
        _, arch = derive_all(store, repo_path.name, repo=name)
        architectures.append((name, arch))

    return merge_architectures(solution_name, description, architectures, config)


def merge_architectures(
    solution_name: str,
    description: str,
    architectures: list[tuple[str, dict]],
    config: dict,
) -> dict:
    merged = {
        "name": solution_name,
        "description": description,
        "repository": None,
        "default_branch": None,
        "generated_at": "",
        "analyzer_version": "",
        "root_path": "",
        "components": [],
        "relationships": [],
        "symbols": [],
        "files": [],
        "stats": {
            "total_files": 0, "total_lines": 0, "total_size_bytes": 0,
            "total_symbols": 0, "total_components": 0,
            "total_relationships": 0, "languages": {},
        },
        "repositories": [],
    }

    for repo_name, arch in architectures:
        prefix = f"{repo_name}/"
        merged["repositories"].append({
            "name": repo_name,
            "repository": arch.get("repository"),
            "default_branch": arch.get("default_branch"),
        })

        stats = arch.get("stats", {})
        merged["components"].append({
            "id": f"repo:{repo_name}",
            "name": repo_name,
            "type": "repository",
            "path": f"@{repo_name}",
            "language": _primary_language(stats.get("languages", {})),
            "framework": None,
            "description": arch.get("description") or None,
            "port": None,
            "children": _prefix_components(arch.get("components", []), prefix),
            "files": [],
            "entry_points": [],
            "config_files": [],
            "metrics": {
                "files": stats.get("total_files", 0),
                "lines": stats.get("total_lines", 0),
                "size_bytes": stats.get("total_size_bytes", 0),
                "symbols": stats.get("total_symbols", 0),
                "languages": stats.get("languages", {}),
            },
            "docs": {
                "readme": None, "claude_md": None, "changelog": None,
                "api_docs": None, "architecture_notes": None,
                "purpose": arch.get("description") or None,
                "key_decisions": [], "patterns": [], "tech_stack": [],
                "env_vars": [], "api_endpoints": [],
            },
        })
        for rel in arch.get("relationships", []):
            r = dict(rel)
            r["source"] = prefix + r["source"]
            r["target"] = prefix + r["target"]
            merged["relationships"].append(r)
        for sym in arch.get("symbols", []):
            s = dict(sym)
            # Grammar ids already carry the repo segment; only the display
            # file path gains the repo prefix (see module docstring).
            s["file"] = prefix + s["file"]
            merged["symbols"].append(s)
        for fi in arch.get("files", []):
            f = dict(fi)
            f["path"] = prefix + f["path"]
            merged["files"].append(f)

        for key in ("total_files", "total_lines", "total_size_bytes",
                    "total_symbols", "total_components", "total_relationships"):
            merged["stats"][key] += stats.get(key, 0)
        for lang, lines in stats.get("languages", {}).items():
            merged["stats"]["languages"][lang] = (
                merged["stats"]["languages"].get(lang, 0) + lines
            )

    for rel_def in config.get("cross_repo_relationships", []):
        merged["relationships"].append({
            "source": f"repo:{rel_def.get('source_repo', '')}",
            "target": f"repo:{rel_def.get('target_repo', '')}",
            "type": rel_def.get("type", "http"),
            "label": rel_def.get("label"),
            "protocol": rel_def.get("type"),
            "port": rel_def.get("port"),
            "bidirectional": rel_def.get("bidirectional", False),
        })
        merged["stats"]["total_relationships"] += 1

    merged["stats"]["total_components"] += len(architectures)
    return merged


def _prefix_components(components: list, prefix: str) -> list:
    out = []
    for comp in components:
        c = dict(comp)
        c["id"] = prefix + c["id"]
        c["path"] = prefix + c["path"]
        c["files"] = [prefix + f for f in c.get("files", [])]
        c["children"] = _prefix_components(c.get("children", []), prefix)
        out.append(c)
    return out


def _primary_language(languages: dict):
    if not languages:
        return None
    return max(languages, key=languages.get)
