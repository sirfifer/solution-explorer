import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { GapsBanner } from "../components/GapsBanner";
import { ChangelogPanel } from "../components/ChangelogPanel";
import { useArchStore } from "../store";
import type { Architecture, ProducerGap, ChangelogEntry } from "../types";

// Honesty-surface fixes from the first GUI regression run (findings V9.2,
// V11.1, V3.1). Each test drives the real store and the real component. The
// changelog test also asserts the owner's notification-persistence principle:
// an important notice clears only on a view/clear action, never on a timer.

function makeArch(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "Demo",
    description: "demo",
    repository: null,
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/demo",
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
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  useArchStore.setState({ architecture: null, changelogReadState: { w: 0, r: [] } });
});

describe("GapsBanner (V9.2: producer gaps must surface visibly)", () => {
  const gaps: ProducerGap[] = [
    { producer: "derive.capabilities", stage: "derive", status: "failed", reason: "unit could not finish" },
    { producer: "project.emitters.activity", stage: "project", status: "failed", reason: "emitter raised" },
  ];

  it("renders nothing when the dataset carries no gaps (byte-parity on clean runs)", () => {
    useArchStore.setState({ architecture: makeArch() });
    const { container } = render(<GapsBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the gap count and, when expanded, every producer, stage, and reason", () => {
    useArchStore.setState({ architecture: makeArch({ gaps }) });
    render(<GapsBanner />);
    // This drives GapsBanner in isolation; the App-level wiring (App.tsx) is
    // exercised by GUI plan case V9.2 (covers: component:GapsBanner). A revert
    // of the component's body fails this; a revert of only the App import is
    // caught by the plan, not here.
    expect(screen.getByText(/2 producer gaps/)).toBeTruthy();
    // Collapsed: producers not yet listed.
    expect(screen.queryByText("derive.capabilities")).toBeNull();
    fireEvent.click(screen.getByTestId("gaps-banner"));
    expect(screen.getByText("derive.capabilities")).toBeTruthy();
    expect(screen.getByText("project.emitters.activity")).toBeTruthy();
    expect(screen.getByText("unit could not finish")).toBeTruthy();
    expect(screen.getAllByTestId("gaps-entry")).toHaveLength(2);
  });
});

describe("ChangelogPanel (V11.1: unread badge must persist until viewed, not on a timer)", () => {
  const entry: ChangelogEntry = {
    serial: 1,
    scan_type: "full",
    timestamp: "2025-01-01T00:00:00Z",
    summary: "82 components added",
    changes: [{ kind: "component_added", target_id: "x", target_name: "x", target_type: "module", detail: "added" }],
  };

  it("keeps the unread badge past any timer and clears it only when the entry is viewed", () => {
    vi.useFakeTimers();
    try {
      useArchStore.setState({
        architecture: makeArch({ changelog: [entry], changelog_serial: 1 }),
        changelogReadState: { w: 0, r: [] },
      });
      render(<ChangelogPanel />);
      expect(screen.getByText("1")).toBeTruthy(); // unread badge

      // Forward guard against re-introducing any time-based auto-read: advance
      // fake time well past the old 2s mark and require the badge to persist.
      // (The old code used an IntersectionObserver timer, which jsdom does not
      // provide, so it would also fail this test by throwing on mount; either
      // way the timer path is gone.)
      vi.advanceTimersByTime(10000);
      expect(screen.getByText("1")).toBeTruthy();

      // The view action (expanding the entry) clears it.
      fireEvent.click(screen.getByText("82 components added"));
      expect(screen.queryByText("1")).toBeNull();
      expect(useArchStore.getState().getUnreadChangelogCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears the badge on the explicit Mark all as read action", () => {
    useArchStore.setState({
      architecture: makeArch({ changelog: [entry], changelog_serial: 1 }),
      changelogReadState: { w: 0, r: [] },
    });
    render(<ChangelogPanel />);
    expect(screen.getByText("1")).toBeTruthy();
    fireEvent.click(screen.getByText("Mark all as read"));
    expect(screen.queryByText("1")).toBeNull();
  });
});
