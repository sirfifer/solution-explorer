"""UI flow and UI action derivation (Tier 3).

Preserves the SwiftUI flow pipeline (screens, tabs, navigation) and UI-action
detection by driving the existing detectors with a store-backed root, so they
read cached content instead of the disk (TARGET-ARCHITECTURE.md 4.3, card item
3). Navigation, tab, modal and embed edges gain evidence rows pointing at the
detected source file. On repos with no client-type component (the current
fixtures) these passes produce nothing, which matches the old engine.
"""

from __future__ import annotations

from ..action_detector import UIActionDetector
from ..models import to_dict
from ..swiftui_flow import SwiftUIFlowDetector
from .context import Deriver

CLIENT_TYPES = {"ios-client", "android-client", "web-client",
                "mobile-client", "desktop-app", "watch-app"}


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
        # the detector found the construct in.
        path_by_id = {c.id: c.path for c in new_components}
        for rel in new_relationships:
            key = (rel.source, rel.target, rel.type)
            d._ui_relationships.append(rel)
            src_file = path_by_id.get(rel.source) or comp.path
            d._ui_edge_evidence[key] = [{
                "file": src_file, "line": None,
                "snippet": rel.label or rel.type,
            }]


def flow_relationship_dicts(d: Deriver) -> list[dict]:
    return [to_dict(r) for r in d._ui_relationships]
