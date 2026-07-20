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

describe("sanitizer battery (adversarial-review blocker: allowlist shape)", () => {
  const hostile = [
    "\\\\evil.com",
    "\\/evil.com",
    "%5C%5Cevil.com",
    "%5C/evil.com",
    "..%2fsecret",
    "%2e%2e/secret",
    "..%5csecret",
    "jAvAsCrIpT:alert(1)",
    "data:text/html,x",
    "blob:https://x",
    "./architecture/../secret",
    "./architecture/members/UPPER",
    "./architecture/members/a b",
    "members/web",
    "architecture/members/web",
  ];
  it.each(hostile)("rejects %s", (value) => {
    expect(getDataBase(`?data=${encodeURIComponent(value)}`)).toBe("./architecture");
    expect(getDataBase(`?data=${value}`)).toBe("./architecture");
  });

  it("accepts exactly the solution member shapes", () => {
    expect(getDataBase("?data=./architecture/members/web")).toBe("./architecture/members/web");
    expect(getDataBase("?data=./architecture/members/ios-app/")).toBe("./architecture/members/ios-app");
    expect(getDataBase("?data=./architecture")).toBe("./architecture");
  });
});
