"""Storyboard flow derivation (Tier 3, P4-9).

Turns the ``storyboard_scene`` and ``storyboard_segue`` signals the extraction
tier emitted (analyzer/extract/signals.py, never a source re-read; invariant I1)
into screen components and navigation/modal/embed edges, exactly the shape the
SwiftUI flow pass (analyzer/derive/flow.py) produces, so the Flow lens draws
storyboard navigation the same way it draws SwiftUI navigation targets.

Each scene becomes a ``screen`` component owned by the component that owns the
storyboard file, attached under it via ``children`` (the SwiftUI screen
convention). Each segue becomes a ``_ui_relationships`` edge between the two
scene components, typed navigation/modal/embed from its ``kind`` and labeled with
the kind (so the reader sees "push: show" versus "modal (presentModally)").

Custom-class binding: a scene's name is its bound controller class (customClass)
when present, so the screen component's name matches the Swift symbol of the same
name. That is the "match them to Swift symbols by name" hook the card asks for;
it is recorded on the component (name plus description) rather than drawn as a
separate edge, keeping the derivation KISS.

Determinism (invariant I4): files are processed in sorted order, scenes and
segues in signal (document) order, and ids are content-derived from the file path
and the Interface Builder controller id, never order-derived.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Component, Relationship
from .capabilities import _slug
from .context import Deriver

__all__ = ["derive_storyboard_flow"]


def derive_storyboard_flow(d: Deriver) -> None:
    """Build screen components and flow edges from storyboard signals; record on ``d``."""
    for path in sorted(d.view.signals_by_path):
        signals = d.view.signals_by_path[path]
        scenes = [s for s in signals if s["kind"] == "storyboard_scene"]
        segues = [s for s in signals if s["kind"] == "storyboard_segue"]
        if not scenes:
            continue
        owner = d._find_component_for_file(path)
        if owner is None:
            continue

        # controller id -> the screen component built for that scene, so segue
        # destinations (Interface Builder ids) resolve within this file.
        node_by_controller: dict[str, Component] = {}
        unnamed_seen = 0
        for sig in scenes:
            value = sig.get("value") or {}
            controller_id = value.get("controller_id")
            if not controller_id or controller_id in node_by_controller:
                continue
            name = value.get("name") or controller_id
            custom_class = value.get("custom_class")
            # A scene with no customClass and no storyboardIdentifier falls back
            # to its raw Interface Builder id (like "01J-lp-oVM"), which is
            # meaningless to a reader. Name such scenes after the storyboard
            # file itself (LaunchScreen.storyboard's lone scene reads
            # "LaunchScreen"), suffixed by position when a file has several
            # unnamed scenes so names stay unique and deterministic.
            if name == controller_id:
                stem = Path(path).name
                for suffix in (".storyboard", ".xib"):
                    if stem.endswith(suffix):
                        stem = stem[: -len(suffix)]
                        break
                unnamed_seen += 1
                name = stem if unnamed_seen == 1 else f"{stem} scene {unnamed_seen}"
            node_id = f"{owner.id}/__ui__/{_slug(path)}/{controller_id}"
            screen = Component(
                id=node_id,
                name=name,
                type="screen",
                path=path,
                language="swift" if custom_class else None,
                framework="UIKit",
                description=(f"Storyboard scene bound to {custom_class}"
                            if custom_class else "Storyboard scene"),
            )
            screen.files = [path]
            node_by_controller[controller_id] = screen
            owner.children.append(screen)

        for sig in segues:
            value = sig.get("value") or {}
            src = node_by_controller.get(value.get("source_id"))
            dst = node_by_controller.get(value.get("destination_id"))
            # A segue whose destination lives in another storyboard file cannot
            # be resolved to a node here, so it is not drawn (recorded scope
            # bound, not a silent guess).
            if src is None or dst is None:
                continue
            kind = value.get("kind") or "show"
            edge_type = value.get("edge_type") or "navigation"
            rel = Relationship(
                source=src.id,
                target=dst.id,
                type=edge_type,
                label=kind,
            )
            key = (rel.source, rel.target, rel.type)
            d._ui_relationships.append(rel)
            d._ui_edge_evidence[key] = [{
                "file": path,
                "line": sig.get("line"),
                "snippet": value.get("identifier") or kind,
            }]
