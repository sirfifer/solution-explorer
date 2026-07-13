"""Zero-source-reads audit for Tier 3 derivation.

Derivation must read only the store (TARGET-ARCHITECTURE.md 4.3, invariant:
"An instrumentation hook counts source-file reads during derivation; the count
must be zero"). This module provides a context manager that patches the file-
read entry points and counts any call that touches a real source file, so a
test can assert the count is zero.

The store itself is SQLite, whose reads go through the C library and never
through ``builtins.open`` or ``pathlib.Path.read_*``, so store access is not
counted. Derivation reads file content from the store's extraction cache via
the ``StoreFS`` shim (see storeview.py), which returns in-memory strings and
never calls these entry points. Any real disk read during derivation is
therefore a defect and is caught here.
"""

from __future__ import annotations

import builtins
import io
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReadAudit:
    """Records source-file read attempts observed during derivation."""

    count: int = 0
    paths: list[str] = field(default_factory=list)

    def _record(self, path: object) -> None:
        self.count += 1
        self.paths.append(str(path))


@contextmanager
def source_read_audit(*, strict: bool = False):
    """Count (or forbid) real source-file reads within the block.

    Patches ``builtins.open`` and ``pathlib.Path.read_text`` /
    ``pathlib.Path.read_bytes`` / ``pathlib.Path.open``. Yields a
    :class:`ReadAudit` whose ``count`` a test asserts is zero. In-memory
    streams (``io.StringIO`` / ``io.BytesIO``) are never file reads, so they
    are ignored. With ``strict=True`` a read raises immediately instead of
    being tallied, which is useful to pinpoint the offending call site.
    """
    audit = ReadAudit()
    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_path_open = Path.open

    def guard(target: object) -> None:
        audit._record(target)
        if strict:
            raise AssertionError(f"derivation read a source file: {target!r}")

    def patched_open(file, *args, **kwargs):
        if not isinstance(file, (io.StringIO, io.BytesIO)):
            guard(file)
        return real_open(file, *args, **kwargs)

    def patched_read_text(self, *args, **kwargs):
        guard(self)
        return real_read_text(self, *args, **kwargs)

    def patched_read_bytes(self, *args, **kwargs):
        guard(self)
        return real_read_bytes(self, *args, **kwargs)

    def patched_path_open(self, *args, **kwargs):
        guard(self)
        return real_path_open(self, *args, **kwargs)

    builtins.open = patched_open
    Path.read_text = patched_read_text
    Path.read_bytes = patched_read_bytes
    Path.open = patched_path_open
    try:
        yield audit
    finally:
        builtins.open = real_open
        Path.read_text = real_read_text
        Path.read_bytes = real_read_bytes
        Path.open = real_path_open
