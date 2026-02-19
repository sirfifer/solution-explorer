"""SwiftUI flow detection for screens, tabs, and navigation."""

import os
import re
from pathlib import Path
from typing import Optional

from .constants import (
    HELPER_CONTAINS,
    HELPER_SUFFIXES,
    SCREEN_SUFFIXES,
    UI_DIR_NAMES,
)
from .models import Component, Relationship
from .utils import _extract_brace_body


class SwiftUIFlowDetector:
    """Detect UI screens and navigation flows from SwiftUI source code.

    Parses TabView, NavigationLink, .sheet, .fullScreenCover, and
    .navigationDestination patterns to build a screen hierarchy with
    navigation relationships.
    """

    # --- Regex patterns for SwiftUI constructs ---

    # View struct: struct FooView: View {
    VIEW_STRUCT_RE = re.compile(
        r'struct\s+(\w+)\s*:\s*(?:\w+\s*,\s*)*View\b'
    )

    # @main attribute (app entry point)
    MAIN_ATTR_RE = re.compile(r'@main\b')

    # TabView keyword
    TABVIEW_RE = re.compile(r'\bTabView\b')

    # .tabItem { Label("Name", systemImage: "icon") }
    # Captures the label text
    TAB_ITEM_LABEL_RE = re.compile(
        r'\.tabItem\s*\{[^}]*?Label\s*\(\s*"([^"]+)"', re.DOTALL
    )

    # NavigationLink { DestView() } label: { ... }
    # Captures the destination view name from the content closure
    NAV_LINK_CONTENT_RE = re.compile(
        r'NavigationLink\s*\{[^}]*?(\w+(?:View|Screen|Page|Tab|Dashboard|Sheet))\s*\(',
        re.DOTALL
    )

    # NavigationLink(destination: DestView(...))
    NAV_LINK_DEST_RE = re.compile(
        r'NavigationLink\s*\(\s*destination:\s*(\w+)\s*\('
    )

    # .navigationDestination(isPresented:) { DestView() }
    # or .navigationDestination(for: X.self) { ... DestView() }
    NAV_DEST_RE = re.compile(
        r'\.navigationDestination\s*\([^)]*\)\s*\{[^}]*?'
        r'(\w+(?:View|Screen|Page|Tab|Dashboard|Sheet))\s*\(',
        re.DOTALL
    )

    # .sheet(isPresented:) { DestView() } or .sheet(item:) { ... DestView() }
    SHEET_RE = re.compile(
        r'\.sheet\s*\([^)]*\)\s*\{[^}]*?'
        r'(\w+(?:View|Screen|Page|Tab|Dashboard|Sheet))\s*\(',
        re.DOTALL
    )

    # .fullScreenCover(isPresented:) { DestView() }
    FULLSCREEN_RE = re.compile(
        r'\.fullScreenCover\s*\([^)]*\)\s*\{[^}]*?'
        r'(\w+(?:View|Screen|Page|Tab|Dashboard|Sheet))\s*\(',
        re.DOTALL
    )

    def _collect_view_structs(
        self, comp_files: list[str], root: Path
    ) -> dict[str, str]:
        """Scan Swift files for View struct declarations.

        Returns dict of view_name -> relative_file_path.
        """
        view_map: dict[str, str] = {}
        for fpath in comp_files:
            if not fpath.endswith(".swift"):
                continue
            try:
                content = (root / fpath).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            for m in self.VIEW_STRUCT_RE.finditer(content):
                view_map[m.group(1)] = fpath
        return view_map

    @staticmethod
    def _extract_view_body(content: str, view_name: str) -> str:
        """Extract the body of a specific View struct from file content.

        Returns the text of the struct body (between outermost braces),
        or the full file content if the struct cannot be found.
        """
        # Find the struct declaration
        pattern = re.compile(
            rf'struct\s+{re.escape(view_name)}\s*:\s*(?:\w+\s*,\s*)*View\b'
        )
        m = pattern.search(content)
        if not m:
            return content  # fallback: scan whole file
        return _extract_brace_body(content, m.start())

    def _find_entry_point(
        self, view_map: dict[str, str], root: Path
    ) -> Optional[tuple[str, str]]:
        """Find the app entry point containing the TabView.

        Returns (view_name, file_path) or None.
        """
        # First: look for @main + TabView in the same file
        for vname, fpath in view_map.items():
            try:
                content = (root / fpath).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            if self.MAIN_ATTR_RE.search(content) and self.TABVIEW_RE.search(content):
                return (vname, fpath)

        # Second: look for any file with TabView
        for vname, fpath in view_map.items():
            try:
                content = (root / fpath).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            if self.TABVIEW_RE.search(content):
                return (vname, fpath)

        return None

    def _detect_tabs(self, content: str) -> list[dict]:
        """Parse TabView body to extract tabs.

        Returns list of {label, view_name} dicts.
        """
        tabs = []
        # Find the TabView and extract its full body using brace counting
        tv_match = self.TABVIEW_RE.search(content)
        if not tv_match:
            return tabs

        tv_body = _extract_brace_body(content, tv_match.start())
        if not tv_body:
            return tabs

        # Split the TabView body by .tabItem to find each tab's content
        # Strategy: find each .tabItem and look backward for the View reference
        parts = tv_body.split(".tabItem")
        for i in range(1, len(parts)):
            # The part before .tabItem contains the View instantiation
            before = parts[i - 1]
            # The part at .tabItem contains the Label
            at_tabitem = parts[i]

            # Extract tab label
            label_match = re.search(
                r'\{\s*(?:[^}]*?)Label\s*\(\s*"([^"]+)"', at_tabitem, re.DOTALL
            )
            label = label_match.group(1) if label_match else f"Tab {i}"

            # Extract view name: find the last View() reference before .tabItem
            # Look for FooView() or FooView(param: value)
            view_matches = list(re.finditer(
                r'(\w+(?:View|Screen|Content|Tab|Dashboard))\s*\(', before
            ))
            view_name = view_matches[-1].group(1) if view_matches else None

            if view_name:
                tabs.append({"label": label, "view_name": view_name})

        return tabs

    def _detect_navigation_targets(self, content: str) -> list[dict]:
        """Find all views referenced as navigation destinations.

        Returns list of {target, nav_type} dicts.
        """
        targets = []
        seen = set()

        for m in self.NAV_LINK_CONTENT_RE.finditer(content):
            name = m.group(1)
            if name not in seen:
                targets.append({"target": name, "nav_type": "push"})
                seen.add(name)

        for m in self.NAV_LINK_DEST_RE.finditer(content):
            name = m.group(1)
            if name not in seen:
                targets.append({"target": name, "nav_type": "push"})
                seen.add(name)

        for m in self.NAV_DEST_RE.finditer(content):
            name = m.group(1)
            if name not in seen:
                targets.append({"target": name, "nav_type": "push"})
                seen.add(name)

        return targets

    def _detect_modal_targets(self, content: str) -> list[dict]:
        """Find all views presented as sheets or fullScreenCovers.

        Returns list of {target, nav_type} dicts.
        """
        targets = []
        seen = set()

        for m in self.SHEET_RE.finditer(content):
            name = m.group(1)
            if name not in seen:
                targets.append({"target": name, "nav_type": "sheet"})
                seen.add(name)

        for m in self.FULLSCREEN_RE.finditer(content):
            name = m.group(1)
            if name not in seen:
                targets.append({"target": name, "nav_type": "fullscreen"})
                seen.add(name)

        return targets

    @staticmethod
    def _detect_embedded_views(
        content: str, source_view: str, view_map: dict[str, str]
    ) -> list[dict]:
        """Find known View structs directly instantiated in the body.

        Detects patterns like ``CurriculumContentView()`` or
        ``TodoListView(model: vm)`` where the referenced view is one of the
        known View structs in *view_map*.  This captures "composition"
        relationships (a parent view embedding a child view directly in its
        body) that are invisible to NavigationLink/sheet scanning.

        Returns list of {target, nav_type: "embeds"} dicts.
        """
        targets = []
        seen: set[str] = set()
        for m in re.finditer(r'\b([A-Z]\w+)\s*\(', content):
            name = m.group(1)
            if name == source_view or name in seen:
                continue
            if name in view_map:
                targets.append({"target": name, "nav_type": "embeds"})
                seen.add(name)
        return targets

    @staticmethod
    def _is_ui_directory(file_path: str) -> bool:
        """Check if a file path contains a UI-related directory name."""
        parts = Path(file_path).parts
        return any(p.lower() in UI_DIR_NAMES for p in parts)

    @staticmethod
    def _has_screen_suffix(view_name: str) -> bool:
        """Check if a view name ends with a screen-like suffix."""
        return any(view_name.endswith(s) for s in SCREEN_SUFFIXES)

    def _humanize_view_name(self, view_name: str) -> str:
        """Convert a view struct name to a human-readable screen name.

        E.g., 'KBDashboardView' -> 'KB Dashboard',
              'SettingsView' -> 'Settings'.
        """
        name = view_name
        for suffix in ("View", "Screen", "Page"):
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[:-len(suffix)]
                break
        # Insert spaces before uppercase letters (camelCase split)
        result = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
        return result

    def _feature_group_name(self, file_path: str) -> Optional[str]:
        """Derive a feature group name from the file's directory.

        E.g., 'UI/Settings/SettingsView.swift' -> 'Settings'.
        Returns None if the directory is not a meaningful feature group.
        """
        parts = Path(file_path).parts
        # Look for the directory right after a UI-like directory
        for i, part in enumerate(parts):
            if part.lower() in UI_DIR_NAMES and i + 1 < len(parts):
                next_part = parts[i + 1]
                # The next part should be a directory name, not a file
                if not next_part.endswith(".swift"):
                    return next_part
        # Fall back to the immediate parent directory if it looks meaningful
        parent = Path(file_path).parent.name
        if parent.lower() not in UI_DIR_NAMES and parent not in (".", ""):
            return parent
        return None

    def detect(
        self, component: "Component", root: Path
    ) -> tuple[list["Component"], list["Relationship"]]:
        """Detect UI screens and navigation flows in a SwiftUI app.

        Returns (new_child_components, navigation_relationships).
        """
        comp_id = component.id
        new_components: list[Component] = []
        new_relationships: list[Relationship] = []

        # Step 1: Collect all View structs from the component's Swift files
        view_map = self._collect_view_structs(component.files, root)
        if not view_map:
            return new_components, new_relationships

        # Step 2: Find the entry point (TabView)
        entry = self._find_entry_point(view_map, root)

        # Step 3: Detect tab structure
        tabs = []
        if entry:
            entry_name, entry_file = entry
            try:
                entry_content = (root / entry_file).read_text(
                    encoding="utf-8", errors="replace"
                )
                tabs = self._detect_tabs(entry_content)
            except OSError:
                pass

        # Step 4: Build navigation graph by scanning each view struct's body.
        # Important: extract each View's body so views in the same file don't
        # share navigation targets (e.g., MoreTabView and SessionTabContent
        # are both in UnaMentisApp.swift but have separate navigation).
        nav_graph: dict[str, list[dict]] = {}
        all_nav_targets: set[str] = set()
        tab_view_names = {t["view_name"] for t in tabs}

        # Cache file contents to avoid re-reading
        file_cache: dict[str, str] = {}
        for vname, fpath in view_map.items():
            if fpath not in file_cache:
                try:
                    file_cache[fpath] = (root / fpath).read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError:
                    file_cache[fpath] = ""

            content = file_cache[fpath]
            if not content:
                continue

            # Extract only this View struct's body for targeted scanning
            view_body = self._extract_view_body(content, vname)

            nav_targets = self._detect_navigation_targets(view_body)
            modal_targets = self._detect_modal_targets(view_body)
            embed_targets = self._detect_embedded_views(
                view_body, vname, view_map
            )
            all_targets = nav_targets + modal_targets + embed_targets

            if all_targets:
                nav_graph[vname] = all_targets
                for t in all_targets:
                    # Embedded views are composition, not explicit navigation.
                    # Only navigation/modal targets count for screen promotion.
                    if t["nav_type"] != "embeds":
                        all_nav_targets.add(t["target"])

        # Step 5: Classify views as screens.
        # Tab content views are always screens (they are the root of a tab).
        # For everything else, apply helper filters before classifying.
        screen_views: dict[str, str] = {}  # view_name -> file_path
        for vname, fpath in view_map.items():
            is_tab_content = vname in tab_view_names

            # Tab content views are always screens (never filtered)
            if is_tab_content:
                screen_views[vname] = fpath
                continue

            # Apply helper filters to all other views, including nav targets
            # (e.g., a HelpSheet opened via .sheet is a helper, not a screen).
            # Strip trailing View/Screen/Page before checking suffixes so that
            # e.g. "KBBarChartView" is recognized as ending with "Chart".
            stripped = vname
            for sfx in ("View", "Screen", "Page"):
                if stripped.endswith(sfx) and len(stripped) > len(sfx):
                    stripped = stripped[:-len(sfx)]
                    break
            if any(stripped.endswith(s) for s in HELPER_SUFFIXES):
                continue
            if any(h in vname for h in HELPER_CONTAINS):
                continue

            is_nav_target = vname in all_nav_targets
            is_in_ui_dir = self._is_ui_directory(fpath)
            has_suffix = self._has_screen_suffix(vname)

            # Explicit navigation/modal targets that survive filtering
            if is_nav_target:
                screen_views[vname] = fpath
            # Views in UI directories with screen-like names
            elif is_in_ui_dir and has_suffix:
                screen_views[vname] = fpath

        if not screen_views and not tabs:
            return new_components, new_relationships

        # Step 6: Group screens by feature area (directory)
        feature_groups: dict[str, list[str]] = {}  # group_name -> [view_names]
        view_to_group: dict[str, str] = {}
        for vname, fpath in screen_views.items():
            group = self._feature_group_name(fpath)
            if group:
                feature_groups.setdefault(group, []).append(vname)
                view_to_group[vname] = group

        # Step 7: Build Components

        # 7a: Tab container (if tabs were detected)
        if tabs:
            tab_container = Component(
                id=f"{comp_id}/__ui__/tab-bar",
                name="Tab Bar",
                type="tab-container",
                path=entry_file if entry else "",
                language="swift",
                framework="SwiftUI",
                description=f"{len(tabs)} tabs",
            )
            if tab_container.path:
                tab_container.files = [tab_container.path]
            new_components.append(tab_container)

        # 7b: Tab components
        tab_components: dict[str, Component] = {}  # view_name -> tab Component
        for tab in tabs:
            tab_id = f"{comp_id}/__ui__/tab-{tab['label'].lower().replace(' ', '-')}"
            tab_comp = Component(
                id=tab_id,
                name=tab["label"],
                type="tab",
                path=screen_views.get(tab["view_name"], ""),
                language="swift",
                framework="SwiftUI",
            )
            if tab_comp.path:
                tab_comp.files = [tab_comp.path]
            tab_components[tab["view_name"]] = tab_comp
            new_components.append(tab_comp)

            # Relationship: tab-container -> tab
            new_relationships.append(Relationship(
                source=f"{comp_id}/__ui__/tab-bar",
                target=tab_id,
                type="tab",
                label=tab["label"],
            ))

        # 7c: Screen components
        screen_components: dict[str, Component] = {}  # view_name -> screen Component
        for vname, fpath in screen_views.items():
            # Skip views that are already tabs (they get tab components)
            if vname in tab_components:
                continue

            screen_id = f"{comp_id}/__ui__/{vname.lower()}"
            human_name = self._humanize_view_name(vname)
            screen_comp = Component(
                id=screen_id,
                name=human_name,
                type="screen",
                path=fpath,
                language="swift",
                framework="SwiftUI",
            )
            if fpath:
                screen_comp.files = [fpath]
            screen_components[vname] = screen_comp
            new_components.append(screen_comp)

        # Step 8: Build navigation Relationships (skip "embeds", which are
        # only used for BFS reachability in Step 9, not user-visible navigation)
        for source_view, targets in nav_graph.items():
            # Determine source component ID
            if source_view in tab_components:
                source_id = tab_components[source_view].id
            elif source_view in screen_components:
                source_id = screen_components[source_view].id
            else:
                continue

            for target_info in targets:
                target_view = target_info["target"]
                nav_type = target_info["nav_type"]

                # Skip embed relationships (composition, not navigation)
                if nav_type == "embeds":
                    continue

                # Determine target component ID
                if target_view in tab_components:
                    target_id = tab_components[target_view].id
                elif target_view in screen_components:
                    target_id = screen_components[target_view].id
                else:
                    continue  # Target view not classified as a screen

                rel_type = "modal" if nav_type in ("sheet", "fullscreen") else "navigation"
                new_relationships.append(Relationship(
                    source=source_id,
                    target=target_id,
                    type=rel_type,
                    label=nav_type if rel_type == "modal" else None,
                ))

        # Step 9: Nest screens under their tabs using the component children
        # Walk the navigation graph starting from each tab's content view
        # to find which screens are reachable from each tab.
        if tabs:
            # BFS from each tab's content view, recording the distance
            # (hop count) at which each screen is discovered.  Screens
            # reachable from multiple tabs are assigned to the closest tab.
            # screen_name -> {tab_view_name -> distance}
            screen_distances: dict[str, dict[str, int]] = {}

            for tab in tabs:
                tab_view = tab["view_name"]
                if tab_view not in tab_components:
                    continue

                queue: list[tuple[str, int]] = [(tab_view, 0)]
                visited: set[str] = set()
                while queue:
                    current, dist = queue.pop(0)
                    if current in visited:
                        continue
                    visited.add(current)
                    for target_info in nav_graph.get(current, []):
                        target = target_info["target"]
                        if target in screen_components:
                            dists = screen_distances.setdefault(target, {})
                            if tab_view not in dists or dist + 1 < dists[tab_view]:
                                dists[tab_view] = dist + 1
                        if target in view_map:
                            queue.append((target, dist + 1))

            # Assign each screen to the tab with the shortest distance.
            # Ties broken by tab order (left-to-right in the tab bar).
            claimed_screens: set[str] = set()
            tab_order = [t["view_name"] for t in tabs]

            for sname, dists in screen_distances.items():
                best_tab = min(
                    dists,
                    key=lambda tv: (dists[tv], tab_order.index(tv)
                                    if tv in tab_order else 999),
                )
                if best_tab in tab_components:
                    tab_components[best_tab].children.append(
                        screen_components[sname]
                    )
                    claimed_screens.add(sname)

            # Step 9.5: Directory-based fallback for orphan screens.
            # Screens not reachable from any tab via BFS are assigned to the
            # tab whose content view lives in the same directory subtree.
            orphan_screens = set(screen_components.keys()) - claimed_screens
            if orphan_screens:
                # Map each tab to the directory subtree of its content view
                tab_dirs: dict[str, str] = {}  # tab_view -> directory prefix
                for tab in tabs:
                    tv = tab["view_name"]
                    fpath = view_map.get(tv, "")
                    if fpath:
                        # Use the parent directory of the tab content view's file
                        tab_dirs[tv] = str(Path(fpath).parent)

                for sname in sorted(orphan_screens):
                    sc = screen_components[sname]
                    screen_dir = str(Path(screen_views[sname]).parent)
                    best_tab = None
                    best_depth = -1
                    for tab in tabs:
                        tv = tab["view_name"]
                        tab_dir = tab_dirs.get(tv, "")
                        if not tab_dir:
                            continue
                        # Check if screen is in the same directory subtree
                        # Use the UI directory level, not exact match
                        tab_parts = Path(tab_dir).parts
                        screen_parts = Path(screen_dir).parts
                        # Find common prefix depth
                        common = 0
                        for a, b in zip(tab_parts, screen_parts):
                            if a == b:
                                common += 1
                            else:
                                break
                        # Require at least sharing a UI feature directory
                        if common > best_depth and common >= 2:
                            best_depth = common
                            best_tab = tv
                    if best_tab and best_tab in tab_components:
                        tab_components[best_tab].children.append(sc)
                        claimed_screens.add(sname)

            # For tabs: add the tab's entry screen info to description
            for tab in tabs:
                tab_view = tab["view_name"]
                if tab_view in tab_components:
                    entry_screen = screen_views.get(tab_view)
                    if entry_screen:
                        tab_components[tab_view].description = (
                            f"Entry: {self._humanize_view_name(tab_view)}"
                        )

            # Nest tabs under the tab container
            if tabs and new_components:
                tab_container = new_components[0]  # First component is tab-container
                for tab in tabs:
                    if tab["view_name"] in tab_components:
                        tab_container.children.append(
                            tab_components[tab["view_name"]]
                        )

        return new_components, new_relationships
