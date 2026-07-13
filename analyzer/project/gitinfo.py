"""Environment facts read at projection time (git remote, default branch, plists).

Two things the derivation tier deliberately left to the projection tier
(TASKS.md P4-3 deviations 1 and 2):

  - **Git repository URL and default branch** are environment, not code. The
    ``derive-reads-only-the-store`` rule (TARGET-ARCHITECTURE.md 4.3) forbids
    derivation from touching ``.git``; reading it here does not violate it,
    because projection is allowed to consult the environment. The URL is
    credential-stripped the same way scanner.py does (F-CRIT-3), so a clone
    token never reaches the manifest the viewer serves.
  - **Info.plist app names.** Info.plist is binary, so it is not cached as text
    in the store; the app-name parse (CFBundleDisplayName / CFBundleName) cannot
    run store-only. Derivation keeps the directory name and marks the component
    ``application``; projection reads the plist from disk and overrides the name
    where one is resolvable, matching the old engine.

All functions here are pure reads of the filesystem under ``root`` and never
mutate anything on disk.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from ..config_parsers import parse_info_plist

__all__ = ["strip_url_credentials", "read_git_info", "apply_info_plist_names"]


def strip_url_credentials(url: str) -> str:
    """Remove embedded userinfo (``user:password@``) from a URL.

    Mirrors analyzer/scanner.py ``_strip_url_credentials`` exactly (F-CRIT-3):
    the ``https://x-access-token:<TOKEN>@github.com/...`` form that multi-repo
    cloning writes into ``.git/config`` must never reach the projected output.
    Non-URL or scp-like SSH remotes (``git@host:path``) carry no password and
    are returned unchanged.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.hostname or "@" not in parts.netloc:
        return url
    netloc = parts.hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def read_git_info(root) -> tuple[Optional[str], str]:
    """Return ``(repository_url, default_branch)`` read from ``root/.git``.

    The URL is normalized (SSH to HTTPS, trailing ``.git`` stripped) and
    credential-stripped, identical to scanner.py ``_detect_project_info``. The
    default branch comes from ``.git/HEAD``; it falls back to ``"main"`` when
    the file is absent, detached, or unreadable, again matching scanner.py.
    """
    root = Path(root)
    repository: Optional[str] = None
    default_branch = ""

    git_config = root / ".git" / "config"
    if git_config.exists():
        try:
            content = git_config.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"url\s*=\s*(.+)", content)
            if m:
                url = m.group(1).strip()
                url = re.sub(r"git@github\.com:", "https://github.com/", url)
                url = re.sub(r"\.git$", "", url)
                repository = strip_url_credentials(url)
        except OSError:
            pass

    head_ref = root / ".git" / "HEAD"
    if head_ref.exists():
        try:
            ref = head_ref.read_text(encoding="utf-8").strip()
            if ref.startswith("ref: refs/heads/"):
                default_branch = ref.removeprefix("ref: refs/heads/")
        except OSError:
            pass
    if not default_branch:
        default_branch = "main"

    return repository, default_branch


def apply_info_plist_names(components: list, root) -> int:
    """Override component names from Info.plist where resolvable, in place.

    Walks the component tree; for any component carrying an ``Info.plist``
    config-file entry, reads the plist at ``root/<path>`` and, if it yields a
    non-placeholder app name (CFBundleDisplayName / CFBundleName), replaces the
    directory-derived name the derivation tier left. Returns the count of names
    overridden (for evidence and tests). A missing or unparseable plist leaves
    the derivation name untouched.
    """
    root = Path(root)
    overridden = 0

    def walk(comps: list) -> None:
        nonlocal overridden
        for comp in comps:
            for cf in comp.get("config_files", []):
                if cf.get("type") == "Info.plist":
                    plist_path = root / cf.get("path", "")
                    if plist_path.is_file():
                        info = parse_info_plist(plist_path)
                        name = info.get("name")
                        if name:
                            comp["name"] = name
                            overridden += 1
                    break
            walk(comp.get("children", []))

    walk(components)
    return overridden
