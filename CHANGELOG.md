# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **AI enhancement pipeline**: Optional enrichment layer (`/ai-assist` skill) that runs alongside the analyzer to add component descriptions, architectural roles, criticality levels, help text, and richer relationship context. All AI data lives under an optional `ai_enhance` key, so the viewer renders identically against non-enhanced data. Includes `scripts/merge-ai-enhancements.py` so CI can merge enhancements from a committed baseline during redeploy.
- **Live monitoring**: Opt-in live data channel with CI status overlays, version history, and an admin dashboard. Backed by either GitHub Pages (30s polling) or Cloudflare Workers + D1 + R2 (15s polling). Adaptive polling hook with circuit breaker and visibility control.
- **UI Actions detection**: `action_detector.py` detects user-triggered actions in Swift and TypeScript (buttons, taps, toolbar items, context menus) and surfaces them in component details with file and line references.
- **Source linking**: Components, files, and symbols deep-link to source locations where available.
- **URL deep linking**: Drill level and selected component are encoded in URL query parameters (`?component=`, `?drill=`), supporting shareable and bookmarkable views with browser back/forward.
- **ErrorBoundary**: React error boundary wraps the viewer app, converting any render crash into a visible, recoverable error panel with a "Reset navigation" button that clears deep-link URL params.
- **Architecture changelog in-viewer**: Changes across runs surfaced as an in-app changelog panel with per-entry read tracking (high-water mark + sparse set) persisted in localStorage.
- **Incremental re-analysis**: Git-diff-based selective re-analysis of changed components only.
- **Tree-sitter parsers**: Added tree-sitter parsers for all 6 supported languages with graceful fallback to regex parsers.
- **Three-tier CLI**: `npx solution-explorer` now supports standalone run, `init` for automated setup, and `init --live` for live monitoring.
- **Mobile UI**: Bottom sheet panel, safe area support, swipe gestures.
- **Review mode with annotations**: Attach notes to components, files, symbols, and relationships.
- **Automated downstream deployment**: Push to `sirfifer/solution-explorer@main` automatically dispatches redeploy workflows for all tracked installations (see `DEPLOYMENTS.md`).
- **Release automation**: PyPI + npm publishing workflow.
- **Cloudflare Workers backend**: Worker + D1 + R2 infrastructure for enhanced live monitoring, plus a resource usage dashboard.

### Changed

- **Split-mode output (`--split`)** is now the preferred path when emitting to CI. Architecture data is split into `manifest.json` plus per-component `detail-*.json` files; the viewer lazy-loads details on demand.
- **Analysis output paths** adjusted to support split-mode and AI enhancement merge flow.

### Fixed

- Viewer renders an empty-state instead of a blank view when component filtering hides everything; hero-filter fallback restores visibility if filters remove all components at a drill level.
- Cloudflare deploy step skips cleanly when no project name is configured (does not fail the workflow).
- Various `ruff` lint fixes in analyzer tests.
- Incremental analyzer uses `to_dict()` instead of `asdict()` to emit correctly serialized output.

## [1.1.0] - 2025-02-17

### Changed

- **Refactored analyzer into modular package**: Split the monolithic `analyze.py` (4,525 lines) into the `analyzer/` package with 17 modules. `analyze.py` remains as a backward-compatible CLI wrapper. Parsers, models, utilities, and config parsers each have their own module.
- **Symbol cap now configurable**: Default is 5,000 in single-file mode, unlimited in split mode. Use `--max-symbols` to override.

### Added

- **Split JSON output** (`--split` flag): Produces a `manifest.json` with the component tree, relationships, and stats, plus per-component `detail-{id}.json` files with symbols and file metadata. Reduces initial page load from megabytes to ~20-100 KB.
- **Lazy loading in viewer**: When using split output, the viewer loads component details on demand. Search indexes progressively as components are explored.
- **Comprehensive test suite**: 370 tests covering 81% of the analyzer package (up from 43 tests at ~10% coverage). New test files: `test_utils.py`, `test_cli.py`, `test_parsers_extra.py`, `test_scanner_deep.py`.
- **Module docstrings**: All analyzer modules now have descriptive module-level and class-level docstrings.

### Fixed

- Viewer gracefully handles both split and monolithic JSON formats with automatic detection and fallback.

## [1.0.0] - 2025-01-01

### Added

- Architecture analyzer with support for Swift, Python, Rust, TypeScript/JavaScript, and Go
- Detection and metrics for Java, Kotlin, Ruby, C/C++, C#, Dart, Vue, Svelte, HTML/CSS, SQL, Shell
- Interactive React viewer with graph visualization using React Flow and ELK layout
- Hierarchical drill-down navigation with breadcrumbs
- Fuzzy search across components, files, and symbols (Cmd/Ctrl+K)
- Code preview with syntax highlighting
- Relationship visualization including imports, HTTP connections, and Docker links
- Dark and light mode support
- Mobile-friendly responsive layout with touch gestures
- Multi-repository support with cross-repo relationships
- GitHub Action for easy CI/CD integration
- Deployment support for Cloudflare Pages, GitHub Pages, Vercel, and Netlify
- SwiftUI flow detection for TabView, NavigationLink, sheets, and fullScreenCover
- Framework and API endpoint detection
- External cloud service detection
- Session and localStorage persistence for UI state
