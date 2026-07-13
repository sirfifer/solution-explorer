"""The v2 fact store: SQLite schema, symbol identity, and query surface.

This package is the foundation of the Program 2 engine (TARGET-ARCHITECTURE.md
sections 4.2 and 6). It depends only on the Python standard library and must
never import from scanner.py or incremental.py; the new engine's store tier is
independent of the old engine.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .db import FactStore, fts5_available
from .ids import (
    LOCAL_REPO,
    ROOT_COMPONENT,
    SymbolId,
    assign_symbol_ids,
    build_symbol_id,
    parse_symbol_id,
)
from .schema import SCHEMA_VERSION

__all__ = [
    "FactStore",
    "fts5_available",
    "SCHEMA_VERSION",
    "SymbolId",
    "build_symbol_id",
    "parse_symbol_id",
    "assign_symbol_ids",
    "LOCAL_REPO",
    "ROOT_COMPONENT",
]
