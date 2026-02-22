# Live Architecture Implementation: Review Feedback

**Reviewer**: Claude (Opus 4.6)
**Date**: 2026-02-21
**Document reviewed**: `live-architecture-implementation.md`
**Supporting material**: `research/live-architecture-monitoring.md`, `architectural-assessment.md`, `analyzer-package.md`, `ui-actions-source-linking-plan.md`

---

## Overall Assessment

The implementation plan is exceptionally well structured. The research is thorough, the dual-mode architecture is sound, the tiered dependency graph enabling 6-way parallel execution is smart, and the obsessive attention to backward compatibility is exactly right. The free-tier-first philosophy is well executed: GitHub mode is genuinely $0 for public repos, and the Cloudflare free tier budget analysis shows comfortable headroom even at scale (100 repos, 20 viewers). No fundamental architectural objections. What follows are detail-level recommendations for tightening specific decisions.

---

## Recommendations

### 1. SettingsTab must be read-only in GitHub mode (Stream C)

**Priority**: High
**Stream**: C (Admin Dashboard UI)

The SettingsTab is described as having "mutable settings" with toggle-style inputs, but in GitHub mode there is no backend to persist changes. Settings live in a committed repo file (`solution-explorer.json`). In GitHub mode, the tab should be explicitly read-only with guidance like "Edit `solution-explorer.json` in your repo to change settings." Only in Cloudflare mode does the `POST /settings/:project_id` endpoint exist. Without this distinction, users will toggle settings and wonder why nothing persists.

### 2. Replace hard "stay paused" with slow-retry backoff in circuit breaker (Stream E)

**Priority**: High
**Stream**: E (Live Monitor Hooks)

The circuit breaker design (5 failures -> 60s pause -> single retry -> resume or stay paused) has a terminal "stay paused" state. This means a viewer could permanently stop updating after a transient GitHub Pages outage. A user who leaves a tab open overnight shouldn't come back to a stale dashboard because GitHub had a 30-second hiccup during the night.

**Recommendation**: After the initial pause, enter a slow-retry backoff (e.g., retry every 5 minutes while in error state). Reset to normal adaptive polling on first success. This provides self-healing without hammering a degraded service.

### 3. Add "full refresh every 30 min" safety net to Stream E tasks (Stream E)

**Priority**: Medium
**Stream**: E (Live Monitor Hooks)

The research document (Section 14) mentions a "full refresh every 30 min as safety net" but this does not appear in Stream E's implementation task list. If still desired, it should be an explicit task item. This serves as a catch-all for edge cases where ETag-based polling misses a change (e.g., CDN cache inconsistency).

### 4. Use `actions/deploy-pages` instead of `peaceiris/actions-gh-pages` (Stream F)

**Priority**: Medium-High
**Stream**: F (GitHub Actions Workflow)

The workflow uses `peaceiris/actions-gh-pages@v4`, a third-party action. For a security-conscious project, consider using GitHub's own `actions/deploy-pages` with `actions/upload-pages-artifact` instead. It is the officially supported path, does not require granting a PAT to a third-party action, and reduces supply-chain risk. The migration is straightforward and the official actions are well-documented.

### 5. Address race condition between `update-architecture` and `update-ci-status` deployments (Stream F)

**Priority**: High
**Stream**: F (GitHub Actions Workflow)

The `update-ci-status` job deploys only `status-overlay.json` to GitHub Pages with `keep_files: true`. Meanwhile `update-architecture` deploys all files. If a push triggers the main job at the same time as a `workflow_run` fires from a previous push's CI completion, the two jobs can race on gh-pages deployments, causing one to overwrite the other's changes.

The `concurrency` group (`live-monitor-${{ github.ref }}`) only serializes within the same workflow. Two separate jobs within the same workflow run, or overlapping workflow runs, can still conflict.

**Options**:
- Fold `update-ci-status` into `update-architecture` as a single deployment step
- Use a separate concurrency group that covers both jobs
- Use a mutex action like `turnstyle` to serialize all gh-pages writes

### 6. Build a flat component ID index for O(1) status overlay lookups (Stream B)

**Priority**: Medium
**Stream**: B (Types + Store Foundation)

`applyStatusOverlay` does a "recursive component tree traversal to match by ID" on every poll cycle. For large architectures (Vapor, Alamofire, and similar projects used as test cases), this is wasteful. Building a flat `Map<string, Component>` index once when the architecture loads (or when it changes) enables O(1) lookups during overlay merges. This is especially important since polling happens every 15-120 seconds.

### 7. Use timing-safe comparison for webhook signature verification (Stream H)

**Priority**: Low-Medium
**Stream**: H (Cloudflare-Enhanced Mode)

