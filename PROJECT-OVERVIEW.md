# Solution Explorer: Interactive Architecture Visualization for AI-Era Codebases

AI coding assistants can generate entire codebases in hours. They scaffold projects, implement features, wire up services, and write tests. But the output is files. Hundreds of files across dozens of directories, with architecture that lives only in the AI's context window. The person who needs to review, extend, and maintain that code faces the same old problem: understanding what was built. Except now the pace of generation far outstrips the pace of comprehension.

Solution Explorer closes that gap. It scans any codebase, extracts the full component structure, relationships, and metrics, then renders everything as an interactive architecture diagram. An optional AI enhancement layer adds human-readable descriptions, role classifications, and criticality ratings to every component. And a built-in review system lets you annotate anything you see, then export those annotations as structured prompts that go back to the AI for implementation. The loop closes: AI builds, human reviews, AI refines.

This document covers the vision, the user experience, the system architecture, and the project's evolution. For installation and configuration, see [README.md](README.md). For contributing, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## The Vision: Human-in-the-Loop Architecture

### The Problem

When a developer inherits an unfamiliar codebase, the traditional tools available to them assume pre-existing knowledge. Class diagrams require understanding the object model. API documentation requires knowing which services exist. Dependency graphs require recognizing library names. These tools serve developers who already understand the stack and need a reference. They do not serve someone encountering the architecture for the first time.

This problem intensifies with AI-generated code. An AI assistant can produce a full-stack application in a single session, complete with database models, API routes, frontend components, and infrastructure configuration. But the human receiving that output has no mental model of what was built. The architecture was never designed on a whiteboard or discussed in a planning meeting. It emerged from a conversation with an AI, and now it needs to be understood, validated, and maintained by people.

### The Approach

Solution Explorer is built on three principles:

**1. Representation for humans.** The architecture diagram is the primary artifact. Every component appears as a visual card shaped like the device it represents: an iOS app looks like an iPhone, a web client looks like a browser window, an API server looks like a server rack. You do not need to know that the project uses SwiftUI or React or Express. The visual representation tells you what each component is and how it relates to the others. User interface workflows and navigation flows are the primary gateways into understanding the application, not raw class hierarchies or API specifications.

**2. 100% coverage.** Every component, every file, every symbol, every relationship. The diagram accounts for the entire codebase. No sampling, no approximation, no arbitrary caps. When you drill into a component, you see all of its internals. When you open its files tab, every file is listed. When you open its symbols tab, every class, struct, function, and protocol is there. The goal is a complete, navigable map of the entire system.

**3. Bidirectional workflow.** Humans explore what AI built, annotate what needs to change, and export those annotations as structured prompts that feed back into the AI. Each annotation carries full context: the component's path, framework, language, current values, relationships, and the reviewer's feedback. The exported prompt is designed to be pasted directly into Claude Code or any AI coding assistant to implement the requested changes. This is not just a visualization tool. It is a review and feedback tool that completes the human-AI collaboration loop.

### What This Is Not

Solution Explorer is not a linter, a test framework, a runtime monitor, or a documentation generator (though it extracts existing documentation). It is a comprehension and review tool. It answers the question: "What did the AI build, and what do I want to change?"

---

## The User Experience

### First Impression: The Architecture Graph

When you open Solution Explorer, an interactive graph fills the screen. Each node is a component card. Arrows connect related components. The layout is automatic, computed by the ELK layout engine with a layered algorithm that places client applications at the top and servers below. A subtle dot grid provides spatial context. Zoom controls sit at the bottom-left, and a color-coded minimap at the bottom-right shows your current viewport within the full graph.

<p align="center">
  <img src="docs/screenshots/architecture-overview.png" alt="Architecture overview showing components and relationships" width="800">
</p>

The most striking visual feature is the device-shaped frames. Hero components, the primary entry points and services of the application, are rendered inside frames that match their real-world form factor:

