"""The Solution Explorer MCP server (TARGET-ARCHITECTURE section 8, LENS-DESIGN
section 6): a curated, nine-tool query surface over the v2 fact store for AI
agents.

Packaging decision (recorded, TASKS.md P8-1): this ships INSIDE the
``solution-explorer`` PyPI package as the ``analyzer.mcp`` subpackage with a
console entry point ``solution-explorer-mcp``. It is a thin read layer over
``analyzer.store``; a separate package would duplicate that dependency and
invite version skew. An optional ``mcp`` dependency group is reserved for the
official-SDK upgrade path, but the shipped server needs no third-party dependency.

All queries are pure store reads: no writes, no LLM calls at query time
(invariant I9). Responses cite evidence and mark confidence and AI staleness
(invariants I3, I5).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .cli import main

__all__ = ["main", "__version__"]
