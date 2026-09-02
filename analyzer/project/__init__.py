"""Tier 4: projection from the fact store to the viewer delivery artifacts.

Generators that read the store-derived architecture (plus the store's coverage
ledger and enrichment overlay) and write the split manifest + detail shards,
the monolithic architecture.json, prebuilt search shards, the coverage report,
and the store-vs-previous-projection changelog (TARGET-ARCHITECTURE.md 4.4).

Schema-compatible with viewer/src/types.ts: every new field (evidence,
confidence and origin on relationships, coverage, nested-symbol parents, search
shards) is an optional key the existing viewer ignores. The
``safe_component_id`` shard-filename escaping is preserved (F-CRIT-5).

This package depends on analyzer.store, analyzer.derive, analyzer.extract,
analyzer.config_parsers, analyzer.models, and the standard library. It does not
import scanner.py or incremental.py: the old engine stays the default until the
P4-7 cutover.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .activity import build_activity
from .changelog import apply_changelog
from .coverage import build_coverage
from .frontdoor import FRONT_DOOR_VERSION, build_front_door, write_front_door
from .human_views import (
    build_orientation,
    build_security_view,
    build_support_view,
)
from .naming import safe_component_id
from .pipeline import (
    ProjectionResult,
    prepare_arch,
    project_all,
    project_monolith,
    project_split,
)
from .search_shards import DEFAULT_SHARD_SIZE, build_search_entries, shard_entries

__all__ = [
    "ProjectionResult",
    "prepare_arch",
    "project_all",
    "project_split",
    "project_monolith",
    "apply_changelog",
    "build_coverage",
    "build_activity",
    "build_orientation",
    "build_support_view",
    "build_security_view",
    "safe_component_id",
    "build_search_entries",
    "shard_entries",
    "DEFAULT_SHARD_SIZE",
    "build_front_door",
    "write_front_door",
    "FRONT_DOOR_VERSION",
]
