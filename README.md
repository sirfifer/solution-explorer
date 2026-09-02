<p align="center">
  <img src="docs/screenshots/architecture-overview.png" alt="SysCorpus architecture visualization" width="800">
</p>

<h1 align="center">SysCorpus</h1>

<p align="center">
  <strong>Interactive architecture visualization for any codebase</strong>
</p>

<p align="center">
  <a href="https://github.com/sirfifer/solution-explorer/actions/workflows/architecture-viz.yml"><img src="https://github.com/sirfifer/solution-explorer/actions/workflows/architecture-viz.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm--Noncommercial--1.0.0-blue.svg" alt="PolyForm Noncommercial 1.0.0 License"></a>
  <a href="https://github.com/sirfifer/solution-explorer/releases"><img src="https://img.shields.io/github/v/release/sirfifer/solution-explorer" alt="Release"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/node-20%2B-green" alt="Node 20+">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#screenshots">Screenshots</a> &middot;
  <a href="#how-it-works">How It Works</a> &middot;
  <a href="#deployment-options">Deploy</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

SysCorpus is a static analysis and comprehension system that maps codebases into evidence-linked components, relationships, metrics, findings, and human- and machine-readable views. It supports solutions that span multiple repositories and works with many languages.

## Screenshots

### Architecture Overview

The main graph view shows all components in your codebase as interactive cards. Each card displays the component type, framework, language, file count, and key metrics. Arrows between components indicate relationships like imports, HTTP connections, and Docker links.

<p align="center">
  <img src="docs/screenshots/architecture-overview.png" alt="Architecture overview showing components and relationships" width="800">
</p>

### Component Detail Panel

Click any component to open the detail panel on the right. It shows files, lines of code, symbols, documented symbols with descriptions, external services, tech stack tags, and a button to drill deeper into the component's internals.

<p align="center">
  <img src="docs/screenshots/detail-panel.png" alt="Detail panel showing component metadata, symbols, and metrics" width="800">
</p>

### Drill-Down View

Double-click a component to drill into it and see its internal structure. Breadcrumbs at the top let you navigate back. Each sub-component is rendered as its own card, showing the hierarchical architecture of your codebase.

<p align="center">
  <img src="docs/screenshots/drill-down.png" alt="Drill-down view showing internal component structure with breadcrumbs" width="800">
</p>

## Quick Start

### One command (recommended)

```bash
npx solution-explorer /path/to/your/repo
```

This analyzes your codebase, builds an interactive architecture visualization, and opens it in your browser. No cloning, no setup.

To export a static site you can host anywhere:

```bash
npx solution-explorer --out ./docs/architecture /path/to/your/repo
```

### Set up automated updates

Run the interactive setup wizard in your project directory:

```bash
npx solution-explorer init
```

This creates a GitHub Actions workflow and config file. Every push to main regenerates and deploys your architecture visualization automatically.

For live monitoring with CI status overlays and version history:

```bash
npx solution-explorer init --live
```

### Using the GitHub Action directly

If you prefer to write the workflow yourself:

```yaml
name: Architecture Visualization
on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  visualize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: sirfifer/solution-explorer@main
```

