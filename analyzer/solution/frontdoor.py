"""Solution-level AI front door (M1).

A composed solution is a static tree whose root ``manifest.json`` is a member
INDEX, not a component graph. An agent pointed at the solution root needs to be
told that up front, and taught to DESCEND into ``members/<slug>/`` where each
member carries its own single-repo front door (``ai.json`` / ``llms.txt``, the
one ``analyzer/project/frontdoor.py`` emits). This module writes that small
solution front door.

It deliberately reuses the same two file names and the same token-economy framing
as the per-member front door, so an agent sees one consistent contract at every
level. Determinism (invariant I4): ai.json is written ``sort_keys=True`` and
llms.txt in a fixed line order, both derived from the manifest which is itself
byte-stable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..project.frontdoor import (
    AI_JSON_NAME,
    FRONT_DOOR_VERSION,
    LLMS_TXT_NAME,
)

__all__ = ["build_solution_front_door", "write_solution_front_door"]


def build_solution_front_door(manifest: dict) -> tuple[dict, str]:
    """Build the ``(ai_json_dict, llms_txt_str)`` pair for a solution root."""
    members = manifest.get("members", [])
    member_entries: list[dict] = []
    for m in members:
        entry = {
            "slug": m.get("slug"),
            "label": m.get("label"),
            "resolved": m.get("resolved", False),
        }
        if m.get("resolved") and m.get("projection"):
            entry["projection"] = m["projection"]
            entry["front_door"] = f"{m['projection']}ai.json"
            entry["entry"] = f"{m['projection']}manifest.json"
            cov = m.get("coverage") or {}
            entry["source_percent"] = cov.get("source_percent")
            entry["has_gaps"] = cov.get("has_gaps", False)
        else:
            entry["unresolved_reason"] = m.get("unresolved_reason") or m.get("error")
        member_entries.append(entry)

    ai_json = {
        "front_door_version": FRONT_DOOR_VERSION,
        "kind": "solution-explorer-solution-front-door",
        "mode": "solution",
        "solution": {
            "name": manifest.get("name", ""),
            "generated_at": manifest.get("generated_at", ""),
            "analyzer_version": manifest.get("analyzer_version", ""),
        },
        "entry": "manifest.json",
        "projection_root": "./",
        "members": member_entries,
        "summary": manifest.get("summary", {}),
        "endpoints": [
            {
                "path": "manifest.json",
                "role": "solution-entry",
                "contains": (
                    "The solution member index: solution name, the ordered `members` "
                    "list (each with slug, label, resolved flag, stats, and a "
                    "per-member coverage summary), and a `summary` roll-up. Coverage "
                    "is per member and never blended: read each member's own numbers."
                ),
            },
            {
                "path": "members/<slug>/",
                "role": "member-projection",
                "contains": (
                    "A complete standalone single-repo projection for one member: "
                    "its own manifest.json, ai.json, llms.txt, detail/search shards, "
                    "coverage.json and activity.json. Descend here and follow that "
                    "member's ai.json exactly as if it were a standalone dataset."
                ),
            },
        ],
        "walk_orders": [
            {
                "question": "solution overview",
                "steps": [
                    {
                        "fetch": "manifest.json",
                        "then": (
                            "Read `name`, `summary` (member counts, summed files, "
                            "members_with_gaps), and the `members` index for per-member "
                            "stats and coverage. This is one fetch."
                        ),
                    }
                ],
            },
            {
                "question": "explore one member in depth",
                "steps": [
                    {
                        "fetch": "manifest.json",
                        "then": "Pick the member by slug and read its `projection` path.",
                    },
                    {
                        "fetch": "members/<slug>/ai.json",
                        "then": (
                            "Follow that member's own front door and walk orders; the "
                            "member projection is a full standalone dataset."
                        ),
                    },
                ],
            },
        ],
        "token_economy": {
            "principle": (
                "One fetch of the solution manifest answers 'what repos, how big, "
                "which have gaps'. Only descend into a member's shards for questions "
                "about that member's code. Coverage stays per member: never blend a "
                "denominator across repos."
            ),
        },
    }
    llms_txt = _render_solution_llms_txt(ai_json)
    return ai_json, llms_txt


def _render_solution_llms_txt(ai_json: dict) -> str:
    solution = ai_json["solution"]
    name = solution.get("name") or "this solution"
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name).strip() or "this solution"
    lines: list[str] = []
    lines.append(f"# {name} (solution-explorer multi-repo solution)")
    lines.append("")
    lines.append(
        "> Machine-readable index of a multi-repo solution. The root manifest.json "
        "lists member repositories; each member under members/<slug>/ is a complete "
        "standalone architecture projection with its own ai.json. Coverage is "
        "reported per member and is never blended across repos."
    )
    lines.append("")
    meta = []
    if solution.get("generated_at"):
        meta.append(f"generated_at: {solution['generated_at']}")
    if solution.get("analyzer_version"):
        meta.append(f"analyzer_version: {solution['analyzer_version']}")
    meta.append(f"front_door_version: {ai_json['front_door_version']}")
    meta.append("mode: solution")
    lines.append(f"_{'; '.join(meta)}_")
    lines.append("")
    lines.append("## Start here")
    lines.append("")
    lines.append("- [ai.json](./ai.json): endpoint map, member index, walk orders, token-economy contract (read this first).")
    lines.append("- [manifest.json](./manifest.json): the member index with per-member stats and coverage.")
    lines.append("")
    lines.append("## Members")
    lines.append("")
    for m in ai_json["members"]:
        slug = m.get("slug")
        label = m.get("label") or slug
        if m.get("resolved") and m.get("projection"):
            pct = m.get("source_percent")
            gap = " (has source gaps)" if m.get("has_gaps") else ""
            pct_str = f": {pct}% of source analyzed{gap}" if pct is not None else ""
            lines.append(f"- [{label}](./{m['projection']}ai.json){pct_str}")
        else:
            lines.append(f"- {label}: not analyzed in M1 ({m.get('unresolved_reason', 'unresolved')})")
    lines.append("")
    lines.append("## Token economy")
    lines.append("")
    lines.append(ai_json["token_economy"]["principle"])
    lines.append("")
    return "\n".join(lines)


def write_solution_front_door(
    manifest: dict, output_dir, *, indent=2
) -> tuple[Path, Path]:
    """Emit ``ai.json`` and ``llms.txt`` into the solution root. Return their paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ai_json, llms_txt = build_solution_front_door(manifest)

    ai_path = output_dir / AI_JSON_NAME
    with open(ai_path, "w", encoding="utf-8") as fh:
        json.dump(ai_json, fh, indent=indent, default=str, sort_keys=True)

    llms_path = output_dir / LLMS_TXT_NAME
    with open(llms_path, "w", encoding="utf-8") as fh:
        fh.write(llms_txt)
        if not llms_txt.endswith("\n"):
            fh.write("\n")
    return ai_path, llms_path
