# SysCorpus: Evidence-Linked System Comprehension for AI-Era Codebases

AI coding assistants can generate entire codebases in hours. They scaffold projects, implement features, wire up services, and write tests. But the output is files. Hundreds of files across dozens of directories, with architecture that lives only in the AI's context window. The person who needs to review, extend, and maintain that code faces the same old problem: understanding what was built. Except now the pace of generation far outstrips the pace of comprehension.

SysCorpus closes that gap. It scans a codebase or multi-repository system, extracts its component structure, relationships, metrics, and evidence, then renders human- and machine-readable views over the same fact base. Optional enrichment adds grounded explanations and guided paths. A built-in review system lets people annotate what they see and export structured directives for implementation. The loop closes: AI builds, humans understand and review, AI refines.

Some package names, repository paths, configuration filenames, and URL compatibility values retain earlier internal identifiers. They are implementation details, not a second public product name.

This document covers the vision, the user experience, the system architecture, and the project's evolution. For installation and configuration, see [README.md](README.md). For contributing, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## The Vision: Human-in-the-Loop Architecture

### The Problem

When a developer inherits an unfamiliar codebase, the traditional tools available to them assume pre-existing knowledge. Class diagrams require understanding the object model. API documentation requires knowing which services exist. Dependency graphs require recognizing library names. These tools serve developers who already understand the stack and need a reference. They do not serve someone encountering the architecture for the first time.

This problem intensifies with AI-generated code. An AI assistant can produce a full-stack application in a single session, complete with database models, API routes, frontend components, and infrastructure configuration. But the human receiving that output has no mental model of what was built. The architecture was never designed on a whiteboard or discussed in a planning meeting. It emerged from a conversation with an AI, and now it needs to be understood, validated, and maintained by people.

### The Approach

SysCorpus is built on three principles:

**1. Representation for humans.** The architecture diagram is the primary artifact. Every component appears as a visual card shaped like the device it represents: an iOS app looks like an iPhone, a web client looks like a browser window, an API server looks like a server rack. You do not need to know that the project uses SwiftUI or React or Express. The visual representation tells you what each component is and how it relates to the others. User interface workflows and navigation flows are the primary gateways into understanding the application, not raw class hierarchies or API specifications.

**2. 100% coverage.** Every component, every file, every symbol, every relationship. The diagram accounts for the entire codebase. No sampling, no approximation, no arbitrary caps. When you drill into a component, you see all of its internals. When you open its files tab, every file is listed. When you open its symbols tab, every class, struct, function, and protocol is there. The default v2 engine makes this verifiable rather than aspirational: it emits a coverage ledger that accounts for every file exactly once, either parsed or skipped for a stated reason, and the viewer surfaces it as a coverage badge. The goal is a complete, navigable map of the entire system.

**3. Bidirectional workflow.** Humans explore what AI built, annotate what needs to change, and export those annotations as structured prompts that feed back into the AI. Each annotation carries full context: the component's path, framework, language, current values, relationships, and the reviewer's feedback. The exported prompt is designed to be pasted directly into Claude Code or any AI coding assistant to implement the requested changes. This is not just a visualization tool. It is a review and feedback tool that completes the human-AI collaboration loop.

### What This Is Not

SysCorpus is not a linter, a test framework, a runtime monitor, or a documentation generator (though it extracts existing documentation). It is a comprehension and review tool. It answers the question: "What did the AI build, and what do I want to change?"

---

## The User Experience

### First Impression: The Architecture Graph

When you open SysCorpus, an interactive graph fills the screen. Each node is a component card. Arrows connect related components. The layout is automatic, computed by the ELK layout engine with a layered algorithm that places client applications at the top and servers below. A subtle dot grid provides spatial context. Zoom controls sit at the bottom-left, and a color-coded minimap at the bottom-right shows your current viewport within the full graph.

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

### Lenses

The graph answers "what is here". Lenses answer narrower questions without
making you leave it. A selector above the canvas switches between them. Structure
is the default view; the other seven dock their own ranked panel beside the graph
while the graph itself stays live and navigable.

