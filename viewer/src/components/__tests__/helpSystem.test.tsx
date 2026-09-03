import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WALK_STOPS } from "../../orientation/stops";
import { useArchStore } from "../../store";
import type { Architecture } from "../../types";
import { HelpSystem } from "../HelpSystem";

const architecture: Architecture = {
  name: "Fixture",
  description: "A small fixture system.",
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

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
  useArchStore.setState({
    architecture,
    publication: null,
    experienceMode: "workbench",
    helpOpen: true,
    orientationOpen: false,
    orientationInvite: false,
    orientationStep: 0,
    orientationSkipped: [],
  });
});

afterEach(() => cleanup());

describe("HelpSystem", () => {
  it("renders the live orientation stops in the Guide tab", () => {
    render(<HelpSystem />);
    for (const stop of WALK_STOPS.filter((item) => item.viewport !== "mobile")) {
      expect(screen.getByText(stop.heading)).toBeTruthy();
    }
  });

  it("names SysCorpus in About and removes the old product name", () => {
    render(<HelpSystem />);
    fireEvent.click(screen.getByText("about"));
    expect(screen.getAllByText(/SysCorpus/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Architecture Visualizer/)).toBeNull();
  });

  it("closes Help and starts the orientation from replay", () => {
    render(<HelpSystem />);
    act(() => fireEvent.click(screen.getByTestId("orientation-replay")));
    expect(useArchStore.getState().helpOpen).toBe(false);
    expect(useArchStore.getState().orientationOpen).toBe(true);
    expect(useArchStore.getState().orientationStep).toBe(0);
    expect(useArchStore.getState().experienceMode).toBe("overview");
  });
});