| Component Type | Visual Frame | Description |
|---------------|-------------|-------------|
| iOS / Mobile Client | iPhone | Rounded corners, Dynamic Island notch, volume and power buttons |
| Web Client | Browser Window | Traffic light dots (red, yellow, green), URL bar |
| API Server | Server Rack | LED status dots, terminal prompt (`$ ~/api`) |
| Watch App | Apple Watch | Digital crown, side button, time display |
| Desktop App | macOS Window | Title bar with traffic lights, menu bar |
| CLI Tool | Terminal | Green-on-black header with prompt |
| Service | Dashed Border | Live status badge, emerald accent |
| Screen | Mobile Screen | Status bar, cyan accent |
| Tab Container | Tab Bar | Tab indicator, indigo accent |

Each frame makes the component's role immediately recognizable without reading any text. A non-hero component (a library, module, or internal package) renders as a simple card with a colored border.

**What's on each card:** The component name with a type icon, a type badge with tooltip, the detected framework with tooltip, an architectural role badge (when AI-enhanced), a purpose line, pattern badges (up to three), and a metrics bar showing a language-colored dot, file count, line count, port number, documentation indicator, API endpoint count, and connection count. If the component has AI-assigned criticality, a colored dot appears: red for critical, amber for important.

**Hover behavior:** Hovering over a node for 400 milliseconds reveals a documentation hover card. This card shows the component's purpose, detected patterns, tech stack, API endpoints (color-coded by HTTP method), environment variables, documented symbols, and indicators for which documentation files exist (README, CLAUDE.md, CHANGELOG, Architecture Notes).

**First-time experience:** A guided welcome tour walks new users through the five core interactions: navigation, drill-down, hover documentation, the detail panel, and search.

### Navigating: Drill-Down and Breadcrumbs

The architecture is hierarchical. An iOS application contains modules. Modules contain screens. Screens contain tabs. Double-click any component to drill into it and see its sub-components rendered as a new graph. A breadcrumb bar appears at the top showing the full navigation path (Home / AppName / ModuleName). Click any breadcrumb to jump back to that level. The Up button goes one level.

<p align="center">
  <img src="docs/screenshots/drill-down.png" alt="Drill-down view showing internal component structure with breadcrumbs" width="800">
</p>

The viewer applies smart display logic at each level. At the top level, it surfaces client applications and their directly-connected servers, unwrapping structural containers (projects, repositories). When you drill into a component, hero-type grandchildren are promoted up from non-hero wrappers. If an iOS app contains a "Sources" module that itself contains screens and services, those screens and services appear directly when you drill into the app, without an intermediate stop at "Sources."

### The Detail Panel

Click any node to open the detail panel on the right side of the screen. The panel has six tabs, each showing a different facet of the component.

<p align="center">
  <img src="docs/screenshots/detail-panel.png" alt="Detail panel showing component metadata, symbols, and metrics" width="800">
</p>

| Tab | What It Shows |
|-----|-------------|
| **Overview** | Metrics grid (files, lines, symbols, size), external services with category colors, API endpoints with HTTP method badges, environment variables, documented symbols with docstrings, language breakdown bar chart, sub-components list |
| **Docs** | Full markdown rendering of README, CLAUDE.md, Architecture Notes, API Docs, and Changelog, with sub-tabs when multiple documentation sources exist |
| **Files** | Filterable list of all files grouped by directory. Each row shows the language color dot, line count, and documentation indicator. Click any file to see its full detail: language, size, symbols with code previews, and import list |
| **Symbols** | Filterable by text and kind. Each symbol shows its kind icon (C for class, S for struct, E for enum, P for protocol, f for function, and more), name, file location, and expandable detail with docstring and syntax-highlighted code preview |
| **Relationships** | Incoming and outgoing connections. Each relationship shows direction arrows, type badge, protocol, port number, AI-discovered indicator, and data flow description. Click any relationship to navigate to the connected component |
| **AI Insights** | Architectural role badge, criticality rating, a multi-sentence help text explaining the component, data handled description, and connection summary (incoming and outgoing counts). This tab appears only when AI enhancement data is present |

In split mode (for larger codebases), the detail panel lazy-loads component data on demand, showing a brief loading state while symbols and files are fetched from per-component JSON files.

### Search

Press Cmd+K (or Ctrl+K) to open a spotlight-style search overlay. Fuzzy matching powered by Fuse.js searches across all components, files, and symbols simultaneously. Results show a type icon, name, path, language dot, and kind badge. Navigate with arrow keys, press Enter to select. The result counter shows how many matches exist (up to 50 displayed). In split mode, the search index builds progressively as components are explored.

