import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { architectureIdentity, loadAnnotations } from "../utils/annotationStorage";
import { parsePublication } from "../utils/publication";
import type { Architecture, Component, Publication } from "../types";

// Annotation-identity guard for the publication display-name feature.
//
// Annotations key on the STABLE projection identity (architecture.name plus
// repository), NEVER on the editable publication.subject.name used only for
// DISPLAY. This test proves that overriding the display name via publication.json
// leaves the annotation storage key untouched, so an edited name can never orphan
// review annotations. It exercises the real store and the real localStorage layer
// (jsdom), no mocks.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "comp-a",
    name: "Component A",
    type: "module",
    path: "src/a",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/a/index.ts"],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: {
      readme: null,
      claude_md: null,
      changelog: null,
      api_docs: null,
      architecture_notes: null,
      purpose: null,
      key_decisions: [],
      patterns: [],
      tech_stack: [],
      env_vars: [],
      api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "projection-folder-name",
    description: "A test project",
    repository: "https://github.com/acme/demo",
    generated_at: "2026-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/demo",
    components: [makeComponent()],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 0,
      total_lines: 0,
      total_size_bytes: 0,
      languages: {},
      total_symbols: 0,
      total_components: 0,
      total_relationships: 0,
    },
    ...overrides,
  };
}

function makePublication(subjectName: string): Publication {
  const pub = parsePublication({
    publication_version: 1,
    publisher: { name: "Acme", contact: "a@b.example" },
    subject: {
      name: subjectName,
      commit: "abc1234",
      snapshot_date: "2026-07-21",
      affiliation: "owner",
    },
    purpose: "documentation",
    update_policy: "continuous",
    header: { banner: "b" },
    footer: { always: ["f"] },
    disclaimers: [],
    access: { visibility: "public", gate: null },
    generated_by: { tool: "solution-explorer", version: "0.0.0" },
  });
  if (!pub) throw new Error("test fixture publication failed validation");
  return pub;
}

describe("publication display name does not affect annotation identity", () => {
  beforeEach(() => {
    localStorage.clear();
    useArchStore.setState({
      architecture: null,
      publication: null,
      annotations: [],
      componentDetailCache: {},
      reviewMode: false,
      activePanel: null,
    });
  });

  it("architectureIdentity depends only on name + repository, not on any display name", () => {
    const arch = makeArchitecture();
    const identity = architectureIdentity(arch);
    // The identity is derived from the projection name, not the editable display
    // name; a totally different display name is irrelevant to the key.
    expect(identity).toContain("projection-folder-name");
    expect(identity).not.toContain("Totally Different Display Name");
  });

  it("keeps the annotation keyed on the projection name even with a display-name override", () => {
    const arch = makeArchitecture();
    useArchStore.getState().setArchitecture(arch);
    // Override the DISPLAY name via a valid publication sidecar.
    useArchStore.getState().setPublication(makePublication("Totally Different Display Name"));

    useArchStore.getState().addAnnotation("comp-a", "keep me keyed on projection identity");
    expect(useArchStore.getState().annotations).toHaveLength(1);

    // The annotation is stored under the projection identity...
    const projectionIdentity = architectureIdentity(arch);
    expect(loadAnnotations(projectionIdentity)).toHaveLength(1);

    // ...and NOT under an identity derived from the publication display name.
    const displayNameIdentity = architectureIdentity({
      name: "Totally Different Display Name",
      repository: arch.repository,
    });
    expect(loadAnnotations(displayNameIdentity)).toHaveLength(0);
  });

  it("restores the annotation after a reload regardless of the publication display name", () => {
    const arch = makeArchitecture();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setPublication(makePublication("Display Name One"));
    useArchStore.getState().addAnnotation("comp-a", "survives across display-name changes");

    // Simulate a reload: wipe in-memory state, keep localStorage.
    useArchStore.setState({ architecture: null, publication: null, annotations: [] });

    // Reload the same projection but with a DIFFERENT display name this time.
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().setPublication(makePublication("Display Name Two"));

    const restored = useArchStore.getState().annotations;
    expect(restored).toHaveLength(1);
    expect(restored[0].text).toBe("survives across display-name changes");
  });
});
