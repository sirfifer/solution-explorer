import { describe, it, expect } from "vitest";
import {
  useArchStore,
  flattenTopLevel,
  isContentBlob,
  countSubtreeFiles,
  isPromotedRoot,
  TOP_LEVEL_MIN_COVERAGE,
  PROMOTION_MIN_SHARE,
} from "../store";
import type { Architecture, Component } from "../types";

// The top level and promotion rules the VS Code crawl of 2026-09-02 forced
// (docs/testing/RUN-2026-09-02-vscode-demo-gate.md, P1 and P2).
//
// Fail-before: on the VS Code projection the top level rendered exactly one
// node, `cli`, a 4-file Rust helper that the client/server model found by
// unwrapping the root; src, extensions and test, 99% of the subject, never
// rendered at any level, and hero promotion dissolved src and extensions at
// the root drill level so a tour step naming them had nothing to select.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c",
    name: "C",
    type: "module",
    path: "src/c",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/c/index.ts"],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "T", description: "", repository: null,
    generated_at: "2025-01-01T00:00:00Z", analyzer_version: "1.2.0", root_path: "/t",
    components: [], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

function files(n: number, prefix: string): string[] {
  return Array.from({ length: n }, (_, i) => `${prefix}/f${i}.ts`);
}

// A monorepo in VS Code's shape: a package root whose only hero within reach
// is a tiny cli-tool, beside a huge src module, an extensions folder typed
// content because its own files are json, and a docs blob.
function makeMonorepo() {
  const cli = makeComponent({ id: "cli", name: "cli", type: "cli-tool", files: files(4, "cli") });
  const workbench = makeComponent({ id: "src/vs/workbench", name: "workbench", type: "web-client", files: files(40, "src/vs/workbench") });
  const base = makeComponent({ id: "src/vs/base", name: "base", type: "module", files: files(30, "src/vs/base") });
  const vs = makeComponent({ id: "src/vs", name: "vs", type: "module", files: files(2, "src/vs"), children: [base, workbench] });
  const src = makeComponent({ id: "src", name: "src", type: "module", files: files(3, "src"), children: [vs] });
  const copilotScript = makeComponent({ id: "extensions/copilot/script", name: "script", type: "cli-tool", files: files(2, "extensions/copilot/script") });
  const copilotSrc = makeComponent({ id: "extensions/copilot/src", name: "src", type: "module", files: files(50, "extensions/copilot/src") });
  const copilot = makeComponent({ id: "extensions/copilot", name: "copilot", type: "vscode-extension", files: files(1, "extensions/copilot"), children: [copilotScript, copilotSrc] });
  const git = makeComponent({ id: "extensions/git", name: "git", type: "content", files: ["extensions/git/package.json"], children: [
    makeComponent({ id: "extensions/git/src", name: "src", type: "module", files: files(10, "extensions/git/src") }),
  ] });
  const extensions = makeComponent({ id: "extensions", name: "extensions", type: "content", files: ["extensions/package.json"], children: [copilot, git] });
  const docs = makeComponent({ id: "docs", name: "docs", type: "content", files: ["docs/README.md"], children: [
    makeComponent({ id: "docs/images", name: "images", type: "content", files: ["docs/images/a.png"] }),
  ] });
  const root = makeComponent({ id: "root", name: "code-oss-dev", type: "package", files: ["package.json"], children: [cli, src, extensions, docs] });
  return { arch: makeArchitecture({ components: [root] }), root, cli, src, vs, extensions, copilot, docs };
}

// An app in UnaMentis's shape: the root is itself the client.
function makeAppRepo() {
  const screen = makeComponent({ id: "app/views/home", name: "Home", type: "screen", files: files(3, "app/views/home") });
  const views = makeComponent({ id: "app/views", name: "Views", type: "module", files: files(1, "app/views"), children: [screen] });
  const docs = makeComponent({ id: "docs", name: "docs", type: "content", files: ["docs/a.md"] });
  const root = makeComponent({ id: "root", name: "App", type: "ios-client", files: files(2, "app"), children: [views, docs] });
  return { arch: makeArchitecture({ components: [root] }), root, views, screen };
}

describe("countSubtreeFiles and isContentBlob", () => {
  it("counts a whole subtree, not a component's own files", () => {
    const { src } = makeMonorepo();
    expect(countSubtreeFiles(src)).toBe(3 + 2 + 30 + 40);
  });

  it("treats content as a blob only when nothing beneath it is code", () => {
    const { extensions, docs } = makeMonorepo();
    expect(isContentBlob(docs)).toBe(true);
    expect(isContentBlob(extensions)).toBe(false);
    expect(isContentBlob(extensions.children[1])).toBe(false);
  });
});

