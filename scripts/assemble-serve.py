#!/usr/bin/env python3
"""Assemble a servable viewer bundle for a subject, ready for the crawl.

The crawl needs two things served together from one origin: the built viewer,
and the projection it should load. This puts them together.

Two decisions worth stating, because both were mistakes at some point today:

  The viewer is BUILT, never assumed built. A crawl against a stale bundle
  tests code that no longer exists, and the failure looks exactly like a real
  defect. Pass --no-build only when you have just built it yourself.

  The projection is SYMLINKED, not copied. private large-repository validation corpus's is 268 MB, and copying it
  for every crawl is a minute of disk churn per run for no benefit. Python's
  http.server follows symlinks, so the served bytes are identical. When a
  canonical projection predates the human-first sidecars, assembly creates a
  small derived overlay: canonical files remain symlinks and only the three
  deterministic sidecars are newly written. The source projection is never
  modified.

The layout mirrors what scripts/gui-datasets.py assemble produces, so the two
harnesses serve datasets the same way and a bundle from either is crawlable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.project.human_views import (  # noqa: E402 - repo root must precede local import
    ORIENTATION_FILENAME,
    SECURITY_FILENAME,
    SUPPORT_FILENAME,
    build_orientation,
    build_security_view,
    build_support_view,
    write_human_view,
)
from analyzer.project.review import apply_review_corrections  # noqa: E402

VIEWER = REPO_ROOT / "viewer"
DIST = VIEWER / "dist"
SERVE_ROOT = REPO_ROOT / ".testboard" / "serve"
DERIVED_ROOT = REPO_ROOT / ".testboard" / "derived"

# Data baked into the viewer's own public/ directory. It has to go, or the app
# loads the repo's committed dataset instead of the subject under test, and the
# crawl silently checks the wrong thing.
BAKED = ("architecture", "architecture.json", "ai.json", "llms.txt")
UPSTREAM_LICENSE_CANDIDATES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")
UPSTREAM_NOTICE_CANDIDATES = ("NOTICE", "NOTICE.txt", "ThirdPartyNotices.txt")


def _corpus_dir() -> Path:
    override = os.environ.get("DEMO_CORPUS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "dev" / ".demo-corpus"


def resolve_projection(slug: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (_corpus_dir() / "_out" / slug / "architecture").resolve()


def build_viewer(slug: str) -> None:
    """Build the viewer, in this subject's own mode when it has one.

    A demo can pin build-time defaults (its theme, for one) in
    ``viewer/.env.<slug>-demo``, and Vite loads that file only when built with
    the matching ``--mode``. A plain ``npm run build`` silently ignores it, so
    the bundle served for review is not the bundle the demo is meant to be: the
    VS Code demo lost its Atlas default exactly that way.
    """
    mode = f"{slug}-demo"
    if (VIEWER / f".env.{mode}").is_file():
        print(f"[assemble] building the viewer in {mode} mode")
        subprocess.run(
            ["npx", "vite", "build", "--mode", mode], cwd=str(VIEWER), check=True,
        )
        return
    print("[assemble] building the viewer")
    subprocess.run(["npm", "run", "build"], cwd=str(VIEWER), check=True)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: cannot read projection document {path}: {exc}")


def _scrub_activity_identifiers(value):
    """Replace email author keys with stable, non-reversible public ids."""
    if isinstance(value, list):
        return [_scrub_activity_identifiers(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        # Git history occasionally carries an email as the display name too,
        # including GitHub noreply addresses. Neither identity field in a
        # review bundle should expose it.
        if key in {"author_key", "author_name"} and isinstance(item, str) and "@" in item:
            digest = hashlib.sha256(item.strip().lower().encode("utf-8")).hexdigest()[:12]
            result[key] = f"contributor-{digest}"
        else:
            result[key] = _scrub_activity_identifiers(item)
    return result


def _first_file(root: Path, names: tuple[str, ...]) -> Path | None:
    return next((root / name for name in names if (root / name).is_file()), None)


def _projection_with_human_views(
    slug: str,
    projection: Path,
    corrections: Path | None = None,
    publication: Path | None = None,
    upstream_source: Path | None = None,
    scrub_activity: bool = False,
) -> tuple[Path, list[str]]:
    """Return a projection root with all human-view sidecars available.

    Existing canonical sidecars are used as-is. If any are absent, build a
    derived directory whose canonical entries are absolute symlinks and whose
    missing sidecars are pure, deterministic derivatives of manifest.json and
    coverage.json. This keeps the canonical run byte-for-byte immutable.
    """
    sidecars = (ORIENTATION_FILENAME, SUPPORT_FILENAME, SECURITY_FILENAME)
    missing = [name for name in sidecars if not (projection / name).is_file()]
    activity_path = projection / "activity.json"
    if not missing and corrections is None and publication is None and upstream_source is None and not scrub_activity:
        return projection, []
    generated_sidecars = list(missing)
    if corrections is not None and ORIENTATION_FILENAME not in generated_sidecars:
        generated_sidecars.append(ORIENTATION_FILENAME)

    derived = DERIVED_ROOT / slug / "architecture"
    if derived.exists() or derived.is_symlink():
        if derived.is_symlink() or derived.is_file():
            derived.unlink()
        else:
            shutil.rmtree(derived)
    derived.mkdir(parents=True, exist_ok=True)

    for source in sorted(projection.iterdir(), key=lambda path: path.name):
        target = derived / source.name
        if corrections is not None and source.name == "manifest.json":
            shutil.copy2(source, target)
        elif corrections is not None and source.name == ORIENTATION_FILENAME:
            continue
        elif scrub_activity and source == activity_path:
            activity = _scrub_activity_identifiers(_load_json(source))
            write_human_view(activity, target)
            generated_sidecars.append("activity.json (privacy-scrubbed)")
        elif publication is not None and source.name == "publication.json":
            continue
        else:
            target.symlink_to(source.resolve())

    if publication is not None:
        shutil.copy2(publication, derived / "publication.json")
        generated_sidecars.append("publication.json")

    if upstream_source is not None:
        license_path = _first_file(upstream_source, UPSTREAM_LICENSE_CANDIDATES)
        if license_path is None:
            sys.exit(f"error: no upstream license found in {upstream_source}")
        shutil.copy2(license_path, derived / "UPSTREAM-LICENSE.txt")
        generated_sidecars.append("UPSTREAM-LICENSE.txt")
        notice_path = _first_file(upstream_source, UPSTREAM_NOTICE_CANDIDATES)
        if notice_path is not None:
            shutil.copy2(notice_path, derived / notice_path.name)
            generated_sidecars.append(notice_path.name)

    if corrections is not None:
        apply_review_corrections(derived, corrections)

    manifest = _load_json(derived / "manifest.json")
    coverage_path = projection / "coverage.json"
    coverage = _load_json(coverage_path) if coverage_path.is_file() else None
    support = (
        _load_json(projection / SUPPORT_FILENAME)
        if (projection / SUPPORT_FILENAME).is_file()
        else build_support_view(manifest)
    )
    security = (
        _load_json(projection / SECURITY_FILENAME)
        if (projection / SECURITY_FILENAME).is_file()
        else build_security_view(manifest)
    )
    generated = {
        SUPPORT_FILENAME: support,
        SECURITY_FILENAME: security,
        ORIENTATION_FILENAME: build_orientation(
            manifest,
            coverage=coverage,
            support=support,
            security=security,
        ),
    }
    for name in (entry for entry in generated_sidecars if entry in generated):
        write_human_view(generated[name], derived / name)
    return derived, generated_sidecars


def assemble(
    slug: str,
    projection: Path,
    build: bool = True,
    corrections: Path | None = None,
    publication: Path | None = None,
    upstream_source: Path | None = None,
    scrub_activity: bool = False,
) -> Path:
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
        build_viewer(slug)
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

    served_projection, generated_sidecars = _projection_with_human_views(
        slug, projection, corrections, publication, upstream_source, scrub_activity
    )
    (serve / "architecture").symlink_to(served_projection)

    manifest = _load_json(projection / "manifest.json")
    components = len(manifest.get("component_detail_index") or {})
    print(f"[assemble] {slug}: {serve}")
    print(f"[assemble]   projection {projection} ({components} components)")
    if served_projection != projection:
        print(f"[assemble]   derived overlay {served_projection}")
        print(f"[assemble]   deterministic sidecars {', '.join(generated_sidecars)}")
    print(f"[assemble]   serve with: python3 -m http.server <port> --directory {serve}")
    return serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug")
    parser.add_argument("--projection", default=None,
                        help="projection directory (default: the corpus output for this slug)")
    parser.add_argument("--no-build", action="store_true",
                        help="skip the viewer build; only when you just built it yourself")
    parser.add_argument("--corrections", default=None,
                        help="exact review-correction JSON applied only to the derived assembly")
    parser.add_argument("--publication", default=None,
                        help="validated publication.json copied only to the derived assembly")
    parser.add_argument("--upstream-source", default=None,
                        help="subject checkout supplying the upstream license and notice")
    parser.add_argument("--scrub-activity", action="store_true",
                        help="replace contributor email keys with stable pseudonymous ids")
    args = parser.parse_args(argv)
    assemble(
        args.slug,
        resolve_projection(args.slug, args.projection),
        build=not args.no_build,
        corrections=Path(args.corrections).resolve() if args.corrections else None,
        publication=Path(args.publication).resolve() if args.publication else None,
        upstream_source=Path(args.upstream_source).resolve() if args.upstream_source else None,
        scrub_activity=args.scrub_activity,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
