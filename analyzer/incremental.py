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
import re
import subprocess
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import __version__
from .constants import CODE_LANGUAGES, LANGUAGE_MAP, SKIP_EXTENSIONS
from .models import to_dict
from .parsers import PARSERS
from .scanner import ArchitectureScanner
from .utils import _should_skip_dir

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
# K.2: Selective file re-scanning
# ------------------------------------------------------------------

def _find_component_in_tree(components: list[dict], component_id: str) -> Optional[dict]:
    """Find a component dict by ID in a nested component tree."""
    for comp in components:
        if comp.get("id") == component_id:
            return comp
        found = _find_component_in_tree(comp.get("children", []), component_id)
        if found is not None:
            return found
    return None


def _all_component_paths_flat(baseline: dict) -> list[tuple[str, str]]:
    """Extract (path, component_id) pairs from the baseline tree, sorted deepest first."""
    result = []

    def _walk(components):
        for comp in components:
            result.append((comp.get("path", ""), comp.get("id", "")))
            _walk(comp.get("children", []))

    _walk(baseline.get("components", []))
    result.sort(key=lambda x: len(x[0]), reverse=True)
    return result


def _find_component_for_file_from_baseline(
    file_path: str,
    comp_paths: list[tuple[str, str]],
) -> Optional[str]:
    """Find the deepest component that contains a file path.

    comp_paths should be sorted deepest-first (by path depth).
    Returns the component_id of the deepest matching component.
    """
    file_dir = os.path.dirname(file_path).replace(os.sep, "/")
    root_id = None
    for comp_path, comp_id in comp_paths:
        if not comp_path:
            root_id = comp_id
            continue
        if file_dir == comp_path or file_dir.startswith(comp_path + "/"):
            return comp_id
    return root_id


def _should_skip_file(fpath: Path) -> bool:
    """Check if a file should be skipped during scanning."""
    if fpath.name.startswith("."):
        return True
    if fpath.suffix.lower() in SKIP_EXTENSIONS:
        return True
    return False


def rescan_component(
    component_id: str,
    baseline: dict,
    root: Path,
    max_file_size: int = 500_000,
    preview_lines: int = 5,  # noqa: ARG001 - kept for API consistency with ArchitectureScanner
) -> Optional[dict]:
    """Re-scan a single component's files and return updated data.

    .. deprecated::
        Use ``ArchitectureScanner(scope_paths=..., baseline=...)`` instead.
        This function duplicates scanner logic and misses several phases.

    Walks the component's directory, re-parses all code files using the
    standard parsers, and returns a dict with updated file lists, symbols,
    metrics, framework, and port info.

    Returns None if the component is not found in the baseline.
    """
    warnings.warn(
        "rescan_component() is deprecated. Use ArchitectureScanner with "
        "scope_paths and baseline parameters instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    comp = _find_component_in_tree(
        baseline.get("components", []), component_id
    )
    if comp is None:
        return None

    comp_path = comp.get("path", "")
    comp_dir = root / comp_path if comp_path else root

    if not comp_dir.is_dir():
        return {
            "files": [],
            "metrics": {"files": 0, "lines": 0, "size_bytes": 0},
            "language": None,
            "framework": None,
            "port": None,
            "_file_infos": [],
            "_symbols": [],
        }

    # Build component path index from baseline so we can assign files
    # to the correct component (this component, not its children)
    comp_paths = _all_component_paths_flat(baseline)

    files = []
    file_infos = []
    symbols = []
    total_lines = 0
    total_size = 0
    language_counts: dict[str, int] = defaultdict(int)
    detected_framework = None
    detected_port = None

    for dirpath, dirnames, filenames in os.walk(comp_dir):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if _should_skip_file(fpath):
                continue

            ext = fpath.suffix.lower()
            lang = LANGUAGE_MAP.get(ext)
            if not lang:
                continue

            try:
                stat = fpath.stat()
                if stat.st_size > max_file_size or stat.st_size == 0:
                    continue
            except OSError:
                continue

            rel = os.path.relpath(fpath, root).replace(os.sep, "/")

            # Only include files that belong to THIS component, not children
            owning_comp = _find_component_for_file_from_baseline(rel, comp_paths)
            if owning_comp != component_id:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            lines = content.count("\n") + 1
            total_lines += lines
            total_size += stat.st_size
            language_counts[lang] += lines

            # Parse symbols and imports
            parser = PARSERS.get(lang)
            file_symbols = []
            file_imports = []
            module_doc = None
            if parser:
                file_symbols = parser.extract_symbols(content, rel)
                file_imports = parser.extract_imports(content)
                module_doc = parser.extract_file_doc(content)

                # Detect framework
                fw = parser.detect_framework(content)
                if fw:
                    if detected_framework is None:
                        detected_framework = fw

                # Detect ports (only in code files for server-type components)
                if lang in CODE_LANGUAGES:
                    ports = parser.detect_ports(content)
                    if ports and detected_port is None:
                        detected_port = ports[0]

            files.append(rel)
            file_infos.append({
                "path": rel,
                "language": lang,
                "lines": lines,
                "size_bytes": stat.st_size,
                "symbols": [s.id if hasattr(s, "id") else s for s in file_symbols],
                "imports": file_imports,
                "module_doc": module_doc,
            })
            for sym in file_symbols:
                symbols.append(to_dict(sym) if hasattr(sym, "id") else sym)

    # Determine primary language
    primary_language = None
    if language_counts:
        primary_language = max(language_counts, key=language_counts.get)

    metrics = {
        "files": len(files),
        "lines": total_lines,
        "size_bytes": total_size,
        "languages": dict(language_counts),
    }

    return {
        "files": files,
        "metrics": metrics,
        "language": primary_language,
        "framework": detected_framework,
        "port": detected_port,
        "_file_infos": file_infos,
        "_symbols": symbols,
    }


