> **Historical snapshot (written 2026-02-22, banner added 2026-08-20).** This document describes SysCorpus's architecture as it existed then and is kept for its research and reasoning, not as a description of the current codebase. Since it was written, tree-sitter parsers replaced the six regex-only parsers it describes, the analyzer was rebuilt around the default v2 extract, derive, project index engine with a coverage ledger, and an MCP server (`solution-explorer-mcp`) shipped for AI agents. None of that exists in the description below. Treat this document as the state on 2026-02-22. See CHANGELOG.md and PROJECT-OVERVIEW.md for what ships today.

# SysCorpus: Technical Architecture

This document describes the internal architecture of SysCorpus, covering the analyzer, viewer, data model, CI/CD pipelines, and infrastructure.

## System Overview

SysCorpus has three main layers:

```
┌──────────────────────────────────────────────────────────┐
│                    GitHub Actions CI                      │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐    │
│  │ ci.yml   │   │ arch-    │   │ live-monitor.yml  │    │
│  │ (gate)   │   │ viz.yml  │   │ (incremental)     │    │
│  └──────────┘   └────┬─────┘   └────────┬──────────┘    │
└───────────────────────┼─────────────────┼────────────────┘
                        │                 │
                        v                 v
┌───────────────────────────────┐  ┌─────────────────────┐
│  Python Analyzer              │  │  Live Data Pipeline  │
│  ┌─────────┐ ┌────────────┐  │  │  version.json        │
│  │ Scanner │ │ Parsers    │  │  │  live-config.json     │
│  │         │ │ (7 langs)  │  │  │  ci-status.json       │
│  └────┬────┘ └────────────┘  │  │  admin-summary.json   │
│       v                      │  └──────────┬────────────┘
│  architecture.json           │             │
│  (or split manifest + data/) │             │
└──────────────┬───────────────┘             │
               │                             │
               v                             v
┌──────────────────────────────────────────────────────────┐
│  Static Hosting (Cloudflare Pages / GitHub Pages)        │
│  ┌──────────────────────────────────────────────────┐    │
│  │  React Viewer (SPA)                              │    │
│  │  ┌────────┐ ┌──────────┐ ┌───────┐ ┌────────┐  │    │
│  │  │ Graph  │ │ Detail   │ │ Tree  │ │ Admin  │  │    │
│  │  │ View   │ │ Panel    │ │ Nav   │ │ Dash   │  │    │
│  │  └────────┘ └──────────┘ └───────┘ └────────┘  │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
               │ (optional, for live monitoring)
               v
┌──────────────────────────────────────────────────────────┐
│  Cloudflare Backend (Optional)                           │
│  Worker (API) + D1 (DB) + R2 (Storage) + KV (Config)    │
└──────────────────────────────────────────────────────────┘
```

## Python Analyzer

### Package Structure

The analyzer lives in the `analyzer/` package. `analyze.py` at the project root is a thin wrapper that re-exports key classes for backward compatibility and calls `main()`.

```
analyzer/
  __init__.py          # Package init
  cli.py               # CLI argument parsing, output formatting, main()
  scanner.py           # ArchitectureScanner: core orchestration
  models.py            # Data model (Architecture, Component, Symbol, etc.)
  constants.py         # SKIP_DIRS, LANGUAGE_MAP, COMPONENT_MARKERS
  config_parsers.py    # Parsers for package.json, Cargo.toml, etc.
  swiftui_flow.py      # SwiftUI navigation flow detection
  multi_repo.py        # Multi-repository orchestration
  incremental.py       # Incremental analysis engine
  utils.py             # Shared utilities
  parsers/
    __init__.py        # Parser registry and factory
    base.py            # BaseParser abstract class
    swift.py           # SwiftParser (regex)
    swift_ts.py        # SwiftTreeSitterParser
    python_lang.py     # PythonParser (regex)
    python_ts.py       # PythonTreeSitterParser
    typescript.py      # TypeScriptParser (regex)
    typescript_ts.py   # TypeScriptTreeSitterParser
    go.py              # GoParser (regex)
    go_ts.py           # GoTreeSitterParser
    rust.py            # RustParser (regex)
    rust_ts.py         # RustTreeSitterParser
    ruby.py            # RubyParser (regex)
    ruby_ts.py         # RubyTreeSitterParser
    tree_sitter_base.py  # Base class for tree-sitter parsers
```

