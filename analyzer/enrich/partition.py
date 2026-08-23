"""Deterministic DPEA Phase 2 partitioning over the projected architecture tree.

The `/ai-assist` skill (SKILL.md Phase 2) partitions the component tree so
enhancement scales from a handful of components to thousands. This is the
industrialized, deterministic form of that algorithm: no AI, pure functions of
the arch dict plus the relationship list, so a partition plan is byte-stable
across runs (invariant I4) and testable.

The plan groups each top-level subtree that fits a line budget into one
partition (never splitting a parent from its direct children), recurses into
oversized subtrees at the child level, then affinity-merges undersized
partitions into the neighbour partition they share the most relationships with.
Relationships are source-owned: a relationship is assigned to the partition
holding its source component, which is where the enhancing agent has the code to
describe it.

An optional ``include_ids`` filter scopes the plan to a subset of components
(the --update mini-partition path): partitions are built over the full tree for
affinity, then each partition's membership is intersected with the update set
and empty partitions dropped, so update partitions keep the structural grouping
of a full run.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "Partition",
    "PartitionPlan",
    "plan_partitions",
    "flatten_components",
    "relationship_key",
]

# Soft budgets from SKILL.md Phase 2a/2d. Lines are the cheap proxy for source
# token weight the skill uses; the caps are deliberately soft (a single subtree
# that exceeds them but cannot be split further stays whole rather than orphaning
# a child from its parent).
DEFAULT_MAX_LINES = 50_000
DEFAULT_MAX_COMPONENTS = 30
DEFAULT_MIN_COMPONENTS = 5
# Cap on relationships per partition, because every relationship demands a
# full contract block in the RESPONSE: the partitioner bounded input (lines,
# components) but never demanded output, and the first real smoke run
# (2026-08-22) planned a partition carrying src/vs/workbench with 331
# relationships, whose ~78k-token response came back truncated mid-JSON and
# unparseable. Oversized partitions are split into chunks that repeat the
# same components (context and component answers stay intact) with the
# relationship set sliced across them.
DEFAULT_MAX_RELATIONSHIPS = 40


def relationship_key(rel: dict) -> str:
    """The ``enrichment.target_id`` string for a relationship (source|target|type)."""
    return f"{rel.get('source', '')}|{rel.get('target', '')}|{rel.get('type', '')}"


@dataclass(frozen=True)
class Partition:
    """One unit of enhancement work: a set of components and their relationships."""

    id: int
    component_ids: tuple[str, ...]
    relationship_keys: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.component_ids)


@dataclass(frozen=True)
class PartitionPlan:
    """A deterministic partition plan plus the caps it was built under."""

    partitions: tuple[Partition, ...]
    max_lines: int
    max_components: int
    total_components: int

    @property
    def count(self) -> int:
        return len(self.partitions)


def flatten_components(components: Iterable[dict]) -> list[dict]:
    """Depth-first flatten of the arch component tree, parents before children."""
    out: list[dict] = []

    def walk(nodes: Iterable[dict]) -> None:
        for node in nodes:
            out.append(node)
            walk(node.get("children", []))

    walk(components)
    return out


def _subtree_lines(comp: dict) -> int:
    total = int((comp.get("metrics") or {}).get("lines", 0) or 0)
    for child in comp.get("children", []):
        total += _subtree_lines(child)
    return total


def _subtree_ids(comp: dict) -> list[str]:
    ids = [comp["id"]]
    for child in comp.get("children", []):
        ids.extend(_subtree_ids(child))
    return ids


def _split_subtree(
    comp: dict, max_lines: int, max_components: int
) -> list[list[str]]:
    """Return groups of component ids for one subtree, honouring the budget.

    A subtree that fits (by lines and component count) is one group. An oversized
    subtree recurses at the child level; the subtree root is attached to the
    first child group so a parent is never split from all its children (SKILL.md
    Phase 2a rule 3). A leaf that alone exceeds the budget stays whole (soft cap).
    """
    ids = _subtree_ids(comp)
    lines = _subtree_lines(comp)
    if (lines <= max_lines and len(ids) <= max_components) or not comp.get("children"):
        return [ids]

    groups: list[list[str]] = []
    for child in comp.get("children", []):
        groups.extend(_split_subtree(child, max_lines, max_components))
    if groups:
        # Keep the subtree root with its first (deterministic, id-sorted) child
        # group rather than orphaning it into a singleton.
        groups[0] = [comp["id"], *groups[0]]
    else:
        groups = [ids]
    return groups


def _build_affinity(relationships: Iterable[dict]) -> dict[str, dict[str, int]]:
    """Undirected relationship-count affinity between component ids."""
    affinity: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rel in relationships:
        a, b = rel.get("source", ""), rel.get("target", "")
        if a and b and a != b:
            affinity[a][b] += 1
            affinity[b][a] += 1
    return affinity


def plan_partitions(
    components: list[dict],
    relationships: list[dict],
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    max_components: int = DEFAULT_MAX_COMPONENTS,
    min_components: int = DEFAULT_MIN_COMPONENTS,
    max_relationships: int = DEFAULT_MAX_RELATIONSHIPS,
    include_ids: Optional[Iterable[str]] = None,
) -> PartitionPlan:
    """Partition the arch component tree deterministically (DPEA Phase 2).

    ``components`` is the hierarchical arch dict tree (each node may carry
    ``children`` and ``metrics.lines``). ``relationships`` is the flat arch
    relationship list. ``include_ids``, when given, scopes the resulting plan to
    those component ids (the --update mini-partition path).
    """
    # Phase 2a: natural subtree grouping. Sort top-level subtrees by id so the
    # plan is order-independent of the arch dict's component ordering.
    groups: list[list[str]] = []
    for subtree in sorted(components, key=lambda c: c["id"]):
        groups.extend(_split_subtree(subtree, max_lines, max_components))

    # Phase 2b: affinity-merge undersized groups into the group they share the
    # most relationships with, as long as the merge stays within budget.
    affinity = _build_affinity(relationships)
    lines_by_id: dict[str, int] = {}
    for comp in flatten_components(components):
        lines_by_id[comp["id"]] = int((comp.get("metrics") or {}).get("lines", 0) or 0)

    def group_lines(group: list[str]) -> int:
        return sum(lines_by_id.get(cid, 0) for cid in group)

    # Deterministic pass: repeatedly fold the smallest undersized group into its
    # best-affinity in-budget neighbour until none can move.
    merged = True
    while merged and len(groups) > 1:
        merged = False
        # Stable order: by size then first id.
        order = sorted(range(len(groups)), key=lambda i: (len(groups[i]), groups[i][0]))
        for gi in order:
            group = groups[gi]
            if len(group) >= min_components:
                continue
            members = set(group)
            # Best-affinity other group.
            scores: list[tuple[int, str, int]] = []
            for gj, other in enumerate(groups):
                if gj == gi:
                    continue
                score = sum(
                    affinity.get(cid, {}).get(oid, 0)
                    for cid in group
                    for oid in other
                )
                if group_lines(group) + group_lines(other) > max_lines:
                    continue
                if len(members) + len(other) > max_components:
                    continue
                scores.append((score, other[0], gj))
            if not scores:
                continue
            # Highest affinity, then lowest first-id for determinism.
            scores.sort(key=lambda s: (-s[0], s[1]))
            _, _, target = scores[0]
            groups[target] = [*groups[target], *group]
            del groups[gi]
            merged = True
            break

    # Optional --update scoping: intersect each group with the update set.
    if include_ids is not None:
        keep = set(include_ids)
        groups = [[cid for cid in g if cid in keep] for g in groups]
        groups = [g for g in groups if g]

    # Assemble partitions with deterministic ids (sorted by first component id),
    # each carrying its source-owned relationships.
    groups = [sorted(set(g)) for g in groups]
    groups.sort(key=lambda g: g[0] if g else "")
    owner_of: dict[str, int] = {}
    for pid, group in enumerate(groups):
        for cid in group:
            owner_of[cid] = pid

    rel_by_partition: dict[int, list[str]] = defaultdict(list)
    for rel in relationships:
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        owner = owner_of.get(src)
        if owner is None:
            owner = owner_of.get(tgt)
        if owner is not None:
            rel_by_partition[owner].append(relationship_key(rel))

    # Chunk any partition whose relationship set exceeds the response bound.
    # Each chunk repeats the group's components (their facts are the context
    # the relationship contracts need, and absorbing a component twice is a
    # deterministic overwrite), while the sorted relationship list is sliced
    # across chunks. Ids are renumbered sequentially afterwards so they stay
    # dense and deterministic.
    assembled: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for pid, group in enumerate(groups):
        rels = sorted(set(rel_by_partition.get(pid, [])))
        if max_relationships > 0 and len(rels) > max_relationships:
            for start in range(0, len(rels), max_relationships):
                assembled.append(
                    (tuple(group), tuple(rels[start : start + max_relationships]))
                )
        else:
            assembled.append((tuple(group), tuple(rels)))

    partitions = tuple(
        Partition(id=pid, component_ids=comp_ids, relationship_keys=rel_keys)
        for pid, (comp_ids, rel_keys) in enumerate(assembled)
    )

    total = len(set().union(*groups)) if groups else 0
    return PartitionPlan(
        partitions=partitions,
        max_lines=max_lines,
        max_components=max_components,
        total_components=total,
    )