### The Tree Navigator

A collapsible sidebar on the left side shows the full component tree. Top-level components appear in the first section. Internal components are grouped by parent in a second section. Each row shows a language-colored dot, the component name (bold for hero types), a type badge, file count, and an annotation indicator (blue dot when annotations exist for that component). Click to select and show on the graph. Double-click to drill in. Expansion state persists across the session.

### Visual Design

Dark mode and light mode toggle with one click, persisted to localStorage. The interface is mobile-responsive with touch gestures and bottom sheet panels replacing the sidebar and detail panel on small screens. Language-colored dots appear throughout the interface (Swift orange-red, Python blue, Rust peach, TypeScript blue, Go cyan, Ruby red). Interactive tooltips explain every badge: component types, symbol kinds, design patterns, tech stack items, and protocols.

Edges between components carry visual meaning. Communication edges (HTTP, WebSocket, gRPC, database) are colored, animated, and solid, indicating runtime data flow. Structural edges (imports, FFI, navigation, Docker) are gray and dashed, indicating code-level or organizational relationships. AI-discovered relationships use a distinct dashed style with reduced opacity. Bidirectional connections show arrows on both ends.

---

## The Review System

The review system is what closes the human-in-the-loop workflow. It turns passive exploration into active feedback that can be fed directly to an AI for implementation.

### Entering Review Mode

Click the Review button in the header toolbar. A banner confirms you are in review mode. Now, every visual element on every component node becomes an annotation target. Hover over any element to see a subtle blue ring indicating it can be annotated. Click to open the annotation input modal.

### What You Can Annotate

The annotation system is fine-grained. You can annotate nine different aspects of each component:

| Target | What It Refers To | Example Feedback |
|--------|------------------|------------------|
| Component (whole) | General feedback on the component | "This should be split into two services" |
| Component Name | The display name | "Rename to 'AuthService'" |
| Component Type | The type classification | "This is an api-server, not a service" |
| Component Framework | The detected framework | "Actually using Fastify, not Express" |
| Component Port | The network port | "Port should be 8080 in production" |
| Component Purpose | The purpose statement | "Purpose should mention authentication" |
| Component Pattern | A detected pattern badge | "This is Observer, not Delegate" |
| File | A specific source file | "Dead code, should be removed" |
| Symbol | A class, function, or struct | "Needs better error handling" |

The annotation input modal is contextual. It shows the target's icon, name, and current value, and provides a placeholder specific to the annotation type (for example, "e.g., Rename to 'AuthService'..." for name annotations). Save with Cmd+Enter. Edit or delete any existing annotation.

### The Review Summary

The Review Summary panel, accessible from the right sidebar, groups all annotations by component. Each group shows the component name, type badge, annotation count, and individual annotations sorted by target type (component-level first, then sub-properties, then files, then symbols). Every annotation can be edited or deleted. A "Clear All" button with confirmation removes everything.

### Exporting to AI

The "Copy All to Claude Code" button generates a structured markdown prompt that includes:

- The architecture name and generation timestamp
- For each annotated component: path, framework, language, port, purpose, detected patterns, tech stack, API endpoints, environment variables, and relationships
- For each annotation: a numbered sub-section with the target's current value, contextual information (config files, detection method, related symbols), and the reviewer's feedback in a blockquote
- For file annotations: path, language, line count, and the names of symbols defined in that file
- For symbol annotations: kind, file and line number, visibility, docstring, and code preview
- A summary with total annotation counts by type

The prompt is designed to paste directly into Claude Code or any AI coding assistant. The AI receives enough context to understand what the reviewer saw and implement the requested changes without needing to re-analyze the codebase. A per-component copy button also exists for focused, single-component exports.

### Visual Indicators

Annotations are visible throughout the interface. Annotated nodes show a count badge. The tree navigator shows a blue dot next to annotated components. The Review button in the toolbar displays the total annotation count. These indicators persist across the session so you can review and annotate across multiple drill-down levels without losing track.

---

## The System Architecture

### Pipeline Overview

Solution Explorer is a static pipeline:

```
Codebase  ──>  Analyzer (Python)  ──>  architecture.json  ──>  AI Enhancement (optional)  ──>  Viewer (React)  ──>  Deploy
```

