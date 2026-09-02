"""Tier 1 runner: parallel, content-hash-cached extraction into the fact store.

Enumerate files under the root, hash each once, reuse cached facts for files
whose (content_hash, parser_version) is already extracted, parse the rest in a
worker pool, and write symbols, signals, and a coverage-ledger row for every
file (TARGET-ARCHITECTURE.md 4.1; invariants I2 no silent skips, I6 incremental
by construction).

Worker-pool decision (TARGET-ARCHITECTURE 12 defers this here): tree-sitter
parsing is CPU-bound and releases nothing to threads, so a process pool is the
right tool. We use ``concurrent.futures.ProcessPoolExecutor``: it is stdlib,
its ``spawn``/``fork`` workers each re-import analyzer.parsers and build their
own PARSERS registry (no un-picklable parser objects cross the boundary), and
file content is shipped in while a plain FileFacts dict is shipped out. Files
are read and hashed once in the parent (so the coverage ledger and the cache
key are computed before any parse), and only cache misses are dispatched. The
parent read is the single read the invariant requires; workers never touch the
disk. Worker count heuristic: ``min(cpu_count, len(parse_queue))``, capped by
an explicit ``max_workers``; below INLINE_THRESHOLD misses (or with one worker)
we parse inline to avoid pool spawn overhead.

Determinism: files are enumerated with ``sorted(filenames)`` and written in
sorted path order; symbol IDs come from analyzer/store/ids.assign_symbol_ids
(source order in, order out); every emitted list is position- or key-ordered,
never set iteration (invariant I4; TASKS.md Discovered 2026-07-13). The parser
tier is encoded in parser_version so cache entries from the tree-sitter and
regex tiers never mix.

Incremental (P4-6, invariant I6). This runner is incremental by construction:
``clear_extraction_facts`` rebuilds the per-file rows this tier owns (files,
symbols, signals, coverage) while KEEPING the content-hash extraction cache, so
a warm store re-parses only files whose content (or parser tier) changed and
reuses cached facts for the rest. The fact rows are fully rebuilt every run, so
deleted, renamed, and modified files leave no stale rows and a warm-store run
over a given tree state produces the same store contents (modulo the cache's
retained historical entries, which are content-addressed and never re-served for
different content) as a fresh-store cold run. That is what makes a full rescan
and an incremental run project byte-identically. Reading and hashing each file
once per run is the single read invariant 4.1 allows and the only way to know a
file changed; parsing, the dominant cost, is what the cache elides.
"""

from __future__ import annotations

import hashlib
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..constants import LANGUAGE_MAP, SKIP_EXTENSIONS
from ..parsers import PARSERS
from ..parsers.markdown import extract_markdown_text
from ..store import LOCAL_REPO, ROOT_COMPONENT, FactStore, assign_symbol_ids
from ..utils import (
    GitignoreMatcher,
    _is_generated_dataset_dir,
    _is_generated_projection,
    _is_vendored_repo,
    _should_skip_dir,
)
from .clones import extract_clone_signals
from .facts import FileFacts
from .signals import extract_entity_signals, extract_rule_signals, extract_signals

