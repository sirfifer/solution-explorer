#!/usr/bin/env python3
"""Publish gate for publication.json (PUBLICATION-METADATA.md design rule 2).

Every deployed viewer is a publication, and publishing carries obligations the
analyzer cannot know: who is publishing, from what snapshot, with what
disclaimers, under what access rules. For a public map of a codebase we do not
own, that sidecar carries the entire legal and ethical framing: the unofficial
and not-affiliated notice, the upstream license, the exact commit. Its absence
is silent, which is the whole problem.

The design says the deploy paths fail loudly when the file is missing or
invalid, and name the boilerplate to copy. This is that gate.

Two modes, because breaking existing installs would be a worse failure than the
one this prevents:

  default    validate the file if present; if absent, warn loudly and pass.
  --require  absent or invalid is a hard failure. Demo-program deploys and any
             publication of a codebase we do not own run with --require.

An INVALID file always fails in both modes. A half-written publication.json is
never better than none, since the viewer would render partial framing.

Stdlib only, deliberately: action.yml installs almost nothing, so a validator
that needs jsonschema would not run where it matters most. Full JSON Schema
validation runs additionally when jsonschema happens to be importable, and the
mode is reported either way.

Exit codes: 0 ok (or absent without --require), 1 invalid, 2 absent with
--require, 3 the schema itself could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "publication" / "publication.schema.json"
TEMPLATES = REPO_ROOT / "docs" / "publication" / "templates"

# Mirrors publication.schema.json. Kept explicit rather than derived so the
# gate still works where jsonschema is unavailable, and cross-checked against
# the schema file by tests so the two cannot drift.
REQUIRED_TOP = [
    "publication_version", "publisher", "subject", "purpose", "update_policy",
    "header", "footer", "disclaimers", "access", "generated_by",
]
REQUIRED_NESTED = {
    "publisher": ["name", "contact"],
    "subject": ["name", "commit", "snapshot_date", "affiliation"],
    "header": ["banner"],
    "footer": ["always"],
    "access": ["visibility"],
    "generated_by": ["tool", "version"],
}
ENUMS = {
    ("purpose",): ["demo", "documentation", "internal", "evaluation", "other"],
    ("update_policy",): ["snapshot", "periodic", "continuous"],
    ("subject", "affiliation"): ["owner", "maintainer", "contributor", "none"],
    ("access", "visibility"): ["public", "private-preview", "internal"],
}
# An unofficial publication must SAY so somewhere a reader sees it. Checked as
# an obligation, not a schema shape: affiliation contributor or none means we
# are publishing someone else's work.
UNOFFICIAL_AFFILIATIONS = {"contributor", "none"}
UNOFFICIAL_MARKERS = ("unofficial", "not affiliated", "not an official")


def _at(doc: dict, path: tuple) -> Any:
    node: Any = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _boilerplate_hint() -> str:
    names = sorted(p.name for p in TEMPLATES.glob("publication.*.json")) if TEMPLATES.is_dir() else []
    listed = ", ".join(names) if names else "publication.default.json, publication.showcase.json"
    return (
        f"Copy a template from docs/publication/templates/ ({listed}) next to the "
        f"deployed architecture data and fill it in. Use publication.showcase.json "
        f"for any codebase you do not own."
    )


def _unfilled_placeholders(node: Any, path: str = "") -> list[str]:
    """Every string still carrying a template EDIT marker, with its key path.

    The shipped templates use "EDIT: ..." to mark what a publisher must fill in.
    Deploying one unfilled is the failure this whole gate exists to prevent, and
    "must be a git SHA" is a confusing way to say "you shipped the template".
    """
    out: list[str] = []
    if isinstance(node, str):
        if node.strip().upper().startswith("EDIT:"):
            out.append(path or "<root>")
    elif isinstance(node, dict):
        for key, value in node.items():
            out.extend(_unfilled_placeholders(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.extend(_unfilled_placeholders(value, f"{path}[{i}]"))
    return out


def validate_doc(doc: Any) -> list[str]:
    """Structural and obligation errors, most specific first. Empty means valid."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["publication.json must contain a JSON object at the top level"]

    unfilled = _unfilled_placeholders(doc)
    if unfilled:
        # Report this alone. Every other error would be a downstream symptom of
        # the same cause, and a wall of them buries the actual problem.
        return [
            "this is still an unfilled template: "
            + ", ".join(sorted(unfilled))
            + " still carry the 'EDIT:' placeholder"
        ]

    for key in REQUIRED_TOP:
        if key not in doc:
            errors.append(f"missing required key: {key}")
    for parent, children in REQUIRED_NESTED.items():
        node = doc.get(parent)
        if node is None:
            continue  # already reported by the top-level pass
        if not isinstance(node, dict):
            errors.append(f"{parent} must be an object")
            continue
        for child in children:
            if child not in node:
                errors.append(f"missing required key: {parent}.{child}")

    for path, allowed in ENUMS.items():
        value = _at(doc, path)
        if value is not None and value not in allowed:
            errors.append(
                f"{'.'.join(path)} must be one of {allowed}, got {value!r}"
            )

    version = doc.get("publication_version")
    if version is not None and version != 1:
        errors.append(f"publication_version must be 1, got {version!r}")

    always = _at(doc, ("footer", "always"))
    if always is not None and (not isinstance(always, list) or not always):
        errors.append("footer.always must be a non-empty array of strings")

    if "disclaimers" in doc and not isinstance(doc["disclaimers"], list):
        errors.append("disclaimers must be an array (it may be empty)")

    # Provenance must be real, not a placeholder. A snapshot with no commit is
    # a publication that cannot be reproduced or checked.
    commit = _at(doc, ("subject", "commit"))
    if isinstance(commit, str) and not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit.strip()):
        errors.append(
            f"subject.commit must be a git SHA (7 to 40 hex characters), got {commit!r}"
        )
    snapshot = _at(doc, ("subject", "snapshot_date"))
    if isinstance(snapshot, str) and not re.match(r"^\d{4}-\d{2}-\d{2}", snapshot.strip()):
        errors.append(
            f"subject.snapshot_date must start with an ISO date (YYYY-MM-DD), got {snapshot!r}"
        )

    # Publishing someone else's codebase carries obligations the schema cannot
    # express. These are the ones that matter (DISCLOSURE-POLICY.md).
    affiliation = _at(doc, ("subject", "affiliation"))
    if affiliation in UNOFFICIAL_AFFILIATIONS:
        haystack = " ".join(
            str(x) for x in [
                _at(doc, ("header", "banner")),
                *(always if isinstance(always, list) else []),
                *(doc.get("disclaimers") or []),
            ]
        ).lower()
        if not any(marker in haystack for marker in UNOFFICIAL_MARKERS):
            errors.append(
                f"subject.affiliation is {affiliation!r}, so the banner, footer or "
                f"disclaimers must say plainly that this is unofficial and not "
                f"affiliated with the project"
            )
        if not _at(doc, ("subject", "license")):
            errors.append(
                f"subject.affiliation is {affiliation!r}, so subject.license is "
                f"required: the upstream license must travel with what we publish"
            )
        if not _at(doc, ("subject", "repo_url")):
            errors.append(
                f"subject.affiliation is {affiliation!r}, so subject.repo_url is "
                f"required so a reader can reach the real project"
            )

    # An unresolved substitution renders as [missing: path] in the viewer, which
    # is loud by design; catching it here is louder and earlier.
    for path in (("header", "banner"),):
        value = _at(doc, path)
        if isinstance(value, str):
            for token in re.findall(r"\{\{([^}]+)\}\}", value):
                if _at(doc, tuple(token.strip().split("."))) is None:
                    errors.append(
                        f"{'.'.join(path)} substitutes {{{{{token.strip()}}}}}, "
                        f"which resolves to nothing"
                    )
    return errors