| Lens | The question it answers |
|------|-------------------------|
| **Structure** | How is the system composed? The default view |
| **Inventory** | What is critical, what does this depend on, and what ports does it listen on? |
| **Flow** | How does a user move through the application? |
| **Activity** | Where is the code changing? |
| **Capability** | What can this system do, expressed as capabilities rather than files? |
| **Data** | What data exists, and which entities relate to which? |
| **Rules** | What business rules are encoded, and where? |
| **Design** | Where is the structure under stress, and what would a change here break? |

A lens only appears when the loaded dataset can actually answer its question. A
project with no detected business rules does not get a Rules lens showing an
empty panel; the lens is simply absent. This is the same principle the coverage
ledger follows, applied to navigation: offer nothing you cannot substantiate.

Every row in a lens panel is a way back into the graph: clicking a critical
component, an external dependency's caller, or a listening port navigates
straight to the component that owns it. On a phone the panel becomes a bottom
sheet rather than disappearing, so a lens is usable in a hallway, not only at a
desk.

The Design lens carries one interaction of its own: **blast radius**. Toggle the
mode and select any component. Everything that could break if it changes shades
one way, everything it stands on shades another, and the rest of the graph dims.
The computation runs client-side, so it works at any drill level and on any
dataset that carries design signals, and each card shows its blast radius count
so the heavy hitters are visible before you ask.

### Search

Press Cmd+K (or Ctrl+K) to open a spotlight-style search overlay. Fuzzy matching powered by Fuse.js searches across components, files, symbols, and the text of the project's own documentation simultaneously. That last one matters more than it sounds: a system's most important facts are often written in prose rather than expressed in code, and a map that indexes Markdown by filename alone cannot lead anyone to them. Results show a type icon, name, path, language dot, and kind badge. Navigate with arrow keys, press Enter to select. The result counter shows how many matches exist (up to 50 displayed).

In split mode the index arrives in shards, fetched in parallel in the background. Search is usable immediately against what is already loaded, and the overlay says so: it reports that it is still indexing rather than presenting a partially-loaded index as a complete one, and says plainly if a shard failed to arrive.

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

Annotations are visible throughout the interface. Annotated nodes show a count badge. The tree navigator shows a blue dot next to annotated components. The Review button in the toolbar displays the total annotation count. Annotations persist to localStorage under the architecture's stable identity, so they survive a hard reload and you can review and annotate across multiple drill-down levels without losing track.

---

## The System Architecture

### Pipeline Overview

SysCorpus is a static pipeline:

```
Codebase  ──>  Analyzer (Python)  ──>  architecture.json  ──>  AI Enhancement (optional)  ──>  Viewer (React)  ──>  Deploy
```

The analyzer runs once, either in CI or locally, and produces a JSON file. The viewer loads that JSON as static data. There is no server runtime, no database, no background process. The deployed viewer is a static site served from Cloudflare Pages, GitHub Pages, or any CDN. This simplicity is a deliberate architectural choice.

### The Analyzer

The analyzer is written in Python with a stdlib-only core for maximum CI/CD compatibility. It runs in GitHub Actions on any runner without additional setup. Optional dependencies for advanced features (incremental analysis, live monitoring) are declared in pyproject.toml and installed only when needed.

How it works:

1. **Component discovery.** Walk the filesystem, detect components by marker files (package.json, Cargo.toml, pyproject.toml, go.mod, Info.plist, Dockerfile, docker-compose.yml, Gemfile, build.gradle, and more). Each marker file creates a component in the hierarchy.

2. **Source parsing.** For each source file, apply a language-specific parser to extract symbols (classes, structs, enums, protocols, functions, React components), imports, and framework indicators.

3. **Type promotion.** Infer component types from framework detection, directory structure, and configuration. A generic "service" becomes an "api-server" when the analyzer detects Express, Flask, or Vapor. An "application" becomes an "ios-client" when it detects SwiftUI and Info.plist.

4. **Relationship detection.** Find inter-component connections: import paths, port-based HTTP references, Docker Compose links, URL patterns, and gRPC service definitions.

