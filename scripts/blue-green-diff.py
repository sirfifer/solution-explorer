#!/usr/bin/env python3
"""Two-slot blue/green projection diff for the demo and dogfood deploys (card G3).

This is the deploy-time half of REGRESSION-STRATEGY.md's blue/green practice.
Every build should be comparable to the one before it: keep the prior projection
(blue) and diff the new one (green) against it with the G1 projection-diff tool,
so a build can always be judged improved versus regressed before it ships.

It is a HEALTH CHECK, not a gate. The demo and dogfood targets change on their
own (the analyzed project moves), so a non-empty diff mixes engine changes with
project changes and must never block the deploy. The rule is: surface the diff
loudly, never fail the deploy because the diff infrastructure failed.

Where blue comes from depends on the target, and this tool is deliberately
agnostic about it:

  - DOGFOOD (this repo). VISION.md keeps the self-repo dogfood site LOCAL (no
    public deploy), so there is no live URL to fetch. Git is the native
    retention slot: the committed ``architecture.json`` is the prior projection.
    The workflow passes it as a local ``--blue`` path.
  - DEMO (downstream consumers of action.yml). Those deploy to Cloudflare Pages,
    whose alias URL is the live green and whose prior deployment URL is a
    fetchable blue. The action passes that URL as ``--blue`` (opt-in).

So ``--blue`` accepts EITHER a local path OR an http/https/file URL, and blue is
fetched or read accordingly. ``--new`` is always a local path (the projection
this build just produced).

Determinism: the JSON diff body is the G1 tool's deterministic delta (never reads
a clock, every list sorted, byte-identical output for byte-identical inputs). The
markdown summary adds a fixed header (label and blue source identity) with no
timestamps, so the report is reproducible.

Usage:
    blue-green-diff.py --blue architecture.json --new viewer/public/architecture.json \
        --label dogfood --summary-out "$GITHUB_STEP_SUMMARY" --json-out projection-diff.json
    blue-green-diff.py --blue https://example.pages.dev/architecture.json \
        --new dist/architecture.json --label demo --summary-out "$GITHUB_STEP_SUMMARY"

The process ALWAYS exits 0: a missing blue (first deploy), an unreachable site, a
network error, or a malformed projection each degrade to a loud honest note in
the summary and a zero exit, so the diff can never break a deploy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# Total wall-clock deadline for fetching a remote blue projection, in seconds.
# This is a TOTAL bound, not merely a per-socket timeout: a slow-drip server that
# trickles a few bytes just inside every socket read would otherwise hold a
# deploy far past any per-recv timeout. The deadline is checked between chunk
# reads, and each individual read is additionally bounded by the socket timeout
# below, so the whole fetch cannot exceed roughly one socket-timeout past this
# deadline. On breach the diff degrades loudly and the deploy continues.
_FETCH_TIMEOUT_S = 30

# Per-socket-operation timeout (seconds). Bounds a single stalled read so the
# between-chunk deadline check is actually reached on a fully-hung connection.
_SOCKET_TIMEOUT_S = 15

# Chunk size for the capped, deadline-bounded read.
_READ_CHUNK = 1 << 16  # 64 KiB

# Hard cap on a fetched blue projection, in bytes. A projection larger than this
# is anomalous (the dogfood monolith is a few MB); reading unbounded into memory
# is a denial-of-service surface for a live-fetched blue. On breach the diff
# degrades loudly rather than reading without limit.
_MAX_BLUE_BYTES = 64 * 1024 * 1024

# The URL schemes a remote blue may use. http/https for a live deploy; file for
# a local file:// URL (used by the hermetic tests and as a local-path escape).
# Anything else (a bare path, a Windows drive) is treated as a local filesystem
# path, so ``--blue architecture.json`` and ``--blue ./x.json`` just work.
_URL_SCHEMES = frozenset({"http", "https", "file"})


def _load_projection_diff() -> Any:
    """Import the G1 projection-diff script as a module (single source of truth).

    ``projection-diff.py`` is a hyphenated script, not an importable package, so
    it is loaded by file path relative to this script's directory (the same
    importlib-by-path pattern the engine uses for the quality scorer). This keeps
    the diff logic in one place; this tool only wraps it with fetch and summary.
    """
    here = Path(__file__).resolve().parent
    path = here / "projection-diff.py"
    spec = importlib.util.spec_from_file_location("_projection_diff", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load projection-diff from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_url(source: str) -> bool:
    """True when ``source`` is an http/https/file URL, else it is a local path."""
    try:
        scheme = urlparse(source).scheme.lower()
    except ValueError:
        return False
    return scheme in _URL_SCHEMES


def _parse_projection(raw: bytes | str, origin: str) -> dict:
    """Parse projection bytes/text to a top-level dict, raising a clear error."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"projection is not valid JSON ({origin}): {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"projection root is not a JSON object ({origin})")
    return data


