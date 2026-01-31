# Solution Explorer

Interactive architecture visualization for any codebase. Analyzes source code to extract components, relationships, symbols, and metrics, then renders them as a drillable, searchable diagram. Supports solutions that span multiple repositories.

## Quick Start

### Using the GitHub Action (recommended)

Add this workflow to your repo at `.github/workflows/architecture.yml`:

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
      - uses: sirfifer/solution-explorer@v1
```

This analyzes your repo and uploads the visualization as a downloadable artifact. To deploy it automatically, see [Deployment Options](#deployment-options) below.

### Running Locally

```bash
# 1. Clone solution-explorer
git clone https://github.com/sirfifer/solution-explorer.git
cd solution-explorer

# 2. Analyze your project
python3 analyze.py /path/to/your/repo -o viewer/public/architecture.json

# 3. Start the viewer
cd viewer && npm install && npm run dev
```

Or use the build script to produce a deployable static site:

```bash
bash build.sh /path/to/your/repo
# Output: viewer/dist/ (deploy anywhere)
```

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
- uses: sirfifer/solution-explorer@v1
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
- uses: sirfifer/solution-explorer@v1
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
- uses: sirfifer/solution-explorer@v1
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
- uses: sirfifer/solution-explorer@v1
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
```

## How It Works

1. **Python Analyzer** (`analyze.py`) walks the codebase with zero external dependencies (stdlib only)
2. Detects components via marker files (package.json, Cargo.toml, Info.plist, Dockerfile, etc.)
3. Parses source files to extract symbols, imports, and API patterns
4. Detects inter-component relationships (imports, HTTP/port references, protocols)
5. Outputs `architecture.json` with the full hierarchical model
6. **React Viewer** renders the data as an interactive graph

### Supported Languages

Primary (full parsing): **Swift, Python, Rust, TypeScript/JavaScript, Go**

Detection and metrics: Java, Kotlin, Ruby, C/C++, C#, Dart, Vue, Svelte, HTML/CSS, SQL, Shell

### What It Detects

- **Components**: Via marker files (package.json, Cargo.toml, pyproject.toml, go.mod, Info.plist, Dockerfile, etc.)
- **Symbols**: Classes, structs, enums, protocols/traits/interfaces, functions, React components
- **Relationships**: Import dependencies, port-based HTTP connections, Docker Compose links
- **Metrics**: File counts, line counts, size, language breakdown per component
- **Frameworks**: SwiftUI, UIKit, React, Next.js, Flask, Django, Axum, Express, Vue, and more
- **Documentation**: README, CLAUDE.md, CHANGELOG, API endpoints, env vars, architectural patterns

### CLI Options

```
python3 analyze.py [path] [options]

Options:
  -o, --output        Output JSON path (default: architecture.json)
  --config            Path to solution-explorer.json for multi-repo mode
  --max-file-size     Skip files larger than N bytes (default: 500KB)
  --max-symbols       Limit symbols in output (default: 5000, 0=unlimited)
  --preview-lines     Lines per code preview (default: 5)
  --compact           Compact JSON (no indentation)
```

## Viewer Features

- **Hierarchical drill-down**: Click to see details, double-click to drill into sub-components
- **Breadcrumb navigation**: Always know where you are, click to jump back
- **Fuzzy search**: Cmd/Ctrl+K to search across components, files, and symbols
- **Code preview**: Inline syntax-highlighted code for every symbol
- **Relationship visualization**: Arrows show dependencies and HTTP connections
- **Dark/light mode**: Toggle with one click
- **Mobile-friendly**: Touch gestures, bottom sheet panels, responsive layout
- **Multi-repo grouping**: Repository-level nodes when visualizing multi-repo solutions

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Cmd/Ctrl + K | Open search |
| Escape | Close search/panels |
| Arrow keys | Navigate search results |
| Enter | Select search result |

## Architecture Data Format

```
{
  name, description, repository, generated_at,
  repositories: [{ name, repository }],       // multi-repo only
  components: [{
    id, name, type, path, language, framework, port,
    children: [...],
    files: [...],
    metrics: { files, lines, size_bytes, symbols, languages },
    docs: { readme, purpose, patterns, tech_stack, api_endpoints, env_vars, ... }
  }],
  relationships: [{ source, target, type, label, protocol, port }],
  symbols: [{ id, name, kind, file, line, end_line, code_preview, visibility }],
  files: [{ path, language, lines, size_bytes, symbols, imports }],
  stats: { total_files, total_lines, total_symbols, ... }
}
```

## Local Development

For contributing to solution-explorer itself:

```bash
git clone https://github.com/sirfifer/solution-explorer.git
cd solution-explorer

# Analyze this repo as a test
python3 analyze.py . -o viewer/public/architecture.json

# Start the viewer in dev mode
cd viewer && npm install && npm run dev
```

Requirements: Python 3.10+, Node.js 18+

## License

MIT