5. **Metrics and documentation.** Compute file counts, line counts, size, and language breakdown. Extract documentation from README, CLAUDE.md, CHANGELOG, and code comments. Detect API endpoints, environment variables, and external cloud services.

| Tier | Languages | Capabilities |
|------|-----------|-------------|
| **Full parsing (regex)** | Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby, Java, C#, C/C++ | Components, symbols, relationships, frameworks, API endpoints |
| **Full parsing (tree-sitter)** | Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby, Java, C#, C/C++ | Same as above, with more accurate AST-based extraction |
| **Detection + metrics** | Kotlin, Dart, Vue, Svelte, HTML/CSS, SQL, Shell | File counts, line counts, size, language breakdown |

**SwiftUI flow detection** is a specialized capability. The SwiftUIFlowDetector identifies TabView tabs, NavigationLink targets, sheet and fullScreenCover modals, and embedded view composition. It uses distance-based breadth-first search to assign screens to their closest tab, preventing contamination across navigation hierarchies. The result is a faithful representation of an iOS app's navigation structure rendered as navigable nodes in the viewer.

**Analysis engine (v2, default).** The default engine is an extract, derive, project pipeline over a persistent fact store. Extraction parses each file once and records its symbols and signals in the store, keyed by content hash, so a warm run re-parses only the files whose content changed. Derivation builds components, relationships, and metrics from the store without re-reading source. Projection writes the same `architecture.json` or split output the viewer already renders. Two properties fall out of this design: a coverage ledger that accounts for every file under the root exactly once (parsed, skipped for a stated reason, or inside a pruned directory recorded as a single row), and incremental analysis by construction (the store is the baseline, so `--incremental` and its sibling flags are accepted as no-ops). There is no symbol cap in v2. On a private 4.94M-line validation corpus spanning 15,256 parsed files, a cold run took 136 seconds, peaked at 1.9 GB, and produced a complete ledger. The corpus identity remains unpublished until its map is ready. The legacy v1 single-pass scanner remains available via `--engine v1` for rollback and is scheduled for removal at a later gate.

**Output modes:** The analyzer supports two output formats. Single-file mode produces one `architecture.json` with everything. Split mode (`--split` flag) produces a directory with a lightweight `manifest.json` (~20-100 KB) containing the component tree, relationships, and stats, plus per-component detail files loaded on demand. Under the legacy v1 engine, single-file mode applies a configurable default 5,000 symbol cap (lifted with `--max-symbols 0` or `--split`); the default v2 engine never caps symbols.

**Tree-sitter parsers.** Each of the six language parsers has an optional tree-sitter upgrade that provides AST-based extraction instead of regex matching. Tree-sitter parsers activate automatically when the `treesitter` dependency group is installed (`pip install -e ".[treesitter]"`). If tree-sitter is unavailable, the analyzer falls back to regex parsers silently. This dual-parser architecture means the core analyzer remains zero-dependency while teams that need higher parsing accuracy can opt in.

**Incremental analysis.** The default v2 engine is incremental by construction: the persistent fact store is the baseline and content-hash comparison decides what re-parses, so no explicit flags are needed. Under the legacy v1 engine, the `--incremental` flag enables selective re-scanning: the `IncrementalAnalyzer` compares git revisions (via `--base-sha` and `--head-sha`), identifies which files changed, maps those changes to affected components, and rescans only those components plus their direct importers. Results merge back into a `--baseline` file to produce an updated architecture. Marker file changes (package.json, Cargo.toml, etc.) trigger a full rescan. Either way, analysis time drops significantly for large projects with small changesets.

**Validation.** The `--validate` flag (requires the `models` dependency group with pydantic) validates the output JSON against the data model, checking cross-references between components, symbols, files, and relationships.

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

