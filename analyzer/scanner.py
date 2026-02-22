"""Core architecture scanner that discovers components, files, and relationships."""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config_parsers import (
    parse_cargo_toml,
    parse_docker_compose,
    parse_gemfile,
    parse_info_plist,
    parse_package_json,
    parse_pyproject_toml,
    parse_sam_template,
    parse_serverless_yml,
)
from .constants import (
    CODE_LANGUAGES,
    COMPONENT_MARKERS,
    CONTENT_DIR_NAMES,
    CONTENT_EXTENSIONS,
    EXTERNAL_CLOUD_APIS,
    HTTP_CLIENT_PATTERNS,
    LANGUAGE_MAP,
    SKIP_DIRS,
    SKIP_EXTENSIONS,
    URL_EXTRACTION_PATTERNS,
    WATCH_CONNECTIVITY_IMPORTS,
)
from .models import (
    Architecture,
    Component,
    ComponentDoc,
    FileInfo,
    Relationship,
    Symbol,
    to_dict,
)
from .parsers import PARSERS
from .swiftui_flow import SwiftUIFlowDetector
from .utils import (
    _framework_priority,
    _is_vendored_repo,
    _name_from_server_script,
    _should_skip_dir,
)


class ArchitectureScanner:
    """Scan a project directory to build a complete architecture model.

    Discovers components by directory structure, parses source files for
    symbols and imports, detects frameworks, and infers relationships
    between components.
    """

    def __init__(self, root: Path, max_file_size: int = 500_000,
                 max_symbols: int = 0, preview_lines: int = 5,
                 scope_paths: Optional[list[str]] = None,
                 baseline: Optional[dict] = None):
        if scope_paths is not None and baseline is None:
            raise ValueError("scope_paths requires a baseline dict")
        self.root = root.resolve()
        self.max_file_size = max_file_size
        self.max_symbols = max_symbols
        self.preview_lines = preview_lines
        self._scope_paths = scope_paths
        self._baseline = baseline
        self._scoped_component_ids: set[str] = set()
        self.architecture = Architecture(
            name=self.root.name,
            description="",
            root_path=str(self.root),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._all_files: list[FileInfo] = []
        self._all_symbols: list[Symbol] = []
        self._component_map: dict[str, Component] = {}
        self._language_counts: dict[str, int] = defaultdict(int)
        self._vendored_paths: set[str] = set()
        self._total_lines = 0
        self._total_size = 0

    def scan(self) -> Architecture:
        """Run the full scan pipeline."""
        # Compute scoped component IDs if in scoped mode
        if self._scope_paths is not None:
            self._compute_scoped_components()

        # Phase 1: Discover components (or load from baseline in scoped mode)
        self._discover_components()

        # Phase 2: Scan files and extract symbols
        self._scan_files()

        # Phase 2.5: Promote generic types to architectural roles
        self._promote_component_types()

        # Phase 2.6: Improve component names after type promotion
        self._improve_component_names()

        # Phase 2.7: Assign ports to server components (after types are finalized)
        self._assign_server_ports()

        # Phase 2.8: Detect UI flows (screens, tabs, navigation)
        self._detect_ui_flows()

        # Phase 3: Detect relationships
        self._detect_relationships()

        # Phase 4: Compute metrics
        self._compute_metrics()

        # Phase 5: Detect project-level info
        self._detect_project_info()

        # Phase 6: Extract documentation for every component
        self._extract_component_docs()

        # Assemble
        self.architecture.components = self._build_component_tree()
        self.architecture.files = [to_dict(f) for f in self._all_files]

        # Limit symbols if needed, prioritizing public types
        symbols = self._all_symbols
        if self.max_symbols > 0 and len(symbols) > self.max_symbols:
            # Prioritize: public types > private types > functions
            priority = {"class": 0, "struct": 0, "enum": 0, "protocol": 0,
                        "trait": 0, "interface": 0, "actor": 0,
                        "type": 1, "component": 1, "impl": 2, "extension": 2,
                        "function": 3}
            symbols = sorted(symbols, key=lambda s: (
                priority.get(s.kind, 5),
                0 if s.visibility == "public" else 1,
                s.file,
            ))[:self.max_symbols]
        self.architecture.symbols = [to_dict(s) for s in symbols]
        self.architecture.stats = {
            "total_files": len(self._all_files),
            "total_lines": self._total_lines,
            "total_size_bytes": self._total_size,
            "languages": dict(self._language_counts),
            "total_symbols": len(self._all_symbols),
            "total_components": len(self._component_map),
            "total_relationships": len(self.architecture.relationships),
        }

        return self.architecture

    def _should_skip(self, path: Path) -> bool:
        """Check if a path should be skipped."""
        if path.name in SKIP_DIRS:
            return True
        if path.suffix.lower() in SKIP_EXTENSIONS:
            return True
        if path.name.startswith(".") and path.is_dir():
            return True
        return False

    def _load_baseline_components(self) -> None:
        """Hydrate _component_map from a baseline dict instead of filesystem discovery.

        For non-scoped components, also restores their files list. For scoped
        components, leaves files empty (will be repopulated by _scan_files).
        """
        ui_types = {"screen", "tab-container", "tab", "feature-group"}

        def _walk(components: list[dict]) -> None:
            for comp_dict in components:
                path = comp_dict.get("path", "")
                comp_id = comp_dict.get("id", "")
                comp = Component(
                    id=comp_id,
                    name=comp_dict.get("name", ""),
                    type=comp_dict.get("type", "module"),
                    path=path,
                    language=comp_dict.get("language"),
                    framework=comp_dict.get("framework"),
                    description=comp_dict.get("description"),
                    port=comp_dict.get("port"),
                )
                comp.config_files = list(comp_dict.get("config_files", []))
                comp.docs = dict(comp_dict.get("docs", {})) if comp_dict.get("docs") else {}
                comp.metrics = dict(comp_dict.get("metrics", {})) if comp_dict.get("metrics") else {}
                comp.external_services = list(comp_dict.get("external_services", []))
                comp.entry_points = list(comp_dict.get("entry_points", []))

                # Non-scoped components keep their baseline files
                if comp_id not in self._scoped_component_ids:
                    comp.files = list(comp_dict.get("files", []))

                # Detect vendored paths from baseline (library type at non-root)
                if comp.type == "library" and path:
                    self._vendored_paths.add(path)

                self._component_map[path] = comp

                # Process children: separate UI synthetic children from path-based
                for child_dict in comp_dict.get("children", []):
                    child_type = child_dict.get("type", "")
                    if child_type in ui_types:
                        # Restore UI children as Component objects on parent.children
                        ui_child = self._restore_ui_component(child_dict)
                        comp.children.append(ui_child)
                    else:
                        # Path-based children go into _component_map
                        _walk([child_dict])

        _walk(self._baseline.get("components", []))

    def _restore_ui_component(self, comp_dict: dict) -> Component:
        """Recursively restore a synthetic UI component from a baseline dict."""
        comp = Component(
            id=comp_dict.get("id", ""),
            name=comp_dict.get("name", ""),
            type=comp_dict.get("type", "screen"),
            path=comp_dict.get("path", ""),
            language=comp_dict.get("language"),
            framework=comp_dict.get("framework"),
        )
        comp.files = list(comp_dict.get("files", []))
        comp.metrics = dict(comp_dict.get("metrics", {})) if comp_dict.get("metrics") else {}
        for child_dict in comp_dict.get("children", []):
            comp.children.append(self._restore_ui_component(child_dict))
        return comp

    def _discover_components(self):
        """Walk the tree and identify component boundaries."""
        # In scoped mode, load from baseline instead of filesystem discovery
        if self._scope_paths is not None and self._baseline is not None:
            self._load_baseline_components()
            return

        # Root is always a component
        root_comp = Component(
            id=self._make_component_id(""),
            name=self.root.name,
            type="project",
            path="",
        )
        self._component_map[""] = root_comp

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter directories
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

            rel = os.path.relpath(dirpath, self.root)
            if rel == ".":
                rel = ""

            # Detect vendored third-party repos and prevent recursion into them.
            # Create a single "library" component for the vendored repo instead.
            if rel and _is_vendored_repo(dirpath):
                comp_id = self._make_component_id(rel)
                if comp_id not in self._component_map:
                    self._component_map[rel] = Component(
                        id=comp_id,
                        name=os.path.basename(dirpath),
                        type="library",
                        path=rel,
                    )
                self._vendored_paths.add(rel)
                dirnames.clear()  # Don't recurse into vendored code
                continue

            for marker, (lang, comp_type) in COMPONENT_MARKERS.items():
                if marker in filenames:
                    comp_id = self._make_component_id(rel)
                    if comp_id not in self._component_map:
                        name = os.path.basename(dirpath) if rel else self.root.name
                        comp = Component(
                            id=comp_id,
                            name=name,
                            type=comp_type,
                            path=rel,
                            language=lang,
                        )
                        # Parse config files for metadata
                        marker_path = Path(dirpath) / marker
                        if marker == "package.json":
                            info = parse_package_json(marker_path)
                            comp.name = info.get("name", comp.name)
                            comp.description = info.get("description", "")
                            comp.config_files.append({"type": "package.json", "path": os.path.join(rel, marker)})
                        elif marker == "Cargo.toml":
                            info = parse_cargo_toml(marker_path)
                            comp.name = info.get("name", comp.name) or comp.name
                            comp.config_files.append({"type": "Cargo.toml", "path": os.path.join(rel, marker)})
                        elif marker == "pyproject.toml":
                            info = parse_pyproject_toml(marker_path)
                            comp.name = info.get("name", comp.name) or comp.name
                            comp.config_files.append({"type": "pyproject.toml", "path": os.path.join(rel, marker)})
                        elif marker in ("docker-compose.yml", "docker-compose.yaml"):
                            info = parse_docker_compose(marker_path)
                            # Use service names for a better component description
                            svc_names = info.get("services", [])
                            if svc_names:
                                comp.description = f"Services: {', '.join(svc_names)}"
                            # Assign port from docker-compose (primary service port)
                            dc_ports = info.get("ports", [])
                            if dc_ports and not comp.port:
                                comp.port = dc_ports[0].get("host")
                            comp.config_files.append({"type": "docker-compose", "path": os.path.join(rel, marker), **info})
                        elif marker == "Info.plist":
                            comp.type = "application"
                            info = parse_info_plist(marker_path)
                            if info.get("name"):
                                comp.name = info["name"]
                            comp.config_files.append({"type": "Info.plist", "path": os.path.join(rel, marker)})
                        elif marker == "Gemfile":
                            info = parse_gemfile(marker_path)
                            if info.get("name"):
                                comp.name = info["name"]
                            comp.config_files.append({"type": "Gemfile", "path": os.path.join(rel, marker)})
                        elif marker in ("template.yaml", "template.yml"):
                            info = parse_sam_template(marker_path)
                            if info.get("functions"):
                                comp.type = "api-server"
                                fn_names = [f["name"] for f in info["functions"]]
                                comp.description = f"AWS SAM: {', '.join(fn_names)}"
                                # Derive a name from the directory or function names
                                if len(fn_names) == 1:
                                    comp.name = fn_names[0]
                            comp.config_files.append({"type": "sam-template", "path": os.path.join(rel, marker), **info})
                        elif marker in ("serverless.yml", "serverless.yaml"):
                            info = parse_serverless_yml(marker_path)
                            if info.get("functions"):
                                comp.type = "api-server"
                                fn_names = [f["name"] for f in info["functions"]]
                                comp.description = f"Serverless: {', '.join(fn_names)}"
                            comp.config_files.append({"type": "serverless", "path": os.path.join(rel, marker), **info})

                        self._component_map[rel] = comp
                        break

        # Also create intermediate directory components for significant directories
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            rel = os.path.relpath(dirpath, self.root)
            if rel == ".":
                rel = ""

            # Skip directories under vendored repos
            if self._is_under_vendored(rel):
                dirnames.clear()
                continue

            # Count code files in this directory
            code_files = [f for f in filenames if Path(f).suffix.lower() in LANGUAGE_MAP]
            if len(code_files) >= 2 and rel and rel not in self._component_map:
                # Check depth - only create for meaningful groupings
                depth = rel.count(os.sep)
                if depth <= 4:
                    parent_id = self._find_parent_component(rel)
                    if parent_id is not None:
                        self._component_map[rel] = Component(
                            id=self._make_component_id(rel),
                            name=os.path.basename(rel),
                            type="module",
                            path=rel,
                        )

    def _is_under_vendored(self, rel_path: str) -> bool:
        """Check if a path is inside a vendored third-party repo."""
        for vp in self._vendored_paths:
            if rel_path.startswith(vp + os.sep):
                return True
        return False

    def _compute_scoped_components(self) -> None:
        """Identify which component IDs fall within scope_paths."""
        if not self._scope_paths or not self._baseline:
            return

        def _walk(components: list[dict]) -> None:
            for comp in components:
                comp_path = comp.get("path", "")
                comp_id = comp.get("id", "")
                for sp in self._scope_paths:
                    if (comp_path == sp
                            or comp_path.startswith(sp + "/")
                            or sp.startswith(comp_path + "/")
                            or (sp == "" and comp_path == "")):
                        self._scoped_component_ids.add(comp_id)
                        break
                _walk(comp.get("children", []))

        _walk(self._baseline.get("components", []))

    def _restore_baseline_files(self) -> None:
        """Restore file info and symbols for non-scoped components from baseline."""
        if not self._baseline:
            return

        # Restore files from baseline that belong to non-scoped components
        for f in self._baseline.get("files", []):
            fpath = f.get("path", "")
            file_comp = self._find_component_for_file(fpath)
            if file_comp and file_comp.id in self._scoped_component_ids:
                continue  # Will be re-scanned from disk

            file_info = FileInfo(
                path=fpath,
                language=f.get("language", ""),
                lines=f.get("lines", 0),
                size_bytes=f.get("size_bytes", 0),
                symbols=list(f.get("symbols", [])),
                imports=list(f.get("imports", [])),
                module_doc=f.get("module_doc"),
            )
            self._all_files.append(file_info)
            self._total_lines += file_info.lines
            self._total_size += file_info.size_bytes
            if file_info.language:
                self._language_counts[file_info.language] += file_info.lines

        # Restore symbols for non-scoped files
        for s in self._baseline.get("symbols", []):
            s_file = s.get("file", "")
            file_comp = self._find_component_for_file(s_file)
            if file_comp and file_comp.id in self._scoped_component_ids:
                continue  # Will be re-extracted from disk

            sym = Symbol(
                id=s.get("id", ""),
                name=s.get("name", ""),
                kind=s.get("kind", ""),
                file=s_file,
                line=s.get("line", 0),
                end_line=s.get("end_line", 0),
                code_preview=s.get("code_preview", ""),
                visibility=s.get("visibility", "internal"),
                docstring=s.get("docstring"),
                parent=s.get("parent"),
            )
            self._all_symbols.append(sym)

    def _scan_files(self):
        """Scan all code files and extract symbols."""
        # In scoped mode, restore non-scoped data from baseline first
        if self._scope_paths is not None and self._baseline is not None:
            self._restore_baseline_files()

        # Determine directories to walk
        if self._scope_paths is not None:
            walk_roots = []
            for sp in self._scope_paths:
                walk_root = self.root / sp if sp else self.root
                if walk_root.is_dir():
                    walk_roots.append(walk_root)
        else:
            walk_roots = [self.root]

        for walk_root in walk_roots:
            for dirpath, dirnames, filenames in os.walk(walk_root):
                dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

                # Skip vendored directories
                rel_dir = os.path.relpath(dirpath, self.root)
                if rel_dir != "." and self._is_under_vendored(rel_dir):
                    dirnames.clear()
                    continue

                for fname in sorted(filenames):
                    fpath = Path(dirpath) / fname
                    if self._should_skip(fpath):
                        continue

                    ext = fpath.suffix.lower()
                    lang = LANGUAGE_MAP.get(ext)
                    if not lang:
                        continue

                    try:
                        stat = fpath.stat()
                        if stat.st_size > self.max_file_size:
                            continue
                        if stat.st_size == 0:
                            continue
                    except OSError:
                        continue

                    rel = os.path.relpath(fpath, self.root)
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue

                    lines = content.count("\n") + 1
                    self._total_lines += lines
                    self._total_size += stat.st_size
                    self._language_counts[lang] += lines

                    # Parse symbols
                    parser = PARSERS.get(lang)
                    symbols = []
                    imports = []
                    if parser:
                        symbols = parser.extract_symbols(content, rel)
                        imports = parser.extract_imports(content)

                        # Detect framework at file level.
                        # Platform-specific frameworks (AppKit, UIKit, Vapor) take
                        # priority over cross-platform ones (SwiftUI).
                        fw = parser.detect_framework(content)
                        if fw:
                            comp = self._find_component_for_file(rel)
                            if comp:
                                if not comp.framework:
                                    comp.framework = fw
                                elif _framework_priority(fw) > _framework_priority(comp.framework):
                                    comp.framework = fw

                        # Detect ports (only in code files, not docs/config)
                        # Only assign to server-type components to avoid client code
                        if lang in CODE_LANGUAGES:
                            ports = parser.detect_ports(content)
                            if ports:
                                comp = self._find_component_for_file(rel)
                                if comp and not comp.port:
                                    # Only assign ports to server-type components
                                    server_types = {"api-server", "service", "infrastructure"}
                                    if comp.type in server_types:
                                        comp.port = ports[0]

                    # Extract file-level documentation
                    module_doc = None
                    if parser:
                        module_doc = parser.extract_file_doc(content)

                    file_info = FileInfo(
                        path=rel,
                        language=lang,
                        lines=lines,
                        size_bytes=stat.st_size,
                        symbols=[s.id for s in symbols],
                        imports=imports,
                        module_doc=module_doc,
                    )

                    self._all_files.append(file_info)
                    self._all_symbols.extend(symbols)

                    # Associate file with component
                    comp = self._find_component_for_file(rel)
                    if comp:
                        comp.files.append(rel)

    # ------------------------------------------------------------------
    # Phase 2.5: Promote generic types to architectural roles
    # ------------------------------------------------------------------

    def _promote_component_types(self):
        """Promote generic component types (package, module) to specific
        architectural roles (mobile-client, api-server, etc.) using
        framework detection, dependency analysis, and directory heuristics."""
        for rel_path, comp in self._component_map.items():
            # In scoped mode, skip non-scoped components (types already correct)
            if self._scope_paths is not None and comp.id not in self._scoped_component_ids:
                continue
            # Skip root for content detection but still promote its type
            if rel_path:
                if self._is_content_only(comp, rel_path):
                    comp.type = "content"
                    continue
            promoted = self._classify_architectural_role(comp, rel_path)
            if promoted:
                comp.type = promoted

        # Post-promotion pass: demote hero components that are actually wrappers
        # containing diverse hero children. A monorepo root with Package.swift
        # might be classified as ios-client, but if it also contains api-servers
        # and web-clients, it's really a project wrapper.
        hero_types = {
            "ios-client", "android-client", "mobile-client", "web-client",
            "api-server", "watch-app", "desktop-app", "cli-tool", "service",
        }
        for rel_path, comp in self._component_map.items():
            if comp.type not in hero_types:
                continue
            # Collect hero types from direct children and all descendants.
            # Exclude subordinate directories (tests, static, etc.) since those
            # are part of the parent component, not independent heroes.
            subordinate_dirs = {
                "tests", "test", "spec", "specs", "__tests__",
                "static", "public", "dist", "build", "assets",
            }
            direct_child_hero_types: set[str] = set()
            descendant_hero_types: set[str] = set()
            prefix = (rel_path + os.sep) if rel_path else ""
            for child_path, child_comp in self._component_map.items():
                if not child_path or child_path == rel_path:
                    continue
                if prefix and not child_path.startswith(prefix):
                    continue
                child_dirname = os.path.basename(child_path).lower()
                if child_dirname in subordinate_dirs:
                    continue
                if not prefix:
                    # Root: direct children have no separator
                    is_direct = os.sep not in child_path
                else:
                    is_direct = child_path[len(prefix):].count(os.sep) == 0
                if child_comp.type in hero_types:
                    descendant_hero_types.add(child_comp.type)
                    if is_direct:
                        direct_child_hero_types.add(child_comp.type)
            # Demote if direct children have 2+ different hero types (clear wrapper).
            # Also demote if descendants have 3+ different hero types AND this
            # component has few direct files (monorepo root pattern).
            other_direct = direct_child_hero_types - {comp.type}
            other_all = descendant_hero_types - {comp.type}
            if len(other_direct) >= 2:
                comp.type = "package"
            elif len(other_all) >= 3 and len(comp.files) <= 25:
                comp.type = "package"

    def _is_content_only(self, comp: Component, rel_path: str) -> bool:
        """Determine if a component is a content-only directory."""
        dir_name = os.path.basename(rel_path).lower()

        if dir_name in CONTENT_DIR_NAMES:
            code_exts = set(LANGUAGE_MAP.keys()) - CONTENT_EXTENSIONS
            code_files = [f for f in comp.files
                          if Path(f).suffix.lower() in code_exts]
            total = len(comp.files)
            if total == 0 or len(code_files) / max(total, 1) < 0.2:
                return True

        if comp.files:
            content_count = sum(
                1 for f in comp.files
                if Path(f).suffix.lower() in CONTENT_EXTENSIONS
            )
            if content_count / len(comp.files) > 0.8:
                return True

        return False

    def _classify_architectural_role(self, comp: Component, rel_path: str) -> Optional[str]:
        """Classify a component into a specific architectural role."""
        framework = (comp.framework or "").lower()
        comp_dir = self.root / rel_path
        dir_name = os.path.basename(rel_path).lower()

        # Gather marker file signals
        has_info_plist = (comp_dir / "Info.plist").exists()
        has_xcodeproj = any(
            p.suffix == ".xcodeproj" for p in comp_dir.iterdir() if p.is_dir()
        ) if comp_dir.is_dir() else False
        # Also check parent for .xcodeproj (common iOS layout where code
        # dir sits beside the xcodeproj). Only check direct parent, not root,
        # to avoid false positives for nested Swift packages. Skip if this
        # component has its own Package.swift (it's a library, not an app).
        has_package_swift = (comp_dir / "Package.swift").exists()
        if not has_xcodeproj and comp.language == "swift" and not has_package_swift:
            parent_dir = comp_dir.parent
            if parent_dir.is_dir() and parent_dir != self.root:
                has_xcodeproj = any(
                    p.suffix == ".xcodeproj" for p in parent_dir.iterdir()
                    if p.is_dir()
                )
        has_android_manifest = (
            (comp_dir / "AndroidManifest.xml").exists()
            or (comp_dir / "src" / "main" / "AndroidManifest.xml").exists()
        )
        has_build_gradle = (
            (comp_dir / "build.gradle").exists()
            or (comp_dir / "build.gradle.kts").exists()
        )
        has_package_json = (comp_dir / "package.json").exists()
        has_cargo_toml = (comp_dir / "Cargo.toml").exists()
        has_pubspec = (comp_dir / "pubspec.yaml").exists()

        # Read dependency lists from config files
        pkg_deps: set[str] = set()
        if has_package_json:
            info = parse_package_json(comp_dir / "package.json")
            pkg_deps = set(info.get("dependencies", []))

        cargo_deps: set[str] = set()
        if has_cargo_toml:
            info = parse_cargo_toml(comp_dir / "Cargo.toml")
            cargo_deps = set(info.get("dependencies", []))

        # --- Watch app ---
        if "watch" in dir_name:
            if comp.language == "swift" or framework in ("swiftui", "watchkit"):
                return "watch-app"

        # --- macOS desktop app ---
        # Must check before iOS: AppKit is macOS-only, SwiftUI is cross-platform.
        # Also detect macOS-specific SwiftUI APIs (MenuBarExtra, NSApplication, etc.)
        if framework == "appkit":
            return "desktop-app"
        if framework == "swiftui":
            # Check for macOS-specific SwiftUI APIs in any Swift file owned by
            # this component. Don't require comp.language == "swift" since mixed-
            # content directories (e.g., docs + code) may have a different primary
            # language.
            macos_indicators = {"MenuBarExtra", "NSApplication", "NSWindow",
                                "NSStatusBar", ".menuBarExtraStyle"}
            for fpath in comp.files:
                if not fpath.endswith(".swift"):
                    continue
                try:
                    fc = (self.root / fpath).read_text(encoding="utf-8", errors="replace")
                    if any(ind in fc for ind in macos_indicators):
                        return "desktop-app"
                except OSError:
                    continue

        # --- iOS client ---
        if framework in ("swiftui", "uikit"):
            if has_info_plist or has_xcodeproj or comp.type == "application":
                return "ios-client"

        # --- Android client ---
        if has_android_manifest:
            return "android-client"
        if has_build_gradle and comp.language in ("java", "kotlin"):
            if has_android_manifest or "android" in dir_name:
                return "android-client"

        # --- Mobile client: React Native (cross-platform) ---
        if "react-native" in pkg_deps:
            return "mobile-client"

        # --- Mobile client: Flutter (cross-platform) ---
        if has_pubspec:
            try:
                content = (comp_dir / "pubspec.yaml").read_text(errors="replace")
                if "flutter:" in content:
                    return "mobile-client"
            except OSError:
                pass

        # --- Desktop app (Electron / other) ---
        # Note: AppKit-based desktop apps are handled earlier (before iOS check).
        if framework == "electron":
            return "desktop-app"
        if "electron" in pkg_deps:
            return "desktop-app"

        # --- API server: framework detection ---
        server_frameworks = {
            "axum", "actix", "rocket", "warp", "vapor",
            "express", "fastify", "hono", "koa", "nestjs",
            "flask", "django", "fastapi", "starlette", "aiohttp",
            "tornado", "gin", "echo", "fiber", "chi", "gorilla", "beego",
            "rails", "sinatra", "grape", "hanami",
        }
        if framework in server_frameworks:
            return "api-server"

        # --- API server: JS/TS deps (pure server, no client framework) ---
        pure_server_deps = {
            "express", "fastify", "hono", "koa", "@nestjs/core",
        }
        client_deps = {"react", "vue", "svelte", "@angular/core"}
        if pkg_deps & pure_server_deps and not (pkg_deps & client_deps):
            return "api-server"

        # --- API server: Rust deps ---
        rust_server_deps = {"axum", "actix-web", "rocket", "warp"}
        if cargo_deps & rust_server_deps:
            return "api-server"

        # --- API server: Ruby deps ---
        has_gemfile = (comp_dir / "Gemfile").exists()
        if has_gemfile:
            gem_info = parse_gemfile(comp_dir / "Gemfile")
            ruby_deps = set(gem_info.get("dependencies", []))
            ruby_server_deps = {"rails", "sinatra", "grape", "hanami", "roda"}
            if ruby_deps & ruby_server_deps:
                return "api-server"

        # --- Service: standalone server scripts ---
        # Detect directories containing explicitly-named server files (e.g.,
        # log_server.py, gateway.py) that import HTTP server modules, even in
        # utility directories that would otherwise be excluded.
        # Check Python files regardless of component's primary language (e.g.,
        # scripts/ may have Gemfile but contain Python server scripts).
        # Skip test directories since test_server.py files test servers, not run them.
        test_dir_names = {"tests", "test", "spec", "specs", "__tests__",
                          "testing", "test_suite", "e2e", "integration"}
        python_files = [f for f in comp.files if f.endswith('.py')]
        if python_files and dir_name not in test_dir_names:
            server_file_patterns = re.compile(
                r'(?:^|/)(?:.*server.*|.*gateway.*|.*daemon.*)\.py$', re.I)
            server_imports = {
                "http.server", "aiohttp", "flask", "fastapi", "tornado",
                "uvicorn", "gunicorn", "starlette", "socketserver",
            }
            for fpath in python_files:
                if server_file_patterns.search(fpath):
                    try:
                        content = (self.root / fpath).read_text(
                            encoding="utf-8", errors="replace")
                        for srv_import in server_imports:
                            if (f"import {srv_import}" in content
                                    or f"from {srv_import}" in content):
                                # Also extract port from the server file
                                if not comp.port:
                                    port_match = re.search(
                                        r'(?:default|port)["\']?\s*[:=]\s*(\d{4,5})',
                                        content, re.I)
                                    if port_match:
                                        comp.port = int(port_match.group(1))
                                # Derive a better name from the server script
                                # when the component has a generic folder name
                                if comp.name == dir_name:
                                    comp.name = _name_from_server_script(fpath, content)
                                return "service"
                    except OSError:
                        pass

        # --- API server: port + server language + no client signals ---
        # Only for languages that are typically server-side. Swift/Kotlin/Java
        # mobile code often references ports as API clients, not servers.
        # Also exclude utility/build directories that may reference ports in scripts.
        utility_dir_names = {"scripts", "bin", "tools", "utils", "ci", "build", "devops", "deploy"}
        server_languages = {"python", "rust", "go", "ruby", "typescript", "javascript"}
        if (comp.port and comp.language in server_languages
                and not (pkg_deps & client_deps)
                and dir_name not in utility_dir_names):
            return "api-server"

        # --- Logging/monitoring service ---
        # Detect logging servers, log collectors, metrics services
        logging_dir_patterns = {"log", "logger", "logging", "logs", "metrics", "monitor", "telemetry", "observability"}
        if dir_name in logging_dir_patterns:
            # Check for server-like characteristics
            if comp.port or comp.language in server_languages:
                return "service"

        # Check for logging framework dependencies
        logging_deps = {
            "winston", "pino", "bunyan", "log4js",  # Node.js
            "loguru", "structlog", "python-json-logger",  # Python
            "slog", "zap", "logrus",  # Go
            "tracing", "log4rs",  # Rust
            "sentry-sdk", "@sentry/node", "datadog", "ddtrace",  # Observability
            "prometheus-client", "prom-client", "opentelemetry",  # Metrics
        }
        if pkg_deps & logging_deps and comp.port:
            return "service"

        # --- Web client ---
        web_client_frameworks = {
            "react", "next.js", "vue", "nuxt", "svelte",
            "sveltekit", "angular",
        }
        if framework in web_client_frameworks:
            return "web-client"

        web_client_deps = {
            "react", "vue", "svelte", "@angular/core",
            "next", "nuxt", "@sveltejs/kit",
        }
        if pkg_deps & web_client_deps:
            return "web-client"

        # --- Admin/dashboard frontend for API servers ---
        # Detect web UIs that are admin panels or dashboards for backend services
        admin_dir_patterns = {"admin", "dashboard", "console", "portal", "ui", "frontend", "web-client", "webclient"}
        if dir_name in admin_dir_patterns:
            # Check for web framework
            if framework in web_client_frameworks or (pkg_deps & web_client_deps):
                return "web-client"
            # Check if it has HTML/JS files suggesting a frontend
            has_frontend_files = any(
                f.endswith(('.html', '.jsx', '.tsx', '.vue', '.svelte'))
                for f in comp.files
            )
            if has_frontend_files:
                return "web-client"

        # --- CLI tool ---
        if comp.language == "python" and framework in ("click", "typer"):
            return "cli-tool"
        rust_cli_deps = {"clap"}
        if cargo_deps & rust_cli_deps and not (cargo_deps & rust_server_deps):
            return "cli-tool"

        return None

    def _improve_component_names(self):
        """Improve component names after type promotion.

        Some components get generic folder-based names during discovery because
        their marker files don't provide names (e.g., Makefile, Dockerfile).
        After type promotion identifies the architectural role, we can try
        harder to find a meaningful name.
        """
        for rel_path, comp in self._component_map.items():
            if not rel_path:
                continue
            if self._scope_paths is not None and comp.id not in self._scoped_component_ids:
                continue
            folder_name = os.path.basename(rel_path)
            # Only improve if the name is still the generic folder name
            if comp.name != folder_name:
                continue

            comp_dir = self.root / rel_path

            # Ruby/Rails apps: try to find the real app name
            if comp.language == "ruby" or (comp.framework and comp.framework.lower() in ("rails", "sinatra", "grape")):
                from .config_parsers import _extract_ruby_app_name
                name = _extract_ruby_app_name(comp_dir)
                if name:
                    comp.name = name
                    continue

            # Python apps: try pyproject.toml or setup.cfg in subtree
            if comp.language == "python":
                for cfg_name in ("pyproject.toml", "setup.cfg", "setup.py"):
                    cfg_path = comp_dir / cfg_name
                    if cfg_path.exists():
                        if cfg_name == "pyproject.toml":
                            info = parse_pyproject_toml(cfg_path)
                        else:
                            continue
                        if info.get("name"):
                            comp.name = info["name"]
                            break

    def _assign_server_ports(self):
        """Second pass for port assignment after component types are finalized.

        During file scanning, we may detect ports but not assign them because
        the component type wasn't known yet. This pass re-scans server components
        to ensure they get their ports assigned.

        Also propagates ports from child components (e.g., cli-tool with server
        subcommand) up to parent server components (e.g., workspace containing
        the CLI and library crates).
        """
        server_types = {"api-server", "service", "infrastructure"}

        # First pass: direct port assignment to server components
        for comp in self._component_map.values():
            if self._scope_paths is not None and comp.id not in self._scoped_component_ids:
                continue
            if comp.port:
                continue  # Already has a port
            if comp.type not in server_types:
                continue  # Not a server type

            # Find files belonging to this component and scan for ports
            for file_info in self._all_files:
                if file_info.language not in CODE_LANGUAGES:
                    continue
                file_comp = self._find_component_for_file(file_info.path)
                if file_comp and file_comp.id == comp.id:
                    # Re-scan this file for ports
                    try:
                        fpath = self.root / file_info.path
                        content = fpath.read_text(encoding="utf-8", errors="replace")
                        parser = PARSERS.get(file_info.language)
                        if parser:
                            ports = parser.detect_ports(content)
                            if ports:
                                comp.port = ports[0]
                                break  # Got a port, done with this component
                    except OSError:
                        continue

        # Second pass: propagate ports from children to parent server components
        # This handles cases like Rust workspaces where the CLI crate defines the
        # port but the parent workspace is the server component.
        for comp in self._component_map.values():
            if comp.port:
                continue  # Already has a port
            if comp.type not in server_types:
                continue  # Not a server type

            # Find child components and scan their files for ports
            for rel_path, child in self._component_map.items():
                if not rel_path:
                    continue
                # Check if this component is a parent of the child
                parent_id = self._find_parent_component(rel_path)
                if parent_id == comp.id:
                    # This is a child of our server component
                    # Scan child's files for ports
                    for file_info in self._all_files:
                        if file_info.language not in CODE_LANGUAGES:
                            continue
                        file_comp = self._find_component_for_file(file_info.path)
                        if file_comp and file_comp.id == child.id:
                            try:
                                fpath = self.root / file_info.path
                                content = fpath.read_text(encoding="utf-8", errors="replace")
                                parser = PARSERS.get(file_info.language)
                                if parser:
                                    ports = parser.detect_ports(content)
                                    if ports:
                                        comp.port = ports[0]
                                        break
                            except OSError:
                                continue
                    if comp.port:
                        break

    def _detect_ui_flows(self):
        """Phase 2.8: Detect UI screens and navigation flows in client apps.

        For each client-type component (ios-client, web-client, etc.), runs the
        appropriate UI flow detector to discover screens, tab structures, and
        navigation relationships. Detected screens become child Components;
        navigation paths become Relationships.

        In scoped mode, runs fully (not skipped) because _component_map is
        complete from baseline and all files exist on disk. The detector
        builds everything from scratch, producing a complete replacement.
        Baseline UI children are cleared first to prevent duplication.
        """
        # In scoped mode, clear baseline UI children so the detector can
        # rebuild them from scratch without creating duplicates.
        ui_types = {"screen", "tab-container", "tab", "feature-group"}
        if self._scope_paths is not None:
            self._ui_relationships = []
            for comp in self._component_map.values():
                comp.children = [
                    c for c in comp.children
                    if not (isinstance(c, Component) and c.type in ui_types)
                ]

        client_types = {
            "ios-client", "android-client", "web-client",
            "mobile-client", "desktop-app", "watch-app",
        }

        # Map frameworks to detectors
        detector_map = {
            "SwiftUI": SwiftUIFlowDetector(),
            "UIKit": SwiftUIFlowDetector(),  # shares some patterns
            "AppKit": SwiftUIFlowDetector(),
        }

        for rel_path, comp in list(self._component_map.items()):
            if comp.type not in client_types:
                continue

            framework = comp.framework or ""
            detector = detector_map.get(framework)
            if not detector:
                continue

            # Gather files from this component AND all its descendants,
            # since UI views span across child modules (e.g., Settings/,
            # Learning/ are separate components but part of the same app UI).
            all_files = set(comp.files)
            for child_path, child_comp in self._component_map.items():
                if child_path and child_path.startswith(rel_path + os.sep):
                    all_files.update(child_comp.files)
            # Temporarily expand comp.files for the detector
            original_files = comp.files
            comp.files = sorted(all_files)

            new_components, new_relationships = detector.detect(comp, self.root)

            # Restore original files
            comp.files = original_files

            if not new_components:
                continue

            # Register new components as children of this component.
            # They use synthetic __ui__ paths so they don't collide with
            # file-path-based component IDs.
            for new_comp in new_components:
                # Only add top-level UI components as direct children.
                # Tab containers and screens not nested under a tab.
                if new_comp.type == "tab-container":
                    comp.children.append(new_comp)
                elif new_comp.type == "screen" and not any(
                    new_comp in tc.children
                    for tc in new_components if tc.type in ("tab", "tab-container")
                ):
                    # Orphan screen (not under any tab), add to component directly
                    comp.children.append(new_comp)

            # Store relationships for later assembly
            self._ui_relationships = getattr(self, "_ui_relationships", [])
            self._ui_relationships.extend(new_relationships)

    def _detect_relationships(self):
        """Detect inter-component relationships."""
        relationships = []
        seen = set()

        # In scoped mode, pre-populate with baseline relationships between
        # non-scoped components. The seen set prevents re-detection of these.
        if self._scope_paths is not None and self._baseline is not None:
            for rel in self._baseline.get("relationships", []):
                src = rel.get("source", "")
                tgt = rel.get("target", "")
                if (src not in self._scoped_component_ids
                        and tgt not in self._scoped_component_ids):
                    relationships.append(Relationship(
                        source=src,
                        target=tgt,
                        type=rel.get("type", "import"),
                        label=rel.get("label"),
                        protocol=rel.get("protocol"),
                        port=rel.get("port"),
                        bidirectional=rel.get("bidirectional", False),
                    ))
                    seen.add((src, tgt, rel.get("type", "")))

        # Content components should not participate in relationships
        content_ids = {comp.id for comp in self._component_map.values()
                       if comp.type == "content"}

        # Build a map of component paths to IDs
        comp_by_path = {}
        for path, comp in self._component_map.items():
            comp_by_path[path] = comp.id

        # Import-based relationships
        for file_info in self._all_files:
            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue

            for imp in file_info.imports:
                # Try to resolve import to a component
                target_comp = self._resolve_import_to_component(imp, file_info.path)
                if (target_comp and target_comp.id != source_comp.id
                        and target_comp.id not in content_ids):
                    key = (source_comp.id, target_comp.id, "import")
                    if key not in seen:
                        seen.add(key)
                        relationships.append(Relationship(
                            source=source_comp.id,
                            target=target_comp.id,
                            type="import",
                            label=imp,
                        ))

        # Port-based relationships (service A calls service B's port)
        port_map = {}  # port -> component
        for comp in self._component_map.values():
            if comp.port and comp.id not in content_ids:
                port_map[comp.port] = comp

        for file_info in self._all_files:
            # Only scan code files for port references, not docs/config
            if file_info.language not in CODE_LANGUAGES:
                continue
            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue

            try:
                fpath = self.root / file_info.path
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Look for references to other services' ports
            for port, target_comp in port_map.items():
                if target_comp.id == source_comp.id:
                    continue
                port_str = str(port)
                if port_str in content:
                    # Verify it's actually a port reference with tight patterns
                    patterns = [
                        rf"localhost:{port_str}\b",
                        rf"127\.0\.0\.1:{port_str}\b",
                        rf"0\.0\.0\.0:{port_str}\b",
                        rf"""[\"']https?://[^\"']*:{port_str}\b""",
                        rf"(?:PORT|port)\s*[=:]\s*{port_str}\b",
                    ]
                    for pat in patterns:
                        if re.search(pat, content):
                            key = (source_comp.id, target_comp.id, "http")
                            if key not in seen:
                                seen.add(key)
                                relationships.append(Relationship(
                                    source=source_comp.id,
                                    target=target_comp.id,
                                    type="http",
                                    port=port,
                                    protocol="HTTP",
                                    label=f"port {port}",
                                    bidirectional=True,
                                ))
                            break

        # Service name-based relationships (from docker-compose, kubernetes, etc.)
        # Build a map of service names to components for matching
        service_name_map = {}  # lowercase name -> component
        for comp in self._component_map.values():
            if comp.id in content_ids:
                continue
            # Use component name (lowercase, hyphenated form) as potential service name
            name_variants = [
                comp.name.lower().replace(" ", "-").replace("_", "-"),
                comp.name.lower().replace(" ", "_").replace("-", "_"),
                comp.name.lower().replace(" ", "").replace("-", "").replace("_", ""),
            ]
            # Also use the directory name as a service name
            if comp.path:
                dir_name = os.path.basename(comp.path).lower()
                name_variants.extend([
                    dir_name,
                    dir_name.replace("-", "_"),
                    dir_name.replace("_", "-"),
                ])
            for variant in name_variants:
                if variant and len(variant) > 2:  # Skip very short names
                    service_name_map[variant] = comp

        # Scan for service name references in code
        for file_info in self._all_files:
            if file_info.language not in CODE_LANGUAGES:
                continue
            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue

            try:
                fpath = self.root / file_info.path
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Look for service names in URL-like patterns
            # Pattern: "service-name:port" or "http://service-name" or "service_name.internal"
            for service_name, target_comp in service_name_map.items():
                if target_comp.id == source_comp.id:
                    continue
                if len(service_name) < 4:  # Skip short names to avoid false positives
                    continue

                # Check for service name in URL-like contexts
                patterns = [
                    rf'["\']https?://{re.escape(service_name)}[:/\'".]',
                    rf'["\']https?://[^"\']*\.{re.escape(service_name)}\.',
                    rf'["\'](?:http://|https://)?{re.escape(service_name)}:\d+["\']',
                    rf'host\s*[=:]\s*["\'](?:[^"\']*\.)?{re.escape(service_name)}["\']',
                    rf'(?:API_|SERVER_|SERVICE_){re.escape(service_name).upper()}',
                ]
                for pat in patterns:
                    if re.search(pat, content, re.IGNORECASE):
                        key = (source_comp.id, target_comp.id, "http")
                        if key not in seen:
                            seen.add(key)
                            relationships.append(Relationship(
                                source=source_comp.id,
                                target=target_comp.id,
                                type="http",
                                protocol="HTTP",
                                label=f"calls {service_name}",
                                bidirectional=True,
                            ))
                        break

        # HTTP client pattern-based relationships for mobile/frontend apps
        # Detect when a client component makes HTTP calls to API servers
        api_servers = [c for c in self._component_map.values()
                       if c.type in ("api-server", "service") and c.id not in content_ids]
        client_types = {"ios-client", "android-client", "web-client", "mobile-client", "watch-app"}

        for file_info in self._all_files:
            lang = file_info.language
            if lang not in HTTP_CLIENT_PATTERNS:
                continue

            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue
            # Only process client-type components
            if source_comp.type not in client_types:
                continue

            try:
                fpath = self.root / file_info.path
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Check if this file contains HTTP client calls
            has_http_calls = False
            for pattern in HTTP_CLIENT_PATTERNS.get(lang, []):
                if re.search(pattern, content):
                    has_http_calls = True
                    break

            if not has_http_calls:
                continue

            # Extract URLs from the file to find target services
            urls_found = set()
            for url_pat in URL_EXTRACTION_PATTERNS:
                for match in re.finditer(url_pat, content):
                    url = match.group("url") if "url" in match.groupdict() else match.group(0)
                    if url:
                        urls_found.add(url.lower())

            # Try to match URLs to API servers
            for api_server in api_servers:
                if api_server.id == source_comp.id:
                    continue

                # Check if any extracted URL references this server
                server_indicators = [
                    api_server.name.lower().replace(" ", "-"),
                    api_server.name.lower().replace(" ", "_"),
                    os.path.basename(api_server.path).lower() if api_server.path else "",
                ]
                if api_server.port:
                    server_indicators.append(f":{api_server.port}")

                matched = False
                for url in urls_found:
                    for indicator in server_indicators:
                        if indicator and len(indicator) > 2 and indicator in url:
                            matched = True
                            break
                    if matched:
                        break

                # If no URL match but we have HTTP calls and only one API server,
                # assume the client talks to it (common in single-backend apps)
                if not matched and len(api_servers) == 1:
                    matched = True

                if matched:
                    key = (source_comp.id, api_server.id, "http")
                    if key not in seen:
                        seen.add(key)
                        relationships.append(Relationship(
                            source=source_comp.id,
                            target=api_server.id,
                            type="http",
                            protocol="HTTP",
                            label="API call",
                            bidirectional=True,
                        ))

        # Watch app -> iOS client companion relationship
        watch_apps = [c for c in self._component_map.values() if c.type == "watch-app"]
        ios_clients = [c for c in self._component_map.values() if c.type == "ios-client"]
        if watch_apps and ios_clients:
            # Pair each watch app with the most likely iOS companion
            # (same project, closest shared parent, or just the first iOS client)
            for watch in watch_apps:
                best_ios = ios_clients[0]
                # Prefer an iOS client in the same parent directory
                watch_parent = os.path.dirname(watch.path) if watch.path else ""
                for ios in ios_clients:
                    ios_parent = os.path.dirname(ios.path) if ios.path else ""
                    if watch_parent == ios_parent or watch.name.lower().replace(" watch", "").replace("watch", "").strip() in ios.name.lower():
                        best_ios = ios
                        break
                key = (watch.id, best_ios.id, "import")
                if key not in seen:
                    seen.add(key)
                    relationships.append(Relationship(
                        source=watch.id,
                        target=best_ios.id,
                        type="import",
                        label="companion app",
                    ))

        # Docker-compose service relationships
        # Build a map of docker service names to components
        docker_services = {}  # service_name -> component
        for comp in self._component_map.values():
            for config in comp.config_files:
                if config.get("type") == "docker-compose":
                    service_name = config.get("service_name", "").lower()
                    if service_name:
                        docker_services[service_name] = comp
                    # Also try component name as fallback
                    docker_services[comp.name.lower().replace(" ", "-")] = comp

        # Look for depends_on relationships in docker-compose configs
        for comp in self._component_map.values():
            for config in comp.config_files:
                if config.get("type") == "docker-compose":
                    depends_on = config.get("depends_on", [])
                    for dep_name in depends_on:
                        dep_name_lower = dep_name.lower()
                        if dep_name_lower in docker_services:
                            target_comp = docker_services[dep_name_lower]
                            if target_comp.id != comp.id:
                                key = (comp.id, target_comp.id, "docker")
                                if key not in seen:
                                    seen.add(key)
                                    relationships.append(Relationship(
                                        source=comp.id,
                                        target=target_comp.id,
                                        type="docker",
                                        label="depends_on",
                                    ))

        # Client-to-all-servers fallback for small projects
        # If we have clients but no HTTP relationships detected, connect clients
        # to all API servers (common pattern in monorepos where URLs are in config)
        clients = [c for c in self._component_map.values()
                   if c.type in client_types and c.id not in content_ids]
        if clients and api_servers:
            # Check if any HTTP relationships exist from clients
            client_ids = {c.id for c in clients}
            has_client_http = any(
                r.source in client_ids and r.type == "http"
                for r in relationships
            )
            if not has_client_http:
                # No HTTP relationships detected, create fallback connections
                for client in clients:
                    for server in api_servers:
                        key = (client.id, server.id, "http")
                        if key not in seen:
                            seen.add(key)
                            relationships.append(Relationship(
                                source=client.id,
                                target=server.id,
                                type="http",
                                protocol="HTTP",
                                label="API (inferred)",
                                bidirectional=True,
                            ))

        # External cloud API detection
        # Track external services referenced by components to surface as notes/metadata
        external_services_by_component = defaultdict(set)
        for file_info in self._all_files:
            lang = file_info.language
            if lang not in CODE_LANGUAGES:
                continue

            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue

            try:
                fpath = self.root / file_info.path
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Check for external cloud API domains
            for domain, (service_name, category) in EXTERNAL_CLOUD_APIS.items():
                if domain in content:
                    # Verify it's in a URL-like context
                    patterns = [
                        rf'["\']https?://{re.escape(domain)}',
                        rf'wss?://{re.escape(domain)}',
                        rf'host["\s:=]+["\']?{re.escape(domain)}',
                    ]
                    for pat in patterns:
                        if re.search(pat, content):
                            external_services_by_component[source_comp.id].add(
                                (service_name, category)
                            )
                            break

        # Add external services as metadata on components
        for comp_id, services in external_services_by_component.items():
            for path, comp in self._component_map.items():
                if comp.id == comp_id:
                    if not hasattr(comp, "external_services"):
                        comp.external_services = []
                    comp.external_services = [
                        {"name": name, "category": cat}
                        for name, cat in sorted(services)
                    ]
                    break

        # WatchConnectivity-based relationship enhancement
        # Scan for WatchConnectivity framework imports to confirm Watch-iOS pairing
        for file_info in self._all_files:
            if file_info.language != "swift":
                continue

            for imp in file_info.imports:
                if imp in WATCH_CONNECTIVITY_IMPORTS:
                    source_comp = self._find_component_for_file(file_info.path)
                    if not source_comp:
                        continue
                    # If this is an iOS client, find any Watch apps and ensure relationship
                    if source_comp.type == "ios-client":
                        for watch in watch_apps:
                            key = (watch.id, source_comp.id, "import")
                            if key not in seen:
                                seen.add(key)
                                relationships.append(Relationship(
                                    source=watch.id,
                                    target=source_comp.id,
                                    type="import",
                                    label="WatchConnectivity",
                                ))
                    # If this is a watch app, find parent iOS client
                    elif source_comp.type == "watch-app":
                        for ios in ios_clients:
                            key = (source_comp.id, ios.id, "import")
                            if key not in seen:
                                seen.add(key)
                                relationships.append(Relationship(
                                    source=source_comp.id,
                                    target=ios.id,
                                    type="import",
                                    label="WatchConnectivity",
                                ))
                    break  # Only need to find it once per file

        # Next.js/web config file URL detection
        # Parse .env files and next.config.* for API URLs to detect backend connections
        env_api_urls = {}  # component_id -> list of URLs
        for file_info in self._all_files:
            filename = os.path.basename(file_info.path)
            # Check for env files and Next.js config
            if not (filename.startswith(".env") or
                    filename in ("next.config.js", "next.config.ts", "next.config.mjs")):
                continue

            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue
            if source_comp.type not in client_types:
                continue

            try:
                fpath = self.root / file_info.path
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Extract URLs from env/config files
            env_patterns = [
                r'(?:NEXT_PUBLIC_)?(?:API_URL|BACKEND_URL|SERVER_URL|WS_URL)\s*[=:]\s*["\']?([^"\'\s\n]+)',
                r'(?:destination|source|rewrites).*?["\']https?://([^"\']+)["\']',
            ]
            for pattern in env_patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    url = match.group(1)
                    if url and not url.startswith("$"):  # Skip env var references
                        if source_comp.id not in env_api_urls:
                            env_api_urls[source_comp.id] = []
                        env_api_urls[source_comp.id].append(url)

        # Match env URLs to API servers
        for comp_id, urls in env_api_urls.items():
            for url in urls:
                for api_server in api_servers:
                    matched = False
                    # Check port match
                    if api_server.port:
                        if f":{api_server.port}" in url:
                            matched = True
                    # Check name match
                    server_name = api_server.name.lower().replace(" ", "-")
                    if server_name in url.lower():
                        matched = True

                    if matched:
                        key = (comp_id, api_server.id, "http")
                        if key not in seen:
                            seen.add(key)
                            relationships.append(Relationship(
                                source=comp_id,
                                target=api_server.id,
                                type="http",
                                protocol="HTTP",
                                label="env config",
                                bidirectional=True,
                            ))

        # Append UI flow relationships (from Phase 2.8) if any
        ui_rels = getattr(self, "_ui_relationships", [])
        relationships.extend(ui_rels)

        self.architecture.relationships = [to_dict(r) for r in relationships]

    def _compute_metrics(self):
        """Compute metrics for each component."""
        for comp in self._component_map.values():
            self._compute_component_metrics(comp)

    def _compute_component_metrics(self, comp):
        """Compute metrics for a single component and its children."""
        file_count = len(comp.files)
        total_lines = 0
        total_size = 0
        lang_counts = defaultdict(int)
        symbol_count = 0

        for fpath in comp.files:
            for fi in self._all_files:
                if fi.path == fpath:
                    total_lines += fi.lines
                    total_size += fi.size_bytes
                    lang_counts[fi.language] += fi.lines
                    symbol_count += len(fi.symbols)
                    break

        comp.metrics = {
            "files": file_count,
            "lines": total_lines,
            "size_bytes": total_size,
            "symbols": symbol_count,
            "languages": dict(lang_counts),
        }

        # Determine primary language
        if lang_counts and not comp.language:
            comp.language = max(lang_counts, key=lang_counts.get)

        # Recurse into children (synthetic UI components not in _component_map)
        for child in comp.children:
            if isinstance(child, Component):
                self._compute_component_metrics(child)

    def _extract_component_docs(self):
        """Extract rich documentation for every component."""
        for rel_path, comp in self._component_map.items():
            if self._scope_paths is not None and comp.id not in self._scoped_component_ids:
                continue
            comp_dir = self.root / rel_path if rel_path else self.root
            if not comp_dir.is_dir():
                continue

            doc = ComponentDoc()

            # --- Read documentation files ---
            doc_file_map = {
                "readme": ("README.md", "README.rst", "README.txt", "README"),
                "claude_md": ("CLAUDE.md",),
                "changelog": ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"),
            }
            for field_name, candidates in doc_file_map.items():
                for fname in candidates:
                    fpath = comp_dir / fname
                    if fpath.exists():
                        try:
                            content = fpath.read_text(encoding="utf-8", errors="replace")
                            # Truncate very large docs to keep JSON manageable
                            if len(content) > 8000:
                                content = content[:8000] + "\n\n... (truncated)"
                            setattr(doc, field_name, content)
                        except OSError:
                            pass
                        break

            # --- Scan docs/ directory for architecture notes ---
            docs_dir = comp_dir / "docs"
            if not docs_dir.is_dir():
                docs_dir = comp_dir / "doc"
            if docs_dir.is_dir():
                arch_notes = []
                for fname in sorted(os.listdir(docs_dir)):
                    if not fname.endswith((".md", ".txt", ".rst")):
                        continue
                    fpath = docs_dir / fname
                    if not fpath.is_file():
                        continue
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="replace")
                        # Extract first heading and first paragraph as summary
                        heading = ""
                        summary_lines = []
                        for line in content.split("\n"):
                            stripped = line.strip()
                            if stripped.startswith("#") and not heading:
                                heading = stripped.lstrip("#").strip()
                            elif heading and stripped:
                                summary_lines.append(stripped)
                                if len(summary_lines) >= 3:
                                    break
                            elif heading and not stripped and summary_lines:
                                break
                        if heading:
                            arch_notes.append(f"**{heading}** ({fname}): {' '.join(summary_lines)}")
                    except OSError:
                        pass
                if arch_notes:
                    doc.architecture_notes = "\n\n".join(arch_notes[:20])

            # --- Extract purpose from package metadata ---
            for cfg in comp.config_files:
                cfg_path = cfg.get("path", "") if isinstance(cfg, dict) else ""
                if not cfg_path:
                    continue
                full_path = self.root / cfg_path
                if not full_path.exists():
                    continue
                try:
                    cfg_content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                basename = os.path.basename(cfg_path)
                if basename == "package.json":
                    try:
                        data = json.loads(cfg_content)
                        desc = data.get("description", "")
                        if desc:
                            doc.purpose = desc
                    except json.JSONDecodeError:
                        pass
                elif basename == "Cargo.toml":
                    m = re.search(r'description\s*=\s*"([^"]+)"', cfg_content)
                    if m:
                        doc.purpose = m.group(1)
                elif basename in ("pyproject.toml", "setup.cfg"):
                    m = re.search(r'description\s*=\s*"([^"]+)"', cfg_content)
                    if m:
                        doc.purpose = m.group(1)

            # --- Collect env vars and API endpoints from files ---
            for file_path in comp.files[:100]:  # limit to prevent slowdown
                full_path = self.root / file_path
                if not full_path.exists():
                    continue
                ext = full_path.suffix.lower()
                lang = LANGUAGE_MAP.get(ext)
                parser = PARSERS.get(lang) if lang else None
                if not parser:
                    continue
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                env_vars = parser.extract_env_vars(content)
                doc.env_vars.extend(v for v in env_vars if v not in doc.env_vars)

                if hasattr(parser, 'detect_api_endpoints'):
                    endpoints = parser.detect_api_endpoints(content)
                    for ep in endpoints:
                        ep_str = f"{ep['method']} {ep['path']}"
                        if ep_str not in [f"{e['method']} {e['path']}" for e in doc.api_endpoints]:
                            doc.api_endpoints.append(ep)

            # --- Detect architectural patterns ---
            patterns = self._detect_patterns(comp)
            doc.patterns = patterns

            # --- Determine tech stack ---
            tech = []
            if comp.framework:
                tech.append(comp.framework)
            if comp.language:
                tech.append(comp.language.capitalize())
            # Check config for additional tech
            for file_path in comp.files[:50]:
                basename = os.path.basename(file_path).lower()
                if basename == "tailwind.config.js" or basename == "tailwind.config.ts":
                    tech.append("TailwindCSS")
                elif basename == "tsconfig.json":
                    tech.append("TypeScript")
                elif basename == ".eslintrc" or basename == "eslint.config.js":
                    tech.append("ESLint")
                elif basename == "jest.config.js" or basename == "jest.config.ts":
                    tech.append("Jest")
                elif basename == "vitest.config.ts":
                    tech.append("Vitest")
                elif basename == "webpack.config.js":
                    tech.append("Webpack")
                elif basename == "vite.config.ts" or basename == "vite.config.js":
                    tech.append("Vite")
            doc.tech_stack = sorted(set(tech))

            comp.docs = to_dict(doc)

    def _detect_patterns(self, comp: Component) -> list[str]:
        """Detect architectural patterns in a component."""
        patterns = []
        file_names = [os.path.basename(f).lower() for f in comp.files]

        # MVC / MVVM / MVP
        has_view = any("view" in f for f in file_names)
        has_model = any("model" in f for f in file_names)
        has_controller = any("controller" in f for f in file_names)
        has_viewmodel = any("viewmodel" in f or "view_model" in f for f in file_names)
        has_presenter = any("presenter" in f for f in file_names)

        if has_view and has_model and has_viewmodel:
            patterns.append("MVVM")
        elif has_view and has_model and has_controller:
            patterns.append("MVC")
        elif has_view and has_model and has_presenter:
            patterns.append("MVP")

        # Repository pattern
        if any("repository" in f or "repo" in f for f in file_names):
            patterns.append("Repository Pattern")

        # Service layer
        if any("service" in f for f in file_names) and comp.type != "service":
            patterns.append("Service Layer")

        # Observer / Pub-Sub
        if any("observer" in f or "subscriber" in f or "publisher" in f for f in file_names):
            patterns.append("Observer/Pub-Sub")

        # Store / State Management
        if any("store" in f or "reducer" in f or "slice" in f for f in file_names):
            patterns.append("State Management")

        # Middleware
        if any("middleware" in f for f in file_names):
            patterns.append("Middleware")

        # Plugin/Extension
        if any("plugin" in f or "extension" in f for f in file_names):
            patterns.append("Plugin Architecture")

        # Factory
        if any("factory" in f for f in file_names):
            patterns.append("Factory Pattern")

        # Dependency Injection
        if any("container" in f or "injector" in f or "provider" in f for f in file_names):
            patterns.append("Dependency Injection")

        # API layer
        if any("api" in f or "endpoint" in f or "route" in f for f in file_names):
            patterns.append("API Layer")

        # Test structure
        test_files = [f for f in file_names if "test" in f or "spec" in f]
        if test_files:
            ratio = len(test_files) / max(len(file_names), 1)
            if ratio > 0.3:
                patterns.append("Well-Tested")
            patterns.append(f"Tests ({len(test_files)} files)")

        return patterns

    def _detect_project_info(self):
        """Detect project-level information."""
        # Try to find README
        for name in ("README.md", "README.rst", "README.txt", "README"):
            readme = self.root / name
            if readme.exists():
                try:
                    content = readme.read_text(encoding="utf-8", errors="replace")
                    # First non-empty, non-heading line as description
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("="):
                            self.architecture.description = line[:200]
                            break
                except OSError:
                    pass
                break

        # Try to detect git remote
        git_config = self.root / ".git" / "config"
        if git_config.exists():
            try:
                content = git_config.read_text(encoding="utf-8", errors="replace")
                m = re.search(r'url\s*=\s*(.+)', content)
                if m:
                    url = m.group(1).strip()
                    # Convert SSH to HTTPS
                    url = re.sub(r'git@github\.com:', 'https://github.com/', url)
                    url = re.sub(r'\.git$', '', url)
                    self.architecture.repository = url
            except OSError:
                pass

    def _build_component_tree(self) -> list[dict]:
        """Build a hierarchical tree of components."""
        # Build parent-child mapping first (paths only)
        children_map: dict[str, list[str]] = defaultdict(list)
        root_paths = []

        for path in self._component_map:
            parent_path = self._find_parent_component(path)
            if parent_path is None or path == "":
                root_paths.append(path)
            else:
                children_map[parent_path].append(path)

        # Recursively serialize
        def serialize(path: str) -> dict:
            comp = self._component_map[path]
            d = to_dict(comp)
            # Build children from path-based hierarchy
            path_children = [serialize(cp) for cp in sorted(children_map.get(path, []))]
            # Preserve UI flow children added by _detect_ui_flows (Component objects
            # stored directly in comp.children, not in _component_map).
            ui_children = []
            for child in comp.children:
                if isinstance(child, Component):
                    ui_children.append(to_dict(child))
            d["children"] = ui_children + path_children
            return d

        roots = [serialize(p) for p in sorted(root_paths)]

        # If single root project, keep it but ensure children are populated
        return roots

    def _make_component_id(self, rel_path: str) -> str:
        """Create a stable component ID from relative path."""
        if not rel_path:
            return "root"
        return rel_path.replace(os.sep, "/").replace(" ", "-").lower()

    def _find_parent_component(self, rel_path: str) -> Optional[str]:
        """Find the nearest parent component for a path."""
        if not rel_path:
            return None

        parts = rel_path.split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            parent = os.sep.join(parts[:i])
            if not parent:
                parent = ""
            if parent in self._component_map and parent != rel_path:
                return parent
        return "" if "" in self._component_map else None

    def _find_component_for_file(self, file_path: str) -> Optional[Component]:
        """Find the deepest component that contains this file."""
        parts = file_path.split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            dir_path = os.sep.join(parts[:i])
            if not dir_path:
                dir_path = ""
            if dir_path in self._component_map:
                return self._component_map[dir_path]
        return self._component_map.get("")

    def _resolve_import_to_component(self, import_name: str, source_file: str) -> Optional[Component]:
        """Try to resolve an import to a component."""
        # For relative imports, try to find the target file/directory
        if import_name.startswith("."):
            source_dir = os.path.dirname(source_file)
            # Resolve relative path
            parts = import_name.split("/")
            current = source_dir
            for part in parts:
                if part == ".":
                    continue
                elif part == "..":
                    current = os.path.dirname(current)
                else:
                    current = os.path.join(current, part)
            return self._find_component_for_file(current)

        # For absolute imports, try to match against component names/paths
        import_lower = import_name.lower()
        for path, comp in self._component_map.items():
            comp_name = comp.name.lower().replace("-", "").replace("_", "")
            if import_lower.replace("-", "").replace("_", "") == comp_name:
                return comp
            # Check if import matches a directory name in the component
            if path and os.path.basename(path).lower() == import_lower:
                return comp

        return None
