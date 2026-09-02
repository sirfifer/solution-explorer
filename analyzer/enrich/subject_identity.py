"""Authoritative identity for the repository representation being enriched.

The analyzer normally maps the repository it was pointed at.  A clone or
worktree is only the acquisition mechanism; it does not make the subject a
fork, downstream build, or special edition.  Model-written orientation,
narrative, and final determination all consume this same deterministic record
so they cannot silently invent a different subject.

An integrator may explicitly declare a variant by adding a
``subject_representation`` object to the derived architecture.  That is a
deliberately narrow seam for a future launch form/API; inference from package
names, branches, or code differences never activates it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..project.gitinfo import read_git_info

CANONICAL_MODE = "canonical_repository_snapshot"
DECLARED_VARIANT_MODE = "declared_variant_snapshot"
SUBJECT_IDENTITY_CONTRACT_VERSION = 1

_VARIANT_KINDS = frozenset({
    "fork", "branch", "unreleased", "customer_variant", "private_variant", "custom",
})

# Narrowly target claims about the subject as a whole.  A narrative may still
# accurately say that a child process forks or that the repository contains a
# vendored fork; those are architecture facts, not subject-identity claims.
_UNSUPPORTED_CANONICAL_PATTERNS = (
    re.compile(
        r"\b(?:this|the)\s+(?:repository|repo|codebase|project|system)\s+"
        r"(?:is|appears\s+to\s+be|looks\s+like)\s+(?:an?\s+)?fork\b",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*this\s+is\s+(?:an?\s+)?fork\b", re.IGNORECASE),
    re.compile(r"\bdistinguished\s+from\s+upstream\b", re.IGNORECASE),
    re.compile(
        r"\b(?:the\s+)?(?:repository|repo|codebase|project|system)\s+is\s+"
        r"(?:an?\s+)?(?:downstream|modified)\s+(?:fork|version|variant)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:downstream|local)\s+fork\s+of\b", re.IGNORECASE),
)


def build_subject_identity(
    arch: dict,
    *,
    root: Optional[Path] = None,
    commit_sha: Optional[str] = None,
) -> dict:
    """Build the one identity record every model-authored phase must obey.

    Canonical snapshot is the fail-closed default.  A variant is recognized
    only when an explicit declaration names both a supported kind and a useful
    description.  Merely running from a non-default branch or seeing a package
    name such as ``code-oss-dev`` never changes the mode.
    """
    repository = arch.get("repository")
    default_branch = arch.get("default_branch") or "main"
    if root is not None:
        try:
            git_repository, git_branch = read_git_info(Path(root))
        except OSError:
            git_repository, git_branch = None, ""
        repository = repository or git_repository
        default_branch = arch.get("default_branch") or git_branch or "main"

    declaration = arch.get("subject_representation")
    if isinstance(declaration, dict):
        declared_kind = str(declaration.get("kind") or "").strip().lower()
        declared_description = str(declaration.get("description") or "").strip()
        if (
            declaration.get("explicit") is True
            and declared_kind in _VARIANT_KINDS
            and declared_description
        ):
            return {
                "mode": DECLARED_VARIANT_MODE,
                "name": arch.get("name"),
                "repository": repository,
                "default_branch": default_branch,
                "commit_sha": commit_sha,
                "variant_kind": declared_kind,
                "variant_description": declared_description,
                "authority": "explicit_operator_declaration",
            }

    return {
        "mode": CANONICAL_MODE,
        "name": arch.get("name"),
        "repository": repository,
        "default_branch": default_branch,
        "commit_sha": commit_sha,
        "authority": "deterministic_repository_provenance",
        "meaning": (
            "This product is a representation of the analyzed repository itself "
            "at the stated commit. A clone or worktree is only how the source was "
            "acquired; it is not evidence of a fork, downstream version, or special "
            "edition. Package and product names inside the repository are not "
            "repository identities."
        ),
    }


def subject_identity_errors(payload: dict, identity: dict) -> list[str]:
    """Reject unsupported whole-subject identity claims in publishable prose."""
    if identity.get("mode") != CANONICAL_MODE:
        return []
    errors: list[str] = []
    for field in ("summary", "data_flow_narrative"):
        value = str(payload.get(field) or "")
        for pattern in _UNSUPPORTED_CANONICAL_PATTERNS:
            match = pattern.search(value)
            if match:
                errors.append(
                    f"Root ai_enhance.{field}: unsupported subject-identity claim "
                    f"{match.group(0)!r}; the subject is the canonical repository "
                    "snapshot unless an explicit variant declaration says otherwise"
                )
                break
    return errors


def subject_identity_prompt(identity: dict) -> str:
    """Render the stable instructions shared by orientation and review prompts."""
    if identity.get("mode") == DECLARED_VARIANT_MODE:
        return (
            "An operator explicitly declared this analyzed snapshot as a variant. "
            "Use exactly the declared kind and description below; do not infer any "
            "additional upstream/downstream relationship.\n"
            + _compact_identity(identity)
        )
    return (
        "This map represents the repository itself at the analyzed commit. The "
        "local clone/worktree is only the acquisition mechanism. Never describe "
        "the subject as a fork, downstream build, modified upstream version, or "
        "special edition unless an explicit variant declaration is present. Do "
        "not mistake an internal package/product name for repository identity.\n"
        + _compact_identity(identity)
    )


def _compact_identity(identity: dict) -> str:
    fields = [
        f"mode={identity.get('mode')}",
        f"name={identity.get('name') or '(unknown)'}",
        f"repository={identity.get('repository') or '(local source tree; no remote derived)'}",
        f"default_branch={identity.get('default_branch') or '(unknown)'}",
        f"commit_sha={identity.get('commit_sha') or '(not available)'}",
    ]
    if identity.get("mode") == DECLARED_VARIANT_MODE:
        fields.extend([
            f"variant_kind={identity.get('variant_kind')}",
            f"variant_description={identity.get('variant_description')}",
        ])
    return "SUBJECT IDENTITY: " + "; ".join(fields)


__all__ = [
    "CANONICAL_MODE",
    "DECLARED_VARIANT_MODE",
    "SUBJECT_IDENTITY_CONTRACT_VERSION",
    "build_subject_identity",
    "subject_identity_errors",
    "subject_identity_prompt",
]
