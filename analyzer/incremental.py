"""Incremental analysis with true selective re-scanning.

Compares architecture scans between git revisions. When changes are small,
only affected components (and their direct importers) are rescanned. The
results are merged back into the baseline to produce an updated architecture.

Known limitations of incremental mode:
- Dependency expansion is one level deep (direct importers only). Transitive
  re-exports can cause missed updates. Add --deep-incremental later if needed.
- No component discovery (new dirs without marker files need full rescan).
- Content hashes are stored but not yet used for skip optimization.
"""

import hashlib
import json
import logging
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import __version__
from .models import to_dict
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


# ------------------------------------------------------------------
# K.1: Component dependency graph
# ------------------------------------------------------------------

def build_component_dependency_graph(baseline: dict) -> dict[str, set[str]]:
    """Build a reverse dependency map from the baseline's relationships.

    Returns a dict mapping each component ID to the set of component IDs
    that directly import from it. Only considers "import" relationships;
    runtime relationships (http, websocket, etc.) do not represent
    compile-time dependencies.

    Expansion is one level deep: if A imports B imports C, changing C
    expands to {C, B} but not to A.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for rel in baseline.get("relationships", []):
        if rel.get("type") != "import":
            continue
        source = rel.get("source", "")
        target = rel.get("target", "")
        if source and target and source != target:
            graph[target].add(source)
    return dict(graph)


def build_architectural_neighbor_graph(baseline: dict) -> dict[str, set[str]]:
    """Build an undirected neighbor map using ALL relationship types.

    Unlike ``build_component_dependency_graph`` (import-only, directed),
    this considers every relationship type (http, websocket, database,
    import, etc.) and treats them as bidirectional. When component A has
    any relationship with component B, both A and B appear in each
    other's neighbor set.

    This is used for AI enhancement expansion: if a server changes its
    auth scheme, the client's relationship description is stale even
    though the client is not an *import* neighbor.

    Returns a dict mapping each component ID to the set of component IDs
    that are architecturally related to it via any relationship.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for rel in baseline.get("relationships", []):
        source = rel.get("source", "")
        target = rel.get("target", "")
        if source and target and source != target:
            graph[source].add(target)
            graph[target].add(source)
    return dict(graph)


# ------------------------------------------------------------------
# K.5: Baseline caching
# ------------------------------------------------------------------

def save_baseline_cache(
    arch_dict: dict,
    baseline_dir: Path,
    root: Path,
) -> None:
    """Save baseline with auxiliary cache files for fast incremental lookups.

    Creates:
    - architecture.json: full architecture snapshot
    - file-index.json: file path -> component_id + content_hash
    - import-graph.json: component dependency graph (reverse import map)
    """
    baseline_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save architecture.json
    arch_path = baseline_dir / "architecture.json"
    with open(arch_path, "w", encoding="utf-8") as f:
        json.dump(arch_dict, f, default=str)

    # 2. Build and save file-index.json
    file_index = {}
    # Build file-to-component map
    file_to_comp: dict[str, str] = {}

    def _index_comp_files(components):
        for comp in components:
            cid = comp.get("id", "")
            for fpath in comp.get("files", []):
                file_to_comp[fpath] = cid
            _index_comp_files(comp.get("children", []))

    _index_comp_files(arch_dict.get("components", []))

    for f in arch_dict.get("files", []):
        fpath = f.get("path", "")
        if not fpath:
            continue
        content_hash = ""
        try:
            full_path = root / fpath
            content = full_path.read_bytes()
            content_hash = "sha256:" + hashlib.sha256(content).hexdigest()[:16]
        except OSError:
            pass
        file_index[fpath] = {
            "component_id": file_to_comp.get(fpath, ""),
            "content_hash": content_hash,
            "lines": f.get("lines", 0),
            "size_bytes": f.get("size_bytes", 0),
        }

    index_path = baseline_dir / "file-index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(file_index, f, default=str)

    # 3. Build and save import-graph.json
    dep_graph = build_component_dependency_graph(arch_dict)
    # Convert sets to lists for JSON serialization
    serializable_graph = {k: sorted(v) for k, v in dep_graph.items()}
    graph_path = baseline_dir / "import-graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(serializable_graph, f, default=str)


def load_file_index(baseline_dir: Path) -> Optional[dict]:
    """Load the file-index.json cache file."""
    path = baseline_dir / "file-index.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_import_graph(baseline_dir: Path) -> Optional[dict[str, list[str]]]:
    """Load the import-graph.json cache file."""
    path = baseline_dir / "import-graph.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ------------------------------------------------------------------
# Stats recalculation
# ------------------------------------------------------------------