def merge_component_into_baseline(
    baseline: dict,
    component_id: str,
    new_data: dict,
) -> dict:
    """Merge rescanned component data back into the baseline.

    .. deprecated::
        Use ``ArchitectureScanner(scope_paths=..., baseline=...)`` instead.

    Replaces the component's files and metrics in the baseline tree.
    Updates the architecture-level files and symbols lists.
    Preserves structural fields (children, type, name, path, docs, config_files).
    """
    warnings.warn(
        "merge_component_into_baseline() is deprecated. Use "
        "ArchitectureScanner with scope_paths and baseline parameters instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    comp = _find_component_in_tree(
        baseline.get("components", []), component_id
    )
    if comp is None:
        return baseline

    old_files = set(comp.get("files", []))

    # Update component fields
    comp["files"] = new_data["files"]
    comp["metrics"] = new_data["metrics"]
    if new_data.get("language"):
        comp["language"] = new_data["language"]
    if new_data.get("framework"):
        comp["framework"] = new_data["framework"]
    if new_data.get("port") is not None:
        comp["port"] = new_data["port"]

    # Update architecture-level files list
    baseline["files"] = [
        f for f in baseline.get("files", [])
        if f.get("path") not in old_files
    ]
    baseline["files"].extend(new_data.get("_file_infos", []))

    # Update architecture-level symbols list
    baseline["symbols"] = [
        s for s in baseline.get("symbols", [])
        if s.get("file") not in old_files
    ]
    baseline["symbols"].extend(new_data.get("_symbols", []))

    return baseline


# ------------------------------------------------------------------
# K.3: Incremental relationship detection
# ------------------------------------------------------------------

def _resolve_import_from_baseline(
    import_name: str,
    source_file: str,
    comp_paths: list[tuple[str, str]],
    comp_names: dict[str, str],
) -> Optional[str]:
    """Resolve an import to a component ID using baseline data.

    Mirrors ArchitectureScanner._resolve_import_to_component but works
    against flat lists instead of the scanner's internal _component_map.

    comp_paths: [(path, component_id), ...] sorted deepest first
    comp_names: {normalized_name: component_id}
    """
    if import_name.startswith("."):
        # Relative import: resolve path
        source_dir = os.path.dirname(source_file)
        parts = import_name.split("/")
        current = source_dir
        for part in parts:
            if part == ".":
                continue
            elif part == "..":
                current = os.path.dirname(current)
            else:
                current = os.path.join(current, part) if current else part
        return _find_component_for_file_from_baseline(current, comp_paths)

    # Absolute import: match against component names/paths
    import_lower = import_name.lower().replace("-", "").replace("_", "")
    if import_lower in comp_names:
        return comp_names[import_lower]

    # Check directory basenames
    for comp_path, comp_id in comp_paths:
        if comp_path and os.path.basename(comp_path).lower() == import_name.lower():
            return comp_id

    return None


def _build_comp_name_index(baseline: dict) -> dict[str, str]:
    """Build a normalized component name -> ID index."""
    result = {}

    def _walk(components):
        for comp in components:
            name = comp.get("name", "").lower().replace("-", "").replace("_", "")
            if name:
                result[name] = comp.get("id", "")
            _walk(comp.get("children", []))

    _walk(baseline.get("components", []))
    return result


