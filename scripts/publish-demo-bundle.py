#!/usr/bin/env python3
"""Turn an assembled serve bundle into a Cloudflare Pages deployable bundle.

`scripts/assemble-serve.py` produces what the crawl needs: the built viewer
plus a projection, symlinked for speed. Cloudflare Pages needs something
else, and every difference below was learned by a refused or an unsafe
deploy:

  - No symlinks. wrangler follows them, but the served bundle must be a plain
    directory so what was tested is byte for byte what was uploaded.
  - No file over 25 MiB. Pages refuses the upload (wrangler client-side, and
    the API with a 500 if the client check is bypassed). A large subject's
    manifest.json and its biggest detail shard exceed it. Each such file is
    stored gzip-compressed under `<name>.gz` and served by `_worker.js` with
    Content-Encoding: gzip, so the browser decodes it and the viewer never
    knows. Compact JSON would not be enough on its own: VS Code's largest
    shard is 41 MiB compact.
  - A gate that actually runs. An advanced-mode `_worker.js` replaces
    `functions/_middleware.js`, so the passcode gate is composed INTO the
    Worker. Cloudflare Access on the custom hostname does not cover the
    `*.pages.dev` hostname of the same deployment; the Worker gate does.
  - No machine path. `manifest.root_path` names the analyzing machine's
    working copy; it is blanked with a note, as demo-site.py does.
  - The upstream license and notices at the bundle root, beside the copies
    the assembly already placed under architecture/.
  - publication.json present and valid (`validate-publication.py --require`).

Usage:

    scripts/publish-demo-bundle.py <slug> [--serve-dir DIR] [--out DIR]
    scripts/publish-demo-bundle.py vscode --check-only

It prints the wrangler command to run next and never runs it: the deploy is
a deliberate, separate step (DISCLOSURE-POLICY.md), and the Pages project
must already carry the PREVIEW_PASSCODE and PREVIEW_SUBJECT secrets or the
gate fails closed and nobody gets in.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_MAX_FILE_BYTES = 25 * 1024 * 1024
GATE_DIR = REPO_ROOT / "infrastructure" / "preview-gate"
WORKER_TEMPLATE = GATE_DIR / "_worker.js"
GATE_MIDDLEWARE = GATE_DIR / "_middleware.js"
VALIDATE_PUBLICATION = REPO_ROOT / "scripts" / "validate-publication.py"
LICENSE_NAMES = ("UPSTREAM-LICENSE.txt",)
NOTICE_NAMES = ("ThirdPartyNotices.txt", "NOTICE", "NOTICE.txt")

ROOT_PATH_NOTE = (
    "Removed when this bundle was assembled for publication. The analyzed "
    "tree's absolute path on the generating machine is not part of the map."
)


def _human(n: int) -> str:
    return f"{n / 1048576:.1f} MiB"


def dereference_copy(serve_dir: Path, out: Path) -> None:
    """Copy the serve bundle, resolving every symlink into a real file."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(serve_dir, out, symlinks=False)


def scrub_root_path(arch: Path) -> str | None:
    manifest = arch / "manifest.json"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    original = doc.get("root_path")
    if not isinstance(original, str) or not original:
        return None
    doc["root_path"] = ""
    doc["root_path_note"] = ROOT_PATH_NOTE
    manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return original


def hoist_notices(out: Path) -> list[str]:
    """Copy the license and notices from architecture/ to the bundle root."""
    arch = out / "architecture"
    hoisted = []
    for name in LICENSE_NAMES + NOTICE_NAMES:
        source = arch / name
        if source.is_file():
            shutil.copy2(source, out / name)
            hoisted.append(name)
    return hoisted


