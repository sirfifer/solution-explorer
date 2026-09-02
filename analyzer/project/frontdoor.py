"""AI front door for deployed projections (P8-3).

A deployed solution-explorer site is a static tree of JSON shards. An agent
pointed at that URL should consume the enumeration efficiently (owner ambition:
a tenth to a hundredth of the tokens of reading the raw repo) without
reverse-engineering the shard layout by trial and error. This module emits the
entry documents that teach it the layout:

  - ``ai.json``: a versioned, machine-readable map of the dataset identity, the
    endpoint layout with exact relative paths and what each file contains, the
    sharding schemes (how detail and search shards are named and picked), the
    recommended walk order for common question shapes, and the token-economy
    contract (fetch shards, never crawl the tree).
  - ``llms.txt``: the llms.txt-convention markdown companion, short, linking to
    ``ai.json`` and the key endpoints with one-line descriptions.

Both are emitted by the projection tier into the projection root (beside
``manifest.json`` in split mode, beside the single ``architecture.json`` in
monolith mode). The viewer build also ships dataset-independent static pointer
files at the SITE ROOT (viewer/public/ai.json, viewer/public/llms.txt) that send
an agent to ``./architecture/`` where the real projection lands on a deploy.

Determinism (invariant I4): given the same arch dict and the same injected
identity fields, the byte output is identical across runs and across
PYTHONHASHSEED. Both files are written with ``sort_keys=True`` (ai.json) and a
fixed line order (llms.txt), and every list built here is derived from sorted or
insertion-stable inputs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

__all__ = [
    "FRONT_DOOR_VERSION",
    "build_front_door",
    "write_front_door",
    "refresh_front_door",
    "AI_JSON_NAME",
    "LLMS_TXT_NAME",
]

FRONT_DOOR_VERSION = 1
AI_JSON_NAME = "ai.json"
LLMS_TXT_NAME = "llms.txt"

# The optional top-level manifest sections, in a fixed presentation order, each
# with the JSON pointer (relative to manifest.json) and a one-line description.
# Presence is computed per dataset so an agent knows both where a section lives
# and whether this dataset populated it.
_MANIFEST_SECTIONS: tuple[tuple[str, str], ...] = (
    ("components", "Component tree (nested via `children`); each node carries id, name, path, type, files, relationships refs, and optional `ai_enhance`."),
    ("relationships", "Flat list of edges between components (source, target, type; optional `evidence`, `confidence`, `origin`, `ai_enhance`)."),
    ("stats", "Roll-up counts: total_components (distinct component tree nodes; matches the tree and the search index), total_path_components (path-level components only, excluding derived UI-flow nodes), total_files, total_lines, total_symbols, total_relationships, languages."),
    ("coverage", "Manifest-embedded coverage summary (counts per disposition + total + parsed). Full ledger with per-file rows and non-source inventory is in coverage.json."),
    ("activity", "Manifest-embedded activity summary (hotspots/knowledge headline). Full activity lens is in activity.json."),
    ("findings", "Ranked flat list of findings (rule violations, duplication, intent conformance, AI-verified issues). Each finding carries kind, summary, detail, rank_score, confidence, and verification_status; filter on those."),
    ("concerns", "Flat list of concerns (named cross-cutting groupings of findings)."),
    ("capabilities", "Flat index of detected capabilities (web/CLI frameworks and features)."),
    ("data_entities", "Flat index of data entities (models, schemas, tables)."),
    ("entity_access", "Flat index of which components read/write which data entities."),
    ("rules", "Flat index of project rules and their pass/violation state."),
    ("supply_chain", "Software bill of materials summary: ecosystems, dependencies (name, version, pin_status, direct/transitive, evidence), language target/SDK versions, and warnings. The full CycloneDX 1.5 document is sbom.json."),
    # Term-first, per the machine-front-door inversion in the research document
    # Part 3: an agent wants the canonical key it can map to the literature, and
    # the plain sentence rides along as the description. The human surfaces
    # invert this and lead with the sentence.
    ("design_signals", "Architecture quality signals, deterministic (no AI). Per-component metrics ride on each component's `design`: fan_in (afferent coupling Ca), fan_out (efferent coupling Ce), instability (I = Ce/(Ca+Ce)), abstractness (A), distance_main_sequence (D = |A+I-1|), blast_radius (transitive dependents), and quintile `bands`. The ratios are NULLABLE and null means not measurable, never zero: abstractness is only computed where the language distinguishes an interface from a class. Architecture level carries `findings` (kinds: cycle, zone_of_pain, zone_of_uselessness, stability_inversion, change_coupling, boundary_strength; each with `term`, plain-language `lead`, `method` naming the epistemic class, `targets`, `edges`, `evidence`, and `rank_within_kind`), `boundaries` (per-pair boundary strength: source, deployment, process, service), `finding_counts`, and `method_caveat`. Findings rank WITHIN a kind only. There is deliberately no overall architecture score and no ranking of one kind against another. Present only when the analyzer ran with --design-signals."),
    ("orientation", "Bounded human orientation: subject identity, deterministic system portrait groups, question routes, trust rollups, and stable launch targets."),
    ("support", "Support and Operations view: required configuration, external reliance, entry points, data handled, and mechanically ranked attention. The score is not incident probability."),
    ("security", "Repository-observable security mechanisms, credential configuration references, communication boundaries, sensitive-data leads, findings, and explicit unknowns. Not an audit or verdict."),
    ("tours", "Guided walkthroughs (ordered component sequences) when present."),
    ("ai_enhance", "Architecture-level AI overlay (description, help text, provenance markers) when the dataset is enriched."),
    ("changelog", "Ordered projection changelog entries (what changed since the previous projection)."),
    ("component_detail_index", "Map of component id -> {symbolCount, fileCount}; sizes the per-component detail shards before you fetch them."),
)


def _provenance(arch: dict) -> Optional[dict]:
    """Extract the small, safe provenance slice from an enriched arch, or None.

    The architecture-level ``ai_enhance`` overlay carries the enrichment payload
    plus, when the enrichment is stale, a ``derived_from_commit`` anchor. We
    surface only identity/provenance-shaped fields, never the free-text payload,
    so the front door stays small and stable.
    """
    ai = arch.get("ai_enhance")
    if not isinstance(ai, dict):
        return None
    prov: dict = {"enriched": True}
    if "derived_from_commit" in ai:
        prov["derived_from_commit"] = ai["derived_from_commit"]
    if "stale" in ai:
        prov["stale"] = ai["stale"]
    return prov


def _dataset_identity(arch: dict) -> dict:
    identity = {
        "name": arch.get("name", ""),
        "generated_at": arch.get("generated_at", ""),
        "analyzer_version": arch.get("analyzer_version", ""),
    }
    repository = arch.get("repository")
    if repository:
        identity["repository"] = repository
    default_branch = arch.get("default_branch")
    if default_branch:
        identity["default_branch"] = default_branch
    provenance = _provenance(arch)
    if provenance is not None:
        identity["provenance"] = provenance
    # Maturity-gate provenance (card R3): present only on a non-default-channel
    # run that activated a non-stable gate, so a default projection is
    # byte-identical here. Surfaced so an AI consumer of a non-default dataset
    # sees which experimental/beta gates shaped it.
    gate_provenance = arch.get("gate_provenance")
    if gate_provenance:
        identity["gate_provenance"] = gate_provenance
    # An agent needs to know up front whether prose exists: an unenriched
    # dataset has empty descriptions and no help text, and "what does each
    # component do" degrades to structure-only answers (battery finding).
    identity["enriched"] = bool(arch.get("ai_enhance")) or any(
        c.get("ai_enhance") for c in arch.get("components", []) or []
    )
    return identity


def _section_present(
    key: str,
    arch: dict,
    *,
    mode: str,
    coverage: Optional[dict],
    activity: Optional[dict],
) -> bool:
    """Whether a section actually lands in the emitted entry document.

    ``coverage``, ``activity``, and ``component_detail_index`` are injected by
    the manifest/monolith writers, not carried on the arch dict, so they are
    resolved from the projection inputs rather than ``arch.get``:

      - coverage/activity ride in both entry documents whenever the store had
        the corresponding rows (the writers add a summary in split mode and the
        full block in monolith mode);
      - component_detail_index exists only in split mode (there are no detail
        shards in a monolith).
    """
    if key == "coverage":
        return coverage is not None
    if key == "activity":
        return activity is not None
    if key == "component_detail_index":
        return mode == "split"
    value = arch.get(key)
    return value is not None and value != [] and value != {}


def _manifest_sections(
    arch: dict,
    *,
    mode: str,
    coverage: Optional[dict],
    activity: Optional[dict],
) -> list[dict]:
    sections: list[dict] = []
    for key, contains in _MANIFEST_SECTIONS:
        sections.append({
            "key": key,
            "pointer": f".{key}",
            "present": _section_present(
                key, arch, mode=mode, coverage=coverage, activity=activity
            ),
            "contains": contains,
        })
    return sections


def _sbom_endpoint() -> dict:
    """The sbom.json endpoint, listed in both modes when a SBOM was emitted."""
    return {
        "path": "sbom.json",
        "role": "sbom",
        "contains": (
            "CycloneDX 1.5 SBOM: bomFormat, specVersion, a content-derived "
            "serialNumber, the metadata component (the repo, with language "
            "target/SDK versions as properties), and one component per dependency "
            "(name, version, purl, pin status, direct/transitive, evidence). For "
            "a quick 'what does this depend on', read manifest.json .supply_chain "
            "instead; fetch this for the standard interchange document."
        ),
    }


def _cra_endpoint() -> dict:
    """The cra-readiness.json endpoint, listed in both modes when emitted (P10-4)."""
    return {
        "path": "cra-readiness.json",
        "role": "cra-readiness",
        "contains": (
            "Repo-observable EU Cyber Resilience Act readiness checklist: a "
            "versioned, byte-stable list of presence/absence items (SECURITY.md, "
            "vulnerability disclosure contact, SBOM, update config, support "
            "statement, signed-commit sample), each with an evidence pointer or an "
            "explicit gap and a short CRA-clause reference, plus a top-level "
            "`scope` string. NOT a conformity assessment; absent items also appear "
            "as cra_readiness findings in the manifest."
        ),
    }


def _human_view_endpoints(arch: dict) -> list[dict]:
    definitions = (
        ("orientation", "orientation.json", "human-orientation", "Identity, bounded system portrait, question routes, trust rollups, and stable Workbench launch targets."),
        ("support", "support.json", "support-operations", "Observed configuration, external reliance, entry points, data handled, and attention ordering; not incident probability."),
        ("security", "security.json", "security-observations", "Repository-observable mechanisms, boundaries, leads, and explicit unknowns; not an audit or safety verdict."),
    )
    return [
        {"path": path, "role": role, "contains": contains}
        for key, path, role, contains in definitions
        if arch.get(key) is not None
    ]


def _split_endpoints(
    arch: dict,
    *,
    coverage: Optional[dict],
    activity: Optional[dict],
    search_present: bool = True,
    supply_chain: Optional[dict] = None,
    cra_present: bool = False,
) -> list[dict]:
    """The endpoint map for split mode, listing only files that are emitted."""
    endpoints: list[dict] = [
        {
            "path": "manifest.json",
            "role": "entry",
            "contains": (
                "The structural entry document: components (nested), relationships, "
                "stats, and every optional section listed under `manifest_sections`. "
                "Fetch this first for any structural question. Excludes the heavy "
                "per-symbol/per-file arrays (those live in the detail shards)."
            ),
        },

        {
            "path": "data/detail-<safe_id>.json",
            "role": "detail-shard",
            "contains": (
                "Per-component depth: {symbols: [...], files: [...]}. Fetch only for "
                "the component you are drilling into. See `detail_shards.filename_rule`."
            ),
        },
    ]
    if search_present:
        endpoints.insert(1, {
            "path": "search/search-<NNNN>.json",
            "role": "search-shard",
            "contains": (
                "A shard of search entries {ref_kind, ref_id, name, path, component, "
                "text}. Use to resolve a symbol/file/component name or a path to its "
                "owning component. See `search.how_to_pick_a_shard`."
            ),
        })
        endpoints.insert(1, {
            "path": "search/manifest.json",
            "role": "search-index",
            "contains": (
                "Search-shard index: shard_size, total entry count, per-kind counts "
                "(by_kind), the entry field list, and the ordered list of shard "
                "filenames. Fetch this to size a lookup before pulling shards."
            ),
        })
    if coverage is not None:
        endpoints.append({
            "path": "coverage.json",
            "role": "coverage",
            "contains": (
                "Full coverage ledger: summary (counts per disposition), total, "
                "parsed, every per-file row with its disposition "
                "(parsed | excluded:<rule> | failed | binary), and the non-source "
                "inventory. Fetch to answer 'what was and was not analyzed'."
            ),
        })
    if activity is not None:
        endpoints.append({
            "path": "activity.json",
            "role": "activity",
            "contains": (
                "Full activity lens from git history: hotspots (most-changed files), "
                "knowledge (authorship concentration), and coupling (co-change). "
                "Fetch to answer 'what changes most / who owns what'."
            ),
        })
    if supply_chain is not None:
        endpoints.append(_sbom_endpoint())
    if cra_present:
        endpoints.append(_cra_endpoint())
    endpoints.extend(_human_view_endpoints(arch))
    return endpoints


def _monolith_endpoints(
    single_file: str,
    arch: dict,
    supply_chain: Optional[dict] = None,
    cra_present: bool = False,
) -> list[dict]:
    endpoints = [
        {
            "path": single_file,
            "role": "monolith",
            "contains": (
                "The whole dataset in one file: components (nested), relationships, "
                "stats, the inline `symbols` and `files` arrays, embedded `coverage` "
                "(full ledger) and `activity` when present, and every optional "
                "section under `manifest_sections` (including `supply_chain`). "
                "Small-repo / backward-compat layout: there are no separate search "
                "or detail shards, so read the sections you need directly from this "
                "document."
            ),
        }
    ]
    # sbom.json is a separate CycloneDX file beside the monolith even here.
    if supply_chain is not None:
        endpoints.append(_sbom_endpoint())
    if cra_present:
        endpoints.append(_cra_endpoint())
    endpoints.extend(_human_view_endpoints(arch))
    return endpoints


def _supply_chain_walk_order(mode: str, monolith_filename: str) -> dict:
    """The 'what does this depend on' walk order (P10-1)."""
    if mode == "monolith":
        return {
            "question": "what does this depend on",
            "steps": [
                {"fetch": monolith_filename, "then": "Read .supply_chain: .ecosystems for the per-ecosystem counts, .targets for the language target/SDK versions, and .dependencies (each with name, version, pin_status, scope direct/transitive, and evidence). Fetch sbom.json for the CycloneDX interchange document."},
            ],
        }
    return {
        "question": "what does this depend on",
        "steps": [
            {"fetch": "manifest.json", "then": "Read .supply_chain: .ecosystems for the per-ecosystem counts, .targets for the language target/SDK versions, and .dependencies (name, version, pin_status, scope, evidence). One fetch answers most dependency questions."},
            {"fetch": "sbom.json", "then": "Only if you need the standard CycloneDX 1.5 document (components with purls) for interchange with other SBOM tooling."},
        ],
    }


def _design_signals_walk_order(mode: str, monolith_filename: str) -> dict:
    """The 'where is this architecture weak' walk order (D6).

    Term-first, because the reader is an agent: the canonical names lead so they
    can be mapped to the literature and acted on, with the plain-language
    consequence carried as the description of each. The viewer inverts this.

    The last step is the one that matters most for an agent fleet. Blast radius
    is the coordination primitive: it decides what can be edited in parallel and
    what has to queue.
    """
    entry = monolith_filename if mode == "monolith" else "manifest.json"
    return {
        "question": "where is this architecture weak, and what can I change safely",
        "steps": [
            {"fetch": entry, "then": "Read .design_signals.method_caveat FIRST and carry it into anything you report: these are static edges only, so reflection, dependency injection wiring, and dynamic dispatch are invisible. Then .design_signals.finding_counts for the shape of the problem."},
            {"fetch": entry, "then": "Read .design_signals.findings. Each carries `term` (the canonical name: Dependency cycle, Zone of pain, Stability inversion, Cross-boundary change coupling, Zone of uselessness, Boundary strength), `lead` (the same fact in plain language, for reporting to a human), `method` (static-graph, git-history, or static-graph+git-history: which evidence class the claim rests on), `targets` (component ids), `edges` ([source, target] pairs), and `rank_within_kind`. Rank compares a finding ONLY against its own kind; there is no ranking of one kind against another and no overall score, so do not synthesize one."},
            {"fetch": entry, "then": "Before editing a component, read its `design.blast_radius`: that many components transitively depend on it and could break. Use it to plan parallel work along real boundaries. Check `.design_signals.findings` for a cycle whose `targets` contain the component: inside a cycle, the members can only be changed as a unit. Read `.design_signals.boundaries` for how strongly a pair is separated (source means convention only, service means a network contract)."},
        ],
    }


def _cra_walk_order() -> dict:
    """The 'is this repo CRA-ready' walk order (P10-4). Same path in both modes."""
    return {
        "question": "is this repo CRA-ready",
        "steps": [
            {"fetch": "cra-readiness.json", "then": "Read .scope first (this is repo-observable readiness only, not a conformity assessment), then .items: each has id, label, status (present/absent/not_applicable), evidence (path plus matched detail, or null), and cra_clause. Absent items are the gaps; present items name the artifact that satisfies them."},
        ],
    }


def _walk_orders(
    mode: str,
    monolith_filename: str = "architecture.json",
    supply_chain: Optional[dict] = None,
    cra_present: bool = False,
    design_signals: bool = False,
) -> list[dict]:
    """Recommended fetch sequences for common question shapes."""
    orders = _base_walk_orders(mode, monolith_filename)
    if supply_chain is not None:
        orders.append(_supply_chain_walk_order(mode, monolith_filename))
    if cra_present:
        orders.append(_cra_walk_order())
    if design_signals:
        orders.append(_design_signals_walk_order(mode, monolith_filename))
    return orders


def _base_walk_orders(mode: str, monolith_filename: str) -> list[dict]:
    if mode == "monolith":
        return [
            {
                "question": "project overview",
                "steps": [
                    {"fetch": monolith_filename, "then": "Read stats for scale, then the components tree for structure. Do not re-fetch; everything is here."},
                ],
            },
            {
                "question": "review findings first",
                "steps": [
                    {"fetch": monolith_filename, "then": "Read .findings (ranked) and .concerns. Filter on kind, rank_score, and verification_status (the real finding fields)."},
                ],
            },
            {
                "question": "look up a symbol or file",
                "steps": [
                    {"fetch": monolith_filename, "then": "Scan the inline .symbols / .files arrays by name or path; each file's owning component is the component whose .files contains that path."},
                ],
            },
            {
                "question": "assess coverage",
                "steps": [
                    {"fetch": monolith_filename, "then": "Read .coverage.summary for the disposition counts and .coverage.rows for per-file dispositions."},
                ],
            },
        ]
    return [
        {
            "question": "project overview",
            "steps": [
                {"fetch": "manifest.json", "then": "Read stats for scale, then the components tree (nested) for structure. To rank components by importance use activity.json hotspots and/or each component's ai_enhance.criticality when enriched, plus relationship fan-in."},
            ],
        },
        {
            "question": "review findings first",
            "steps": [
                {"fetch": "manifest.json", "then": "Read .findings (already ranked) and .concerns. Filter on kind, rank_score, and verification_status (the real finding fields). This is one fetch; do not pull shards."},
            ],
        },
        {
            "question": "look up a symbol, file, or component by name",
            "steps": [
                {"fetch": "search/manifest.json", "then": "Read total and shards. If there is one shard, fetch it; otherwise fetch shards in order and scan (see search.how_to_pick_a_shard)."},
                {"fetch": "search/search-<NNNN>.json", "then": "Match on `name`/`path`/`text`. The `component` field on a hit is the owning component id."},
                {"fetch": "data/detail-<safe_id>.json", "then": "Only if you need the symbol/file bodies for that component; apply the filename rule to the owning component id."},
            ],
        },
        {
            "question": "find the component that owns a file path",
            "steps": [
                {"fetch": "search/manifest.json", "then": "Confirm shard count."},
                {"fetch": "search/search-<NNNN>.json", "then": "Find the entry with ref_kind=file and ref_id equal to the path; its `component` field is the owning component id."},
            ],
        },
        {
            "question": "assess coverage",
            "steps": [
                {"fetch": "manifest.json", "then": "Read .coverage for the headline disposition counts (one fetch may be enough)."},
                {"fetch": "coverage.json", "then": "Only if you need per-file dispositions or the non-source inventory: read .summary, .rows, and .inventory."},
            ],
        },
        {
            "question": "explore flows and structure in depth",
            "steps": [
                {"fetch": "manifest.json", "then": "Walk .components and .relationships; follow `target_view` and composition edges. Read .tours if present for curated walkthroughs."},
                {"fetch": "data/detail-<safe_id>.json", "then": "Drill into a specific component's symbols and files as needed, one component at a time."},
            ],
        },
    ]


def _token_economy() -> dict:
    return {
        "principle": (
            "Fetch the smallest set of files that answers the question. Never crawl "
            "the whole tree. The point of this projection is to answer questions "
            "about the codebase in a fraction of the tokens that reading the raw "
            "source would cost."
        ),
        "rules": [
            "Start at manifest.json (split) or architecture.json (monolith) for any structural question.",
            "For findings/concerns/coverage-summary/activity-summary, the manifest often answers in a single fetch; do not pull shards.",
            "For a name/path lookup, use the search shards, then fetch at most one detail shard for depth.",
            "Detail shards are per-component: fetch only the component you are drilling into, never the whole data/ directory.",
            "Treat each fetch as a cost; prefer the manifest's embedded summaries over the full coverage.json / activity.json unless you need per-row detail.",
        ],
    }


def build_front_door(
    arch: dict,
    *,
    mode: str,
    coverage: Optional[dict] = None,
    activity: Optional[dict] = None,
    search_manifest: Optional[dict] = None,
    supply_chain: Optional[dict] = None,
    cra_present: bool = False,
    monolith_filename: str = "architecture.json",
) -> tuple[dict, str]:
    """Build the ``(ai_json_dict, llms_txt_str)`` pair for a projection.

    ``mode`` is ``"split"`` or ``"monolith"``. In split mode ``search_manifest``
    is the dict returned by ``write_search_shards`` (its shard list and sizing
    feed the search section); in monolith mode it is ignored. ``coverage``,
    ``activity``, ``supply_chain``, and ``cra_present`` gate the corresponding
    endpoints (link integrity: only files that are emitted are listed).
    """
    if mode not in ("split", "monolith"):
        raise ValueError(f"mode must be 'split' or 'monolith', got {mode!r}")

    dataset = _dataset_identity(arch)

    ai_json: dict = {
        "front_door_version": FRONT_DOOR_VERSION,
        "kind": "solution-explorer-front-door",
        "mode": mode,
        "dataset": dataset,
        "manifest_sections": _manifest_sections(
            arch, mode=mode, coverage=coverage, activity=activity
        ),
        "walk_orders": _walk_orders(
            mode, monolith_filename, supply_chain=supply_chain, cra_present=cra_present,
            # Derived from the arch itself, not passed in: the design section is
            # stamped onto the arch by the projection before the front door
            # runs, so reading it here keeps the advertisement and the data in
            # lockstep. Advertising a recipe for a section that is absent would
            # be the same lying contract the search gating guards against.
            design_signals=bool(arch.get("design_signals")),
        ),
        "token_economy": _token_economy(),
    }

    if mode == "split":
        ai_json["projection_root"] = "./"
        ai_json["entry"] = "manifest.json"
        ai_json["endpoints"] = _split_endpoints(
            arch, coverage=coverage, activity=activity,
            search_present=search_manifest is not None, supply_chain=supply_chain,
            cra_present=cra_present,
        )
        sm = search_manifest or {}
        ai_json["search"] = {
            "index": "search/manifest.json",
            "shard_dir": "search/",
            "shard_size": sm.get("shard_size"),
            "total": sm.get("total", 0),
            "by_kind": sm.get("by_kind", {}),
            "ref_kinds": sorted((sm.get("by_kind") or {}).keys()),
            "fields": sm.get("fields", ["ref_kind", "ref_id", "name", "path", "component", "text"]),
            "shards": sm.get("shards", []),
            "how_to_pick_a_shard": (
                "Entries are globally sorted by (ref_kind, ref_id) and chunked into "
                "shards of `shard_size`, named search-0000.json, search-0001.json, ... "
                "There is no per-shard key range, so a lookup fetches shards in order "
                "and scans. Most repos fit in a single shard (shard_size is 2000), so "
                "one fetch usually suffices; only fetch further shards if the term is "
                "not found and more shards remain."
            ),
        }
        ai_json["detail_shards"] = {
            "dir": "data/",
            "filename_rule": (
                "detail-<safe_id>.json where safe_id is the component id with '/' "
                "replaced by '--' and ':' replaced by '__'. Example: component id "
                "'viewer/src' -> data/detail-viewer--src.json."
            ),
            "index": "component_detail_index (in manifest.json) maps component id -> {symbolCount, fileCount}",
            "contains": "{symbols: [...], files: [...]} for that one component.",
        }
        if search_manifest is None:
            # A legacy split dataset without search shards (pre-search committed
            # demos). Advertising an index that does not exist is a lying
            # contract; the search section goes null and the lookup walk orders
            # fall back to the manifest components tree (review-driven gating).
            ai_json["search"] = None
            fallback = {
                "fetch": "manifest.json",
                "then": (
                    "This dataset has no search index. Walk the components tree "
                    "(names and paths) and component_detail_index, then fetch the "
                    "matching detail shard via detail_shards.filename_rule."
                ),
            }
            ai_json["walk_orders"] = [
                order if not any("search/" in st.get("fetch", "") for st in order["steps"])
                else {"question": order["question"], "steps": [fallback]}
                for order in ai_json["walk_orders"]
            ]
    else:
        ai_json["projection_root"] = "./"
        ai_json["entry"] = monolith_filename
        ai_json["endpoints"] = _monolith_endpoints(
            monolith_filename, arch, supply_chain=supply_chain, cra_present=cra_present
        )

    llms_txt = _render_llms_txt(ai_json, mode=mode, monolith_filename=monolith_filename)
    return ai_json, llms_txt


def _render_llms_txt(ai_json: dict, *, mode: str, monolith_filename: str) -> str:
    """Render the llms.txt markdown companion in a fixed line order."""
    dataset = ai_json["dataset"]
    name = dataset.get("name") or "this project"
    # The name is interpolated into markdown: collapse any control characters
    # and newlines to single spaces so a hostile or odd directory name cannot
    # split the heading or inject markdown lines (review finding). ai.json is
    # JSON-escaped and needs no such treatment.
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name).strip() or "this project"
    lines: list[str] = []
    lines.append(f"# {name} architecture (solution-explorer projection)")
    lines.append("")
    lines.append(
        "> Machine-readable architecture enumeration of this codebase. Answer "
        "questions about the code by fetching the small JSON files below instead "
        "of reading the raw repository. Start with ai.json for the full endpoint "
        "map, walk orders, and the token-economy contract."
    )
    lines.append("")
    generated = dataset.get("generated_at")
    version = dataset.get("analyzer_version")
    meta = []
    if generated:
        meta.append(f"generated_at: {generated}")
    if version:
        meta.append(f"analyzer_version: {version}")
    meta.append(f"front_door_version: {ai_json['front_door_version']}")
    meta.append(f"mode: {mode}")
    lines.append(f"_{'; '.join(meta)}_")
    lines.append("")
    lines.append("## Start here")
    lines.append("")
    lines.append("- [ai.json](./ai.json): endpoint map, sharding schemes, walk orders, token-economy contract (read this first).")
    lines.append("")
    lines.append("## Endpoints")
    lines.append("")
    if mode == "split":
        lines.append("- [manifest.json](./manifest.json): structural entry document (components, relationships, stats, findings, concerns, coverage/activity summaries). Fetch first.")
        if ai_json.get("search") is not None:
            lines.append("- [search/manifest.json](./search/manifest.json): search-shard index; then search/search-<NNNN>.json shards resolve a name or path to its owning component.")
        lines.append("- data/detail-<safe_id>.json: per-component symbols and files (fetch only the component you drill into).")
        if any(e["path"] == "coverage.json" for e in ai_json["endpoints"]):
            lines.append("- [coverage.json](./coverage.json): full per-file coverage ledger and non-source inventory.")
        if any(e["path"] == "activity.json" for e in ai_json["endpoints"]):
            lines.append("- [activity.json](./activity.json): git-history activity lens (hotspots, knowledge, coupling).")
        if any(e["path"] == "sbom.json" for e in ai_json["endpoints"]):
            lines.append("- [sbom.json](./sbom.json): CycloneDX 1.5 SBOM; a quick dependency summary is in manifest.json .supply_chain.")
        if any(e["path"] == "cra-readiness.json" for e in ai_json["endpoints"]):
            lines.append("- [cra-readiness.json](./cra-readiness.json): repo-observable CRA readiness checklist (presence/absence items with evidence; not a conformity assessment).")
        for filename, label in (("orientation.json", "human orientation and question routes"), ("support.json", "Support and Operations view"), ("security.json", "repository-observable Security view")):
            if any(e["path"] == filename for e in ai_json["endpoints"]):
                lines.append(f"- [{filename}](./{filename}): {label}.")
    else:
        lines.append(f"- [{monolith_filename}](./{monolith_filename}): the whole dataset in one file (components, relationships, stats, inline symbols/files, embedded coverage/activity/supply_chain). Small-repo layout with no separate shards.")
        if any(e["path"] == "sbom.json" for e in ai_json["endpoints"]):
            lines.append("- [sbom.json](./sbom.json): CycloneDX 1.5 SBOM beside the monolith; a quick dependency summary is in its .supply_chain section.")
        if any(e["path"] == "cra-readiness.json" for e in ai_json["endpoints"]):
            lines.append("- [cra-readiness.json](./cra-readiness.json): repo-observable CRA readiness checklist beside the monolith (presence/absence items with evidence; not a conformity assessment).")
        for filename, label in (("orientation.json", "human orientation and question routes"), ("support.json", "Support and Operations view"), ("security.json", "repository-observable Security view")):
            if any(e["path"] == filename for e in ai_json["endpoints"]):
                lines.append(f"- [{filename}](./{filename}): {label} beside the monolith.")
    lines.append("")
    lines.append("## Token economy")
    lines.append("")
    lines.append(f"{ai_json['token_economy']['principle']}")
    lines.append("")
    return "\n".join(lines)


def write_front_door(
    arch: dict,
    output_dir: Path,
    *,
    mode: str,
    coverage: Optional[dict] = None,
    activity: Optional[dict] = None,
    search_manifest: Optional[dict] = None,
    supply_chain: Optional[dict] = None,
    cra_present: bool = False,
    monolith_filename: str = "architecture.json",
    indent=2,
) -> tuple[Path, Path]:
    """Emit ``ai.json`` and ``llms.txt`` into ``output_dir``. Return their paths.

    ``output_dir`` is the projection root: the split output directory (beside
    ``manifest.json``) or the parent directory of the monolith file (beside
    ``architecture.json``). Byte-stable: ai.json is written sorted, llms.txt in a
    fixed line order.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ai_json, llms_txt = build_front_door(
        arch,
        mode=mode,
        coverage=coverage,
        activity=activity,
        search_manifest=search_manifest,
        supply_chain=supply_chain,
        cra_present=cra_present,
        monolith_filename=monolith_filename,
    )

    ai_path = output_dir / AI_JSON_NAME
    with open(ai_path, "w", encoding="utf-8") as fh:
        json.dump(ai_json, fh, indent=indent, default=str, sort_keys=True)

    llms_path = output_dir / LLMS_TXT_NAME
    with open(llms_path, "w", encoding="utf-8") as fh:
        fh.write(llms_txt)
        if not llms_txt.endswith("\n"):
            fh.write("\n")

    return ai_path, llms_path


