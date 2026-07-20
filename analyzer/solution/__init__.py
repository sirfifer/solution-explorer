"""Multi-repo solution composition (M1, MULTI-REPO-DESIGN.md).

A *solution* is one product that spans several repositories (for example a
server plus one or more clients). This package composes the EXISTING single-repo
v2 engine over each member repo and emits a composed projection: every member's
unchanged split projection under ``members/<slug>/`` plus a thin solution layer
(a member index, per-member coverage summaries, and an AI front door that
teaches descent into members).

M1 is composition only. There are NO cross-repo edges, NO merged store, and NO
blended coverage denominator (each design decision is spelled out in
``docs/remediation/MULTI-REPO-DESIGN.md``). The member repo store stays the unit
of truth (decision 1); the solution is a concatenation plus a solution layer,
never a blend (decisions 3 and 5).
"""

from __future__ import annotations

from .compose import SOLUTION_KIND, SolutionProjectionResult, compose_solution
from .manifest import (
    SOLUTION_SCHEMA,
    Solution,
    SolutionMember,
    load_solution_manifest,
)

__all__ = [
    "SOLUTION_SCHEMA",
    "SOLUTION_KIND",
    "Solution",
    "SolutionMember",
    "SolutionProjectionResult",
    "load_solution_manifest",
    "compose_solution",
]
