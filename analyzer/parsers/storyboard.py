"""Storyboard and XIB parser (P4-9, v2-only).

Interface Builder storyboards (`.storyboard`) and nib files (`.xib`) are XML
documents that declare scenes (each owning a view controller) and the segues
that navigate between them. This parser turns one such document into:

  - symbols: one per view controller (the scene's controller), so a storyboard
    contributes searchable view-controller symbols to the store like any source
    file; and
  - a flow model (scenes plus segues) that ``analyzer/extract/signals.py`` emits
    as ``storyboard_scene`` and ``storyboard_segue`` signals, which the Tier 3
    storyboard pass (``analyzer/derive/storyboard.py``) turns into screen
    components and navigation/modal edges for the Flow lens, exactly the way
    SwiftUI navigation targets feed it.

Parsing is stdlib ``xml.etree.ElementTree``. ElementTree does NOT resolve
external entities (no external DTD/entity fetch), so it is XXE-safe for
untrusted input; we rely on that default rather than a third-party guard. A
malformed document raises ``ElementTree.ParseError``; the extraction worker
catches it and records the file ``failed`` (it never crashes the run).

Determinism (invariant I4): scenes are emitted in document order, segues in
document order within their scene, and every name falls back through a fixed
precedence (customClass, storyboardIdentifier, controller id), so two runs over
the same bytes produce byte-identical output.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from .base import BaseParser, NestedSymbol

# Segue ``kind`` values that present the destination modally rather than pushing
# it. Everything else that is a real navigation (show, showDetail, push, custom)
# is treated as a push; embed/relationship kinds are containment, not navigation.
_MODAL_KINDS = {"presentModally", "present", "presentAsPopover", "popoverPresentation",
                "modal", "sheet", "formSheet"}
_EMBED_KINDS = {"embed", "relationship"}


@dataclass
class Scene:
    """One view controller in a storyboard scene."""

    controller_id: str          # Interface Builder object id (segue destinations use it)
    name: str                   # customClass, else storyboardIdentifier, else the id
    custom_class: Optional[str]  # the Swift/Obj-C class bound to this scene, if any
    storyboard_id: Optional[str]
    tag: str                    # the element tag, e.g. "viewController"
    line: int                   # 1-based line of the controller's id in the source


@dataclass
class Segue:
    """One segue: a navigation from a source controller to a destination."""

    segue_id: str
    source_id: str              # controller id the segue originates from
    destination_id: str         # controller id the segue navigates to
    kind: str                   # show / showDetail / presentModally / embed / ...
    identifier: Optional[str]
    line: int


@dataclass
class StoryboardModel:
    scenes: list[Scene] = field(default_factory=list)
    segues: list[Segue] = field(default_factory=list)
    initial_controller_id: Optional[str] = None


def _line_of_marker(content: str, marker: str) -> int:
    """1-based line of the first occurrence of ``marker`` in ``content``.

    Interface Builder object ids are unique within a document, so searching for
    ``id="<id>"`` yields a stable, deterministic line for a controller or segue.
    Returns 1 when the marker is absent (ElementTree strips no attributes we key
    on, so this is a defensive fallback, not an expected path).
    """
    idx = content.find(marker)
    if idx < 0:
        return 1
    return content.count("\n", 0, idx) + 1


def _local_tag(tag: str) -> str:
    """Strip any XML namespace from a tag (storyboards are namespace-free, but
    guard against a namespaced document rather than mis-tagging it)."""
    return tag.rsplit("}", 1)[-1]


def _is_controller(tag: str) -> bool:
    # Every Interface Builder controller element ends in "Controller"
    # (viewController, tableViewController, navigationController, tabBarController,
    # collectionViewController, splitViewController, pageViewController, ...).
    return _local_tag(tag).endswith("Controller")


def _scene_controller(scene: ET.Element) -> Optional[ET.Element]:
    """The primary controller element of a ``<scene>``.

    Prefers the object marked ``sceneMemberID="viewController"`` (Interface
    Builder's own marker for the scene's root controller); falls back to the
    first controller-tagged descendant so custom controller subclasses still
    resolve. Returns None for a scene that owns no controller (a placeholder).
    """
    for el in scene.iter():
        # A viewControllerPlaceholder is a REFERENCE to a scene in another
        # storyboard, not a screen of this one. Emitting it would create a
        # phantom screen named by its raw Interface Builder id (review
        # finding); cross-storyboard resolution is out of scope (card bound),
        # so placeholders are skipped and segues to them drop harmlessly.
        if el.tag == "viewControllerPlaceholder":
            continue
        if el.get("sceneMemberID") == "viewController" and el.get("id"):
            return el
    for el in scene.iter():
        if el.tag != "viewControllerPlaceholder" and _is_controller(el.tag) and el.get("id"):
            return el
    return None


def parse_storyboard(content: str) -> StoryboardModel:
    """Parse a storyboard/xib document into scenes and segues.

    Raises ``ElementTree.ParseError`` on malformed XML (the worker records the
    file failed). A well-formed document with no scenes returns an empty model.
    """
    root = ET.fromstring(content)
    model = StoryboardModel(initial_controller_id=root.get("initialViewController"))

    # Storyboards nest scenes under a <scenes> element; xibs put objects at the
    # top level with no <scene>. Handle both: collect explicit <scene> elements,
    # and if there are none, treat the whole document as one implicit scene.
    scenes = [el for el in root.iter() if _local_tag(el.tag) == "scene"]
    scene_elements = scenes if scenes else [root]

    controller_by_id: dict[str, Scene] = {}
    for scene_el in scene_elements:
        controller = _scene_controller(scene_el)
        if controller is None:
            continue
        cid = controller.get("id")
        if not cid or cid in controller_by_id:
            continue
        custom_class = controller.get("customClass")
        storyboard_id = controller.get("storyboardIdentifier")
        name = custom_class or storyboard_id or cid
        scene = Scene(
            controller_id=cid,
            name=name,
            custom_class=custom_class,
            storyboard_id=storyboard_id,
            tag=_local_tag(controller.tag),
            line=_line_of_marker(content, f'id="{cid}"'),
        )
        controller_by_id[cid] = scene
        model.scenes.append(scene)

        # Segues live anywhere under the controller subtree (on the controller,
        # a button, a table cell, ...). Every one of them originates from this
        # scene's controller, so attribute them to it.
        for el in controller.iter():
            if _local_tag(el.tag) != "segue":
                continue
            dest = el.get("destination")
            if not dest:
                continue
            sid = el.get("id") or f"{cid}->{dest}"
            model.segues.append(Segue(
                segue_id=sid,
                source_id=cid,
                destination_id=dest,
                kind=el.get("kind") or "show",
                identifier=el.get("identifier"),
                line=_line_of_marker(content, f'id="{sid}"' if el.get("id") else f'destination="{dest}"'),
            ))

    return model


def segue_edge_type(kind: str) -> str:
    """Map a segue ``kind`` to a Flow-lens relationship type.

    modal for presented segues, embed for containment, navigation otherwise.
    Kept next to the parser so the extraction and derivation tiers agree.
    """
    if kind in _MODAL_KINDS:
        return "modal"
    if kind in _EMBED_KINDS:
        return "embed"
    return "navigation"


class StoryboardParser(BaseParser):
    """Regex-tier parser (no tree-sitter) for storyboards and xibs.

    Emits one symbol per view controller. Imports, framework, ports and env
    vars are not meaningful for a storyboard, so the base no-op implementations
    stand. The flow model (scenes/segues) is emitted as signals, not symbols, so
    it can feed the Tier 3 storyboard pass; see this module's docstring.
    """

    def extract_nested_symbols(self, content: str, file_path: str) -> list[NestedSymbol]:
        try:
            model = parse_storyboard(content)
        except ET.ParseError:
            # Let the worker see the failure through the signal path instead;
            # symbols are best-effort. Re-raising here would also work, but the
            # worker parses signals after symbols, so raising is handled there.
            raise
        out: list[NestedSymbol] = []
        for scene in model.scenes:
            out.append(NestedSymbol(
                name=scene.name,
                kind="view-controller",
                line=scene.line,
                end_line=scene.line,
                visibility="internal",
                docstring=None,
                code_preview="",
                parent_index=None,
                path=(scene.name,),
                via_regex=True,
            ))
        return out
