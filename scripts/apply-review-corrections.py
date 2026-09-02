#!/usr/bin/env python3
"""Apply an exact, auditable human-review correction file to a derived projection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.project.review import apply_review_corrections  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projection")
    parser.add_argument("corrections")
    args = parser.parse_args()
    result = apply_review_corrections(args.projection, args.corrections)
    print(f"Applied {len(result['applied'])} reviewed correction(s) to {args.projection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

