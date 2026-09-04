import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InterfacePreview } from "../components/InterfacePreview";
import type { UISurfacesProjection } from "../types";

const surfaces: UISurfacesProjection = {
  schema: "syscorpus.ui-surfaces/v1",
  subject: { repository: "https://example.test/repo", commit: "subject-commit" },
  clients: [{
    id: "desktop", label: "Desktop", kind: "desktop-app", platforms: ["macos"],
    primary: true, coverage: "captured",
  }, {
    id: "web", label: "Web", kind: "web-app", platforms: ["browser"],
    primary: false, coverage: "missing", note: "Not captured yet",
  }],
  screens: [{
    id: "desktop:main", client_id: "desktop", label: "Main workbench", role: "primary",
    image: { path: "ui-surfaces/main.png", sha256: "abc", width: 1440, height: 900 },
    capture: {
      captured_at: "2026-09-04T00:00:00Z", method: "playwright-electron",
      runtime_name: "Visual Studio Code", runtime_version: "1.0", runtime_commit: "runtime-commit",
      source_match: "representative", sanitized: true,
    },
    hotspots: [{
      id: "editor", label: "Editor area", kind: "region",
      rect: { x: 0.2, y: 0.1, width: 0.6, height: 0.8 },
      evidence: { component_id: "workbench", file: "src/editor.ts", line: 100, symbol: "EditorPart" },
      action: { kind: "open_source" },
    }],
  }],
};

describe("InterfacePreview", () => {
  it("shows an honestly labelled real capture and opens hotspot evidence", () => {
    const openSource = vi.fn();
    render(<InterfacePreview surfaces={surfaces} expectsInterface darkMode={false} onOpenSource={openSource} />);
    expect(screen.getByTestId("interface-preview").getAttribute("data-source-match")).toBe("representative");
    expect(screen.getByTestId("capture-provenance").textContent).toBe("Representative runtime");
    expect(screen.getByTestId("interface-client-coverage").textContent).toContain("Desktop · captured");
    expect(screen.getByTestId("interface-client-coverage").textContent).toContain("Web · missing");
    expect(screen.getByAltText("Visual Studio Code Main workbench interface capture").getAttribute("src")).toContain("ui-surfaces/main.png");

    const hotspot = screen.getAllByRole("button", { name: /Editor area/ })[0];
    fireEvent.click(hotspot);
    expect(openSource).toHaveBeenCalledWith(surfaces.screens[0].hotspots[0]);
  });

  it("records the missing capture instead of inventing a diagram", () => {
    render(<InterfacePreview expectsInterface darkMode onOpenSource={() => undefined} />);
    expect(screen.getByTestId("interface-preview-missing").textContent).toContain("No verified screenshot is attached");
  });

  it("adds no empty capture furniture to a non-UI subject", () => {
    const { container } = render(<InterfacePreview expectsInterface={false} darkMode={false} onOpenSource={() => undefined} />);
    expect(container.innerHTML).toBe("");
  });
});
