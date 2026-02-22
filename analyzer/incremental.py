"""Incremental analysis with diff metadata and baseline management.

Compares architecture scans between git revisions to produce diff summaries
indicating which components, relationships, and files changed. Both incremental
and full-rescan modes currently run the full ArchitectureScanner pipeline,
but they differ in the metadata attached to the output.
"""

import json
import logging
import os
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import __version__
from .scanner import ArchitectureScanner

logger = logging.getLogger(__name__)

# Marker files whose changes indicate the build system structure changed,
# warranting a full rescan rather than incremental analysis.
MARKER_FILES = frozenset({
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pyproject.toml",
    "Gemfile",
    "Podfile",
    "Package.swift",
    "build.gradle",
    "build.gradle.kts",
    "pom.xml",
    "pubspec.yaml",
})


class IncrementalAnalyzer:
    """Runs architecture analysis with diff metadata between git revisions.

    Compares the current scan against a previous baseline to produce a
    diff summary. For now, both incremental and full-rescan modes run
    the full ArchitectureScanner pipeline, but they differ in metadata.
    True selective re-analysis is a future optimization (Stream K).
    """

    def __init__(
        self,
        root: Path,
        base_sha: str = "",
        head_sha: str = "HEAD",
        baseline_path: Optional[Path] = None,
        max_file_size: int = 500_000,
        max_symbols: int = 0,
        preview_lines: int = 5,
    ):
        self.root = root.resolve()
        self.base_sha = base_sha
        self.head_sha = head_sha
        self.baseline_path = baseline_path
        self.max_file_size = max_file_size
        self.max_symbols = max_symbols
        self.preview_lines = preview_lines

    # ------------------------------------------------------------------
    # Baseline loading
    # ------------------------------------------------------------------

    def load_baseline(self) -> Optional[dict]:
        """Load a previous architecture.json from the baseline path.

        Returns None if the file does not exist, is unreadable, or
        contains invalid JSON.
        """
        if not self.baseline_path:
            return None
        path = Path(self.baseline_path)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load baseline %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Git diff
    # ------------------------------------------------------------------

    def get_changed_files(self) -> list[tuple[str, str]]:
        """Get changed files between base_sha and head_sha via git diff.

        Returns a list of (status, relative_path) tuples where status is
        one of: A (added), M (modified), D (deleted), C (copied),
        T (type changed). Renames appear as D+A pairs due to --no-renames.

        Returns an empty list if git is unavailable, the directory is
        not a git repo, or base_sha is empty.
        """
        if not self.base_sha:
            return []

        try:
            result = subprocess.run(
                [
                    "git", "diff", "--name-status", "--no-renames",
                    f"{self.base_sha}..{self.head_sha}",
                ],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            logger.warning("git is not available on PATH")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("git diff timed out")
            return []

        if result.returncode != 0:
            logger.warning(
                "git diff failed (exit %d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return []

        entries = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                entries.append((status[0], path))
        return entries

    # ------------------------------------------------------------------
    # File-to-component mapping
    # ------------------------------------------------------------------

    def map_files_to_components(
        self,
        changed_files: list[tuple[str, str]],
        baseline: dict,
    ) -> set[str]:
        """Map changed file paths to affected component IDs from baseline.

        Builds a file-to-component index by walking the baseline component
        tree. For files not in the index, walks parent directories to find
        the nearest component by path.
        """
        file_to_component: dict[str, str] = {}

        def _index_components(components: list[dict]):
            for comp in components:
                comp_id = comp.get("id", "")
                for fpath in comp.get("files", []):
                    file_to_component[fpath] = comp_id
                _index_components(comp.get("children", []))

        _index_components(baseline.get("components", []))

        # Also build component path index for fallback matching
        comp_paths = self._all_component_paths(baseline)

        affected = set()
        for _status, path in changed_files:
            normalized = path.replace(os.sep, "/")
            if normalized in file_to_component:
                affected.add(file_to_component[normalized])
            else:
                # File not in baseline; find nearest component by directory
                parts = normalized.split("/")
                for i in range(len(parts) - 1, 0, -1):
                    parent = "/".join(parts[:i])
                    for comp_id, comp_path in comp_paths:
                        if comp_path == parent:
                            affected.add(comp_id)
                            break
                    else:
                        continue
                    break

        return affected

    @staticmethod
    def _all_component_paths(baseline: dict) -> list[tuple[str, str]]:
        """Extract (component_id, component_path) from the baseline tree."""
        result = []

        def _walk(components):
            for comp in components:
                result.append((comp.get("id", ""), comp.get("path", "")))
                _walk(comp.get("children", []))

        _walk(baseline.get("components", []))
        return result

    # ------------------------------------------------------------------
    # Full rescan decision
    # ------------------------------------------------------------------

    def should_full_rescan(
        self,
        changed_files: list[tuple[str, str]],
        baseline: Optional[dict],
    ) -> bool:
        """Determine whether a full rescan is needed.

        Returns True when:
        - No base_sha is provided (nothing to diff against)
        - No baseline exists (first run)
        - Analyzer version mismatch (parser improvements need full rescan)
        - No changed files (git diff failed or empty range)
        - A marker file (package.json, Cargo.toml, etc.) changed
        - More than 50% of known files changed
        """
        if not self.base_sha:
            return True

        if baseline is None:
            return True

        baseline_version = baseline.get("analyzer_version", "")
        if baseline_version != __version__:
            return True

        if not changed_files:
            return True

        changed_names = {os.path.basename(path) for _status, path in changed_files}
        if changed_names & MARKER_FILES:
            return True

        baseline_file_count = len(baseline.get("files", []))
        if baseline_file_count > 0 and len(changed_files) / baseline_file_count > 0.5:
            return True

        return False

    def _rescan_reason(
        self,
        changed_files: list[tuple[str, str]],
        baseline: Optional[dict],
    ) -> str:
        """Return a human-readable reason for the full rescan."""
        if not self.base_sha:
            return "no base SHA provided"
        if baseline is None:
            return "no baseline found"
        baseline_version = baseline.get("analyzer_version", "")
        if baseline_version != __version__:
            return (
                f"analyzer version changed ({baseline_version} -> {__version__})"
            )
        if not changed_files:
            return "could not determine changed files"
        changed_names = {os.path.basename(p) for _, p in changed_files}
        marker_hits = changed_names & MARKER_FILES
        if marker_hits:
            return f"marker file changed: {', '.join(sorted(marker_hits))}"
        baseline_file_count = len(baseline.get("files", []))
        if baseline_file_count > 0 and len(changed_files) / baseline_file_count > 0.5:
            return (
                f"too many files changed ({len(changed_files)}/{baseline_file_count})"
            )
        return "unknown"

    # ------------------------------------------------------------------
    # Diff summary
    # ------------------------------------------------------------------

    def compute_diff_summary(
        self,
        old_baseline: Optional[dict],
        new_arch: dict,
        changed_file_count: int = 0,
    ) -> dict:
        """Compute a summary of what changed between old baseline and new scan.

        Returns a dict with component add/remove/modify lists,
        relationship change counts, and file change count.
        """
        new_ids = set(self._collect_component_ids(new_arch.get("components", [])))

        if old_baseline is None:
            return {
                "components_added": sorted(new_ids),
                "components_removed": [],
                "components_modified": [],
                "relationships_added": len(new_arch.get("relationships", [])),
                "relationships_removed": 0,
                "files_changed": changed_file_count,
            }

        old_ids = set(
            self._collect_component_ids(old_baseline.get("components", []))
        )

        added = sorted(new_ids - old_ids)
        removed = sorted(old_ids - new_ids)

        # Detect modifications via metrics comparison
        old_metrics = self._collect_component_metrics(
            old_baseline.get("components", [])
        )
        new_metrics = self._collect_component_metrics(
            new_arch.get("components", [])
        )
        modified = sorted(
            cid for cid in (old_ids & new_ids)
            if old_metrics.get(cid, {}) != new_metrics.get(cid, {})
        )

        # Relationship set diff
        old_rels = {
            (r.get("source"), r.get("target"), r.get("type"))
            for r in old_baseline.get("relationships", [])
        }
        new_rels = {
            (r.get("source"), r.get("target"), r.get("type"))
            for r in new_arch.get("relationships", [])
        }

        return {
            "components_added": added,
            "components_removed": removed,
            "components_modified": modified,
            "relationships_added": len(new_rels - old_rels),
            "relationships_removed": len(old_rels - new_rels),
            "files_changed": changed_file_count,
        }

    @staticmethod
    def _collect_component_ids(components: list) -> list[str]:
        """Recursively collect all component IDs from a component tree."""
        ids = []
        for comp in components:
            ids.append(comp.get("id", ""))
            ids.extend(
                IncrementalAnalyzer._collect_component_ids(
                    comp.get("children", [])
                )
            )
        return ids

    @staticmethod
    def _collect_component_metrics(components: list) -> dict[str, dict]:
        """Recursively collect component metrics keyed by ID."""
        result = {}
        for comp in components:
            comp_id = comp.get("id", "")
            result[comp_id] = comp.get("metrics", {})
            result.update(
                IncrementalAnalyzer._collect_component_metrics(
                    comp.get("children", [])
                )
            )
        return result

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Orchestrate the incremental analysis.

        1. Load baseline from disk
        2. Get changed files from git diff
        3. Decide full rescan vs incremental
        4. Run the full scan (both paths use ArchitectureScanner for now)
        5. Compute diff summary
        6. Attach incremental metadata to the output
        7. Return the architecture dict
        """
        baseline = self.load_baseline()
        changed_files = self.get_changed_files()
        full_rescan = self.should_full_rescan(changed_files, baseline)

        if full_rescan:
            reason = self._rescan_reason(changed_files, baseline)
            print(f"Full rescan: {reason}")
        else:
            affected = self.map_files_to_components(changed_files, baseline)
            print(
                f"Incremental: {len(changed_files)} files changed, "
                f"{len(affected)} components affected"
            )

        # Both paths run full scan for now (true incremental is Stream K)
        print(f"Scanning {self.root}...")
        scanner = ArchitectureScanner(
            self.root,
            max_file_size=self.max_file_size,
            max_symbols=self.max_symbols,
            preview_lines=self.preview_lines,
        )
        arch = scanner.scan()
        arch_dict = asdict(arch)

        # Compute diff
        diff_summary = self.compute_diff_summary(
            baseline, arch_dict, changed_file_count=len(changed_files)
        )

        # Attach incremental metadata
        arch_dict["incremental"] = {
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "full_rescan": full_rescan,
            "diff": diff_summary,
            "changed_files": [
                {"status": s, "path": p} for s, p in changed_files
            ],
            "affected_components": sorted(
                self.map_files_to_components(changed_files, baseline)
                if baseline else []
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return arch_dict