**The Enrichment Engine (`enhance --ladder`, default off).** The newer enrichment path treats "the map must never lie" as an engineering constraint rather than a hope. It runs five phases against the fact store: orientation, a three-rung model ladder, adjudication, synthesis, and determination, and it always writes a Run Report. Every claim it produces must answer a completeness contract (purpose, mechanism, place, identity, next step) with citations that a no-AI validator checks against the repository and the store. A claim that cannot cite does not ship. Items that cannot be grounded escalate rung by rung and terminate either grounded or as a declared honest gap, never as silently missing. Model tiers are configuration, not architecture: a rung binds to a source plus an optionally pinned model, so adding a provider is a registration rather than a refactor. Cost is budget-metered with a ceiling that stops new work gracefully, and the default path without `--ladder` is byte-identical to not having the engine at all.

Two supporting capabilities ride along. A deterministic **navigation-importance ranking** (dependency fan-in, git activity, entry points, size) orders enrichment work and adjudication sampling, and is deliberately not projected into the output. And enrichment can author **tours**: guided walkthroughs through the architecture, each an ordered component sequence with narration and file evidence, validated against the viewer's tour contract at write time.

### Design Signals

Architecture quality signals (`--design-signals`, default off) are the deterministic sibling of AI enhancement: the analyzer derives them with no model and no spend, so they cost nothing to refresh and cannot hallucinate. Per component: fan-in, fan-out, instability, abstractness, distance from the main sequence, blast radius, and quintile bands. Per architecture: findings for dependency cycles, the zones of pain and uselessness, stability inversions, cross-boundary change coupling, and boundary strength. Each finding carries three things together: a plain-language statement of the consequence, the canonical term for readers who know the literature, and the method naming its evidence class.