### Core Classes

**ArchitectureScanner** (`scanner.py`): The main orchestrator. Walks a directory tree, identifies components via marker files (package.json, Cargo.toml, Info.plist, Dockerfile, etc.), delegates file parsing to language-specific parsers, collects metrics, and assembles the `Architecture` object.

**BaseParser** (`parsers/base.py`): Abstract interface that all language parsers implement. Key methods:
- `extract_symbols(source, filepath)`: Returns list of `Symbol` objects (classes, functions, structs, etc.)
- `extract_imports(source, filepath)`: Returns list of import strings
- `detect_framework(source)`: Returns framework name if detected (e.g., "SwiftUI", "React", "Flask")

**Language Parsers**: Each language has a regex-based parser and an optional tree-sitter parser. The parser registry in `parsers/__init__.py` automatically upgrades to tree-sitter when the dependencies are available, falling back to regex silently on ImportError.

**SwiftUIFlowDetector** (`swiftui_flow.py`): Specialized analyzer for SwiftUI codebases. Detects:
- TabView tabs and their content views
- NavigationLink, sheet, and fullScreenCover navigation targets
- Embedded view composition (one view instantiating another)
- Uses brace-depth counting for multi-line body extraction
- Per-view-struct scanning prevents cross-view target contamination
- Distance-based BFS assigns screens to their nearest tab

**IncrementalAnalyzer** (`incremental.py`): Compares git revisions to determine which files changed, maps changes to affected components, rescans only those components (plus direct importers), and merges results back into a baseline architecture. Marker file changes (e.g., package.json modifications) trigger a full rescan.

**MultiRepoOrchestrator** (`multi_repo.py`): Reads a `solution-explorer.json` config file, clones or locates each repository, runs ArchitectureScanner on each, and merges results into a single Architecture with repository-level grouping and cross-repo relationships.

### Data Model

Defined in `models.py` using Python dataclasses:

```
Architecture
├── name: str
├── description: str
├── components: list[Component]     # Top-level component tree
├── relationships: list[Relationship]
├── symbols: list[Symbol]           # Flat list (single-file mode)
├── files: list[FileInfo]           # Flat list (single-file mode)
├── stats: dict                     # Aggregate metrics
└── ai_enhance?: dict               # Optional AI data

Component
├── id: str
├── name: str
├── type: str                       # ios_app, web_client, api_server, etc.
├── path: str
├── language: str
├── framework: str
├── children: list[Component]       # Nested sub-components
├── metrics: dict                   # files, lines, size_bytes, languages
├── docs: ComponentDoc              # readme, purpose, patterns, tech_stack
└── ai_enhance?: dict               # Optional AI data

Symbol
├── id: str
├── name: str
├── kind: str                       # class, struct, enum, function, etc.
├── file: str
├── line: int
├── end_line: int
├── code_preview: str
└── visibility: str                 # public, internal, private

Relationship
├── source: str                     # Component ID
├── target: str                     # Component ID
├── type: str                       # import, http, docker, grpc, websocket
├── label: str
└── ai_enhance?: dict               # Optional AI data

FileInfo
├── path: str
├── language: str
├── lines: int
├── size_bytes: int
├── symbols: int
└── imports: list[str]
```

### Output Modes

**Single-file mode** (default): Produces one `architecture.json` containing everything. Suitable for projects under ~2,000 files.

**Split mode** (`--split`): Produces:
- `manifest.json`: Component tree, relationships, stats, AI enhancements. Everything needed to render the graph. Typically 20-100 KB.
- `data/detail-{componentId}.json`: Symbols and file details per component. Loaded on demand when a user opens the detail panel.

The viewer tries `manifest.json` first and falls back to `architecture.json` automatically.

### Dependency Strategy

The core analyzer requires only Python 3.10+ stdlib. Optional dependency groups declared in `pyproject.toml`:

| Group | Dependencies | Features |
|-------|-------------|----------|
| (none) | stdlib only | Core analysis, all 7 regex parsers |
| `models` | pydantic | `--validate` flag |
| `incremental` | gitpython | `--incremental` flag |
| `treesitter` | tree-sitter + 7 language bindings | AST-based parsing |
| `live` | gitpython, httpx, pydantic | Live monitoring data generation |
| `all` | live + treesitter | Everything |
| `dev` | pytest, pytest-cov, ruff | Development and testing |