See [Deployment Options](#deployment-options) for Cloudflare Pages, GitHub Pages, and other hosting.

### Running from source

```bash
git clone https://github.com/sirfifer/solution-explorer.git
cd solution-explorer
bash build.sh /path/to/your/repo
# Output: viewer/dist/ (deploy anywhere)
```

### Requirements

- **Python 3.10+** (for code analysis, no pip install needed)
- **Node.js 20+** (for the CLI and viewer)

Optional Python dependencies for advanced features:

```bash
pip install -e ".[treesitter]"   # AST-based parsing (7 languages)
pip install -e ".[incremental]"  # Git-based incremental analysis
pip install -e ".[models]"       # Pydantic validation (--validate)
pip install -e ".[live]"         # Live monitoring data generation
pip install -e ".[all]"          # Everything above
```

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Your Codebase  │────>│  analyzer/        │────>│  architecture.json  │
│                 │     │  (Python)         │     │                     │
└─────────────────┘     └──────────────────┘     └──────────┬──────────┘
                                                            │
                                                            v
                                                 ┌─────────────────────┐
                                                 │  React Viewer       │
                                                 │  (interactive graph)│
                                                 └─────────────────────┘
```

1. **Python Analyzer** (`analyzer/` package) walks the codebase
2. Detects components via marker files (package.json, Cargo.toml, Info.plist, Dockerfile, etc.)
3. Parses source files to extract symbols, imports, and API patterns
4. Detects inter-component relationships (imports, HTTP/port references, protocols)
5. Outputs `architecture.json` with the full hierarchical model
6. **React Viewer** renders the data as an interactive graph using React Flow and ELK layout

### Supported Languages

| Tier | Languages | What's Extracted |
|------|-----------|-----------------|
| **Full parsing** | Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby, Java, C#, C/C++ | Components, symbols, relationships, frameworks, API endpoints |
| **Detection + metrics** | Kotlin, Dart, Vue, Svelte, HTML/CSS, SQL, Shell | File counts, line counts, size, language breakdown |

### What It Detects

| Category | Details |
|----------|---------|
| **Components** | Via marker files: package.json, Cargo.toml, pyproject.toml, go.mod, Info.plist, Dockerfile, and more |
| **Symbols** | Classes, structs, enums, protocols/traits/interfaces, functions, React components |
| **Relationships** | Import dependencies, port-based HTTP connections, Docker Compose links, URL patterns |
| **Metrics** | File counts, line counts, size, language breakdown per component |
| **Frameworks** | SwiftUI, UIKit, React, Next.js, Flask, Django, Axum, Express, Vue, Rails, Sinatra, and more |
| **Documentation** | README, CLAUDE.md, CHANGELOG, API endpoints, env vars, architectural patterns |
| **Cloud Services** | AWS, Firebase, Supabase, and other external service references |
| **UI Actions** | Buttons, tap/long-press gestures, toolbar items, context menus, swipe actions (Swift and TypeScript) |
| **SwiftUI Flows** | TabView tabs, NavigationLink targets, sheet/fullScreenCover destinations, embedded view composition |

## Viewer Features

The comprehension-first **Overview is the default interface**. It establishes the system portrait, offers guided questions, and opens focused technical paths without requiring the reader to understand the stack first. **Workbench** is the current full technical interface for direct graph, lens, source, evidence, and review work. Both apertures read the same projection and route state; see [viewer/README.md](viewer/README.md).

- **Hierarchical drill-down**: Click to see details, double-click to drill into sub-components
- **Breadcrumb navigation**: Always know where you are, click to jump back
- **Graph and tree views**: An interactive React Flow diagram plus a collapsible component tree sidebar, with a tabbed detail panel for the selected component
- **Fuzzy search**: Cmd/Ctrl+K to search across components, files, symbols, and markdown documentation content
- **Detail panel**: Tabbed view with overview, files, symbols, relationships, and AI insights
- **Code preview**: Inline syntax-highlighted code for every symbol
- **Relationship visualization**: Arrows show dependencies, HTTP connections, and AI-discovered relationships
- **Tree sidebar**: Collapsible component tree for quick navigation
- **Source linking**: Clickable links from symbols and files to their GitHub source code
- **URL deep linking**: Shareable URLs that encode selected component, tab, and drill-down state, plus inbound `?file=&line=` links that drill straight to the owning component and select the symbol at that line
- **Review mode**: Add architectural annotations to components, then view a summary of all feedback
- **Architecture changelog**: Track component additions, removals, and modifications over time
- **AI enhancements**: Role badges, criticality indicators, help text tooltips, and data flow descriptions (when AI data is present)
- **Live monitoring**: CI status overlay on components, admin dashboard with version history and activity log
- **Dark/light mode**: Toggle with one click, persisted in localStorage
- **Mobile-friendly**: Touch gestures, bottom sheet panels, responsive layout
- **Multi-repo grouping**: Repository-level nodes when visualizing multi-repo solutions
- **Split mode support**: Lazy-loads component details on demand for large projects

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Cmd/Ctrl + K | Open search |
| Escape | Close search/panels |
| Arrow keys | Navigate search results |
| Enter | Select search result |

## Multi-Repo Solutions

For solutions that span multiple repositories, create a `solution-explorer.json` config file:

```json
{
  "solution": "My Platform",
  "description": "Backend services and mobile client",
  "repositories": [
    { "name": "backend", "path": "." },
    {
      "name": "android-client",
      "url": "https://github.com/your-org/android-client",
      "ref": "main"
    }
  ],
  "cross_repo_relationships": [
    {
      "source_repo": "android-client",
      "target_repo": "backend",
      "type": "http",
      "label": "REST API"
    }
  ]
}
```

See [solution-explorer.json.example](solution-explorer.json.example) for a complete template.

### Config Reference

**repositories** (required): List of repos to analyze.
- `name`: Display name for the repository
- `path`: Local filesystem path (relative to the config file). Use `"."` for the current repo.
- `url`: Git URL to clone (alternative to `path`). Supports HTTPS URLs.
- `ref`: Branch or tag to clone (default: HEAD)

For private repos, set the `GITHUB_TOKEN` environment variable.

**cross_repo_relationships** (optional): Explicit connections between repos that the analyzer cannot detect automatically (since repos are analyzed independently).
- `source_repo` / `target_repo`: Repository names from the `repositories` list
- `type`: Relationship type (`http`, `grpc`, `websocket`, `import`, `database`)
- `label`: Human-readable description

### Multi-Repo with the GitHub Action

```yaml
- uses: sirfifer/solution-explorer@main
  with:
    config: solution-explorer.json
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Multi-Repo Locally

```bash
python3 analyze.py --config solution-explorer.json -o viewer/public/architecture.json
cd viewer && npm install && npm run dev
```

## Deployment Options

The viewer builds to a static site (`viewer/dist/`). Deploy it to any static host.

### Cloudflare Pages

Using the GitHub Action:

```yaml
- uses: sirfifer/solution-explorer@main
  with:
    deploy-to: cloudflare
    cloudflare-api-token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    cloudflare-account-id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
    cloudflare-project-name: my-architecture
```

**Setup:**
1. In the Cloudflare dashboard, go to Workers & Pages and create a new Pages project
2. Choose "Direct Upload" (the Action handles the upload)
3. Create an API token at Account > API Tokens with the "Cloudflare Pages: Edit" permission
4. Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as repository secrets
5. Optionally set `CLOUDFLARE_PROJECT_NAME` as a repository variable

To use a custom domain, add it in the Cloudflare Pages project settings under "Custom domains."

Using Cloudflare's git integration directly:
- **Build command**: `bash build.sh`
- **Build output directory**: `viewer/dist`
- **Environment variables**: `NODE_VERSION=22`, `PYTHON_VERSION=3.12`

### GitHub Pages

```yaml
- uses: sirfifer/solution-explorer@main
  with:
    deploy-to: github-pages
```

Then add a separate deploy job:

```yaml
deploy:
  needs: visualize
  runs-on: ubuntu-latest
  permissions:
    pages: write
    id-token: write
  environment:
    name: github-pages
  steps:
    - uses: actions/deploy-pages@v4
```

### Vercel / Netlify

Point your project at the repo with:
- **Build command**: `bash build.sh`
- **Output directory**: `viewer/dist`

### Self-Hosted / S3

Run `bash build.sh` and copy `viewer/dist/` to your server or bucket.

## GitHub Action Reference

```yaml
- uses: sirfifer/solution-explorer@main
  with:
    # Single-repo: path to analyze (default: ".")
    path: '.'

    # Multi-repo: path to config file
    config: 'solution-explorer.json'

    # Where to deploy: cloudflare, github-pages, or artifact-only (default)
    deploy-to: 'artifact-only'

    # Cloudflare settings (required when deploy-to is cloudflare)
    cloudflare-api-token: ''
    cloudflare-account-id: ''
    cloudflare-project-name: 'solution-explorer'

    # For cloning private repos in multi-repo mode
    github-token: ''

    # Enable live monitoring data generation
    live-monitor: 'false'

    # Version override (defaults to the action ref tag)
    version: ''
```

## CLI Options

```
python3 analyze.py [path] [options]

Output:
  -o, --output PATH       Output file (default: architecture.json)
  --split                 Split files for lazy loading (manifest.json + per-component details)
  --compact               Compact JSON (no indentation)
  --pretty                Pretty-print JSON (default)

Analysis:
  --config PATH           Multi-repo config file (solution-explorer.json)
  --engine {v1,v2}        Analysis engine (default: v2). See "Analysis Engine" below.
  --store PATH            v2 only: persistent fact-store database used as the
                          incremental baseline (default: <root>/.solution-explorer/index.db)
  --max-file-size BYTES   Skip files larger than N bytes (default: 500KB)
  --max-symbols N         v1 only: limit symbols (default: 5000 single-file, unlimited split; 0=unlimited)
  --preview-lines N       Lines per code preview (default: 5)
  --validate              Validate output against data model (requires pydantic)

Incremental:
  --incremental           Only rescan changed files and their importers
  --base-sha SHA          Base commit for diff (default: previous HEAD)
  --head-sha SHA          Head commit for diff (default: HEAD)
  --baseline PATH         Previous architecture.json to merge into
```

## Analysis Engine

The default engine is **v2**, an extract, derive, project pipeline built around a
persistent fact store:

- **Extraction** parses each file once and records its symbols and signals in the store, keyed by content hash so unchanged files are skipped on the next run.
- **Derivation** builds components, relationships, and metrics from the store without re-reading source.
- **Projection** writes the same `architecture.json` (or split `manifest.json` plus detail files) the viewer already renders.

Two properties come from this design:

- **Coverage ledger.** Every file under the root is accounted for exactly once: parsed, skipped for a stated reason, or inside a pruned directory recorded as a single row. Split output writes a `coverage.json` the viewer surfaces as a coverage badge, so a silent gap is not possible. There is no symbol cap in v2.
- **Incremental by construction.** The fact store is the baseline. A warm run re-parses only the files whose content changed, so `--incremental`, `--base-sha`, `--head-sha`, and `--baseline` are accepted as compatibility no-ops.

On a private 4,936,720-line validation corpus, a cold analysis took 136.5 seconds and produced a complete coverage ledger. The corpus identity is intentionally unpublished until its map is ready.

The legacy **v1** single-pass scanner is still available with `--engine v1` for rollback. It is scheduled for removal at a later gate. Rollback is a flag flip; nothing else changes.

## MCP Server (for AI agents)

The v2 fact store doubles as a query surface for AI coding agents. `solution-explorer-mcp` is an [MCP](https://modelcontextprotocol.io) server that answers architectural questions directly from the store, so an agent stops re-reading whole files. It ships in the same package (`analyzer.mcp`), speaks the MCP stdio transport with no extra dependency, and only reads the store: no writes, no model calls at query time.

Every answer is compact structured text (pass `json: true` on any tool for a machine-readable payload), and every fact carries its evidence (`file:line`), its confidence tier (`certain` for parse facts, `inferred` for heuristics, `ai` for AI-discovered), and a staleness marker on any AI content whose code has changed since it was written.

### Build a store, then start the server

```bash
# 1. Build (or refresh) the fact store for a repo
solution-explorer /path/to/repo --engine v2 --split --store /path/to/repo/.solution-explorer/index.db

# 2. Serve it over stdio (agents launch this for you; run it by hand only to smoke-test)
solution-explorer-mcp --store /path/to/repo/.solution-explorer/index.db
```

A missing store is a clean error, not a crash: the server exits with a message telling you to build one first.

### Register with Claude Code

```bash
claude mcp add solution-explorer -- solution-explorer-mcp --store /path/to/repo/.solution-explorer/index.db
```

### Register with any MCP client

Add this to the client's MCP config (for example Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "solution-explorer": {
      "command": "solution-explorer-mcp",
      "args": ["--store", "/path/to/repo/.solution-explorer/index.db"]
    }
  }
}
```

If `solution-explorer-mcp` is not on the client's `PATH`, use `"command": "python"` with `"args": ["-m", "analyzer.mcp", "--store", "..."]` instead.

### The nine tools

| Tool | Answers |
|---|---|
| `se_overview` | What is this system? Component counts and roles, capability counts, entity/rule/concern/finding counts, coverage, enrichment freshness, AI narrative. |
| `se_search` | Where is the thing named or described like X? Ranked full-text search over names, paths, docs, and AI help text. |
| `se_component` | The full card for one component: role, files, capabilities, entities touched, rules, edges in/out with evidence and verdicts, enrichment, activity. |
| `se_symbol` | One symbol: signature, doc, preview, `file:line`, containing component, and enclosing parent chain. |
| `se_refs` | Who uses this and what does it use? Importers and importees, at component granularity, with confidence. |
| `se_impact` | What breaks if this changes? The transitive blast radius, ranked nearest-first, with the per-hop evidence chain. |
| `se_coverage` | The coverage ledger: the disposition summary, or the file rows for one disposition. |
| `se_rules` | The business and validation rules, filterable by component, entity, or kind, with plain-language names when enrichment provides them. |
| `se_findings` | Ranked correlations (duplication, orphans, inconsistencies, intent violations) with verification status always shown and unverified findings marked. |

List responses are bounded: each takes a `limit` and appends an explicit "N more" notice rather than truncating silently.

## AI Enhancement

SysCorpus supports optional AI-powered enhancement of architecture data. The `/ai-assist` Claude Code skill analyzes source files and enriches the architecture JSON with:

- **Component descriptions**: Contextual help text, architectural role classification, criticality ratings
- **Relationship annotations**: Data flow descriptions, importance ratings, AI-discovered connections
- **Architecture summary**: High-level system description and data flow narrative

All AI data lives under optional `ai_enhance` keys in the JSON. The viewer renders this data when present (role badges, criticality dots, help tooltips, an AI Insights tab) and works identically without it.

## Tree-sitter Parsers

Each language parser has an optional tree-sitter upgrade that provides more accurate AST-based extraction. Tree-sitter parsers are used automatically when the dependencies are installed:

```bash
pip install -e ".[treesitter]"
```

If tree-sitter is not available, the analyzer falls back to regex parsers silently. No configuration needed.

## Live Monitoring

When enabled, SysCorpus can continuously update architecture data as the codebase changes:

- **Incremental analysis** in CI rescans only changed files and their importers
- **CI status collection** overlays build pass/fail indicators on components
- **Version history** tracks architecture changes over time
- **Admin dashboard** provides repo monitoring, activity logs, and version comparisons

Two backend modes are supported:

- **GitHub Pages** (free): Stores live data as static files on GitHub Pages, polled every 30 seconds
- **Cloudflare** (optional): Uses Workers + D1 + R2 for lower-latency updates (15-second polling)

Enable in the GitHub Action with `live-monitor: 'true'`. See [Live Monitoring Status](docs/live-architecture-status.md) for configuration details.

## Architecture Data Format

<details>
<summary>Click to expand the full schema</summary>

```json
{
  "name": "string",
  "description": "string",
  "repository": "string",
  "generated_at": "ISO 8601 timestamp",
  "repositories": [
    { "name": "string", "repository": "string" }
  ],
  "components": [
    {
      "id": "string",
      "name": "string",
      "type": "ios_app | web_client | api_server | service | library | ...",
      "path": "string",
      "language": "string",
      "framework": "string",
      "port": "number | null",
      "children": ["... nested components"],
      "files": ["... file paths"],
      "metrics": {
        "files": "number",
        "lines": "number",
        "size_bytes": "number",
        "symbols": "number",
        "languages": { "lang": "number of files" }
      },
      "docs": {
        "readme": "string | null",
        "purpose": "string | null",
        "patterns": ["string"],
        "tech_stack": ["string"],
        "api_endpoints": ["string"],
        "env_vars": ["string"]
      },
      "actions": [
        {
          "label": "string",
          "action_type": "button | tap_gesture | toolbar_item | context_menu | ...",
          "handler": "string | null",
          "file": "string",
          "line": "number",
          "target_view": "string | null"
        }
      ]
    }
  ],
  "relationships": [
    {
      "source": "component_id",
      "target": "component_id",
      "type": "import | http | docker | grpc | websocket",
      "label": "string",
      "protocol": "string | null",
      "port": "number | null"
    }
  ],
  "symbols": [
    {
      "id": "string",
      "name": "string",
      "kind": "class | struct | enum | protocol | function | component",
      "file": "string",
      "line": "number",
      "end_line": "number",
      "code_preview": "string",
      "visibility": "public | internal | private"
    }
  ],
  "files": [
    {
      "path": "string",
      "language": "string",
      "lines": "number",
      "size_bytes": "number",
      "symbols": "number",
      "imports": ["string"]
    }
  ],
  "stats": {
    "total_files": "number",
    "total_lines": "number",
    "total_symbols": "number",
    "total_symbols_detected": "number (optional; pre-truncation count when single-file mode drops symbols, equals total_symbols otherwise)"
  },
  "ai_enhance": {
    "summary": "string (optional, from AI enhancement)",
    "data_flow_narrative": "string (optional)",
    "component_groups": ["..."]
  },
  "live_status": {
    "component_statuses": {},
    "monitored_branch": "string",
    "last_commit_sha": "string"
  }
}
```

</details>

### Split Mode Output

When using `--split`, the analyzer produces a directory instead of a single file:

```
architecture/
├── manifest.json                    # Component tree, relationships, stats (~20-100 KB)
└── data/
    ├── detail-component-a.json      # Symbols and files for component A
    ├── detail-component-b.json      # Symbols and files for component B
    └── ...
