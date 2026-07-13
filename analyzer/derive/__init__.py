"""Tier 3: derivation passes over the fact store (TARGET-ARCHITECTURE.md 4.3).

Component discovery, role classification, relationship inference, docs and
testing extraction, and the SwiftUI flow pipeline are re-expressed as passes
that read only the store (via :class:`~analyzer.derive.storeview.StoreView` and
its content-backed FS shim) and write only the store. Every derived edge carries
evidence and a confidence tier (invariant I3). A ``source_read_audit`` proves
the passes open zero source files.

This package depends on analyzer.store, analyzer.models, analyzer.constants,
analyzer.config_parsers, analyzer.swiftui_flow, analyzer.action_detector and
the standard library. It must never import scanner.py or incremental.py: the
old engine stays the default until the P4-7 cutover.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .context import Deriver
from .instrumentation import ReadAudit, source_read_audit
from .multi import derive_multi_from_config
from .pipeline import derive_all
from .storeview import StoreFS, StorePath, StoreView

__all__ = [
    "Deriver",
    "derive_all",
    "derive_multi_from_config",
    "StoreView",
    "StoreFS",
    "StorePath",
    "ReadAudit",
    "source_read_audit",
]
