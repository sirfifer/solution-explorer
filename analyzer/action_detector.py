"""UI action detection for buttons, gestures, toolbar items, and menus.

Detects user-interactive elements from source code across SwiftUI, UIKit,
and React/TypeScript codebases.
"""

import re
from pathlib import Path


class UIActionDetector:
    """Detect interactive UI actions from source code."""

    # --- SwiftUI patterns ---

    # Button("Label") { ... } or Button("Label", action: { ... })
    SWIFTUI_BUTTON_LABEL_RE = re.compile(r'Button\s*\(\s*"([^"]+)"')

    # Button(action: { handler() }) { Text("Label") }
    SWIFTUI_BUTTON_ACTION_RE = re.compile(
        r"Button\s*\(\s*action:\s*\{[^}]*?(\w+)\s*\(",
        re.DOTALL,
    )

    # .onTapGesture { handler() }
    ONTAP_RE = re.compile(r"\.onTapGesture\s*\{")

    # .onLongPressGesture { handler() }
    ONLONGPRESS_RE = re.compile(r"\.onLongPressGesture\s*(?:\([^)]*\)\s*)?\{")

    # ToolbarItem(placement: ...) { Button("Label") { } }
    TOOLBAR_ITEM_RE = re.compile(
        r'ToolbarItem\s*\([^)]*\)\s*\{[^}]*?Button\s*\(\s*"([^"]+)"',
        re.DOTALL,
    )

    # .contextMenu { Button("Label") { } }
    CONTEXT_MENU_BUTTON_RE = re.compile(
        r'\.contextMenu\s*\{[^}]*?Button\s*\(\s*"([^"]+)"',
        re.DOTALL,
    )

    # .swipeActions { Button("Label") { } }
    SWIPE_ACTION_RE = re.compile(
        r'\.swipeActions\s*(?:\([^)]*\))?\s*\{[^}]*?Button\s*\(\s*"([^"]+)"',
        re.DOTALL,
    )

    # .confirmationDialog("Title", ...)
    CONFIRMATION_DIALOG_RE = re.compile(r'\.confirmationDialog\s*\(\s*"([^"]+)"')

    # .alert("Title", ...)
    ALERT_RE = re.compile(r'\.alert\s*\(\s*"([^"]+)"')

    # --- UIKit patterns ---

    # @IBAction func name(...)
    IBACTION_RE = re.compile(r"@IBAction\s+func\s+(\w+)")

    # addTarget(self, action: #selector(name), ...)
    ADD_TARGET_RE = re.compile(r"addTarget\s*\([^)]*#selector\s*\(\s*(\w+)")

    # --- React/TypeScript patterns ---

    # onClick={handler} or onClick={() => handler()}
    ONCLICK_RE = re.compile(r"onClick\s*=\s*\{\s*(?:\(\)\s*=>\s*)?(\w+)")

    # onSubmit={handler}
    ONSUBMIT_RE = re.compile(r"onSubmit\s*=\s*\{\s*(?:\(\)\s*=>\s*)?(\w+)")

    # <button ...>Label</button>
    BUTTON_ELEMENT_RE = re.compile(r"<button[^>]*>\s*([^<]{1,50}?)\s*</button>", re.DOTALL)

    def detect(self, files: list[str], root: Path, language: str | None) -> list[dict]:
        """Detect UI actions in the given source files.

        Args:
            files: List of relative file paths belonging to a component.
            root: Root directory of the scanned codebase.
            language: Primary language of the component.

        Returns:
            List of action dicts with keys: label, action_type, handler, file, line, target_view.
        """
        if not language:
            return []

        actions: list[dict] = []
        for fpath in files:
            if language == "swift":
                if fpath.endswith(".swift"):
                    actions.extend(self._detect_swift_actions(fpath, root))
            elif language in ("typescript", "javascript", "tsx", "jsx"):
                if fpath.endswith((".ts", ".tsx", ".js", ".jsx")):
                    actions.extend(self._detect_react_actions(fpath, root))
        return actions

    def _read_file(self, file_path: str, root: Path) -> str | None:
        """Read file contents, returning None on failure."""
        try:
            return (root / file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _detect_swift_actions(self, file_path: str, root: Path) -> list[dict]:
        """Detect SwiftUI and UIKit actions in a Swift file."""
        content = self._read_file(file_path, root)
        if not content:
            return []

        actions: list[dict] = []
        lines = content.split("\n")

        # Line-by-line patterns (for precise line numbers)
        for i, line in enumerate(lines, 1):
            # Button("Label")
            for m in self.SWIFTUI_BUTTON_LABEL_RE.finditer(line):
                actions.append(self._make_action(
                    m.group(1), "button", file=file_path, line=i,
                ))

            # @IBAction func name(...)
            m = self.IBACTION_RE.search(line)
            if m:
                actions.append(self._make_action(
                    self._humanize(m.group(1)), "ibaction",
                    handler=m.group(1), file=file_path, line=i,
                ))

            # addTarget(... #selector(name))
            m = self.ADD_TARGET_RE.search(line)
            if m:
                actions.append(self._make_action(
                    self._humanize(m.group(1)), "button",
                    handler=m.group(1), file=file_path, line=i,
                ))

            # .onTapGesture
            if self.ONTAP_RE.search(line):
                actions.append(self._make_action(
                    "Tap gesture", "gesture", file=file_path, line=i,
                ))

            # .onLongPressGesture
            if self.ONLONGPRESS_RE.search(line):
                actions.append(self._make_action(
                    "Long press gesture", "gesture", file=file_path, line=i,
                ))

            # .confirmationDialog("Title")
            m = self.CONFIRMATION_DIALOG_RE.search(line)
            if m:
                actions.append(self._make_action(
                    m.group(1), "dialog", file=file_path, line=i,
                ))

            # .alert("Title")
            m = self.ALERT_RE.search(line)
            if m:
                actions.append(self._make_action(
                    m.group(1), "alert", file=file_path, line=i,
                ))

        # Multi-line patterns (scan full content for nested constructs)
        for m in self.TOOLBAR_ITEM_RE.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            actions.append(self._make_action(
                m.group(1), "toolbar", file=file_path, line=line_num,
            ))

        for m in self.CONTEXT_MENU_BUTTON_RE.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            actions.append(self._make_action(
                m.group(1), "menu", file=file_path, line=line_num,
            ))

        for m in self.SWIPE_ACTION_RE.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            actions.append(self._make_action(
                m.group(1), "swipe", file=file_path, line=line_num,
            ))

        return self._deduplicate(actions)

    def _detect_react_actions(self, file_path: str, root: Path) -> list[dict]:
        """Detect React event handlers in TypeScript/JavaScript files."""
        content = self._read_file(file_path, root)
        if not content:
            return []

        actions: list[dict] = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # onClick={handler}
            m = self.ONCLICK_RE.search(line)
            if m:
                handler = m.group(1)
                actions.append(self._make_action(
                    self._humanize(handler), "button",
                    handler=handler, file=file_path, line=i,
                ))

            # onSubmit={handler}
            m = self.ONSUBMIT_RE.search(line)
            if m:
                handler = m.group(1)
                actions.append(self._make_action(
                    self._humanize(handler), "form",
                    handler=handler, file=file_path, line=i,
                ))

        # <button>Label</button>
        for m in self.BUTTON_ELEMENT_RE.finditer(content):
            label = m.group(1).strip()
            if label and not label.startswith("{"):
                line_num = content[:m.start()].count("\n") + 1
                actions.append(self._make_action(
                    label, "button", file=file_path, line=line_num,
                ))

        return self._deduplicate(actions)

    @staticmethod
    def _make_action(
        label: str,
        action_type: str,
        handler: str | None = None,
        file: str = "",
        line: int = 0,
        target_view: str | None = None,
    ) -> dict:
        return {
            "label": label,
            "action_type": action_type,
            "handler": handler,
            "file": file,
            "line": line,
            "target_view": target_view,
        }

    @staticmethod
    def _humanize(name: str) -> str:
        """Convert a camelCase action name to a human-readable label."""
        result = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        # Strip common suffixes
        for suffix in ("Tapped", "Pressed", "Action", "Handler", "Clicked"):
            if result.endswith(suffix) and len(result) > len(suffix):
                result = result[: -len(suffix)]
        return result.strip().title()

    @staticmethod
    def _deduplicate(actions: list[dict]) -> list[dict]:
        """Remove duplicate actions at the same file:line with the same label."""
        seen: set[tuple[str, int, str]] = set()
        unique: list[dict] = []
        for a in actions:
            key = (a["file"], a["line"], a["label"])
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return unique