def _recalculate_stats(arch_dict: dict) -> dict:
    """Recalculate architecture-level statistics from current state."""
    total_files = len(arch_dict.get("files", []))
    total_lines = 0
    total_size = 0
    languages: dict[str, int] = defaultdict(int)

    for f in arch_dict.get("files", []):
        lines = f.get("lines", 0)
        total_lines += lines
        total_size += f.get("size_bytes", 0)
        lang = f.get("language", "")
        if lang:
            languages[lang] += lines

    total_components = 0

    def _count_components(components):
        nonlocal total_components
        for comp in components:
            total_components += 1
            _count_components(comp.get("children", []))

    _count_components(arch_dict.get("components", []))

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "total_size_bytes": total_size,
        "languages": dict(languages),
        "total_symbols": len(arch_dict.get("symbols", [])),
        "total_components": total_components,
        "total_relationships": len(arch_dict.get("relationships", [])),
    }


def _affected_ids_to_paths(
    affected_ids: set[str], baseline: dict
) -> list[str]:
    """Convert affected component IDs to their directory paths.

    Walks the baseline component tree and collects the ``path`` field
    for every component whose ``id`` is in *affected_ids*.  Returns a
    deduplicated, sorted list of directory paths suitable for passing
    as ``scope_paths`` to ``ArchitectureScanner``.
    """
    paths: set[str] = set()

    def _walk(components: list[dict]) -> None:
        for comp in components:
            if comp.get("id", "") in affected_ids:
                p = comp.get("path", "")
                if p:
                    paths.add(p)
            _walk(comp.get("children", []))

    _walk(baseline.get("components", []))
    return sorted(paths)


# ------------------------------------------------------------------
# IncrementalAnalyzer class
# ------------------------------------------------------------------

