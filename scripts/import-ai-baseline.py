#!/usr/bin/env python3
"""Import an ai_enhance baseline architecture.json into a v2 store as enrichment.

This is the migration utility for P7-1: it moves human-curated AI content from
the legacy inline ``ai_enhance`` shape (the committed root baseline, or any
architecture.json a downstream deploy still carries) into provenance-stamped
enrichment rows in a v2 fact store. Each target is stamped with the store's
current digest and marked as imported (commit unknown); see
analyzer/enrich/importer.py for why the current digest is the honest choice.

The store must already be derived for the same codebase (run the v2 analyzer
with ``--store <path>`` first). This script does not build the store.

Usage:
    python3 scripts/import-ai-baseline.py \\
        --baseline architecture.json \\
        --store .solution-explorer/index.db
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer.enrich import import_ai_baseline  # noqa: E402
from analyzer.store import FactStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="architecture.json with ai_enhance data")
    parser.add_argument("--store", required=True, help="v2 fact store (already derived)")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    store_path = Path(args.store)

    if not baseline_path.is_file():
        print(f"Baseline not found: {baseline_path}", file=sys.stderr)
        return 1
    if not store_path.is_file():
        print(f"Store not found: {store_path} (run the v2 analyzer with --store first)", file=sys.stderr)
        return 1

    with open(baseline_path, "r", encoding="utf-8") as fh:
        baseline = json.load(fh)

    with FactStore(store_path) as store:
        result = import_ai_baseline(store, baseline)

    print(
        f"Imported {result.components_imported} components, "
        f"{result.relationships_imported} relationships, "
        f"architecture={'yes' if result.architecture_imported else 'no'}."
    )
    if result.components_unmatched:
        print(
            f"  WARNING: {len(result.components_unmatched)} component(s) had no "
            f"target in the store (not imported, never guessed): "
            f"{result.components_unmatched[:10]}",
            file=sys.stderr,
        )
    if result.relationships_unmatched:
        print(
            f"  WARNING: {len(result.relationships_unmatched)} relationship(s) had no "
            f"target in the store: {result.relationships_unmatched[:10]}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