The analyzer runs once, either in CI or locally, and produces a JSON file. The viewer loads that JSON as static data. There is no server runtime, no database, no background process. The deployed viewer is a static site served from Cloudflare Pages, GitHub Pages, or any CDN. This simplicity is a deliberate architectural choice.

### The Analyzer

The analyzer is written in Python with minimal dependencies chosen for CI/CD compatibility. It runs in GitHub Actions on any runner with a simple `pip install`, which is critical for the CI/CD integration model.

How it works:

1. **Component discovery.** Walk the filesystem, detect components by marker files (package.json, Cargo.toml, pyproject.toml, go.mod, Info.plist, Dockerfile, docker-compose.yml, Gemfile, build.gradle, and more). Each marker file creates a component in the hierarchy.

2. **Source parsing.** For each source file, apply a language-specific parser to extract symbols (classes, structs, enums, protocols, functions, React components), imports, and framework indicators.

3. **Type promotion.** Infer component types from framework detection, directory structure, and configuration. A generic "service" becomes an "api-server" when the analyzer detects Express, Flask, or Vapor. An "application" becomes an "ios-client" when it detects SwiftUI and Info.plist.

4. **Relationship detection.** Find inter-component connections: import paths, port-based HTTP references, Docker Compose links, URL patterns, and gRPC service definitions.

5. **Metrics and documentation.** Compute file counts, line counts, size, and language breakdown. Extract documentation from README, CLAUDE.md, CHANGELOG, and code comments. Detect API endpoints, environment variables, and external cloud services.

| Tier | Languages | Capabilities |
|------|-----------|-------------|
| **Full parsing** | Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby | Components, symbols, relationships, frameworks, API endpoints |
| **Detection + metrics** | Java, Kotlin, C/C++, C#, Dart, Vue, Svelte, HTML/CSS, SQL, Shell | File counts, line counts, size, language breakdown |

**SwiftUI flow detection** is a specialized capability. The SwiftUIFlowDetector identifies TabView tabs, NavigationLink targets, sheet and fullScreenCover modals, and embedded view composition. It uses distance-based breadth-first search to assign screens to their closest tab, preventing contamination across navigation hierarchies. The result is a faithful representation of an iOS app's navigation structure rendered as navigable nodes in the viewer.

**Output modes:** The analyzer supports two output formats. Single-file mode produces one `architecture.json` with everything (default 5,000 symbol limit, configurable). Split mode (`--split` flag) produces a directory with a lightweight `manifest.json` (~20-100 KB) containing the component tree, relationships, and stats, plus per-component detail files loaded on demand. Split mode has no symbol limit.

### AI Enhancement

An optional layer enriches the analyzer's output with AI-generated content. The `/ai-assist` skill reads every component's source files and adds:

- **Descriptions and purpose statements** for someone encountering the component for the first time
- **Architectural roles** from an 18-role vocabulary (api-gateway, auth-service, data-store, cache-layer, queue-processor, event-bus, orchestrator, worker, proxy, monitoring, logging, scheduler, notification-service, file-storage, search-engine, ml-pipeline, presentation-layer, business-logic, data-access)
- **Criticality ratings:** critical (system fails without it), important (system works but degraded), supporting (developer tooling and utilities)
- **Help text** for the ? tooltip on each node, explaining the component in 3-5 sentences
- **Data flow descriptions** on relationships, explaining what data moves and in which direction
- **AI-discovered relationships** the static analyzer missed
- **Architecture-level summary** and data flow narrative describing a typical user request
- **Component groupings** by logical layer (Client, API, Data, Infrastructure)

All AI data lives in optional `ai_enhance` sub-objects at the component, relationship, and architecture levels. The viewer works identically with or without AI data. Every access uses optional chaining, so the same viewer renders both enhanced and non-enhanced JSON without any configuration.

### The Viewer

The viewer is built with React 19, TypeScript, and Tailwind CSS. React Flow renders the graph. ELK (Eclipse Layout Kernel) computes automatic layouts. Zustand manages state. Vite builds the production bundle.

The key architectural decision in the viewer is hierarchical drill-down. At any level of the hierarchy, the viewer displays at most ~100 nodes. This keeps React Flow's SVG-based rendering performant without needing a Canvas or WebGL replacement. The performance bottleneck in architecture visualization is never the rendering engine. It is data loading. Split mode addresses this: the manifest loads on startup (~20-100 KB), and per-component details load on demand when a user opens a detail panel.

