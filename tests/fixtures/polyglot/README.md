# polyglot fixture

A tiny multi-language solution used by the analyzer test suite. It exists to
exercise the current engine across every tree-sitter language and the main
component and relationship types, and to anchor the P4-1 parity snapshot that
the P4-7 cutover diffs against.

Layout:

- `services/api` Python service (pyproject.toml), binds port 8000, uses a
  Postgres driver.
- `services/web` TypeScript + JavaScript web client (package.json), calls the
  API over HTTP.
- `services/worker` Go module (go.mod).
- `libs/core` Rust library (Cargo.toml).
- `libs/rubylib` Ruby package (Gemfile).
- `apps/ios` Swift package (Package.swift).
- `docker-compose.yml` infrastructure: db and cache services.

Keep it tiny. It is committed as real files and must parse fast in CI.