# p4-extract/1 -> p5-extract/1: extraction now also emits `data_entity` signals
# (P5-2). p5-extract/1 -> p5-extract/2: extraction now also emits `rule` signals
# (P5-5). p5-extract/2 -> p5-extract/3: extraction now also emits `clone_fragment`
# signals (token fingerprints, P5-6). p5-extract/5 -> p5-extract/6: Swift
# static-member-access references (Name.member) join the symbol_reference
# signal, so warm caches re-extract once and never serve reference sets that
# predate the pattern. Bumping the tier invalidates the
# content-hash cache so a warm store is re-extracted once and never silently
# serves cached facts that predate the new signal kind (invariant I2 / "no
# silent anything").
# p5-extract/3 -> p5-extract/4: framework/driver/job/cli signal detectors now
# ignore matches that fall inside a string literal (D3 string-literal awareness),
# so a pattern/detector tool no longer detects its own pattern definitions.
# Bumping the tier invalidates the content-hash cache so a warm store re-extracts
# once and never serves cached facts that predate the guard.
# p5-extract/4 -> p5-extract/5: extraction now also emits `symbol_reference`
# signals (type-like names a file references, references.py) so Tier 3 can draw
# component-to-component `uses` edges (D5). The string-literal guard also gained
# language-gated `#`-comment awareness (PR #53 comment-phantom nit; PR #55
# review findings 2/3: whole comments are masked, and only in languages where
# `#` opens a comment), which can change which driver/job matches are
# suppressed. Bumping the tier invalidates the content-hash cache so a warm
# store re-extracts once and never serves cached facts that predate the new
# signal kind (one-time re-extract disclosure).
# /7 (comprehension-study S2): env-var extraction became reads-only (writes
# like env["CFG_SCALE"] = ... are no longer inputs) and SQL entity parsing
# blanks comments before splitting columns, so cached env_var and entity
# signals from /6 are wrong under the new rules and must re-extract.
# /8 (doc-search fix): markdown files now get a module_doc via
# analyzer/parsers/markdown.extract_markdown_text (previously always None, so
# every markdown search-index entry carried empty text). Markdown has no
# parser, so parser_version() never tier-tags it; bumping EXTRACT_TIER is the
# only way to invalidate cached FileFacts rows that predate this fix.
# /10 (comprehension review): queue names no longer accept Swift-style
# ``topic:`` argument labels, websocket URLs join the transport evidence, and
# assignment-shaped queue names require an observed queue driver. JSON/Markdown
# are routed away from the executable-code rule extractor. Warm stores must
# refresh these signals once or they preserve the exact false capabilities and
# rules this tier corrected.
EXTRACT_TIER = "p5-extract/10"
INLINE_THRESHOLD = 8  # below this many cache misses, parse inline (no pool)

# In-run retry for transient extraction failures (P4-8). A worker crash, an
# OS-layer error, or a dead process pool must not cost a file for the whole run:
# failed items are re-submitted through the same worker path up to _MAX_ATTEMPTS
# times total. Failures were already never cached (cross-run retry by
# construction); this bounds the retry to the current run so 100 percent is
# reachable without a rescan. The budget is failure-kind aware: infrastructure
# and OS-layer failures are transient candidates and get the full budget, while
# a parser exception on stable input is deterministic and is retried only once
# (cheap, and expected to reproduce). Either way the final ledger disposition is
# a pure function of the input, so full-vs-incremental parity and PYTHONHASHSEED
# determinism are preserved.
_MAX_ATTEMPTS = 3  # total attempts for a transient candidate (1 initial + 2 retries)
_DETERMINISTIC_ATTEMPTS = 2  # a parser error is retried once, then stands

# Error payloads whose type-name prefix marks them transient. The worker reports
# failures as "<ExceptionType>: <message>" strings (it catches everything so a
# bad file never crashes the pool), and pool death is synthesized as a
# BrokenProcessPool payload by _run_parse_batch, so classification is a prefix
# match on that leading type name. MemoryError and the OS/connection errors are
# environmental; a BrokenProcessPool means the pool itself died and the batch is
# retried against a freshly built pool.
_TRANSIENT_ERROR_PREFIXES = (
    "BrokenProcessPool",
    "OSError",
    "MemoryError",
    "TimeoutError",
    "BrokenPipeError",
    "ConnectionError",
    "ConnectionResetError",
)

# v2-only schema/UI formats that are not in the shared LANGUAGE_MAP (which v1
# scanner.py reads). `.sql` and `.json` are already enumerated; these are not,
# so they are recognized here on the v2 path only, leaving v1 output byte-stable.
# `.storyboard`/`.xib` parse to view-controller symbols and segue flow edges;
# Core Data models parse to data entities (both P4-9).
_SCHEMA_ONLY_EXTENSIONS = {
    ".prisma": "prisma",
    ".storyboard": "storyboard",
    ".xib": "storyboard",
}


def _schema_only_language(rel: str, fname: str, ext: str) -> Optional[str]:
    """v2-only language for a schema/UI file, or None.

    Extension-keyed formats come from ``_SCHEMA_ONLY_EXTENSIONS``. Core Data
    models are the extension-less ``contents`` XML inside a ``*.xcdatamodel``
    version directory, so they are matched by path component instead. Recognized
    on the v2 path only (v1 scanner.py never sees them), keeping parity snapshots
    byte-identical.
    """
    lang = _SCHEMA_ONLY_EXTENSIONS.get(ext)
    if lang:
        return lang
    if fname == "contents":
        parts = rel.replace("\\", "/").split("/")
        if any(p.endswith(".xcdatamodel") for p in parts):
            return "coredata"
    return None


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parser_version(language: str, parser) -> str:
    """Tier-tagged parser version. The tier is probed via ``_ts_available``.

    Encoding the tier means a file parsed under tree-sitter and the same file
    parsed under the regex fallback occupy distinct cache keys and never mix
    (TASKS.md Discovered 2026-07-13, CI parser-tier split).
    """
    tier = "ts" if getattr(parser, "_ts_available", False) else "regex"
    return f"{EXTRACT_TIER}:{language}:{tier}"