### Deployment

A GitHub Action workflow handles the full pipeline. Push to main triggers the analyzer (or uses a pre-built JSON if one exists, preserving AI enhancements), builds the viewer, and deploys to the configured target. Supported targets include Cloudflare Pages, GitHub Pages, Vercel, Netlify, and any static host. The viewer builds to a `dist/` directory that can be served from anywhere.

---

## The Data Model

The analyzer captures four core types:

| Type | What It Represents | Key Fields |
|------|-------------------|------------|
| **Component** | A package, module, service, or application | id, name, type, path, language, framework, port, children, files, metrics, docs, ai_enhance |
| **Symbol** | A class, struct, enum, protocol, function, or component | id, name, kind, file, line, end_line, code_preview, visibility, docstring |
| **Relationship** | A connection between two components | source, target, type, protocol, port, label, ai_enhance |
| **FileInfo** | Metadata about a source file | path, language, lines, size_bytes, symbols, imports, module_doc |

### Component Types and Visual Representation

| Type | Viewer Frame | Color Family |
|------|-------------|-------------|
| ios-client, android-client, mobile-client | iPhone frame | Orange / Emerald |
| web-client | Browser frame | Sky |
| api-server | Server rack frame | Green |
| watch-app | Watch frame | Pink |
| desktop-app | Desktop window frame | Teal |
| cli-tool | Terminal frame | Lime |
| service | Dashed service frame | Emerald |
| screen | Screen frame | Cyan |
| tab-container | Tab bar frame | Indigo |
| tab | Mobile frame | Blue |
| application | Enhanced card with ring | Blue |
| library, module, package | Standard card | Violet, Cyan, Amber |
| infrastructure | Standard card | Rose |

### Relationship Types

| Category | Types | Visual Style |
|----------|-------|-------------|
| **Communication** (runtime data flow) | http, websocket, grpc, database, file | Colored, animated, solid arrows |
| **Structural** (code-level) | import, ffi, navigation, tab, modal, docker, companion | Gray, dashed, static |

---

## Multi-Repository Support

Many real solutions span multiple repositories: a mobile client in one repo, an API server in another, shared libraries in a third. Solution Explorer handles this with a `solution-explorer.json` configuration file that declares repositories (local paths or git URLs), cross-repo relationships, and solution metadata.

The analyzer clones remote repositories, analyzes each independently, then merges the results into a single architecture. Repository-level grouping nodes appear in the viewer, and explicit cross-repo relationships supplement the automatic detection. Private repositories are supported via the `GITHUB_TOKEN` environment variable.

