import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StructuredExplanation } from "../components/StructuredExplanation";

afterEach(cleanup);

describe("StructuredExplanation", () => {
  it("renders audited atoms as labeled sections instead of the legacy blob", () => {
    render(
      <StructuredExplanation
        explanation={{
          purpose: { text: "Declares workbench commands." },
          mechanism: {
            text: "Registers Action2 subclasses.",
            evidence: [{ path: "src/actions.ts", line: 12, symbol: "OpenFileAction" }],
          },
          place: { text: "Lives below the workbench browser layer." },
        }}
        fallback="Purpose. Mechanism. Place."
        showEvidence
      />,
    );

    const explanation = screen.getByTestId("structured-explanation");
    expect(explanation.getAttribute("data-structured")).toBe("true");
    expect(within(explanation).getByRole("heading", { name: "Purpose" })).toBeDefined();
    expect(within(explanation).getByRole("heading", { name: "How it works" })).toBeDefined();
    expect(within(explanation).getByRole("heading", { name: "Place in the system" })).toBeDefined();
    expect(within(explanation).getByText("Purpose. Mechanism. Place.").closest("details")?.open).toBe(false);
    expect(within(explanation).getByText("Evidence (1)")).toBeDefined();
    expect(within(explanation).getByText("src/actions.ts:12 · OpenFileAction")).toBeDefined();
  });

  it("keeps old projections readable and exposes honest gaps", () => {
    render(
      <StructuredExplanation
        fallback="Legacy explanation remains intact."
        honestGaps={[{ question: "why_matters", why: "The available evidence does not establish impact." }]}
      />,
    );

    const explanation = screen.getByTestId("structured-explanation");
    expect(explanation.getAttribute("data-structured")).toBe("false");
    expect(within(explanation).getByRole("heading", { name: "Overview" })).toBeDefined();
    expect(within(explanation).getByText("Legacy explanation remains intact.")).toBeDefined();
    expect(within(explanation).getByRole("region", { name: "Not established" })).toBeDefined();
    expect(within(explanation).getByText("Why it matters")).toBeDefined();
  });

  it("separates rejected references from supporting evidence and preserves the reason", () => {
    render(<StructuredExplanation explanation={{ mechanism: {
      text: "Registers commands.", evidence: [
        { kind: "symbol", path: "commands.ts", symbol: "register" },
        { kind: "compact-invalid", raw_citation: ["missing.ts", "dispatch"], reason: "Outside the supplied source menu." },
      ],
    } }} showEvidence />);
    expect(screen.getByText("Evidence (1) · 1 rejected")).toBeDefined();
    expect(screen.getByText("Rejected references")).toBeDefined();
    expect(screen.getByText("Outside the supplied source menu.")).toBeDefined();
  });

  it("preserves authored paragraphs and does not invent an empty overview for gaps alone", () => {
    const view = render(<StructuredExplanation fallback={"First paragraph.\n\nSecond paragraph."} />);
    expect(view.container.querySelectorAll("p.se-info-body")).toHaveLength(2);
    view.rerender(<StructuredExplanation honestGaps={[{ question: "purpose", why: "Not documented." }]} />);
    expect(screen.queryByRole("heading", { name: "Overview" })).toBeNull();
  });
});
