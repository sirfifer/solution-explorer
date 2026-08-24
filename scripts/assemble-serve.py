#!/usr/bin/env python3
"""Assemble a servable viewer bundle for a subject, ready for the crawl.

The crawl needs two things served together from one origin: the built viewer,
and the projection it should load. This puts them together.

Two decisions worth stating, because both were mistakes at some point today:

  The viewer is BUILT, never assumed built. A crawl against a stale bundle
  tests code that no longer exists, and the failure looks exactly like a real
  defect. Pass --no-build only when you have just built it yourself.

  The projection is SYMLINKED, not copied. VS Code's is 268 MB, and copying it
  for every crawl is a minute of disk churn per run for no benefit. Python's
  http.server follows symlinks, so the served bytes are identical.

The layout mirrors what scripts/gui-datasets.py assemble produces, so the two
harnesses serve datasets the same way and a bundle from either is crawlable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VIEWER = REPO_ROOT / "viewer"
DIST = VIEWER / "dist"
SERVE_ROOT = REPO_ROOT / ".testboard" / "serve"

# Data baked into the viewer's own public/ directory. It has to go, or the app
# loads the repo's committed dataset instead of the subject under test, and the
# crawl silently checks the wrong thing.
BAKED = ("architecture", "architecture.json", "ai.json", "llms.txt")


def _corpus_dir() -> Path:
    override = os.environ.get("DEMO_CORPUS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "dev" / ".demo-corpus"


def resolve_projection(slug: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (_corpus_dir() / "_out" / slug / "architecture").resolve()


def build_viewer() -> None:
    print("[assemble] building the viewer")
    subprocess.run(["npm", "run", "build"], cwd=str(VIEWER), check=True)


def assemble(slug: str, projection: Path, build: bool = True) -> Path:
    if not projection.is_dir():
        sys.exit(
            f"error: no projection at {projection}\n"
            f"Run an analyze first: python3 scripts/demo-site.py analyze {slug}"
        )
    if not (projection / "manifest.json").is_file():
        sys.exit(
            f"error: {projection} has no manifest.json, so it is not a split "
            f"projection. The crawl only covers split mode."
        )
    if build:
        build_viewer()
    if not (DIST / "index.html").is_file():
        sys.exit(f"error: no built viewer at {DIST}. Run: cd viewer && npm run build")

    serve = SERVE_ROOT / slug
    if serve.exists():
        shutil.rmtree(serve)
    serve.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DIST, serve)

    for name in BAKED:
        target = serve / name
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    (serve / "architecture").symlink_to(projection)

    manifest = json.loads((projection / "manifest.json").read_text(encoding="utf-8"))
    components = len(manifest.get("component_detail_index") or {})
    print(f"[assemble] {slug}: {serve}")
    print(f"[assemble]   projection {projection} ({components} components)")
    print(f"[assemble]   serve with: python3 -m http.server <port> --directory {serve}")
    return serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug")
    parser.add_argument("--projection", default=None,
                        help="projection directory (default: the corpus output for this slug)")
    parser.add_argument("--no-build", action="store_true",
                        help="skip the viewer build; only when you just built it yourself")
    args = parser.parse_args(argv)
    assemble(args.slug, resolve_projection(args.slug, args.projection), build=not args.no_build)
    return 0


if __name__ == "__main__":
    sys.exit(main())
