import { describe, it, expect } from "vitest";
import { safeComponentId } from "../utils/componentId";

// Must stay in sync with tests/test_cli.py::TestSafeComponentId.
describe("safeComponentId", () => {
  it("replaces slashes with double-dash", () => {
    expect(safeComponentId("viewer/src")).toBe("viewer--src");
  });

  it("replaces colons with double-underscore", () => {
    expect(safeComponentId("repo:unamentis")).toBe("repo__unamentis");
  });

  it("handles slashes and colons together", () => {
    expect(safeComponentId("repo:unamentis/viewer")).toBe("repo__unamentis--viewer");
  });

  it("leaves plain ids unchanged", () => {
    expect(safeComponentId("plain-id")).toBe("plain-id");
  });
});
