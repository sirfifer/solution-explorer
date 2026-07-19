"""Non-source inventory (P6-10; repo totality).

The coverage ledger records every file under the scan root with exactly one
disposition. The CoverageBadge splits those dispositions into three families:
analyzed source, source gaps, and NON-SOURCE ACCOUNTED. This module takes the
non-source family and answers, deterministically and without any AI, three
questions for every file that reached the repository but is not analyzable
source: what is it, why is it probably here, and what should you do about it.

Owner directive (2026-07-14): the unit of totality is the repository, not the
source subset. The unamentis-ios demo showed "6,046 non-source files accounted
for" and 5,970 of them were one accidentally committed TestResults.xcresult
bundle plus a .DS_Store. The tool counted them honestly but explained nothing.
The inventory makes that discovery one drill away: a dominant group is ranked
first and carries a plain-language cleanup recommendation, so gross
disproportion between source and non-source becomes a finding on its own.

Tier discipline (invariant I1, I9): this is a Tier 3/4 reader. It reads ledger
paths, dispositions, and reasons; it may ``stat`` a file for its size and read
the repository's top-level ``.gitignore``; it NEVER reads file contents and it
never calls a model. AI may later elaborate a group through an ``ai_enhance``
overlay (the group shape leaves room for that), but the deterministic skeleton
must stand on its own.

Classification uses path components AND extension together, never extension
alone: a ``.md`` under ``docs/`` is documentation while a ``.md`` under
``prompts/`` or ``.claude/`` is agent content that is part of the product. The
rules are ordered and the first match wins, so more specific contexts (a file
inside a build-output bundle) win over broader ones (its extension).

Pruned-directory ruling (matches the coverage ledger, TARGET-ARCHITECTURE.md
section 7): an excluded directory is ONE ledger row standing for everything
beneath it. This module classifies that single row honestly as what the ledger
knows and never fabricates per-file counts under it, so a pruned ``node_modules``
contributes one row to the vendored group, not thousands.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Optional

__all__ = ["INVENTORY_VERSION", "build_inventory", "classify_row", "CATEGORY_META"]

# Bump when the emitted shape changes. The viewer reads this and an older
# dataset without an inventory section degrades to the plain coverage panel.
INVENTORY_VERSION = 1

# Bounds so a group with millions of files stays small in the projection. The
# viewer virtualizes over the sample it fetches here; the complete per-file
# enumeration always remains available in the coverage ledger drill-in (which
# already carries every row), so a bounded sample never hides anything. The
# sample is generous enough to be worth virtualizing while keeping coverage.json
# from doubling in size on a huge repo.
_MAX_SAMPLES = 200
_MAX_TOP_DIRS = 12
_MAX_EXTENSIONS = 20

# The non-source dispositions, mirroring the viewer's CoverageBadge
# NON_SOURCE_DISPOSITIONS so the analyzer and the viewer agree on exactly which
# rows the inventory covers. Everything else that is not "parsed" is a source
# gap (failed, oversized), already surfaced loudly in the coverage gaps family,
# so it is out of scope here.
NON_SOURCE_DISPOSITIONS = frozenset({
    "binary",
    "excluded:unsupported_extension",
    "excluded:empty_file",
    "excluded:skipped_directory",
    "excluded:vendored_repo",
})

# Dispositions whose single row stands in for a whole pruned subtree. The
# inventory counts these as one row and never invents per-file counts beneath
# them (the pruned-directory ruling).
_DIRECTORY_DISPOSITIONS = frozenset({
    "excluded:skipped_directory",
    "excluded:vendored_repo",
})


# ---------------------------------------------------------------------------
# Category metadata
# ---------------------------------------------------------------------------
# Each category carries a stable id, a human label, a one-line explanation of
# what the group is and why it is probably in the repo, a high-level
# recommendation, and its default flags. Copy follows the project writing rule:
# no em or en dashes, commas and periods only.

CATEGORY_META: dict[str, dict] = {
    "documentation": {
        "label": "Documentation",
        "explanation": "Human-readable docs, readmes, licenses, and change logs.",
        "recommendation": "Keep. This is intended repository content.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "agent_content": {
        "label": "Agent and prompt content",
        "explanation": "Instructions and prompts that steer AI tools. Part of the product, not stray text.",
        "recommendation": "Keep. Treat as first-class product content and review it like code.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "product_assets": {
        "label": "Product assets",
        "explanation": "Images, fonts, media, and asset catalogs the product ships.",
        "recommendation": "Keep. Expected here. Consider Git LFS if large binaries bloat the history.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "localization": {
        "label": "Localization",
        "explanation": "Translated strings and locale resources.",
        "recommendation": "Keep. This is translated product content.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "ui_definition": {
        "label": "Interface Builder UI",
        "explanation": "Interface Builder UI definitions such as storyboards and xib files. The tool does not parse them into screens yet.",
        "recommendation": "Keep. These define UI layouts. Parsing them into the graph is planned.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "build_test_output": {
        "label": "Build and test output",
        "explanation": "Generated artifacts from building or testing, such as test result bundles, coverage reports, and logs.",
        "recommendation": "Remove from version control and add to .gitignore. These are regenerated on every build.",
        "flags": {"security_sensitive": False, "likely_unwanted": True, "gitignore_candidate": True},
    },
    "ide_metadata": {
        "label": "IDE and workspace metadata",
        "explanation": "Editor and project settings such as .idea, .vscode, and Xcode project internals.",
        "recommendation": "Keep only the shared settings a team agrees on. Ignore per-user state.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "os_cruft": {
        "label": "Operating system cruft",
        "explanation": "Files the operating system drops into folders, such as .DS_Store and Thumbs.db.",
        "recommendation": "Remove from version control and add to .gitignore. These never belong in a repository.",
        "flags": {"security_sensitive": False, "likely_unwanted": True, "gitignore_candidate": True},
    },
    "backup_files": {
        "label": "Backup and editor droppings",
        "explanation": "Backup copies and editor save files such as .bak, .orig, .backup, and trailing-tilde files.",
        "recommendation": "Remove from version control and add to .gitignore. These are stray local copies, not intended content.",
        "flags": {"security_sensitive": False, "likely_unwanted": True, "gitignore_candidate": True},
    },
    "vcs_ci": {
        "label": "Version control and CI infrastructure",
        "explanation": "Version-control and continuous-integration plumbing such as .git, .github, and hooks.",
        "recommendation": "Keep. This is your automation and history configuration.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "config": {
        "label": "Configuration",
        "explanation": "Config files the analyzer has no parser for, such as plists, and yaml, toml, or json the parser did not claim.",
        "recommendation": "Keep, but review anything that carries environment or deployment settings.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "lockfile": {
        "label": "Dependency lockfiles",
        "explanation": "Pinned dependency graphs such as package-lock.json, Podfile.lock, and Cargo.lock.",
        "recommendation": "Keep. Lockfiles make builds reproducible.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "secrets": {
        "label": "Certificates, keys, and secret-shaped files",
        "explanation": "Files shaped like certificates, private keys, or credential stores.",
        "recommendation": "Verify intent. If any of these are real secrets, remove them from history and rotate the credential.",
        "flags": {"security_sensitive": True, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "archive": {
        "label": "Archives",
        "explanation": "Compressed or packaged bundles such as zip, tar, and jar files.",
        "recommendation": "Review. Archives are often build inputs or outputs that do not need to live in the repo.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "data": {
        "label": "Data files",
        "explanation": "Datasets, databases, and model files such as csv, sqlite, machine-learning weights, and Core Data models.",
        "recommendation": "Review. Large data files usually belong in storage or Git LFS, not the source tree.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
    "vendored": {
        "label": "Vendored dependencies",
        "explanation": "Third-party code checked into the tree, such as node_modules, vendor, and Pods.",
        "recommendation": "Usually keep ignored and let the package manager restore it. Vendor deliberately only when you must.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": True},
    },
    "unknown": {
        "label": "Unknown",
        "explanation": "Non-source files that matched no known category. Flagged loudly so nothing hides in a silent bucket.",
        "recommendation": "Inspect these directly. The tool cannot say what they are.",
        "flags": {"security_sensitive": False, "likely_unwanted": False, "gitignore_candidate": False},
    },
}

# Fixed rank order for the categories, applied only as the final tie-break after
# count and bytes, so ranking is fully deterministic (I4, I11).
_CATEGORY_ORDER = list(CATEGORY_META.keys())


# ---------------------------------------------------------------------------
# Extension families
# ---------------------------------------------------------------------------

_IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".bmp", ".tiff", ".tif", ".icns", ".heic",
})
_MEDIA_EXTS = frozenset({
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov", ".avi", ".m4a",
    ".aac", ".flac", ".mkv", ".m4v",
})
_FONT_EXTS = frozenset({".woff", ".woff2", ".ttf", ".eot", ".otf"})
_ASSET_EXTS = _IMAGE_EXTS | _MEDIA_EXTS | _FONT_EXTS

_DOC_EXTS = frozenset({
    ".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".asciidoc",
    ".rtf", ".pdf", ".doc", ".docx",
})
_DOC_NAMES = frozenset({
    "license", "license.txt", "license.md", "licence", "notice", "copying",
    "authors", "contributors", "changelog", "changelog.md", "readme",
    "readme.md", "readme.txt", "code_of_conduct.md",
})

_LOCALIZATION_EXTS = frozenset({".strings", ".stringsdict", ".xcstrings", ".po", ".pot", ".mo"})

_ARCHIVE_EXTS = frozenset({
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z", ".tgz",
    ".jar", ".war", ".aar", ".dmg", ".pkg", ".iso",
})

_LOCKFILE_EXTS = frozenset({".lock", ".sum", ".resolved"})
_LOCKFILE_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "podfile.lock",
    "package.resolved", "cargo.lock", "poetry.lock", "gemfile.lock",
    "composer.lock", "go.sum", "flake.lock", "bun.lockb", "pipfile.lock",
})

_SECRET_EXTS = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".crt", ".cer",
    ".der", ".mobileprovision", ".provisionprofile", ".asc", ".gpg", ".pub",
})
_SECRET_NAMES = frozenset({
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".env", ".env.local",
    ".env.production", ".env.development", ".netrc", ".npmrc",
})

_DATA_EXTS = frozenset({
    ".csv", ".tsv", ".parquet", ".arrow", ".feather", ".xls", ".xlsx",
    ".db", ".sqlite", ".sqlite3", ".dat", ".bin", ".pickle", ".pkl",
    ".npy", ".npz", ".h5", ".hdf5", ".avro", ".orc",
    ".gguf", ".mlmodel", ".mlmodelc", ".mlpackage", ".onnx", ".pt", ".pth",
    ".pb", ".tflite", ".safetensors",
})

_CONFIG_EXTS = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".plist", ".xml", ".ini", ".cfg",
    ".conf", ".properties", ".editorconfig", ".entitlements", ".xcconfig",
    ".pbxproj", ".xcsettings", ".xcscheme", ".xcprivacy",
})
# Tool configuration dotfiles whose whole name is the config (no useful
# extension to key off, such as ".swiftformat"). Matched by exact filename.
_CONFIG_NAMES = frozenset({
    ".swiftformat", ".swiftlint.yml", ".swiftlint.yaml", ".swiftgen.yml",
    ".prettierrc", ".stylelintrc", ".babelrc", ".clang-format", ".clang-tidy",
})

# Directory-name tokens (lowercased) that anchor a category when they appear as
# a path component. Checked with the extension, per the context rule.
_BUILD_DIR_TOKENS = frozenset({
    ".build", "build", "dist", "deriveddata", "coverage", "htmlcov",
    ".gradle", "target", ".next", ".nuxt", ".output", ".turbo", ".vercel",
    "out", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
})
_IDE_DIR_TOKENS = frozenset({".idea", ".vscode", ".vs", ".swiftpm", ".fleet"})
_VENDOR_DIR_TOKENS = frozenset({
    "node_modules", "vendor", "pods", "bower_components", "third_party",
    "third-party", ".yarn", "packages_cache",
})
_VCS_DIR_TOKENS = frozenset({".git", ".github", ".circleci", ".gitlab", ".husky", ".hooks"})

# Extensions and trailing markers that identify a backup or editor-save dropping.
# A trailing tilde is matched on the whole filename because splitext keeps it on
# the extension side (``foo.py~`` -> ext ``.py~``), so the endswith test is used
# instead of an extension-set membership check.
_BACKUP_EXTS = frozenset({".backup", ".bak", ".orig"})
_AGENT_DIR_TOKENS = frozenset({".claude", "prompts", ".cursor", ".continue", ".aider"})
_LOCALIZATION_DIR_TOKENS = frozenset({"translations", "locales", "i18n", "l10n"})


def _tokens(path: str) -> list[str]:
    """Path components in POSIX order, lowercased."""
    norm = path.replace("\\", "/")
    return [p.lower() for p in norm.split("/") if p]


def classify_row(path: str, disposition: str, reason: Optional[str] = None) -> str:
    """Return the category id for one non-source ledger row.

    Path components and the extension are considered together and the first
    matching rule wins, so a file inside a build-output bundle is build output
    regardless of its extension, and a ``.md`` under ``prompts/`` is agent
    content while a ``.md`` under ``docs/`` is documentation. A row that matches
    nothing lands in ``unknown`` (loud), never a silent catch-all.
    """
    parts = _tokens(path)
    partset = set(parts)
    filename = parts[-1] if parts else path.lower()
    ext = os.path.splitext(filename)[1]

    # Vendored repos are declared by the ledger disposition itself.
    if disposition == "excluded:vendored_repo":
        return "vendored"

    # 1. Build and test output. A path inside an Xcode result bundle or any
    #    build/coverage directory is build output before anything else, so the
    #    thousands of files inside a committed .xcresult all land here.
    if any(p.endswith(".xcresult") for p in parts):
        return "build_test_output"
    if partset & _BUILD_DIR_TOKENS:
        return "build_test_output"
    if ext in {".log", ".xcactivitylog", ".gcda", ".gcno", ".profraw", ".profdata"}:
        return "build_test_output"
    if filename in {"lcov.info", "coverage.xml", ".coverage"}:
        return "build_test_output"

    # 2. Operating system cruft.
    if filename in {".ds_store", "thumbs.db", "desktop.ini", ".spotlight-v100", ".trashes"}:
        return "os_cruft"

    # 3. Backup and editor droppings. Checked early so a backup of any other file
    #    type (for example ``config.json.bak`` or ``main.py~``) reads as a stray
    #    copy to remove, not as the thing it is a backup of.
    if ext in _BACKUP_EXTS or filename.endswith("~"):
        return "backup_files"

    # 4. IDE and workspace metadata. Xcode project bundles are directories that
    #    are walked (not pruned), so their internals arrive as per-file rows.
    if partset & _IDE_DIR_TOKENS:
        return "ide_metadata"
    if any(p.endswith(".xcodeproj") or p.endswith(".xcworkspace") for p in parts):
        return "ide_metadata"
    if ext == ".xcworkspace" or filename.endswith(".xcuserstate"):
        return "ide_metadata"

    # 4. Certificates, keys, and secret-shaped files. Checked early so a stray
    #    key is never absorbed by a broader config or data rule.
    if ext in _SECRET_EXTS or filename in _SECRET_NAMES or filename.startswith(".env"):
        return "secrets"

    # 5. Agent and prompt content. A prompts/ or .claude/ context wins over the
    #    documentation rule for the same .md extension.
    if partset & _AGENT_DIR_TOKENS:
        return "agent_content"
    if filename in {"claude.md", "agents.md", ".cursorrules", ".windsurfrules"}:
        return "agent_content"
    if filename.endswith(".instructions.md") or filename.endswith(".prompt.md"):
        return "agent_content"

    # 6. Version control and CI infrastructure.
    if partset & _VCS_DIR_TOKENS:
        return "vcs_ci"
    if filename in {".gitignore", ".gitattributes", ".gitmodules", ".mailmap", ".gitkeep", "codeowners"}:
        return "vcs_ci"

    # 7. Vendored dependencies (per-file rows, when a vendored dir was walked).
    #    A .xcframework bundle is a third-party binary framework: everything
    #    inside it (binaries, headers, Info.plist) is vendored code we did not
    #    write, so the whole bundle lands here regardless of per-file extension.
    if any(p.endswith(".xcframework") for p in parts):
        return "vendored"
    if partset & _VENDOR_DIR_TOKENS:
        return "vendored"

    # 8. Localization.
    if any(p.endswith(".lproj") for p in parts):
        return "localization"
    if partset & _LOCALIZATION_DIR_TOKENS:
        return "localization"
    if ext in _LOCALIZATION_EXTS or filename in {"localizable.strings", "infoplist.strings"}:
        return "localization"

    # 9. Product assets: asset catalogs and shipped media.
    if any(
        p.endswith(".xcassets") or p.endswith(".imageset") or p.endswith(".appiconset")
        or p.endswith(".colorset") or p.endswith(".dataset")
        for p in parts
    ):
        return "product_assets"
    if ext in _ASSET_EXTS:
        return "product_assets"

    # 10. Interface Builder UI definitions. Storyboards and xib files describe UI
    #     layouts; the tool does not parse them into screens yet (that is P4-9),
    #     so this stops them landing in the loud unknown bucket in the meantime.
    if ext in {".storyboard", ".xib"}:
        return "ui_definition"

    # 11. Core Data models. A .xcdatamodeld (or its inner .xcdatamodel) is a data
    #     model bundle whose internals (for example the ``contents`` XML) are all
    #     data, not source; parsing it into entities is P4-9's job.
    if any(p.endswith(".xcdatamodeld") or p.endswith(".xcdatamodel") for p in parts):
        return "data"

    # 12. Archives.
    if ext in _ARCHIVE_EXTS:
        return "archive"

    # 13. Dependency lockfiles.
    if filename in _LOCKFILE_NAMES or ext in _LOCKFILE_EXTS:
        return "lockfile"

    # 14. Documentation. A docs/ context or a doc extension, now that the
    #     agent-content rule has already claimed prompt docs.
    if "docs" in partset or "doc" in partset:
        return "documentation"
    if ext in _DOC_EXTS or filename in _DOC_NAMES:
        return "documentation"

    # 15. Data files.
    if ext in _DATA_EXTS:
        return "data"

    # 16. Configuration the parser did not claim, including tool config dotfiles
    #     whose whole name is the config (``.swiftformat``) and Apple privacy
    #     manifests (``.xcprivacy``, a plist by any other name).
    if ext in _CONFIG_EXTS or filename in _CONFIG_NAMES:
        return "config"

    # 17. Unknown: loud, never a silent bucket.
    return "unknown"


# ---------------------------------------------------------------------------
# .gitignore reading (top-level only, cheap and bounded)
# ---------------------------------------------------------------------------

def _read_gitignore_patterns(root: Optional[Path]) -> list[str]:
    """Return the plain patterns from the repo's top-level .gitignore.

    Negations and comments are dropped and each pattern is reduced to a
    basename-level token for a cheap membership test. This is a heuristic used
    only to set the gitignore_candidate flag more honestly, never a full
    gitignore engine.
    """
    if root is None:
        return []
    path = Path(root) / ".gitignore"
    if not path.is_file():
        return []
    patterns: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue
            token = stripped.strip("/")
            if token:
                patterns.append(token.lower())
    except OSError:
        return []
    return patterns


def _is_ignored(path: str, patterns: list[str]) -> bool:
    """Best-effort check: is this path already covered by a top-level pattern.

    A path is treated as ignored when any of its components equals a pattern, or
    its basename matches a pattern as a glob. Good enough to avoid recommending
    a .gitignore entry that already exists.
    """
    if not patterns:
        return False
    parts = _tokens(path)
    partset = set(parts)
    basename = parts[-1] if parts else path.lower()
    for pat in patterns:
        base_pat = pat.rsplit("/", 1)[-1]
        if pat in partset or base_pat in partset:
            return True
        if fnmatch.fnmatch(basename, base_pat):
            return True
    return False


# ---------------------------------------------------------------------------
# Group assembly
# ---------------------------------------------------------------------------

def _file_size(root: Optional[Path], path: str) -> Optional[int]:
    """Stat a file for its size, when the tree is available. Bytes are
    environment data (like the git remote in prepare_arch), best-effort and
    omitted when the file is not on disk, so a re-projection from the store
    alone still works.
    """
    if root is None:
        return None
    try:
        st = os.stat(Path(root) / path)
    except OSError:
        return None
    if not os.path.isfile(Path(root) / path):
        return None
    return st.st_size


def _extension_of(path: str) -> str:
    filename = _tokens(path)[-1] if _tokens(path) else path
    ext = os.path.splitext(filename)[1].lower()
    return ext or "(none)"


def _top_directory(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def build_inventory(rows: list[dict], root=None) -> Optional[dict]:
    """Build the inventory section from coverage ledger rows.

    ``rows`` are the ledger rows (dicts with ``path``, ``disposition``,
    ``reason``) already sorted by path. Only the non-source family is classified;
    source gaps stay in the coverage gaps family where they already live.
    Returns ``None`` when there are no non-source rows, so the projection omits
    the section and the viewer degrades to the plain coverage panel.
    """
    root_path = Path(root) if root is not None else None
    patterns = _read_gitignore_patterns(root_path)

    # Aggregate per category in a single deterministic pass over sorted rows.
    groups: dict[str, dict] = {}
    source_gap_total = 0
    non_source_total = 0

    for row in rows:
        disposition = row.get("disposition", "")
        if disposition == "parsed":
            continue
        if disposition not in NON_SOURCE_DISPOSITIONS:
            source_gap_total += 1
            continue
        path = row.get("path", "")
        reason = row.get("reason")
        category = classify_row(path, disposition, reason)
        non_source_total += 1

        g = groups.get(category)
        if g is None:
            g = {
                "count": 0,
                "bytes": 0,
                "bytes_known": False,
                "directory_rows": 0,
                "ext_counts": {},
                "ext_bytes": {},
                "dir_counts": {},
                "samples": [],
                "any_gitignore_candidate": False,
            }
            groups[category] = g

        g["count"] += 1
        is_dir_row = disposition in _DIRECTORY_DISPOSITIONS
        if is_dir_row:
            g["directory_rows"] += 1
        else:
            size = _file_size(root_path, path)
            if size is not None:
                g["bytes"] += size
                g["bytes_known"] = True

        ext = _extension_of(path)
        g["ext_counts"][ext] = g["ext_counts"].get(ext, 0) + 1
        top = _top_directory(path)
        g["dir_counts"][top] = g["dir_counts"].get(top, 0) + 1
        if len(g["samples"]) < _MAX_SAMPLES:
            g["samples"].append(path)

        # A likely-unwanted or vendored group member that is not already ignored
        # makes the whole group a gitignore candidate.
        meta_flags = CATEGORY_META[category]["flags"]
        if meta_flags["gitignore_candidate"] and not _is_ignored(path, patterns):
            g["any_gitignore_candidate"] = True

    if non_source_total == 0:
        return None

    out_groups = [_finish_group(cat, g) for cat, g in groups.items()]
    out_groups.sort(key=_group_sort_key)

    dominant = None
    if out_groups:
        top_group = out_groups[0]
        # A group dominates when it is both the largest and more than half of
        # all non-source rows. The viewer turns this into the disproportion cue.
        if top_group["count"] * 2 > non_source_total:
            dominant = {
                "id": top_group["id"],
                "count": top_group["count"],
                "share": round(top_group["count"] / non_source_total, 4),
            }

    return {
        "version": INVENTORY_VERSION,
        "non_source_total": non_source_total,
        "source_gap_total": source_gap_total,
        "groups": out_groups,
        "dominant": dominant,
    }


def _finish_group(category: str, g: dict) -> dict:
    meta = CATEGORY_META[category]
    flags = dict(meta["flags"])
    # gitignore_candidate is only asserted when a real, not-yet-ignored member
    # exists, so we never nag about a directory that .gitignore already covers.
    if flags["gitignore_candidate"]:
        flags["gitignore_candidate"] = g["any_gitignore_candidate"]

    extensions = [
        {"ext": ext, "count": count}
        for ext, count in sorted(
            g["ext_counts"].items(), key=lambda kv: (-kv[1], kv[0])
        )[:_MAX_EXTENSIONS]
    ]
    top_directories = [
        {"dir": d, "count": count}
        for d, count in sorted(
            g["dir_counts"].items(), key=lambda kv: (-kv[1], kv[0])
        )[:_MAX_TOP_DIRS]
    ]

    group = {
        "id": category,
        "label": meta["label"],
        "explanation": meta["explanation"],
        "recommendation": meta["recommendation"],
        "count": g["count"],
        "bytes": g["bytes"] if g["bytes_known"] else None,
        "directory_rows": g["directory_rows"],
        "extensions": extensions,
        "top_directories": top_directories,
        "samples": g["samples"],
        "flags": flags,
    }
    return group


def _group_sort_key(group: dict):
    # Rank by count, then bytes, then the fixed category order, all descending
    # for the first two so the biggest group leads (I11 rank-don't-render).
    order = _CATEGORY_ORDER.index(group["id"]) if group["id"] in _CATEGORY_ORDER else len(_CATEGORY_ORDER)
    return (-group["count"], -(group["bytes"] or 0), order)
