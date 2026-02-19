# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
