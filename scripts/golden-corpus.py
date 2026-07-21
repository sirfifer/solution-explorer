#!/usr/bin/env python3
"""Golden-corpus regression harness (card G2).

This is the clean regression signal that the always-changing demo and dogfood
cannot give (REGRESSION-STRATEGY.md). It analyzes a respected real-world
repository held FROZEN at a pinned commit, so any diff between a fresh
generation and the approved baseline is attributable to OUR engine change, not
to the target moving.

Storage model (owner decision, 2026-07-20): fetch-at-pinned-commit plus a
committed baseline. The corpus source is never vendored into this repo; a small
lock file pins the exact commit and the harness fetches it on demand into a
gitignored cache. Only the approved baseline projection is committed.

Layout:
    tests/golden/<name>/corpus.lock   pinned repo + commit + excludes (committed)
    tests/golden/<name>/baseline.json approved projection            (committed)
    .golden-cache/<name>/             fetched source at the pinned SHA (gitignored)

Subcommands:
    list                 show configured corpora and whether a baseline exists
    fetch <name>         fetch the pinned commit into the cache (idempotent)
    generate <name>      fetch, then analyze into a projection (default stdout path)
    baseline <name>      fetch, analyze, and APPROVE (write baseline.json) -- the
                         re-baseline procedure; run at a stopping point on purpose
    check <name>         fetch, analyze, and diff against the committed baseline;
                         a non-empty diff that is not an intended improvement is a
                         regression to investigate. Exits 1 on drift (CI gate).
    parity <name>        prove the full-vs-incremental parity contract at scale
                         (card G4): a cold full regeneration and a warm rerun must
                         produce the same projection, and a warm incremental over
                         a one-file edit must equal a cold full of the mutated
                         tree. Exits 1 on any divergence (a real engine finding).

The first corpus is FLASK (pallets/flask, BSD-3-Clause, SWE-bench standard):
stable, small, low diff noise, built first while the harness is shaken out.
FASTAPI is added second for lens breadth (see REGRESSION-STRATEGY.md).

The diff itself is the G1 projection-diff tool, imported here so the harness and
the demo/dogfood two-slot flow (G3) speak exactly the same delta language.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"
CACHE_DIR = REPO_ROOT / ".golden-cache"
ANALYZE_SCRIPT = REPO_ROOT / "analyze.py"

# The parity check (G4) reuses analyzer.parity's volatile-field allowlist. Put
# THIS checkout first on sys.path so `import analyzer` resolves to the repo the
# harness lives in (a worktree, or the CI checkout), not whatever an editable
# install elsewhere points at. The rest of the harness shells out to analyze.py
# in a fresh process, so this only affects the in-process parity import.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Markers bounding the harness-managed excludes block appended to a fetched
# corpus's .gitignore. Rewritten on every fetch so the block is idempotent and
# deterministic (the analyzer honors .gitignore, so this is how a corpus can
# exclude, e.g., FastAPI's translated docs from the scan).
_EXCLUDE_BEGIN = "# >>> golden-corpus excludes (managed)"
_EXCLUDE_END = "# <<< golden-corpus excludes (managed)"


def _load_projection_diff():
    """Load the sibling projection-diff.py module (hyphenated name)."""
    path = SCRIPTS_DIR / "projection-diff.py"
    spec = importlib.util.spec_from_file_location("projection_diff", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_corpus(name: str, golden_dir: Optional[Path] = None) -> dict:
    """Load and validate a corpus lock file.

    A lock must pin an exact commit (not just a mutable tag) so a fetch is
    reproducible. The tag/ref is retained for humans and for re-baselining.
    """
    golden_dir = golden_dir or GOLDEN_DIR
    lock_path = golden_dir / name / "corpus.lock"
    if not lock_path.exists():
        raise FileNotFoundError(f"no corpus lock for '{name}' at {lock_path}")
    with lock_path.open(encoding="utf-8") as fh:
        lock = json.load(fh)
    for required in ("name", "repo", "commit"):
        if not lock.get(required):
            raise ValueError(f"corpus lock {lock_path} is missing '{required}'")
    if lock["name"] != name:
        raise ValueError(
            f"corpus lock name '{lock['name']}' does not match directory '{name}'"
        )
    lock.setdefault("ref", lock["commit"])
    lock.setdefault("exclude", [])
    return lock


def list_corpora(golden_dir: Optional[Path] = None) -> list[str]:
    """Names of every configured corpus (a directory with a corpus.lock)."""
    golden_dir = golden_dir or GOLDEN_DIR
    if not golden_dir.exists():
        return []
    return sorted(
        p.name for p in golden_dir.iterdir() if (p / "corpus.lock").exists()
    )


def baseline_path(name: str, golden_dir: Optional[Path] = None) -> Path:
    golden_dir = golden_dir or GOLDEN_DIR
    return golden_dir / name / "baseline.json"


def _out_dir(name: str, cache_dir: Optional[Path] = None) -> Path:
    """Directory for generated projections and their sidecars.

    Deliberately a SIBLING of the fetched source (cache/_out/<name>), never
    inside it. analyze.py writes companion artifacts (ai.json, sbom.json, ...)
    next to its output; writing them into the scanned corpus would pollute it so
    the next scan counts the harness's own output as source files. Keeping the
    output tree out of the source tree is what makes a check reproducible.
    """
    cache_dir = cache_dir or CACHE_DIR
    return cache_dir / "_out" / name


def _apply_excludes(src: Path, excludes: list[str]) -> None:
    """Rewrite the managed excludes block in the corpus .gitignore.

    Idempotent: the block between the markers is fully replaced each call, so a
    re-fetch never accumulates duplicates and the checkout stays deterministic.
    """
    gitignore = src / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = existing.splitlines()
    # Strip any prior managed block.
    cleaned: list[str] = []
    in_block = False
    for line in lines:
        if line.strip() == _EXCLUDE_BEGIN:
            in_block = True
            continue
        if line.strip() == _EXCLUDE_END:
            in_block = False
            continue
        if not in_block:
            cleaned.append(line)
    if excludes:
        cleaned.append(_EXCLUDE_BEGIN)
        cleaned.extend(excludes)
        cleaned.append(_EXCLUDE_END)
    gitignore.write_text("\n".join(cleaned).rstrip("\n") + "\n", encoding="utf-8")


def fetch_corpus(
    corpus: dict, cache_dir: Optional[Path] = None, *, force: bool = False
) -> Path:
    """Fetch the pinned commit into the cache, returning the source path.

    Idempotent: if the cache is already checked out at the pinned commit, this
    is a no-op unless ``force``. Uses a depth-1 fetch of the exact SHA, so no
    history is downloaded and the checkout is byte-stable at the pin.
    """
    cache_dir = cache_dir or CACHE_DIR
    name = corpus["name"]
    commit = corpus["commit"]
    src = cache_dir / name

    if not force and (src / ".git").exists():
        try:
            head = subprocess.run(
                ["git", "-C", str(src), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            head = ""
        if head == commit:
            _apply_excludes(src, corpus.get("exclude", []))
            return src

    if src.exists():
        _rmtree(src)
    src.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(src), *args], check=True)

    git("init", "-q")
    git("remote", "add", "origin", corpus["repo"])
    # Fetch the exact commit (GitHub allows fetching a reachable SHA directly).
    git("fetch", "--depth", "1", "origin", commit)
    git("checkout", "-q", "FETCH_HEAD")

    head = subprocess.run(
        ["git", "-C", str(src), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if head != commit:
        raise RuntimeError(
            f"fetched HEAD {head} does not match pinned commit {commit} for '{name}'"
        )
    _apply_excludes(src, corpus.get("exclude", []))
    return src


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def generate_projection(
    src: Path, out_path: Path, *, analyze_script: Path = ANALYZE_SCRIPT, cold: bool = True
) -> Path:
    """Analyze a fetched corpus into a full projection.

    Cold by default: the fact store under the source is removed first, so every
    generation is a fresh full run independent of any accumulated warm state.
    Reproducibility beats speed for a golden baseline, and it keeps the baseline
    and the check comparing like with like (warm-vs-cold parity is G4's job, not
    a variable that should leak into the regression signal).
    """
    if cold:
        _rmtree(src / ".solution-explorer")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(analyze_script),
            str(src),
            "-o",
            str(out_path),
            "--compact",
        ],
        check=True,
    )
    return out_path


def diff_against_baseline(generated: Path, baseline: Path) -> dict:
    """Return the G1 projection-diff between a generated projection and baseline."""
    pd = _load_projection_diff()
    old = pd.load_projection(baseline)
    new = pd.load_projection(generated)
    return pd.diff_projections(old, new)


def render_diff_text(diff: dict) -> str:
    return _load_projection_diff().render_text(diff)


# ---------------------------------------------------------------------------
# Full-vs-incremental parity at scale (card G4)
# ---------------------------------------------------------------------------


def _normalize_for_parity():
    """Import this checkout's analyzer.parity.normalize_for_parity (see sys.path
    note above), so the parity compare uses the SAME volatile-field allowlist as
    the engine-parity fixture guard rather than a second, drifting copy."""
    from analyzer.parity import normalize_for_parity

    return normalize_for_parity


def _compare_projections(a_path: Path, b_path: Path) -> Optional[dict]:
    """Return None when two projections are byte-identical after normalization.

    On a mismatch, return the G1 projection diff as the human-readable
    explanation. The comparison strips only the volatile fields (timestamps,
    machine path, version, changelog) and then compares bytes with LIST ORDER
    PRESERVED, which is strictly stronger than the G1 semantic diff (it also
    catches an ordering regression a by-id diff would miss). It is never weakened
    to make a real difference pass.
    """
    normalize = _normalize_for_parity()
    with a_path.open(encoding="utf-8") as fh:
        a = json.load(fh)
    with b_path.open(encoding="utf-8") as fh:
        b = json.load(fh)
    if normalize(a) == normalize(b):
        return None
    pd = _load_projection_diff()
    return pd.diff_projections(pd.load_projection(a_path), pd.load_projection(b_path))


def _pick_source_file(projection_path: Path, src: Path) -> Optional[Path]:
    """Pick a deterministic real source file from a projection, for the mutation
    variant. First parsed ``.py`` file by sorted path (both corpora are Python),
    resolved under the fetched ``src`` and confirmed on disk. Returns None when
    none is available (the mutation variant is then skipped, not failed)."""
    try:
        with projection_path.open(encoding="utf-8") as fh:
            projection = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    for rel in sorted(
        f.get("path", "") for f in projection.get("files", [])
        if str(f.get("path", "")).endswith(".py")
    ):
        candidate = src / rel
        if candidate.is_file():
            return candidate
    return None


def run_parity(
    name: str,
    *,
    force: bool = False,
    mutate: bool = True,
    golden_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> int:
    """Prove the incremental-equals-full contract on a frozen corpus at scale.

    Two checks, both required to pass:

      1. NO-CHANGE parity: a cold full regeneration and a warm rerun (the store
         is NOT wiped) over the unchanged tree must produce the same projection.
      2. CHANGED-FILE parity (when ``mutate``): after the cold baseline, one
         source file is edited, a warm incremental run and a cold full run are
         taken over the mutated tree, and they must agree. This proves the
         changed-file path, not only the no-change path. The edit is always
         reverted, so the frozen corpus is left untouched.

    A mismatch prints the G1 diff as the explanation and returns 1; it is a real
    engine finding, never papered over.
    """

    def _report_failure(kind: str, diff: dict) -> None:
        sys.stderr.write(
            f"\nPARITY FAILURE ({kind}): the two runs over the same tree produced "
            "different projections. This is a real incremental-vs-full engine "
            "divergence, not a harness issue. The G1 diff explains it:\n"
        )
        sys.stderr.write(render_diff_text(diff))
        if not diff.get("has_changes"):
            # The byte compare is authoritative and stronger than the semantic
            # diff. If the semantic diff finds nothing, the difference is in list
            # ORDER or a field the by-id diff does not track; say so plainly
            # rather than let the empty diff read as "nothing wrong".
            sys.stderr.write(
                "\n(The semantic diff shows no section change, so the divergence "
                "is a list-ordering or untracked-field difference. The byte-parity "
                "compare is authoritative and it flagged a real difference.)\n"
            )

    corpus = load_corpus(name, golden_dir)
    src = fetch_corpus(corpus, cache_dir, force=force)
    base = _out_dir(name, cache_dir) / "parity"

    print(f"Parity: {name} (cold full vs warm rerun over the frozen tree)")
    cold = base / "cold" / "projection.json"
    warm = base / "warm" / "projection.json"
    generate_projection(src, cold, cold=True)   # wipe the store, full parse
    generate_projection(src, warm, cold=False)  # reuse the warm store
    nochange_diff = _compare_projections(cold, warm)
    if nochange_diff is None:
        print("  OK: warm rerun is byte-identical to the cold full run (no-change parity).")
    else:
        _report_failure("no-change", nochange_diff)

    changed_ok = True
    if mutate:
        mut_file = _pick_source_file(cold, src)
        if mut_file is None:
            print("  changed-file parity SKIPPED: no picked source file in the projection.")
        else:
            rel = mut_file.relative_to(src)
            print(f"Parity: {name} (changed-file: warm incremental vs cold full, edit {rel})")
            original = mut_file.read_text(encoding="utf-8")
            try:
                mut_file.write_text(
                    original + "\n# golden-corpus parity: synthetic edit\n",
                    encoding="utf-8",
                )
                mut_warm = base / "mut-warm" / "projection.json"
                mut_cold = base / "mut-cold" / "projection.json"
                generate_projection(src, mut_warm, cold=False)  # warm incremental
                generate_projection(src, mut_cold, cold=True)   # cold full, mutated tree
                changed_diff = _compare_projections(mut_warm, mut_cold)
            finally:
                mut_file.write_text(original, encoding="utf-8")  # restore the frozen corpus
            if changed_diff is None:
                print(
                    "  OK: warm incremental equals cold full on the mutated tree "
                    "(changed-file parity)."
                )
            else:
                changed_ok = False
                _report_failure("changed-file", changed_diff)

    if nochange_diff is None and changed_ok:
        print(f"\nOK: '{name}' full-vs-incremental parity holds.")
        return 0
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    names = list_corpora()
    if not names:
        print("no corpora configured under tests/golden/")
        return 0
    for name in names:
        corpus = load_corpus(name)
        has_baseline = baseline_path(name).exists()
        state = "baseline present" if has_baseline else "NO baseline (run: baseline)"
        print(f"{name}: {corpus['repo']} @ {corpus.get('ref')} ({corpus['commit'][:12]}) - {state}")
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.name)
    src = fetch_corpus(corpus, force=args.force)
    print(f"fetched {args.name} @ {corpus['commit']} -> {src}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.name)
    src = fetch_corpus(corpus, force=args.force)
    out = Path(args.output) if args.output else _out_dir(args.name) / "projection.json"
    generate_projection(src, out)
    print(f"generated projection -> {out}")
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.name)
    src = fetch_corpus(corpus, force=args.force)
    # analyze.py writes companion artifacts (ai.json, sbom.json, llms.txt, ...)
    # into the output directory. Generate into the gitignored cache so those
    # sidecars never pollute the committed golden directory, then copy only the
    # monolith projection into place. corpus.lock and baseline.json are the whole
    # committed contract.
    candidate = _out_dir(args.name) / "baseline-candidate.json"
    generate_projection(src, candidate)
    target = baseline_path(args.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, target)
    print(f"approved baseline for {args.name} @ {corpus['commit']} -> {target}")
    print("Review the diff and commit the new baseline to record the approval.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.name)
    baseline = baseline_path(args.name)
    if not baseline.exists():
        print(
            f"error: no committed baseline for '{args.name}'. Run: "
            f"golden-corpus.py baseline {args.name}",
            file=sys.stderr,
        )
        return 2

    if args.generated:
        generated = Path(args.generated)
    else:
        src = fetch_corpus(corpus, force=args.force)
        generated = _out_dir(args.name) / "projection.json"
        generate_projection(src, generated)

    diff = diff_against_baseline(generated, baseline)

    if args.format == "json":
        sys.stdout.write(json.dumps(diff, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_diff_text(diff))

    if diff["has_changes"]:
        print(
            f"\nGOLDEN DRIFT: '{args.name}' differs from the approved baseline. "
            "If this is an intended engine improvement, re-baseline "
            f"(golden-corpus.py baseline {args.name}) and commit; otherwise "
            "investigate as a regression.",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: '{args.name}' matches the approved baseline (no drift).")
    return 0


def _cmd_parity(args: argparse.Namespace) -> int:
    return run_parity(args.name, force=args.force, mutate=not args.no_mutate)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Golden-corpus regression harness (G2): analyze a frozen "
        "real-world repo and diff against an approved baseline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list configured corpora")
    p_list.set_defaults(func=_cmd_list)

    for name, func, help_text in (
        ("fetch", _cmd_fetch, "fetch the pinned commit into the cache"),
        ("generate", _cmd_generate, "fetch and analyze into a projection"),
        ("baseline", _cmd_baseline, "fetch, analyze, and approve a new baseline"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("name", help="corpus name (directory under tests/golden/)")
        sp.add_argument(
            "--force", action="store_true", help="re-fetch even if the cache is at the pin"
        )
        if name == "generate":
            sp.add_argument("-o", "--output", help="projection output path")
        sp.set_defaults(func=func)

    p_check = sub.add_parser(
        "check", help="diff a fresh generation against the approved baseline"
    )
    p_check.add_argument("name", help="corpus name (directory under tests/golden/)")
    p_check.add_argument(
        "--force", action="store_true", help="re-fetch even if the cache is at the pin"
    )
    p_check.add_argument(
        "--generated",
        help="use this pre-generated projection instead of fetching and analyzing",
    )
    p_check.add_argument(
        "--format", choices=("text", "json"), default="text", help="diff output format"
    )
    p_check.set_defaults(func=_cmd_check)

    p_parity = sub.add_parser(
        "parity",
        help="prove full-vs-incremental parity: cold full == warm rerun (G4)",
    )
    p_parity.add_argument("name", help="corpus name (directory under tests/golden/)")
    p_parity.add_argument(
        "--force", action="store_true", help="re-fetch even if the cache is at the pin"
    )
    p_parity.add_argument(
        "--no-mutate",
        action="store_true",
        help="skip the changed-file variant, run only the no-change parity",
    )
    p_parity.set_defaults(func=_cmd_parity)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"error: command failed ({exc})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
