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


def _top_level_keys(head: bytes) -> set:
    """Top-level JSON object keys found in ``head``, string-and-depth aware.

    A tiny scanner, not a parser: tracks string state (with escapes) and brace
    or bracket depth, and records only keys that open at depth 1. Substring
    checks were the adversarial-review blocker: a user file merely CONTAINING
    the generator key names anywhere (nested, or as values) was pruned as
    generated while the tool still claimed 100 percent coverage. Depth
    awareness closes that; the head window covers enriched projections whose
    long architecture description pushes the generator keys deep into the file.
    """
    keys: set = set()
    depth = 0
    in_str = False
    esc = False
    token = bytearray()
    expecting_key = False
    for b in head:
        c = chr(b)
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
                if depth == 1 and expecting_key:
                    keys.add(token.decode("utf-8", "replace"))
            else:
                token.append(b)
            continue
        if c == '"':
            in_str = True
            token = bytearray()
            continue
        if c == "{":
            depth += 1
            expecting_key = True
        elif c == "}":
            depth -= 1
        elif c == "[":
            depth += 1
            expecting_key = False
        elif c == "]":
            depth -= 1
        elif c == ":":
            if depth == 1:
                expecting_key = False
        elif c == ",":
            if depth == 1:
                expecting_key = True
    return keys


# The head window for projection detection. 256 KB covers an enriched
# projection whose architecture-level description precedes the generator keys
# (the adversarial review proved 4 KB was escapable by a long description).
_PROJECTION_HEAD_BYTES = 262144


def _is_generated_projection(raw: bytes) -> bool:
    """True when ``raw`` is a solution-explorer architecture projection (D1).

    The tool emits its own datasets (the monolith ``architecture.json`` and the
    split ``manifest.json`` and detail shards). When such a dataset is
    committed into a repository the stats counted the tool's own output as
    source. The check requires the generator keys the projection always writes
    (``analyzer_version``, ``generated_at``, ``components``) as TOP-LEVEL keys
    of the JSON object, via a string-and-depth-aware scan of the head window.
    A user file that merely mentions those names nested or as values is NOT a
    projection and stays parsed (adversarial-review fix: the previous substring
    check silently pruned such files while claiming full coverage).
    """
    head = raw[:_PROJECTION_HEAD_BYTES].lstrip()
    if not head.startswith(b"{"):
        return False
    keys = _top_level_keys(head)
    return {"analyzer_version", "generated_at", "components"} <= keys


def _is_generated_dataset_dir(dirpath: str) -> bool:
    """True when ``dirpath`` is the tool's own emitted projection dataset (D1).

    Recognized by a projection ``manifest.json`` or ``architecture.json``
    sitting directly in the directory AND the split-output shard shape beside
    it (a ``data/`` or ``search/`` directory). Requiring the shard shape is the
    adversarial-review fix: a lone lookalike manifest must never prune a
    directory of real user source. The whole subtree is generated output, so
    it is pruned and ledgered as one ``excluded:skipped_directory`` row. Only
    the manifest head is read.
    """
    d = Path(dirpath)
    if not ((d / "data").is_dir() or (d / "search").is_dir()):
        return False
    for name in ("manifest.json", "architecture.json"):
        p = d / name
        if not p.is_file():
            continue
        try:
            with open(p, "rb") as fh:
                head = fh.read(_PROJECTION_HEAD_BYTES)
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
