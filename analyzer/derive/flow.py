"""UI flow and UI action derivation (Tier 3).

Preserves the SwiftUI flow pipeline (screens, tabs, navigation) and UI-action
detection by driving the existing detectors with a store-backed root, so they
read cached content instead of the disk (TARGET-ARCHITECTURE.md 4.3, card item
3). Navigation, tab, modal and embed edges gain evidence rows pointing at the
detected source file. On repos with no client-type component (the current
fixtures) these passes produce nothing, which matches the old engine.
"""

from __future__ import annotations

import re

from ..action_detector import UIActionDetector
from ..models import to_dict
from ..swiftui_flow import SwiftUIFlowDetector
from .context import Deriver

CLIENT_TYPES = {"ios-client", "android-client", "web-client",
                "mobile-client", "desktop-app", "watch-app"}


def _ui_edge_source_evidence(
    content: str, path: str, target_view: str, fallback: str
) -> dict:
    """Point at both the presentation construct and target construction.

    A destination initializer proves the hand-off arguments but not whether it
    is a sheet, navigation destination, or plain embedded child. Search the
    bounded preceding source window for the detector construct and retain both
    lines in one deterministic excerpt. This gives enrichment and adjudication
    the evidence needed for the relationship type without reading source later.
    """
    pattern = re.compile(rf"\b{re.escape(target_view)}\s*\(")
    matches = list(pattern.finditer(content or ""))
    if not matches:
        return {"file": path, "line": None, "snippet": fallback}
    lines = content.splitlines()
    modal = str(fallback or "").lower() in {"sheet", "fullscreen", "modal"}
    marker = (
        re.compile(r"\.(?:sheet|fullScreenCover)\s*\(")
        if modal else
        re.compile(r"(?:\bNavigationLink\b|\.navigationDestination\s*\()")
    )
    candidates = []
    for match in matches:
        target_index = content.count("\n", 0, match.start())
        source_line = lines[target_index].strip()
        for index in range(target_index, max(-1, target_index - 80), -1):
            marker_line = lines[index].strip()
            if marker.search(marker_line):
                candidates.append((
                    target_index - index, target_index, index,
                    marker_line, source_line,
                ))
                break
    if candidates:
        _, _, index, marker_line, source_line = min(candidates)
        snippet = source_line if marker_line == source_line else (
            f"{marker_line} … {source_line}"
        )
        return {"file": path, "line": index + 1, "snippet": snippet[:600]}
    first = matches[0]
    target_index = content.count("\n", 0, first.start())
    source_line = lines[target_index].strip()
    return {"file": path, "line": target_index + 1, "snippet": source_line[:300]}


def detect_ui_actions(d: Deriver) -> None:
    detector = UIActionDetector()
    for comp in d._component_map.values():
        if not comp.language or not comp.files:
            continue
        actions = detector.detect(comp.files, d.root, comp.language)
        if actions:
            comp.actions = actions


def detect_ui_flows(d: Deriver) -> None:
    detector_map = {
        "SwiftUI": SwiftUIFlowDetector(),
        "UIKit": SwiftUIFlowDetector(),
        "AppKit": SwiftUIFlowDetector(),
    }
    for rel_path, comp in list(d._component_map.items()):
        if comp.type not in CLIENT_TYPES:
            continue
        detector = detector_map.get(comp.framework or "")
        if not detector:
            continue

        # Expand to descendant files, as the scanner does, then restore.
        all_files = set(comp.files)
        for child_path, child_comp in d._component_map.items():
            if child_path and child_path.startswith(rel_path + "/"):
                all_files.update(child_comp.files)
        original_files = comp.files
        comp.files = sorted(all_files)

        new_components, new_relationships = detector.detect(comp, d.root)
        comp.files = original_files
        if not new_components:
            continue

        for new_comp in new_components:
            if new_comp.type == "tab-container":
                comp.children.append(new_comp)
            elif new_comp.type == "screen" and not any(
                new_comp in tc.children
                for tc in new_components if tc.type in ("tab", "tab-container")
            ):
                comp.children.append(new_comp)

        # Evidence: the source screen/tab component's `path` is the Swift file
        # the detector found the construct in. Point at the exact destination
        # constructor when it is present; a bare file plus the word "sheet" or
        # "navigation" proves existence but cannot support a claim about flow.
        path_by_id = {c.id: c.path for c in new_components}
        symbol_names_by_file: dict[str, list[str]] = {}
        for file_info in d._all_files:
            for symbol in file_info.symbols:
                # During derivation FileInfo.symbols contains stable symbol IDs;
                # the final path segment is the declared symbol name.
                symbol_names_by_file.setdefault(file_info.path, []).append(
                    str(symbol).rsplit(" ", 1)[-1]
                )
        view_name_by_id = {}
        for component in new_components:
            slug = component.id.rsplit("/", 1)[-1].lower()
            view_name_by_id[component.id] = next(
                (
                    name for name in symbol_names_by_file.get(component.path, [])
                    if name.lower() == slug
                ),
                component.name.replace(" ", ""),
            )
        for rel in new_relationships:
            key = (rel.source, rel.target, rel.type)
            d._ui_relationships.append(rel)
            src_file = path_by_id.get(rel.source) or comp.path
            source_content = d.view.content(src_file) or ""
            d._ui_edge_evidence[key] = [_ui_edge_source_evidence(
                source_content,
                src_file,
                view_name_by_id.get(rel.target) or rel.target.rsplit("/", 1)[-1],
                rel.label or rel.type,
            )]


def flow_relationship_dicts(d: Deriver) -> list[dict]:
    return [to_dict(r) for r in d._ui_relationships]
