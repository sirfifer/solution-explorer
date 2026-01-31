# Architecture Visualizer

A tool that generates interactive, navigable architecture diagrams from any codebase. It intrinsically inspects source code to extract components, relationships, symbols, and metrics, then renders them as a live, drillable visualization.

## How it Works

1. **Python Analyzer** (`analyze.py`) walks the codebase with zero external dependencies (stdlib only)
2. Detects components via marker files (package.json, Cargo.toml, Info.plist, etc.)
3. Parses source files to extract symbols, imports, and API patterns
4. Detects inter-component relationships (imports, HTTP/port references, protocols)
5. Outputs `architecture.json` with the full hierarchical model
6. **React Viewer** renders the data as an interactive graph with drill-down navigation

## Quick Start

```bash
# 1. Generate architecture data
python3 analyze.py /path/to/your/repo -o viewer/public/architecture.json

# 2. Install viewer dependencies
cd viewer && npm install

# 3. Run the dev server
npm run dev

# Or do it all in one command:
npm run analyze
```

## Analyzer

The analyzer supports: **Swift, Python, Rust, TypeScript/JavaScript, Go** with extensible parser architecture.

### What it Detects

- **Components**: Identified via marker files (package.json, Cargo.toml, pyproject.toml, Info.plist, Dockerfile, etc.)
- **Symbols**: Classes, structs, enums, protocols/traits/interfaces, functions, extensions, React components
- **Imports**: Language-specific import resolution
- **Relationships**: Import-based dependencies, port-based HTTP connections, protocol detection
- **Metrics**: File counts, line counts, size, language breakdown per component
- **Frameworks**: SwiftUI, UIKit, React, Next.js, Flask, Django, Axum, Tokio, Express, Vue, etc.

### CLI Options

```
python3 analyze.py [path] [options]

Options:
  -o, --output        Output JSON path (default: architecture.json)
  --max-file-size     Skip files larger than N bytes (default: 500KB)
  --max-symbols       Limit symbols in output (default: 5000, 0=unlimited)
  --preview-lines     Lines per code preview (default: 5)
  --compact           Compact JSON (no indentation)
```

## Viewer

Built with best-of-breed tech:

- **React 19** + **TypeScript 5** for the UI
- **React Flow v12** (@xyflow/react) for interactive node graphs
- **ELK.js** for automatic graph layout (same engine as VS Code)
- **TailwindCSS v4** for responsive styling
- **Zustand v5** for state management
- **Fuse.js** for fuzzy search

### Features

- **Hierarchical drill-down**: Click a component to see details, double-click to drill into sub-components
- **Breadcrumb navigation**: Always know where you are, click to jump back
- **Fuzzy search**: Cmd/Ctrl+K to search across components, files, and symbols
- **Code preview**: Inline syntax-highlighted code for every symbol
- **Relationship visualization**: Arrows show import dependencies and HTTP connections with port numbers
- **Dark/light mode**: Toggle with one click
- **Mobile-friendly**: Touch gestures on graph, bottom sheet panels, responsive layout
- **Metrics at a glance**: File counts, lines, language breakdown, size

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Cmd/Ctrl + K | Open search |
| Escape | Close search/panels |
| Arrow keys | Navigate search results |
| Enter | Select search result |

## Deployment

### Cloudflare Pages

Point Cloudflare Pages to your repo with:
- **Build command**: `cd tools/arch-visualizer && python3 analyze.py ../.. -o viewer/public/architecture.json --compact && cd viewer && npm install && npm run build`
- **Build output directory**: `tools/arch-visualizer/viewer/dist`
- **Root directory**: `/` (repo root)

The architecture diagram auto-updates on every push.

### GitHub Pages

A workflow at `.github/workflows/architecture-viz.yml` handles this automatically:
- Runs on push to main
- Generates architecture data
- Builds the viewer
- Deploys to GitHub Pages

### GitHub Actions Artifact

Every push also uploads the built visualization as a downloadable artifact.

## Architecture Data Format

The `architecture.json` follows this structure:

```
{
  name, description, repository, generated_at,
  components: [{
    id, name, type, path, language, framework, port,
    children: [...],    // nested components
    files: [...],       // file paths
    metrics: { files, lines, size_bytes, symbols, languages }
  }],
  relationships: [{
    source, target, type, label, protocol, port
  }],
  symbols: [{
    id, name, kind, file, line, end_line, code_preview, visibility
  }],
  files: [{
    path, language, lines, size_bytes, symbols, imports
  }],
  stats: { total_files, total_lines, total_symbols, ... }
}
```

## Adding to Another Project

1. Copy `tools/arch-visualizer/` into your repo
2. Run `python3 analyze.py . -o viewer/public/architecture.json`
3. `cd viewer && npm install && npm run dev`

The analyzer has zero Python dependencies. The viewer needs Node.js 18+.
