"""Activity-lens projection (LENS-DESIGN.md L5; P5-4).

Reads the store's git-activity tables (schema v2) and aggregates them to
component granularity via ``component_files`` (populated by ``derive_all``'s
flush, which runs before projection), producing the data the Activity lens
renders in P6-5:

  - **Hotspots**: components ranked by change frequency times size (the gateway
    "where should I look first" view). Per-file hotspot is ``commit_count *
    lines``; the component score sums its member files' hotspots.
  - **Knowledge map**: author contribution shares per component, knowledge
    islands (top author holds >= 95% of commits), and bus factor (the fewest
    authors covering >= 50% of commits).
  - **Change coupling**: file pairs and cross-component pairs that change
    together, above a support floor.

The viewer ignores these keys until P6-5 (backward compatibility). Every read is
sorted, so the projection is byte-deterministic for a given store (invariant I4).
"""

from __future__ import annotations

from typing import Optional

__all__ = ["build_activity", "activity_manifest_summary"]

# Below this many shared commits a file pair is noise, not coupling.
MIN_COCHANGE_SUPPORT = 2
# A component whose top author holds at least this commit share is a knowledge
# island (bus-factor risk); LENS-DESIGN L5.
KNOWLEDGE_ISLAND_SHARE = 0.95
# Bounds on the ranked coupling lists that reach the projection.
MAX_FILE_COUPLING = 100
MAX_COMPONENT_COUPLING = 100
# Top hotspots carried in the lightweight manifest summary.
MANIFEST_TOP_HOTSPOTS = 10


def _provenance(store) -> dict:
    def flag(key: str) -> bool:
        return store.get_meta(key) == "1"

    return {
        "git": flag("activity_git"),
        "shallow": flag("activity_shallow"),
        "head": store.get_meta("activity_head"),
        "commits": int(store.get_meta("activity_commits") or 0),
        "first_commit": store.get_meta("activity_first_commit"),
        "last_commit": store.get_meta("activity_last_commit"),
    }


def _bus_factor(sorted_commits: list[int], total: int) -> int:
    """Fewest top contributors whose cumulative commits reach half the total."""
    if total <= 0:
        return 0
    cum = 0
    for i, c in enumerate(sorted_commits, start=1):
        cum += c
        if cum * 2 >= total:
            return i
    return len(sorted_commits)