This zero-dependency core is a deliberate design choice. The analyzer runs in GitHub Actions on any runner without setup steps. The GitHub Action installs only Python and Node, never pip.

## React Viewer

### Tech Stack

| Library | Version | Purpose |
|---------|---------|---------|
| React | 19.1 | UI framework |
| TypeScript | 5.7 | Type safety |
| Vite | 6.3 | Build tool and dev server |
| @xyflow/react | 12.6 | Graph rendering (React Flow) |
| elkjs | 0.9 | Automatic graph layout (ELK algorithm) |
| zustand | 5.0 | State management |
| fuse.js | 7.0 | Fuzzy search |
| Tailwind CSS | 4.1 | Styling |

### Component Architecture

```
App.tsx
├── ArchitectureGraph.tsx      # Main graph view (React Flow + ELK layout)
│   └── ComponentNode.tsx      # Individual node rendering
├── TreeNavigator.tsx          # Left sidebar: hierarchical tree
├── DetailPanel.tsx            # Right panel: component details
│   └── CodePreview.tsx        # Symbol code previews
├── SearchOverlay.tsx          # Global fuzzy search (Cmd+K)
├── HelpSystem.tsx             # Help tooltips
├── ReviewModeButton.tsx       # Review mode toggle
├── ReviewSummary.tsx          # Annotation summary
├── AnnotationInput.tsx        # Review annotation form
├── AdminDashboard.tsx         # Live monitoring admin panel
├── StatusDashboard.tsx        # CI status overlay
├── MarkdownRenderer.tsx       # Markdown content rendering
└── Tooltip.tsx                # Generic tooltip
```

### State Management

The Zustand store (`store.ts`) manages all application state:

**Architecture Data**
- `architecture`: The loaded Architecture object
- `loading`, `error`: Loading states
- `componentDetailCache`: Cache for lazily-loaded component details (split mode)

**Navigation**
- `selectedComponentId`: Currently selected component
- `breadcrumbs`: Navigation stack for drill-down
- `drillLevel`: Current depth in component hierarchy
- `viewMode`: "graph", "tree", or "list"

**Panels**
- `activePanel`: Which sidebar is open (tree, detail, review, or null)
- `detailItem`: Currently displayed detail item

**Search**
- `searchOpen`: Whether search overlay is visible
- `searchQuery`: Current search text

**Theme**
- `darkMode`: Boolean, persisted to localStorage

**Review**
- `reviewMode`: Whether annotation mode is active
- `annotations`: List of architectural annotations
- `annotatingComponentId`: Component being annotated
- `annotatingTarget`: Annotation target type

**Live Monitoring**
- `liveConfig`: Live monitoring configuration
- `liveVersion`: Current data version
- `liveMonitorStatus`: Monitor connection status
- `statusOverlay`: CI status data

**Key Methods**
- `getVisibleComponents()`: Returns components for the current drill level, applying hero-promotion and wrapper-unwrapping logic
- `getComponentRelationships()`: Returns relationships for visible components
- `getComponentFiles(id)`: Returns files belonging to a component
- `getComponentSymbols(id)`: Returns symbols belonging to a component
- `loadComponentDetail(id)`: Fetches and caches detail data for split mode

### Visibility Logic

The viewer uses a multi-level visibility system to keep the graph readable:

1. **Top level**: Shows "Domain 1" (client-facing) and "Domain 2" (server-facing) components
2. **Drill-down**: When entering a component, promotes "hero" children (significant sub-components) while collapsing generic wrappers
3. **Wrapper unwrapping**: Automatically pierces up to 2 levels of structural wrappers (project, repository) to surface meaningful components
4. **Hero types**: Certain component types (ios_app, web_client, api_server, etc.) are always surfaced

### Custom Hooks

**useLiveMonitor** (`hooks/useLiveMonitor.ts`): Polls for live data updates with adaptive intervals:
- 15-30 seconds when active (depends on backend mode)
- 120 seconds when idle
- Pauses when the browser tab is hidden

**useAdminData** (`hooks/useAdminData.ts`): Fetches admin dashboard data including version history, activity logs, and repo status.

### Styling

