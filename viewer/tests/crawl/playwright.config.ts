import { defineConfig, devices } from "@playwright/test";

/**
 * The deterministic GUI crawl (design authority: README.md in this directory).
 *
 * This is the scripted counterpart to viewer/tests/gui/, not a replacement for
 * it. The AI-operated plan judges whether a surface reads correctly to a human;
 * this crawl proves, mechanically and exhaustively, that everything the data
 * says exists is reachable in the UI and renders without erroring. The two
 * answer different questions and neither subsumes the other.
 *
 * Configured by environment so one suite runs against any dataset:
 *
 *   CRAWL_SERVE_DIR   directory to serve (an assembled root from
 *                     scripts/gui-datasets.py assemble). When set, Playwright
 *                     starts the static server itself.
 *   CRAWL_BASE_URL    an already-running origin to crawl instead.
 *   CRAWL_DATA_DIR    the projection directory on disk, read to build the
 *                     expectation model. Defaults to
 *                     <CRAWL_SERVE_DIR>/architecture.
 *   CRAWL_MAX_COMPONENTS  budget for the per-component sweeps. 0 means all.
 *                     Whatever is dropped is logged by name count, never
 *                     silently.
 *   CRAWL_ALLOW_ERRORS  comma-separated URL path fragments that may 404. The
 *                     default list mirrors datasets.yaml's probe inventory for
 *                     a split-layout dataset.
 */

const serveDir = process.env.CRAWL_SERVE_DIR;
const baseURL = process.env.CRAWL_BASE_URL ?? "http://127.0.0.1:4180";
const port = Number(new URL(baseURL).port || 4180);

export default defineConfig({
  testDir: ".",
  // The sweeps are long by construction (one navigation per component, then one
  // click per tab it offers), so the per-test timeout is generous while the
  // per-action timeout below stays tight: a slow suite is acceptable, a hung
  // assertion is not. At VS Code's scale (573 components, ten-ish tabs each)
  // a full unbudgeted tab sweep is an hour-scale job, which is why this is
  // measured in hours rather than minutes.
  timeout: 2 * 60 * 60 * 1000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["json", { outputFile: "results/crawl-results.json" }],
    // Publishes the run to the testboard as it happens, so whoever wants to
    // watch can, whether or not they are the one who started it.
    ["./testboard-reporter.ts"],
  ],
  outputDir: "results/artifacts",
  use: {
    baseURL,
    ...devices["Desktop Chrome"],
    // Both are load bearing. Playwright's default action timeout is "wait
    // forever", so a click on an element that never becomes actionable hangs
    // the whole run with no output at all rather than failing the case. The
    // first crawl run did exactly that; a bounded action is what turns a
    // stuck UI into a reported defect.
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: serveDir
    ? {
        command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory ${serveDir}`,
        url: baseURL,
        reuseExistingServer: true,
        // http.server logs every request to stderr; piping it drowns the test
        // output. Failed requests are policed by the recorder, from the page
        // side, which is where the allowlist lives anyway.
        stdout: "ignore",
        stderr: "ignore",
      }
    : undefined,
});
