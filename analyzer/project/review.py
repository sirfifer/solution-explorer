"""Apply explicit human review corrections to a derived projection.

This is deliberately narrow. It does not alter the canonical fact store or
silently rewrite analyzer output. Every edit is an exact expected-value swap,
bound to a repository and enrichment commit, and the manifest records which
review file was applied. A stale correction fails loudly instead of drifting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "syscorpus.review-corrections/v1"


def _components(tree):
    for component in tree or []:
        yield component
        yield from _components(component.get("children") or [])


def _apply_exact_edit(target: dict, edit: dict, target_label: str) -> str:
    field_path = edit.get("field_path") or edit.get("field")
    keys = field_path.split(".") if isinstance(field_path, str) else list(field_path or [])
    if not keys:
        raise ValueError(f"review correction has no field at {target_label}")
    parent = target
    for key in keys[:-1]:
        value = parent.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"review correction field path missing at {target_label}.{'.'.join(keys)}")
        parent = value
    field = keys[-1]
    current = parent.get(field)
    if "expected" in edit:
        if current != edit.get("expected"):
            raise ValueError(
                f"review correction stale at {target_label}.{'.'.join(keys)}: "
                f"expected {edit.get('expected')!r}, found {current!r}"
            )
    elif edit.get("expected_sha256"):
        actual_hash = hashlib.sha256(str(current).encode("utf-8")).hexdigest()
        if actual_hash != edit["expected_sha256"]:
            raise ValueError(
                f"review correction stale at {target_label}.{'.'.join(keys)}: "
                f"expected sha256 {edit['expected_sha256']!r}, found {actual_hash!r}"
            )
    else:
        raise ValueError(f"review correction lacks an exact expectation at {target_label}")
    parent[field] = edit.get("replacement")
    return f"{target_label}.{'.'.join(keys)}"


def apply_review_corrections(projection, corrections) -> dict:
    projection = Path(projection)
    corrections_path = Path(corrections)
    manifest_path = projection / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec = json.loads(corrections_path.read_text(encoding="utf-8"))

    if spec.get("schema") != SCHEMA:
        raise ValueError(f"unsupported review correction schema: {spec.get('schema')!r}")
    subject = spec.get("subject") or {}
    if manifest.get("repository") != subject.get("repository"):
        raise ValueError("review correction repository does not match projection")

    expected_commit = subject.get("commit")
    tours = {tour.get("id"): tour for tour in manifest.get("tours") or []}
    tour_commits = {
        (tour.get("provenance") or {}).get("derived_from_commit")
        for tour in tours.values()
        if (tour.get("provenance") or {}).get("derived_from_commit")
    }
    if expected_commit and tour_commits != {expected_commit}:
        raise ValueError(
            f"review correction commit {expected_commit!r} does not match tour provenance {sorted(tour_commits)!r}"
        )

    applied: list[str] = []
    for edit in spec.get("manifest_edits") or []:
        applied.append(_apply_exact_edit(manifest, edit, "manifest"))

    for edit in spec.get("tour_edits") or []:
        tour_id = edit.get("tour_id")
        tour = tours.get(tour_id)
        if tour is None:
            raise ValueError(f"review correction tour not found: {tour_id!r}")
        step_title = edit.get("step_title")
        target = tour
        target_label = f"tour:{tour_id}"
        if step_title is not None:
            matches = [step for step in tour.get("steps") or [] if step.get("title") == step_title]
            if len(matches) != 1:
                raise ValueError(
                    f"review correction expected one step {step_title!r} in {tour_id!r}, found {len(matches)}"
                )
            target = matches[0]
            target_label += f"/step:{step_title}"
        applied.append(_apply_exact_edit(target, edit, target_label))

    components = {
        component.get("id"): component
        for component in _components(manifest.get("components") or [])
        if component.get("id")
    }
    for edit in spec.get("component_edits") or []:
        component_id = edit.get("component_id")
        component = components.get(component_id)
        if component is None:
            raise ValueError(f"review correction component not found: {component_id!r}")
        applied.append(_apply_exact_edit(component, edit, f"component:{component_id}"))

    manifest["review_corrections"] = {
        "schema": SCHEMA,
        "source": str(corrections_path),
        "repository": subject.get("repository"),
        "commit": expected_commit,
        "applied": applied,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest["review_corrections"]
