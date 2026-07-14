"""Tier 1: the parallel extraction tier (TARGET-ARCHITECTURE.md section 4.1).

Files are parsed once, in parallel, and cached by (content hash, parser
version). Each file yields a :class:`~analyzer.extract.facts.FileFacts` record
carrying nested symbols (with parent references and exact ranges) and signals
(the raw observations Tier 3 derivation joins over). The runner writes those
facts and a coverage-ledger row for every file into the v2 fact store.

This package depends only on analyzer.parsers, analyzer.constants,
analyzer.store, and the Python standard library. It must never import
scanner.py or incremental.py: the old engine stays untouched and default until
the P4-7 cutover.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .activity import ActivityResult, extract_activity
from .facts import FileFacts, SignalRecord
from .runner import EXTRACT_TIER, ExtractionResult, extract_repo

__all__ = [
    "FileFacts",
    "SignalRecord",
    "ExtractionResult",
    "extract_repo",
    "EXTRACT_TIER",
    "ActivityResult",
    "extract_activity",
]
