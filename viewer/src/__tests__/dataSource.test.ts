import { describe, it, expect } from "vitest";
import {
  DEFAULT_DATA_BASE,
  getDataBase,
  dataUrl,
  isMemberView,
  memberDataUrl,
} from "../utils/dataSource";

describe("dataSource base resolution", () => {
  it("defaults to ./architecture with no param", () => {
    expect(getDataBase("")).toBe(DEFAULT_DATA_BASE);
    expect(getDataBase("?foo=bar")).toBe(DEFAULT_DATA_BASE);
  });

  it("accepts a relative member path and strips the trailing slash", () => {
    expect(getDataBase("?data=./architecture/members/web/")).toBe(
      "./architecture/members/web",
    );
    expect(getDataBase("?data=./architecture/members/web")).toBe(
      "./architecture/members/web",
    );
  });

  it("rejects absolute, protocol-relative, root-absolute, and traversal bases", () => {
    expect(getDataBase("?data=https://evil.example/x")).toBe(DEFAULT_DATA_BASE);
    expect(getDataBase("?data=//evil.example/x")).toBe(DEFAULT_DATA_BASE);
    expect(getDataBase("?data=/etc/passwd")).toBe(DEFAULT_DATA_BASE);
    expect(getDataBase("?data=./architecture/../../secret")).toBe(DEFAULT_DATA_BASE);
    expect(getDataBase("?data=file:///etc/passwd")).toBe(DEFAULT_DATA_BASE);
  });

  it("resolves projection-relative fetch paths against the base", () => {
    expect(dataUrl("manifest.json", "")).toBe("./architecture/manifest.json");
    expect(dataUrl("data/detail-x.json", "?data=./architecture/members/web")).toBe(
      "./architecture/members/web/data/detail-x.json",
    );
    expect(dataUrl("/coverage.json", "")).toBe("./architecture/coverage.json");
  });

  it("reports member view only for a non-default base", () => {
    expect(isMemberView("")).toBe(false);
    expect(isMemberView("?data=./architecture/members/web")).toBe(true);
  });
});

describe("memberDataUrl", () => {
  it("builds a ?data= link joining the solution base and member projection", () => {
    const href = memberDataUrl("members/web/", DEFAULT_DATA_BASE);
    const params = new URLSearchParams(href.replace(/^\?/, ""));
    expect(params.get("data")).toBe("./architecture/members/web");
  });
});
