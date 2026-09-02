# SysCorpus viewer interfaces

The React viewer contains two interfaces over the same projection and route state.

| Interface | Status | Purpose |
|---|---|---|
| **Overview** (`?mode=overview`) | **Primary and default** | Comprehension-first system portrait, guided questions, bounded atlas entry, and trust context. |
| **Legacy workspace** (`?mode=workbench`) | **Deprecated; temporary** | Historical comparison, deep-link compatibility, and validation while remaining flows move into the primary interface. |

`workbench` remains the internal route value so existing links continue to work. It is not a second product direction. New product work belongs in Overview or in shared components that Overview opens. The legacy workspace should receive only compatibility, security, accessibility, and validation fixes.

The legacy interface can be removed only after its required routes have primary-interface equivalents, existing deep links have a migration path, and parity tests no longer depend on it.

## Local development

```bash
cd viewer
npm ci
npm run dev
```

Use `?mode=overview` to force the primary interface and `?mode=workbench` to exercise the deprecated surface. Both modes use the same `data` URL and preserve compatible navigation parameters.
