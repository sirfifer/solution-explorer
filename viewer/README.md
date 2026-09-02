# SysCorpus viewer interfaces

The React viewer contains two interfaces over the same projection and route state.

| Interface | Status | Purpose |
|---|---|---|
| **Overview** (`?mode=overview`) | **Default** | Comprehension-first system portrait, guided questions, bounded atlas entry, and trust context. |
| **Workbench** (`?mode=workbench`) | **Current** | Full technical exploration: graph, lenses, inspector, evidence, files, symbols, findings, review, sets, and directives. |

Overview and Workbench are two durable apertures in one product. Overview makes the system approachable without requiring repository vocabulary; Workbench gives experienced readers direct access to the complete technical surface. Handoffs preserve the current subject and navigation context.

The short-lived same-data comparison experiment did not preserve a third renderer: it merely relabeled Workbench as “Classic” and later “Legacy.” Those labels were incorrect and are not interface modes.

## Local development

```bash
cd viewer
npm ci
npm run dev
```

Use `?mode=overview` to force the guided entry and `?mode=workbench` to open the detailed workspace. Both modes use the same `data` URL and preserve compatible navigation parameters.
