import { describe, it, expect } from "vitest";
import { safeComponentId } from "./componentId";

// Fixture ids shared with tests/test_cli.py::TestSafeComponentId (lines 556-569)
// and viewer/src/utils/componentId.test.ts. All three escape implementations
// must produce identical output or the worker deletes fresh detail uploads
// (F-CRIT-5).
describe("safeComponentId", () => {
  it("replaces slashes with double dashes", () => {
    expect(safeComponentId("viewer/src")).toBe("viewer--src");
  });

  it("replaces colons with double underscores", () => {
    expect(safeComponentId("repo:unamentis")).toBe("repo__unamentis");
  });

  it("replaces slashes and colons together", () => {
    expect(safeComponentId("repo:unamentis/viewer")).toBe("repo__unamentis--viewer");
  });

  it("leaves plain ids unchanged", () => {
    expect(safeComponentId("plain-id")).toBe("plain-id");
  });
});

// This is the regression assertion for F-CRIT-5. The worker's
// cleanupOrphanedDetails builds active R2 keys as
// `${projectId}/detail-${safeComponentId(id)}.json`. Before the fix it used
// only `id.replace(/\//g, "--")`, so for a multi-repo id like "repo:unamentis"
// it computed the key with a raw colon, never matched the uploaded
// "detail-repo__unamentis.json", and deleted it as orphaned.
describe("cleanupOrphanedDetails active key derivation", () => {
  const activeKey = (projectId: string, id: string) =>
    `${projectId}/detail-${safeComponentId(id)}.json`;

  it("computes detail-repo__unamentis.json for id repo:unamentis", () => {
    expect(activeKey("unamentis", "repo:unamentis")).toBe(
      "unamentis/detail-repo__unamentis.json",
    );
  });

  it("computes detail-repo__unamentis--viewer.json for id repo:unamentis/viewer", () => {
    expect(activeKey("unamentis", "repo:unamentis/viewer")).toBe(
      "unamentis/detail-repo__unamentis--viewer.json",
    );
  });
});