def refresh_front_door(target_path) -> Optional[tuple[Path, Path]]:
    """Regenerate ``ai.json``/``llms.txt`` beside a projection mutated in place.

    The deploy pipeline's AI-enhancement merge edits ``manifest.json`` (or the
    monolith ``architecture.json``) AFTER projection wrote the front door, which
    left deployed datasets whose ``ai.json`` asserted ``enriched: false`` while
    the manifest carried ``ai_enhance`` on nearly every component (the
    comprehension-study S3 finding). Any step that rewrites a projected entry
    document calls this afterward so the front door describes the file as it
    now is.

    Every optional endpoint is gated on what actually exists on disk beside the
    target, mirroring the projection's own link-integrity rule (only files that
    are emitted are listed) without re-running the projection. Returns the
    written ``(ai.json, llms.txt)`` paths, or ``None`` when no front door exists
    beside the target (a projection that never emitted one keeps not having
    one).
    """
    target_path = Path(target_path)
    output_dir = target_path.parent
    if not (output_dir / AI_JSON_NAME).is_file():
        return None
    with open(target_path, encoding="utf-8") as fh:
        arch = json.load(fh)
    mode = "split" if target_path.name == "manifest.json" else "monolith"

    def _sibling_json(rel_name: str) -> Optional[dict]:
        path = output_dir / rel_name
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as sibling:
                loaded = json.load(sibling)
        except (json.JSONDecodeError, OSError):
            return None
        return loaded if isinstance(loaded, dict) else None

    if mode == "split":
        # In split mode the full coverage/activity payloads live in sibling
        # files; their presence on disk is exactly the emit-time gate.
        coverage = _sibling_json("coverage.json")
        activity = _sibling_json("activity.json")
        search_manifest = _sibling_json("search/manifest.json")
    else:
        # In monolith mode the writer injected the full blocks into the entry
        # document itself, which is the file just loaded.
        coverage = arch.get("coverage")
        activity = arch.get("activity")
        search_manifest = None

    supply_chain = (
        arch.get("supply_chain")
        if (output_dir / "sbom.json").is_file()
        else None
    )
    cra_present = (output_dir / "cra-readiness.json").is_file()

    return write_front_door(
        arch,
        output_dir,
        mode=mode,
        coverage=coverage,
        activity=activity,
        search_manifest=search_manifest,
        supply_chain=supply_chain,
        cra_present=cra_present,
        monolith_filename=target_path.name,
    )
