"""Correlation derivation (Tier 3, P5-6): what the system noticed on its own.

Deterministic, evidence-bearing correlations over the store, never AI-invented
(invariant I1; LENS-DESIGN.md section 9). Three families, all read-only over the
Deriver's store view:

  - CLONE CLUSTERS. Group the ``clone_fragment`` fingerprints the extraction
    tier emitted (token-stream winnowing, extract/clones.py) into near-duplicate
    sets. Whole-fragment normalized-hash equality catches type-1/2 clones;
    fingerprint-set Jaccard over a document-frequency-filtered inverted index
    catches type-3 near-duplicates. Each cross-file cluster becomes a
    duplication finding with per-member file and line-range evidence.
  - ORPHANS. Leaf components unreachable from any entry point (no incoming edge,
    no entry-point role, no owned capability, not test code), emitted as orphan
    findings. Symbol-level orphans are out of scope: the store has no
    symbol-granularity reference graph, so they are not "cheaply resolvable".
  - CONCERNS. Cross-cutting membership sets orthogonal to the hierarchy
    (logging, auth, persistence, http-client, caching, configuration) detected
    from imports, signals, rules, and entity access, plus clone-derived concerns
    for clusters spanning three or more components. Mechanical slug ids only;
    domain naming is P7-4.

Findings are typed store entities (kind, members, evidence, confidence,
verification_status='unverified', rank_score). Verification is P7-4's job
(invariant I15); this pass sets the status field and a deterministic rank score
(I11). Emission is deterministic (I4): ids are content-derived (blake2b), never
discovery-order-derived; concerns are id-sorted, findings rank-then-id-sorted,
and every member/evidence list is sorted.

Complexity. Fragment fingerprinting is linear in tokens (done in Tier 1).
Clustering here is near-linear in fragment count for distinctive code: building
the inverted fingerprint index is O(sum of fingerprints); a document-frequency
filter drops stop-fingerprints (idiom shingles) so no bucket exceeds MAX_DF_ABS
members, bounding candidate pairs to O(MAX_DF_ABS * total_fingerprints); union
-find is near-linear. Concern and orphan detection are single passes over
components and their files.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from .context import Deriver

__all__ = ["derive_correlations"]

# -- clone-cluster thresholds (recorded in the P5-6 card, proven by tests) ---
SIM_THRESHOLD = 0.80   # minimum fingerprint-set Jaccard for a type-3 near-dup
MAX_DF_ABS = 40        # a fingerprint in more than this many fragments is dropped
MAX_DF_FRAC = 0.20     # ... or in more than this fraction of all fragments

# -- concern threshold -------------------------------------------------------
MIN_CONCERN_MEMBERS = 2      # signal concerns are cross-cutting: 2+ components
MIN_CLONE_CONCERN_COMPONENTS = 3  # a cluster is a concern only across 3+ comps

# Concern kinds that get an inconsistency finding when members use visibly
# divergent implementations. Kept conservative (LENS-DESIGN 9): logging is the
# canonical "ten logging implementations" case. The mechanism is generic; enable
# more kinds here only with evidence they are not noisy.
_INCONSISTENCY_CONCERN_KINDS = frozenset({"logging"})

# Component types that are externally reachable entry points, so never orphans.
_ENTRY_TYPES = frozenset({
    "application", "api-server", "cli-tool", "service", "screen", "watch-app",
    "desktop-app", "mobile-app", "web-app", "infrastructure",
})
# Component types that are test code, excluded from orphan detection.
_TEST_TYPES = frozenset({"test", "tests", "testing", "test_suite", "e2e", "integration"})
# Non-code content strata are never orphans.
_NONCODE_TYPES = frozenset({"content", "static", "assets"})

# ---------------------------------------------------------------------------
# Concern library vocabularies. Matched against import first-segments, so they
# stay language-agnostic (a Python ``logging.handlers`` and a Go ``log`` both
# match ``log*`` families). Mechanical detection only; AI naming is P7-4.
# ---------------------------------------------------------------------------

_LOGGING_LIBS = frozenset({
    "logging", "loguru", "structlog", "winston", "pino", "bunyan", "log4js",
    "zap", "logrus", "zerolog", "slog", "logger", "tracing", "env_logger",
    "oslog", "swiftlog", "log",
})
_AUTH_LIBS = frozenset({
    "jwt", "pyjwt", "authlib", "oauthlib", "passlib", "bcrypt", "argon2",
    "flask_login", "flask_jwt_extended", "passport", "jsonwebtoken", "next-auth",
    "@auth", "devise", "warden", "oauth2", "golang-jwt",
})
_CACHING_LIBS = frozenset({
    "redis", "ioredis", "go-redis", "memcache", "memcached", "pymemcache",
    "dalli", "cachetools", "diskcache", "aiocache", "node-cache", "lru-cache",
    "lru", "cached", "moka", "groupcache", "bigcache",
})
# Access-control keywords. A P5-5 ``policy`` rule feeds the auth concern only
# when its mechanical summary names one of these: a generic multi-branch
# decision rule ("if language == python") is a policy rule but NOT auth, so
# feeding every policy rule into auth would flood it (precision over recall).
_AUTH_RULE_KEYWORDS = (
    "authoriz", "authentic", "permission", "credential", "unauthor",
    "forbidden", "role ", "roles", "login", "logout", "jwt", "oauth",
    "session", "rbac", "acl", "access control", "access-control",
)


def _hash8(*parts: object) -> str:
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.blake2b(joined.encode("utf-8"), digest_size=8).hexdigest()[:8]


def _import_markers(imports: list[str], libs: frozenset) -> set[str]:
    """Library names from ``libs`` that ``imports`` references."""
    out: set[str] = set()
    for raw in imports:
        imp = raw.strip().strip("\"'")
        if not imp:
            continue
        candidates = {imp, imp.split(".")[0], imp.split("/")[0]}
        out |= candidates & libs
    return out


# ---------------------------------------------------------------------------
# Clone clusters
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int):
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def _collect_fragments(d: Deriver) -> list[dict]:
    """Read every ``clone_fragment`` signal, resolve the owning component."""
    frags: list[dict] = []
    for path in sorted(d.view.signals_by_path):
        comp = d._find_component_for_file(path)
        comp_id = comp.id if comp else None
        for sig in d.view.signals_by_path[path]:
            if sig.get("kind") != "clone_fragment":
                continue
            v = sig.get("value") or {}
            fps = v.get("fps") or []
            frags.append({
                "file": path,
                "component_id": comp_id,
                "symbol": v.get("symbol"),
                "line": v.get("line"),
                "end_line": v.get("end_line"),
                "ntokens": v.get("ntokens") or 0,
                "norm_hash": v.get("norm_hash"),
                "raw_hash": v.get("raw_hash"),
                "fps": frozenset(fps),
            })
    # Deterministic order so fragment indices (and thus union-find tie-breaks)
    # do not depend on signal-read order.
    frags.sort(key=lambda f: (f["file"], f["line"] or 0, f["symbol"] or ""))
    return frags


def _cluster_fragments(frags: list[dict]) -> list[list[int]]:
    """Union near-duplicate fragments; return member-index groups (size >= 2)."""
    n = len(frags)
    uf = _UnionFind(n)

    # Whole-fragment normalized-hash equality (type-1/2 exact-normalized).
    by_norm: dict[str, list[int]] = {}
    for i, f in enumerate(frags):
        if f["norm_hash"]:
            by_norm.setdefault(f["norm_hash"], []).append(i)
    for members in by_norm.values():
        for j in members[1:]:
            uf.union(members[0], j)

    # Inverted fingerprint index with a document-frequency filter: idiom
    # shingles that appear everywhere carry no signal and would blow up buckets.
    index: dict[int, list[int]] = {}
    for i, f in enumerate(frags):
        for fp in f["fps"]:
            index.setdefault(fp, []).append(i)
    df_cap = min(MAX_DF_ABS, max(2, int(MAX_DF_FRAC * n))) if n else MAX_DF_ABS

    candidate_pairs: set[tuple[int, int]] = set()
    for fp in sorted(index):
        bucket = index[fp]
        if len(bucket) > df_cap:
            continue  # stop-fingerprint (too common to be distinctive)
        for a_i in range(len(bucket)):
            for b_i in range(a_i + 1, len(bucket)):
                candidate_pairs.add((bucket[a_i], bucket[b_i]))

    for a, b in sorted(candidate_pairs):
        fa, fb = frags[a]["fps"], frags[b]["fps"]
        if not fa or not fb:
            continue
        inter = len(fa & fb)
        if inter == 0:
            continue
        union = len(fa | fb)
        if union and inter / union >= SIM_THRESHOLD:
            uf.union(a, b)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return [sorted(m) for m in groups.values() if len(m) >= 2]


def _classify(members: list[dict]) -> str:
    raw_hashes = {m["raw_hash"] for m in members}
    if len(raw_hashes) == 1:
        return "exact"
    norm_hashes = {m["norm_hash"] for m in members}
    if len(norm_hashes) == 1:
        return "renamed"
    return "similar"


_CLASS_WEIGHT = {"exact": 15.0, "renamed": 8.0, "similar": 3.0}


def _build_clusters(d: Deriver) -> list[dict]:
    """Return clone clusters (cross-file), each with members and a class."""
    frags = _collect_fragments(d)
    clusters: list[dict] = []
    for group in _cluster_fragments(frags):
        members = [frags[i] for i in group]
        files = {m["file"] for m in members}
        if len(files) < 2:
            continue  # a within-file repeat is not a clone cluster
        members.sort(key=lambda m: (m["file"], m["line"] or 0))
        cls = _classify(members)
        comp_ids = sorted({m["component_id"] for m in members if m["component_id"]})
        total_tokens = sum(m["ntokens"] for m in members)
        key = _hash8(*[f"{m['file']}:{m['line']}-{m['end_line']}" for m in members])
        clusters.append({
            "id": f"clone-{key}",
            "class": cls,
            "members": members,
            "component_ids": comp_ids,
            "total_tokens": total_tokens,
        })
    clusters.sort(key=lambda c: c["id"])
    return clusters


def _duplication_finding(cluster: dict) -> dict:
    members = cluster["members"]
    comps = cluster["component_ids"]
    rank = (
        100.0
        + len(members) * 8.0
        + len(comps) * 12.0
        + min(cluster["total_tokens"], 1000) / 20.0
        + _CLASS_WEIGHT.get(cluster["class"], 3.0)
    )
    finding_members = [{
        "kind": "fragment",
        "id": f"{m['file']}:{m['line']}",
        "file": m["file"],
        "line_start": m["line"],
        "line_end": m["end_line"],
        "symbol": m["symbol"],
        "component_id": m["component_id"],
    } for m in members]
    evidence = [{
        "file": m["file"], "line": m["line"], "end_line": m["end_line"],
        "symbol": m["symbol"],
    } for m in members]
    span = f"{len(comps)} components" if len(comps) != 1 else "1 component"
    return {
        "id": f"finding:duplication:{cluster['id'].split('-', 1)[1]}",
        "kind": "duplication",
        "summary": (
            f"{cluster['class']} clone across {len(members)} fragments in {span}"
        ),
        "members": finding_members,
        "evidence": evidence,
        "confidence": "inferred",
        "verification_status": "unverified",
        "rank_score": round(rank, 4),
        "detail": {
            "clone_class": cluster["class"],
            "component_ids": comps,
            "total_tokens": cluster["total_tokens"],
        },
    }


# ---------------------------------------------------------------------------
# Concerns
# ---------------------------------------------------------------------------

def _component_files(d: Deriver) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for comp in d._component_map.values():
        out[comp.id] = list(comp.files)
    return out


def _signal_lines(d: Deriver, files: list[str], kinds: set[str]) -> list[dict]:
    """Evidence rows for the first occurrence of each kind per file."""
    ev: list[dict] = []
    for f in sorted(files):
        seen: set[str] = set()
        for sig in d.view.signals_by_path.get(f, []):
            k = sig.get("kind")
            if k in kinds and k not in seen:
                seen.add(k)
                ev.append({"file": f, "line": sig.get("line"), "signal": k})
    return ev


def _build_concerns(d: Deriver, clusters: list[dict]) -> list[dict]:
    comp_files = _component_files(d)

    # Auth is fed by P5-5 access-control policy rules in addition to
    # auth-library imports. Only policy rules naming an access-control concept
    # count (an auth "gate"); generic decision branching does not (precision).
    policy_components: dict[str, list[dict]] = {}
    for rule in d.rules:
        if rule.get("kind") != "policy" or not rule.get("component_id"):
            continue
        summary = (rule.get("summary") or "").lower()
        if not any(kw in summary for kw in _AUTH_RULE_KEYWORDS):
            continue
        policy_components.setdefault(rule["component_id"], []).extend(rule.get("evidence") or [])

    # Persistence is fed by entity ownership and access in addition to drivers.
    entity_components: set[str] = set()
    for ent in d.data_entities:
        if ent.get("component_id"):
            entity_components.add(ent["component_id"])
    accessor_components: set[str] = set()
    for acc in d.entity_access:
        aid = acc.get("accessor_id")
        if aid:
            accessor_components.add(aid)

    concerns: list[dict] = []

    def emit(kind: str, basis: str, members: list[dict], detail: Optional[dict] = None) -> None:
        if len(members) < MIN_CONCERN_MEMBERS:
            return
        members.sort(key=lambda m: m["component_id"] or "")
        concerns.append({
            "id": f"concern:{kind}",
            "kind": kind,
            "title": kind.replace("-", " ").title(),
            "basis": basis,
            "members": members,
            "detail": detail or {},
        })

    # -- library-import concerns (logging, auth, caching) --
    for kind, libs in (("logging", _LOGGING_LIBS), ("auth", _AUTH_LIBS),
                       ("caching", _CACHING_LIBS)):
        members: list[dict] = []
        for cid in sorted(comp_files):
            markers: set[str] = set()
            files_hit: list[str] = []
            for f in sorted(comp_files[cid]):
                m = _import_markers(d.view.imports_by_path.get(f, []), libs)
                if m:
                    markers |= m
                    files_hit.append(f)
            # Auth also counts a component carrying a policy rule.
            extra_ev: list[dict] = []
            if kind == "auth" and cid in policy_components:
                markers.add("policy-rule")
                extra_ev = [
                    {"file": e.get("file"), "line": e.get("line"), "signal": "policy-rule"}
                    for e in policy_components[cid][:3]
                ]
            # Caching also counts a redis database driver.
            if kind == "caching":
                for f in sorted(comp_files[cid]):
                    for sig in d.view.signals_by_path.get(f, []):
                        if sig.get("kind") == "db_driver" and (sig.get("value") or {}).get("engine") == "redis":
                            markers.add("redis")
                            if f not in files_hit:
                                files_hit.append(f)
            if markers:
                ev = [{"file": f, "signal": "import"} for f in sorted(files_hit)] + extra_ev
                members.append({
                    "component_id": cid,
                    "files": sorted(files_hit),
                    "evidence": ev,
                    "markers": sorted(markers),
                })
        emit(kind, f"{kind} library imports", members)

    # -- signal-driven concerns --
    signal_concerns = [
        ("persistence", {"db_driver"}, "database drivers, entity access"),
        ("http-client", {"http_client"}, "http client usage"),
        ("configuration", {"env_var"}, "environment-variable reads"),
    ]
    for kind, sig_kinds, basis in signal_concerns:
        members = []
        for cid in sorted(comp_files):
            ev = _signal_lines(d, comp_files[cid], sig_kinds)
            files_hit = sorted({e["file"] for e in ev})
            if kind == "persistence" and (cid in entity_components or cid in accessor_components):
                if not ev:
                    ev = [{"file": None, "line": None, "signal": "entity_access"}]
            if ev:
                members.append({
                    "component_id": cid,
                    "files": files_hit,
                    "evidence": ev,
                    "markers": sorted({e["signal"] for e in ev}),
                })
        emit(kind, basis, members)

    # -- clone-derived concerns (a cluster spanning 3+ components) --
    for cluster in clusters:
        comps = cluster["component_ids"]
        if len(comps) < MIN_CLONE_CONCERN_COMPONENTS:
            continue
        members = [{
            "component_id": cid,
            "files": sorted({m["file"] for m in cluster["members"] if m["component_id"] == cid}),
            "evidence": [
                {"file": m["file"], "line": m["line"], "signal": "clone"}
                for m in cluster["members"] if m["component_id"] == cid
            ],
            "markers": [cluster["class"]],
        } for cid in comps]
        members.sort(key=lambda m: m["component_id"] or "")
        concerns.append({
            "id": f"concern:{cluster['id']}",
            "kind": "clone",
            "title": f"Duplicated code ({cluster['class']})",
            "basis": f"clone cluster spanning {len(comps)} components",
            "members": members,
            "detail": {"clone_class": cluster["class"], "cluster_id": cluster["id"]},
        })

    concerns.sort(key=lambda c: c["id"])
    return concerns


def _inconsistency_findings(concerns: list[dict]) -> list[dict]:
    """Same concern, visibly divergent implementations (conservative, inferred)."""
    out: list[dict] = []
    for concern in concerns:
        if concern["kind"] not in _INCONSISTENCY_CONCERN_KINDS:
            continue
        libs: set[str] = set()
        for m in concern["members"]:
            libs |= {mk for mk in m.get("markers", []) if mk != "policy-rule"}
        if len(libs) < 2:
            continue
        members = [{
            "kind": "component", "id": m["component_id"],
            "component_id": m["component_id"], "markers": m.get("markers", []),
        } for m in concern["members"]]
        evidence = [{
            "component_id": m["component_id"], "libraries": m.get("markers", []),
            "files": m.get("files", []),
        } for m in concern["members"]]
        rank = 60.0 + len(libs) * 10.0 + len(members) * 3.0
        out.append({
            "id": f"finding:inconsistency:{concern['kind']}-{_hash8(*sorted(libs))}",
            "kind": "inconsistency",
            "summary": (
                f"{concern['kind']} concern uses {len(libs)} distinct "
                f"implementations: {', '.join(sorted(libs))}"
            ),
            "members": members,
            "evidence": evidence,
            "confidence": "inferred",
            "verification_status": "unverified",
            "rank_score": round(rank, 4),
            "detail": {"concern_id": concern["id"], "libraries": sorted(libs)},
        })
    return out


# ---------------------------------------------------------------------------
# Orphans
# ---------------------------------------------------------------------------

def _incoming_targets(d: Deriver) -> set[str]:
    targets: set[str] = set()
    for rel in list(d.relationships) + list(d._ui_relationships):
        targets.add(rel.target)
    return targets


def _orphan_findings(d: Deriver) -> list[dict]:
    incoming = _incoming_targets(d)
    cap_owners = {c.get("component_id") for c in d.capabilities if c.get("component_id")}
    child_parents = {c.id for comp in d._component_map.values()
                     for c in comp.children if getattr(c, "id", None)}
    # A component with path-children is not a leaf.
    parent_paths: set[str] = set()
    for path in d._component_map:
        parent = d._find_parent_component(path)
        if parent is not None and parent in d._component_map:
            parent_paths.add(parent)

    out: list[dict] = []
    for path in sorted(d._component_map):
        comp = d._component_map[path]
        if path == "" or comp.id == "root":
            continue
        if path in parent_paths or comp.id in child_parents:
            continue  # not a leaf
        if comp.type in _ENTRY_TYPES or comp.type in _TEST_TYPES or comp.type in _NONCODE_TYPES:
            continue
        if getattr(comp, "entry_points", None):
            continue
        if comp.id in cap_owners:
            continue
        if comp.id in incoming:
            continue
        if d._is_under_vendored(path):
            continue
        metrics = getattr(comp, "metrics", None) or {}
        symbols = metrics.get("symbols", 0)
        lines = metrics.get("lines", 0)
        if symbols <= 0:
            continue  # no code, not a meaningful orphan
        rank = 20.0 + min(lines, 500) / 12.0
        out.append({
            "id": f"finding:orphan:{comp.id}",
            "kind": "orphan",
            "summary": f"component '{comp.name}' has no incoming references",
            "members": [{
                "kind": "component", "id": comp.id, "component_id": comp.id,
                "file": None, "line_start": None, "line_end": None,
            }],
            "evidence": [{
                "component_id": comp.id, "path": comp.path,
                "files": sorted(comp.files)[:10], "type": comp.type,
            }],
            "confidence": "inferred",
            "verification_status": "unverified",
            "rank_score": round(rank, 4),
            "detail": {"lines": lines, "symbols": symbols, "type": comp.type},
        })
    return out


# ---------------------------------------------------------------------------
# Pass entry point
# ---------------------------------------------------------------------------

def derive_correlations(d: Deriver) -> None:
    """Derive clone clusters, concerns, and findings; record them on ``d``."""
    clusters = _build_clusters(d)
    concerns = _build_concerns(d, clusters)

    findings: list[dict] = []
    findings.extend(_duplication_finding(c) for c in clusters)
    findings.extend(_inconsistency_findings(concerns))
    findings.extend(_orphan_findings(d))
    findings.sort(key=lambda f: (-f["rank_score"], f["id"]))

    d.concerns = concerns
    d.findings = findings

    # Per-component reference indexes for the projection (I12: same element,
    # every lens). A component references the concerns it belongs to and the
    # findings that involve it.
    by_comp_concern: dict[str, list[str]] = {}
    for concern in concerns:
        for m in concern["members"]:
            cid = m.get("component_id")
            if cid:
                by_comp_concern.setdefault(cid, []).append(concern["id"])
    by_comp_finding: dict[str, list[str]] = {}
    for finding in findings:
        seen: set[str] = set()
        for m in finding["members"]:
            cid = m.get("component_id")
            if cid and cid not in seen:
                seen.add(cid)
                by_comp_finding.setdefault(cid, []).append(finding["id"])
    d._concerns_by_component = {k: sorted(set(v)) for k, v in by_comp_concern.items()}
    d._findings_by_component = {k: v for k, v in by_comp_finding.items()}
