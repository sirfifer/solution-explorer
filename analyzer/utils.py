"""Shared utility functions for the architecture analyzer."""

import os
import re
from pathlib import Path

from .constants import FRAMEWORK_PRIORITY, SKIP_DIR_SUFFIXES, SKIP_DIRS


def _should_skip_dir(name: str) -> bool:
    """Check if a directory should be skipped during traversal."""
    if name in SKIP_DIRS or name.startswith("."):
        return True
    # Skip prebuilt binary framework directories
    for suffix in SKIP_DIR_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


def _is_generated_projection(raw: bytes) -> bool:
    """True when ``raw`` is a solution-explorer architecture projection (D1).

    The tool emits its own datasets (the monolith ``architecture.json`` and the
    split ``manifest.json`` / detail shards). When such a dataset is committed
    into a repository (for example a demo dataset under ``viewer/public/``) the
    v1 path counted it as source, inflating the line and language stats by the
    tool's own output. This is a cheap, deterministic content check: a JSON
    object whose header declares the generator keys the projection always writes
    (``analyzer_version`` and ``generated_at``) plus a ``components`` collection.
    Only the head of the file is inspected because those keys are written at the
    top of the object, so the check stays O(1) regardless of dataset size. A
    hand-written config JSON (package.json, tsconfig.json) never carries all
    three markers, and no test fixture declares them, so fixtures stay parsed.
    """
    head = raw[:4096].lstrip()
    if not head.startswith(b"{"):
        return False
    return (
        b'"analyzer_version"' in head
        and b'"generated_at"' in head
        and b'"components"' in head
    )


def _is_generated_dataset_dir(dirpath: str) -> bool:
    """True when ``dirpath`` is the tool's own emitted projection dataset (D1).

    Recognized by a projection ``manifest.json`` or ``architecture.json`` sitting
    directly in the directory (the split-output shape puts ``manifest.json`` next
    to a ``data/`` shard directory). The whole subtree is generated output, so it
    is pruned and ledgered as one ``excluded:skipped_directory`` row rather than
    parsed as hundreds of source files. Only the manifest head is read.
    """
    for name in ("manifest.json", "architecture.json"):
        p = Path(dirpath) / name
        if not p.is_file():
            continue
        try:
            with open(p, "rb") as fh:
                head = fh.read(4096)
        except OSError:
            continue
        if _is_generated_projection(head):
            return True
    return False


def _is_vendored_repo(dirpath: str) -> bool:
    """Detect vendored third-party source repositories.

    These are full external repos checked into the project (e.g., llama.cpp).
    They have their own build system and many files that shouldn't be treated
    as part of the project's architecture.
    """
    p = Path(dirpath)
    # Must have its own build system (CMakeLists.txt or Makefile) AND
    # a LICENSE file (strong signal of external project)
    has_build = (p / "CMakeLists.txt").exists() or (p / "Makefile").exists()
    has_license = (p / "LICENSE").exists() or (p / "LICENSE.md").exists()
    if has_build and has_license:
        # Check that it has substantial code (not just a simple subproject)
        code_count = sum(
            1 for f in p.iterdir()
            if f.is_dir() and not _should_skip_dir(f.name)
        )
        return code_count >= 5  # vendored repos tend to have many subdirectories
    return False


def _is_conditional_import(content: str, framework: str) -> bool:
    """Check if 'import <framework>' only appears inside #if conditional blocks.

    Returns True if every occurrence of the import is preceded (on a nearby
    earlier line) by an #if directive, meaning it's a conditional/compat shim.
    """
    lines = content.split("\n")
    in_conditional = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#if "):
            in_conditional += 1
        elif stripped == "#endif":
            in_conditional = max(0, in_conditional - 1)
        elif stripped == f"import {framework}" and in_conditional == 0:
            # Unconditional import found
            return False
    # All occurrences were inside conditional blocks (or none existed)
    return True


def _framework_priority(fw: str) -> int:
    """Return priority rank for a framework (higher = more specific)."""
    return FRAMEWORK_PRIORITY.get(fw, 1)


def _name_from_server_script(fpath: str, content: str) -> str:
    """Derive a human-readable service name from a server script.

    Checks the module docstring first (e.g., "Remote Log Server"), then
    falls back to the filename (e.g., log_server.py -> "Log Server").
    """
    # Try to extract a name from the module docstring (first triple-quoted string)
    doc_match = re.match(r'(?:#[^\n]*\n)*\s*(?:\'\'\'|""")([^\'\"]+)', content)
    if doc_match:
        first_line = doc_match.group(1).strip().split("\n")[0].strip()
        # Clean up common prefixes/suffixes
        for prefix in ("UnaMentis ", "una-mentis "):
            if first_line.lower().startswith(prefix.lower()):
                first_line = first_line[len(prefix):]
        # Strip trailing qualifiers (e.g., "with Web Interface", "for XYZ")
        for sep in (" with ", " for ", " - ", " -- ", " :: "):
            idx = first_line.lower().find(sep)
            if idx > 5:  # Keep at least 5 chars of the core name
                first_line = first_line[:idx]
        # Truncate overly long descriptions
        if len(first_line) > 30:
            first_line = first_line[:30].rsplit(" ", 1)[0]
        if first_line and len(first_line) > 3:
            return first_line

    # Fall back to filename: log_server.py -> "Log Server"
    basename = os.path.basename(fpath).replace(".py", "")
    return basename.replace("_", " ").replace("-", " ").title()


def _extract_brace_body(content: str, start: int) -> str:
    """Extract the body enclosed in { } starting from position `start`.

    `start` should point at or before the opening brace.  Returns the text
    between (and including) the outermost braces, handling nested braces.
    """
    idx = content.find("{", start)
    if idx == -1:
        return ""
    depth = 0
    for i in range(idx, len(content)):
        ch = content[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[idx:i + 1]
    return content[idx:]  # unclosed, return what we have