@dataclass
class ExtractionResult:
    """Summary of one extraction pass, for tests and speedup measurement."""

    files_parsed: int = 0
    files_cached: int = 0
    files_failed: int = 0
    symbols: int = 0
    signals: int = 0
    ledger: dict[str, int] = field(default_factory=dict)
    worker_count: int = 1
    parse_queue_size: int = 0
    parser_tiers: dict[str, str] = field(default_factory=dict)


def _parse_worker(task: tuple[str, str, str, str]) -> tuple[str, str, object]:
    """Parse one file's content in a worker process. Returns (rel, status, payload).

    status is 'ok' with a FileFacts dict payload, or 'failed' with an error
    string. The parent already read and hashed the content, so the worker only
    parses; it re-imports PARSERS in its own process.
    """
    rel, language, content, pversion = task
    try:
        parser = PARSERS.get(language)
        symbols = parser.extract_nested_symbols(content, rel) if parser else []
        imports = sorted(set(parser.extract_imports(content))) if parser else []
        if parser:
            module_doc = parser.extract_file_doc(content)
        elif language == "markdown":
            # Markdown has no code-language parser (PARSERS registers none for
            # "markdown" by design; see analyzer/parsers/markdown.py) so it is
            # not routed through extract_signals below, which stays gated on
            # `parser` to keep the regex signal pipeline (URLs, HTTP/DB/queue
            # drivers, endpoints, CLI commands, ...) off documentation prose.
            module_doc = extract_markdown_text(content)
        else:
            module_doc = None
        signals = extract_signals(content, language, parser) if parser else []
        # Entity signals are parser-independent (pure regex), so they run for
        # both code files and parser-less schema files (P5-2, Data lens L3).
        signals = signals + extract_entity_signals(content, language, rel)
        # Rule signals are likewise parser-independent (P5-5, Rules lens L6).
        signals = signals + extract_rule_signals(content, language, rel)
        # Clone-fragment fingerprints (P5-6, correlation extraction). Needs the
        # parser's token stream and the already-extracted symbols; empty for
        # regex-only parsers and parser-less files.
        signals = signals + extract_clone_signals(content, language, parser, symbols)
        facts = FileFacts(
            path=rel,
            language=language,
            content_hash="",  # filled by the parent (it owns the hash)
            parser_version=pversion,
            lines=content.count("\n") + 1,
            size_bytes=len(content.encode("utf-8")),
            parse_status="parsed",
            symbols=symbols,
            imports=imports,
            module_doc=module_doc,
            signals=signals,
            content=content,
        )
        return (rel, "ok", facts.to_dict())
    except Exception as exc:  # noqa: BLE001 - report, never crash the pool
        return (rel, "failed", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------

@dataclass
class _Candidate:
    rel: str
    language: str
    content: str
    content_hash: str
    size_bytes: int
    pversion: str


CI_TIER = f"{EXTRACT_TIER}:ci:raw"

# The tool's own state directory inside an analyzed repo (the default fact-store
# path is ``<root>/.solution-explorer/index.db``). It is accounted as ONE pruned
# ledger row with the ``excluded:tool_state`` disposition and never walked, so
# the tool never scans its own store and rules as if they were repo source. The
# committed ``rules/inventory.yml`` under it is still read by the rules loader,
# which opens it directly by path and does not go through enumeration.
TOOL_STATE_DIRNAME = ".solution-explorer"

# Extension-less filenames cached as ci_config rows; the extension rule would
# otherwise drop their content, which Tier 3's CI check needs (P4-3).
_CI_BARE_FILENAMES = {"Jenkinsfile"}


def _ci_files_in_pruned_dir(dirpath: str, name: str) -> list[str]:
    """CI config files rescued from a pruned dot-directory.

    Tier 3's root-bounded CI-test detection (P4-3, porting the P2-2 item-3
    fix) reads only the store, so `.github/workflows/*.yml` and
    `.circleci/config.yml` content must be cached at extraction time even
    though their parent directories are pruned. Returns absolute paths.
    """
    out: list[str] = []
    base = os.path.join(dirpath, name)
    if name == ".github":
        wf = os.path.join(base, "workflows")
        if os.path.isdir(wf):
            for f in sorted(os.listdir(wf)):
                if f.endswith((".yml", ".yaml")):
                    out.append(os.path.join(wf, f))
    elif name == ".circleci":
        cfg = os.path.join(base, "config.yml")
        if os.path.isfile(cfg):
            out.append(cfg)
    return out


def _enumerate(
    root: Path, max_file_size: Optional[int]
) -> tuple[list[_Candidate], list[tuple[str, str, str]], set[str]]:
    """Walk the root once, reading and hashing each file.

    Returns (candidates, ledger_rows, marker_dirs) where candidates are files
    to parse-or-load, ledger_rows are (path, disposition, reason) for every
    file and every pruned directory, and marker_dirs holds directories that
    carry a component-marker file (for lightweight component resolution).
    Candidates whose ``pversion`` is ``CI_TIER`` are CI configs: cached and
    written as ``ci_config`` file rows for Tier 3's root-bounded CI check,
    but excluded from the architecture's file output (old-engine parity).
    """
    from ..constants import COMPONENT_MARKERS

    candidates: list[_Candidate] = []
    ledger: list[tuple[str, str, str]] = []
    marker_dirs: set[str] = set()
    gitignore = GitignoreMatcher(root)

    def add_ci_candidate(abs_path: str) -> None:
        rel = os.path.relpath(abs_path, root)
        try:
            raw = Path(abs_path).read_bytes()
        except OSError as exc:
            ledger.append((rel, "failed", f"read_error: {exc}"))
            return
        candidates.append(_Candidate(
            rel=rel, language=LANGUAGE_MAP.get(Path(abs_path).suffix.lower(), ""),
            content=raw.decode("utf-8", errors="replace"),
            content_hash=_hash_bytes(raw), size_bytes=len(raw),
            pversion=CI_TIER,
        ))

    for dirpath, dirnames, filenames in os.walk(root):
        # Record and prune skipped directories so the ledger is honest without
        # exploding their (potentially millions of) files (invariant O5 scale).
        kept = []
        for d in sorted(dirnames):
            child = os.path.relpath(os.path.join(dirpath, d), root)
            if d == TOOL_STATE_DIRNAME:
                # The tool's own state directory (store + learned rules). Pruned
                # to one row and never walked; the checked-in rules file is read
                # by the loader directly, not through enumeration. Checked before
                # _should_skip_dir (which would otherwise prune it as a generic
                # dot-directory) so it carries the honest tool_state disposition.
                ledger.append((child, "excluded:tool_state",
                               "solution-explorer tool state"))
            elif _should_skip_dir(d):
                ledger.append((child, "excluded:skipped_directory", d))
                for ci_path in _ci_files_in_pruned_dir(dirpath, d):
                    add_ci_candidate(ci_path)
            elif _is_generated_dataset_dir(os.path.join(dirpath, d)):
                # The tool's own emitted projection dataset (D1). Do not parse
                # its serialized code previews as product source, but keep the
                # repository accounting file-complete. Every file receives its
                # own generated disposition and remains available to the
                # inventory/human-classification path.
                generated_root = os.path.join(dirpath, d)
                generated_files: list[str] = []
                for generated_dir, generated_dirs, generated_names in os.walk(generated_root):
                    generated_dirs.sort()
                    for generated_name in sorted(generated_names):
                        generated_files.append(os.path.relpath(
                            os.path.join(generated_dir, generated_name), root
                        ))
                for generated_rel in generated_files:
                    ledger.append((
                        generated_rel,
                        "excluded:generated",
                        "generated: solution-explorer projection dataset",
                    ))
                print(
                    f"NOTE: {child}/ accounted as a generated solution-explorer "
                    f"projection dataset ({len(generated_files)} files classified individually); "
                    "if this directory is real source, rename its manifest.json "
                    "or report this as a misdetection.",
                    file=sys.stderr,
                )
            elif _is_vendored_repo(os.path.join(dirpath, d)):
                ledger.append((child, "excluded:vendored_repo", d))
            else:
                # A gitignored directory is workstation-local, not repo content.
                # Prune it to ONE row (like .git) instead of walking a possibly
                # huge ignored subtree (the TestResults.xcresult case). Checked
                # AFTER the existing skip rules so already-handled dirs keep their
                # disposition and fresh-clone output stays byte-identical.
                gi = gitignore.match(child, is_dir=True)
                if gi is not None:
                    ledger.append((child, "excluded:gitignored", gi))
                else:
                    kept.append(d)
        dirnames[:] = kept

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel = os.path.relpath(fpath, root)
            # A gitignored file is workstation-local and never reaches the
            # central repo, so it is accounted (excluded:gitignored, non-source)
            # rather than parsed. Checked first and cheaply (no read), and it
            # keeps a gitignored marker file from anchoring a phantom component.
            gi = gitignore.match(rel, is_dir=False)
            if gi is not None:
                ledger.append((rel, "excluded:gitignored", gi))
                continue
            if fname in COMPONENT_MARKERS:
                marker_dirs.add(os.path.relpath(dirpath, root))

            ext = fpath.suffix.lower()
            if not ext and fname in _CI_BARE_FILENAMES:
                add_ci_candidate(str(fpath))
                continue
            if ext in SKIP_EXTENSIONS:
                ledger.append((rel, "binary", f"skip_extension:{ext}"))
                continue
            try:
                raw = fpath.read_bytes()
            except OSError as exc:
                ledger.append((rel, "failed", f"read_error: {exc}"))
                continue

            size = len(raw)
            if size == 0:
                ledger.append((rel, "excluded:empty_file", None))
                continue
            if b"\x00" in raw[:8192]:
                ledger.append((rel, "binary", "null_byte"))
                continue
            # A standalone emitted projection file is the tool's own output,
            # not source (D1). Restricted to the two basenames the tool emits
            # (adversarial-review fix: an arbitrary user .json must never be
            # swallowed by the projection signature).
            if fname in ("architecture.json", "manifest.json") and _is_generated_projection(raw):
                ledger.append((rel, "excluded:generated",
                               "generated: solution-explorer projection"))
                continue

            language = LANGUAGE_MAP.get(ext) or _schema_only_language(rel, fname, ext)
            if not language:
                ledger.append((rel, "excluded:unsupported_extension", ext or fname))
                continue
            if max_file_size is not None and size > max_file_size:
                # Explicit opt-in bound only; its effect lands in the ledger,
                # never a silent default (invariant I2).
                ledger.append((rel, "excluded:max_file_size", str(max_file_size)))
                continue

            content = raw.decode("utf-8", errors="replace")
            parser = PARSERS.get(language)
            pversion = parser_version(language, parser) if parser else EXTRACT_TIER
            candidates.append(_Candidate(
                rel=rel, language=language, content=content,
                content_hash=_hash_bytes(raw), size_bytes=size, pversion=pversion,
            ))

    candidates.sort(key=lambda c: c.rel)
    return candidates, ledger, marker_dirs


def _resolve_component(rel: str, marker_dirs: set[str]) -> str:
    """Nearest ancestor directory carrying a component marker, else root.

    This is the lightweight component segment for the frozen symbol-ID grammar
    at extraction time. Full component discovery is Tier 3 (P4-3); the grammar
    (format) is frozen, the specific component value is not.
    """
    d = os.path.dirname(rel)
    while True:
        norm = d if d else "."
        if norm in marker_dirs:
            return norm
        if not d:
            return ROOT_COMPONENT
        parent = os.path.dirname(d)
        if parent == d:
            return ROOT_COMPONENT
        d = parent


def _worker_count(queue_size: int, max_workers: Optional[int]) -> int:
    """Heuristic: one worker per queued file, capped by CPUs and max_workers."""
    if queue_size <= 0:
        return 1
    n = min(os.cpu_count() or 1, queue_size)
    if max_workers is not None:
        n = min(n, max_workers)
    return max(1, n)


# ---------------------------------------------------------------------------
# Retry (P4-8)
# ---------------------------------------------------------------------------

def _is_transient(payload: str) -> bool:
    """True if a failure payload names a transient (retryable) error kind.

    The payload is the "<ExceptionType>: <message>" string the worker returns
    (or the synthesized BrokenProcessPool string from a dead pool). Anything
    outside _TRANSIENT_ERROR_PREFIXES is treated as a deterministic parser
    failure: retried once, then it stands.
    """
    return payload.startswith(_TRANSIENT_ERROR_PREFIXES)


def _should_retry(payload: str, attempt: int) -> bool:
    """Whether a file that failed on ``attempt`` should be re-submitted.

    Transient candidates get the full _MAX_ATTEMPTS budget; deterministic parser
    failures get one retry only. ``attempt`` is the 1-based number of the pass
    just completed.
    """
    budget = _MAX_ATTEMPTS if _is_transient(payload) else _DETERMINISTIC_ATTEMPTS
    return attempt < budget


def _run_parse_batch(tasks, n_workers: int, use_pool: bool):
    """Run one parse pass over ``tasks``; return a list of (rel, status, payload).

    A live pool is built fresh for every pass, so a retry that follows a pool
    death runs against a new pool (rebuild, do not abort). If the pool dies
    mid-pass (BrokenProcessPool while draining the map), every task in the batch
    is reported failed with a transient BrokenProcessPool payload; the caller's
    retry loop then re-submits them against the rebuilt pool.
    """
    if not tasks:
        return []
    if use_pool:
        try:
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                return list(pool.map(_parse_worker, tasks))
        except BrokenProcessPool as exc:
            return [(t[0], "failed", f"BrokenProcessPool: {exc}") for t in tasks]
    return [_parse_worker(t) for t in tasks]


# ---------------------------------------------------------------------------
# Store writing
# ---------------------------------------------------------------------------

def _write_facts(
    store: FactStore, facts: FileFacts, repo: str, marker_dirs: set[str]
) -> tuple[int, int]:
    """Write one file's facts to the store. Returns (n_symbols, n_signals)."""
    file_id = store.add_file(
        path=facts.path,
        language=facts.language,
        lines=facts.lines,
        size_bytes=facts.size_bytes,
        content_hash=facts.content_hash,
        parse_status=facts.parse_status,
    )

    component = _resolve_component(facts.path, marker_dirs)
    records = [(repo, component, facts.path, tuple(s.path)) for s in facts.symbols]
    ids = assign_symbol_ids(records)
    for sym, sym_id in zip(facts.symbols, ids, strict=True):
        parent_id = ids[sym.parent_index] if sym.parent_index is not None else None
        store.add_symbol(
            symbol_id=sym_id,
            file_id=file_id,
            name=sym.name,
            kind=sym.kind,
            parent_id=parent_id,
            line=sym.line,
            end_line=sym.end_line,
            visibility=sym.visibility,
            docstring=sym.docstring,
            code_preview=sym.code_preview,
        )

    for sig in facts.signals:
        store.add_signal(file_id=file_id, kind=sig.kind, value=sig.value, line=sig.line)

    return len(facts.symbols), len(facts.signals)


def extract_repo(
    root,
    store: FactStore,
    *,
    repo: str = LOCAL_REPO,
    max_file_size: Optional[int] = None,
    max_workers: Optional[int] = None,
) -> ExtractionResult:
    """Extract all files under ``root`` into ``store`` (Tier 1).

    ``max_file_size`` is an explicit opt-in bound (default: no bound; large
    files are parsed). ``max_workers`` caps the process pool; None uses the
    heuristic. Returns an :class:`ExtractionResult` with ledger and timing
    inputs.
    """
    root = Path(root)
    result = ExtractionResult()

    # Extraction is idempotent: rebuild the fact rows this tier owns while
    # keeping the content-hash cache, so a warm re-run reuses cached facts
    # without duplicating store rows (invariant I6).
    store.clear_extraction_facts()

    candidates, ledger_rows, marker_dirs = _enumerate(root, max_file_size)

    # Split candidates into cache hits and a parse queue. CI configs never
    # enter the pool: they are stored verbatim (no parser) as ci_config rows.
    cached: dict[str, FileFacts] = {}
    queue: list[_Candidate] = []
    for c in candidates:
        hit = store.get_cached_facts(c.content_hash, c.pversion)
        if hit is not None:
            facts = FileFacts.from_dict(hit)
            # The cache is keyed by content hash, so two files with identical
            # content share one entry. Path is per-file metadata (and the file
            # segment of every symbol's grammar ID), so it must come from the
            # current candidate, not from whichever file was cached first.
            facts.path = c.rel
            facts.content_hash = c.content_hash
            cached[c.rel] = facts
        elif c.pversion == CI_TIER:
            facts = FileFacts(
                path=c.rel, language=c.language, content_hash=c.content_hash,
                parser_version=CI_TIER, lines=c.content.count("\n") + 1,
                size_bytes=c.size_bytes, parse_status="ci_config",
                content=c.content,
            )
            store.cache_facts(c.content_hash, CI_TIER, facts.to_dict())
            cached[c.rel] = facts
        else:
            queue.append(c)

    result.parse_queue_size = len(queue)

    # Parse the queue (pool or inline) and collect FileFacts by rel.
    parsed: dict[str, FileFacts] = {}
    failed: dict[str, str] = {}
    attempts: dict[str, int] = {}
    tasks = [(c.rel, c.language, c.content, c.pversion) for c in queue]
    hash_by_rel = {c.rel: c.content_hash for c in queue}
    task_by_rel = {t[0]: t for t in tasks}

    n_workers = _worker_count(len(queue), max_workers)
    result.worker_count = n_workers
    use_pool = bool(queue) and n_workers > 1 and len(queue) >= INLINE_THRESHOLD
    if not use_pool:
        result.worker_count = 1

    # In-run retry loop (P4-8). Each pass re-parses only the items still failing
    # and still within their kind's budget. A file that succeeds on a retry is
    # recorded exactly like a first-try success (it goes into ``parsed`` and its
    # facts are cached), so retried and first-try successes are indistinguishable
    # in the output. Only successes are cached, so failures still retry across
    # runs by construction; this loop just bounds the retry to the current run.
    pending = tasks
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        outcomes = _run_parse_batch(pending, n_workers, use_pool)
        retry_next: list = []
        for rel, status, payload in outcomes:
            attempts[rel] = attempt
            if status == "ok":
                facts = FileFacts.from_dict(payload)
                facts.content_hash = hash_by_rel[rel]
                parsed[rel] = facts
                store.cache_facts(
                    facts.content_hash, facts.parser_version, facts.to_dict()
                )
                failed.pop(rel, None)  # a later pass may clear an earlier failure
            else:
                failed[rel] = str(payload)
                if _should_retry(str(payload), attempt):
                    retry_next.append(task_by_rel[rel])
        pending = retry_next
        if not pending:
            break

    # Write everything in deterministic path order.
    for c in candidates:
        rel = c.rel
        if rel in cached:
            n_sym, n_sig = _write_facts(store, cached[rel], repo, marker_dirs)
            result.files_cached += 1
            result.symbols += n_sym
            result.signals += n_sig
            ledger_rows.append(
                (rel, "parsed", "ci_config" if c.pversion == CI_TIER else "")
            )
            result.parser_tiers.setdefault(c.language, c.pversion.rsplit(":", 1)[-1])
        elif rel in parsed:
            n_sym, n_sig = _write_facts(store, parsed[rel], repo, marker_dirs)
            result.files_parsed += 1
            result.symbols += n_sym
            result.signals += n_sig
            ledger_rows.append((rel, "parsed", ""))
            result.parser_tiers.setdefault(c.language, c.pversion.rsplit(":", 1)[-1])
        elif rel in failed:
            store.add_file(
                path=rel, language=c.language, lines=None, size_bytes=c.size_bytes,
                content_hash=c.content_hash, parse_status="failed",
            )
            result.files_failed += 1
            # Record how many attempts were spent so a permanent failure is
            # honest about the retry effort (P4-8). The attempt count is a pure
            # function of the input and the failure kind, so this reason is
            # stable across a full rescan and an incremental run.
            n = attempts.get(rel, 1)
            ledger_rows.append(
                (rel, "failed", f"failed after {n} attempts: {failed[rel]}")
            )

    # Write the coverage ledger. Dispositions are already final:
    # parsed | excluded:<rule> | failed | binary (invariant I2).
    counts: dict[str, int] = {}
    for path, disposition, reason in ledger_rows:
        store.add_coverage(path, disposition, reason or None)
        counts[disposition] = counts.get(disposition, 0) + 1
    result.ledger = counts

    store.commit()
    return result
