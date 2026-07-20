"""P4-9: Storyboard/XIB and Core Data model parsers.

Three layers:
  1. Direct unit tests over the parser (scenes, segues, malformed XML) and the
     Core Data entity extractor (entities, attributes, relationships, toMany).
  2. End-to-end tests that run the real extract + derive tiers over the dedicated
     tests/fixtures/storyboard repo and assert the ledger dispositions, the
     view-controller symbols, the screen components with navigation/modal flow
     edges, and the Core Data data_entities.
  3. Fail-before / determinism: the fixtures ledger as non-source WITHOUT the
     v2-only recognition and as parsed WITH it (proving both directions), and two
     runs are byte-identical (invariant I4).

Everything is real fixture files, a real store, and no mocks. Parsing is pure
stdlib XML (regex tier), so these tests do not need the tree-sitter tier.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

import pytest

from analyzer.derive import derive_all
from analyzer.extract.entities import extract_schema_entities
from analyzer.extract.runner import _schema_only_language, extract_repo
from analyzer.extract.signals import _storyboard_flow
from analyzer.parsers.storyboard import (
    StoryboardParser,
    parse_storyboard,
    segue_edge_type,
)
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SB_FIXTURE = os.path.join(FIXTURES, "storyboard")
STORYBOARD = os.path.join(SB_FIXTURE, "App", "Base.lproj", "Main.storyboard")
CONTENTS = os.path.join(
    SB_FIXTURE, "App", "Model.xcdatamodeld", "Model.xcdatamodel", "contents"
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _derive(root=SB_FIXTURE, name="storyboard"):
    store = FactStore(":memory:")
    extract_repo(root, store)
    d, arch = derive_all(store, name)
    return store, d, arch


def _flow_components(components):
    out = []

    def walk(comps):
        for c in comps:
            if c["type"] in ("screen", "tab", "tab-container"):
                out.append(c)
            walk(c.get("children", []))

    walk(components)
    return out


# ---------------------------------------------------------------------------
# 1. Parser unit tests
# ---------------------------------------------------------------------------

def test_parse_storyboard_scenes():
    model = parse_storyboard(_read(STORYBOARD))
    names = [s.name for s in model.scenes]
    assert names == ["HomeViewController", "DetailViewController", "SettingsViewController"]
    home = model.scenes[0]
    # Name falls back through customClass; the binding class is recorded.
    assert home.custom_class == "HomeViewController"
    assert home.storyboard_id == "Home"
    assert home.controller_id == "home-vc-01"
    assert model.initial_controller_id == "home-vc-01"


def test_parse_storyboard_segues():
    model = parse_storyboard(_read(STORYBOARD))
    edges = {(s.source_id, s.destination_id): s for s in model.segues}
    # A segue nested inside a button and one directly on the controller both
    # attribute to the home controller (the scene's controller).
    show = edges[("home-vc-01", "detail-vc-02")]
    assert show.kind == "show" and show.identifier == "showDetail"
    modal = edges[("home-vc-01", "settings-vc-03")]
    assert modal.kind == "presentModally" and modal.identifier == "showSettings"


def test_segue_edge_type_mapping():
    assert segue_edge_type("show") == "navigation"
    assert segue_edge_type("showDetail") == "navigation"
    assert segue_edge_type("presentModally") == "modal"
    assert segue_edge_type("presentAsPopover") == "modal"
    assert segue_edge_type("embed") == "embed"
    assert segue_edge_type("relationship") == "embed"


def test_storyboard_parser_emits_view_controller_symbols():
    syms = StoryboardParser().extract_nested_symbols(_read(STORYBOARD), "Main.storyboard")
    assert [s.name for s in syms] == [
        "HomeViewController", "DetailViewController", "SettingsViewController"
    ]
    assert all(s.kind == "view-controller" for s in syms)
    assert all(s.line >= 1 for s in syms)


def test_xib_without_scenes_parses_as_single_scene():
    # A xib has no <scenes>; the whole document is one implicit scene.
    xib = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<document type="com.apple.InterfaceBuilder3.CocoaTouch.XIB">\n'
        '  <objects>\n'
        '    <viewController id="vc-1" customClass="CellController" sceneMemberID="viewController"/>\n'
        '  </objects>\n'
        '</document>\n'
    )
    model = parse_storyboard(xib)
    assert [s.name for s in model.scenes] == ["CellController"]
    assert model.segues == []


def test_malformed_storyboard_raises_parse_error():
    # The worker catches this and records the file failed (never a crash).
    with pytest.raises(ET.ParseError):
        parse_storyboard("<document><scenes><scene></document>")


def test_storyboard_flow_signals_only_for_storyboard_language():
    content = _read(STORYBOARD)
    assert _storyboard_flow(content, "swift") == []
    sigs = _storyboard_flow(content, "storyboard")
    kinds = [s.kind for s in sigs]
    assert kinds.count("storyboard_scene") == 3
    assert kinds.count("storyboard_segue") == 2
    scene = next(s for s in sigs if s.kind == "storyboard_scene")
    assert scene.value["custom_class"] == "HomeViewController"


# ---------------------------------------------------------------------------
# 2. Core Data entity extraction
# ---------------------------------------------------------------------------

def test_coredata_entities_attributes_and_relationships():
    ents = extract_schema_entities(_read(CONTENTS), "coredata", CONTENTS)
    by_name = {v["name"]: v for v, _ in ents}
    assert set(by_name) == {"Session", "Message"}
    assert all(v["framework"] == "coredata" and v["kind"] == "model" for v in by_name.values())

    session_fields = {f["name"]: f["type"] for f in by_name["Session"]["fields"]}
    assert session_fields["id"] == "UUID"
    assert session_fields["startedAt"] == "Date"
    # A to-many relationship is typed as a bracketed destination entity.
    assert session_fields["messages"] == "[Message]"

    message_fields = {f["name"]: f["type"] for f in by_name["Message"]["fields"]}
    assert message_fields["text"] == "String"
    # A to-one relationship is typed as the bare destination entity.
    assert message_fields["session"] == "Session"


def test_coredata_extractor_ignored_for_other_languages():
    assert extract_schema_entities(_read(CONTENTS), "swift", CONTENTS) == []


def test_malformed_coredata_raises_parse_error():
    with pytest.raises(ET.ParseError):
        extract_schema_entities('<model><entity name="X"></model>', "coredata", "contents")


# ---------------------------------------------------------------------------
# 3. v2-only recognition
# ---------------------------------------------------------------------------

def test_schema_only_language_recognizes_the_new_formats():
    assert _schema_only_language("a/Main.storyboard", "Main.storyboard", ".storyboard") == "storyboard"
    assert _schema_only_language("a/Cell.xib", "Cell.xib", ".xib") == "storyboard"
    assert _schema_only_language(
        "M.xcdatamodeld/M.xcdatamodel/contents", "contents", ""
    ) == "coredata"
    # An unrelated extension-less `contents` file is not Core Data.
    assert _schema_only_language("docs/contents", "contents", "") is None
    # An ordinary file is untouched.
    assert _schema_only_language("a/main.py", "main.py", ".py") is None


# ---------------------------------------------------------------------------
# 4. End-to-end extract + derive
# ---------------------------------------------------------------------------

def test_storyboard_and_coredata_ledger_as_parsed():
    store, _d, _arch = _derive()
    status = dict(store._conn.execute("SELECT path, parse_status FROM files").fetchall())
    assert status["App/Base.lproj/Main.storyboard"] == "parsed"
    assert status["App/Model.xcdatamodeld/Model.xcdatamodel/contents"] == "parsed"
    cov = dict(store._conn.execute("SELECT path, disposition FROM coverage").fetchall())
    assert cov["App/Base.lproj/Main.storyboard"] == "parsed"
    assert cov["App/Model.xcdatamodeld/Model.xcdatamodel/contents"] == "parsed"


def test_view_controller_symbols_land_in_store():
    store, _d, _arch = _derive()
    names = {
        r[0] for r in store._conn.execute(
            "SELECT name FROM symbols WHERE kind = 'view-controller'"
        ).fetchall()
    }
    assert names == {"HomeViewController", "DetailViewController", "SettingsViewController"}


def test_storyboard_produces_screen_components_and_flow_edges():
    _store, _d, arch = _derive()
    screens = _flow_components(arch["components"])
    by_name = {c["name"]: c for c in screens}
    assert {"HomeViewController", "DetailViewController", "SettingsViewController"} <= set(by_name)
    assert all(c["type"] == "screen" for c in screens)

    flow_edges = [r for r in arch["relationships"] if r["type"] in ("navigation", "modal", "embed")]
    labeled = {(r["type"], r["label"]) for r in flow_edges}
    assert ("navigation", "show") in labeled
    assert ("modal", "presentModally") in labeled
    # Each flow edge carries file+line evidence pointing at the storyboard.
    for r in flow_edges:
        ev = r.get("evidence") or []
        assert ev and ev[0]["file"] == "App/Base.lproj/Main.storyboard"


def test_coredata_entities_land_in_data_lens():
    _store, _d, arch = _derive()
    ents = {e["name"]: e for e in arch["data_entities"]}
    assert {"Session", "Message"} <= set(ents)
    assert ents["Session"]["framework"] == "coredata"
    session_fields = {f["name"] for f in ents["Session"]["fields"]}
    assert {"id", "startedAt", "messages"} <= session_fields


def test_custom_class_matches_swift_symbol_by_name():
    # The HomeViewController scene binds to the Swift class of the same name;
    # the screen component name equals the Swift symbol name so the two can be
    # matched by name (the card's custom-class binding).
    _store, _d, arch = _derive()
    swift_symbol_names = {s["name"] for s in arch["symbols"] if s.get("kind") == "class"}
    assert "HomeViewController" in swift_symbol_names
    screens = {c["name"] for c in _flow_components(arch["components"])}
    assert "HomeViewController" in screens


# ---------------------------------------------------------------------------
# 5. Fail-before proof and determinism
# ---------------------------------------------------------------------------

def test_fail_before_without_v2_recognition(monkeypatch):
    # WITHOUT the v2-only recognition, both files are unsupported extensions and
    # ledger as non-source (no symbols, no entities). This is the pre-P4-9 world.
    import analyzer.extract.runner as runner

    def _no_recognition(rel, fname, ext):
        return None

    monkeypatch.setattr(runner, "_schema_only_language", _no_recognition)
    store = FactStore(":memory:")
    extract_repo(SB_FIXTURE, store)
    cov = dict(store._conn.execute("SELECT path, disposition FROM coverage").fetchall())
    assert cov["App/Base.lproj/Main.storyboard"] == "excluded:unsupported_extension"
    assert cov["App/Model.xcdatamodeld/Model.xcdatamodel/contents"] == "excluded:unsupported_extension"
    vc = store._conn.execute(
        "SELECT COUNT(*) FROM symbols WHERE kind = 'view-controller'"
    ).fetchone()[0]
    assert vc == 0
    _d, arch = derive_all(store, "storyboard")
    assert [e for e in arch["data_entities"] if e["framework"] == "coredata"] == []


def test_after_with_v2_recognition_emits_symbols_entities_edges():
    # WITH the recognition (the default), the same fixtures parse and emit
    # symbols, entities, and flow edges. The other direction of the fail-before.
    _store, _d, arch = _derive()
    assert any(s.get("kind") == "view-controller" for s in arch["symbols"])
    assert any(e["framework"] == "coredata" for e in arch["data_entities"])
    assert any(
        r["type"] in ("navigation", "modal") for r in arch["relationships"]
    )


def test_extraction_and_derivation_are_deterministic():
    def run():
        store = FactStore(":memory:")
        extract_repo(SB_FIXTURE, store)
        _d, arch = derive_all(store, "storyboard")
        return json.dumps(
            {
                "entities": arch["data_entities"],
                "edges": [
                    (r["source"], r["target"], r["type"], r["label"])
                    for r in arch["relationships"]
                    if r["type"] in ("navigation", "modal", "embed")
                ],
            },
            sort_keys=True,
        )

    assert run() == run()


# ---------------------------------------------------------------------------
# Adversarial-review fixes (PR #48)
# ---------------------------------------------------------------------------


def test_placeholder_scene_is_skipped_not_a_phantom_screen():
    # A viewControllerPlaceholder references a scene in ANOTHER storyboard. It
    # must not become a screen (pre-fix it did, named by its raw IB id), and a
    # segue pointing at it must drop harmlessly rather than draw a junk edge.
    content = """<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.CocoaTouch.Storyboard.XIB" version="3.0">
  <scenes>
    <scene sceneID="s1">
      <objects>
        <viewController id="vc1" customClass="HomeController" sceneMemberID="viewController">
          <connections>
            <segue destination="ph1" kind="show" id="sg1"/>
          </connections>
        </viewController>
      </objects>
    </scene>
    <scene sceneID="s2">
      <objects>
        <viewControllerPlaceholder storyboardName="Other" id="ph1" sceneMemberID="viewController"/>
      </objects>
    </scene>
  </scenes>