# The bundle must carry the upstream license TEXT, not just its identifier.
# The viewer renders upstream README, CLAUDE.md and documentation excerpts in
# the detail panel, so a deployed demo redistributes third-party copyrighted
# text and not merely facts about it. MIT, BSD and Apache-2.0 all permit that
# and all require the notice to travel with it.
UPSTREAM_LICENSE_NAMES = ("UPSTREAM-LICENSE.txt", "UPSTREAM-LICENSE", "UPSTREAM-LICENSE.md")


def validate_bundle(bundle_dir: Path, doc: dict) -> list[str]:
    """Obligations on the deployed FILES, not on the document.

    Only the ones that would be wrong to discover after publishing.
    """
    errors: list[str] = []
    affiliation = _at(doc, ("subject", "affiliation"))
    if affiliation in UNOFFICIAL_AFFILIATIONS:
        if not any((bundle_dir / name).exists() for name in UPSTREAM_LICENSE_NAMES):
            errors.append(
                f"subject.affiliation is {affiliation!r}, so the upstream license "
                f"text must ship in the bundle as one of {list(UPSTREAM_LICENSE_NAMES)}. "
                f"The viewer renders upstream README and documentation excerpts, so "
                f"this deployment redistributes third-party text and the notice has "
                f"to travel with it"
            )
    return errors


def _jsonschema_errors(doc: Any) -> Optional[list[str]]:
    """Full schema validation when jsonschema is importable, else None."""
    try:
        import jsonschema  # type: ignore
    except Exception:
        return None
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except OSError:
        return None
    validator = jsonschema.Draft7Validator(schema)
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", help="path to publication.json (or its directory)")
    parser.add_argument(
        "--require", action="store_true",
        help="a missing publication.json is a hard failure (demo-program deploys)",
    )
    args = parser.parse_args(argv)

    target = Path(args.path)
    if target.is_dir():
        target = target / "publication.json"

    if not target.exists():
        if args.require:
            print(f"ERROR: {target} is missing and --require was passed.", file=sys.stderr)
            print(_boilerplate_hint(), file=sys.stderr)
            return 2
        print(
            f"WARNING: no publication.json at {target}. This deployment will "
            f"carry no publisher, no provenance and no disclaimers.",
            file=sys.stderr,
        )
        print(_boilerplate_hint(), file=sys.stderr)
        return 0

    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {target} could not be read as JSON: {exc}", file=sys.stderr)
        print(_boilerplate_hint(), file=sys.stderr)
        return 1

    errors = validate_doc(doc)
    if not errors and args.require:
        # Bundle obligations are checked only where a real bundle is being
        # published; a document validated on its own has no bundle to inspect.
        errors.extend(validate_bundle(target.parent, doc))
    schema_errors = _jsonschema_errors(doc)
    if schema_errors:
        errors.extend(f"schema: {e}" for e in schema_errors)

    if errors:
        print(f"ERROR: {target} is not a valid publication.json:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(_boilerplate_hint(), file=sys.stderr)
        return 1

    mode = "structural + schema" if schema_errors is not None else "structural only (jsonschema not installed)"
    visibility = _at(doc, ("access", "visibility"))
    affiliation = _at(doc, ("subject", "affiliation"))
    print(
        f"publication.json OK ({mode}): "
        f"subject={_at(doc, ('subject', 'name'))!r} "
        f"affiliation={affiliation} visibility={visibility} "
        f"commit={_at(doc, ('subject', 'commit'))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