The viewer uses Tailwind CSS with a custom color system defined in `utils/layout.ts`:
- Component type colors (different hues for iOS apps, web clients, servers, etc.)
- Role badge colors for AI-assigned architectural roles
- Edge styles for different relationship types (import, HTTP, Docker, etc.)
- Dark mode variant for all colors

## CI/CD Pipelines

### ci.yml (Quality Gate)

Runs on every push and pull request. All checks must pass.

| Job | Tool | What It Checks |
|-----|------|---------------|
| Python lint | ruff | Code style and errors in analyzer/, tests/, scripts/ |
| Python test | pytest | Unit tests with coverage reporting |
| TypeScript lint | eslint | Code style in viewer/src/ |
| TypeScript test | vitest | Component and hook tests with coverage |
| Type check | tsc -b | TypeScript compilation |
| Build | npm run build | Viewer builds successfully |

Coverage reports (HTML) are uploaded as artifacts with 14-day retention.

### architecture-viz.yml (Build and Deploy)

Runs on push to main (post-merge). Produces and deploys the architecture visualization.

1. Runs the full CI test suite
2. Executes the analyzer on the target codebase
3. Builds the viewer with the generated data
4. Uploads the built site as an artifact
5. Deploys to Cloudflare Pages (if configured)

Supports pre-built architecture JSON for the AI-enhanced flow: if `architecture.json` already exists in the repo (committed by the `/ai-assist` skill), the analyzer step uses it instead of re-running analysis.

### live-monitor.yml (Live Data)

Runs on push to main, after architecture-viz completes, or on manual dispatch.

1. Restores the previous architecture baseline from cache
2. Runs the analyzer with `--incremental` and `--baseline` flags
3. Collects CI status via `scripts/collect-ci-status.py`
4. Generates `version.json`, `live-config.json`, and admin summary
5. Saves the new baseline to cache for the next run
6. Publishes live data to GitHub Pages and/or Cloudflare R2

## Cloudflare Backend (Optional)

For projects that need lower-latency live updates, SysCorpus includes a Cloudflare Worker backend.

### Infrastructure

| Service | Resource | Purpose |
|---------|----------|---------|
| Workers | `solution-explorer-api` | API endpoints for data ingestion and retrieval |
| D1 | `solution-explorer-db` | Version history, activity logs |
| R2 | `solution-explorer-data` | Architecture data files, CI status |
| KV | `SETTINGS_KV` | Configuration and settings cache |

Configuration is in `infrastructure/cloudflare/worker/wrangler.toml`. Setup script at `infrastructure/cloudflare/setup.sh`.

### Data Flow (Cloudflare Mode)

1. `live-monitor.yml` runs in CI, generates updated architecture and status data
2. Uploads data to R2 bucket
3. Notifies Worker via POST `/ingest` (authenticated with `INGEST_TOKEN`)
4. Worker stores metadata in D1, makes data available via API
5. Viewer polls Worker API every 15 seconds for updates

### Data Flow (GitHub Pages Mode)

1. `live-monitor.yml` runs in CI, generates updated data
2. Publishes data as static files to GitHub Pages (`/.arch-output/live/`)
3. Viewer polls GitHub Pages URL every 30 seconds for `version.json` changes
4. On version change, fetches updated status and architecture data

## Reusable GitHub Action

The `action.yml` at the project root defines a composite GitHub Action that other repositories consume. It handles the full pipeline:

1. Sets up Python 3.12 and Node.js 22
2. Checks out the solution-explorer repository
3. Runs the analyzer (or uses pre-built JSON if present)
4. Builds the viewer
5. Optionally generates live monitoring data
6. Uploads artifact and/or deploys to Cloudflare Pages or GitHub Pages

### Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `path` | `.` | Repository root to analyze (single-repo mode) |
| `config` | (empty) | Path to solution-explorer.json (multi-repo mode) |
| `deploy-to` | `artifact-only` | Deployment target: `cloudflare`, `github-pages`, or `artifact-only` |
| `cloudflare-api-token` | (empty) | Cloudflare API token |
| `cloudflare-account-id` | (empty) | Cloudflare account ID |
| `cloudflare-project-name` | `solution-explorer` | Cloudflare Pages project name |
| `github-token` | (empty) | Token for cloning private repos in multi-repo mode |
| `live-monitor` | `false` | Enable live monitoring data generation |

