#!/usr/bin/env python3
"""Rebuild orientation.json for a projection that already exists.

A full reprojection of VS Code takes minutes. Every change to the portrait, the
identity statement or the question routes then costs minutes before anyone can
look at it on the real subject, which is how a front-door change gets shipped
having only ever been seen against a fixture. The orientation sidecar is a pure
function of manifest.json and the three optional sidecars beside it, so it can
be rebuilt in seconds without touching the parser.

Use --check in a verification pass: it prints the unified diff between what is
on disk and what the current code would write, and exits 1 when they differ.

A projection whose manifest carries no ``identity`` key predates the identity
derive pass. Nothing here can invent those facts, so the script refuses with
exit 2 and asks for a real reprojection rather than writing a sidecar that
quietly claims the subject has no form factors.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.project.human_views import (  # noqa: E402 - repo root must precede local import
    ORIENTATION_FILENAME,
    SECURITY_FILENAME,
    SUPPORT_FILENAME,
    build_orientation,
    write_human_view,
)

COVERAGE_FILENAME = "coverage.json"
MANIFEST_FILENAME = "manifest.json"

EXIT_OK = 0
EXIT_DIFFERS = 1
EXIT_PREDATES_IDENTITY = 2


def _load(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _serialized(document: dict, indent: int = 2) -> str:
    """Exactly what write_human_view puts on disk, as text."""
    return json.dumps(document, indent=indent, default=str, sort_keys=True)


def reorient(projection: Path, *, check: bool = False) -> int:
    manifest = _load(projection / MANIFEST_FILENAME)
    if manifest is None:
        print(f"error: no {MANIFEST_FILENAME} in {projection}", file=sys.stderr)
        return EXIT_PREDATES_IDENTITY
    if "identity" not in manifest:
        print(
            "warning: projection predates the identity pass; reproject with analyze.py",
            file=sys.stderr,
        )
        return EXIT_PREDATES_IDENTITY

    orientation = build_orientation(
        manifest,
        coverage=_load(projection / COVERAGE_FILENAME),
        support=_load(projection / SUPPORT_FILENAME),
        security=_load(projection / SECURITY_FILENAME),
    )
    target = projection / ORIENTATION_FILENAME
    rebuilt = _serialized(orientation)

    if not check:
        write_human_view(orientation, target)
        print(f"[reorient] wrote {target}")
        return EXIT_OK

    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    if existing.rstrip("\n") == rebuilt.rstrip("\n"):
        print(f"[reorient] {target} is up to date")
        return EXIT_OK
    diff = difflib.unified_diff(
        existing.splitlines(keepends=True),
        f"{rebuilt}\n".splitlines(keepends=True),
        fromfile=f"{target} (on disk)",
        tofile=f"{target} (rebuilt)",
    )
    sys.stdout.writelines(diff)
    return EXIT_DIFFERS


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("projection", help="projection directory holding manifest.json")
    parser.add_argument(
        "--check", action="store_true",
        help="print a unified diff instead of writing; exit 1 when it differs",
    )
    args = parser.parse_args(argv)
    return reorient(Path(args.projection).resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
