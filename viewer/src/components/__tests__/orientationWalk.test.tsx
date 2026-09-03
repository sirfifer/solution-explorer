import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NavStateBeacon } from "../../App";
import { useArchStore } from "../../store";
import type { Architecture } from "../../types";
import { OrientationWalk } from "../OrientationWalk";

const architecture: Architecture = {
  name: "Fixture",
  description: "A fixture",
  repository: null,
  generated_at: "2026-09-03T00:00:00Z",
  analyzer_version: "1.2.0",
  root_path: "/fixture",
  components: [],
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
};

function Harness() {
  const mode = useArchStore((state) => state.experienceMode);
  return (
    <>
      <NavStateBeacon />
      {mode === "overview" ? (
        <div>
          <div data-testid="overview-title" />
          <div data-testid="identity-statement" />
          <div data-testid="question-routes" />
          <div data-testid="experience-switcher" />
          <div data-testid="overview-trust-button" />
          <div data-testid="header-tools" />
        </div>
      ) : (
        <div>
          <div data-testid="graph-frame" />
          <div data-testid="lens-select" />
          <div data-testid="help-button" />
          <div data-testid="more-menu" />
        </div>
      )}
      <OrientationWalk />
    </>
  );
}

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 768 });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(() => ({
    top: 100,
    left: 100,
    right: 220,
    bottom: 160,
    width: 120,
    height: 60,
    x: 100,
    y: 100,
    toJSON: () => ({}),
  }));
  HTMLElement.prototype.scrollIntoView = vi.fn();
  localStorage.clear();
  useArchStore.setState({
    architecture,
    publication: null,
    experienceMode: "overview",
    orientationOpen: false,
    orientationInvite: true,
    orientationStep: 0,
    orientationSkipped: [],
    helpOpen: false,
    activeTourId: null,
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("OrientationWalk", () => {
  it("crosses into the workbench and records completion", async () => {
    render(<Harness />);
    act(() => useArchStore.getState().startOrientation());

    await waitFor(() => expect(screen.getByTestId("nav-state").getAttribute("data-orientation")).toBe("what-this-is"));
    expect(screen.getByTestId("nav-state").getAttribute("data-orientation-step")).toBe("1");

    for (const expected of [
      "start-with-a-question",
      "two-views",
      "how-much-was-read",
      "your-tools",
      "the-map",
    ]) {
      fireEvent.click(await screen.findByTestId("orientation-next"));
      await waitFor(() => expect(screen.getByTestId("nav-state").getAttribute("data-orientation")).toBe(expected));
    }

    expect(useArchStore.getState().experienceMode).toBe("workbench");
    fireEvent.click(await screen.findByTestId("orientation-next"));
    fireEvent.click(await screen.findByTestId("orientation-next"));
    fireEvent.click(await screen.findByTestId("orientation-done"));

    expect(localStorage.getItem("arch-viz-orientation-v1")).toBe("done");
    expect(screen.getByTestId("nav-state").getAttribute("data-orientation")).toBe("");
    expect(screen.getByTestId("nav-state").getAttribute("data-orientation-invite")).toBe("false");
  });
});