## AI Enhancement System

The AI enhancement system is decoupled from the core analyzer. It runs as a separate step after analysis.

### Flow

1. Core analyzer produces `architecture.json` (no AI data)
2. The `/ai-assist` Claude Code skill reads the JSON and the actual source files
3. Claude analyzes each component's code and adds `ai_enhance` data
4. Enhanced JSON is written back with all original data preserved
5. On commit and push, the GitHub Action uses the pre-built enhanced JSON

### Data Structure

AI data is always optional and nested under `ai_enhance` keys:

```json
{
  "components": [{
    "id": "...",
    "name": "...",
    "ai_enhance": {
      "help_text": "Manages user authentication...",
      "architectural_role": "orchestrator",
      "data_handled": "User credentials, session tokens",
      "criticality": "critical",
      "criticality_reason": "Central auth failure affects all services"
    }
  }],
  "relationships": [{
    "source": "...",
    "target": "...",
    "ai_enhance": {
      "data_flow_description": "Sends auth tokens for API validation",
      "importance": "critical",
      "ai_discovered": true
    }
  }],
  "ai_enhance": {
    "summary": "A mobile banking platform with...",
    "data_flow_narrative": "User requests flow from the iOS app through...",
    "component_groups": [
      { "name": "Authentication", "component_ids": ["auth-service", "token-store"] }
    ]
  }
}
```

### Viewer Integration

The viewer uses optional chaining throughout (`ai_enhance?.help_text`) so it works identically with or without AI data. When present:

- `ComponentNode.tsx` renders role badges and criticality dots
- The "?" help button shows `ai_enhance.help_text`
- `DetailPanel.tsx` shows an "AI Insights" tab with descriptions, role, and criticality
- `ArchitectureGraph.tsx` styles AI-discovered edges differently
- Architecture summary banner displays the system-level AI description

## Testing

### Python Tests

Location: `tests/` directory. Framework: pytest with pytest-cov.

| Test File | Coverage |
|-----------|----------|
| `test_analyzer.py` | Core analyzer integration tests |
| `test_cli.py` | CLI argument parsing and output |
| `test_models.py` | Data model serialization |
| `test_scanner_deep.py` | Scanner edge cases |
| `test_parsers_extra.py` | Parser-specific tests |
| `test_incremental.py` | Incremental analysis |
| `test_tree_sitter.py` | Tree-sitter parser tests |
| `test_utils.py` | Utility function tests |

Run: `pytest tests/ -v --cov=analyzer`

### Viewer Tests

Location: `viewer/src/__tests__/`. Framework: vitest with @testing-library/react.

| Test File | Coverage |
|-----------|----------|
| `store.test.ts` | Zustand store logic |
| `useLiveMonitor.test.ts` | Live monitoring hook |

Run: `cd viewer && npm test`

## Design Decisions

### Why Python for the Analyzer?

The stdlib-only core means the GitHub Action works on any runner without pip install or build steps. The analyzer runs once in CI, not interactively, so execution speed is less important than correctness, comprehensiveness, and zero-setup deployment. Optional dependencies are available for teams that want advanced features.

### Why React Flow for the Viewer?

The custom node rendering (device frames, role badges, criticality indicators, help buttons) is a key differentiator. React Flow supports this level of customization. The drill-down navigation pattern keeps visible nodes under ~100, well within React Flow's SVG rendering limits. Switching to a Canvas or WebGL renderer (Cytoscape, Sigma.js) would mean rebuilding all the rich node UI.

### Why Static Site Deployment?

Deploying as a static site (Cloudflare Pages, GitHub Pages) eliminates server runtime costs and complexity. The architecture data is generated in CI and served as static JSON files. The optional Cloudflare Worker backend adds live features without changing the core deployment model.

### Why Split JSON Instead of a Database?

Split JSON files on static hosting provide the right balance of simplicity and scalability. Each component's detail loads as a small, cacheable JSON file. No database server needed. The approach scales to large projects (5,000+ files) while remaining deployable to any static host.

### Why Optional Tree-sitter?

Tree-sitter provides more accurate AST parsing but requires native binary dependencies. Making it optional means the core analyzer works everywhere (including constrained CI environments) while teams that need higher accuracy can install the additional dependencies. The fallback to regex parsers is silent and automatic.
