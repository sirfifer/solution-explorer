"""Multi-repository analysis orchestrator."""

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Architecture
from .scanner import ArchitectureScanner


class MultiRepoOrchestrator:
    """Orchestrates analysis across multiple repositories defined in a config file."""

    def __init__(self, config_path: Path, max_file_size: int = 500_000,
                 max_symbols: int = 5000, preview_lines: int = 5):
        self.config_path = config_path.resolve()
        self.config_dir = self.config_path.parent
        self.max_file_size = max_file_size
        self.max_symbols = max_symbols
        self.preview_lines = preview_lines

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

    def run(self) -> Architecture:
        """Analyze all repositories and merge into a single Architecture."""
        solution_name = self.config.get("solution", "Solution")
        description = self.config.get("description", "")
        repos = self.config.get("repositories", [])

        if not repos:
            print("Error: No repositories defined in config", file=sys.stderr)
            sys.exit(1)

        architectures: list[tuple[str, Architecture]] = []
        temp_dirs: list[tempfile.TemporaryDirectory] = []

        try:
            for repo_def in repos:
                name = repo_def["name"]
                repo_path = self._resolve_repo(repo_def, temp_dirs)
                print(f"\nAnalyzing repository: {name} ({repo_path})")

                scanner = ArchitectureScanner(
                    repo_path,
                    max_file_size=self.max_file_size,
                    max_symbols=self.max_symbols,
                    preview_lines=self.preview_lines,
                )
                arch = scanner.scan()
                architectures.append((name, arch))
        finally:
            for td in temp_dirs:
                td.cleanup()

        return self._merge(solution_name, description, architectures)

    def _resolve_repo(self, repo_def: dict,
                      temp_dirs: list) -> Path:
        """Resolve a repository definition to a local path."""
        if "path" in repo_def:
            p = Path(repo_def["path"])
            if not p.is_absolute():
                p = (self.config_dir / p).resolve()
            if not p.is_dir():
                print(f"Error: Repository path does not exist: {p}", file=sys.stderr)
                sys.exit(1)
            return p

        url = repo_def.get("url", "")
        ref = repo_def.get("ref", "HEAD")

        if not url:
            print(f"Error: Repository '{repo_def.get('name', '?')}' has no path or url",
                  file=sys.stderr)
            sys.exit(1)

        td = tempfile.TemporaryDirectory(prefix="solution-explorer-")
        temp_dirs.append(td)
        clone_path = Path(td.name)

        # Support private repos via GITHUB_TOKEN env var
        clone_url = url
        token = os.environ.get("GITHUB_TOKEN")
        if token and "github.com" in url:
            clone_url = re.sub(
                r'https://github\.com/',
                f'https://x-access-token:{token}@github.com/',
                url,
            )

        cmd = ["git", "clone", "--depth", "1"]
        if ref and ref != "HEAD":
            cmd.extend(["--branch", ref])
        cmd.extend([clone_url, str(clone_path)])

        print(f"  Cloning {url} (ref={ref})...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error cloning {url}: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        return clone_path

    def _merge(self, solution_name: str, description: str,
               architectures: list[tuple[str, Architecture]]) -> Architecture:
        """Merge multiple Architecture results into one."""
        merged = Architecture(
            name=solution_name,
            description=description,
            generated_at=datetime.now(timezone.utc).isoformat(),
            repositories=[],
        )

        all_components = []
        all_relationships = []
        all_symbols = []
        all_files = []
        total_stats: dict = {
            "total_files": 0,
            "total_lines": 0,
            "total_size_bytes": 0,
            "total_symbols": 0,
            "total_components": 0,
            "total_relationships": 0,
            "languages": {},
        }

        for repo_name, arch in architectures:
            prefix = f"{repo_name}/"

            # Record repository metadata
            repo_info = {"name": repo_name, "repository": arch.repository}
            merged.repositories.append(repo_info)

            # Prefix all IDs to avoid collisions
            prefixed_components = self._prefix_components(arch.components, prefix)
            prefixed_relationships = self._prefix_relationships(arch.relationships, prefix)
            prefixed_symbols = self._prefix_symbols(arch.symbols, prefix)
            prefixed_files = self._prefix_files(arch.files, prefix)

            # Wrap in a repository-level component
            repo_component = {
                "id": f"repo:{repo_name}",
                "name": repo_name,
                "type": "repository",
                "path": f"@{repo_name}",
                "language": self._primary_language(arch.stats.get("languages", {})),
                "framework": None,
                "description": arch.description or None,
                "port": None,
                "children": prefixed_components,
                "files": [],
                "entry_points": [],
                "config_files": [],
                "metrics": {
                    "files": arch.stats.get("total_files", 0),
                    "lines": arch.stats.get("total_lines", 0),
                    "size_bytes": arch.stats.get("total_size_bytes", 0),
                    "symbols": arch.stats.get("total_symbols", 0),
                    "languages": arch.stats.get("languages", {}),
                },
                "docs": {
                    "readme": None, "claude_md": None, "changelog": None,
                    "api_docs": None, "architecture_notes": None,
                    "purpose": arch.description or None,
                    "key_decisions": [], "patterns": [], "tech_stack": [],
                    "env_vars": [], "api_endpoints": [],
                },
            }
            all_components.append(repo_component)
            all_relationships.extend(prefixed_relationships)
            all_symbols.extend(prefixed_symbols)
            all_files.extend(prefixed_files)

            # Merge stats
            stats = arch.stats or {}
            total_stats["total_files"] += stats.get("total_files", 0)
            total_stats["total_lines"] += stats.get("total_lines", 0)
            total_stats["total_size_bytes"] += stats.get("total_size_bytes", 0)
            total_stats["total_symbols"] += stats.get("total_symbols", 0)
            total_stats["total_components"] += stats.get("total_components", 0)
            total_stats["total_relationships"] += stats.get("total_relationships", 0)
            for lang, lines in stats.get("languages", {}).items():
                total_stats["languages"][lang] = total_stats["languages"].get(lang, 0) + lines

        # Add explicit cross-repo relationships from config
        for rel_def in self.config.get("cross_repo_relationships", []):
            source_repo = rel_def.get("source_repo", "")
            target_repo = rel_def.get("target_repo", "")
            all_relationships.append({
                "source": f"repo:{source_repo}",
                "target": f"repo:{target_repo}",
                "type": rel_def.get("type", "http"),
                "label": rel_def.get("label"),
                "protocol": rel_def.get("type"),
                "port": rel_def.get("port"),
                "bidirectional": rel_def.get("bidirectional", False),
            })
            total_stats["total_relationships"] += 1

        total_stats["total_components"] += len(architectures)  # count repo nodes
        merged.components = all_components
        merged.relationships = all_relationships
        merged.symbols = all_symbols
        merged.files = all_files
        merged.stats = total_stats

        return merged

    def _prefix_components(self, components: list, prefix: str) -> list:
        """Recursively prefix all component IDs."""
        result = []
        for comp in components:
            c = dict(comp) if isinstance(comp, dict) else asdict(comp)
            c["id"] = prefix + c["id"]
            c["path"] = prefix + c["path"]
            c["files"] = [prefix + f for f in c.get("files", [])]
            c["children"] = self._prefix_components(c.get("children", []), prefix)
            result.append(c)
        return result

    def _prefix_relationships(self, relationships: list, prefix: str) -> list:
        result = []
        for rel in relationships:
            r = dict(rel) if isinstance(rel, dict) else asdict(rel)
            r["source"] = prefix + r["source"]
            r["target"] = prefix + r["target"]
            result.append(r)
        return result

    def _prefix_symbols(self, symbols: list, prefix: str) -> list:
        result = []
        for sym in symbols:
            s = dict(sym) if isinstance(sym, dict) else asdict(sym)
            s["id"] = prefix + s["id"]
            s["file"] = prefix + s["file"]
            if s.get("parent"):
                s["parent"] = prefix + s["parent"]
            result.append(s)
        return result

    def _prefix_files(self, files: list, prefix: str) -> list:
        result = []
        for fi in files:
            f = dict(fi) if isinstance(fi, dict) else asdict(fi)
            f["path"] = prefix + f["path"]
            f["symbols"] = [prefix + s for s in f.get("symbols", [])]
            result.append(f)
        return result

    def _primary_language(self, languages: dict) -> Optional[str]:
        if not languages:
            return None
        return max(languages, key=languages.get)
