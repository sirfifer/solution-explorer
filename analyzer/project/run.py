"""Opt-in v2 engine entry point: extract -> derive -> project.

Wired into analyzer/cli.py behind ``--engine v2`` (default stays ``v1``, the old
engine; no default behavior changes). This runs the full Program 2 pipeline:
Tier 1 extraction into a persistent fact store, Tier 3 derivation, then Tier 4
projection to the same delivery artifacts the viewer already loads.

Incremental by construction (P4-6, invariant I6). The fact store is a durable
file (default ``<root>/.solution-explorer/index.db``). On a warm store the
content-hash extraction cache means unchanged files are never re-parsed: cost
tracks the size of the change, not the size of the repo. The store itself is the
incremental baseline, so the v2 path never reads or writes the old engine's
``.arch-baseline/file-index.json`` or ``import-graph.json`` caches. The
``--incremental`` / ``--base-sha`` / ``--head-sha`` / ``--baseline`` flags are
accepted as compatibility no-ops (existing CI invocations keep working); v2 is
always incremental, so they change nothing. Derivation re-runs in full each pass
because it is cheap store queries whose correctness is global (component
membership and relationship joins can change anywhere when any file changes); it
never re-reads source (P4-3), so full re-derivation over a warm store stays fast.

EXPERIMENTAL. The v2 engine is not the default and is not yet the cutover path
(that is P4-7). It exists so the projection tier can be driven end to end and
integration-tested against the real viewer build.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ..derive import derive_all, derive_multi_from_config
from ..extract import extract_activity, extract_repo
from ..store import FactStore
from .coverage import coverage_families, format_source_percent
from .pipeline import project_monolith, project_split

DEFAULT_STORE_RELPATH = Path(".solution-explorer") / "index.db"


def default_store_path(root: Path) -> Path:
    """The default persistent-store location for a single-repo v2 scan.

    Under ``<root>/.solution-explorer/`` so the store is discoverable next to
    the code it indexes. The directory is a dot-directory, so extraction prunes
    it (one ``excluded:skipped_directory`` ledger row) and never scans the
    database file. Creating it before enumeration keeps that ledger row present
    on both cold and warm runs, so a fresh-store rescan and a warm-store
    incremental run over the same tree project byte-identically (P4-6 parity).
    """
    return Path(root) / DEFAULT_STORE_RELPATH


def _reject_remote_multi_repo(config_path: Path) -> None:
    """Exit with a clear message if a multi-repo config needs a remote clone.

    v2's ``derive_multi_from_config`` resolves each repo from a local ``path``.
    A repo defined only by ``url`` requires a git clone, which the v1
    orchestrator does but v2 does not yet. Detect it here and direct the user to
    ``--engine v1`` instead of letting ``derive_multi_from_config`` raise a bare
    KeyError on the missing ``path``.
    """
    import json

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return  # derive_multi_from_config will surface the real load error
    remote = [
        r.get("name", "?")
        for r in config.get("repositories", [])
        if "path" not in r and r.get("url")
    ]
    if remote:
        print(
            "Error: engine=v2 multi-repo supports local `path` repositories only; "
            f"these are defined by `url` and need a remote clone: {', '.join(remote)}.\n"
            "Run with --engine v1 for remote multi-repo clones until v2 remote "
            "clone lands (deferred, TASKS.md P4-7).",
            file=sys.stderr,
        )
        sys.exit(1)


def run_v2(args) -> None:
    """Run the v2 pipeline from parsed CLI args (analyzer/cli.py ``main``)."""
    generated_at = datetime.now(timezone.utc).isoformat()
    indent = None if args.compact else 2

    # v2 is incremental by construction; the legacy incremental flags are
    # accepted so existing workflow invocations keep running unmodified, but
    # they select nothing (there is no separate full/incremental mode here).
    if getattr(args, "incremental", False) or getattr(args, "base_sha", ""):
        print(
            "Note: engine=v2 is incremental by construction "
            "(the fact store is the baseline); --incremental/--base-sha are "
            "accepted as no-ops."
        )

    store = None
    store_owned = False
    root = None
    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Multi-repo mode (engine=v2): {config_path}")
        # v2 multi-repo assembles per-repo stores from LOCAL paths. Remote-clone
        # (a repo defined by `url` rather than `path`) is not yet wired into v2
        # (deferred, see TASKS.md P4-7 Discovered). Fail loudly rather than crash
        # with a KeyError, and name the one-flag rollback (no silent breakage,
        # WORK-PLAN principle 4).
        _reject_remote_multi_repo(config_path)
        # A unified persistent incremental store and a merged coverage ledger
        # across per-repo stores are deferred (TASKS.md P4-7 Discovered).
        arch = derive_multi_from_config(config_path)
    else:
        root = Path(args.path).resolve()
        if not root.is_dir():
            print(f"Error: {root} is not a directory", file=sys.stderr)
            sys.exit(1)

        store_path = Path(args.store).resolve() if args.store else default_store_path(root)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        warm = store_path.exists() and store_path.stat().st_size > 0
        print(
            f"Scanning {root} (engine=v2, {'warm' if warm else 'cold'} store: "
            f"{store_path})..."
        )
        store = FactStore(str(store_path))
        store_owned = True
        # v2 analyzes 100 percent of source by default (invariant I2). The CLI
        # default for --max-file-size is None, so an unspecified value forwards
        # None (unbounded) and every file is parsed. A user-supplied bound is
        # forwarded verbatim, honored, and lands as an excluded:max_file_size
        # ledger row (never a silent default). An explicit 0 is a real bound
        # (it excludes every non-empty file), matching the v1 engine, so an
        # explicit value never silently means "not provided".
        extraction = extract_repo(root, store, max_file_size=args.max_file_size)
        print(
            f"  Extraction: {extraction.files_parsed} parsed, "
            f"{extraction.files_cached} cached (unchanged)"
        )
        # Git-activity extraction (P5-4): extraction-adjacent, reads git not
        # source, cached by commit range. Graceful no-op on a non-git root.
        activity = extract_activity(root, store)
        if activity.git:
            print(
                f"  Activity: {activity.commits_processed} commits processed "
                f"({activity.mode}"
                f"{', shallow' if activity.shallow else ''})"
            )
        _, arch = derive_all(store, root.name, root_path=str(root))

    try:
        if args.split:
            output_dir = (
                Path(args.output) if args.output != "architecture.json" else Path("architecture")
            )
            result = project_split(
                arch, output_dir, store=store, root=root,
                generated_at=generated_at, analyzer_version=__version__, indent=indent,
            )
            output_label = f"{output_dir}/"
        else:
            output_path = Path(args.output)
            result = project_monolith(
                arch, output_path, store=store, root=root,
                generated_at=generated_at, analyzer_version=__version__, indent=indent,
            )
            output_label = str(output_path)
    finally:
        if store_owned and store is not None:
            store.close()

    stats = arch.get("stats", {})
    print("\nAnalysis complete (engine=v2):")
    print(f"  Components: {stats.get('total_components', 0)}")
    print(f"  Files: {stats.get('total_files', 0)}")
    print(f"  Lines: {stats.get('total_lines', 0):,}")
    print(f"  Symbols: {stats.get('total_symbols', 0)}")
    print(f"  Relationships: {stats.get('total_relationships', 0)}")
    if result.coverage is not None:
        cov = result.coverage
        # Speak the three-family coverage semantics that the viewer badge shows,
        # not a raw parsed/total ratio. "Percent of SOURCE analyzed" excludes the
        # non-source files (assets, vendored, docs) from the denominator, and the
        # non-source total is reported separately as accounted for, so a repo full
        # of images never reads as low coverage. A real gap is never rounded up to
        # a bare 100 (format_source_percent mirrors the viewer's formatSourcePercent).
        fam = coverage_families(cov["summary"])
        pct = format_source_percent(fam)
        gap_word = "gap" if fam["gap"] == 1 else "gaps"
        ns_word = "file" if fam["nonsource"] == 1 else "files"
        print(
            f"  Coverage: {pct}% of source analyzed "
            f"({fam['analyzed']} parsed, {fam['gap']} {gap_word}); "
            f"{fam['nonsource']} non-source {ns_word} accounted for"
        )
    print(f"\nOutput: {output_label}")