The `verifyGitHubWebhook` function uses string comparison (`signature === expected`) for the HMAC check. This is technically vulnerable to timing attacks. Use a constant-time comparison instead. In the Workers environment, one approach is to compare via `crypto.subtle.verify` or to use a byte-by-byte XOR comparison. The practical risk is negligible for webhook signatures, but it is a best practice worth adopting.

### 8. Add analyzer version stamp to baseline for full-rescan triggering (Stream G)

**Priority**: Medium
**Stream**: G (Incremental Analyzer)

The `should_full_rescan` heuristic checks for marker file changes, threshold exceedance, and force pushes, but does not check whether the analyzer itself has changed. If a parser improvement ships (e.g., better Swift property wrapper detection), unchanged files will never benefit from it because the incremental analyzer will skip them based on the unchanged baseline.

**Recommendation**: Include an analyzer version stamp in the baseline. When the current analyzer version differs from the baseline's version, trigger a full rescan. This ensures parser improvements are always applied.

### 9. Make Pydantic cross-reference root_validator opt-in or benchmark it (Stream I)

**Priority**: Medium
**Stream**: I (Pydantic Models + Validation)

The `Architecture` model has a root_validator that checks all relationship sources/targets exist in component IDs. This is a valuable integrity check, but it runs on every `Architecture` construction. For large architectures with thousands of components and tens of thousands of relationships, this O(relationships * components) validation could be expensive.

**Options**:
- Run the validator only when the `--validate` CLI flag is used
- Use a pre-built ID set for O(1) membership checks (reducing to O(relationships))
- Benchmark on a real large architecture and decide based on actual numbers

### 10. Clarify dependency graph expansion depth for transitive imports (Stream K)

**Priority**: Medium
**Stream**: K (True Incremental Re-Analysis)

The plan says "expand affected set via dependency graph (importers of changed components)" but does not specify the depth of expansion. If component A changes, component B imports A, and component C imports B (and re-exports A's types), does C need re-analysis?

For most codebases, one level of expansion suffices because imports are direct references. But re-exported symbols create transitive dependencies that can propagate changes further. The plan should explicitly state whether expansion is one-level or transitive, and if one-level, document the known limitation. A pragmatic default is one level with a `--deep-incremental` flag for transitive expansion.

### 11. Add R2 lifecycle rules for stale component detail files (Stream H)

**Priority**: Low
**Stream**: H (Cloudflare-Enhanced Mode)

The R2 bucket structure puts split-mode detail files at `live/{project_id}/detail/detail-{component-id}.json`. When components are removed from the architecture, their detail files become orphaned. Over time these accumulate.

**Recommendation**: Add a cleanup step to the Worker's `/ingest` endpoint: after processing a new architecture version, compare the manifest's component IDs against the existing detail files in R2 and delete any that are no longer referenced. Alternatively, use R2 lifecycle rules with TTL-based expiration.

### 12. Confirm no new npm dependencies needed for viewer streams (Cross-cutting)

**Priority**: Low
**Stream**: Cross-cutting (B, C, D, E)

The file manifest lists 30 new files and 14 modified files but does not mention any changes to `viewer/package.json`. The viewer streams appear to use only existing dependencies (React, Zustand, React Flow), which is ideal. This should be explicitly confirmed in the plan to avoid surprises during implementation.

---

## Items Validated (No Changes Needed)

These aspects of the plan were reviewed and found sound:

- **Tiered dependency graph** enabling 6-agent parallelism at Tier 1 is well-designed. The non-overlapping App.tsx touch points for Streams C, D, and E are credible based on the line references provided.
- **Backward compatibility** strategy (all new fields optional, `live-config.json` detection for feature activation, optional chaining throughout) is correct.
- **Free tier math** checks out. GitHub mode is genuinely $0. Cloudflare mode stays well within free tier limits at projected usage levels.
- **Incremental analyzer pragmatism** (Stream G runs full scan but adds diff metadata, with true incrementality deferred to Stream K) is the right approach. Ship the infrastructure first, optimize later.
- **Tree-sitter hybrid approach** (AST for symbol extraction, regex for framework/port detection) is pragmatic. The fallback-to-regex design means this can never make things worse.
- **Circuit breaker + adaptive polling + visibility control** is a solid resilience pattern for the viewer.
- **10ms Worker CPU constraint** is well understood, with all heavy compute correctly staying in GitHub Actions.
- **Status overlay merge design** (client-side merge via `applyStatusOverlay`) avoids server-side complexity.
- **The `collect-ci-status.py` using stdlib** (`urllib.request`) instead of httpx is the right call for CI scripts.

---

## Summary

12 actionable recommendations, 0 fundamental architecture concerns. The plan is ready for implementation with the above refinements. The highest-priority items to address before starting are: SettingsTab read-only behavior in GitHub mode (#1), circuit breaker self-healing (#2), gh-pages deployment race condition (#5), and replacing the third-party deployment action (#4).