The signals decline to claim more than they can support, and the schema enforces that rather than a policy requesting it. There is no overall architecture score, no grade, and no ranking of one kind of finding against another anywhere in the payload; findings rank within their own kind only. Abstractness is measured only in languages whose declarations distinguish an interface from a class (C#, Go, Java, Rust, Swift, TypeScript), so a Python component reports it as unknown rather than as zero. That distinction prevents a load-bearing module being reported in the zone of pain on a number nobody measured.

In the viewer, the Design lens renders these findings plain-language first with the canonical term as a secondary chip, alongside an abstractness against instability scatter with the main sequence and both zones shaded. The method caveat is rendered verbatim from the payload, never composed by the viewer. With `--design-signals` off, the output is byte-identical to not having the feature.

### The Viewer

The viewer is built with React 19, TypeScript, and Tailwind CSS. React Flow renders the graph. ELK (Eclipse Layout Kernel) computes automatic layouts. Zustand manages state. Vite builds the production bundle.

The comprehension-first **Overview is the default interface**. It starts with a bounded system portrait, guided questions, and trust context, then hands off without losing context. **Workbench** is the current full technical interface for direct graph, lens, source, evidence, and review work. They are two apertures over one product and one projection.

The key architectural decision in the viewer is hierarchical drill-down. At any level of the hierarchy, the viewer displays at most ~100 nodes. This keeps React Flow's SVG-based rendering performant without needing a Canvas or WebGL replacement. The performance bottleneck in architecture visualization is never the rendering engine. It is data loading. Split mode addresses this: the manifest loads on startup (~20-100 KB), and per-component details load on demand when a user opens a detail panel.

### The Machine Front Door

The viewer is not the only consumer of a projection. Every published map also
carries an `ai.json` front door and an `llms.txt` pointer, and an MCP server
exposes the same facts as twelve tools an AI agent can call directly: overview,
search, component and symbol detail, references, impact, coverage, rules,
findings, design signals per architecture and per component, and blast radius.
An agent answering a question about an unfamiliar codebase can read a structured
projection instead of the raw repository, which is a different order of
magnitude of context. For design signals, `ai.json` leads with the canonical
term and carries the plain sentence as the description, and it adds a walk
order for planning safe parallel changes.

This is the same design principle as the viewer, applied to a different reader.
Both consume the fact store; neither is privileged. A claim that appears in
one and not the other is a defect, and the two are checked against each other,
including by a publish gate that blocks a release when the front door and the
manifest disagree. For design signals specifically the guarantee is stronger:
both surfaces derive from the same function over the same store, so those
numbers agree by construction.

### Deployment

A GitHub Action workflow handles the full pipeline. Push to main triggers the analyzer (or uses a pre-built JSON if one exists, preserving AI enhancements), builds the viewer, and deploys to the configured target. Supported targets include Cloudflare Pages, GitHub Pages, Vercel, Netlify, and any static host. The viewer builds to a `dist/` directory that can be served from anywhere.

### Live Monitoring

SysCorpus supports continuous architecture updates as the codebase changes. When enabled, a dedicated CI workflow (`live-monitor.yml`) runs on every push to main:

1. Restores the previous architecture baseline from cache
2. Runs incremental analysis (only changed files and their importers)
3. Collects CI status from GitHub Actions (build pass/fail per component)
4. Generates version metadata, live configuration, and admin summary
5. Publishes live data to GitHub Pages and/or Cloudflare R2

The viewer polls for updates and displays them in real time:

- **CI status overlay**: Build pass/fail/running indicators on component nodes
- **Admin dashboard**: Repository monitoring, version history, activity log, and version comparisons
- **Adaptive polling**: 15-30 seconds when active (depending on backend mode), 120 seconds when idle, pauses when the browser tab is hidden

Two backend modes are supported:

| Mode | Cost | Polling | Storage | Setup |
|------|------|---------|---------|-------|
| **GitHub Pages** | Free (public repos) | 30-second intervals | Static files on GitHub Pages | Enable `live-monitor: 'true'` in the action |
| **Cloudflare** | Free tier sufficient | 15-second intervals | Workers + D1 + R2 + KV | Configure Worker, set secrets |

The Cloudflare backend (`infrastructure/cloudflare/worker/`) provides an API Worker with D1 database for version history, R2 bucket for architecture data, and KV namespace for settings. It accepts data via authenticated POST `/ingest` from CI and serves it to the viewer with lower latency than GitHub Pages polling.

Both modes are optional. The viewer works without live monitoring, displaying only the statically-generated architecture data.

### CI Pipeline

Three GitHub Actions workflows automate the full lifecycle:

| Workflow | Trigger | What It Does |
|----------|---------|-------------|
| `ci.yml` | Push, PR | Quality gate: ruff lint, pytest with coverage, eslint, vitest with coverage, type checking, build verification |
| `architecture-viz.yml` | Push to main | Runs analyzer, builds viewer, deploys to Cloudflare Pages |
| `live-monitor.yml` | Push to main, post-deploy, manual | Incremental analysis, CI status collection, live data publishing |

The CI gate job requires all checks to pass before merging. Coverage reports (HTML) are uploaded as artifacts.

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

Many real solutions span multiple repositories: a mobile client in one repo, an API server in another, shared libraries in a third. SysCorpus handles this with a `solution-explorer.json` configuration file that declares repositories (local paths or git URLs), cross-repo relationships, and solution metadata.

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

### v1.2.0 (February 2025): Tree-sitter, Incremental Analysis, and Live Monitoring

Three major capabilities were added in parallel:

**Tree-sitter parsers.** Every language gained an optional tree-sitter parser alongside the existing regex parser. The tree-sitter variants provide more accurate AST-based symbol extraction, while the regex parsers remain the zero-dependency default. The upgrade is automatic when tree-sitter dependencies are installed and silent when they are not.

**Incremental analysis.** The `IncrementalAnalyzer` enabled selective re-scanning in CI. Instead of re-analyzing the entire codebase on every push, only changed files and their direct importers are rescanned. Results merge into a cached baseline. This reduced analysis time for large projects with small changesets from minutes to seconds.

**Live monitoring.** A complete live architecture pipeline was implemented: a CI workflow that publishes incremental updates, CI status collection, version tracking, an admin dashboard in the viewer, and adaptive polling. Two backend modes (GitHub Pages for zero cost, Cloudflare Workers for lower latency) give teams flexibility. The viewer gained a StatusDashboard component for CI overlays and an AdminDashboard for monitoring.

**CI pipeline.** A proper quality gate (`ci.yml`) was added with Python linting (ruff), TypeScript linting (eslint), test suites for both layers (pytest with coverage, vitest with coverage), type checking, and build verification. The architecture visualization and live monitoring workflows were separated into dedicated pipeline files.

### After 1.2.0: The Index Engine

The work since 1.2.0 replaced the in-memory scanner with the default v2 extract, derive, project engine, added the coverage ledger and its viewer badge, made review annotations persist across reloads, and shipped inbound `?file=&line=` deep links. See the CHANGELOG's Unreleased section for the full list.

The package version is reconciled to **1.2.0** across `pyproject.toml`, the CLI package, and the viewer, and the CHANGELOG carries a 1.2.0 entry. The tagged release and the npm and PyPI publish are prepared but not yet done, pending the maintainer setting the publish credentials, so `npx solution-explorer` is not on the public registries yet. The CHANGELOG is the authoritative record of release dates.

### After the Index Engine: Measuring Whether the Map Can Be Trusted

Everything above is a story about capability: more languages, more coverage,
more surfaces. The next chapter is a different kind of work, and a more
uncomfortable one.

The claim at the centre of this project is that a person who does not know a
codebase, or even its language, can navigate it, work out how it fits together,
and start finding real issues, without an AI holding their hand. That claim had
never actually been measured. It had been assumed, demonstrated informally, and
believed. So an instrument was built to test it: the Comprehension Review. Three
fixed personas run genuinely cold against a deployed map, each with a mission
and a five-question battery. A senior engineer who does not know the subject's
language. A technology executive who last wrote code fifteen years ago. A staff
engineer who drives tools hard and distrusts anything derived. Their answers are
scored against a key built independently from the subject's own source, so the
tool is never graded against its own output.

The first run measured the same subject before and after a known change, so the
instrument and the change could be validated together. What it surfaced was not
a list of rough edges. Almost every finding was the same species of defect: a
place where the map said more than it could support.

Documentation was indexed by filename only. Every one of a subject's 233
Markdown files was in the search index with its content empty, which meant the
single richest description of that system was invisible to anyone searching for
what it said. Two reviewers, months apart and working independently, both failed
to discover that the subject's entire backend ran on one laptop, a fact its own
documentation stated plainly, because that fact lived in prose. The changelog
reported an identifier-scheme change as 254 newly discovered components when
about six had genuinely changed. A count of five external dependencies was
presented as fact when the method behind it was matching a hardcoded list of
domains, one of which had been picked up from a continuous-integration script.
An administrative overlay served data six months old, republished on every run
so that every freshness signal available said it was current.

The shape those failures share is the important part. **None of them looked
wrong.** A component count of 251 sitting beside 254 reads as a scoping
difference. "254 components added" reads as an active week. That is the
dangerous failure mode for a comprehension tool: not an error a reader catches
and discounts, but a plausible number they carry into a decision. A tool that is
obviously broken costs you an afternoon. A tool that is quietly, credibly wrong
costs you the decision you made on top of it.

So the fixes were less about features than about epistemics. Documentation
content is indexed. Identifier migrations are detected and reported as
re-identification rather than discovery. Dependency counts say they were
detected by matching known domains, and that the list is not exhaustive. When
two published surfaces disagree about the same number, the interface now says so
loudly instead of showing both as though they agreed. Where the tool cannot
support a claim, it now declines to make it. That is a harder product to
demonstrate and a much easier one to trust.

The instrument corrected itself in the process, which is the part worth
repeating to anyone building something similar. A reviewer reported that the
graph never rendered; their own screenshot, taken during the attempt, showed it
rendered. Across the run, reviewer claims about *data* proved reliable and their
claims about *interfaces* frequently did not. So every claim is now verified
against source or evidence before it counts, in both directions, and a
confirmation is held to the same standard as a contradiction. Two of the
verifier's own findings turned out to be wrong for exactly the opposite reason:
a plausible fact, a partial check, a confident conclusion.

Where this leads is a programme of published maps: well-known open-source
codebases, mapped by the tool, refreshed on a schedule, with every refresh
feeding what it exposes back into the engine. Any map good enough to publish
under its subject's name is a map worth trusting. The instrument that decides
when a map is ready now exists, and it has already been sharp enough to be
unflattering. Its first calibration run measured three cold personas against
the same subject before and after a known change, verified every claim in both
directions, and moved the scores it was built to move.

### SysCorpus: The Publication Program

That programme now has a name, a domain, and most of its machinery. SysCorpus
(`syscorpus.com`) is the public face of the work: a maintained register of
well-known codebases mapped by the tool, refreshed weekly from a single
machine, with every refresh feeding fixes back into the product.

The machinery built for it spans three layers. The demo harness
(`scripts/demo-site.py`) runs the whole chain per subject: fetch a pinned
clone, analyze into a split projection, enrich, validate against a graduation
gate, diff against last week, bundle, and deploy, stopping at the first gate
failure. The graduation gate is a hard gate, not a guideline: complete coverage
ledger, bounded detect-only share, enrichment quality at threshold, front door
agreeing with the manifest, license review passed, upstream LICENSE shipped.
A demo that cannot pass stays private. The Enrichment Engine and Design
Signals, described above, are the two newest layers, and both follow the same
rule the whole product follows: default off, byte-identical when off, and
never claiming what they cannot cite.

The honest state of the program, at the time of this writing: the harness, the
gates, the engine, and the instrument are built and tested. The first public
demos are being prepared and are not yet live. What is published under the
SysCorpus name will have passed every gate above, and nothing gets to skip
them for being famous.

### The Decision Not to Rewrite

Before the v1.1.0 refactor, a thorough architectural assessment was conducted. Research into Sourcegraph, Sourcetrail, CodeScene, NDepend, Structure101, Semgrep, SonarQube, and other tools informed the key decisions.

The question of rewriting the analyzer in TypeScript was considered and rejected. The Python analyzer's stdlib-only core is a genuine advantage for CI/CD: it runs on any GitHub Actions runner without Node.js setup and with no required pip dependencies. Optional dependencies for advanced features are declared in pyproject.toml but never required for basic analysis. A TypeScript rewrite would add runtime complexity for marginal benefit, since the analyzer runs once in CI, not interactively. Speed does not matter; correctness and comprehensiveness do.

The incremental refactoring (modular package, split output, configurable caps) delivered the architectural benefits at a fraction of the rewrite effort. The option to rewrite remains viable as a future choice, but the current architecture scales for the foreseeable roadmap.

See [docs/architectural-assessment.md](docs/architectural-assessment.md) for the complete analysis.

---

## Roadmap

### Wave 2: Features (Shipped)

All three Wave 2 features have shipped:

**UI action detection.** The analyzer captures interactive elements, buttons, tap and long-press gestures, toolbar items, context menus, and swipe actions, and surfaces them in component details with file and line references (Swift and TypeScript today).

**Source code linking.** Symbols, files, and actions link directly to their source location. Click a function name in the symbols tab to open it on GitHub at the right line number, connecting the abstract architecture view to the concrete code.

**Bidirectional navigation.** Inbound deep-link URLs let external tools navigate into the viewer. An AI assistant can output a link like `?file=Sources/Auth/LoginView.swift&line=42`, and opening it drills into the owning component and selects the symbol at that line. Ambiguous and missing targets degrade gracefully rather than crashing.

See [docs/archive/ui-actions-source-linking-plan.md](docs/archive/ui-actions-source-linking-plan.md) for the original implementation plan, archived now that all three have shipped.

### Wave 3: Scale Hardening (Future)

For projects exceeding 5,000 files, additional optimizations are planned:

- **IndexedDB caching** for fetched component data across browser sessions
- **Service worker** for offline support and prefetching adjacent components
- **Web Worker** for layout computation on dense sub-graphs
- **O(1) component and symbol lookups** via pre-built indexes in the store
- **Gzip compression** of JSON outputs

### Possible Future Directions

- **Runtime action recording** to capture actual user workflows alongside the static analysis
- **IDE integration** for navigating between the architecture viewer and the code editor

---

## Quick Reference

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Analyzer | Python 3.10+ | Stdlib core, optional tree-sitter/pydantic/gitpython via pyproject.toml |
| Viewer | React 19, TypeScript, Tailwind CSS | Vite 6 build, Node.js 22+ |
| Graph | React Flow + ELK layout engine | SVG-based, ~100 visible nodes per drill level |
| Search | Fuse.js | Fuzzy matching, progressive indexing in split mode |
| State | Zustand | Lazy loading support for split mode |
| CI | GitHub Actions (3 workflows) | Quality gate, architecture viz, live monitor |
| Deployment | Reusable GitHub Action | Cloudflare Pages, GitHub Pages, Vercel, Netlify, static hosting |
| Live Backend | Cloudflare Workers + D1 + R2 + KV | Optional, for lower-latency live monitoring |
| AI Enhancement | Claude (via /ai-assist skill) | Optional, backward-compatible |
| Testing | pytest + vitest | Coverage reporting, testing-library for React |

### Key Numbers

| Metric | Value |
|--------|-------|
| Languages (full parsing) | 9 parser pairs (Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby, Java, C#, C/C++), each with regex + tree-sitter |
| Languages (detection + metrics) | 7 (Kotlin, Dart, Vue, Svelte, HTML/CSS, SQL, Shell) |
| Component types recognized | 21 |
| Architectural roles (AI) | 18 |
| Device frame styles | 10 |
| Annotation target types | 9 |
| Detail panel tabs | 6 |
| Lenses | 8 (Structure, Inventory, Flow, Activity, Capability, Data, Rules, Design), each shown only when the dataset supports it |
| MCP tools in the machine front door | 12 |
| Design signal finding kinds | 6 (cycles, zone of pain, zone of uselessness, stability inversions, change coupling, boundary strength) |
| Enrichment ladder phases | 5 (orientation, ladder, adjudication, synthesis, determination) |
| Comprehension Review personas | 3, each scored on 6 dimensions |
| CI workflows | 10 (quality gate, architecture viz, live monitor, golden corpus, GUI plan check, SBOM, scorecard, release, downstream deploy, demo domain) |

### Related Documents

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Installation, configuration, CLI reference, deployment options |
| [docs/quality/COMPREHENSION-REVIEW.md](docs/quality/COMPREHENSION-REVIEW.md) | The instrument that measures whether the map teaches: personas, battery, rubric, answer keys |
| [docs/publication/DEMO-PROGRAM.md](docs/publication/DEMO-PROGRAM.md) | The SysCorpus demo program: the register, the two tracks, the graduation gate, the refresh loop |
| [docs/publication/ENRICHMENT-ENGINE.md](docs/publication/ENRICHMENT-ENGINE.md) | The Enrichment Engine: the ladder, the completeness contract, the Run Report |
| [docs/research/architecture-quality-signals.md](docs/research/architecture-quality-signals.md) | Design signals: the research base and the tier plan |
| [docs/publication/PREFLIGHT-MEASUREMENTS.md](docs/publication/PREFLIGHT-MEASUREMENTS.md) | Measured scale, timing and cost figures per subject |
| [docs/architecture.md](docs/architecture.md) | Technical architecture and data model. **Predates v1.2.0; see its banner** |
| [docs/architectural-assessment.md](docs/architectural-assessment.md) | Technical design decisions, industry research, evolution plan |
| [docs/analyzer-package.md](docs/analyzer-package.md) | Analyzer package structure and module guide. **Predates v1.2.0; see its banner** |
| [docs/archive/live-architecture-monitoring.md](docs/archive/live-architecture-monitoring.md) | Live monitoring design, cost analysis, dual-mode architecture (historical) |
| [docs/archive/ui-actions-source-linking-plan.md](docs/archive/ui-actions-source-linking-plan.md) | Wave 2 feature design (UI actions, source linking, deep navigation). Archived; all three shipped |
| [DEPLOYMENTS.md](DEPLOYMENTS.md) | Installation tracking and redeployment guide |