See the [README](README.md#multi-repo-solutions) for the full configuration reference.

---

## The Evolution Story

### v1.0.0 (January 2025): The Foundation

Everything shipped at once. The analyzer supported five language parsers (Swift, Python, Rust, TypeScript/JavaScript, Go) plus detection for ten more languages. The React viewer included hierarchical drill-down, fuzzy search, a six-tab detail panel, dark and light mode, and mobile responsive design. SwiftUI flow detection mapped iOS navigation hierarchies. A GitHub Action handled CI/CD deployment to Cloudflare Pages or GitHub Pages.

The entire analyzer was a single 4,525-line Python file. The architecture JSON was a monolithic blob loaded entirely into the browser on page open. For the projects it targeted (small to medium, ~2,000 files), this worked fine.

### v1.1.0 (February 2025): Modular and Scalable

The single Python file was refactored into a 17-module package under `analyzer/`. Each parser got its own file. Models, utilities, configuration parsers, and constants were separated into dedicated modules. The original `analyze.py` was kept as a thin wrapper for backward compatibility. Existing scripts and GitHub Actions continued working unchanged.

Split JSON output was introduced. Instead of loading a 5+ MB monolithic file on page open, the viewer could now load a ~20-100 KB manifest containing just the component tree, relationships, and stats. Symbols and files loaded on demand when a user opened a component's detail panel. The symbol cap (previously a hard 5,000 limit) became configurable and was removed entirely in split mode, unblocking the 100% coverage goal.

Test coverage jumped from ~10% (43 tests) to 81% (370 tests) across five test files. Ruby was added as the sixth fully-parsed language.

### The Decision Not to Rewrite

Before the v1.1.0 refactor, a thorough architectural assessment was conducted. Research into Sourcegraph, Sourcetrail, CodeScene, NDepend, Structure101, Semgrep, SonarQube, and other tools informed the key decisions.

The question of rewriting the analyzer in TypeScript was considered and rejected. The Python analyzer is a genuine advantage for CI/CD: it runs on any GitHub Actions runner without Node.js setup and with minimal pip dependencies. A TypeScript rewrite would add runtime complexity for marginal benefit, since the analyzer runs once in CI, not interactively. Speed does not matter; correctness and comprehensiveness do.

The incremental refactoring (modular package, split output, configurable caps) delivered the architectural benefits at a fraction of the rewrite effort. The option to rewrite remains viable as a future choice, but the current architecture scales for the foreseeable roadmap.

See [docs/architectural-assessment.md](docs/architectural-assessment.md) for the complete analysis.

---

## Roadmap

### Wave 2: Features (Planned)

**UI action detection.** Capture every interactive element, buttons, toolbar items, menus, swipe actions, context menus, and state properties, as symbols in the analyzer. When you drill into a screen, you will see not just its code structure but every user-facing action it offers. This applies across languages: SwiftUI buttons, React onClick handlers, Python endpoint handlers.

**Source code linking.** Every symbol, file, and action will link directly to the exact GitHub source location. Click a function name in the symbols tab and open it on GitHub at the right line number. This connects the abstract architecture view to the concrete code.

**Bidirectional navigation.** Deep-link URLs will let external tools navigate into the architecture viewer. An AI assistant could output a link like `?file=Sources/Auth/LoginView.swift&line=42`, and clicking it would drill into the right component and highlight the right symbol.

See [docs/ui-actions-source-linking-plan.md](docs/ui-actions-source-linking-plan.md) for the detailed implementation plan.

### Wave 3: Scale Hardening (Future)

For projects exceeding 5,000 files, additional optimizations are planned:

- **IndexedDB caching** for fetched component data across browser sessions
- **Service worker** for offline support and prefetching adjacent components
- **Web Worker** for layout computation on dense sub-graphs
- **O(1) component and symbol lookups** via pre-built indexes in the store
- **Gzip compression** of JSON outputs

### Possible Future Directions

- **Tree-sitter integration** via py-tree-sitter for proper AST parsing, staying in Python while getting real parse trees instead of regex-based extraction
- **Runtime action recording** to capture actual user workflows alongside the static analysis
- **IDE integration** for navigating between the architecture viewer and the code editor

---

## Quick Reference

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Analyzer | Python 3.10+ | Minimal dependencies, CI-friendly |
| Viewer | React 19, TypeScript, Tailwind CSS | Vite build |
| Graph | React Flow + ELK layout engine | SVG-based, ~100 visible nodes per drill level |
| Search | Fuse.js | Fuzzy matching, progressive indexing in split mode |
| State | Zustand | Lazy loading support for split mode |
| Deployment | GitHub Action | Cloudflare Pages, GitHub Pages, Vercel, Netlify, static hosting |
| AI Enhancement | Claude (via /ai-assist skill) | Optional, backward-compatible |

### Key Numbers

| Metric | Value |
|--------|-------|
| Test coverage | 81% (370 tests) |
| Languages (full parsing) | 6 (Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby) |
| Languages (detection + metrics) | 10+ |
| Component types recognized | 21 |
| Architectural roles (AI) | 18 |
| Device frame styles | 10 |
| Annotation target types | 9 |
| Detail panel tabs | 6 |

### Related Documents

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Installation, configuration, CLI reference, deployment options |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, code style, PR guidelines |
| [CHANGELOG.md](CHANGELOG.md) | Version history and release notes |
| [docs/architectural-assessment.md](docs/architectural-assessment.md) | Technical design decisions, industry research, evolution plan |
| [docs/ui-actions-source-linking-plan.md](docs/ui-actions-source-linking-plan.md) | Wave 2 feature design (UI actions, source linking, deep navigation) |
| [docs/analyzer-package.md](docs/analyzer-package.md) | Analyzer package structure and module guide |