class IncrementalAnalyzer:
    """Runs architecture analysis with true incremental re-scanning.

    When changes are small, only rescans affected components and their
    direct importers, then merges results back into the baseline. Falls
    back to a full ArchitectureScanner pipeline when structural changes
    are detected (marker files, version mismatch, etc.).
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
        - A changed file maps to no known component (new root-level file or
          new directory), which the incremental path would silently drop
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

        # A changed file that maps to no baseline component (a new root-level
        # file or a file in a brand-new directory) would be silently dropped by
        # the incremental path, which only rescans components reachable from the
        # change set. Fall back to a full rescan so the new file is included
        # (F-CRIT-8).
        if self._unmapped_changed_files(changed_files, baseline):
            return True

        return False

    def _unmapped_changed_files(
        self,
        changed_files: list[tuple[str, str]],
        baseline: Optional[dict],
    ) -> list[str]:
        """Return changed file paths that map to no baseline component.

        Mirrors the per-file matching in ``map_files_to_components``: a path is
        mapped if it is a known baseline file or if one of its parent
        directories is a component path. Anything else (a new root-level file,
        or a file under a directory that has no component) is unmapped and would
        be dropped by the incremental path.
        """
        if baseline is None:
            return []

        file_to_component: dict[str, str] = {}

        def _index_components(components):
            for comp in components:
                comp_id = comp.get("id", "")
                for fpath in comp.get("files", []):
                    file_to_component[fpath] = comp_id
                _index_components(comp.get("children", []))

        _index_components(baseline.get("components", []))
        comp_paths = self._all_component_paths(baseline)

        unmapped = []
        for _status, path in changed_files:
            normalized = path.replace(os.sep, "/")
            if normalized in file_to_component:
                continue
            parts = normalized.split("/")
            matched = False
            for i in range(len(parts) - 1, 0, -1):
                parent = "/".join(parts[:i])
                if any(comp_path == parent for _cid, comp_path in comp_paths):
                    matched = True
                    break
            if not matched:
                unmapped.append(normalized)
        return unmapped

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
        unmapped = self._unmapped_changed_files(changed_files, baseline)
        if unmapped:
            preview = ", ".join(sorted(unmapped)[:5])
            suffix = ", ..." if len(unmapped) > 5 else ""
            return (
                f"{len(unmapped)} changed file(s) map to no known component "
                f"(new root-level file or new directory): {preview}{suffix}"
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
            all_rels = {
                (r.get("source"), r.get("target"), r.get("type"))
                for r in new_arch.get("relationships", [])
            }
            return {
                "components_added": sorted(new_ids),
                "components_removed": [],
                "components_modified": [],
                "relationships_added": len(all_rels),
                "relationships_removed": 0,
                "relationships_added_tuples": sorted(all_rels),
                "relationships_removed_tuples": [],
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
            "relationships_added_tuples": sorted(new_rels - old_rels),
            "relationships_removed_tuples": sorted(old_rels - new_rels),
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
    # Changelog
    # ------------------------------------------------------------------

    @staticmethod
    def _build_component_info_map(
        components: list,
    ) -> dict[str, dict[str, str]]:
        """Build id -> {name, type} map from a component tree."""
        result: dict[str, dict[str, str]] = {}

        def walk(comps: list) -> None:
            for comp in comps:
                cid = comp.get("id", "")
                result[cid] = {
                    "name": comp.get("name", cid),
                    "type": comp.get("type", "module"),
                }
                walk(comp.get("children", []))

        walk(components)
        return result

    def build_changelog_entry(
        self,
        diff_summary: dict,
        old_arch: Optional[dict],
        new_arch: dict,
        scan_type: str,
        serial: int,
    ) -> dict:
        """Convert a diff summary into a structured changelog entry.

        Each change references specific component/relationship IDs with
        human-readable names so the viewer can render clickable links.
        """
        # Build name/type lookup from both old and new trees
        info = self._build_component_info_map(
            new_arch.get("components", [])
        )
        if old_arch:
            old_info = self._build_component_info_map(
                old_arch.get("components", [])
            )
            # Merge old info for removed components (not in new tree)
            for cid, cinfo in old_info.items():
                if cid not in info:
                    info[cid] = cinfo

        changes: list[dict] = []

        # Component changes
        for cid in diff_summary.get("components_added", []):
            ci = info.get(cid, {"name": cid, "type": "module"})
            changes.append({
                "kind": "component_added",
                "target_id": cid,
                "target_name": ci["name"],
                "target_type": ci["type"],
                "detail": "New component discovered",
            })

        for cid in diff_summary.get("components_removed", []):
            ci = info.get(cid, {"name": cid, "type": "module"})
            changes.append({
                "kind": "component_removed",
                "target_id": cid,
                "target_name": ci["name"],
                "target_type": ci["type"],
                "detail": "Component no longer detected",
            })

        for cid in diff_summary.get("components_modified", []):
            ci = info.get(cid, {"name": cid, "type": "module"})
            changes.append({
                "kind": "component_modified",
                "target_id": cid,
                "target_name": ci["name"],
                "target_type": ci["type"],
                "detail": "Component structure changed",
            })

        # Relationship changes
        for src, tgt, rtype in diff_summary.get(
            "relationships_added_tuples", []
        ):
            src_info = info.get(src, {"name": src})
            tgt_info = info.get(tgt, {"name": tgt})
            changes.append({
                "kind": "relationship_added",
                "target_id": f"{src}->{tgt}",
                "target_name": (
                    f"{src_info['name']} -> {tgt_info['name']}"
                ),
                "target_type": rtype or "dependency",
                "source_id": src,
                "source_name": src_info["name"],
                "dest_id": tgt,
                "dest_name": tgt_info["name"],
                "detail": f"{rtype or 'dependency'} connection",
            })

        for src, tgt, rtype in diff_summary.get(
            "relationships_removed_tuples", []
        ):
            src_info = info.get(src, {"name": src})
            tgt_info = info.get(tgt, {"name": tgt})
            changes.append({
                "kind": "relationship_removed",
                "target_id": f"{src}->{tgt}",
                "target_name": (
                    f"{src_info['name']} -> {tgt_info['name']}"
                ),
                "target_type": rtype or "dependency",
                "source_id": src,
                "source_name": src_info["name"],
                "dest_id": tgt,
                "dest_name": tgt_info["name"],
                "detail": f"{rtype or 'dependency'} connection removed",
            })

        # Build summary string
        parts = []
        added = len(diff_summary.get("components_added", []))
        removed = len(diff_summary.get("components_removed", []))
        modified = len(diff_summary.get("components_modified", []))
        rel_added = diff_summary.get("relationships_added", 0)
        rel_removed = diff_summary.get("relationships_removed", 0)
        if added:
            parts.append(
                f"{added} component{'s' if added != 1 else ''} added"
            )
        if modified:
            parts.append(
                f"{modified} component{'s' if modified != 1 else ''} modified"
            )
        if removed:
            parts.append(
                f"{removed} component{'s' if removed != 1 else ''} removed"
            )
        if rel_added:
            parts.append(
                f"{rel_added} relationship{'s' if rel_added != 1 else ''} added"
            )
        if rel_removed:
            parts.append(
                f"{rel_removed} relationship{'s' if rel_removed != 1 else ''} removed"
            )
        summary = ", ".join(parts) if parts else "No structural changes"

        # Get commit sha
        commit_sha = getattr(self, "head_sha", None) or ""

        return {
            "serial": serial,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "commit_sha": commit_sha,
            "scan_type": scan_type,
            "summary": summary,
            "changes": changes,
        }

    @staticmethod
    def _append_changelog(
        arch_dict: dict,
        entry: dict,
        baseline: Optional[dict],
        max_entries: int = 50,
    ) -> None:
        """Append a changelog entry to arch_dict, preserving history from baseline."""
        existing = list(baseline.get("changelog", [])) if baseline else []
        if entry.get("changes"):
            existing.append(entry)
        # Cap at max_entries, trimming oldest
        if len(existing) > max_entries:
            existing = existing[-max_entries:]
        arch_dict["changelog"] = existing
        arch_dict["changelog_serial"] = entry["serial"]

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Orchestrate the incremental analysis.

        Full rescan path: delegates to ArchitectureScanner when structural
        changes are detected.

        Incremental path:
        1. Map changed files to affected component IDs
        2. Expand affected set via dependency graph (one level deep)
        3. Rescan each affected component
        4. Merge rescanned data into baseline
        5. Re-detect relationships for affected components
        6. Recalculate stats and compute diff summary
        """
        baseline = self.load_baseline()
        changed_files = self.get_changed_files()
        full_rescan = self.should_full_rescan(changed_files, baseline)

        if full_rescan:
            return self._run_full_rescan(baseline, changed_files)

        return self._run_incremental(baseline, changed_files)

    def _run_full_rescan(
        self,
        baseline: Optional[dict],
        changed_files: list[tuple[str, str]],
    ) -> dict:
        """Run a full rescan using ArchitectureScanner."""
        reason = self._rescan_reason(changed_files, baseline)
        print(f"Full rescan: {reason}")
        print(f"Scanning {self.root}...")

        scanner = ArchitectureScanner(
            self.root,
            max_file_size=self.max_file_size,
            max_symbols=self.max_symbols,
            preview_lines=self.preview_lines,
        )
        arch = scanner.scan()
        arch_dict = to_dict(arch)

        diff_summary = self.compute_diff_summary(
            baseline, arch_dict, changed_file_count=len(changed_files)
        )

        arch_dict["incremental"] = {
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "full_rescan": True,
            "rescan_reason": reason,
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

        # Build and append changelog entry
        scan_type = "initial" if baseline is None else "full"
        prev_serial = (baseline or {}).get("changelog_serial", 0)
        entry = self.build_changelog_entry(
            diff_summary, baseline, arch_dict, scan_type, prev_serial + 1
        )
        self._append_changelog(arch_dict, entry, baseline)

        return arch_dict

    def _run_incremental(
        self,
        baseline: dict,
        changed_files: list[tuple[str, str]],
    ) -> dict:
        """Run true incremental re-analysis on affected components only.

        Uses ArchitectureScanner with scope_paths to rescan only the affected
        components while preserving baseline data for everything else. This
        eliminates code duplication and runs all scanner phases (type promotion,
        port assignment, UI flow detection, all 11 relationship strategies,
        documentation extraction) on the affected components.
        """
        # Map changed files to directly affected components
        directly_affected = self.map_files_to_components(changed_files, baseline)

        # Expand via dependency graph (one level: direct importers)
        dep_graph = build_component_dependency_graph(baseline)
        expanded = set(directly_affected)
        for comp_id in directly_affected:
            importers = dep_graph.get(comp_id, set())
            expanded.update(importers)

        affected = expanded
        print(
            f"Incremental: {len(changed_files)} files changed, "
            f"{len(directly_affected)} directly affected, "
            f"{len(affected)} total (with importers)"
        )

        # Convert affected component IDs to scope_paths (directory paths)
        scope_paths = _affected_ids_to_paths(affected, baseline)
        print(f"  Scope paths: {scope_paths}")

        # Run scoped scanner: rescans only scope_paths, preserves baseline
        # for everything else. All scanner phases run with proper scoping.
        scanner = ArchitectureScanner(
            self.root,
            max_file_size=self.max_file_size,
            max_symbols=self.max_symbols,
            preview_lines=self.preview_lines,
            scope_paths=scope_paths,
            baseline=baseline,
        )
        arch = scanner.scan()
        working = to_dict(arch)

        working["generated_at"] = datetime.now(timezone.utc).isoformat()
        working["analyzer_version"] = __version__

        # Compute diff summary
        diff_summary = self.compute_diff_summary(
            baseline, working, changed_file_count=len(changed_files)
        )

        # Attach incremental metadata
        working["incremental"] = {
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "full_rescan": False,
            "diff": diff_summary,
            "changed_files": [
                {"status": s, "path": p} for s, p in changed_files
            ],
            "affected_components": sorted(affected),
            "directly_affected_components": sorted(directly_affected),
            "expanded_via_dependency": sorted(affected - directly_affected),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Build and append changelog entry
        prev_serial = baseline.get("changelog_serial", 0)
        entry = self.build_changelog_entry(
            diff_summary, baseline, working, "incremental", prev_serial + 1
        )
        self._append_changelog(working, entry, baseline)

        return working