```

The manifest contains everything needed to render the graph: component hierarchy, relationships, metrics, and AI enhancements. Symbols and files are loaded on demand when a user opens a component's detail panel.

The viewer automatically detects split mode (tries `manifest.json` first, falls back to `architecture.json`).

## Local Development

For contributing to solution-explorer itself:

```bash
git clone https://github.com/sirfifer/solution-explorer.git
cd solution-explorer

# Install dev dependencies
pip install -e ".[dev]"

# Run Python tests with coverage
python3 -m pytest tests/ -v --cov=analyzer

# Run Python linter
ruff check analyzer/ tests/

# Analyze this repo as a test
python3 analyze.py . -o viewer/public/architecture.json

# Start the viewer in dev mode
cd viewer && npm ci && npm run dev

# Run TypeScript tests and linting
npm test
npm run lint
npx tsc -b
```

> **Note:** `analyze.py` is a thin wrapper around the `analyzer/` package. See the `analyzer/` directory for the full implementation.

## Project Structure

```
solution-explorer/
├── analyze.py              # Python CLI entry point (thin wrapper)
├── analyzer/               # Core analysis package
│   ├── cli.py              # Argument parsing, split/single-file output
│   ├── models.py           # Dataclasses: Component, Symbol, Relationship, etc.
│   ├── scanner.py          # ArchitectureScanner (component discovery, metrics, docs)
│   ├── action_detector.py  # UI action detection (buttons, gestures, menus)
│   ├── incremental.py      # Incremental analysis engine (selective rescan)
│   ├── swiftui_flow.py     # SwiftUI navigation/tab flow detection
│   ├── multi_repo.py       # Multi-repo orchestration
│   ├── config_parsers.py   # Config file parsers (package.json, Cargo.toml, etc.)
│   ├── constants.py        # Skip dirs, language maps, component markers
│   ├── utils.py            # Shared helpers
│   └── parsers/            # Per-language source parsers
│       ├── base.py         # BaseParser interface
│       ├── swift.py        # Swift/SwiftUI (regex)
│       ├── swift_ts.py     # Swift/SwiftUI (tree-sitter)
│       ├── python_lang.py  # Python (regex)
│       ├── python_ts.py    # Python (tree-sitter)
│       ├── typescript.py   # TypeScript/JavaScript (regex)
│       ├── typescript_ts.py # TypeScript/JavaScript (tree-sitter)
│       ├── go.py           # Go (regex)
│       ├── go_ts.py        # Go (tree-sitter)
│       ├── rust.py         # Rust (regex)
│       ├── rust_ts.py      # Rust (tree-sitter)
│       ├── ruby.py         # Ruby (regex)
│       ├── ruby_ts.py      # Ruby (tree-sitter)
│       └── tree_sitter_base.py  # Tree-sitter base class
├── packages/cli/           # npm CLI package (npx solution-explorer)
│   ├── src/commands/       # generate, serve, init commands
│   ├── src/lib/            # Python detection, viewer management
│   └── src/templates/      # Workflow and config templates
├── infrastructure/         # Optional backend infrastructure
│   └── cloudflare/         # Cloudflare Worker for live monitoring
├── scripts/                # CI and AI enhancement helper scripts
├── tests/                  # Python test suite
├── action.yml              # Reusable GitHub Action definition
├── pyproject.toml          # Python project configuration
└── viewer/                 # React/TypeScript frontend
    ├── src/
    │   ├── components/     # React components (graph, nodes, panels, search)
    │   │   └── admin/      # Admin dashboard tabs (activity, health, history)
    │   ├── hooks/          # useLiveMonitor, useAdminData, useBottomSheet
    │   ├── utils/          # Layout, search, source links, URL state, prompts
    │   ├── store.ts        # Zustand state management (drill-down, lazy loading)
    │   └── types.ts        # TypeScript type definitions
    ├── vite.config.ts      # Build configuration
    └── vitest.config.ts    # Test configuration
