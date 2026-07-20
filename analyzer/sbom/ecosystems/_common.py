"""Shared helpers for the per-ecosystem manifest parsers.

Every parser reads text files under the scan root deterministically and never
runs a package manager or touches the network. These helpers cover the two
things they all need: reading a manifest's text safely, and finding the line a
declaration sits on so evidence can carry a file:line pointer where it is cheap.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

__all__ = ["read_text", "join_rel", "find_line", "find_line_regex"]


def read_text(path: Path) -> str:
    """Read a manifest as UTF-8, replacing undecodable bytes. Raises on OSError.

    The parsers catch the raise and turn it into a loud ParseWarning, so a
    genuinely unreadable manifest is reported, never silently skipped.
    """
    return path.read_text(encoding="utf-8", errors="replace")


def join_rel(dirpath: str, filename: str) -> str:
    """Join a relative directory and a filename with forward slashes.

    ``dirpath`` is "" for the scan root. The result is the manifest's path
    relative to the root, which is what evidence carries.
    """
    return f"{dirpath}/{filename}" if dirpath else filename


def find_line(lines: list[str], needle: str) -> Optional[int]:
    """Return the 1-based line number of the first line containing ``needle``.

    Used to anchor a dependency's evidence to the manifest line that names it.
    Best effort: returns None when the token is not found on its own line (for
    example a dependency read out of a nested lockfile structure), and evidence
    then carries just the file. Cheap: a single linear scan.
    """
    if not needle:
        return None
    for i, line in enumerate(lines):
        if needle in line:
            return i + 1
    return None


def find_line_regex(lines: list[str], pattern: re.Pattern) -> Optional[int]:
    """Return the 1-based line number of the first line matching ``pattern``."""
    for i, line in enumerate(lines):
        if pattern.search(line):
            return i + 1
    return None