def redetect_relationships(
    baseline: dict,
    affected_ids: set[str],
    root: Path,
) -> list[dict]:
    """Re-detect relationships for affected components.

    .. deprecated::
        Use ``ArchitectureScanner(scope_paths=..., baseline=...)`` instead.
        This function only runs 2 of 11 relationship strategies.

    Preserves relationships between unaffected components. Removes all
    relationships where source OR target is affected, then re-detects
    import-based and port-based relationships for those components.
    """
    warnings.warn(
        "redetect_relationships() is deprecated. Use ArchitectureScanner "
        "with scope_paths and baseline parameters instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Preserve unaffected relationships
    preserved = [
        rel for rel in baseline.get("relationships", [])
        if rel.get("source") not in affected_ids
        and rel.get("target") not in affected_ids
    ]

    # Build indexes for import resolution
    comp_paths = _all_component_paths_flat(baseline)
    comp_names = _build_comp_name_index(baseline)

    # Build file-to-imports index from baseline files
    file_imports: dict[str, list[str]] = {}
    for f in baseline.get("files", []):
        file_imports[f.get("path", "")] = f.get("imports", [])

    # Build component -> files index
    comp_files: dict[str, list[str]] = {}

    def _index_files(components):
        for comp in components:
            comp_files[comp.get("id", "")] = comp.get("files", [])
            _index_files(comp.get("children", []))

    _index_files(baseline.get("components", []))

    # Content component IDs (should not participate in relationships)
    content_ids = set()

    def _find_content(components):
        for comp in components:
            if comp.get("type") == "content":
                content_ids.add(comp.get("id", ""))
            _find_content(comp.get("children", []))

    _find_content(baseline.get("components", []))

    # Re-detect import-based relationships for affected components
    new_rels = []
    seen = {(r.get("source"), r.get("target"), r.get("type")) for r in preserved}

    for comp_id in affected_ids:
        if comp_id in content_ids:
            continue
        for fpath in comp_files.get(comp_id, []):
            for imp in file_imports.get(fpath, []):
                target_id = _resolve_import_from_baseline(
                    imp, fpath, comp_paths, comp_names
                )
                if (target_id and target_id != comp_id
                        and target_id not in content_ids):
                    key = (comp_id, target_id, "import")
                    if key not in seen:
                        seen.add(key)
                        new_rels.append({
                            "source": comp_id,
                            "target": target_id,
                            "type": "import",
                            "label": imp,
                        })

    # Re-detect port-based relationships involving affected components
    # Build port map: port -> component
    port_map: dict[int, str] = {}

    def _collect_ports(components):
        for comp in components:
            port = comp.get("port")
            cid = comp.get("id", "")
            if port and cid not in content_ids:
                port_map[port] = cid
            _collect_ports(comp.get("children", []))

    _collect_ports(baseline.get("components", []))

    # For affected components that have ports, scan other components' files
    # for references to those ports
    for comp_id in affected_ids:
        comp = _find_component_in_tree(
            baseline.get("components", []), comp_id
        )
        if not comp:
            continue
        comp_port = comp.get("port")
        if not comp_port:
            continue

        # Scan non-affected components' files for references to this port
        for other_id, other_files in comp_files.items():
            if other_id == comp_id or other_id in content_ids:
                continue
            for fpath in other_files:
                full_path = root / fpath
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                port_str = str(comp_port)
                if port_str not in content:
                    continue
                patterns = [
                    rf"localhost:{port_str}\b",
                    rf"127\.0\.0\.1:{port_str}\b",
                    rf"0\.0\.0\.0:{port_str}\b",
                    rf"""[\"']https?://[^\"']*:{port_str}\b""",
                    rf"(?:PORT|port)\s*[=:]\s*{port_str}\b",
                ]
                for pat in patterns:
                    if re.search(pat, content):
                        key = (other_id, comp_id, "http")
                        if key not in seen:
                            seen.add(key)
                            new_rels.append({
                                "source": other_id,
                                "target": comp_id,
                                "type": "http",
                                "port": comp_port,
                                "protocol": "HTTP",
                                "label": f"port {comp_port}",
                                "bidirectional": True,
                            })
                        break

    # For affected components' files, scan for references to other components' ports
    for comp_id in affected_ids:
        if comp_id in content_ids:
            continue
        for fpath in comp_files.get(comp_id, []):
            full_path = root / fpath
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for port, target_id in port_map.items():
                if target_id == comp_id:
                    continue
                port_str = str(port)
                if port_str not in content:
                    continue
                patterns = [
                    rf"localhost:{port_str}\b",
                    rf"127\.0\.0\.1:{port_str}\b",
                    rf"0\.0\.0\.0:{port_str}\b",
                    rf"""[\"']https?://[^\"']*:{port_str}\b""",
                    rf"(?:PORT|port)\s*[=:]\s*{port_str}\b",
                ]
                for pat in patterns:
                    if re.search(pat, content):
                        key = (comp_id, target_id, "http")
                        if key not in seen:
                            seen.add(key)
                            new_rels.append({
                                "source": comp_id,
                                "target": target_id,
                                "type": "http",
                                "port": port,
                                "protocol": "HTTP",
                                "label": f"port {port}",
                                "bidirectional": True,
                            })
                        break

    return preserved + new_rels


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