def compress_oversized(out: Path, cap: int = PAGES_MAX_FILE_BYTES) -> list[str]:
    """gzip every regular file over the cap; return their URL paths."""
    paths = []
    for file in sorted(out.rglob("*")):
        if not file.is_file() or file.suffix == ".gz":
            continue
        if file.stat().st_size <= cap:
            continue
        target = file.with_name(file.name + ".gz")
        with open(file, "rb") as src, gzip.open(target, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        file.unlink()
        if target.stat().st_size > cap:
            raise SystemExit(
                f"error: {file.relative_to(out)} is still {_human(target.stat().st_size)} "
                f"after gzip; it needs a smaller projection, not a bigger trick"
            )
        paths.append("/" + file.relative_to(out).as_posix())
    return paths


def write_worker(out: Path, gzipped_paths: list[str]) -> None:
    template = WORKER_TEMPLATE.read_text(encoding="utf-8")
    if "__GZIPPED_JSON__" not in template:
        raise SystemExit(f"error: {WORKER_TEMPLATE} has no __GZIPPED_JSON__ placeholder")
    worker = template.replace("__GZIPPED_JSON__", json.dumps(gzipped_paths))
    (out / "_worker.js").write_text(worker, encoding="utf-8")
    shutil.copy2(GATE_MIDDLEWARE, out / "preview-gate.js")
    # An advanced-mode Worker ignores functions/; a stale copy there would
    # only mislead the next reader into thinking the gate lives in two places.
    functions = out / "functions"
    if functions.exists():
        shutil.rmtree(functions)


def safety_errors(out: Path, cap: int = PAGES_MAX_FILE_BYTES) -> list[str]:
    """Hard refusals, checked against the finished directory."""
    errors = []
    if not (out / "index.html").is_file():
        errors.append("no index.html: this is data, not a viewer")
    worker = out / "_worker.js"
    if not worker.is_file():
        errors.append("no _worker.js: the preview gate would be absent (DISCLOSURE-POLICY.md step 3)")
    elif "preview-gate.js" not in worker.read_text(encoding="utf-8"):
        errors.append("_worker.js does not import the preview gate")
    if not (out / "preview-gate.js").is_file():
        errors.append("no preview-gate.js beside _worker.js")
    if not any((out / n).is_file() for n in LICENSE_NAMES):
        errors.append("no upstream license at the bundle root (LICENSE-REVIEW.md step 3)")
    arch = out / "architecture"
    if not (arch / "publication.json").is_file():
        errors.append("no architecture/publication.json")
    manifest = arch / "manifest.json"
    manifest_gz = arch / "manifest.json.gz"
    if manifest.is_file():
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    elif manifest_gz.is_file():
        with gzip.open(manifest_gz, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
    else:
        errors.append("no architecture/manifest.json (plain or gzip)")
        doc = {}
    if doc.get("root_path"):
        errors.append("manifest.root_path still names the generating machine")
    for file in out.rglob("*"):
        if file.is_symlink():
            errors.append(f"symlink in bundle: {file.relative_to(out)}")
        elif file.is_file() and file.stat().st_size > cap:
            errors.append(f"{file.relative_to(out)} is {_human(file.stat().st_size)}, over the Pages cap")
    return errors


def validate_publication(out: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATE_PUBLICATION), "--require", str(out / "architecture" / "publication.json")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"error: publication.json failed validation:\n{result.stdout}{result.stderr}")
    print(result.stdout.strip())


def build(slug: str, serve_dir: Path, out: Path) -> Path:
    print(f"[publish] {slug}: {serve_dir} -> {out}")
    dereference_copy(serve_dir, out)
    scrubbed = scrub_root_path(out / "architecture")
    print(f"[publish]   root_path: {'removed' if scrubbed else 'absent'}")
    print(f"[publish]   notices at root: {', '.join(hoist_notices(out)) or 'none found'}")
    gzipped = compress_oversized(out)
    for path in gzipped:
        print(f"[publish]   gzip (over {_human(PAGES_MAX_FILE_BYTES)}): {path}")
    write_worker(out, gzipped)
    print("[publish]   _worker.js written with the preview gate composed in")
    validate_publication(out)
    errors = safety_errors(out)
    if errors:
        for err in errors:
            print(f"  UNSAFE: {err}", file=sys.stderr)
        raise SystemExit(2)
    count = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"[publish]   bundle ready: {count} files, no symlinks, nothing over the cap")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug")
    parser.add_argument("--serve-dir", default=None,
                        help="assembled serve bundle (default .testboard/serve/<slug>)")
    parser.add_argument("--out", default=None,
                        help="output directory (default .testboard/publish/<slug>)")
    parser.add_argument("--project", default=None,
                        help="Cloudflare Pages project name for the printed deploy command")
    parser.add_argument("--check-only", action="store_true",
                        help="run the safety checks on an existing --out and exit")
    args = parser.parse_args(argv)
    serve_dir = Path(args.serve_dir or REPO_ROOT / ".testboard" / "serve" / args.slug).resolve()
    out = Path(args.out or REPO_ROOT / ".testboard" / "publish" / args.slug).resolve()
    if args.check_only:
        errors = safety_errors(out)
        for err in errors:
            print(f"  UNSAFE: {err}", file=sys.stderr)
        print("bundle safe" if not errors else "bundle unsafe")
        return 2 if errors else 0
    if not (serve_dir / "index.html").is_file():
        raise SystemExit(f"error: no serve bundle at {serve_dir}; run scripts/assemble-serve.py first")
    build(args.slug, serve_dir, out)
    project = args.project or f"syscorpus-{args.slug}"
    print("\nNext, deliberately (see docs/publication/DEMO-DEPLOY-RUNBOOK.md):")
    print(f"  wrangler pages deploy {out} --project-name {project} --branch main "
          f"--commit-hash <main sha> --commit-dirty=false --commit-message '<what and why>'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