def _read_capped(resp: Any) -> tuple[bytes, Optional[str]]:
    """Read a response body with a total deadline and a size cap.

    Reads in chunks, checking the total wall-clock deadline BEFORE each read (so a
    slow-drip server cannot hold the fetch past ``_FETCH_TIMEOUT_S`` by more than
    one in-flight socket read) and the cumulative size AFTER each read (so an
    oversized blue cannot be read unbounded into memory). Returns
    ``(body, None)`` on a complete read, or ``(b"", reason)`` when a bound is
    breached. Socket errors propagate to the caller's except handlers.
    """
    start = time.monotonic()
    chunks: list[bytes] = []
    total = 0
    while True:
        if time.monotonic() - start > _FETCH_TIMEOUT_S:
            return b"", f"exceeded {_FETCH_TIMEOUT_S}s total fetch deadline"
        chunk = resp.read(_READ_CHUNK)
        if not chunk:
            return b"".join(chunks), None
        total += len(chunk)
        if total > _MAX_BLUE_BYTES:
            return b"", f"blue projection exceeds the {_MAX_BLUE_BYTES}-byte cap"
        chunks.append(chunk)


def load_blue(source: str) -> tuple[Optional[dict], Optional[str]]:
    """Load the prior/blue projection from a URL or a local path.

    Returns (projection, None) on success, or (None, reason) on any failure. It
    never raises: a missing file, an unreachable host, an HTTP error, a timeout,
    or malformed JSON all become a reason string the caller surfaces loudly. This
    is the "diff infrastructure failed, degrade loudly, never break the deploy"
    contract.
    """
    if _is_url(source):
        try:
            with urllib.request.urlopen(source, timeout=_SOCKET_TIMEOUT_S) as resp:  # noqa: S310 - schemes are allowlisted above
                body, cap_reason = _read_capped(resp)
        except urllib.error.HTTPError as exc:
            return None, f"could not fetch blue from {source}: HTTP {exc.code} {exc.reason}"
        except urllib.error.URLError as exc:
            return None, f"could not fetch blue from {source}: {exc.reason}"
        except (OSError, ValueError) as exc:
            return None, f"could not fetch blue from {source}: {exc}"
        if cap_reason is not None:
            return None, f"could not fetch blue from {source}: {cap_reason}"
        try:
            return _parse_projection(body, source), None
        except ValueError as exc:
            return None, str(exc)
    # Local path.
    p = Path(source)
    if not p.exists():
        return None, f"blue projection not found at {p} (first build, or no retained prior projection)"
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"could not read blue projection at {p}: {exc}"
    try:
        return _parse_projection(raw, str(p)), None
    except ValueError as exc:
        return None, str(exc)


def load_green(path: str) -> tuple[Optional[dict], Optional[str]]:
    """Load the new/green projection from a local path (never raises)."""
    p = Path(path)
    if not p.exists():
        return None, f"new (green) projection not found at {p}"
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"could not read new (green) projection at {p}: {exc}"
    try:
        return _parse_projection(raw, str(p)), None
    except ValueError as exc:
        return None, str(exc)


def _identity_line(proj: dict) -> str:
    name = proj.get("name")
    ver = proj.get("analyzer_version")
    return f"{name} (analyzer {ver})"