```

## Documentation

- [Project Overview](PROJECT-OVERVIEW.md): Vision, user experience, and system architecture
- [Architecture](docs/architecture.md): Technical architecture and design decisions
- [Architectural Assessment](docs/architectural-assessment.md): Evolution plan and industry research
- [Analyzer Package](docs/analyzer-package.md): Analyzer module structure and extension guide
- [Live Monitoring Status](docs/live-architecture-status.md): Live architecture monitoring status and configuration
- [DPEA Pattern](docs/research/scalable-ai-enhancement-dpea-pattern.md): Scalable AI enhancement pipeline design
- [Deployments](DEPLOYMENTS.md): Installation tracking and redeployment guide

## License

[PolyForm Noncommercial License 1.0.0](LICENSE) (SPDX: `PolyForm-Noncommercial-1.0.0`) &copy; 2025-2026 Richard Amerman (sirfifer).

In plain terms: you can use, copy, modify, and redistribute this software for any noncommercial purpose. Personal, hobby, study, and research use is free, and so is use by charities, schools, public research bodies, public safety and health organizations, environmental organizations, and government institutions.

**Commercial use requires a written license.** That includes a company running it internally on its own code, consultancies using it on client work, and anyone embedding it in something they sell. Evaluation and proof of concept access is granted routinely, and free grants for open source and public benefit work are common, but each one is granted explicitly rather than assumed. See [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) to ask, [ADDITIONAL-PERMISSIONS.md](ADDITIONAL-PERMISSIONS.md) for what has been granted, and [docs/commercial/GRANT-POLICY.md](docs/commercial/GRANT-POLICY.md) for the criteria.

This is a source-available license, not an OSI open source license, and we label it honestly as such. Earlier versions of this project carried different terms and keep them; see [NOTICE](NOTICE).
