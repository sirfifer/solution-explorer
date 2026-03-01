"""Tests for analyzer.action_detector (UI action detection)."""

import tempfile
from pathlib import Path

import pytest

from analyzer.action_detector import UIActionDetector


@pytest.fixture
def detector():
    return UIActionDetector()


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write(tmpdir: Path, name: str, content: str) -> str:
    """Write a file and return its relative path."""
    path = tmpdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return name


# ---------------------------------------------------------------------------
# SwiftUI tests
# ---------------------------------------------------------------------------

class TestSwiftUIButtons:
    def test_button_with_string_label(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            Button("Save") {
                save()
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        assert len(actions) == 1
        assert actions[0]["label"] == "Save"
        assert actions[0]["action_type"] == "button"

    def test_multiple_buttons(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            Button("Save") { save() }
            Button("Cancel") { cancel() }
            Button("Delete") { delete() }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        labels = [a["label"] for a in actions]
        assert "Save" in labels
        assert "Cancel" in labels
        assert "Delete" in labels

    def test_button_line_numbers(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", 'line1\nButton("OK") { }\nline3\n')
        actions = detector.detect([f], tmpdir, "swift")
        assert len(actions) == 1
        assert actions[0]["line"] == 2


class TestSwiftUIToolbar:
    def test_toolbar_button(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Edit") { edit() }
                }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        # Should detect both the toolbar-level and button-level patterns
        types = {a["action_type"] for a in actions}
        assert "toolbar" in types

    def test_toolbar_label_extracted(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            ToolbarItem(placement: .bottomBar) {
                Button("Add Item") { addItem() }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        toolbar_actions = [a for a in actions if a["action_type"] == "toolbar"]
        assert len(toolbar_actions) == 1
        assert toolbar_actions[0]["label"] == "Add Item"


class TestSwiftUIContextMenu:
    def test_context_menu_button(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            .contextMenu {
                Button("Copy") { copy() }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        menu_actions = [a for a in actions if a["action_type"] == "menu"]
        assert len(menu_actions) == 1
        assert menu_actions[0]["label"] == "Copy"


class TestSwiftUISwipeActions:
    def test_swipe_action(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            .swipeActions(edge: .trailing) {
                Button("Delete") { delete() }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        swipe_actions = [a for a in actions if a["action_type"] == "swipe"]
        assert len(swipe_actions) == 1
        assert swipe_actions[0]["label"] == "Delete"

    def test_swipe_action_no_params(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            .swipeActions {
                Button("Archive") { archive() }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        swipe_actions = [a for a in actions if a["action_type"] == "swipe"]
        assert len(swipe_actions) == 1
        assert swipe_actions[0]["label"] == "Archive"


class TestSwiftUIGestures:
    def test_on_tap_gesture(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            Text("Hello")
                .onTapGesture {
                    handleTap()
                }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        gesture_actions = [a for a in actions if a["action_type"] == "gesture"]
        assert len(gesture_actions) == 1
        assert gesture_actions[0]["label"] == "Tap gesture"

    def test_on_long_press_gesture(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            Text("Hello")
                .onLongPressGesture {
                    handleLongPress()
                }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        gesture_actions = [a for a in actions if a["action_type"] == "gesture"]
        assert len(gesture_actions) == 1
        assert gesture_actions[0]["label"] == "Long press gesture"


class TestSwiftUIDialogsAlerts:
    def test_confirmation_dialog(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            .confirmationDialog("Delete Item", isPresented: $showDelete) {
                Button("Delete", role: .destructive) { delete() }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        dialog_actions = [a for a in actions if a["action_type"] == "dialog"]
        assert len(dialog_actions) == 1
        assert dialog_actions[0]["label"] == "Delete Item"

    def test_alert(self, detector, tmpdir):
        f = _write(tmpdir, "View.swift", '''
            .alert("Error Occurred", isPresented: $showError) {
                Button("OK") { }
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        alert_actions = [a for a in actions if a["action_type"] == "alert"]
        assert len(alert_actions) == 1
        assert alert_actions[0]["label"] == "Error Occurred"


# ---------------------------------------------------------------------------
# UIKit tests
# ---------------------------------------------------------------------------

class TestUIKitActions:
    def test_ibaction(self, detector, tmpdir):
        f = _write(tmpdir, "ViewController.swift", '''
            @IBAction func saveTapped(_ sender: UIButton) {
                save()
            }
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        ib_actions = [a for a in actions if a["action_type"] == "ibaction"]
        assert len(ib_actions) == 1
        assert ib_actions[0]["handler"] == "saveTapped"

    def test_add_target(self, detector, tmpdir):
        f = _write(tmpdir, "ViewController.swift", '''
            button.addTarget(self, action: #selector(handleRefresh), for: .touchUpInside)
        ''')
        actions = detector.detect([f], tmpdir, "swift")
        button_actions = [a for a in actions if a["handler"] == "handleRefresh"]
        assert len(button_actions) == 1
        assert button_actions[0]["action_type"] == "button"


# ---------------------------------------------------------------------------
# React/TypeScript tests
# ---------------------------------------------------------------------------

class TestReactActions:
    def test_onclick_handler(self, detector, tmpdir):
        f = _write(tmpdir, "Component.tsx", '''
            <div onClick={handleClick}>Click me</div>
        ''')
        actions = detector.detect([f], tmpdir, "typescript")
        assert len(actions) >= 1
        click_actions = [a for a in actions if a["handler"] == "handleClick"]
        assert len(click_actions) == 1
        assert click_actions[0]["action_type"] == "button"

    def test_onsubmit_handler(self, detector, tmpdir):
        f = _write(tmpdir, "Form.tsx", '''
            <form onSubmit={handleSubmit}>
        ''')
        actions = detector.detect([f], tmpdir, "typescript")
        form_actions = [a for a in actions if a["action_type"] == "form"]
        assert len(form_actions) == 1
        assert form_actions[0]["handler"] == "handleSubmit"

    def test_button_element(self, detector, tmpdir):
        f = _write(tmpdir, "Page.tsx", '''
            <button className="btn">Submit</button>
        ''')
        actions = detector.detect([f], tmpdir, "typescript")
        button_actions = [a for a in actions if a["label"] == "Submit"]
        assert len(button_actions) == 1

    def test_ignores_jsx_expression_in_button(self, detector, tmpdir):
        f = _write(tmpdir, "Page.tsx", '''
            <button>{label}</button>
        ''')
        actions = detector.detect([f], tmpdir, "typescript")
        # Should NOT match because content starts with {
        button_actions = [a for a in actions if a["action_type"] == "button"]
        assert len(button_actions) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_actions_in_empty_file(self, detector, tmpdir):
        f = _write(tmpdir, "Empty.swift", "")
        actions = detector.detect([f], tmpdir, "swift")
        assert actions == []

    def test_no_actions_for_unsupported_language(self, detector, tmpdir):
        f = _write(tmpdir, "main.go", 'func main() { fmt.Println("hello") }')
        actions = detector.detect([f], tmpdir, "go")
        assert actions == []

    def test_no_language_returns_empty(self, detector, tmpdir):
        f = _write(tmpdir, "file.txt", "Button(\"test\")")
        actions = detector.detect([f], tmpdir, None)
        assert actions == []

    def test_nonexistent_file_handled(self, detector, tmpdir):
        actions = detector.detect(["nonexistent.swift"], tmpdir, "swift")
        assert actions == []

    def test_deduplication(self, detector, tmpdir):
        # Same button on same line should not produce duplicates
        f = _write(tmpdir, "View.swift", 'Button("Save") { save() }')
        actions = detector.detect([f], tmpdir, "swift")
        assert len(actions) == 1

    def test_only_scans_matching_extensions(self, detector, tmpdir):
        # A .py file should not be scanned for swift patterns
        f = _write(tmpdir, "script.py", 'Button("Save")')
        actions = detector.detect([f], tmpdir, "swift")
        assert actions == []

    def test_file_path_stored(self, detector, tmpdir):
        f = _write(tmpdir, "src/MyView.swift", 'Button("Go") { go() }')
        actions = detector.detect([f], tmpdir, "swift")
        assert actions[0]["file"] == "src/MyView.swift"


class TestHumanize:
    def test_camel_case(self):
        assert UIActionDetector._humanize("handleSaveAction") == "Handle Save"

    def test_simple_name(self):
        assert UIActionDetector._humanize("refresh") == "Refresh"

    def test_tapped_suffix(self):
        assert UIActionDetector._humanize("deleteTapped") == "Delete"