describe("the top level accounts for the subject", () => {
  it("falls back to the root's children when the anchors are incidental", () => {
    const { arch, root } = makeMonorepo();
    const top = flattenTopLevel(arch.components, arch.relationships);
    // cli is 4 of 182 files, far below the coverage floor.
    expect(4 / countSubtreeFiles(root)).toBeLessThan(TOP_LEVEL_MIN_COVERAGE);
    expect(top.map((c) => c.id).sort()).toEqual(["cli", "docs", "extensions", "src"]);
    expect(isPromotedRoot(arch.components, arch.relationships, "root")).toBe(true);
  });

  it("renders those children, minus the content blob, with no aggregate needed", () => {
    const { arch } = makeMonorepo();
    useArchStore.getState().setArchitecture(arch);
    const visible = useArchStore.getState().getVisibleComponents().map((c) => c.id).sort();
    expect(visible).toEqual(["cli", "extensions", "src"]);
    expect(useArchStore.getState().getAggregateNodes()).toEqual([]);
  });

  it("keeps the client alone at the top when the client is the subject", () => {
    const { arch } = makeAppRepo();
    const top = flattenTopLevel(arch.components, arch.relationships);
    expect(top.map((c) => c.id)).toEqual(["root"]);
    expect(isPromotedRoot(arch.components, arch.relationships, "root")).toBe(false);
  });

  it("stands the rest of the subject beside anchors that cover it but not all of it", () => {
    const app = makeComponent({ id: "app", name: "App", type: "ios-client", files: files(60, "app") });
    const shared = makeComponent({ id: "packages/shared", name: "shared", type: "library", files: files(20, "packages/shared") });
    const root = makeComponent({ id: "root", name: "Repo", type: "package", files: [], children: [app, shared] });
    const arch = makeArchitecture({ components: [root] });
    const top = flattenTopLevel(arch.components, arch.relationships);
    expect(top.map((c) => c.id)).toEqual(["app", "packages/shared"]);
  });

  it("shows a server with no client instead of nothing", () => {
    const server = makeComponent({ id: "src/flask", name: "flask", type: "api-server", files: files(25, "src/flask") });
    const tests = makeComponent({ id: "tests", name: "tests", type: "module", files: files(50, "tests") });
    const root = makeComponent({ id: "root", name: "flask", type: "package", files: [], children: [server, tests] });
    const arch = makeArchitecture({ components: [root] });
    useArchStore.getState().setArchitecture(arch);
    const visible = useArchStore.getState().getVisibleComponents().map((c) => c.id).sort();
    expect(visible).toEqual(["src/flask", "tests"]);
  });

  it("leaves a hero-less single root as one drillable node, as before", () => {
    const child = makeComponent({ id: "lib/a", name: "a" });
    const root = makeComponent({ id: "root", name: "lib", type: "package", children: [child] });
    const arch = makeArchitecture({ components: [root] });
    expect(flattenTopLevel(arch.components, arch.relationships).map((c) => c.id)).toEqual(["root"]);
  });
});

describe("hero promotion is bounded", () => {
  it("does not dissolve a wrapper for a hero buried beneath it", () => {
    const { arch, root } = makeMonorepo();
    useArchStore.getState().setArchitecture(arch);
    // Drilling into the root shows exactly what the top level shows: src and
    // extensions stay, the web-client three levels down does not replace src.
    useArchStore.getState().drillInto(root);
    const visible = useArchStore.getState().getVisibleComponents().map((c) => c.id).sort();
    expect(visible).toEqual(["cli", "extensions", "src"]);
  });

  it("promotes direct hero children that carry their wrapper", () => {
    const { arch, vs, src } = makeMonorepo();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(src);
    // src/vs holds the workbench (40 of 72 files): it dissolves into workbench and base.
    expect(40 / countSubtreeFiles(vs)).toBeGreaterThanOrEqual(PROMOTION_MIN_SHARE);
    const visible = useArchStore.getState().getVisibleComponents().map((c) => c.id).sort();
    expect(visible).toEqual(["src/vs/base", "src/vs/workbench"]);
  });

  it("keeps a wrapper whose direct hero is incidental", () => {
    const { arch, extensions } = makeMonorepo();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(extensions);
    // copilot's cli-tool script is 2 of 53 files; copilot stays a node and the
    // content-typed git extension with code inside is not filtered.
    const visible = useArchStore.getState().getVisibleComponents().map((c) => c.id).sort();
    expect(visible).toEqual(["extensions/copilot", "extensions/git"]);
  });

  it("never dissolves the component the reader was sent to", () => {
    const { arch, root } = makeAppRepo();
    useArchStore.getState().setArchitecture(arch);
    // Views carries a screen that is 3 of 4 files, so it normally dissolves.
    useArchStore.getState().drillInto(root);
    expect(useArchStore.getState().getVisibleComponents().map((c) => c.id)).toEqual(["app/views/home"]);
    // A tour step naming Views itself must find Views on the canvas.
    useArchStore.getState().navigateToComponent("app/views");
    expect(useArchStore.getState().drillLevel).toBe("root");
    expect(useArchStore.getState().getVisibleComponents().map((c) => c.id)).toContain("app/views");
  });
});

describe("navigating onto a promoted root's child", () => {
  it("lands on the top level, not on a drill into the root", () => {
    const { arch } = makeMonorepo();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().navigateToComponent("src");
    expect(useArchStore.getState().drillLevel).toBeNull();
    expect(useArchStore.getState().selectedComponentId).toBe("src");
    expect(useArchStore.getState().getVisibleComponents().map((c) => c.id)).toContain("src");
  });

  it("still drills to the parent when the root is not promoted", () => {
    const { arch } = makeAppRepo();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().navigateToComponent("app/views/home");
    expect(useArchStore.getState().drillLevel).toBe("app/views");
  });
});