</document>
"""
    from analyzer.parsers.storyboard import parse_storyboard

    model = parse_storyboard(content)
    names = [s.name for s in model.scenes]
    assert names == ["HomeController"], names
    assert all(s.controller_id != "ph1" for s in model.scenes)


def test_coredata_entity_line_anchors_on_the_entity_element():
    # An attribute elsewhere named like the entity must not steal the entity's
    # reported position (pre-fix: content.find('name="Session"') matched the
    # attribute on an earlier line).
    content = """<?xml version="1.0" encoding="UTF-8"?>
<model type="com.apple.IDECoreDataModeler.DataModel">
  <entity name="Account" syncable="YES">
    <attribute name="Session" attributeType="String"/>
  </entity>
  <entity name="Session" syncable="YES">
    <attribute name="startedAt" attributeType="Date"/>
  </entity>
</model>
"""
    from analyzer.extract.entities import _coredata_entities

    out = _coredata_entities(content)
    by_name = {e["name"]: start for e, start in out}
    assert "Session" in by_name
    marker = content.find('<entity name="Session"')
    assert by_name["Session"] == marker, (
        "the Session entity must anchor on its own <entity> element, "
        f"expected offset {marker}, got {by_name['Session']}"
    )


def test_unnamed_scene_is_named_after_its_storyboard_file(tmp_path):
    # A scene with no customClass and no storyboardIdentifier must read as the
    # storyboard's own name, not a raw Interface Builder id (dogfood finding:
    # the iOS demo's launch screen surfaced as "01J-lp-oVM").
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "LaunchScreen.storyboard").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.CocoaTouch.Storyboard.XIB" version="3.0">
  <scenes>
    <scene sceneID="s1">
      <objects>
        <viewController id="01J-lp-oVM" sceneMemberID="viewController"/>
      </objects>
    </scene>
  </scenes>
</document>
"""
    )
    from analyzer.derive import derive_all
    from analyzer.extract import extract_repo
    from analyzer.store import FactStore

    store = FactStore(":memory:")
    extract_repo(tmp_path, store)
    _d, arch = derive_all(store, "launch-demo")

    def walk(comps):
        for c in comps:
            yield c
            yield from walk(c.get("children") or [])

    screens = [c for c in walk(arch["components"]) if c.get("type") == "screen"]
    names = [c["name"] for c in screens]
    assert "LaunchScreen" in names, names
    assert "01J-lp-oVM" not in names, names
