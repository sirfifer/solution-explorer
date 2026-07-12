import { describe, it, expect, vi, beforeEach } from "vitest";
import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Mock the Python and viewer libs so generate() runs without spawning Python
// or touching a real viewer build. buildAnalyzerArgs is kept real (spread from
// the actual module) so the argument-vector test below exercises production code.
vi.mock("../src/lib/python.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/lib/python.js")>();
  return {
    ...actual,
    detectPython: vi.fn().mockResolvedValue("python3"),
    runAnalyzer: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock("../src/lib/viewer.js", () => ({
  assembleStaticSite: vi.fn(),
}));

import { buildAnalyzerArgs, runAnalyzer } from "../src/lib/python.js";
import { assembleStaticSite } from "../src/lib/viewer.js";
import { generate } from "../src/commands/generate.js";

describe("buildAnalyzerArgs", () => {
  it("emits --split for the default (uncapped) CLI path", () => {
    const args = buildAnalyzerArgs("/a/analyze.py", {
      repoPath: "/repo",
      outputPath: "/out/architecture",
      split: true,
    });
    expect(args).toContain("--split");
    // -o must point at the split output directory
    expect(args[args.indexOf("-o") + 1]).toBe("/out/architecture");
    expect(args).toContain("/repo");
    expect(args).toContain("--compact");
  });

  it("omits --split when split is not requested (single-file mode)", () => {
    const args = buildAnalyzerArgs("/a/analyze.py", {
      repoPath: "/repo",
      outputPath: "/out/architecture.json",
    });
    expect(args).not.toContain("--split");
  });

  it("uses --config instead of a positional path in multi-repo mode", () => {
    const args = buildAnalyzerArgs("/a/analyze.py", {
      config: "/repo/solution-explorer.json",
      repoPath: "/repo",
      outputPath: "/out/architecture",
      split: true,
    });
    expect(args).toContain("--config");
    expect(args).toContain("/repo/solution-explorer.json");
    // positional repo path is not passed when a config is used
    expect(args).not.toContain("/repo");
    expect(args).toContain("--split");
  });
});

describe("generate uses split mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (assembleStaticSite as unknown as ReturnType<typeof vi.fn>).mockReset();
  });

  it("invokes the analyzer with split: true and assembles a split site", async () => {
    const outDir = mkdtempSync(join(tmpdir(), "se-generate-test-"));

    await generate({ repoPath: "/some/repo", outputDir: outDir });

    // The analyzer was asked for split output
    const runMock = runAnalyzer as unknown as ReturnType<typeof vi.fn>;
    expect(runMock).toHaveBeenCalledTimes(1);
    const analyzeOptions = runMock.mock.calls[0][1];
    expect(analyzeOptions.split).toBe(true);
    // and the output path is a directory (no .json suffix), so --split writes
    // manifest.json + data/ there
    expect(analyzeOptions.outputPath.endsWith(".json")).toBe(false);

    // The built argv for that call would carry --split
    const builtArgs = buildAnalyzerArgs("/a/analyze.py", analyzeOptions);
    expect(builtArgs).toContain("--split");

    // The site was assembled in split mode
    const assembleMock = assembleStaticSite as unknown as ReturnType<
      typeof vi.fn
    >;
    expect(assembleMock).toHaveBeenCalledTimes(1);
    const assembleArgs = assembleMock.mock.calls[0];
    expect(assembleArgs[2]).toEqual({ split: true });

    // generate created the output directory
    expect(existsSync(outDir)).toBe(true);
  });
});
