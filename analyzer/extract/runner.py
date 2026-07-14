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
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..constants import LANGUAGE_MAP, SKIP_EXTENSIONS
from ..parsers import PARSERS
from ..store import LOCAL_REPO, ROOT_COMPONENT, FactStore, assign_symbol_ids
from ..utils import _is_vendored_repo, _should_skip_dir
from .facts import FileFacts
from .signals import extract_entity_signals, extract_rule_signals, extract_signals

# p4-extract/1 -> p5-extract/1: extraction now also emits `data_entity` signals
# (P5-2). p5-extract/1 -> p5-extract/2: extraction now also emits `rule` signals
# (P5-5). Bumping the tier invalidates the content-hash cache so a warm store is
# re-extracted once and never silently serves cached facts that predate the new
# signal kind (invariant I2 / "no silent anything").
EXTRACT_TIER = "p5-extract/2"
INLINE_THRESHOLD = 8  # below this many cache misses, parse inline (no pool)

# v2-only schema formats that are not in the shared LANGUAGE_MAP (which v1
# scanner.py reads). `.sql` and `.json` are already enumerated; `.prisma` is not,
# so it is recognized here on the v2 path only, leaving v1 output byte-stable.
_SCHEMA_ONLY_EXTENSIONS = {".prisma": "prisma"}


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
        module_doc = parser.extract_file_doc(content) if parser else None
        signals = extract_signals(content, language, parser) if parser else []
        # Entity signals are parser-independent (pure regex), so they run for
        # both code files and parser-less schema files (P5-2, Data lens L3).
        signals = signals + extract_entity_signals(content, language, rel)
        # Rule signals are likewise parser-independent (P5-5, Rules lens L6).
        signals = signals + extract_rule_signals(content, language, rel)
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
            if _should_skip_dir(d):
                ledger.append((child, "excluded:skipped_directory", d))
                for ci_path in _ci_files_in_pruned_dir(dirpath, d):
                    add_ci_candidate(ci_path)
            elif _is_vendored_repo(os.path.join(dirpath, d)):
                ledger.append((child, "excluded:vendored_repo", d))
            else:
                kept.append(d)
        dirnames[:] = kept

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel = os.path.relpath(fpath, root)
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

            language = LANGUAGE_MAP.get(ext) or _SCHEMA_ONLY_EXTENSIONS.get(ext)
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
    tasks = [(c.rel, c.language, c.content, c.pversion) for c in queue]
    hash_by_rel = {c.rel: c.content_hash for c in queue}

    n_workers = _worker_count(len(queue), max_workers)
    result.worker_count = n_workers

    if queue and n_workers > 1 and len(queue) >= INLINE_THRESHOLD:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            outcomes = list(pool.map(_parse_worker, tasks))
    else:
        result.worker_count = 1
        outcomes = [_parse_worker(t) for t in tasks]

    for rel, status, payload in outcomes:
        if status == "ok":
            facts = FileFacts.from_dict(payload)
            facts.content_hash = hash_by_rel[rel]
            parsed[rel] = facts
            store.cache_facts(facts.content_hash, facts.parser_version, facts.to_dict())
        else:
            failed[rel] = str(payload)

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
            ledger_rows.append((rel, "failed", failed[rel]))

    # Write the coverage ledger. Dispositions are already final:
    # parsed | excluded:<rule> | failed | binary (invariant I2).
    counts: dict[str, int] = {}
    for path, disposition, reason in ledger_rows:
        store.add_coverage(path, disposition, reason or None)
        counts[disposition] = counts.get(disposition, 0) + 1
    result.ledger = counts

    store.commit()
    return result
