import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useArchStore } from "../store";
import { buildOrientationFallback } from "../utils/orientation";
import { SystemOverview } from "../components/SystemOverview";
import identityFixture from "./fixtures/orientation-identity.json";
import type { Architecture, Component, OrientationProjection } from "../types";

/**
 * The front door a first-time reader lands on.
 *
 * The claim under test is not "the component renders": it is that the page
 * opens on what the system IS, that every new statement on it carries where it
 * came from, and that a bundle written before the identity pass still renders
 * exactly as it used to.
 */

function component(id: string, type = "module", children: Component[] = []): Component {
  return {
    id, name: id, type, path: `src/${id}`, language: "typescript", framework: null,
    description: null, port: null, children, files: [], entry_points: [], config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
  };
}

function architecture(): Architecture {
  return {
    name: "Visual Studio Code",
    description: "A snapshot of the source at the recorded commit.",
    repository: null,
    generated_at: "2026-09-03T00:00:00Z",
    analyzer_version: "2.0.0",
    root_path: "/vscode",
    components: [component("src/vs/workbench", "web-client"), component("cli", "cli-tool")],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 15204, total_lines: 4921023, total_size_bytes: 0, languages: {},
      total_symbols: 151134, total_components: 571, total_relationships: 5453,
    },
    activity: { provenance: { git: true, shallow: false, head: "474a349ad5b745e512ef86b864d1c74f7264dd7a", commits: 1, first_commit: null, last_commit: null } },
  } as unknown as Architecture;
}

/** The orientation sidecar shape the analyzer now writes, from the fixture. */
function orientationWithIdentity(): OrientationProjection {
  const base = buildOrientationFallback(architecture());
  const fixture = identityFixture as unknown as Record<string, unknown>;
  const nodes = base.portrait.nodes.map((node, index) => ({
    ...node,
    ...(index === 0 ? (fixture.portrait_node_additions as object) : {}),
  }));
  return {
    ...base,
    identity: fixture.identity as never,
    portrait: { ...base.portrait, nodes },
    orientation: {
      ...base.orientation,
      interpreted_statement: {
        text: "An editor built on Electron with a browser renderer, Node and web-worker targets.",
        status: "interpreted",
        provenance: { derived_from_commit: "474a349", stale: false },
      },
      default_path: {
        ...base.orientation.default_path,
        ...(fixture.default_path_addition as object),
      },
    },
  } as OrientationProjection;
}

function renderOverview(orientation: OrientationProjection | null) {
  const arch = architecture();
  if (orientation) arch.orientation = orientation;
  useArchStore.setState({
    architecture: arch,
    experienceMode: "overview",
    overviewDirection: "portrait",
    darkMode: false,
  });
  return render(<SystemOverview displayName="Visual Studio Code" />);
}

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, "", "/");
  useArchStore.setState({
    experienceMode: "overview",
    overviewDirection: "portrait",
    darkMode: false,
    architecture: null,
    trustOpen: false,
  });
});