def render_summary(
    label: str,
    blue_source: str,
    *,
    blue: Optional[dict],
    green: Optional[dict],
    diff_text: Optional[str],
    degrade_reason: Optional[str],
    blue_context: Optional[str] = None,
) -> str:
    """Build the markdown step-summary block (deterministic, no timestamps).

    On a clean diff it embeds the G1 text report in a fenced block. On any
    degrade it emits a loud, clearly-marked UNAVAILABLE note with the reason and
    an explicit "non-blocking, the deploy continues" line, so a failure of the
    diff infrastructure is visible but never mistaken for a deploy failure.
    """
    lines: list[str] = []
    header = f"## Blue/green projection diff ({label})" if label else "## Blue/green projection diff"
    lines.append(header)
    lines.append("")
    if blue_context:
        lines.append(f"Prior deployment context: {blue_context}")
        lines.append("")

    if degrade_reason is not None:
        lines.append(f"**BLUE/GREEN DIFF UNAVAILABLE:** {degrade_reason}")
        lines.append("")
        lines.append(
            "This is a non-blocking health check; the deploy continues. "
            "The diff will appear once a comparable prior (blue) projection is available."
        )
        lines.append("")
        if green is not None:
            lines.append(f"New (green): {_identity_line(green)}")
            lines.append("")
        return "\n".join(lines) + "\n"

    assert blue is not None and green is not None and diff_text is not None
    lines.append(f"Blue (prior): {_identity_line(blue)}  from `{blue_source}`")
    lines.append(f"Green (new): {_identity_line(green)}")
    lines.append("")
    lines.append("```")
    lines.append(diff_text.rstrip("\n"))
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write(out_path: Optional[str], text: str) -> None:
    """Append to a summary file, or write to stdout when no path is given.

    The GitHub step summary file is append-only across steps, so this appends.
    A write failure (unwritable path, a directory, a full disk) must NOT crash:
    the whole tool is a non-blocking health check that always exits 0, so a
    failed summary write degrades to a last-ditch stderr note and the report is
    also echoed to stdout so it is not lost.
    """
    if not out_path:
        sys.stdout.write(text)
        return
    try:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        print(
            f"blue-green-diff: could not write summary to {out_path}: {exc}; "
            "echoing to stdout instead (non-blocking).",
            file=sys.stderr,
        )
        sys.stdout.write(text)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Two-slot blue/green projection diff for demo and dogfood deploys (G3). "
        "A non-blocking health check that always exits 0.",
    )
    parser.add_argument(
        "--blue",
        required=True,
        help="Prior/blue projection: a local path, or an http/https/file URL to fetch.",
    )
    parser.add_argument(
        "--new",
        required=True,
        help="New/green projection: a local path (the projection this build produced).",
    )
    parser.add_argument(
        "--label",
        default="",
        help="Short context label for the summary header (e.g. dogfood, demo).",
    )
    parser.add_argument(
        "--summary-out",
        default=None,
        help="Append the markdown report here (pass $GITHUB_STEP_SUMMARY in CI). "
        "Default: stdout.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Write the full machine-readable JSON diff here (upload it as a run artifact).",
    )
    parser.add_argument(
        "--blue-context",
        default=None,
        help="Optional prior-deployment context string to record in the summary.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    green, green_err = load_green(args.new)
    if green is None:
        # No green means nothing to diff; degrade loudly, still exit 0.
        summary = render_summary(
            args.label, args.blue, blue=None, green=None, diff_text=None,
            degrade_reason=green_err, blue_context=args.blue_context,
        )
        _write(args.summary_out, summary)
        return 0

    blue, blue_err = load_blue(args.blue)
    if blue is None:
        summary = render_summary(
            args.label, args.blue, blue=None, green=green, diff_text=None,
            degrade_reason=blue_err, blue_context=args.blue_context,
        )
        _write(args.summary_out, summary)
        return 0

    pd = _load_projection_diff()
    diff = pd.diff_projections(blue, green)
    diff_text = pd.render_text(diff)

    summary = render_summary(
        args.label, args.blue, blue=blue, green=green, diff_text=diff_text,
        degrade_reason=None, blue_context=args.blue_context,
    )
    _write(args.summary_out, summary)

    if args.json_out:
        # A failed artifact write must not crash the health check either.
        try:
            Path(args.json_out).write_text(
                json.dumps(diff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            print(
                f"blue-green-diff: could not write JSON diff to {args.json_out}: "
                f"{exc} (non-blocking).",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