def build_activity(store) -> Optional[dict]:
    """Return the full activity projection dict, or ``None`` when absent.

    ``None`` when the store carries no git-activity rows (non-git root, or a
    repo with no commits), so the projection omits the ``activity`` key and old
    viewers degrade to their pre-activity behavior.
    """
    if store is None or not store.has_activity():
        return None

    activity_rows = store.file_activity()
    author_rows = store.file_authors()
    files = store.files()
    comp_files = store.component_files()
    components = {c["id"]: c for c in store.components()}

    lines_by_path = {f["path"]: (f["lines"] or 0) for f in files}
    act_by_path = {r["path"]: r for r in activity_rows}

    # path -> list of owning component ids (a file may join multiple components)
    comps_by_path: dict[str, list[str]] = {}
    for row in comp_files:
        comps_by_path.setdefault(row["path"], []).append(row["component_id"])

    authors_by_path: dict[str, list[dict]] = {}
    for r in author_rows:
        authors_by_path.setdefault(r["path"], []).append(r)

    # ---- per-file detail --------------------------------------------------
    files_detail: dict[str, dict] = {}
    for r in activity_rows:
        path = r["path"]
        total = sum(a["commit_count"] for a in authors_by_path.get(path, []))
        authors = [
            {
                "author_key": a["author_key"],
                "author_name": a["author_name"],
                "commits": a["commit_count"],
                "share": (a["commit_count"] / total) if total else 0.0,
            }
            for a in sorted(
                authors_by_path.get(path, []),
                key=lambda a: (-a["commit_count"], a["author_key"]),
            )
        ]
        owners = sorted(comps_by_path.get(path, []))
        files_detail[path] = {
            "commit_count": r["commit_count"],
            "lines_added": r["lines_added"],
            "lines_removed": r["lines_removed"],
            "churn": r["lines_added"] + r["lines_removed"],
            "lines": lines_by_path.get(path, 0),
            "hotspot_score": r["commit_count"] * lines_by_path.get(path, 0),
            "first_seen": r["first_seen"],
            "last_modified": r["last_modified"],
            "component_ids": owners,
            "authors": authors,
        }

    # ---- component aggregation -------------------------------------------
    # Accumulate per component: churn, hotspot score, author commits, dates.
    agg: dict[str, dict] = {}
    for row in comp_files:
        cid = row["component_id"]
        path = row["path"]
        r = act_by_path.get(path)
        if r is None:
            continue
        a = agg.setdefault(
            cid,
            {
                "commit_count": 0,
                "lines_added": 0,
                "lines_removed": 0,
                "lines": 0,
                "hotspot_score": 0,
                "authors": {},  # author_key -> [name, commits]
                "first_seen": None,
                "last_modified": None,
                "files": 0,
            },
        )
        a["commit_count"] += r["commit_count"]
        a["lines_added"] += r["lines_added"]
        a["lines_removed"] += r["lines_removed"]
        lines = lines_by_path.get(path, 0)
        a["lines"] += lines
        a["hotspot_score"] += r["commit_count"] * lines
        a["files"] += 1
        if r["first_seen"] and (a["first_seen"] is None or r["first_seen"] < a["first_seen"]):
            a["first_seen"] = r["first_seen"]
        if r["last_modified"] and (a["last_modified"] is None or r["last_modified"] > a["last_modified"]):
            a["last_modified"] = r["last_modified"]
        for au in authors_by_path.get(path, []):
            slot = a["authors"].setdefault(au["author_key"], [au["author_name"], 0])
            slot[1] += au["commit_count"]

    comp_list = []
    for cid, a in agg.items():
        total_author_commits = sum(v[1] for v in a["authors"].values())
        authors_sorted = sorted(
            a["authors"].items(), key=lambda kv: (-kv[1][1], kv[0])
        )
        authors = [
            {
                "author_key": k,
                "author_name": v[0],
                "commits": v[1],
                "share": (v[1] / total_author_commits) if total_author_commits else 0.0,
            }
            for k, v in authors_sorted
        ]
        top_share = authors[0]["share"] if authors else 0.0
        bus = _bus_factor([v[1][1] for v in authors_sorted], total_author_commits)
        comp_list.append(
            {
                "id": cid,
                "name": components.get(cid, {}).get("name", cid),
                "files": a["files"],
                "commit_count": a["commit_count"],
                "lines_added": a["lines_added"],
                "lines_removed": a["lines_removed"],
                "churn": a["lines_added"] + a["lines_removed"],
                "lines": a["lines"],
                "hotspot_score": a["hotspot_score"],
                "first_seen": a["first_seen"],
                "last_modified": a["last_modified"],
                "author_count": len(authors),
                "top_author_share": top_share,
                "knowledge_island": bool(authors) and top_share >= KNOWLEDGE_ISLAND_SHARE,
                "bus_factor": bus,
                "authors": authors,
            }
        )
    comp_list.sort(key=lambda c: (-c["hotspot_score"], c["id"]))

    # ---- coupling ---------------------------------------------------------
    pairs = store.cochange_pairs(min_support=MIN_COCHANGE_SUPPORT)
    file_coupling = [
        {"a": p["path_a"], "b": p["path_b"], "cochange_count": p["cochange_count"]}
        for p in sorted(pairs, key=lambda p: (-p["cochange_count"], p["path_a"], p["path_b"]))
    ][:MAX_FILE_COUPLING]

    # Cross-component coupling: sum file-pair counts across component boundaries.
    comp_pair_counts: dict[tuple[str, str], int] = {}
    for p in pairs:
        a_comps = comps_by_path.get(p["path_a"], [])
        b_comps = comps_by_path.get(p["path_b"], [])
        for ca in a_comps:
            for cb in b_comps:
                if ca == cb:
                    continue
                key = (ca, cb) if ca < cb else (cb, ca)
                comp_pair_counts[key] = comp_pair_counts.get(key, 0) + p["cochange_count"]
    component_coupling = [
        {"a": a, "b": b, "cochange_count": n}
        for (a, b), n in sorted(
            comp_pair_counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
        )
        if n >= MIN_COCHANGE_SUPPORT
    ][:MAX_COMPONENT_COUPLING]

    return {
        "provenance": _provenance(store),
        "components": comp_list,
        "component_coupling": component_coupling,
        "file_coupling": file_coupling,
        "files": files_detail,
    }


def activity_manifest_summary(activity: Optional[dict]) -> Optional[dict]:
    """The lightweight slice that rides in the manifest (top hotspots only)."""
    if not activity:
        return None
    hotspots = [
        {
            "id": c["id"],
            "name": c["name"],
            "hotspot_score": c["hotspot_score"],
            "commit_count": c["commit_count"],
            "knowledge_island": c["knowledge_island"],
            "bus_factor": c["bus_factor"],
        }
        for c in activity["components"][:MANIFEST_TOP_HOTSPOTS]
    ]
    return {
        "provenance": activity["provenance"],
        "top_hotspots": hotspots,
        "component_count": len(activity["components"]),
        "coupling_count": len(activity["component_coupling"]),
    }