describe("the identity front door", () => {
  it("titles the page with the subject and says what it is underneath", () => {
    const { container } = renderOverview(orientationWithIdentity());
    // The title names the system once. The subtitle does not say it again.
    expect(container.querySelector("h2")?.textContent).toBe("Visual Studio Code");
    const headline = screen.getByTestId("identity-statement");
    expect(headline.textContent).toBe(
      "A desktop application for macOS, Windows and Linux, that also runs in a " +
        "web browser, is driven from a terminal by a command-line tool, and is " +
        "extended by plug-ins. It is written mostly in TypeScript, with Rust.",
    );
    expect(headline.tagName).toBe("P");
  });

  it("does not repeat the counts sentence once the identity leads", () => {
    const { container } = renderOverview(orientationWithIdentity());
    expect(container.textContent).not.toContain("mapped components across");
  });

  it("offers one chip per form factor, each marked as observed", () => {
    renderOverview(orientationWithIdentity());
    const chips = screen.getAllByTestId("form-factor");
    expect(chips).toHaveLength(4);
    expect(chips.map((chip) => chip.getAttribute("data-kind"))).toEqual([
      "desktop-app", "web-app", "cli", "plugin-host",
    ]);
    expect(chips[0].textContent).toContain("Desktop application");
    expect(chips[0].textContent).toContain("macOS, Windows, Linux");
    expect(chips[0].textContent).toContain("Observed source reference");
  });

  it("shows the file and line behind a chip when it is opened, and closes on Escape", () => {
    renderOverview(orientationWithIdentity());
    const desktop = screen.getAllByTestId("form-factor")[0];
    expect(screen.queryByTestId("form-factor-evidence")).toBeNull();

    fireEvent.click(desktop);
    const evidence = screen.getByTestId("form-factor-evidence");
    expect(evidence.textContent).toContain("product.json:30");
    expect(evidence.textContent).toContain("darwinBundleIdentifier");
    expect(evidence.textContent).toContain("package.json:188");
    expect(evidence.textContent).toContain("devDependencies.electron");
    expect(desktop.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("form-factor-evidence")).toBeNull();
  });

  it("offers the workbench only from a chip that names a component", () => {
    renderOverview(orientationWithIdentity());
    const chips = screen.getAllByTestId("form-factor");
    fireEvent.click(chips[0]); // desktop-app, component_id "root"
    expect(screen.queryByText(/Open in workbench/)).toBeNull();

    fireEvent.click(chips[0]);
    fireEvent.click(chips[1]); // web-app, component_id "src/vs/workbench"
    expect(screen.getByText(/Open in workbench/)).toBeTruthy();
  });

  it("quotes the maintainers and says whose claim it is", () => {
    renderOverview(orientationWithIdentity());
    const quote = screen.getByTestId("authors-claim");
    expect(quote.textContent).toContain("This repository");
    expect(quote.textContent).toContain("Microsoft");
    const caption = quote.parentElement?.querySelector("figcaption");
    expect(caption?.textContent).toContain("README.md");
    expect(caption?.textContent).toContain("Repository claim");
    expect(caption?.textContent).toContain("474a349");
  });

  it("demotes the interpreted summary out of the headline", () => {
    const { container } = renderOverview(orientationWithIdentity());
    const summary = container.querySelector("details > summary");
    expect(summary?.textContent).toBe("Interpreted summary");
    expect(screen.getByTestId("identity-statement").textContent).not.toContain("Electron");
  });

  it("keeps the counts out of the first viewport and one click from the ledger", () => {
    const { container } = renderOverview(orientationWithIdentity());
    expect(container.querySelectorAll('[data-se="stat"]')).toHaveLength(0);
    const line = screen.getByTestId("scale-summary");
    expect(line.textContent).toContain("571 components");
    expect(line.textContent).toContain("15,204 files");
    expect(line.textContent).toContain("5,453 relationships");

    fireEvent.click(line);
    expect(useArchStore.getState().trustOpen).toBe(true);
  });

  it("names a representative component on the area cards it has one for", () => {
    renderOverview(orientationWithIdentity());
    const cards = screen.getAllByTestId("portrait-card");
    expect(cards[0].textContent).toContain("Workbench");
    expect(cards[0].textContent).toContain("Workbench: the desktop-editor UI shell");
    expect(cards[0].textContent).toContain("interpreted");
    expect(cards[0].textContent).toContain("28%");
    // A node the analyzer gave no representative still renders its role, as
    // before, rather than an empty card.
    expect(cards[1].textContent).not.toContain("interpreted");
    expect(cards[1].textContent).toContain("components");
  });

  it("keeps the posture chooser and every hook the crawl reads", () => {
    const { container } = renderOverview(orientationWithIdentity());
    const directions = container.querySelectorAll('[data-testid="overview-direction"]');
    expect([...directions].map((el) => el.getAttribute("data-direction"))).toEqual([
      "portrait", "questions", "atlas",
    ]);
    expect(directions[0].getAttribute("data-selected")).toBe("true");
    expect(screen.getByText("Other ways in")).toBeTruthy();
    expect(container.querySelector('[data-testid="system-overview"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="open-workbench"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="search-button"]')).toBeTruthy();
  });
});

describe("a bundle written before the identity pass", () => {
  it("keeps its old headline and grows no empty identity furniture", () => {
    const { container } = renderOverview(null);
    expect(screen.queryByTestId("identity-statement")).toBeNull();
    expect(screen.queryAllByTestId("form-factor")).toHaveLength(0);
    expect(screen.queryByTestId("authors-claim")).toBeNull();
    // The old opening statement still leads.
    expect(container.querySelector("h2")?.textContent).toBe(
      "A snapshot of the source at the recorded commit.",
    );
    // The count line replaces the tiles regardless of identity.
    expect(container.querySelectorAll('[data-se="stat"]')).toHaveLength(0);
    expect(screen.getByTestId("scale-summary")).toBeTruthy();
  });

  it("emits a null identity from the browser fallback rather than guessing", () => {
    expect(buildOrientationFallback(architecture()).identity).toBeNull();
  });
});
